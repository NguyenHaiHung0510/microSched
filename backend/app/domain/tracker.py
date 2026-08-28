"""Tracker-group / tracker / entry DTOs and the request-scoped Postgres store.

Mirrors the structure of ``notes.py`` (DTO → exception → stateless store), but with
four structural differences that the 011a spec (§2) pins down:

* ``tracker.name`` / ``entry.amount`` / ``entry.list_amount`` / ``entry.note_md`` are
  ALWAYS ciphertext — there is no "only when private" branch (models.py CHECK
  constraints are unconditional ``LIKE 'enc:v1:%'``). Flipping ``is_private`` never
  re-encrypts anything; it only controls the read gate.
* ``entry`` is read through its parent: ``readable(...)`` is applied to the joined
  ``Tracker``, never to ``Entry`` itself (whose gate is ``VIA_PARENT``).
* Money is a ``TEXT`` ciphertext column, so every validate and every sum runs in
  Python against the decrypted ``Decimal`` — never ``func.sum`` / ``ORDER BY`` in SQL.
* There is no unique index on the encrypted ``tracker.name`` (K19), so duplicate-name
  checking is a decrypt-scan done INSIDE the privacy gate.
"""

import logging
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain import money
from app.domain.models import AuthSession, Entry, Subscription, Tracker, TrackerGroup
from app.domain.reading import can_see_private, not_deleted, readable, with_privacy_gate
from app.web.deps import CRON_TIMER_RELOAD_INFO_KEY

logger = logging.getLogger(__name__)

Kind = Literal["health", "finance", "general"]
Direction = Literal["in", "out"]
InputMode = Literal["event", "money", "quantity"]
ReminderMode = Literal["fixed", "after_entry"]
ReminderAction = Literal["confirm_event", "open_tracker"]
NonEmptyText = Annotated[str, Field(min_length=1)]


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Không được để trống tên.")
    return value


def _is_legacy_reminder(
    *,
    kind: str,
    input_mode: str,
    reminder_time: time | None,
    reminder_mode: str | None,
    reminder_interval_days: int | None,
    reminder_action: str | None,
) -> bool:
    """Return whether a pre-031 medication row has the permitted legacy shape."""
    return (
        kind == "health"
        and input_mode == "event"
        and reminder_time is not None
        and reminder_mode is None
        and reminder_interval_days is None
        and reminder_action is None
    )


def _canonical_reminder(
    *,
    kind: str,
    input_mode: str,
    reminder_time: time | None,
    reminder_text: str | None,
    reminder_mode: str | None,
    reminder_interval_days: int | None,
    reminder_action: str | None,
    allow_legacy: bool,
    interval_was_omitted: bool,
) -> tuple[str | None, int | None, str | None, time | None, str | None]:
    """Normalize one reminder bundle or raise the API-safe invariant error.

    Database checks deliberately leave the rolling old-writer window open. This
    function is therefore the single canonicalizer for every new writer.
    """
    if (
        reminder_mode is None
        and reminder_interval_days is None
        and reminder_action is None
        and reminder_time is None
    ):
        if reminder_text is not None:
            raise TrackerInvalid("Tắt nhắc nhở phải xoá cả nội dung nhắc.")
        return None, None, None, None, None

    if (
        _is_legacy_reminder(
            kind=kind,
            input_mode=input_mode,
            reminder_time=reminder_time,
            reminder_mode=reminder_mode,
            reminder_interval_days=reminder_interval_days,
            reminder_action=reminder_action,
        )
        and allow_legacy
    ):
        return "fixed", 1, "confirm_event", reminder_time, reminder_text

    if reminder_interval_days is None and interval_was_omitted:
        reminder_interval_days = 1
    if (
        reminder_mode is None
        or reminder_interval_days is None
        or reminder_action is None
        or reminder_time is None
    ):
        raise TrackerInvalid("Nhắc nhở bật cần đủ mode, interval, action và time.")
    if reminder_interval_days <= 0:
        raise TrackerInvalid("Khoảng ngày nhắc phải lớn hơn 0.")
    if reminder_action == "confirm_event" and input_mode != "event":
        raise TrackerInvalid("confirm_event chỉ hợp lệ với tracker kiểu event.")
    return reminder_mode, reminder_interval_days, reminder_action, reminder_time, reminder_text


class GroupCreate(BaseModel):
    """Fields accepted when creating a tracker group."""

    id: UUID | None = None
    name: str
    kind: Kind
    color: str | None = None
    position: int = 0

    @model_validator(mode="after")
    def normalize(self) -> "GroupCreate":
        self.name = _clean_name(self.name)
        if self.color is not None:
            self.color = self.color.strip() or None
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        return self


class GroupUpdate(BaseModel):
    """Patch semantics for a tracker group; ``kind`` is intentionally absent.

    Changing a group's kind that already has trackers would violate the composite FK
    ``(group_id, kind) -> tracker_group(id, kind)`` for many rows at once. To change
    kind, create a new group and move trackers explicitly (spec §4.2 trap 4).
    """

    name: str | None = None
    color: str | None = None
    position: int | None = None

    @model_validator(mode="after")
    def normalize(self) -> "GroupUpdate":
        for field in ("name", "color"):
            if field in self.model_fields_set and getattr(self, field) is not None:
                value = getattr(self, field).strip()
                if field == "name" and not value:
                    raise ValueError("Không được để trống tên.")
                setattr(self, field, value or None)
        return self


