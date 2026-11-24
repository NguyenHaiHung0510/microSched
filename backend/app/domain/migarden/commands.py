"""Owner intents. A row is a receipt or in-flight handoff, never a watering job."""

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import CommandRecord, SessionRecord, ZoneState
from app.domain.migarden.recovery import settlement_exists
from app.domain.migarden.storage import Rejected, get_config, lock_zone
from app.domain.migarden.wire import (
    CLOCK_LEAD,
    HOLDOFF,
    Candidate,
    Grant,
    Identity,
    Seconds,
    Snapshot,
    StartContext,
    Stop,
    WireModel,
)

WAITING = ("pending", "received")
UNCERTAIN = ("granted", "started", "unknown")
STOP_PENDING = ("stop_requested", "stop_received", "stop_unconfirmed")
STOP_TERMINAL = ("stop_confirmed", "stop_stale")


class PreviewInput(WireModel):
    duration_seconds: Seconds


class ConfirmInput(WireModel):
    preview_id: Identity


class Preview(WireModel):
    preview_id: Identity
    expires_at: datetime
    context: StartContext
    duration_seconds: Seconds


class CommandView(WireModel):
    request_id: str
    kind: str
    status: str
    reason: str | None
    confirmed_at: datetime
    expires_at: datetime | None
    duration_seconds: int | None
    config_ref: str | None


def command_view(row: CommandRecord, now: datetime) -> CommandView:
    status, reason = row.status, row.reason
    if row.expires_at is not None and now >= row.expires_at:
        if status in WAITING:
            status, reason = "expired", "expired_before_grant"
        elif status == "granted":
            status, reason = "unknown", "grant_outcome_unknown"
    if status in STOP_PENDING and now >= row.confirmed_at + HOLDOFF:
        status, reason = "stop_unconfirmed", "stop_outcome_unconfirmed"
    return CommandView(
        request_id=row.request_id,
        kind=row.kind,
        status=status,
        reason=reason,
        confirmed_at=row.confirmed_at,
        expires_at=row.expires_at,
        duration_seconds=row.duration_seconds,
        config_ref=row.config_ref,
    )


async def command_record(db: AsyncSession, request_id: str | None) -> CommandRecord | None:
    if request_id is None:
        return None
    return await db.scalar(select(CommandRecord).where(CommandRecord.request_id == request_id))


async def latest(db: AsyncSession, kind: str) -> CommandRecord | None:
    return await db.scalar(
        select(CommandRecord)
        .where(CommandRecord.kind == kind)
        .order_by(CommandRecord.confirmed_at.desc(), CommandRecord.request_id.desc())
        .limit(1)
    )


async def waiting_start(db: AsyncSession) -> CommandRecord | None:
    return await open_command(db, "start", WAITING)


async def open_command(
    db: AsyncSession, kind: str, statuses: tuple[str, ...]
) -> CommandRecord | None:
    return await db.scalar(
        select(CommandRecord)
        .where(CommandRecord.kind == kind, CommandRecord.status.in_(statuses))
        .order_by(CommandRecord.confirmed_at.desc(), CommandRecord.request_id.desc())
        .limit(1)
    )


def expire_or_cancel(row: CommandRecord, now: datetime, *, cancel: str | None = None) -> None:
    if row.status in WAITING:
        if row.expires_at is not None and now >= row.expires_at:
            row.status, row.reason = "expired", "expired_before_grant"
        elif cancel:
            row.status, row.reason = "canceled", cancel


def context_of(zone: ZoneState) -> StartContext | None:
    if zone.boot_id is None or zone.applied_ref is None or zone.control_epoch is None:
        return None
    return StartContext(
        config_ref=zone.applied_ref, boot_id=zone.boot_id, control_epoch=zone.control_epoch
    )


def context_matches(row: CommandRecord, zone: ZoneState) -> bool:
    return (row.boot_id, row.control_epoch, row.config_ref) == (
        zone.boot_id,
        zone.control_epoch,
        zone.applied_ref,
    )


