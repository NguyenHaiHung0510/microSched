"""Read-side projections. All displayed output is Controller-reported."""

import base64
import binascii
import json
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import Field, TypeAdapter, ValidationError
from sqlalchemy import Select, and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.migarden.commands import (
    STOP_PENDING,
    WAITING,
    CommandView,
    command_view,
    latest,
    start_block_reason,
)
from app.domain.migarden.configuration import ConfigView, read_config
from app.domain.migarden.models import CommandRecord, ConfigRecord, ReportRecord, SessionRecord
from app.domain.migarden.schedule import ONE_DAY, Forecast, day_start, forecast, local_day
from app.domain.migarden.storage import Rejected, get_config, read_zone
from app.domain.migarden.wire import (
    BINDING,
    HOLDOFF,
    ZONE,
    Snapshot,
    Source,
    UTCDateTime,
    WireModel,
)

Connection = Literal["unconfigured", "waiting", "fresh", "stale"]
HISTORY_KINDS = ("occurrence_decided", "request_rejected", "stop_processed")
DAILY_SESSION_LIMIT = 4096


class StateView(WireModel):
    zone_id: str = ZONE
    binding_ref: str = BINDING
    server_time: datetime
    connection: Connection
    last_seen_at: datetime | None = None
    snapshot: Snapshot | None = None
    snapshot_received_at: datetime | None = None
    config: ConfigView
    start_block_reason: str | None
    stop_available: bool = False
    start_request: CommandView | None = None
    stop_request: CommandView | None = None
    next_schedule: Forecast


async def state(db: AsyncSession, now: datetime) -> StateView:
    zone = await read_zone(db)
    config = await read_config(db, zone)
    reason = await start_block_reason(db, zone, now)
    last_start = await latest(db, "start") if zone else None
    last_stop = await latest(db, "stop") if zone else None
    connection: Connection = "unconfigured"
    if zone is not None and zone.device_id is not None:
        if zone.snapshot_received_at is None:
            connection = "waiting"
        elif zone.snapshot_received_at < now - HOLDOFF or zone.revoked_at is not None:
            connection = "stale"
        else:
            connection = "fresh"
    return StateView(
        server_time=now,
        connection=connection,
        last_seen_at=zone.last_seen_at if zone else None,
        snapshot=Snapshot.model_validate(zone.snapshot) if zone and zone.snapshot else None,
        snapshot_received_at=zone.snapshot_received_at if zone else None,
        config=config,
        start_block_reason=reason,
        stop_available=bool(
            zone
            and zone.device_id
            and (zone.stop_target_boot_id or zone.boot_id)
            and zone.revoked_at is None
        ),
        start_request=command_view(last_start, now) if last_start else None,
        stop_request=command_view(last_stop, now) if last_stop else None,
        next_schedule=forecast(config.applied, now),
    )


class DailyPoint(WireModel):
    day: date
    schedule_seconds: int | None = None
    remote_seconds: int | None = None
    local_button_seconds: int | None = None
    coverage: Literal["unknown", "partial"] = "unknown"


class DailyView(WireModel):
    days: list[DailyPoint]
    forecast: Forecast


def allocate_reported(
    started_at: datetime | None, ended_at: datetime | None, duration: int | None
) -> list[tuple[date, int]]:
    if started_at is None or ended_at is None or duration is None:
        return []
    if ended_at < started_at or abs((ended_at - started_at).total_seconds() - duration) > 1:
        return []  # A wall-clock jump cannot locate elapsed time across midnight.
    try:
        end = started_at + timedelta(seconds=duration)
    except OverflowError:
        return []
    if duration == 0:
        # An explicit zero-length closed report is evidence, not a completeness marker.
        return [(local_day(started_at), 0)]
    result = []
    cursor = started_at
    while cursor < end:
        day = local_day(cursor)
        cut = min(end, day_start(day + ONE_DAY))
        start_offset = int((cursor - started_at).total_seconds())
        end_offset = int((cut - started_at).total_seconds())
        result.append((day, end_offset - start_offset))
        cursor = cut
    return result