class GroupRead(BaseModel):
    """Group returned at the API boundary, with a live ``tracker_count``."""

    id: UUID
    name: str
    kind: Kind
    color: str | None
    position: int
    tracker_count: int
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)


class TrackerCreate(BaseModel):
    """Fields accepted when creating a tracker."""

    id: UUID | None = None
    name: str
    kind: Kind
    direction: Direction = "out"
    input_mode: InputMode = "event"
    group_id: UUID | None = None
    unit: str | None = None
    color: str | None = None
    reminder_time: time | None = None
    reminder_text: str | None = Field(default=None, max_length=240)
    reminder_mode: ReminderMode | None = None
    reminder_interval_days: int | None = None
    reminder_action: ReminderAction | None = None
    is_private: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "TrackerCreate":
        self.name = _clean_name(self.name)
        if self.color is not None:
            self.color = self.color.strip() or None
        if self.unit is not None:
            self.unit = self.unit.strip() or None
        if self.reminder_text is not None:
            self.reminder_text = self.reminder_text.strip() or None
        try:
            (
                self.reminder_mode,
                self.reminder_interval_days,
                self.reminder_action,
                self.reminder_time,
                self.reminder_text,
            ) = _canonical_reminder(
                kind=self.kind,
                input_mode=self.input_mode,
                reminder_time=self.reminder_time,
                reminder_text=self.reminder_text,
                reminder_mode=self.reminder_mode,
                reminder_interval_days=self.reminder_interval_days,
                reminder_action=self.reminder_action,
                allow_legacy=not any(
                    field in self.model_fields_set
                    for field in (
                        "reminder_mode",
                        "reminder_interval_days",
                        "reminder_action",
                    )
                ),
                interval_was_omitted="reminder_interval_days" not in self.model_fields_set,
            )
        except TrackerInvalid as error:
            raise ValueError(str(error)) from error
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        return self


class TrackerUpdate(BaseModel):
    """Patch semantics for a tracker."""

    name: str | None = None
    kind: Kind | None = None
    direction: Direction | None = None
    input_mode: InputMode | None = None
    group_id: UUID | None = None
    unit: str | None = None
    color: str | None = None
    reminder_time: time | None = None
    reminder_text: str | None = Field(default=None, max_length=240)
    reminder_mode: ReminderMode | None = None
    reminder_interval_days: int | None = None
    reminder_action: ReminderAction | None = None
    is_private: bool | None = None

    @model_validator(mode="after")
    def normalize(self) -> "TrackerUpdate":
        if "name" in self.model_fields_set and self.name is not None:
            self.name = _clean_name(self.name)
        if "color" in self.model_fields_set and self.color is not None:
            self.color = self.color.strip() or None
        if "unit" in self.model_fields_set and self.unit is not None:
            self.unit = self.unit.strip() or None
        if "reminder_text" in self.model_fields_set and self.reminder_text is not None:
            self.reminder_text = self.reminder_text.strip() or None
        # Explicit null on a non-nullable patch field must 422 (M5), not silently
        # fall back to "not in payload" semantics; only group_id/unit/color may be
        # explicitly nulled (that is how the UI clears them).
        for field in ("name", "kind", "direction", "input_mode", "is_private"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TrackerRead(BaseModel):
    """Decrypted tracker returned at the API boundary, with capture-grid metadata."""

    id: UUID
    name: str
    kind: Kind
    direction: Direction
    input_mode: InputMode
    group_id: UUID | None
    unit: str | None
    color: str | None
    reminder_time: time | None
    reminder_text: str | None
    reminder_mode: ReminderMode | None
    reminder_interval_days: int | None
    reminder_action: ReminderAction | None
    is_private: bool
    last_entry_at: datetime | None
    entry_count_30d: int
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)


class EntryCreate(BaseModel):
    """Fields accepted when logging an entry (one-tap capture)."""

    id: UUID | None = None
    tracker_id: UUID
    occurred_at: datetime | None = None
    quantity: Decimal | None = None
    amount: Decimal | None = None
    list_amount: Decimal | None = None
    note_md: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "EntryCreate":
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        if self.occurred_at is not None and (
            self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None
        ):
            raise ValueError("occurred_at must include a timezone offset")
        if self.note_md is not None:
            self.note_md = self.note_md.strip() or None
        return self


class EntryUpdate(BaseModel):
    """Patch semantics for an entry; ``tracker_id`` is intentionally absent (no reparent)."""

    occurred_at: datetime | None = None
    quantity: Decimal | None = None
    amount: Decimal | None = None
    list_amount: Decimal | None = None
    note_md: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "EntryUpdate":
        if "occurred_at" in self.model_fields_set and self.occurred_at is None:
            # The physical column is NOT NULL (models.py): an explicit null must
            # be a 422, not a silent no-op or a deferred IntegrityError (M5).
            raise ValueError("occurred_at cannot be null")
        if (
            "occurred_at" in self.model_fields_set
            and self.occurred_at is not None
            and (self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None)
        ):
            raise ValueError("occurred_at must include a timezone offset")
        if "note_md" in self.model_fields_set and self.note_md is not None:
            self.note_md = self.note_md.strip() or None
        return self


