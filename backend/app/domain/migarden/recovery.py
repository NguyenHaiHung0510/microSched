"""Settle only the control uncertainty of a proven reboot interruption.

The immutable terminal and its unknown measured duration remain unchanged.
"""

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.models import CommandRecord, ReportRecord, SessionRecord
from app.domain.migarden.storage import Rejected
from app.domain.migarden.wire import (
    CLOCK_LEAD,
    EndedReport,
    FaultReport,
    Report,
    StartedReport,
)

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


def has_interruption_terminal(session: SessionRecord) -> bool:
    return (
        session.ended_event_id is not None
        and session.outcome == "unknown"
        and session.reason == INTERRUPTED
    )


async def validate_late_interruption_evidence(
    db: AsyncSession, session: SessionRecord, report: StartedReport | EndedReport
) -> None:
    terminal = await db.scalar(
        select(ReportRecord).where(ReportRecord.event_id == session.ended_event_id)
    )
    if terminal is None or report.request_id != session.request_id:
        raise Rejected("interruption_evidence_conflict")
    if isinstance(report, EndedReport):
        if report.payload.model_dump(mode="json") != terminal.body["payload"]:
            raise Rejected("interruption_evidence_conflict")
        return

    # An ended-only local row initially knows the terminal's boot, not the
    # original START boot. A valid delayed START can remain raw evidence; it
    # must never reopen the session or replace any terminal/projection fields.
    expected_duration = session.planned_duration_seconds
    if (
        (expected_duration is not None and report.boot_id != session.boot_id)
        or (expected_duration is not None and report.payload.duration_seconds != expected_duration)
        or (session.started_at is not None and report.payload.started_at != session.started_at)
        or report.sequence >= terminal.sequence
        or (
            report.time_quality != "unknown"
            and terminal.body.get("time_quality") != "unknown"
            and report.occurred_at is not None
            and terminal.occurred_at is not None
            and report.occurred_at > terminal.occurred_at
        )
    ):
        raise Rejected("interruption_evidence_conflict")


async def validate_recovery(
    db: AsyncSession, report: Report, now: datetime
) -> CommandRecord | None:
    # An authenticated durable event keeps the producing boot even when uploaded
    # after another reboot or a later local START. It is historical settlement,
    # never authority for OPEN or for the envelope's live observation.
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
        # The firmware journal sequence is durable across boots. A boot name
        # is not a clock, and rewriting the marker for its upload boot loses proof.
        or report.sequence <= terminal.sequence
        or (
            report.time_quality != "unknown"
            and body["time_quality"] != "unknown"
            and report.occurred_at is not None
            and terminal.occurred_at is not None
            and report.occurred_at < terminal.occurred_at
        )
        or (
            report.time_quality != "unknown"
            and report.occurred_at is not None
            and report.occurred_at > now + CLOCK_LEAD
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
