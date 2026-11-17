"""Serialize receipt, snapshot fencing and response decisions under the Zone lock."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.commands import (
    STOP_PENDING,
    WAITING,
    context_matches,
    expire_or_cancel,
    latest,
    mark_granted,
    start_block_reason,
    start_message,
    stop_message,
    waiting_start,
)
from app.domain.migarden.models import BootRecord, ReportRecord, ZoneState
from app.domain.migarden.reports import ingest_reports, observe_active
from app.domain.migarden.storage import config_record, get_config
from app.domain.migarden.wire import CLOCK_LEAD, HOLDOFF, ExchangeIn, ExchangeOut, Snapshot


async def boot_seen(db: AsyncSession, boot_id: str) -> str | None:
    return await db.scalar(select(BootRecord.boot_id).where(BootRecord.boot_id == boot_id))


async def observe_snapshot(
    db: AsyncSession, zone: ZoneState, packet: ExchangeIn, now: datetime
) -> bool:
    snapshot = packet.snapshot
    payload = snapshot.model_dump(mode="json")
    observed = snapshot.observed_at
    if snapshot.time_quality == "unknown" or observed is None or observed > now + CLOCK_LEAD:
        observed = None

    if packet.boot_id != zone.boot_id:
        if await boot_seen(db, packet.boot_id):
            return False
        # Do not let delayed traffic from an unseen older boot displace a current boot.
        if zone.boot_id is not None and (
            observed is None
            or observed < now - HOLDOFF
            or (zone.last_observed_at is not None and observed <= zone.last_observed_at)
        ):
            return False
        db.add(BootRecord(boot_id=packet.boot_id, first_seen_at=now))
        zone.boot_id = packet.boot_id
        zone.control_epoch = packet.control_epoch
        zone.last_observed_at = None
        zone.preview = None
    elif zone.control_epoch is not None and packet.control_epoch < zone.control_epoch:
        return False

    zone.last_seen_at = now
    higher_epoch = zone.control_epoch is not None and packet.control_epoch > zone.control_epoch
    if higher_epoch:
        zone.control_epoch = packet.control_epoch
        zone.preview = None
    if observed is not None and zone.last_observed_at is not None:
        if observed < zone.last_observed_at and not higher_epoch:
            return False
        if observed == zone.last_observed_at and not higher_epoch:
            # A legitimate immediate candidate receipt can coincide with the same
            # timestamp. It may use the current snapshot; it does not refresh it.
            return zone.snapshot == payload
    if observed is not None:
        zone.last_observed_at = observed
    if observed is None and payload == zone.snapshot and not higher_epoch:
        return True
    zone.snapshot = payload
    zone.snapshot_received_at = now
    return True


async def confirm_applied(
    db: AsyncSession, zone: ZoneState, snapshot: Snapshot, now: datetime
) -> None:
    ref = snapshot.applied_config_ref
    if ref is None or ref == zone.applied_ref or await config_record(db, ref) is None:
        return
    # Report provenance alone cannot regress applied; an accepted current snapshot
    # must corroborate the exact ref. A lost report can be sent after a reboot.
    proof = await db.scalar(
        select(ReportRecord.event_id)
        .where(ReportRecord.kind == "config_applied", ReportRecord.config_ref == ref)
        .limit(1)
    )
    if proof is not None:
        zone.applied_ref, zone.applied_confirmed_at = ref, now


async def exchange(
    db: AsyncSession, zone: ZoneState, packet: ExchangeIn, now: datetime
) -> ExchangeOut:
    current_observation = await observe_snapshot(db, zone, packet, now)
    acked = await ingest_reports(db, packet.reports, now)
    if current_observation:
        await confirm_applied(db, zone, packet.snapshot, now)
        await observe_active(db, zone, packet.snapshot, packet.boot_id)
    current_boot = zone.boot_id == packet.boot_id
    desired = None
    if (
        zone.desired_ref is not None
        and zone.desired_ref != packet.snapshot.applied_config_ref
        and (current_boot or await boot_seen(db, packet.boot_id) is None)
    ):
        desired = await get_config(db, zone.desired_ref)

    candidates, grants, stops = [], [], []
    stopping = await latest(db, "stop")
    if stopping and stopping.status in STOP_PENDING:
        if stopping.boot_id == zone.boot_id and current_boot:
            # STOP is deliverable even on a stale/untrusted clock or a busy/blocked
            # device. The Controller deduplicates the same ID and prioritizes CLOSE.
            stops.append(stop_message(stopping))
        elif (
            current_observation
            and packet.snapshot.output == "off"
            and packet.snapshot.active_session is None
            and stopping.boot_id != zone.boot_id
        ):
            stopping.status, stopping.reason = "stop_stale", "new_boot_reported_off"

    pending = await waiting_start(db)
    if pending is not None:
        expire_or_cancel(pending, now)
        if pending.status in WAITING and (not context_matches(pending, zone) or stops):
            expire_or_cancel(
                pending, now, cancel="context_changed" if not stops else "canceled_by_stop"
            )
        if pending.status in WAITING and current_observation:
            reason = await start_block_reason(db, zone, now, ignore_waiting=True)
            if reason:
                pending.status, pending.reason = "rejected", reason
            elif pending.status == "received":
                grants.append(mark_granted(pending))
            else:
                pending.candidate_offered_at = pending.candidate_offered_at or now
                candidates.append(start_message(pending))
    return ExchangeOut(
        server_time=now,
        desired_config=desired,
        candidates=candidates,
        grants=grants,
        stops=stops,
        acked_event_ids=acked,
    )