class EntryRead(BaseModel):
    """Decrypted entry returned at the API boundary; money is a number, not a string."""

    id: UUID
    tracker_id: UUID
    occurred_at: datetime | None
    quantity: Decimal | None
    amount: Decimal | None
    list_amount: Decimal | None
    note_md: str | None
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)

    @field_serializer("amount", "list_amount")
    def _money_as_number(self, value: Decimal | None) -> int | None:
        """Serialize integral VND as a JSON number, not a string."""
        if value is None:
            return None
        return int(value)


class GroupNameTaken(Exception):
    """A tracker_group with the same (unencrypted) name already exists."""


class TrackerNameTaken(Exception):
    """A visible tracker with the same decrypted name already exists (inside the gate)."""


class TrackerIdConflict(Exception):
    """A client-selected ID belongs to a tracker row hidden by a reading gate."""


class EntryIdConflict(Exception):
    """A client-selected entry ID belongs to a DIFFERENT record (other tracker or
    subscription) or to a row hidden by a reading gate.

    Spec 011c §2.4: a real conflict must surface as 409 — never be coerced into
    an idempotent ``created=False`` retry, which would silently swallow a
    foreign writer's row.
    """


class PrivateWriteLocked(Exception):
    """A write tried to create private data while the display gate was closed."""


class EntryInvalid(Exception):
    """A write violates the K8 input_mode contract or a store invariant (→ 422)."""


class TrackerInvalid(Exception):
    """A tracker patch violates a store invariant (unit/input_mode/kind/group → 422)."""


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


def _amount_out(value: Decimal | None) -> str | None:
    """Seal an API-bound Decimal amount as ciphertext via the storage contract."""
    if value is None:
        return None
    return _sealed(money.to_storage(value))


def _amount_in(raw: str | None) -> Decimal | None:
    """Clear and parse a stored ciphertext amount back to a Decimal."""
    if raw is None:
        return None
    return money.from_storage(_clear(raw))


def _kind_label(value: str) -> str:
    return {"health": "sức khoẻ", "finance": "tài chính", "general": "chung"}[value]


