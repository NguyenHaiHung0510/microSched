"""One row per reported session, plus distinct actions, before cursor pagination."""

from datetime import datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.migarden.commands import command_view
from app.domain.migarden.models import CommandRecord, ConfigRecord, ReportRecord, SessionRecord
from app.domain.migarden.queries import (
    DAILY_SESSION_LIMIT,
    HISTORY_KINDS,
    Cursor,
    HistoryFilter,
    HistoryItem,
    bound_history,
    decode_cursor,
    encode_cursor,
    history_command_status,
    validate_history_dates,
)
from app.domain.migarden.schedule import ONE_DAY, day_start
from app.domain.migarden.wire import WireModel

TIMELINE_GROUPS = ("c", "h", "r")
STOP_RECEIPTS = ("close_requested", "already_off")
MEASURED_OUTCOMES = ("completed", "stopped", "fault")


class TimelineItem(HistoryItem):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    evidence: list[HistoryItem] = Field(default_factory=list)


class HistoryTotals(WireModel):
    recorded_seconds: int | None
    schedule_seconds: int | None
    remote_seconds: int | None
    local_button_seconds: int | None


class TimelineView(WireModel):
    items: list[TimelineItem]
    next_cursor: str | None = None
    coverage: Literal["partial"] = "partial"
    totals: HistoryTotals | None = None


def report_item(report: ReportRecord, **fields) -> TimelineItem:
    body = report.body
    return TimelineItem(
        id=f"r:{report.event_id}",
        kind=report.kind,
        source=report.source,
        result=report.result,
        reason=body["payload"].get("reason"),
        occurred_at=report.occurred_at,
        received_at=report.received_at,
        time_quality=body["time_quality"],
        request_id=body.get("request_id"),
        session_id=body.get("session_id"),
        config_ref=report.config_ref,
        scheduled_at=body["payload"].get("scheduled_at"),
        **fields,
    )


def selected_results(criteria: HistoryFilter) -> tuple[str | None, ...]:
    if criteria.result == "stop_processed":
        return ("stopped", "stop_confirmed", *STOP_RECEIPTS)
    return (criteria.result,)


async def session_rows(
    db: AsyncSession, criteria: HistoryFilter, cursor: Cursor | None
) -> list[tuple[Cursor, TimelineItem]]:
    start, end = aliased(ReportRecord), aliased(ReportRecord)
    order = func.coalesce(SessionRecord.end_sort_at, SessionRecord.start_sort_at)
    # Use the terminal report's source date for a closed session, otherwise the
    # start report's. Receipt time can order unknown dates, never assign one.
    event_at = case((end.event_id.is_not(None), end.occurred_at), else_=start.occurred_at)
    quality = case(
        (end.event_id.is_not(None), end.body["time_quality"].as_string()),
        else_=start.body["time_quality"].as_string(),
    )
    query = (
        select(SessionRecord, start, end)
        .outerjoin(start, start.event_id == SessionRecord.started_event_id)
        .outerjoin(end, end.event_id == SessionRecord.ended_event_id)
        .where(order.is_not(None))
    )
    if criteria.source:
        query = query.where(SessionRecord.source == criteria.source)
    if criteria.result:
        query = query.where(
            func.coalesce(SessionRecord.outcome, "started").in_(selected_results(criteria))
        )
    rows = (
        await db.execute(
            bound_history(
                query,
                criteria,
                cursor,
                group="h",
                key=SessionRecord.session_id,
                ordered_at=order,
                event_at=event_at,
                trusted_time=quality != "unknown",
            )
        )
    ).all()
    items = []
    for session, started, ended in rows:
        main = ended or started
        events = []
        if started is not None:
            events.append(
                report_item(started, planned_duration_seconds=session.planned_duration_seconds)
            )
        if ended is not None:
            events.append(report_item(ended, duration_seconds=session.output_duration_seconds))
        items.append(
            (
                (session.end_sort_at or session.start_sort_at, "h", session.session_id),
                TimelineItem(
                    id=f"h:{session.session_id}",
                    kind="session",
                    source=session.source,
                    result=session.outcome or "started",
                    reason=session.reason,
                    occurred_at=main.occurred_at,
                    received_at=main.received_at,
                    time_quality=main.body["time_quality"],
                    request_id=session.request_id,
                    session_id=session.session_id,
                    config_ref=session.config_ref,
                    duration_seconds=session.output_duration_seconds,
                    planned_duration_seconds=session.planned_duration_seconds,
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                    evidence=events,
                ),
            )
        )
    return items


