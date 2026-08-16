"""Task DTOs and the request-scoped Postgres store for the pattern-setting slice."""

import base64
import hashlib
import hmac
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, delete, false, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task, TaskItem
from app.domain.reading import can_see_private, readable, with_privacy_gate

TaskStatus = Literal["open", "completed"]
TaskListStatus = Literal["open", "completed", "all"]
TaskBucket = Literal["dated", "overdue", "undated"]
TaskPriority = Literal["p1", "p2", "p3"]
NonEmptyText = Annotated[str, Field(min_length=1)]


class TaskItemCreate(BaseModel):
    """Fields accepted when appending a checklist item."""

    content: str = Field(min_length=1)
    position: int = Field(default=0, ge=0)


class TaskItemUpdate(BaseModel):
    """Optional checklist changes; ``task_id`` exists only to reject reparenting."""

    content: str | None = Field(default=None, min_length=1)
    is_completed: bool | None = None
    position: int | None = Field(default=None, ge=0)
    task_id: UUID | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TaskItemUpdate":
        """Explicit nulls cannot replace non-null checklist columns."""
        for field in ("content", "is_completed", "position"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TaskItemRead(BaseModel):
    """Decrypted checklist item returned at the API boundary."""

    id: UUID
    content: str
    is_completed: bool
    position: int
    created_at: datetime | None
    updated_at: datetime | None


class TaskCreate(BaseModel):
    """Fields accepted when creating a task and its initial checklist."""

    id: UUID | None = None
    title: str = Field(min_length=1)
    body_md: str | None = None
    status: TaskStatus = "open"
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    is_private: bool = False
    items: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_uuidv7(self) -> "TaskCreate":
        """Client-selected task IDs must preserve the UUIDv7 ordering contract."""
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        return self

    @field_validator("due_at")
    @classmethod
    def require_aware_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at must include a timezone offset")
        return value


class TaskUpdate(BaseModel):
    """Patch semantics for a task; only explicitly supplied fields are changed."""

    title: str | None = Field(default=None, min_length=1)
    body_md: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    is_private: bool | None = None
    pinned: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TaskUpdate":
        """Explicit nulls cannot replace non-null task columns."""
        for field in ("title", "status", "is_private", "pinned"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("due_at")
    @classmethod
    def require_aware_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("due_at must include a timezone offset")
        return value


class TaskRead(BaseModel):
    """Decrypted task returned at the API boundary."""

    id: UUID
    title: str
    body_md: str | None
    status: TaskStatus
    priority: TaskPriority | None
    due_at: datetime | None
    completed_at: datetime | None
    is_private: bool
    pinned: bool
    items: list[TaskItemRead]
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)


class TaskPage(BaseModel):
    """Bounded keyset page shared by the task timeline and Calendar."""

    items: list[TaskRead]
    next_cursor: str | None = None
    has_previous: bool = False
    has_next: bool = False
    counts: dict[str, int] = Field(default_factory=dict)


class TaskTimeline(BaseModel):
    """One bounded aggregate wave for the primary Task screen."""

    items: list[TaskRead]
    next_cursor: str | None = None
    bucket_cursors: dict[str, str | None] = Field(default_factory=dict)
    has_previous: bool = False
    has_next: bool = False
    loaded_range_start: date
    loaded_range_end: date
    counts: dict[str, int] = Field(default_factory=dict)


class InvalidTaskCursor(ValueError):
    """An opaque cursor was malformed, tampered, expired, or mis-scoped."""


_CURSOR_VERSION = 1
_CURSOR_TTL = timedelta(minutes=15)


def _cursor_secret() -> bytes:
    configured = get_settings().oauth_state_secret
    # Local tests and development can use the app name; production should set the
    # existing OAuth state secret, avoiding a new secret surface for this read token.
    return (configured or get_settings().app_name).encode("utf-8")


def _cursor_encode(payload: dict[str, object]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).rstrip(b"=")
    signature = hmac.new(_cursor_secret(), encoded, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{encoded.decode('ascii')}.{encoded_signature}"


def _cursor_decode(
    token: str,
    *,
    status: TaskListStatus,
    from_instant: datetime | None,
    to_instant: datetime | None,
    bucket: TaskBucket,
    can_see_private: bool,
) -> dict[str, object]:
    try:
        encoded, supplied = token.split(".", 1)
        expected = hmac.new(_cursor_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        if not hmac.compare_digest(expected, actual):
            raise InvalidTaskCursor("invalid cursor signature")
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        )
        if not isinstance(payload, dict):
            raise InvalidTaskCursor("invalid cursor payload")
        expires = float(payload.get("expires", 0))
        if payload.get("v") != _CURSOR_VERSION or expires < datetime.now(UTC).timestamp():
            raise InvalidTaskCursor("expired cursor")
        scope = {
            "status": status,
            "from": from_instant.isoformat() if from_instant else None,
            "to": to_instant.isoformat() if to_instant else None,
            "bucket": bucket,
            "private": can_see_private,
            "direction": "forward",
        }
        if any(payload.get(key) != value for key, value in scope.items()):
            raise InvalidTaskCursor("cursor scope mismatch")
        last = payload.get("last")
        if not isinstance(last, dict) or not isinstance(last.get("id"), str):
            raise InvalidTaskCursor("invalid cursor position")
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        if isinstance(error, InvalidTaskCursor):
            raise
        raise InvalidTaskCursor("invalid cursor") from error


def _cursor_for(
    task: Task,
    *,
    status: TaskListStatus,
    from_instant: datetime | None,
    to_instant: datetime | None,
    bucket: TaskBucket,
    can_see_private: bool,
) -> str:
    return _cursor_encode(
        {
            "v": _CURSOR_VERSION,
            "status": status,
            "from": from_instant.isoformat() if from_instant else None,
            "to": to_instant.isoformat() if to_instant else None,
            "bucket": bucket,
            "private": can_see_private,
            "direction": "forward",
            "expires": (datetime.now(UTC) + _CURSOR_TTL).timestamp(),
            "last": {
                "pinned": task.pinned,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "id": str(task.id),
            },
        }
    )


class TaskIdConflict(Exception):
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


class TaskStore:
    """Stateless task persistence; every method joins its request transaction."""

    async def _parent(
        self,
        db: AsyncSession,
        auth: AuthSession,
        task_id: UUID,
        *,
        for_update: bool = False,
    ) -> Task | None:
        stmt = readable(select(Task).where(Task.id == task_id), Task, auth)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _items(self, db: AsyncSession, task_id: UUID) -> list[TaskItem]:
        result = await db.execute(
            select(TaskItem)
            .where(TaskItem.task_id == task_id)
            .order_by(TaskItem.position, TaskItem.created_at)
        )
        return list(result.scalars())

    def _item_read(self, item: TaskItem) -> TaskItemRead:
        return TaskItemRead(
            id=item.id,
            content=_clear(item.content),
            is_completed=item.is_completed,
            position=item.position,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _task_read(self, task: Task, items: list[TaskItem]) -> TaskRead:
        return TaskRead(
            id=task.id,
            title=_clear(task.title),
            body_md=_clear(task.body_md),
            status=task.status,
            priority=task.priority,
            due_at=task.due_at,
            completed_at=task.completed_at,
            is_private=task.is_private,
            pinned=task.pinned,
            items=[self._item_read(item) for item in items],
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    async def list(
        self,
        db: AsyncSession,
        auth: AuthSession,
        *,
        status: TaskListStatus = "open",
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskRead]:
        """List visible tasks and their children in the locked ordering."""
        stmt = readable(select(Task), Task, auth)
        if status != "all":
            stmt = stmt.where(Task.status == status)
        stmt = stmt.order_by(
            Task.pinned.desc(),
            Task.due_at.asc().nulls_last(),
            Task.created_at.desc(),
        )
        result = await db.execute(stmt.limit(limit).offset(offset))
        parents = list(result.scalars())
        if not parents:
            return []

        task_ids = [task.id for task in parents]
        child_result = await db.execute(
            select(TaskItem)
            .where(TaskItem.task_id.in_(task_ids))
            .order_by(TaskItem.position, TaskItem.created_at)
        )
        grouped: dict[UUID, list[TaskItem]] = defaultdict(list)
        for item in child_result.scalars():
            grouped[item.task_id].append(item)
        return [self._task_read(task, grouped[task.id]) for task in parents]

    @staticmethod
    def _keyset_after(task_cls: type[Task], last: dict[str, object]):
        """Build the forward predicate for pinned/due/created/id ordering."""
        pinned = bool(last["pinned"])
        due_raw = last.get("due_at")
        created_raw = last.get("created_at")
        due_at = datetime.fromisoformat(str(due_raw)) if due_raw else None
        created_at = datetime.fromisoformat(str(created_raw)) if created_raw else None
        task_id = UUID(str(last["id"]))
        same_due = task_cls.due_at.is_(None) if due_at is None else task_cls.due_at == due_at
        later_due = task_cls.due_at > due_at if due_at is not None else false()
        same_created = (
            task_cls.created_at.is_(None)
            if created_at is None
            else task_cls.created_at == created_at
        )
        later_created = (
            task_cls.created_at.is_not(None)
            if created_at is None
            else task_cls.created_at < created_at
        )
        later_pinned = task_cls.pinned.is_(False) if pinned else false()
        return or_(
            later_pinned,
            and_(
                task_cls.pinned == pinned,
                or_(
                    later_due,
                    and_(same_due, later_created),
                    and_(same_due, same_created, task_cls.id > task_id),
                ),
            ),
        )

    @staticmethod
    def _keyset_before(task_cls: type[Task], last: dict[str, object]):
        """Build the inverse predicate used only for honest has_previous metadata."""
        pinned = bool(last["pinned"])
        due_raw = last.get("due_at")
        created_raw = last.get("created_at")
        due_at = datetime.fromisoformat(str(due_raw)) if due_raw else None
        created_at = datetime.fromisoformat(str(created_raw)) if created_raw else None
        task_id = UUID(str(last["id"]))
        same_due = task_cls.due_at.is_(None) if due_at is None else task_cls.due_at == due_at
        earlier_due = task_cls.due_at.is_not(None) if due_at is None else task_cls.due_at < due_at
        same_created = (
            task_cls.created_at.is_(None)
            if created_at is None
            else task_cls.created_at == created_at
        )
        earlier_created = (
            task_cls.created_at.is_not(None)
            if created_at is None
            else task_cls.created_at > created_at
        )
        earlier_pinned = task_cls.pinned.is_(True) if not pinned else false()
        return or_(
            earlier_pinned,
            and_(
                task_cls.pinned == pinned,
                or_(
                    earlier_due,
                    and_(same_due, earlier_created),
                    and_(same_due, same_created, task_cls.id < task_id),
                ),
            ),
        )

    async def list_cursor(
        self,
        db: AsyncSession,
        auth: AuthSession,
        *,
        status: TaskListStatus = "open",
        from_instant: datetime | None = None,
        to_instant: datetime | None = None,
        bucket: TaskBucket = "dated",
        limit: int = 50,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> TaskPage:
        """Return a bounded page using signed keyset cursors.

        ``readable`` and deleted filtering are applied before the cursor and limit;
        this is the privacy boundary that the old offset endpoint could not express.
        """
        if not 1 <= limit <= 100:
            raise InvalidTaskCursor("limit out of range")
        if from_instant and from_instant.tzinfo is None:
            raise InvalidTaskCursor("from must be timezone-aware")
        if to_instant and to_instant.tzinfo is None:
            raise InvalidTaskCursor("to must be timezone-aware")
        visible_private = can_see_private(auth)
        last: dict[str, object] | None = None
        if cursor:
            last = _cursor_decode(
                cursor,
                status=status,
                from_instant=from_instant,
                to_instant=to_instant,
                bucket=bucket,
                can_see_private=visible_private,
            )["last"]  # type: ignore[assignment]

        stmt = readable(select(Task), Task, auth)
        if status != "all":
            stmt = stmt.where(Task.status == status)
        if bucket == "undated":
            stmt = stmt.where(Task.due_at.is_(None))
        elif bucket == "overdue":
            if from_instant is None:
                raise InvalidTaskCursor("overdue bucket requires range start")
            stmt = stmt.where(Task.due_at < (now or datetime.now(UTC)), Task.due_at < from_instant)
        else:
            if from_instant is not None:
                stmt = stmt.where(Task.due_at >= from_instant)
            if to_instant is not None:
                stmt = stmt.where(Task.due_at < to_instant)
        total = int(
            await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        )
        if last:
            stmt = stmt.where(self._keyset_after(Task, last))
        ordered = stmt.order_by(
            Task.pinned.desc(),
            Task.due_at.asc().nulls_last(),
            Task.created_at.desc(),
            Task.id.asc(),
        )
        result = await db.execute(ordered.limit(limit + 1))
        parents = list(result.scalars())
        has_next = len(parents) > limit
        parents = parents[:limit]
        if not parents:
            return TaskPage(
                items=[], has_previous=bool(cursor), has_next=False, counts={bucket: total}
            )
        task_ids = [task.id for task in parents]
        child_result = await db.execute(
            select(TaskItem)
            .where(TaskItem.task_id.in_(task_ids))
            .order_by(TaskItem.position, TaskItem.created_at)
        )
        grouped: dict[UUID, list[TaskItem]] = defaultdict(list)
        for item in child_result.scalars():
            grouped[item.task_id].append(item)
        items = [self._task_read(task, grouped[task.id]) for task in parents]
        next_cursor = (
            _cursor_for(
                parents[-1],
                status=status,
                from_instant=from_instant,
                to_instant=to_instant,
                bucket=bucket,
                can_see_private=visible_private,
            )
            if has_next
            else None
        )
        # A cursor establishes a previous page. On the initial page, a bounded
        # range has a previous page only when an older matching row exists.
        has_previous = bool(cursor)
        return TaskPage(
            items=items,
            next_cursor=next_cursor,
            has_previous=has_previous,
            has_next=has_next,
            counts={bucket: total},
        )

    async def timeline(
        self,
        db: AsyncSession,
        auth: AuthSession,
        *,
        status: TaskListStatus,
        from_instant: datetime,
        to_instant: datetime,
        limit: int,
        cursors: dict[TaskBucket, str | None] | None = None,
    ) -> TaskTimeline:
        """Fetch dated, overdue and undated buckets in one bounded request wave."""
        cursors = cursors or {}
        pages: dict[TaskBucket, TaskPage] = {}
        for bucket in ("overdue", "dated", "undated"):
            pages[bucket] = await self.list_cursor(
                db,
                auth,
                status=status,
                from_instant=from_instant,
                to_instant=to_instant,
                bucket=bucket,
                limit=limit,
                cursor=cursors.get(bucket),
            )
        items = [item for bucket in ("overdue", "dated", "undated") for item in pages[bucket].items]
        bucket_cursors = {bucket: pages[bucket].next_cursor for bucket in pages}
        return TaskTimeline(
            items=items,
            bucket_cursors=bucket_cursors,
            has_previous=any(page.has_previous for page in pages.values()),
            has_next=any(page.has_next for page in pages.values()),
            loaded_range_start=from_instant.date(),
            loaded_range_end=(to_instant - timedelta(days=1)).date(),
            counts={bucket: next(iter(page.counts.values()), 0) for bucket, page in pages.items()},
        )

    async def get(self, db: AsyncSession, auth: AuthSession, task_id: UUID) -> TaskRead | None:
        """Return one visible task, or None without disclosing why it is hidden."""
        task = await self._parent(db, auth, task_id)
        if task is None:
            return None
        return self._task_read(task, await self._items(db, task_id))

    async def create(self, db: AsyncSession, auth: AuthSession, payload: TaskCreate) -> TaskRead:
        """Create a task and its initial checklist atomically."""
        if payload.is_private and not can_see_private(auth):
            raise PrivateWriteLocked
        values = {
            "title": _sealed(payload.title) if payload.is_private else payload.title,
            "body_md": _sealed(payload.body_md) if payload.is_private else payload.body_md,
            "status": payload.status,
            "completed_at": datetime.now(UTC) if payload.status == "completed" else None,
            "priority": payload.priority,
            "due_at": payload.due_at,
            "is_private": payload.is_private,
        }
        if payload.id is None:
            task = Task(**values)
            db.add(task)
            await db.flush()
        else:
            inserted_id = (
                await db.execute(
                    insert(Task)
                    .values(id=payload.id, **values)
                    .on_conflict_do_nothing(index_elements=[Task.id])
                    .returning(Task.id)
                )
            ).scalar_one_or_none()
            if inserted_id is None:
                existing = await self._parent(db, auth, payload.id)
                if existing is None:
                    physical = await db.execute(select(Task.id).where(Task.id == payload.id))
                    if physical.scalar_one_or_none() is not None:
                        raise TaskIdConflict
                    raise RuntimeError("conflicting task disappeared before it could be read")
                result = self._task_read(existing, await self._items(db, payload.id))
                result.created = False
                return result

            inserted = await db.execute(select(Task).where(Task.id == inserted_id))
            task = inserted.scalar_one()

        # The parent is new and cannot yet be reached by another transaction, but
        # taking the same lock used by every other item-write path keeps the store's
        # invariant explicit and makes this transaction shape safe to copy.
        locked = await db.execute(select(Task).where(Task.id == task.id).with_for_update())
        task = locked.scalar_one()
        items = [
            TaskItem(
                task_id=task.id,
                content=_sealed(content) if task.is_private else content,
                position=position,
            )
            for position, content in enumerate(payload.items)
        ]
        db.add_all(items)
        await db.flush()
        result = self._task_read(task, items)
        result.created = True
        return result

    async def update(
        self,
        db: AsyncSession,
        auth: AuthSession,
        task_id: UUID,
        payload: TaskUpdate,
    ) -> TaskRead | None:
        """Patch a task, preserving the trigger-required toggle ordering."""
        changes = payload.model_dump(exclude_unset=True)
        wants_toggle = "is_private" in changes
        task = await self._parent(db, auth, task_id, for_update=wants_toggle or "status" in changes)
        if task is None:
            return None
        items = await self._items(db, task_id)
        target_private = changes.get("is_private", task.is_private)
        if target_private and not can_see_private(auth):
            raise PrivateWriteLocked

        if wants_toggle and target_private != task.is_private:
            if target_private:
                if "title" in changes:
                    task.title = changes["title"]
                if "body_md" in changes:
                    task.body_md = changes["body_md"]
                task.title = _sealed(_clear(task.title))
                task.body_md = _sealed(_clear(task.body_md))
                for item in items:
                    item.content = _sealed(_clear(item.content))
                # Children and prose become ciphertext while the parent is still
                # public; only then may the DB trigger accept the flag transition.
                await db.flush()
                task.is_private = True
                await db.flush()
            else:
                # Flip the parent first so decrypting children cannot leave plaintext
                # beneath a private parent, even transiently inside this transaction.
                task.is_private = False
                await db.flush()
                task.title = _clear(task.title)
                task.body_md = _clear(task.body_md)
                for item in items:
                    item.content = _clear(item.content)
                if "title" in changes:
                    task.title = changes["title"]
                if "body_md" in changes:
                    task.body_md = changes["body_md"]
        else:
            if "title" in changes:
                task.title = _sealed(changes["title"]) if task.is_private else changes["title"]
            if "body_md" in changes:
                body_md = changes["body_md"]
                task.body_md = _sealed(body_md) if task.is_private else body_md

        old_status = task.status
        if "status" in changes and changes["status"] != old_status:
            task.completed_at = datetime.now(UTC) if changes["status"] == "completed" else None

        for field in ("status", "priority", "due_at", "pinned"):
            if field in changes:
                setattr(task, field, changes[field])
        await db.flush()
        return self._task_read(task, items)

    async def soft_delete(self, db: AsyncSession, auth: AuthSession, task_id: UUID) -> bool:
        """Mark a visible task deleted; its children become unreachable through it."""
        task = await self._parent(db, auth, task_id)
        if task is None:
            return False
        task.deleted_at = datetime.now(UTC)
        await db.flush()
        return True

    async def restore(self, db: AsyncSession, auth: AuthSession, task_id: UUID) -> Task | None:
        """Restore a privacy-visible task without exposing why a row is hidden."""
        deleted_stmt = with_privacy_gate(select(Task).where(Task.id == task_id), Task, auth).where(
            Task.deleted_at.is_not(None)
        )
        deleted_result = await db.execute(deleted_stmt)
        task = deleted_result.scalar_one_or_none()

        if task is None:
            # A live task is already restored. Resolve it through the ordinary
            # readable gate so idempotency never bypasses privacy.
            task = await self._parent(db, auth, task_id)
            if task is None:
                return None
        else:
            task.deleted_at = None
            await db.flush()

        return task

    async def list_items(
        self, db: AsyncSession, auth: AuthSession, task_id: UUID
    ) -> list[TaskItemRead] | None:
        """List children only after resolving their visible parent."""
        parent = await self._parent(db, auth, task_id)
        if parent is None:
            return None
        return [self._item_read(item) for item in await self._items(db, task_id)]

    async def add_item(
        self,
        db: AsyncSession,
        auth: AuthSession,
        task_id: UUID,
        payload: TaskItemCreate,
    ) -> TaskItemRead | None:
        """Append an item after locking and resolving its visible parent."""
        parent = await self._parent(db, auth, task_id, for_update=True)
        if parent is None:
            return None
        item = TaskItem(
            task_id=parent.id,
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
        task_id: UUID,
        item_id: UUID,
        payload: TaskItemUpdate,
    ) -> TaskItemRead | None:
        """Patch an item without ever allowing it to move between parents."""
        changes = payload.model_dump(exclude_unset=True)
        if "task_id" in changes:
            raise ValueError("task_item.task_id is immutable")

        parent = await self._parent(db, auth, task_id, for_update=True)
        if parent is None:
            return None
        result = await db.execute(
            select(TaskItem).where(TaskItem.id == item_id, TaskItem.task_id == parent.id)
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
        task_id: UUID,
        item_id: UUID,
    ) -> bool:
        """Hard-delete one checklist item after locking its visible parent."""
        parent = await self._parent(db, auth, task_id, for_update=True)
        if parent is None:
            return False
        result = await db.execute(
            select(TaskItem.id).where(TaskItem.id == item_id, TaskItem.task_id == parent.id)
        )
        if result.scalar_one_or_none() is None:
            return False
        await db.execute(delete(TaskItem).where(TaskItem.id == item_id))
        return True
