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
from app.domain.migarden.reconciliation import reconcile
from app.domain.migarden.reports import ingest_reports, observe_active
from app.domain.migarden.storage import config_record, get_config
from app.domain.migarden.wire import (
    CLOCK_LEAD,
    HOLDOFF,
    ExchangeEnvelope,
    ExchangeOut,
    Snapshot,
)


async def boot_seen(db: AsyncSession, boot_id: str) -> str | None:
    return await db.scalar(select(BootRecord.boot_id).where(BootRecord.boot_id == boot_id))


def trusted_observation(snapshot: Snapshot, now: datetime) -> bool:
    return (
        snapshot.time_quality != "unknown"
        and snapshot.observed_at is not None
        and now - HOLDOFF <= snapshot.observed_at <= now + CLOCK_LEAD
    )


async def observe_stop_target(
    db: AsyncSession, zone: ZoneState, packet: ExchangeEnvelope, now: datetime
) -> None:
    # Only STOP uses this target. Unknown clock cannot establish current OPEN boot.
    # Known retired boots cannot replace it; one pending unseen boot is bounded.
    if packet.boot_id == zone.boot_id:
        if zone.control_epoch is not None and packet.control_epoch < zone.control_epoch:
            return
        if zone.stop_target_boot_id is None or zone.stop_target_boot_id == packet.boot_id:
            zone.stop_target_boot_id = packet.boot_id
            zone.stop_target_epoch = packet.control_epoch
        return
    if await boot_seen(db, packet.boot_id):
        return
    if trusted_observation(packet.snapshot, now):
        observed = packet.snapshot.observed_at
        if zone.last_observed_at is not None and observed <= zone.last_observed_at:
            return
    if zone.stop_target_boot_id not in (None, zone.boot_id, packet.boot_id):
        return  # Competing unknown boots need provenance; do not pick last arrival.
    zone.stop_target_boot_id = packet.boot_id
    zone.stop_target_epoch = packet.control_epoch
    zone.preview = None


async def observe_snapshot(
    db: AsyncSession, zone: ZoneState, packet: ExchangeEnvelope, now: datetime
) -> bool:
    snapshot = packet.snapshot
    payload = snapshot.model_dump(mode="json")
    observed = snapshot.observed_at
    usable = trusted_observation(snapshot, now)
    if not usable:
        observed = None

    if packet.boot_id != zone.boot_id:
        if await boot_seen(db, packet.boot_id):
            return False
        if zone.boot_id is not None and (
            observed is None
            or (zone.last_observed_at is not None and observed <= zone.last_observed_at)
        ):
            return False
        db.add(BootRecord(boot_id=packet.boot_id, first_seen_at=now))
        zone.boot_id = packet.boot_id
        zone.control_epoch = packet.control_epoch
        zone.stop_target_boot_id = packet.boot_id
        zone.stop_target_epoch = packet.control_epoch
        zone.last_observed_at = None
        zone.preview = None
    elif zone.control_epoch is not None and packet.control_epoch < zone.control_epoch:
        return False

    zone.last_seen_at = now
    higher_epoch = zone.control_epoch is not None and packet.control_epoch > zone.control_epoch
    if higher_epoch:
        zone.control_epoch = packet.control_epoch
        if zone.stop_target_boot_id in (None, packet.boot_id):
            zone.stop_target_boot_id = packet.boot_id
            zone.stop_target_epoch = packet.control_epoch
        zone.preview = None
    if observed is not None and zone.last_observed_at is not None:
        if observed < zone.last_observed_at and not higher_epoch:
            return False
        if observed == zone.last_observed_at and not higher_epoch:
            return zone.snapshot == payload
    if observed is not None:
        zone.last_observed_at = max(observed, zone.last_observed_at or observed)
    if observed is None and payload == zone.snapshot and not higher_epoch:
        return True
    zone.snapshot = payload
    zone.snapshot_received_at = now
    return True


async def confirm_applied(
    db: AsyncSession, zone: ZoneState, snapshot: Snapshot, now: datetime
) -> None:
    ref = snapshot.applied_config_ref
    candidate = await config_record(db, ref) if ref else None
    previous = await config_record(db, zone.applied_ref) if zone.applied_ref else None
    if (
        ref is None
        or ref == zone.applied_ref
        or not trusted_observation(snapshot, now)
        or candidate is None
        or (
            previous is not None
            and (candidate.saved_at, candidate.id) < (previous.saved_at, previous.id)
        )
    ):
        return
    # An unordered snapshot never establishes applied. Current ordered snapshot
    # corroborates the exact immutable config even if its durable report was delayed.
    proof = await db.scalar(
        select(ReportRecord.event_id)
        .where(ReportRecord.kind == "config_applied", ReportRecord.config_ref == ref)
        .limit(1)
    )
    if proof is not None:
        zone.applied_ref, zone.applied_confirmed_at = ref, now


async def exchange(
    db: AsyncSession, zone: ZoneState, packet: ExchangeEnvelope, now: datetime
) -> ExchangeOut:
    await observe_stop_target(db, zone, packet, now)
    await db.flush()  # Flush outer target changes outside report savepoints.
    acked, accepted, failed = await ingest_reports(db, packet, now)
    reconciled = reconcile(zone.report_reconciliation, accepted=accepted, failed=failed)
    if zone.report_reconciliation != reconciled:
        zone.report_reconciliation = reconciled

    stops = []
    stopping = await latest(db, "stop")
    if stopping and stopping.status in STOP_PENDING and stopping.boot_id == packet.boot_id:
        stops.append(stop_message(stopping))

    pending = await waiting_start(db)
    if reconciled is not None:
        zone.preview = None
        if pending is not None:
            expire_or_cancel(pending, now, cancel="reports_need_reconciliation")

    if failed:
        # A poisoned exchange may deliver STOP and ACK committed evidence. It
        # cannot certify a snapshot, change desired delivery, or offer OPEN.
        return ExchangeOut(
            server_time=now, stops=stops, acked_event_ids=acked, retry_after_seconds=30
        )

    current_observation = await observe_snapshot(db, zone, packet, now)
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

    candidates, grants = [], []
    if pending is not None and reconciled is None:
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
