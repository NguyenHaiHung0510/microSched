"""Task DTOs and the request-scoped Postgres store for the pattern-setting slice."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain.models import AuthSession, Task, TaskItem
from app.domain.reading import readable, with_privacy_gate

TaskStatus = Literal["open", "completed"]
TaskListStatus = Literal["open", "completed", "all"]
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

    title: str = Field(min_length=1)
    body_md: str | None = None
    status: TaskStatus = "open"
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    is_private: bool = False
    items: list[NonEmptyText] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """Patch semantics for a task; only explicitly supplied fields are changed."""

    title: str | None = Field(default=None, min_length=1)
    body_md: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    is_private: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TaskUpdate":
        """Explicit nulls cannot replace non-null task columns."""
        for field in ("title", "status", "is_private"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TaskRead(BaseModel):
    """Decrypted task returned at the API boundary."""

    id: UUID
    title: str
    body_md: str | None
    status: TaskStatus
    priority: TaskPriority | None
    due_at: datetime | None
    is_private: bool
    items: list[TaskItemRead]
    created_at: datetime | None
    updated_at: datetime | None


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
            is_private=task.is_private,
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
        stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
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

    async def get(self, db: AsyncSession, auth: AuthSession, task_id: UUID) -> TaskRead | None:
        """Return one visible task, or None without disclosing why it is hidden."""
        task = await self._parent(db, auth, task_id)
        if task is None:
            return None
        return self._task_read(task, await self._items(db, task_id))

    async def create(self, db: AsyncSession, auth: AuthSession, payload: TaskCreate) -> TaskRead:
        """Create a task and its initial checklist atomically."""
        task = Task(
            title=_sealed(payload.title) if payload.is_private else payload.title,
            body_md=_sealed(payload.body_md) if payload.is_private else payload.body_md,
            status=payload.status,
            priority=payload.priority,
            due_at=payload.due_at,
            is_private=payload.is_private,
        )
        db.add(task)
        await db.flush()

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
        return self._task_read(task, items)

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
        task = await self._parent(db, auth, task_id, for_update=wants_toggle)
        if task is None:
            return None
        items = await self._items(db, task_id)
        target_private = changes.get("is_private", task.is_private)

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

        for field in ("status", "priority", "due_at"):
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