class TrackerStore:
    """Stateless tracker persistence; every method joins its request transaction."""

    # ------------------------------------------------------------------ helpers

    async def _tracker(
        self,
        db: AsyncSession,
        auth: AuthSession,
        tracker_id: UUID,
        *,
        for_update: bool = False,
    ) -> Tracker | None:
        stmt = readable(select(Tracker).where(Tracker.id == tracker_id), Tracker, auth)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _entry(
        self,
        db: AsyncSession,
        auth: AuthSession,
        entry_id: UUID,
        *,
        for_update: bool = False,
    ) -> Entry | None:
        """Read one entry through its visible parent tracker."""
        stmt = (
            select(Entry).join(Tracker, Entry.tracker_id == Tracker.id).where(Entry.id == entry_id)
        )
        stmt = readable(stmt, Tracker, auth)  # privacy + soft-delete of the PARENT
        stmt = not_deleted(stmt, Entry)  # soft-delete of the entry itself
        if for_update:
            # Callers acquire Tracker before Entry.  Lock only the child here
            # so PostgreSQL does not silently lock the joined parent first.
            stmt = stmt.with_for_update(of=Entry)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _entry_read(self, entry: Entry) -> EntryRead:
        return EntryRead(
            id=entry.id,
            tracker_id=entry.tracker_id,
            occurred_at=entry.occurred_at,
            quantity=entry.quantity,
            amount=_amount_in(entry.amount),
            list_amount=_amount_in(entry.list_amount),
            note_md=_clear(entry.note_md),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    async def _read_tracker(
        self, db: AsyncSession, auth: AuthSession, tracker: Tracker
    ) -> TrackerRead:
        """Build a TrackerRead, folding in last-entry and 30-day-count in one pass."""
        last, count = await self._last_entry_and_count(db, [tracker.id])
        return self._tracker_read_from(tracker, last, count)

    def _tracker_read_from(
        self,
        tracker: Tracker,
        last: dict[UUID, datetime],
        count: dict[UUID, int],
    ) -> TrackerRead:
        """Build a TrackerRead from precomputed batched metadata."""
        mode, interval, action, _time, _text = _canonical_reminder(
            kind=tracker.kind,
            input_mode=tracker.input_mode,
            reminder_time=tracker.reminder_time,
            reminder_text=tracker.reminder_text,
            reminder_mode=tracker.reminder_mode,
            reminder_interval_days=tracker.reminder_interval_days,
            reminder_action=tracker.reminder_action,
            allow_legacy=True,
            interval_was_omitted=False,
        )
        return TrackerRead(
            id=tracker.id,
            name=_clear(tracker.name),
            kind=tracker.kind,
            direction=tracker.direction,
            input_mode=tracker.input_mode,
            group_id=tracker.group_id,
            unit=tracker.unit,
            color=tracker.color,
            reminder_time=tracker.reminder_time,
            reminder_text=tracker.reminder_text,
            reminder_mode=mode,
            reminder_interval_days=interval,
            reminder_action=action,
            is_private=tracker.is_private,
            last_entry_at=last.get(tracker.id),
            entry_count_30d=count.get(tracker.id, 0),
            created_at=tracker.created_at,
            updated_at=tracker.updated_at,
        )

    async def _read_trackers(self, db: AsyncSession, trackers: list[Tracker]) -> list[TrackerRead]:
        """Batch-build TrackerRead rows with ONE last-entry/count pass (M1)."""
        ids = [tracker.id for tracker in trackers]
        last, count = await self._last_entry_and_count(db, ids)
        return [self._tracker_read_from(tracker, last, count) for tracker in trackers]

    async def _last_entry_and_count(
        self, db: AsyncSession, tracker_ids: list[UUID]
    ) -> tuple[dict[UUID, datetime], dict[UUID, int]]:
        """Return ``{tracker_id: last occurred_at}`` and ``{tracker_id: count_30d}``.

        Two batched queries (no N+1): ``DISTINCT ON`` for each tracker's latest
        non-deleted entry, and a ``GROUP BY`` for the 30-day count. Both deliberately
        exclude soft-deleted entries so an undo immediately updates "lần cuối" and the
        grid order.
        """
        if not tracker_ids:
            return {}, {}
        now = datetime.now(UTC)
        last: dict[UUID, datetime] = {}
        last_result = await db.execute(
            select(
                Entry.tracker_id,
                Entry.occurred_at,
            )
            .where(
                Entry.tracker_id.in_(tracker_ids),
                Entry.deleted_at.is_(None),
                Entry.occurred_at.is_not(None),
            )
            .distinct(Entry.tracker_id)
            .order_by(Entry.tracker_id, Entry.occurred_at.desc())
        )
        for tracker_id, occurred_at in last_result:
            last[tracker_id] = occurred_at

        count: dict[UUID, int] = {}
        count_result = await db.execute(
            select(Entry.tracker_id, func.count(Entry.id))
            .where(
                Entry.tracker_id.in_(tracker_ids),
                Entry.deleted_at.is_(None),
                Entry.occurred_at >= now - timedelta(days=30),
            )
            .group_by(Entry.tracker_id)
        )
        for tracker_id, value in count_result:
            count[tracker_id] = value
        return last, count

    async def _group_kind(self, db: AsyncSession, group_id: UUID | None) -> str | None:
        if group_id is None:
            return None
        result = await db.execute(select(TrackerGroup.kind).where(TrackerGroup.id == group_id))
        return result.scalar_one_or_none()

    async def _tracker_name_taken(
        self, db: AsyncSession, auth: AuthSession, name: str, *, exclude_id: UUID | None = None
    ) -> bool:
        """Whether a visible tracker already has this decrypted name (scan INSIDE the gate)."""
        stmt = readable(select(Tracker), Tracker, auth)
        result = await db.execute(stmt)
        wanted = name.casefold()
        for tracker in result.scalars():
            if exclude_id is not None and tracker.id == exclude_id:
                continue
            try:
                stored_name = _clear(tracker.name)
            except Exception:
                # An unreadable tracker row (wrong key, corruption) cannot be compared
                # by name, so it must never block creating or renaming other trackers
                # — logging keeps the failure loud without a global 500 on a bad row.
                logger.warning(
                    "Skipped an unreadable tracker name in duplicate scan (id=%s)", tracker.id
                )
                continue
            if stored_name is not None and stored_name.casefold() == wanted:
                return True
        return False

    # ------------------------------------------------------------------ groups

    async def list_groups(self, db: AsyncSession, auth: AuthSession) -> list[GroupRead]:
        """List every tracker group with a live, privacy-aware tracker count."""
        result = await db.execute(
            select(TrackerGroup).order_by(TrackerGroup.position, TrackerGroup.created_at)
        )
        groups = list(result.scalars())
        counts = await self._group_counts(db, auth)
        return [self._group_read(group, counts) for group in groups]

    def _group_read(self, group: TrackerGroup, counts: dict[UUID, int] | None = None) -> GroupRead:
        counts = counts or {}
        return GroupRead(
            id=group.id,
            name=group.name,
            kind=group.kind,
            color=group.color,
            position=group.position,
            tracker_count=counts.get(group.id, 0),
            created_at=group.created_at,
            updated_at=group.updated_at,
        )

    async def _group_counts(self, db: AsyncSession, auth: AuthSession) -> dict[UUID, int]:
        """Count non-archived trackers per group, filtered by the session's gate.

        ``tracker_count`` feeds the UI's delete confirmation and group rows;
        counting private trackers while the gate is closed would leak their
        existence (C2), so the count goes through the same privacy + soft-delete
        gate as ``list_trackers``.
        """
        stmt = select(Tracker.group_id, func.count(Tracker.id)).where(Tracker.group_id.is_not(None))
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Tracker)
        stmt = stmt.group_by(Tracker.group_id)
        result = await db.execute(stmt)
        return {group_id: value for group_id, value in result}

    async def create_group(self, db: AsyncSession, payload: GroupCreate) -> GroupRead:
        """Create a group, or idempotently return the existing explicit ID."""
        if payload.id is not None:
            existing = await db.execute(select(TrackerGroup).where(TrackerGroup.id == payload.id))
            group = existing.scalar_one_or_none()
            if group is not None:
                result = self._group_read(group)
                result.created = False
                return result
        group = TrackerGroup(**payload.model_dump())
        db.add(group)
        await db.flush()
        result = self._group_read(group)
        result.created = True
        return result

    async def update_group(
        self, db: AsyncSession, auth: AuthSession, group_id: UUID, payload: GroupUpdate
    ) -> GroupRead | None:
        """Patch a group; the router turns a unique-name violation into a 409."""
        result = await db.execute(
            select(TrackerGroup).where(TrackerGroup.id == group_id).with_for_update()
        )
        group = result.scalar_one_or_none()
        if group is None:
            return None
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(group, field, value)
        await db.flush()
        count = (await self._group_counts(db, auth)).get(group.id, 0)
        return self._group_read(group, {group.id: count})

    async def delete_group(self, db: AsyncSession, group_id: UUID) -> bool:
        """Hard-delete a group; the FK sets member trackers' ``group_id`` to NULL."""
        result = await db.execute(
            select(TrackerGroup.id).where(TrackerGroup.id == group_id).with_for_update()
        )
        if result.scalar_one_or_none() is None:
            return False
        await db.execute(delete(TrackerGroup).where(TrackerGroup.id == group_id))
        return True

    # ------------------------------------------------------------------ trackers

    async def list_trackers(self, db: AsyncSession, auth: AuthSession) -> list[TrackerRead]:
        """List visible, non-deleted trackers with capture metadata."""
        stmt = readable(select(Tracker), Tracker, auth)
        result = await db.execute(stmt)
        trackers = list(result.scalars())
        if not trackers:
            return []
        return await self._read_trackers(db, trackers)

    async def get_tracker(
        self, db: AsyncSession, auth: AuthSession, tracker_id: UUID
    ) -> TrackerRead | None:
        tracker = await self._tracker(db, auth, tracker_id)
        if tracker is None:
            return None
        return await self._read_tracker(db, auth, tracker)

    async def create_tracker(
        self, db: AsyncSession, auth: AuthSession, payload: TrackerCreate
    ) -> TrackerRead:
        """Create a tracker (unconditionally encrypted name), or idempotent on ID."""
        if payload.is_private and not can_see_private(auth):
            raise PrivateWriteLocked
        if payload.group_id is not None:
            group_kind = await self._group_kind(db, payload.group_id)
            if group_kind is None:
                raise TrackerInvalid("Nhóm tracker không tồn tại.")
            if group_kind != payload.kind:
                raise TrackerInvalid(
                    f"Không thể đưa tracker vào nhóm thuộc loại '{_kind_label(group_kind)}' — "
                    f"chọn nhóm '{_kind_label(payload.kind)}' cho tracker này."
                )
        if payload.input_mode != "quantity" and payload.unit is not None:
            raise TrackerInvalid("unit chỉ được dùng cho tracker kiểu 'quantity'.")
        if payload.input_mode == "quantity" and not payload.unit:
            raise TrackerInvalid("Tracker kiểu 'quantity' phải có đơn vị (unit).")
        if await self._tracker_name_taken(db, auth, payload.name):
            raise TrackerNameTaken
        values = {
            "name": _sealed(payload.name),
            "kind": payload.kind,
            "direction": payload.direction,
            "input_mode": payload.input_mode,
            "group_id": payload.group_id,
            "unit": payload.unit,
            "color": payload.color,
            # reminder_text is deliberately plaintext: it is the owner-chosen
            # public lock-screen surface, not private tracker content.
            "reminder_time": payload.reminder_time,
            "reminder_text": payload.reminder_text,
            "reminder_mode": payload.reminder_mode,
            "reminder_interval_days": payload.reminder_interval_days,
            "reminder_action": payload.reminder_action,
            "is_private": payload.is_private,
        }
        if payload.id is None:
            tracker = Tracker(**values)
            db.add(tracker)
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "tracker:create"
            await db.flush()
        else:
            inserted_id = (
                await db.execute(
                    insert(Tracker)
                    .values(id=payload.id, **values)
                    .on_conflict_do_nothing(index_elements=[Tracker.id])
                    .returning(Tracker.id)
                )
            ).scalar_one_or_none()
            if inserted_id is None:
                existing = await self._tracker(db, auth, payload.id)
                if existing is None:
                    physical = await db.execute(select(Tracker.id).where(Tracker.id == payload.id))
                    if physical.scalar_one_or_none() is not None:
                        raise TrackerIdConflict
                    raise RuntimeError("conflicting tracker disappeared before it could be read")
                result = await self._read_tracker(db, auth, existing)
                result.created = False
                return result
            inserted = await db.execute(select(Tracker).where(Tracker.id == inserted_id))
            tracker = inserted.scalar_one()
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "tracker:create"
        result = await self._read_tracker(db, auth, tracker)
        result.created = True
        return result

    async def update_tracker(
        self, db: AsyncSession, auth: AuthSession, tracker_id: UUID, payload: TrackerUpdate
    ) -> TrackerRead | None:
        """Patch a tracker, enforcing unit/input_mode and kind/group invariants."""
        changes = payload.model_dump(exclude_unset=True)
        wants_private = "is_private" in changes and changes["is_private"]
        tracker = await self._tracker(db, auth, tracker_id, for_update=True)
        if tracker is None:
            return None
        if wants_private and not can_see_private(auth):
            raise PrivateWriteLocked

        # 011c §2.5: a tracker with live subscriptions cannot be switched away
        # from finance+money, or every renewal would start failing K8 right at
        # the worst moment. Only the effective change is guarded: patching
        # name/color with an identical input_mode/kind stays allowed.
        leaves_money = ("input_mode" in changes and changes["input_mode"] != "money") or (
            "kind" in changes and changes["kind"] != "finance"
        )
        if leaves_money:
            sub_count = (
                await db.execute(
                    select(func.count(Subscription.id)).where(
                        Subscription.tracker_id == tracker_id,
                        Subscription.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
            if sub_count:
                raise TrackerInvalid(
                    f"Tracker còn {sub_count} đăng ký đang gắn — "
                    "không đổi được loại hay kiểu nhập của tracker này."
                )

        new_kind = changes.get("kind", tracker.kind)
        # Validate the effective (group_id, kind) pair even when the PATCH only moves
        # group_id without touching kind: the composite FK fk_tracker_group_kind would
        # otherwise turn a wrong-kind assignment into a raw IntegrityError instead of
        # the intended 422. Reading the tracker's CURRENT group when group_id is unset
        # means a bare {"kind": ...} still cannot silently pass a stale group through.
        effective_group = changes.get("group_id", tracker.group_id)
        if effective_group is not None:
            group_kind = await self._group_kind(db, effective_group)
            if group_kind is None:
                raise TrackerInvalid("Nhóm tracker không tồn tại.")
            if group_kind != new_kind:
                raise TrackerInvalid(
                    f"Nhóm hiện tại thuộc loại '{_kind_label(group_kind)}' — "
                    f"bỏ nhóm hoặc chọn nhóm '{_kind_label(new_kind)}' trong cùng lần sửa."
                )

        new_input_mode = changes.get("input_mode", tracker.input_mode)
        new_unit = changes.get("unit", tracker.unit)
        if new_input_mode != "quantity":
            if changes.get("unit") is not None:
                raise TrackerInvalid("unit chỉ được dùng cho tracker kiểu 'quantity'.")
            # Changing AWAY from quantity: clear the unit in the same UPDATE so the
            # unit_matches_input_mode CHECK does not fire.
            changes["unit"] = None
        else:
            if new_unit is None:
                raise TrackerInvalid("Tracker kiểu 'quantity' phải có đơn vị (unit).")

        reminder_fields = (
            "reminder_mode",
            "reminder_interval_days",
            "reminder_action",
            "reminder_time",
            "reminder_text",
        )
        if any(field in changes for field in reminder_fields) or "input_mode" in changes:
            old_mode, old_interval, old_action, old_time, old_text = _canonical_reminder(
                kind=tracker.kind,
                input_mode=tracker.input_mode,
                reminder_time=tracker.reminder_time,
                reminder_text=tracker.reminder_text,
                reminder_mode=tracker.reminder_mode,
                reminder_interval_days=tracker.reminder_interval_days,
                reminder_action=tracker.reminder_action,
                allow_legacy=True,
                interval_was_omitted=False,
            )
            new_mode = changes.get("reminder_mode", old_mode)
            new_interval = changes.get("reminder_interval_days", old_interval)
            new_action = changes.get("reminder_action", old_action)
            new_time = changes.get("reminder_time", old_time)
            new_text = changes.get("reminder_text", old_text)
            # A time-only explicit null is the backwards-compatible UI disable
            # shape. Clear every hidden field rather than retaining stale action.
            if (
                "reminder_time" in changes
                and changes["reminder_time"] is None
                and not any(
                    field in changes
                    for field in ("reminder_mode", "reminder_interval_days", "reminder_action")
                )
            ):
                new_mode = new_interval = new_action = new_time = new_text = None
            (
                changes["reminder_mode"],
                changes["reminder_interval_days"],
                changes["reminder_action"],
                changes["reminder_time"],
                changes["reminder_text"],
            ) = _canonical_reminder(
                kind=new_kind,
                input_mode=new_input_mode,
                reminder_time=new_time,
                reminder_text=new_text,
                reminder_mode=new_mode,
                reminder_interval_days=new_interval,
                reminder_action=new_action,
                allow_legacy=False,
                interval_was_omitted="reminder_interval_days" not in changes,
            )

        if "name" in changes:
            if await self._tracker_name_taken(db, auth, changes["name"], exclude_id=tracker.id):
                raise TrackerNameTaken
            changes["name"] = _sealed(changes["name"])

        for field in (
            "kind",
            "direction",
            "input_mode",
            "group_id",
            "unit",
            "color",
            "is_private",
            "reminder_time",
            "reminder_text",
            "reminder_mode",
            "reminder_interval_days",
            "reminder_action",
        ):
            if field in changes:
                setattr(tracker, field, changes[field])
        if any(field in changes for field in reminder_fields):
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "tracker:reminder"
        await db.flush()
        return await self._read_tracker(db, auth, tracker)

    async def soft_delete_tracker(
        self, db: AsyncSession, auth: AuthSession, tracker_id: UUID
    ) -> bool:
        """Archive a tracker (soft-delete); its history is preserved for F1–F5."""
        tracker = await self._tracker(db, auth, tracker_id)
        if tracker is None:
            return False
        sub_count = (
            await db.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.tracker_id == tracker_id,
                    Subscription.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        if sub_count:
            raise TrackerInvalid(f"Còn {sub_count} đăng ký đang gắn — xoá hoặc chuyển chúng trước.")
        tracker.deleted_at = datetime.now(UTC)
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "tracker:soft_delete"
        await db.flush()
        return True

    async def restore_tracker(
        self, db: AsyncSession, auth: AuthSession, tracker_id: UUID
    ) -> Tracker | None:
        """Restore an archived tracker without disclosing why a row is hidden."""
        deleted_stmt = with_privacy_gate(
            select(Tracker).where(Tracker.id == tracker_id), Tracker, auth
        ).where(Tracker.deleted_at.is_not(None))
        tracker = (await db.execute(deleted_stmt)).scalar_one_or_none()
        if tracker is None:
            return await self._tracker(db, auth, tracker_id)
        tracker.deleted_at = None
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "tracker:restore"
        await db.flush()
        return tracker

    # ------------------------------------------------------------------ entries

    async def list_entries(
        self,
        db: AsyncSession,
        auth: AuthSession,
        *,
        tracker_id: UUID | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EntryRead]:
        """List entries (paginated) through their visible parent trackers."""
        stmt = select(Entry).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = readable(stmt, Tracker, auth)  # privacy + soft-delete of the PARENT
        stmt = not_deleted(stmt, Entry)  # soft-delete of the entry itself
        if tracker_id is not None:
            stmt = stmt.where(Entry.tracker_id == tracker_id)
        if from_ is not None:
            stmt = stmt.where(Entry.occurred_at >= from_)
        if to is not None:
            stmt = stmt.where(Entry.occurred_at < to)
        stmt = stmt.order_by(Entry.occurred_at.desc(), Entry.id).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return [self._entry_read(entry) for entry in result.scalars()]

    async def get_entry(
        self, db: AsyncSession, auth: AuthSession, entry_id: UUID
    ) -> EntryRead | None:
        """Read one entry through its visible parent."""
        entry = await self._entry(db, auth, entry_id)
        if entry is None:
            return None
        return self._entry_read(entry)

    async def _validate_entry(
        self,
        *,
        input_mode: str,
        quantity: Decimal | None,
        amount: Decimal | None,
        list_amount: Decimal | None,
    ) -> None:
        """Enforce K8: the entry's columns must match the tracker's input_mode (write-time only).

        The rule applies only when logging. Changing a tracker's input_mode later
        neither invalidates nor hides old entries — history is history.
        """
        if input_mode == "event":
            if amount is not None or quantity is not None:
                raise EntryInvalid("Tracker kiểu 'event' không nhận tiền hay số lượng.")
            if list_amount is not None:
                raise EntryInvalid("list_amount chỉ hợp lệ khi có amount.")
        elif input_mode == "money":
            if amount is None:
                raise EntryInvalid("Tracker kiểu 'money' bắt buộc có số tiền.")
            if quantity is not None:
                raise EntryInvalid("Tracker kiểu 'money' không nhận số lượng.")
            if list_amount is not None and list_amount < 0:
                raise EntryInvalid("Số tiền không được âm.")
        elif input_mode == "quantity":
            if quantity is None:
                raise EntryInvalid("Tracker kiểu 'quantity' bắt buộc có số lượng.")
            if quantity <= 0:
                raise EntryInvalid("Số lượng phải lớn hơn 0.")
            if amount is not None or list_amount is not None:
                raise EntryInvalid("Tracker kiểu 'quantity' không nhận số tiền.")

    async def create_entry(
        self,
        db: AsyncSession,
        auth: AuthSession,
        payload: EntryCreate,
        *,
        subscription_id: UUID | None = None,
    ) -> tuple[UUID, bool]:
        """Log one entry (one-tap capture) through its visible parent tracker.

        Returns ``(entry_id, created)`` — the 011c renewal flow needs to know
        whether the INSERT actually landed so it can push ``expires_on`` only
        once (§2.4). ``subscription_id`` is an internal keyword used ONLY by
        ``SubscriptionStore.renew``; the 011a router never sets it.
        """
        tracker = await self._tracker(db, auth, payload.tracker_id, for_update=True)
        if tracker is None:
            raise EntryInvalid("Tracker không tồn tại.")
        await self._validate_entry(
            input_mode=tracker.input_mode,
            quantity=payload.quantity,
            amount=payload.amount,
            list_amount=payload.list_amount,
        )
        values = {
            "tracker_id": payload.tracker_id,
            "subscription_id": subscription_id,
            "occurred_at": payload.occurred_at or datetime.now(UTC),
            "quantity": payload.quantity,
            "amount": _amount_out(payload.amount),
            "list_amount": _amount_out(payload.list_amount),
            "note_md": _sealed(payload.note_md),
        }
        if payload.id is None:
            entry = Entry(**values)
            db.add(entry)
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "entry:create"
            await db.flush()
            return entry.id, True

        inserted_id = (
            await db.execute(
                insert(Entry)
                .values(id=payload.id, **values)
                .on_conflict_do_nothing(index_elements=[Entry.id])
                .returning(Entry.id)
            )
        ).scalar_one_or_none()
        if inserted_id is None:
            existing = await self._entry(db, auth, payload.id)
            if existing is None:
                physical = await db.execute(select(Entry.id).where(Entry.id == payload.id))
                if physical.scalar_one_or_none() is not None:
                    raise EntryIdConflict
                raise RuntimeError("conflicting entry disappeared before it could be read")
            if (
                existing.tracker_id != payload.tracker_id
                or existing.subscription_id != subscription_id
            ):
                # The same client id already belongs to a different row: this is
                # a REAL conflict, not a retry of our own write (§2.4). Swallowing
                # it as created=False would make renew report success while
                # expires_on never moves.
                raise EntryIdConflict
            return existing.id, False
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "entry:create"
        return inserted_id, True

    async def update_entry(
        self, db: AsyncSession, auth: AuthSession, entry_id: UUID, payload: EntryUpdate
    ) -> EntryRead | None:
        """Patch an entry's enrichable fields; never reparent (no tracker_id in DTO)."""
        changes = payload.model_dump(exclude_unset=True)
        # Probe only for identity, then obey the global reminder/freshness lock
        # order Tracker → Entry.  The locked re-read closes the race with a
        # scheduler that uses the same tracker row as its boundary.
        probe = await self._entry(db, auth, entry_id)
        if probe is None:
            return None
        tracker = await self._tracker(db, auth, probe.tracker_id, for_update=True)
        if tracker is None:
            return None
        entry = await self._entry(db, auth, entry_id, for_update=True)
        if entry is None or entry.tracker_id != tracker.id:
            return None
        if "tracker_id" in changes:
            raise EntryInvalid("entry.tracker_id là trường bất biến.")

        quantity = changes.get("quantity", entry.quantity)
        amount_raw = changes.get("amount", _amount_in(entry.amount))
        list_raw = changes.get("list_amount", _amount_in(entry.list_amount))
        await self._validate_entry(
            input_mode=tracker.input_mode,
            quantity=quantity,
            amount=amount_raw,
            list_amount=list_raw,
        )
        if "amount" in changes:
            entry.amount = _amount_out(changes["amount"])
        if "list_amount" in changes:
            entry.list_amount = _amount_out(changes["list_amount"])
        for field in ("occurred_at", "quantity"):
            if field in changes:
                setattr(entry, field, changes[field])
        if "note_md" in changes:
            entry.note_md = _sealed(changes["note_md"])
        if "occurred_at" in changes:
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "entry:update"
        await db.flush()
        return self._entry_read(entry)

    async def soft_delete_entry(self, db: AsyncSession, auth: AuthSession, entry_id: UUID) -> bool:
        """Soft-delete an entry — this is the undo button of a one-tap capture."""
        probe = await self._entry(db, auth, entry_id)
        if probe is None:
            return False
        tracker = await self._tracker(db, auth, probe.tracker_id, for_update=True)
        if tracker is None:
            return False
        entry = await self._entry(db, auth, entry_id, for_update=True)
        if entry is None or entry.tracker_id != tracker.id:
            return False
        entry.deleted_at = datetime.now(UTC)
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "entry:soft_delete"
        await db.flush()
        return True

    async def restore_entry(
        self, db: AsyncSession, auth: AuthSession, entry_id: UUID
    ) -> Entry | None:
        """Restore a soft-deleted entry (undo-of-undo) through its visible parent."""
        stmt = (
            select(Entry).join(Tracker, Entry.tracker_id == Tracker.id).where(Entry.id == entry_id)
        )
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = stmt.where(Entry.deleted_at.is_not(None))
        entry = (await db.execute(stmt)).scalar_one_or_none()
        if entry is None:
            return await self._entry(db, auth, entry_id)
        tracker = await self._tracker(db, auth, entry.tracker_id, for_update=True)
        if tracker is None:
            return None
        locked_stmt = (
            select(Entry)
            .join(Tracker, Entry.tracker_id == Tracker.id)
            .where(Entry.id == entry_id, Entry.deleted_at.is_not(None))
        )
        locked_stmt = with_privacy_gate(locked_stmt, Tracker, auth).with_for_update(of=Entry)
        entry = (await db.execute(locked_stmt)).scalar_one_or_none()
        if entry is None or entry.tracker_id != tracker.id:
            return None
        entry.deleted_at = None
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "entry:restore"
        await db.flush()
        return entry
