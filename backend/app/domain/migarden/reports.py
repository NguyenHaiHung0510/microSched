"""Validate, receipt and project durable device reports without scheduling output."""

from collections import defaultdict
from datetime import datetime

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.commands import (
    STOP_PENDING,
    STOP_TERMINAL,
    UNCERTAIN,
    WAITING,
    command_record,
)
from app.domain.migarden.models import CommandRecord, ReportRecord, SessionRecord, ZoneState
from app.domain.migarden.reconciliation import FailureKey, failure_key, wire_identity
from app.domain.migarden.recovery import RECOVERED, is_recovery, session_settled, validate_recovery
from app.domain.migarden.storage import Rejected
from app.domain.migarden.wire import (
    CLOCK_LEAD,
    EndedReport,
    ExchangeEnvelope,
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


_REPORT = TypeAdapter(Report)


async def ingest_reports(
    db: AsyncSession, packet: ExchangeEnvelope, now: datetime
) -> tuple[list[str], list[FailureKey], list[FailureKey]]:
    """Isolate each report while holding the Zone lock in the outer transaction."""
    parsed: dict[FailureKey, Report] = {}
    by_id: dict[str, set[FailureKey]] = defaultdict(set)
    by_sequence: dict[tuple[str, int], set[str]] = defaultdict(set)
    failed: list[FailureKey] = []
    for item in packet.reports:
        try:
            report = _REPORT.validate_python(item)
        except ValidationError:
            fields = item if isinstance(item, dict) else {}
            key = failure_key(item, wire_identity(fields.get("boot_id")), packet.boot_id)
            failed.append(key)
            if event_id := wire_identity(fields.get("event_id")):
                by_id[event_id].add(key)
        else:
            key = failure_key(report.model_dump(mode="json"), report.boot_id, packet.boot_id)
            parsed[key] = report
            by_id[report.event_id].add(key)
            by_sequence[(report.boot_id, report.sequence)].add(report.event_id)

    accepted: list[FailureKey] = []
    acked: set[str] = set()
    for key, report in sorted(parsed.items(), key=lambda pair: (pair[1].boot_id, pair[1].sequence)):
        # An ID-only ACK cannot distinguish variants in one exchange. Nor can
        # two different IDs both be the durable event for the same boot/sequence.
        if (
            len(by_id[report.event_id]) > 1
            or len(by_sequence[(report.boot_id, report.sequence)]) > 1
        ):
            failed.append(key)
            continue
        try:
            async with db.begin_nested():
                await ingest_report(db, report, now, packet)
                await db.flush()
        except Rejected, IntegrityError:
            failed.append(key)
        else:
            accepted.append(key)
            acked.add(report.event_id)

    # Retain input order on the wire. The caller publishes ACKs only after the outer commit.
    return [event_id for event_id in by_id if event_id in acked], accepted, failed


async def ingest_report(
    db: AsyncSession, report: Report, now: datetime, packet: ExchangeEnvelope
) -> None:
    data = report.model_dump(mode="json")
    existing = await db.scalar(select(ReportRecord).where(ReportRecord.event_id == report.event_id))
    if existing is not None:
        if existing.body != data:
            raise Rejected("event_id_conflict")
        if isinstance(report, StopProcessedReport):
            # A legacy row is not proof of proper STOP correlation.
            validate_stop_receipt(report, await command_record(db, report.request_id))
        return
    collision = await db.scalar(
        select(ReportRecord.event_id).where(
            ReportRecord.boot_id == report.boot_id, ReportRecord.sequence == report.sequence
        )
    )
    if collision is not None:
        raise Rejected("event_sequence_conflict")
    observed = report.occurred_at
    trusted = (
        observed is not None and report.time_quality != "unknown" and observed <= now + CLOCK_LEAD
    )
    recovered_command = (
        await validate_recovery(db, report, packet, now) if is_recovery(report) else None
    )
    row = ReportRecord(
        event_id=report.event_id,
        boot_id=report.boot_id,
        sequence=report.sequence,
        kind=report.kind,
        config_ref=report.config_ref,
        source=report.trigger_source,
        result="recovered" if is_recovery(report) else report_result(report),
        occurred_at=observed,
        sort_at=observed if trusted else now,
        received_at=now,
        body=data,
    )
    db.add(row)
    await db.flush()
    if is_recovery(report):
        if recovered_command is not None:
            recovered_command.status, recovered_command.reason = "recovered", RECOVERED
        return
    command = await command_record(db, report.request_id)
    await project(db, report, row, command)


def validate_stop_receipt(report: StopProcessedReport, command: CommandRecord | None) -> None:
    if command is None:
        if report.trigger_source == "remote":
            raise Rejected("stop_request_unknown")
        return
    if command.kind != "stop" or report.trigger_source != "remote":
        raise Rejected("stop_request_mismatch")
    if report.boot_id != command.boot_id:
        raise Rejected("stop_boot_mismatch")


async def project(
    db: AsyncSession,
    report: Report,
    row: ReportRecord,
    command: CommandRecord | None,
) -> None:
    if isinstance(report, (StartedReport, EndedReport)):
        await project_session(db, report, row, command)
        return

    if isinstance(report, StopProcessedReport):
        validate_stop_receipt(report, command)
        if command is None or command.status in STOP_TERMINAL:
            return
        unconfirmed = report.payload.outcome == "unconfirmed"
        if unconfirmed and not newer(command, report):
            return
        # Positive processing is stronger than a later-arriving negative receipt,
        # even when source sequence ordering puts the negative after it.
        status = "stop_unconfirmed" if unconfirmed else "stop_confirmed"
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

    if command is None or not isinstance(report, (RequestReceivedReport, RequestRejectedReport)):
        return
    if report.trigger_source not in (None, "remote"):
        raise Rejected("request_source_mismatch")
    if command.kind == "stop" and command.status in STOP_TERMINAL:
        return
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
        if await session_settled(db, active.session_id):
            zone.unidentified_execution = True
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
    if await session_settled(db, session.session_id):
        if isinstance(report, StartedReport) and (
            report.boot_id != session.boot_id
            or start != session.started_at
            or payload.duration_seconds != session.planned_duration_seconds
        ):
            raise Rejected("settled_interruption_conflict")
        if isinstance(report, EndedReport) and (
            payload.outcome != session.outcome
            or payload.reason != session.reason
            or payload.output_duration_seconds != session.output_duration_seconds
            or payload.ended_at != session.ended_at
            or start != session.started_at
        ):
            raise Rejected("settled_interruption_conflict")
        return  # Late original evidence must not reopen or rewrite the settled uncertainty.
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