async def start_block_reason(
    db: AsyncSession, zone: ZoneState | None, now: datetime, *, ignore_waiting: bool = False
) -> str | None:
    if zone is None or zone.device_id is None:
        return "controller_not_provisioned"
    if zone.revoked_at is not None:
        return "controller_revoked"
    stop = await latest(db, "stop")
    if stop and stop.status in STOP_PENDING:
        return "stop_pending"
    if zone.report_reconciliation is not None:
        return "reports_need_reconciliation"
    if zone.stop_target_boot_id is not None and zone.stop_target_boot_id != zone.boot_id:
        return "controller_boot_unconfirmed"
    if zone.snapshot is None or zone.snapshot_received_at is None:
        return "device_waiting"
    snapshot = Snapshot.model_validate(zone.snapshot)
    if zone.snapshot_received_at < now - HOLDOFF:
        return "device_stale"
    if snapshot.active_session is not None or snapshot.output == "on":
        return "busy"
    unresolved_command = await open_command(db, "start", UNCERTAIN)
    unresolved_session = await db.scalar(
        select(SessionRecord.session_id)
        .where(
            (SessionRecord.outcome.is_(None)) | (SessionRecord.outcome == "unknown"),
            ~settlement_exists(),
        )
        .limit(1)
    )
    if zone.unidentified_execution or unresolved_command or unresolved_session:
        return "unresolved_execution"
    if snapshot.output != "off":
        return "output_unknown"
    if (
        snapshot.time_quality == "unknown"
        or snapshot.observed_at is None
        or snapshot.observed_at > now + CLOCK_LEAD
        or snapshot.observed_at < now - HOLDOFF
    ):
        return "clock_or_observation_untrusted"
    if not snapshot.ready:
        return "controller_not_ready"
    if zone.applied_ref is None or zone.applied_ref != snapshot.applied_config_ref:
        return "config_unconfirmed"
    if not ignore_waiting:
        pending = await waiting_start(db)
        if pending and pending.expires_at and now < pending.expires_at:
            return "start_pending"
    return None


async def prepare(
    db: AsyncSession, owner: str, form: PreviewInput, clock: Callable[[], datetime]
) -> Preview:
    zone = await lock_zone(db)
    now = clock()
    reason = await start_block_reason(db, zone, now)
    if reason:
        raise Rejected(reason)
    context = context_of(zone)
    assert context is not None
    config = await get_config(db, context.config_ref)
    if config is None or form.duration_seconds > config.policy.max_session_seconds:
        raise Rejected("duration_exceeds_applied_limit", 422)
    preview = Preview(
        preview_id=str(uuid4()),
        expires_at=now + HOLDOFF,
        context=context,
        duration_seconds=form.duration_seconds,
    )
    zone.preview = {"session_owner_id": owner, "value": preview.model_dump(mode="json")}
    return preview


async def confirm(
    db: AsyncSession, owner: str, data: ConfirmInput, clock: Callable[[], datetime]
) -> CommandView:
    zone = await lock_zone(db)
    now = clock()
    prior = await command_record(db, data.preview_id)
    if prior is not None and prior.kind == "start" and prior.session_owner_id == owner:
        return command_view(prior, now)
    if not zone.preview or zone.preview["session_owner_id"] != owner:
        raise Rejected("preview_missing")
    preview = Preview.model_validate(zone.preview["value"])
    if preview.preview_id != data.preview_id or now >= preview.expires_at:
        raise Rejected("preview_expired")
    if preview.context != context_of(zone):
        raise Rejected("preview_context_changed")
    reason = await start_block_reason(db, zone, now)
    if reason:
        raise Rejected(reason)
    pending = await waiting_start(db)
    if pending is not None:
        expire_or_cancel(pending, now)
    start = CommandRecord(
        request_id=preview.preview_id,
        kind="start",
        status="pending",
        session_owner_id=owner,
        confirmed_at=now,
        expires_at=now + HOLDOFF,
        duration_seconds=preview.duration_seconds,
        config_ref=preview.context.config_ref,
        boot_id=preview.context.boot_id,
        control_epoch=preview.context.control_epoch,
    )
    zone.preview = None
    db.add(start)
    return command_view(start, now)


async def request_stop(db: AsyncSession, owner: str, clock: Callable[[], datetime]) -> CommandView:
    zone = await lock_zone(db)
    now = clock()
    target = zone.stop_target_boot_id or zone.boot_id
    epoch = zone.stop_target_epoch if zone.stop_target_boot_id else zone.control_epoch
    if target is None or epoch is None:
        raise Rejected("controller_boot_unknown")
    zone.preview = None
    pending = await waiting_start(db)
    if pending:
        expire_or_cancel(pending, now, cancel="canceled_by_stop")
    existing = await latest(db, "stop")
    if existing and existing.status in STOP_PENDING and existing.boot_id == target:
        return command_view(existing, now)
    stop = CommandRecord(
        request_id=str(uuid4()),
        kind="stop",
        status="stop_requested",
        session_owner_id=owner,
        confirmed_at=now,
        boot_id=target,
        control_epoch=epoch,
    )
    db.add(stop)
    return command_view(stop, now)


def stop_message(row: CommandRecord) -> Stop:
    return Stop(
        request_id=row.request_id,
        boot_id=row.boot_id,
        confirmed_at=row.confirmed_at,
    )


def start_message(row: CommandRecord) -> Candidate:
    assert row.config_ref and row.expires_at and row.duration_seconds
    return Candidate(
        request_id=row.request_id,
        config_ref=row.config_ref,
        boot_id=row.boot_id,
        control_epoch=row.control_epoch,
        confirmed_at=row.confirmed_at,
        expires_at=row.expires_at,
        duration_seconds=row.duration_seconds,
    )


def mark_granted(row: CommandRecord) -> Grant:
    row.grant_id = str(uuid4())
    row.status = "granted"
    return Grant(**start_message(row).model_dump(), grant_id=row.grant_id)