async def daily(db: AsyncSession, days: int, now: datetime) -> DailyView:
    today = local_day(now)
    oldest = today - timedelta(days=days - 1)
    records = (
        await db.execute(
            select(SessionRecord, ReportRecord)
            .join(ReportRecord, ReportRecord.event_id == SessionRecord.ended_event_id)
            .where(
                SessionRecord.outcome.in_(("completed", "stopped", "fault")),
                SessionRecord.output_duration_seconds.is_not(None),
                SessionRecord.ended_at >= day_start(oldest),
                SessionRecord.started_at < day_start(today + ONE_DAY),
            )
            .order_by(SessionRecord.ended_at.desc(), SessionRecord.session_id.desc())
            .limit(DAILY_SESSION_LIMIT)
        )
    ).all()
    buckets: dict[date, dict[str, int]] = {oldest + timedelta(days=i): {} for i in range(days)}
    for session, report in records:
        if report.body["time_quality"] == "unknown" or session.ended_at > now:
            continue
        # Bound projection work even for a fault report claiming an extreme output
        # interval. Only days in the window can contribute.
        cursor = session.started_at
        elapsed = session.output_duration_seconds
        if cursor < day_start(oldest):
            shift = int((day_start(oldest) - cursor).total_seconds())
            if shift > elapsed:
                continue
            cursor += timedelta(seconds=shift)
            elapsed -= shift
        for day, seconds in allocate_reported(cursor, session.ended_at, elapsed):
            if day in buckets:
                bucket = buckets[day]
                bucket[session.source] = bucket.get(session.source, 0) + seconds
    zone = await read_zone(db)
    applied = await get_config(db, zone.applied_ref) if zone else None
    return DailyView(
        days=[
            DailyPoint(
                day=day,
                schedule_seconds=source.get("schedule"),
                remote_seconds=source.get("remote"),
                local_button_seconds=source.get("local_button"),
                coverage="partial" if source else "unknown",
            )
            for day, source in buckets.items()
        ],
        forecast=forecast(applied, now),
    )


class HistoryItem(WireModel):
    id: str
    kind: str
    source: Source | None
    result: str | None
    reason: str | None = None
    occurred_at: datetime | None
    received_at: datetime | None
    time_quality: str | None
    request_id: str | None = None
    session_id: str | None = None
    config_ref: str | None
    config_known: bool = False
    duration_seconds: int | None = None
    planned_duration_seconds: int | None = None
    scheduled_at: datetime | None = None


class HistoryView(WireModel):
    items: list[HistoryItem]
    next_cursor: str | None = None
    coverage: Literal["partial"] = "partial"


class HistoryFilter(WireModel):
    view: Literal["events", "sessions"] = "events"
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=384)
    from_day: date | None = None
    to_day: date | None = None
    source: Source | None = None
    result: (
        Literal[
            "completed",
            "stopped",
            "fault",
            "unknown",
            "rejected",
            "skipped",
            "started",
            "stop_processed",
            "recovered",
        ]
        | None
    ) = None


Cursor = tuple[datetime, str, str]


def decode_cursor(value: str, groups: tuple[str, ...] = ("c", "r", "s", "t")) -> Cursor:
    try:
        timestamp, group, key = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if group not in groups or not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError
        return TypeAdapter(UTCDateTime).validate_python(timestamp), group, key
    except (TypeError, ValueError, ValidationError, binascii.Error) as error:
        raise Rejected("invalid_history_cursor", 422) from error


def encode_cursor(key: Cursor) -> str:
    at, group, locator = key
    return base64.urlsafe_b64encode(json.dumps([at.isoformat(), group, locator]).encode()).decode()


def bound_history(
    query: Select,
    criteria: HistoryFilter,
    cursor: Cursor | None,
    *,
    group: str,
    key,
    ordered_at,
    event_at,
    trusted_time=True,
) -> Select:
    if criteria.from_day:
        query = query.where(trusted_time, event_at >= day_start(criteria.from_day))
    if criteria.to_day:
        query = query.where(trusted_time, event_at < day_start(criteria.to_day + ONE_DAY))
    if cursor:
        at, previous_group, previous_key = cursor
        if group < previous_group:
            query = query.where(ordered_at <= at)
        elif group > previous_group:
            query = query.where(ordered_at < at)
        else:
            query = query.where(or_(ordered_at < at, and_(ordered_at == at, key < previous_key)))
    return query.order_by(ordered_at.desc(), key.desc()).limit(criteria.limit + 1)


def validate_history_dates(criteria: HistoryFilter) -> None:
    if (
        (criteria.from_day and criteria.from_day.year in {1, 9999})
        or (criteria.to_day and criteria.to_day.year in {1, 9999})
        or (criteria.from_day and criteria.to_day and criteria.from_day > criteria.to_day)
    ):
        raise Rejected("invalid_date_range", 422)


def history_command_status(now: datetime):
    return case(
        (and_(CommandRecord.status.in_(WAITING), CommandRecord.expires_at <= now), "expired"),
        (and_(CommandRecord.status == "granted", CommandRecord.expires_at <= now), "unknown"),
        (
            and_(
                CommandRecord.status.in_(STOP_PENDING),
                CommandRecord.confirmed_at <= now - HOLDOFF,
            ),
            "stop_unconfirmed",
        ),
        else_=CommandRecord.status,
    )


