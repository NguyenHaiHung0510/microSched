"""Calendar DTOs and request-scoped persistence for the 010a slice."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ics import ParseReport, parse_ics
from app.domain.models import AuthSession, CalendarEvent, CalendarSource
from app.domain.reading import readable

CalendarSourceKind = Literal["ics", "manual"]


def _require_uuidv7(value: UUID | None) -> UUID | None:
    if value is not None and value.version != 7:
        raise ValueError("id must be a UUIDv7")
    return value


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return value


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


class SourceCreate(BaseModel):
    """Fields accepted when creating an ICS or manual source."""

    id: UUID | None = None
    name: str = Field(min_length=1, max_length=256)
    kind: CalendarSourceKind
    color: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def normalize(self) -> "SourceCreate":
        self.id = _require_uuidv7(self.id)
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name cannot be blank")
        self.color = _clean_optional(self.color)
        return self


class SourceUpdate(BaseModel):
    """Patchable source fields; ``kind`` is intentionally immutable."""

    name: str | None = Field(default=None, min_length=1, max_length=256)
    color: str | None = Field(default=None, max_length=32)
    is_visible: bool | None = None

    @model_validator(mode="after")
    def normalize_and_reject_nulls(self) -> "SourceUpdate":
        if "name" in self.model_fields_set:
            if self.name is None:
                raise ValueError("name cannot be null")
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("name cannot be blank")
        if "is_visible" in self.model_fields_set and self.is_visible is None:
            raise ValueError("is_visible cannot be null")
        if "color" in self.model_fields_set:
            self.color = _clean_optional(self.color)
        return self


class SourceRead(BaseModel):
    """Source returned at the API boundary, including its current event count."""

    id: UUID
    name: str
    kind: str
    color: str | None
    is_visible: bool
    event_count: int
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)


class EventCreate(BaseModel):
    """Fields accepted for a manually created event."""

    id: UUID | None = None
    source_id: UUID
    title: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False
    location: str | None = None
    description_md: str | None = None

    @model_validator(mode="after")
    def normalize_and_validate(self) -> "EventCreate":
        self.id = _require_uuidv7(self.id)
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title cannot be blank")
        self.starts_at = _require_aware(self.starts_at, "starts_at")
        self.ends_at = _require_aware(self.ends_at, "ends_at")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        self.location = _clean_optional(self.location)
        self.description_md = _clean_optional(self.description_md)
        return self


class EventUpdate(BaseModel):
    """Patchable event fields; source ownership cannot be changed."""

    title: str | None = Field(default=None, min_length=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = None
    description_md: str | None = None

    @model_validator(mode="after")
    def normalize_and_reject_nulls(self) -> "EventUpdate":
        for field_name in ("title", "starts_at", "ends_at", "all_day"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if "title" in self.model_fields_set:
            self.title = self.title.strip() if self.title is not None else None
            if not self.title:
                raise ValueError("title cannot be blank")
        if self.starts_at is not None:
            self.starts_at = _require_aware(self.starts_at, "starts_at")
        if self.ends_at is not None:
            self.ends_at = _require_aware(self.ends_at, "ends_at")
        if "location" in self.model_fields_set:
            self.location = _clean_optional(self.location)
        if "description_md" in self.model_fields_set:
            self.description_md = _clean_optional(self.description_md)
        if self.starts_at is not None and self.ends_at is not None:
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at")
        return self


class EventRead(BaseModel):
    """Event returned at the API boundary; hidden state is intentionally absent."""

    id: UUID
    source_id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    location: str | None
    description_md: str | None
    created_at: datetime | None
    updated_at: datetime | None


class ImportRequest(BaseModel):
    """JSON import body; raw body size is guarded by the application middleware."""

    filename: str = Field(min_length=1, max_length=256)
    content: str = Field(max_length=1_048_576)

    @model_validator(mode="after")
    def normalize(self) -> "ImportRequest":
        self.filename = self.filename.strip()
        if not self.filename:
            raise ValueError("filename cannot be blank")
        return self


class ImportReport(BaseModel):
    """Safe import receipt; skipped reasons never contain source content."""

    parsed: int
    inserted: int
    removed: int
    duplicates: int
    skipped: list[str]


class SourceNameTaken(Exception):
    """A source name collides with an existing source."""

    def __init__(self, existing_source_id: UUID):
        self.existing_source_id = existing_source_id


class SourceNotFound(Exception):
    """The requested source is not visible or does not exist."""


class EventNotFound(Exception):
    """The requested event does not exist."""


class ManualSourceImportForbidden(Exception):
    """Manual sources cannot be overwritten by an ICS import."""


class IcsEventCreationForbidden(Exception):
    """Imported sources cannot receive hand-created events."""


class CalendarImportRejected(Exception):
    """An import cannot safely replace the current source events."""

    def __init__(self, message: str, skipped: list[str] | None = None):
        self.message = message
        self.skipped = skipped or []


class CalendarStore:
    """Stateless calendar persistence; methods join the request transaction."""

    async def _source(
        self,
        db: AsyncSession,
        auth: AuthSession,
        source_id: UUID,
        *,
        for_update: bool = False,
    ) -> CalendarSource:
        stmt = readable(
            select(CalendarSource).where(CalendarSource.id == source_id), CalendarSource, auth
        )
        if for_update:
            stmt = stmt.with_for_update()
        source = (await db.execute(stmt)).scalar_one_or_none()
        if source is None:
            raise SourceNotFound
        return source

    async def _source_read(self, db: AsyncSession, source: CalendarSource) -> SourceRead:
        count = await db.scalar(
            select(func.count(CalendarEvent.id)).where(CalendarEvent.source_id == source.id)
        )
        return SourceRead(
            id=source.id,
            name=source.name,
            kind=source.kind,
            color=source.color,
            is_visible=source.is_visible,
            event_count=int(count or 0),
            created_at=source.created_at,
            updated_at=source.updated_at,
        )

    @staticmethod
    def _event_read(event: CalendarEvent) -> EventRead:
        return EventRead(
            id=event.id,
            source_id=event.source_id,
            title=event.title,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            all_day=event.all_day,
            location=event.location,
            description_md=event.description_md,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    async def list_sources(self, db: AsyncSession, auth: AuthSession) -> list[SourceRead]:
        """List every source without pagination and with a live event count."""
        stmt = readable(select(CalendarSource), CalendarSource, auth).order_by(
            func.lower(CalendarSource.name), CalendarSource.id
        )
        sources = list((await db.execute(stmt)).scalars())
        return [await self._source_read(db, source) for source in sources]

    async def create_source(
        self, db: AsyncSession, auth: AuthSession, payload: SourceCreate
    ) -> SourceRead:
        """Create a source, or return the existing row for an explicit repeated ID."""
        if payload.id is not None:
            existing_by_id = await db.scalar(
                readable(
                    select(CalendarSource).where(CalendarSource.id == payload.id),
                    CalendarSource,
                    auth,
                )
            )
            if existing_by_id is not None:
                result = await self._source_read(db, existing_by_id)
                result.created = False
                return result

        existing = await db.scalar(
            readable(
                select(CalendarSource).where(
                    func.lower(CalendarSource.name) == payload.name.lower()
                ),
                CalendarSource,
                auth,
            )
        )
        if existing is not None:
            raise SourceNameTaken(existing.id)

        source = CalendarSource(
            id=payload.id,
            name=payload.name,
            kind=payload.kind,
            color=payload.color,
        )
        try:
            async with db.begin_nested():
                db.add(source)
                await db.flush()
        except IntegrityError as error:
            existing = await db.scalar(
                select(CalendarSource).where(
                    func.lower(CalendarSource.name) == payload.name.lower()
                )
            )
            if existing is not None:
                raise SourceNameTaken(existing.id) from error
            raise
        result = await self._source_read(db, source)
        result.created = True
        return result

    async def update_source(
        self, db: AsyncSession, auth: AuthSession, source_id: UUID, payload: SourceUpdate
    ) -> SourceRead:
        """Patch a source while preserving its immutable kind."""
        source = await self._source(db, auth, source_id, for_update=True)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            existing = await db.scalar(
                select(CalendarSource).where(
                    func.lower(CalendarSource.name) == changes["name"].lower(),
                    CalendarSource.id != source_id,
                )
            )
            if existing is not None:
                raise SourceNameTaken(existing.id)
        for field, value in changes.items():
            setattr(source, field, value)
        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError as error:
            existing = await db.scalar(
                select(CalendarSource).where(
                    func.lower(CalendarSource.name) == source.name.lower(),
                    CalendarSource.id != source_id,
                )
            )
            if existing is not None:
                raise SourceNameTaken(existing.id) from error
            raise
        return await self._source_read(db, source)

    async def delete_source(self, db: AsyncSession, auth: AuthSession, source_id: UUID) -> None:
        """Hard-delete a source; PostgreSQL cascades its events."""
        await self._source(db, auth, source_id, for_update=True)
        await db.execute(delete(CalendarSource).where(CalendarSource.id == source_id))

    async def import_into_source(
        self, db: AsyncSession, auth: AuthSession, source_id: UUID, payload: ImportRequest
    ) -> ImportReport:
        """Parse first, then replace a source's events atomically and safely."""
        try:
            report: ParseReport = parse_ics(payload.content)
        except ValueError as error:
            raise CalendarImportRejected("Tệp lịch không hợp lệ hoặc vượt giới hạn") from error
        if not report.events:
            raise CalendarImportRejected(
                "Không đọc được buổi nào từ file — chưa thay đổi gì", report.skipped
            )

        source = await self._source(db, auth, source_id, for_update=True)
        if source.kind == "manual":
            raise ManualSourceImportForbidden

        deleted = await db.execute(
            delete(CalendarEvent).where(CalendarEvent.source_id == source.id)
        )
        removed = int(deleted.rowcount or 0)
        db.add_all(
            [
                CalendarEvent(
                    source_id=source.id,
                    title=event.title,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    all_day=event.all_day,
                    location=event.location,
                    description_md=event.description_md,
                )
                for event in report.events
            ]
        )
        await db.flush()
        return ImportReport(
            parsed=len(report.events) + report.duplicates + len(report.skipped),
            inserted=len(report.events),
            removed=removed,
            duplicates=report.duplicates,
            skipped=report.skipped,
        )

    async def list_events(
        self,
        db: AsyncSession,
        auth: AuthSession,
        from_: datetime,
        to: datetime,
        include_hidden_sources: bool,
    ) -> list[EventRead]:
        """List every event whose interval intersects the requested range."""
        stmt = readable(
            select(CalendarEvent).where(
                CalendarEvent.starts_at < to,
                CalendarEvent.ends_at > from_,
            ),
            CalendarEvent,
            auth,
        )
        if not include_hidden_sources:
            stmt = stmt.join(CalendarSource, CalendarSource.id == CalendarEvent.source_id).where(
                CalendarSource.is_visible.is_(True)
            )
        stmt = stmt.order_by(CalendarEvent.starts_at, CalendarEvent.id)
        return [self._event_read(event) for event in (await db.execute(stmt)).scalars()]

    async def create_event(
        self, db: AsyncSession, auth: AuthSession, payload: EventCreate
    ) -> EventRead:
        """Create a manual event only under a manual source."""
        source = await self._source(db, auth, payload.source_id, for_update=True)
        if source.kind == "ics":
            raise IcsEventCreationForbidden
        event = CalendarEvent(**payload.model_dump())
        db.add(event)
        await db.flush()
        return self._event_read(event)

    async def update_event(
        self, db: AsyncSession, auth: AuthSession, event_id: UUID, payload: EventUpdate
    ) -> EventRead:
        """Patch an event without allowing reparenting."""
        stmt = readable(
            select(CalendarEvent).where(CalendarEvent.id == event_id), CalendarEvent, auth
        )
        event = (await db.execute(stmt.with_for_update())).scalar_one_or_none()
        if event is None:
            raise EventNotFound
        changes = payload.model_dump(exclude_unset=True)
        starts_at = changes.get("starts_at", event.starts_at)
        ends_at = changes.get("ends_at", event.ends_at)
        if starts_at >= ends_at:
            raise ValueError("ends_at must be after starts_at")
        for field, value in changes.items():
            setattr(event, field, value)
        await db.flush()
        return self._event_read(event)

    async def delete_event(self, db: AsyncSession, auth: AuthSession, event_id: UUID) -> None:
        """Hard-delete one event."""
        stmt = readable(
            select(CalendarEvent).where(CalendarEvent.id == event_id), CalendarEvent, auth
        )
        event = (await db.execute(stmt.with_for_update())).scalar_one_or_none()
        if event is None:
            raise EventNotFound
        await db.execute(delete(CalendarEvent).where(CalendarEvent.id == event_id))