async def command_rows(
    db: AsyncSession, criteria: HistoryFilter, cursor: Cursor | None, now: datetime
) -> list[tuple[Cursor, TimelineItem]]:
    if criteria.source not in (None, "remote"):
        return []
    receipt = aliased(ReportRecord)
    best_stop = (
        select(ReportRecord.event_id)
        .where(
            CommandRecord.kind == "stop",
            ReportRecord.kind == "stop_processed",
            ReportRecord.source == "remote",
            ReportRecord.boot_id == CommandRecord.boot_id,
            ReportRecord.body["request_id"].as_string() == CommandRecord.request_id,
        )
        .order_by(
            case((ReportRecord.result.in_(STOP_RECEIPTS), 0), else_=1),
            ReportRecord.sequence.desc(),
            ReportRecord.event_id.desc(),
        )
        .limit(1)
        .correlate(CommandRecord)
        .scalar_subquery()
    )
    has_session = (
        select(SessionRecord.session_id)
        .where(
            SessionRecord.request_id == CommandRecord.request_id,
            or_(
                SessionRecord.started_event_id.is_not(None),
                SessionRecord.ended_event_id.is_not(None),
            ),
        )
        .exists()
    )
    query = (
        select(CommandRecord, receipt)
        .outerjoin(receipt, receipt.event_id == best_stop)
        .where(
            or_(CommandRecord.kind == "stop", ~has_session),
        )
    )
    if criteria.result:
        selected = selected_results(criteria)
        query = query.where(
            or_(history_command_status(now).in_(selected), receipt.result.in_(selected))
        )
    rows = (
        await db.execute(
            bound_history(
                query,
                criteria,
                cursor,
                group="c",
                key=CommandRecord.request_id,
                ordered_at=CommandRecord.confirmed_at,
                event_at=CommandRecord.confirmed_at,
            )
        )
    ).all()
    return [
        (
            (command.confirmed_at, "c", command.request_id),
            TimelineItem(
                id=f"c:{command.request_id}",
                kind=f"remote_{command.kind}",
                source="remote",
                result=view.status,
                reason=view.reason,
                occurred_at=command.confirmed_at,
                received_at=None,
                time_quality="server",
                request_id=command.request_id,
                config_ref=command.config_ref,
                planned_duration_seconds=command.duration_seconds,
                evidence=[report_item(row)] if row else [],
            ),
        )
        for command, row in rows
        for view in (command_view(command, now),)
    ]


async def separate_reports(
    db: AsyncSession, criteria: HistoryFilter, cursor: Cursor | None
) -> list[tuple[Cursor, TimelineItem]]:
    matched_remote_stop = (
        select(CommandRecord.request_id)
        .where(
            CommandRecord.kind == "stop",
            CommandRecord.boot_id == ReportRecord.boot_id,
            CommandRecord.request_id == ReportRecord.body["request_id"].as_string(),
        )
        .exists()
    )
    query = select(ReportRecord).where(
        or_(
            and_(ReportRecord.kind == "recovered", ReportRecord.result == "recovered"),
            and_(
                ReportRecord.kind.in_(HISTORY_KINDS), ReportRecord.source.is_distinct_from("remote")
            ),
            and_(
                ReportRecord.kind == "stop_processed",
                ReportRecord.source == "remote",
                ~matched_remote_stop,
            ),
        )
    )
    if criteria.source:
        query = query.where(ReportRecord.source == criteria.source)
    if criteria.result:
        query = query.where(ReportRecord.result.in_(selected_results(criteria)))
    rows = (
        await db.scalars(
            bound_history(
                query,
                criteria,
                cursor,
                group="r",
                key=ReportRecord.event_id,
                ordered_at=ReportRecord.sort_at,
                event_at=ReportRecord.occurred_at,
                trusted_time=ReportRecord.body["time_quality"].as_string() != "unknown",
            )
        )
    ).all()
    return [((row.sort_at, "r", row.event_id), report_item(row)) for row in rows]


async def history_totals(db: AsyncSession, criteria: HistoryFilter) -> HistoryTotals | None:
    if (
        criteria.from_day is None
        or criteria.to_day is None
        or (criteria.to_day - criteria.from_day).days >= 31
    ):
        return None
    query = (
        select(SessionRecord.source, SessionRecord.output_duration_seconds)
        .join(ReportRecord, ReportRecord.event_id == SessionRecord.ended_event_id)
        .where(
            SessionRecord.outcome.in_(MEASURED_OUTCOMES),
            SessionRecord.output_duration_seconds.is_not(None),
            ReportRecord.body["time_quality"].as_string() != "unknown",
            ReportRecord.occurred_at >= day_start(criteria.from_day),
            ReportRecord.occurred_at < day_start(criteria.to_day + ONE_DAY),
        )
    )
    if criteria.source:
        query = query.where(SessionRecord.source == criteria.source)
    if criteria.result:
        query = query.where(SessionRecord.outcome.in_(selected_results(criteria)))
    rows = (await db.execute(query.limit(DAILY_SESSION_LIMIT + 1))).all()
    if len(rows) > DAILY_SESSION_LIMIT:
        return None  # Do not show a subtotal for an interval we could not fully count.
    by_source: dict[str, int] = {}
    for source, seconds in rows:
        by_source[source] = by_source.get(source, 0) + seconds
    return HistoryTotals(
        recorded_seconds=sum(by_source.values()) if by_source else None,
        schedule_seconds=by_source.get("schedule"),
        remote_seconds=by_source.get("remote"),
        local_button_seconds=by_source.get("local_button"),
    )


async def timeline(db: AsyncSession, criteria: HistoryFilter, now: datetime) -> TimelineView:
    validate_history_dates(criteria)
    cursor = decode_cursor(criteria.cursor, TIMELINE_GROUPS) if criteria.cursor else None
    merged = await session_rows(db, criteria, cursor)
    merged += await command_rows(db, criteria, cursor, now)
    merged += await separate_reports(db, criteria, cursor)
    merged.sort(key=lambda pair: pair[0], reverse=True)
    page = merged[: criteria.limit]
    refs = {item.config_ref for _, item in page if item.config_ref}
    known = (
        set(
            await db.scalars(
                select(ConfigRecord.config_ref).where(ConfigRecord.config_ref.in_(refs))
            )
        )
        if refs
        else set()
    )
    return TimelineView(
        items=[
            item.model_copy(update={"config_known": item.config_ref in known}) for _, item in page
        ],
        next_cursor=encode_cursor(page[-1][0]) if len(merged) > len(page) else None,
        totals=await history_totals(db, criteria),
    )