async def history(db: AsyncSession, criteria: HistoryFilter, now: datetime) -> HistoryView:
    validate_history_dates(criteria)
    cursor = decode_cursor(criteria.cursor) if criteria.cursor else None
    merged: list[tuple[Cursor, HistoryItem]] = []

    requested = criteria.result
    selected = (
        ("stopped", "stop_confirmed", "close_requested", "already_off")
        if requested == "stop_processed"
        else (requested,)
    )
    if criteria.source in (None, "remote"):
        query = select(CommandRecord)
        if requested:
            query = query.where(history_command_status(now).in_(selected))
        for row in (
            await db.scalars(
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
        ).all():
            view = command_view(row, now)
            merged.append(
                (
                    (row.confirmed_at, "c", row.request_id),
                    HistoryItem(
                        id=f"c:{row.request_id}",
                        kind=f"remote_{row.kind}",
                        source="remote",
                        result=view.status,
                        reason=view.reason,
                        occurred_at=row.confirmed_at,
                        received_at=None,
                        time_quality="server",
                        request_id=row.request_id,
                        config_ref=row.config_ref,
                        planned_duration_seconds=row.duration_seconds,
                    ),
                )
            )

    trusted = ReportRecord.body["time_quality"].as_string() != "unknown"
    query = select(ReportRecord).where(
        or_(
            ReportRecord.kind.in_(HISTORY_KINDS),
            and_(ReportRecord.kind == "recovered", ReportRecord.result == "recovered"),
        ),
        # Known remote actions are already represented by their command row.
        or_(
            ReportRecord.source != "remote",
            ReportRecord.source.is_(None),
            ReportRecord.kind == "recovered",
        ),
    )
    if criteria.source:
        query = query.where(ReportRecord.source == criteria.source)
    if requested:
        query = query.where(ReportRecord.result.in_(selected))
    for row in (
        await db.scalars(
            bound_history(
                query,
                criteria,
                cursor,
                group="r",
                key=ReportRecord.event_id,
                ordered_at=ReportRecord.sort_at,
                event_at=ReportRecord.occurred_at,
                trusted_time=trusted,
            )
        )
    ).all():
        data, payload = row.body, row.body["payload"]
        merged.append(
            (
                (row.sort_at, "r", row.event_id),
                HistoryItem(
                    id=f"r:{row.event_id}",
                    kind=row.kind,
                    source=row.source,
                    result=row.result,
                    reason=payload.get("reason"),
                    occurred_at=row.occurred_at,
                    received_at=row.received_at,
                    time_quality=data["time_quality"],
                    request_id=data.get("request_id"),
                    session_id=data.get("session_id"),
                    config_ref=row.config_ref,
                    scheduled_at=payload.get("scheduled_at"),
                ),
            )
        )

    for group in ("s", "t"):
        start = group == "s"
        if start and requested not in (None, "started"):
            continue
        by_time = SessionRecord.start_sort_at if start else SessionRecord.end_sort_at
        event_id = SessionRecord.started_event_id if start else SessionRecord.ended_event_id
        query = select(SessionRecord, ReportRecord).join(
            ReportRecord, ReportRecord.event_id == event_id
        )
        if criteria.source:
            query = query.where(SessionRecord.source == criteria.source)
        if not start and requested:
            query = query.where(SessionRecord.outcome.in_(selected))
        pairs = (
            await db.execute(
                bound_history(
                    query,
                    criteria,
                    cursor,
                    group=group,
                    key=SessionRecord.session_id,
                    ordered_at=by_time,
                    event_at=ReportRecord.occurred_at,
                    trusted_time=trusted,
                )
            )
        ).all()
        for session, report in pairs:
            at = session.start_sort_at if start else session.end_sort_at
            merged.append(
                (
                    (at, group, session.session_id),
                    HistoryItem(
                        id=f"{group}:{session.session_id}",
                        kind="session_started" if start else "session_ended",
                        source=session.source,
                        result="started" if start else session.outcome,
                        reason=None if start else session.reason,
                        occurred_at=report.occurred_at,
                        received_at=report.received_at,
                        time_quality=report.body["time_quality"],
                        request_id=session.request_id,
                        session_id=session.session_id,
                        config_ref=session.config_ref,
                        duration_seconds=None if start else session.output_duration_seconds,
                        planned_duration_seconds=session.planned_duration_seconds,
                    ),
                )
            )

    ordered = sorted(merged, key=lambda item: item[0], reverse=True)
    page = ordered[: criteria.limit]
    refs = {item.config_ref for _, item in page if item.config_ref}
    configs = (
        {
            row.config_ref: row.bundle
            for row in (
                await db.scalars(select(ConfigRecord).where(ConfigRecord.config_ref.in_(refs)))
            ).all()
        }
        if refs
        else {}
    )
    result = []
    for _, item in page:
        bundle = configs.get(item.config_ref)
        planned = item.planned_duration_seconds
        if bundle and planned is None and item.kind == "session_ended":
            if item.source == "schedule":
                planned = bundle["schedule"]["duration_seconds"]
            elif item.source == "local_button":
                planned = bundle["policy"]["manual_duration_seconds"]
        result.append(
            item.model_copy(
                update={
                    "config_known": bundle is not None,
                    "planned_duration_seconds": planned,
                }
            )
        )
    return HistoryView(
        items=result, next_cursor=encode_cursor(page[-1][0]) if len(ordered) > len(page) else None
    )
