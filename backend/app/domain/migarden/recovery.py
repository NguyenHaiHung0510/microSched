"""Settle only the control uncertainty of a proven reboot interruption.

The immutable terminal and its unknown measured duration remain unchanged.
"""

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import BootRecord, CommandRecord, ReportRecord, SessionRecord
from app.domain.migarden.storage import Rejected, read_zone
from app.domain.migarden.wire import CLOCK_LEAD, HOLDOFF, ExchangeEnvelope, FaultReport, Report

INTERRUPTED = "REBOOT_INTERRUPTED"
RECOVERED = "REBOOT_INTERRUPTED_RECOVERED"


def is_recovery(report: Report) -> bool:
    return (
        isinstance(report, FaultReport)
        and report.kind == "recovered"
        and report.payload.reason == RECOVERED
    )


def settlement_exists():
    # Only rows admitted by validate_recovery receive this result. Correlate all
    # original identities so a receipt cannot settle another session or command.
    return (
        exists()
        .where(
            ReportRecord.kind == "recovered",
            ReportRecord.result == "recovered",
            ReportRecord.body["session_id"].as_string() == SessionRecord.session_id,
            ReportRecord.body["request_id"]
            .as_string()
            .is_not_distinct_from(SessionRecord.request_id),
            ReportRecord.config_ref == SessionRecord.config_ref,
            ReportRecord.source == SessionRecord.source,
            SessionRecord.outcome == "unknown",
            SessionRecord.reason == INTERRUPTED,
            SessionRecord.output_duration_seconds.is_(None),
        )
        .correlate(SessionRecord)
    )


async def session_settled(db: AsyncSession, session_id: str) -> bool:
    return bool(
        await db.scalar(
            select(SessionRecord.session_id).where(
                SessionRecord.session_id == session_id, settlement_exists()
            )
        )
    )


async def validate_recovery(
    db: AsyncSession, report: Report, packet: ExchangeEnvelope, now: datetime
) -> CommandRecord | None:
    zone = await read_zone(db)
    snapshot = packet.snapshot
    observed = snapshot.observed_at
    if (
        zone is None
        or report.boot_id != packet.boot_id
        or snapshot.time_quality == "unknown"
        or observed is None
        or not now - HOLDOFF <= observed <= now + CLOCK_LEAD
        or snapshot.output != "off"
        or snapshot.active_session is not None
        or (zone.boot_id == packet.boot_id and packet.control_epoch < (zone.control_epoch or 0))
        or (zone.last_observed_at is not None and observed < zone.last_observed_at)
    ):
        raise Rejected("recovery_context_unconfirmed")
    if packet.boot_id != zone.boot_id and (
        await db.scalar(select(BootRecord.boot_id).where(BootRecord.boot_id == packet.boot_id))
        or (zone.last_observed_at is not None and observed <= zone.last_observed_at)
    ):
        raise Rejected("recovery_boot_stale")
    if (
        packet.boot_id == zone.boot_id
        and observed == zone.last_observed_at
        and packet.control_epoch == zone.control_epoch
        and snapshot.model_dump(mode="json") != zone.snapshot
    ):
        raise Rejected("recovery_snapshot_unordered")
    session = await db.scalar(
        select(SessionRecord).where(SessionRecord.session_id == report.session_id)
    )
    if (
        session is None
        or session.request_id != report.request_id
        or session.config_ref != report.config_ref
        or session.source != report.trigger_source
        or session.outcome != "unknown"
        or session.reason != INTERRUPTED
        or session.output_duration_seconds is not None
        or session.ended_event_id is None
    ):
        raise Rejected("recovery_session_mismatch")
    terminal = await db.scalar(
        select(ReportRecord).where(ReportRecord.event_id == session.ended_event_id)
    )
    if terminal is None or terminal.kind != "session_ended":
        raise Rejected("recovery_terminal_missing")
    body = terminal.body
    payload = body["payload"]
    if (
        body.get("session_id") != report.session_id
        or body.get("request_id") != report.request_id
        or terminal.config_ref != report.config_ref
        or terminal.source != report.trigger_source
        or payload.get("outcome") != "unknown"
        or payload.get("reason") != INTERRUPTED
        or payload.get("output_duration_seconds") is not None
        or (report.boot_id == terminal.boot_id and report.sequence <= terminal.sequence)
        or (
            report.occurred_at is not None
            and terminal.occurred_at is not None
            and report.occurred_at < terminal.occurred_at
        )
    ):
        raise Rejected("recovery_terminal_mismatch")
    command = None
    if report.trigger_source == "remote":
        command = await db.scalar(
            select(CommandRecord).where(CommandRecord.request_id == report.request_id)
        )
        if (
            command is None
            or command.kind != "start"
            or command.grant_id is None
            or command.config_ref != report.config_ref
            or command.boot_id != session.boot_id
            or command.status not in ("unknown", "recovered")
        ):
            raise Rejected("recovery_command_mismatch")
    elif report.request_id is not None and await db.scalar(
        select(CommandRecord.request_id).where(CommandRecord.request_id == report.request_id)
    ):
        raise Rejected("recovery_command_mismatch")
    return command
