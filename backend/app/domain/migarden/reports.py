"""Validate, receipt and project durable device reports without scheduling output."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.commands import STOP_PENDING, UNCERTAIN, WAITING, command_record
from app.domain.migarden.models import CommandRecord, ReportRecord, SessionRecord, ZoneState
from app.domain.migarden.storage import Rejected
from app.domain.migarden.wire import (
    CLOCK_LEAD,
    EndedReport,
    OccurrenceReport,
    Report,
    RequestReceivedReport,
    RequestRejectedReport,
    Snapshot,
    StartedReport,
    StopProcessedReport,
)


def report_result(report: Report) -> str | None:
    if isinstance(report, OccurrenceReport):
        return report.payload.disposition
    if isinstance(report, StopProcessedReport):
        return report.payload.outcome
    if isinstance(report, RequestRejectedReport):
        return "rejected"
    if isinstance(report, StartedReport):
        return "started"
    if isinstance(report, EndedReport):
        return report.payload.outcome
    return None


async def ingest_reports(db: AsyncSession, reports: list[Report], now: datetime) -> list[str]:
    prepared: list[tuple[Report, ReportRecord]] = []
    acked: dict[str, None] = {}
    for report in reports:
        data = report.model_dump(mode="json")
        existing = await db.scalar(
            select(ReportRecord).where(ReportRecord.event_id == report.event_id)
        )
        if existing is not None:
            if existing.body != data:
                raise Rejected("event_id_conflict")
        else:
            collision = await db.scalar(
                select(ReportRecord.event_id).where(
                    ReportRecord.boot_id == report.boot_id, ReportRecord.sequence == report.sequence
                )
            )
            if collision is not None:
                raise Rejected("event_sequence_conflict")
            observed = report.occurred_at
            trusted = (
                observed is not None
                and report.time_quality != "unknown"
                and observed <= now + CLOCK_LEAD
            )
            row = ReportRecord(
                event_id=report.event_id,
                boot_id=report.boot_id,
                sequence=report.sequence,
                kind=report.kind,
                config_ref=report.config_ref,
                source=report.trigger_source,
                result=report_result(report),
                occurred_at=observed,
                sort_at=observed if trusted else now,
                received_at=now,
                body=data,
            )
            db.add(row)
            await db.flush()
            prepared.append((report, row))
        acked[report.event_id] = None

    for report, row in sorted(prepared, key=lambda item: (item[0].boot_id, item[0].sequence)):
        command = await command_record(db, report.request_id)
        await project(db, report, row, command)
    return list(acked)


async def project(
    db: AsyncSession,
    report: Report,
    row: ReportRecord,
    command: CommandRecord | None,
) -> None:
    if isinstance(report, (StartedReport, EndedReport)):
        await project_session(db, report, row, command)
        return

    if command is None:
        if isinstance(report, StopProcessedReport) and report.trigger_source == "remote":
            raise Rejected("stop_request_unknown")
        return

    if isinstance(report, StopProcessedReport):
        if command.kind != "stop" or report.trigger_source != "remote":
            raise Rejected("stop_request_mismatch")
        # A new-boot off report is not proof that the old-boot packet was processed.
        # The exchange separately fences old-boot STOP against a closed new boot.
        if report.boot_id != command.boot_id:
            return
        if command.status in ("stop_confirmed", "stop_stale") or not newer(command, report):
            return
        status = "stop_unconfirmed" if report.payload.outcome == "unconfirmed" else "stop_confirmed"
        observe_command(command, report, status, report.payload.reason or report.payload.outcome)
        if status == "stop_confirmed":
            await db.execute(
                update(CommandRecord)
                .where(
                    CommandRecord.kind == "stop",
                    CommandRecord.status.in_(STOP_PENDING),
                    CommandRecord.request_id != command.request_id,
                    CommandRecord.confirmed_at <= command.confirmed_at,
                )
                .values(status="stop_stale", reason="reconciled_by_stop:" + command.request_id)
            )
        return

    if not isinstance(report, (RequestReceivedReport, RequestRejectedReport)):
        return
    if report.trigger_source not in (None, "remote"):
        raise Rejected("request_source_mismatch")
    if report.boot_id != command.boot_id:
        return  # A report may describe a stale packet; it cannot authorize a new boot.
    if command.kind == "start" and report.config_ref != command.config_ref:
        return  # E.g. a terminal config mismatch; never treat it as a matching receipt.
    if not newer(command, report):
        return
    if isinstance(report, RequestReceivedReport):
        if command.status == "pending" and command.candidate_offered_at is not None:
            observe_command(command, report, "received")
        elif command.status == "stop_requested":
            observe_command(command, report, "stop_received")
    elif command.kind == "stop":
        # A rejection/negative receipt is not positive evidence of processing.
        observe_command(command, report, "stop_unconfirmed", report.payload.reason)
    elif command.status in (*WAITING, "granted"):
        observe_command(command, report, "rejected", report.payload.reason)


async def find_session(db: AsyncSession, session_id: str) -> SessionRecord | None:
    return await db.scalar(select(SessionRecord).where(SessionRecord.session_id == session_id))


async def observe_active(
    db: AsyncSession, zone: ZoneState, snapshot: Snapshot, boot_id: str
) -> None:
    # Keep evidence of possible execution even if the durable start report has
    # not arrived. A later off snapshot alone cannot resolve this observation.
    active = snapshot.active_session
    if active is None:
        if snapshot.output == "on":
            zone.unidentified_execution = True
        return
    if await find_session(db, active.session_id) is not None:
        return
    command = await command_record(db, active.request_id)
    if active.trigger_source == "remote" and (
        command is None
        or command.kind != "start"
        or not command.grant_id
        or command.config_ref != active.config_ref
        or command.boot_id != boot_id
    ):
        zone.unidentified_execution = True
        return
    if active.request_id and await db.scalar(
        select(SessionRecord.session_id).where(SessionRecord.request_id == active.request_id)
    ):
        zone.unidentified_execution = True
        return
    db.add(
        SessionRecord(
            session_id=active.session_id,
            request_id=active.request_id,
            boot_id=boot_id,
            source=active.trigger_source,
            config_ref=active.config_ref,
            planned_duration_seconds=active.duration_seconds,
            started_at=active.started_at,
        )
    )


def newer(command: CommandRecord, report: Report) -> bool:
    return command.last_report_sequence is None or report.sequence > command.last_report_sequence


def observe_command(
    command: CommandRecord, report: Report, status: str, reason: str | None = None
) -> None:
    if command.boot_id == report.boot_id:
        command.last_report_sequence = max(command.last_report_sequence or 0, report.sequence)
    command.status, command.reason = status, reason


async def project_session(
    db: AsyncSession,
    report: StartedReport | EndedReport,
    row: ReportRecord,
    command: CommandRecord | None,
) -> None:
    begin = isinstance(report, StartedReport)
    recovery = isinstance(report, EndedReport) and report.payload.outcome == "unknown"
    if report.trigger_source == "remote":
        if (
            command is None
            or command.kind != "start"
            or command.grant_id is None
            or command.config_ref != report.config_ref
            or (command.boot_id != report.boot_id and not recovery)
        ):
            raise Rejected("session_without_matching_grant")
        if begin and report.payload.duration_seconds != command.duration_seconds:
            raise Rejected("session_duration_conflict")
    elif command is not None:
        raise Rejected("session_request_conflict")

    session = await find_session(db, report.session_id)
    if session is None:
        if report.request_id is not None and await db.scalar(
            select(SessionRecord.session_id).where(SessionRecord.request_id == report.request_id)
        ):
            raise Rejected("request_session_conflict")
        session = SessionRecord(
            session_id=report.session_id,
            request_id=report.request_id,
            boot_id=command.boot_id if command else report.boot_id,
            source=report.trigger_source,
            config_ref=report.config_ref,
        )
        db.add(session)
    elif (
        session.source != report.trigger_source
        or session.config_ref != report.config_ref
        or (session.request_id and report.request_id and session.request_id != report.request_id)
    ):
        raise Rejected("session_context_conflict")

    if session.request_id is None and report.request_id is not None:
        other = await db.scalar(
            select(SessionRecord.session_id).where(
                SessionRecord.request_id == report.request_id,
                SessionRecord.session_id != session.session_id,
            )
        )
        if other:
            raise Rejected("request_session_conflict")
        session.request_id = report.request_id

    payload = report.payload
    start = payload.started_at
    if not recovery and session.boot_id != report.boot_id:
        if session.outcome == "unknown" and session.started_event_id is None:
            session.boot_id = report.boot_id
        else:
            raise Rejected("session_boot_conflict")
    if session.started_at and start and session.started_at != start:
        raise Rejected("session_started_at_conflict")
    session.started_at = session.started_at or start

    if isinstance(report, StartedReport):
        if session.planned_duration_seconds not in (None, report.payload.duration_seconds):
            raise Rejected("session_duration_conflict")
        if session.started_event_id is None:
            session.planned_duration_seconds = report.payload.duration_seconds
            session.started_event_id = row.event_id
            session.start_sort_at = row.sort_at
        if command and command.status in UNCERTAIN and session.ended_event_id is None:
            observe_command(command, report, "started")
        return

    payload = report.payload
    if session.ended_event_id is not None:
        if session.outcome != "unknown":
            if recovery:
                return  # Late unknown must not erase durable terminal evidence.
            if (
                session.outcome != payload.outcome
                or session.ended_at != payload.ended_at
                or session.output_duration_seconds != payload.output_duration_seconds
                or session.reason != payload.reason
            ):
                raise Rejected("session_terminal_conflict")
            return
        if recovery:
            return
    session.ended_event_id = row.event_id
    session.end_sort_at = row.sort_at
    session.ended_at = payload.ended_at
    session.output_duration_seconds = payload.output_duration_seconds
    session.outcome = payload.outcome
    session.reason = payload.reason
    if command:
        observe_command(command, report, payload.outcome, payload.reason)
