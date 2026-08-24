"""Note DTOs and the request-scoped Postgres store."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain.models import AuthSession, Note, NoteItem
from app.domain.reading import can_see_private, readable, with_privacy_gate

NonEmptyText = Annotated[str, Field(min_length=1)]


class NoteItemCreate(BaseModel):
    """Fields accepted when appending a checklist item."""

    content: str = Field(min_length=1)
    position: int = Field(default=0, ge=0)


class NoteItemUpdate(BaseModel):
    """Optional checklist changes; ``note_id`` exists only to reject reparenting."""

    content: str | None = Field(default=None, min_length=1)
    is_completed: bool | None = None
    position: int | None = Field(default=None, ge=0)
    note_id: UUID | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "NoteItemUpdate":
        """Explicit nulls cannot replace non-null checklist columns."""
        for field in ("content", "is_completed", "position"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class NoteItemRead(BaseModel):
    """Decrypted checklist item returned at the API boundary."""

    id: UUID
    content: str
    is_completed: bool
    position: int
    created_at: datetime | None
    updated_at: datetime | None


class NoteCreate(BaseModel):
    """Fields accepted when creating a note and its initial checklist."""

    id: UUID | None = None
    title: str | None = None
    body_md: str | None = None
    is_private: bool = False
    pinned: bool = False
    items: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_uuidv7(self) -> "NoteCreate":
        """Client-selected note IDs must preserve the UUIDv7 ordering contract."""
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        return self


class NoteUpdate(BaseModel):
    """Patch semantics for a note; only explicitly supplied fields are changed."""

    title: str | None = Field(default=None)
    body_md: str | None = None
    is_private: bool | None = None
    pinned: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "NoteUpdate":
        """Only the non-null boolean flags reject an explicit null."""
        for field in ("is_private", "pinned"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class NoteRead(BaseModel):
    """Decrypted note returned at the API boundary, without its embedding."""

    id: UUID
    title: str | None
    body_md: str | None
    is_private: bool
    pinned: bool = False
    items: list[NoteItemRead]
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)


class NoteIdConflict(Exception):
    """A client-selected ID belongs to a row hidden by a reading gate."""


class PrivateWriteLocked(Exception):
    """A write tried to create private data while the display gate was closed."""


def _clear(value: str | None) -> str | None:
    """Decrypt a stored value when needed, preserving nullable fields."""
    if value is None:
        return None
    return crypto.decrypt(value) if crypto.is_encrypted(value) else value


def _sealed(value: str | None) -> str | None:
    """Encrypt a logical value exactly once, preserving nullable fields."""
    if value is None:
        return None
    return value if crypto.is_encrypted(value) else crypto.encrypt(value)


class NoteStore:
    """Stateless note persistence; every method joins its request transaction."""

    async def _parent(
        self,
        db: AsyncSession,
        auth: AuthSession,
        note_id: UUID,
        *,
        for_update: bool = False,
    ) -> Note | None:
        stmt = readable(select(Note).where(Note.id == note_id), Note, auth)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _items(self, db: AsyncSession, note_id: UUID) -> list[NoteItem]:
        result = await db.execute(
            select(NoteItem)
            .where(NoteItem.note_id == note_id)
            .order_by(NoteItem.position, NoteItem.created_at)
        )
        return list(result.scalars())

    def _item_read(self, item: NoteItem) -> NoteItemRead:
        return NoteItemRead(
            id=item.id,
            content=_clear(item.content),
            is_completed=item.is_completed,
            position=item.position,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _note_read(self, note: Note, items: list[NoteItem]) -> NoteRead:
        return NoteRead(
            id=note.id,
            title=_clear(note.title),
            body_md=_clear(note.body_md),
            is_private=note.is_private,
            pinned=note.pinned,
            items=[self._item_read(item) for item in items],
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    async def list(
        self,
        db: AsyncSession,
        auth: AuthSession,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NoteRead]:
        """List visible notes and their children, pinned first then newest first."""
        stmt = readable(select(Note), Note, auth).order_by(
            Note.pinned.desc(), Note.created_at.desc()
        )
        result = await db.execute(stmt.limit(limit).offset(offset))
        parents = list(result.scalars())
        if not parents:
            return []

        note_ids = [note.id for note in parents]
        child_result = await db.execute(
            select(NoteItem)
            .where(NoteItem.note_id.in_(note_ids))
            .order_by(NoteItem.position, NoteItem.created_at)
        )
        grouped: dict[UUID, list[NoteItem]] = defaultdict(list)
        for item in child_result.scalars():
            grouped[item.note_id].append(item)
        return [self._note_read(note, grouped[note.id]) for note in parents]

    async def get(self, db: AsyncSession, auth: AuthSession, note_id: UUID) -> NoteRead | None:
        """Return one visible note, or None without disclosing why it is hidden."""
        note = await self._parent(db, auth, note_id)
        if note is None:
            return None
        return self._note_read(note, await self._items(db, note_id))

    async def create(self, db: AsyncSession, auth: AuthSession, payload: NoteCreate) -> NoteRead:
        """Create a note and its initial checklist atomically."""
        if payload.is_private and not can_see_private(auth):
            raise PrivateWriteLocked
        values = {
            "title": _sealed(payload.title) if payload.is_private else payload.title,
            "body_md": _sealed(payload.body_md) if payload.is_private else payload.body_md,
            "is_private": payload.is_private,
            "pinned": payload.pinned,
        }
        if payload.id is None:
            note = Note(**values)
            db.add(note)
            await db.flush()
        else:
            inserted_id = (
                await db.execute(
                    insert(Note)
                    .values(id=payload.id, **values)
                    .on_conflict_do_nothing(index_elements=[Note.id])
                    .returning(Note.id)
                )
            ).scalar_one_or_none()
            if inserted_id is None:
                existing = await self._parent(db, auth, payload.id)
                if existing is None:
                    physical = await db.execute(select(Note.id).where(Note.id == payload.id))
                    if physical.scalar_one_or_none() is not None:
                        raise NoteIdConflict
                    raise RuntimeError("conflicting note disappeared before it could be read")
                result = self._note_read(existing, await self._items(db, payload.id))
                result.created = False
                return result

            inserted = await db.execute(select(Note).where(Note.id == inserted_id))
            note = inserted.scalar_one()

        locked = await db.execute(select(Note).where(Note.id == note.id).with_for_update())
        note = locked.scalar_one()
        items = [
            NoteItem(
                note_id=note.id,
                content=_sealed(content) if note.is_private else content,
                position=position,
            )
            for position, content in enumerate(payload.items)
        ]
        db.add_all(items)
        await db.flush()
        result = self._note_read(note, items)
        result.created = True
        return result

    async def update(
        self,
        db: AsyncSession,
        auth: AuthSession,
        note_id: UUID,
        payload: NoteUpdate,
    ) -> NoteRead | None:
        """Patch a note, preserving the constraint-required toggle ordering."""
        changes = payload.model_dump(exclude_unset=True)
        wants_toggle = "is_private" in changes
        note = await self._parent(db, auth, note_id, for_update=wants_toggle)
        if note is None:
            return None
        items = await self._items(db, note_id)
        target_private = changes.get("is_private", note.is_private)
        if target_private and not can_see_private(auth):
            raise PrivateWriteLocked

        if wants_toggle and target_private != note.is_private:
            if target_private:
                if "title" in changes:
                    note.title = changes["title"]
                if "body_md" in changes:
                    note.body_md = changes["body_md"]
                note.title = _sealed(_clear(note.title))
                note.body_md = _sealed(_clear(note.body_md))
                for item in items:
                    item.content = _sealed(_clear(item.content))
                await db.flush()
                note.is_private = True
                await db.flush()
            else:
                note.is_private = False
                await db.flush()
                note.title = _clear(note.title)
                note.body_md = _clear(note.body_md)
                for item in items:
                    item.content = _clear(item.content)
                if "title" in changes:
                    note.title = changes["title"]
                if "body_md" in changes:
                    note.body_md = changes["body_md"]
        else:
            if "title" in changes:
                note.title = _sealed(changes["title"]) if note.is_private else changes["title"]
            if "body_md" in changes:
                body_md = changes["body_md"]
                note.body_md = _sealed(body_md) if note.is_private else body_md

        if "pinned" in changes:
            note.pinned = changes["pinned"]

        await db.flush()
        return self._note_read(note, items)

    async def soft_delete(self, db: AsyncSession, auth: AuthSession, note_id: UUID) -> bool:
        """Mark a visible note deleted; its children become unreachable through it."""
        note = await self._parent(db, auth, note_id)
        if note is None:
            return False
        note.deleted_at = datetime.now(UTC)
        await db.flush()
        return True

    async def restore(self, db: AsyncSession, auth: AuthSession, note_id: UUID) -> Note | None:
        """Restore a privacy-visible note without exposing why a row is hidden."""
        deleted_stmt = with_privacy_gate(select(Note).where(Note.id == note_id), Note, auth).where(
            Note.deleted_at.is_not(None)
        )
        deleted_result = await db.execute(deleted_stmt)
        note = deleted_result.scalar_one_or_none()

        if note is None:
            note = await self._parent(db, auth, note_id)
            if note is None:
                return None
        else:
            note.deleted_at = None
            await db.flush()

        return note

    async def list_items(
        self, db: AsyncSession, auth: AuthSession, note_id: UUID
    ) -> list[NoteItemRead] | None:
        """List children only after resolving their visible parent."""
        parent = await self._parent(db, auth, note_id)
        if parent is None:
            return None
        return [self._item_read(item) for item in await self._items(db, note_id)]

    async def add_item(
        self,
        db: AsyncSession,
        auth: AuthSession,
        note_id: UUID,
        payload: NoteItemCreate,
    ) -> NoteItemRead | None:
        """Append an item after locking and resolving its visible parent."""
        parent = await self._parent(db, auth, note_id, for_update=True)
        if parent is None:
            return None
        item = NoteItem(
            note_id=parent.id,
            content=_sealed(payload.content) if parent.is_private else payload.content,
            position=payload.position,
        )
        db.add(item)
        await db.flush()
        return self._item_read(item)

    async def update_item(
        self,
        db: AsyncSession,
        auth: AuthSession,
        note_id: UUID,
        item_id: UUID,
        payload: NoteItemUpdate,
    ) -> NoteItemRead | None:
        """Patch an item without ever allowing it to move between parents."""
        changes = payload.model_dump(exclude_unset=True)
        if "note_id" in changes:
            raise ValueError("note_item.note_id is immutable")

        parent = await self._parent(db, auth, note_id, for_update=True)
        if parent is None:
            return None
        result = await db.execute(
            select(NoteItem).where(NoteItem.id == item_id, NoteItem.note_id == parent.id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None

        if "content" in changes:
            content = changes["content"]
            item.content = _sealed(content) if parent.is_private else content
        for field in ("is_completed", "position"):
            if field in changes:
                setattr(item, field, changes[field])
        await db.flush()
        return self._item_read(item)

    async def delete_item(
        self,
        db: AsyncSession,
        auth: AuthSession,
        note_id: UUID,
        item_id: UUID,
    ) -> bool:
        """Hard-delete one checklist item after locking its visible parent."""
        parent = await self._parent(db, auth, note_id, for_update=True)
        if parent is None:
            return False
        result = await db.execute(
            select(NoteItem.id).where(NoteItem.id == item_id, NoteItem.note_id == parent.id)
        )
        if result.scalar_one_or_none() is None:
            return False
        await db.execute(delete(NoteItem).where(NoteItem.id == item_id))
        return True
