"""Day-annotation DTOs and request-scoped persistence for the 010b slice."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession, DayAnnotation
from app.domain.reading import readable


def _require_uuidv7(value: UUID | None) -> UUID | None:
    if value is not None and value.version != 7:
        raise ValueError("id must be a UUIDv7")
    return value


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


class AnnotationCreate(BaseModel):
    """Fields accepted when marking a day or a date range."""

    id: UUID | None = None
    starts_on: date
    ends_on: date | None = None
    label: str = Field(min_length=1, max_length=256)
    note_md: str | None = None
    color: str | None = Field(default=None, max_length=32)
    is_private: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "AnnotationCreate":
        """Enforce the inclusive date range while both values are still present."""
        self.id = _require_uuidv7(self.id)
        self.ends_on = self.ends_on or self.starts_on
        self.label = self.label.strip()
        if not self.label:
            raise ValueError("label cannot be blank")
        self.note_md = _clean_optional(self.note_md)
        self.color = _clean_optional(self.color)
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class AnnotationUpdate(BaseModel):
    """Patchable annotation fields; every non-null column rejects an explicit null."""

    starts_on: date | None = None
    ends_on: date | None = None
    label: str | None = Field(default=None, min_length=1, max_length=256)
    note_md: str | None = None
    color: str | None = Field(default=None, max_length=32)
    is_private: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "AnnotationUpdate":
        """Explicit nulls cannot replace the NOT NULL date/label columns."""
        for field_name in ("starts_on", "ends_on", "label"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if "label" in self.model_fields_set and self.label is not None:
            self.label = self.label.strip()
            if not self.label:
                raise ValueError("label cannot be blank")
        if "note_md" in self.model_fields_set:
            self.note_md = _clean_optional(self.note_md)
        if "color" in self.model_fields_set:
            self.color = _clean_optional(self.color)
        return self


class AnnotationRead(BaseModel):
    """Annotation returned at the API boundary."""

    id: UUID
    starts_on: date
    ends_on: date
    label: str
    note_md: str | None
    color: str | None
    is_private: bool
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)


class AnnotationNotFound(Exception):
    """The requested annotation does not exist or is hidden by a reading gate."""


class AnnotationStore:
    """Stateless annotation persistence; methods join the request transaction."""

    @staticmethod
    def _read(annotation: DayAnnotation) -> AnnotationRead:
        return AnnotationRead(
            id=annotation.id,
            starts_on=annotation.starts_on,
            ends_on=annotation.ends_on,
            label=annotation.label,
            note_md=annotation.note_md,
            color=annotation.color,
            is_private=annotation.is_private,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )

    async def list_annotations(
        self,
        db: AsyncSession,
        auth: AuthSession,
        from_: date,
        to: date,
    ) -> list[AnnotationRead]:
        """List every annotation whose inclusive range intersects the request."""
        stmt = readable(
            select(DayAnnotation).where(
                DayAnnotation.starts_on <= to,
                DayAnnotation.ends_on >= from_,
            ),
            DayAnnotation,
            auth,
        ).order_by(DayAnnotation.starts_on, DayAnnotation.created_at, DayAnnotation.id)
        return [self._read(item) for item in (await db.execute(stmt)).scalars()]

    async def create(
        self,
        db: AsyncSession,
        auth: AuthSession,
        payload: AnnotationCreate,
    ) -> AnnotationRead:
        """Create an annotation, or return the existing row for a repeated ID."""
        if payload.id is not None:
            existing = await db.scalar(
                readable(
                    select(DayAnnotation).where(DayAnnotation.id == payload.id),
                    DayAnnotation,
                    auth,
                )
            )
            if existing is not None:
                result = self._read(existing)
                result.created = False
                return result

        annotation = DayAnnotation(**payload.model_dump())
        db.add(annotation)
        await db.flush()
        result = self._read(annotation)
        result.created = True
        return result

    async def update(
        self,
        db: AsyncSession,
        auth: AuthSession,
        annotation_id: UUID,
        payload: AnnotationUpdate,
    ) -> AnnotationRead:
        """Patch an annotation, validating the range on the merged values."""
        stmt = readable(
            select(DayAnnotation).where(DayAnnotation.id == annotation_id),
            DayAnnotation,
            auth,
        )
        annotation = (await db.execute(stmt.with_for_update())).scalar_one_or_none()
        if annotation is None:
            raise AnnotationNotFound

        changes = payload.model_dump(exclude_unset=True)
        starts_on = changes.get("starts_on", annotation.starts_on)
        ends_on = changes.get("ends_on", annotation.ends_on)
        if ends_on < starts_on:
            raise ValueError("ends_on must be on or after starts_on")

        for field, value in changes.items():
            setattr(annotation, field, value)
        await db.flush()
        return self._read(annotation)

    async def delete(
        self,
        db: AsyncSession,
        auth: AuthSession,
        annotation_id: UUID,
    ) -> None:
        """Hard-delete one annotation."""
        stmt = readable(
            select(DayAnnotation).where(DayAnnotation.id == annotation_id),
            DayAnnotation,
            auth,
        )
        annotation = (await db.execute(stmt.with_for_update())).scalar_one_or_none()
        if annotation is None:
            raise AnnotationNotFound
        await db.execute(delete(DayAnnotation).where(DayAnnotation.id == annotation_id))
