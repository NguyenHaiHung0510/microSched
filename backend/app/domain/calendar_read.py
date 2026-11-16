"""Bounded, saved STANDARD Calendar reads; never use the browser PIN or outbox."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.calendar_membership import (
    annotation_overlap,
    event_overlap,
    from_visible_calendar_sources,
)
from app.domain.models import CalendarEvent, CalendarSource, DayAnnotation, Task
from app.domain.reading import standard_readable
from app.domain.tasks import VIETNAM_TZ, dated_task_overlap

CalendarKind = Literal["task", "event", "annotation"]
CalendarDetailKind = Literal["event", "annotation"]
CalendarVersion = tuple[datetime, tuple[UUID, datetime] | None]
KINDS: tuple[CalendarKind, ...] = ("task", "event", "annotation")
MAX_DAYS = 31
PAGE_SIZE = 40
_TEXT = 240
_DETAIL = 2000
_DAY = timedelta(days=1)


def _date_only(value):
    if type(value) is date or (
        isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    ):
        return value
    raise ValueError("use a YYYY-MM-DD date")


CalendarDate = Annotated[date, BeforeValidator(_date_only)]


class CalendarReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: CalendarDate | None = Field(default=None, description="A single Vietnam calendar day.")
    dates: tuple[CalendarDate, ...] | None = Field(default=None, min_length=1, max_length=MAX_DAYS)
    from_date: CalendarDate | None = None
    through_date: CalendarDate | None = Field(default=None, description="Inclusive range end.")
    kinds: tuple[CalendarKind, ...] = Field(default=KINDS, min_length=1, max_length=len(KINDS))
    cursor: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def check_scope(self):
        has_range = self.from_date is not None or self.through_date is not None
        if sum((self.date is not None, self.dates is not None, has_range)) != 1:
            raise ValueError("choose exactly one calendar date selection")
        if has_range and (
            self.from_date is None
            or self.through_date is None
            or not 0 <= (self.through_date - self.from_date).days < MAX_DAYS
        ):
            raise ValueError("calendar range must contain 1 to 31 inclusive days")
        days = self.days()
        if len(set(days)) != len(days) or days[0] == date.min or days[-1] == date.max:
            raise ValueError("calendar dates must be unique and support local midnight bounds")
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("calendar kinds must be unique")
        return self

    def days(self) -> tuple[date, ...]:
        if self.date is not None:
            return (self.date,)
        if self.dates is not None:
            return tuple(sorted(self.dates))
        assert self.from_date is not None and self.through_date is not None
        return tuple(
            self.from_date + timedelta(days=i)
            for i in range((self.through_date - self.from_date).days + 1)
        )


class CalendarInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CalendarDetailKind
    id: UUID


class _CalendarRow(BaseModel):
    id: UUID
    source_version: datetime
    matched_dates: tuple[date, ...] = ()
    truncated_fields: tuple[str, ...] = ()


class CalendarTaskRow(_CalendarRow):
    kind: Literal["task"] = "task"
    title: str
    status: Literal["open", "completed"]
    due_precision: Literal["date", "datetime"]
    due_on: date | None
    due_at: datetime | None


class CalendarEventSource(BaseModel):
    id: UUID
    name: str
    kind: Literal["manual", "ics", "excel"]
    source_version: datetime


class CalendarEventRow(_CalendarRow):
    kind: Literal["event"] = "event"
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    source: CalendarEventSource


class CalendarAnnotationRow(_CalendarRow):
    kind: Literal["annotation"] = "annotation"
    label: str
    starts_on: date
    ends_on: date


class CalendarEventDetail(CalendarEventRow):
    location: str | None
    description_md: str | None


class CalendarAnnotationDetail(CalendarAnnotationRow):
    note_md: str | None


CalendarRow = Annotated[
    CalendarTaskRow | CalendarEventRow | CalendarAnnotationRow, Field(discriminator="kind")
]
CalendarDetail = Annotated[
    CalendarEventDetail | CalendarAnnotationDetail, Field(discriminator="kind")
]


class CalendarReadResult(BaseModel):
    schema_version: Literal["calendar.read.v1"] = "calendar.read.v1"
    timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"
    requested_dates: tuple[date, ...]
    kinds: tuple[CalendarKind, ...]
    rows: tuple[CalendarRow, ...] = Field(max_length=PAGE_SIZE)
    count: int = Field(ge=0, le=PAGE_SIZE)
    coverage: Literal["complete", "partial"]
    has_more: bool
    continued: bool
    next_cursor: str | None
    data_as_of: datetime
    omitted_fields: tuple[str, ...] = (
        "task.body_md",
        "task.items",
        "location",
        "description_md",
        "note_md",
    )


class CalendarInspectResult(BaseModel):
    schema_version: Literal["calendar.inspect.v1"] = "calendar.inspect.v1"
    rows: tuple[CalendarDetail, ...] = Field(max_length=1)
    count: Literal[0, 1]
    coverage: Literal["complete", "unavailable"]
    data_as_of: datetime


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=VIETNAM_TZ)


def _windows(days: tuple[date, ...]) -> list[tuple[date, date]]:
    """Coalesce adjacent days without querying gaps in a disjoint request."""
    windows: list[tuple[date, date]] = []
    for day in days:
        if windows and windows[-1][1] == day - _DAY:
            windows[-1] = (windows[-1][0], day)
        else:
            windows.append((day, day))
    return windows


def _bounded(column, name: str, limit: int = _TEXT):
    # Fetch one extra character to report actual truncation without loading a
    # whole arbitrarily long imported field into Python / the model context.
    return func.left(column, limit + 1).label(name)


def _projection(kind: CalendarKind, *, detail: bool = False):
    if kind == "task":
        return standard_readable(
            select(
                Task.id,
                Task.updated_at,
                _bounded(Task.title, "title"),
                Task.status,
                Task.due_on,
                Task.due_at,
            ),
            Task,
        ), Task.id
    if kind == "event":
        columns = [
            CalendarEvent.id,
            CalendarEvent.updated_at,
            _bounded(CalendarEvent.title, "title"),
            CalendarEvent.starts_at,
            CalendarEvent.ends_at,
            CalendarEvent.all_day,
            CalendarSource.id.label("source_id"),
            _bounded(CalendarSource.name, "source_name"),
            CalendarSource.kind.label("source_kind"),
            CalendarSource.updated_at.label("source_updated_at"),
        ]
        if detail:
            columns += [
                _bounded(CalendarEvent.location, "location"),
                _bounded(CalendarEvent.description_md, "description_md", _DETAIL),
            ]
        return from_visible_calendar_sources(select(*columns)), CalendarEvent.id
    columns = [
        DayAnnotation.id,
        DayAnnotation.updated_at,
        _bounded(DayAnnotation.label, "label"),
        DayAnnotation.starts_on,
        DayAnnotation.ends_on,
    ]
    if detail:
        columns.append(_bounded(DayAnnotation.note_md, "note_md", _DETAIL))
    return standard_readable(select(*columns), DayAnnotation), DayAnnotation.id


def _match(kind: CalendarKind, first: date, last: date):
    if kind == "annotation":
        return annotation_overlap(first, last)
    start, stop = _midnight(first), _midnight(last + _DAY)
    if kind == "event":
        return event_overlap(start, stop)
    return dated_task_overlap(start, stop)


def _row(kind: CalendarKind, record, days: tuple[date, ...], *, detail: bool = False):
    fields = dict(record)
    truncated = []
    for name in ("title", "label", "source_name", "location", "description_md", "note_md"):
        value = fields.get(name)
        limit = _DETAIL if name in {"description_md", "note_md"} else _TEXT
        if value is not None and len(value) > limit:
            fields[name] = value[:limit]
            truncated.append("source.name" if name == "source_name" else name)
    fields["truncated_fields"] = tuple(truncated)
    fields["source_version"] = fields.pop("updated_at")

    if kind == "task":
        due_day = fields["due_on"] or fields["due_at"].astimezone(VIETNAM_TZ).date()
        return CalendarTaskRow(
            **fields,
            due_precision="date" if fields["due_on"] else "datetime",
            matched_dates=(due_day,),
        )
    if kind == "event":
        source = CalendarEventSource(
            id=fields.pop("source_id"),
            name=fields.pop("source_name"),
            kind=fields.pop("source_kind"),
            source_version=fields.pop("source_updated_at"),
        )
        matched = tuple(
            day
            for day in days
            if fields["starts_at"] < _midnight(day + _DAY) and fields["ends_at"] > _midnight(day)
        )
        model = CalendarEventDetail if detail else CalendarEventRow
        return model(**fields, source=source, matched_dates=matched)
    matched = tuple(day for day in days if fields["starts_on"] <= day <= fields["ends_on"])
    model = CalendarAnnotationDetail if detail else CalendarAnnotationRow
    return model(**fields, matched_dates=matched)


async def read_calendar_page(
    db: AsyncSession,
    request: CalendarReadRequest,
    *,
    after: tuple[CalendarKind, UUID] | None = None,
) -> tuple[tuple[CalendarRow, ...], bool]:
    """At most three SELECTs and PAGE_SIZE+1 projected records total.

    Order by kind then UUID for a live keyset page. Each matching entity is
    returned once, with all of its requested Vietnam days attached.
    """
    days = request.days()
    windows = _windows(days)
    rows = []
    for kind in KINDS:
        if kind not in request.kinds or (after and KINDS.index(kind) < KINDS.index(after[0])):
            continue
        stmt, id_column = _projection(kind)
        stmt = stmt.where(or_(*(_match(kind, first, last) for first, last in windows)))
        if after and kind == after[0]:
            stmt = stmt.where(id_column > after[1])
        remaining = PAGE_SIZE - len(rows)
        records = (await db.execute(stmt.order_by(id_column).limit(remaining + 1))).mappings().all()
        rows.extend(_row(kind, record, days) for record in records[:remaining])
        if len(records) > remaining:
            return tuple(rows), True
    return tuple(rows), False


async def inspect_calendar(
    db: AsyncSession, request: CalendarInspectRequest
) -> CalendarInspectResult:
    stmt, id_column = _projection(request.kind, detail=True)
    record = (await db.execute(stmt.where(id_column == request.id))).mappings().one_or_none()
    rows = (_row(request.kind, record, (), detail=True),) if record else ()
    return CalendarInspectResult(
        rows=rows,
        count=1 if rows else 0,
        coverage="complete" if rows else "unavailable",
        data_as_of=datetime.now(UTC),
    )


async def calendar_versions(
    db: AsyncSession, kind: CalendarKind, ids: set[UUID], *, lock: bool = False
) -> dict[UUID, CalendarVersion]:
    """Recheck version and current visibility before replaying an in-run tool payload."""
    if kind == "event":
        stmt = from_visible_calendar_sources(
            select(
                CalendarEvent.id,
                CalendarEvent.updated_at,
                CalendarSource.id,
                CalendarSource.updated_at,
            )
        ).where(CalendarEvent.id.in_(ids))
        if lock:
            # Import/delete lock parents before touching events. Take the same
            # order; the final joined read only accepts sources we locked.
            source_ids = await db.scalars(
                select(CalendarSource.id)
                .where(
                    CalendarSource.id.in_(
                        select(CalendarEvent.source_id).where(CalendarEvent.id.in_(ids))
                    )
                )
                .order_by(CalendarSource.id)
                .with_for_update(read=True)
            )
            stmt = (
                stmt.where(CalendarSource.id.in_(source_ids.all()))
                .order_by(CalendarEvent.id)
                .with_for_update(read=True, of=CalendarEvent)
            )
        return {
            eid: (version, (source_id, source_version))
            for eid, version, source_id, source_version in (await db.execute(stmt))
        }
    model = Task if kind == "task" else DayAnnotation
    stmt = standard_readable(select(model.id, model.updated_at).where(model.id.in_(ids)), model)
    if lock:
        stmt = stmt.order_by(model.id).with_for_update(read=True)
    return {eid: (version, None) for eid, version in (await db.execute(stmt))}
