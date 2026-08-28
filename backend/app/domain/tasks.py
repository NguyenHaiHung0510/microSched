"""Task DTOs and the request-scoped Postgres store for the pattern-setting slice."""

import base64
import hashlib
import hmac
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import Date, and_, case, cast, delete, false, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task, TaskItem
from app.domain.reading import can_see_private, readable, with_privacy_gate

TaskStatus = Literal["open", "completed"]
TaskListStatus = Literal["open", "completed", "all"]
TaskBucket = Literal["dated", "overdue", "undated", "open_picker"]
TaskPriority = Literal["p1", "p2", "p3"]
TaskDuePrecision = Literal["none", "date", "datetime"]
NonEmptyText = Annotated[str, Field(min_length=1)]

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

_SCHEDULE_FIELDS = frozenset({"due_precision", "due_on", "due_at"})


def _schedule_error(message: str) -> PydanticCustomError:
    """Return the stable machine-readable 422 error for an invalid due shape."""
    return PydanticCustomError("task_schedule_invalid", message)


def _canonicalize_schedule(payload: BaseModel, *, default_none: bool) -> None:
    """Validate one input triad and replace it with its canonical representation.

    ``TaskUpdate`` may omit the whole triad, which means preserve. ``TaskCreate``
    maps an omitted legacy schedule to ``none`` without consulting a server clock.
    """
    supplied = payload.model_fields_set & _SCHEDULE_FIELDS
    if not supplied:
        if default_none:
            payload.due_precision = "none"  # type: ignore[attr-defined]
            payload.due_on = None  # type: ignore[attr-defined]
            payload.due_at = None  # type: ignore[attr-defined]
        return

    precision = payload.due_precision  # type: ignore[attr-defined]
    due_on = payload.due_on  # type: ignore[attr-defined]
    due_at = payload.due_at  # type: ignore[attr-defined]

    if "due_precision" in supplied and precision is None:
        raise _schedule_error("due_precision cannot be null")
    if "due_precision" not in supplied:
        if "due_on" in supplied:
            raise _schedule_error("due_on requires an explicit due_precision")
        precision = "datetime" if due_at is not None else "none"

    if precision == "none":
        if due_on is not None or due_at is not None:
            raise _schedule_error("none precision cannot include due_on or due_at")
        due_on = None
        due_at = None
    elif precision == "date":
        if due_on is None or due_at is not None:
            raise _schedule_error("date precision requires due_on and no due_at")
        due_at = None
    elif precision == "datetime":
        if due_at is None or due_on is not None:
            raise _schedule_error("datetime precision requires due_at and no due_on")
        due_on = None
    else:  # Literal validation normally catches this; keep the helper fail-closed.
        raise _schedule_error("unsupported due_precision")

    payload.due_precision = precision  # type: ignore[attr-defined]
    payload.due_on = due_on  # type: ignore[attr-defined]
    payload.due_at = due_at  # type: ignore[attr-defined]


class TaskItemCreate(BaseModel):
    """Fields accepted when appending a checklist item."""

    content: str = Field(min_length=1)
    position: int = Field(default=0, ge=0)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class TaskItemUpdate(BaseModel):
    """Optional checklist changes; ``task_id`` exists only to reject reparenting."""

    content: str | None = Field(default=None, min_length=1)
    is_completed: bool | None = None
    position: int | None = Field(default=None, ge=0)
    task_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("content must not be blank")
        return value

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
    due_precision: TaskDuePrecision | None = None
    due_on: date | None = None
    due_at: datetime | None = None
    is_private: bool = False
    items: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_create(self) -> "TaskCreate":
        """Preserve UUID ordering and canonicalize legacy/V2 due inputs."""
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        _canonicalize_schedule(self, default_none=True)
        return self

    @field_validator("due_at")
    @classmethod
    def require_aware_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise _schedule_error("due_at must include a timezone offset")
        return value

    @field_validator("items")
    @classmethod
    def reject_blank_items(cls, value: list[str]) -> list[str]:
        for idx, item in enumerate(value):
            if not item.strip():
                raise ValueError(f"items[{idx}] must not be blank")
        return value

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str) -> str:
        """Keep the stored title intact while refusing a whitespace-only task."""
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class TaskUpdate(BaseModel):
    """Patch semantics for a task; only explicitly supplied fields are changed."""

    title: str | None = Field(default=None, min_length=1)
    body_md: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_precision: TaskDuePrecision | None = None
    due_on: date | None = None
    due_at: datetime | None = None
    is_private: bool | None = None
    pinned: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TaskUpdate":
        """Explicit nulls cannot replace non-null task columns."""
        for field in ("title", "status", "is_private", "pinned"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        _canonicalize_schedule(self, default_none=False)
        return self

    @field_validator("due_at")
    @classmethod
    def require_aware_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise _schedule_error("due_at must include a timezone offset")
        return value

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str | None) -> str | None:
        """PATCH follows create's whitespace rule without rewriting valid text."""
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value


class TaskRead(BaseModel):
    """Decrypted task returned at the API boundary."""

    id: UUID
    title: str
    body_md: str | None
    status: TaskStatus
    priority: TaskPriority | None
    due_precision: TaskDuePrecision
    due_on: date | None
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


_CURSOR_VERSION = 2
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


def _canonical_instant(value: datetime) -> str:
    """Serialize cursor instants in one timezone-independent RFC3339 form."""
    if value.tzinfo is None:
        raise InvalidTaskCursor("cursor instant must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _scope_instant(value: datetime | None) -> str | None:
    return _canonical_instant(value) if value is not None else None


def _parse_cursor_instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise InvalidTaskCursor(f"cursor {field} must be an instant")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidTaskCursor(f"cursor {field} is invalid") from error
    if parsed.tzinfo is None or _canonical_instant(parsed) != value:
        raise InvalidTaskCursor(f"cursor {field} is not canonical UTC")
    return parsed


def _parse_cursor_day(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise InvalidTaskCursor(f"cursor {field} must be a civil date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise InvalidTaskCursor(f"cursor {field} is invalid") from error
    if parsed.isoformat() != value:
        raise InvalidTaskCursor(f"cursor {field} is not canonical")
    return parsed


def _validate_cursor_last(last: object, bucket: TaskBucket) -> dict[str, object]:
    """Validate every normalized-key field before it reaches a SQL predicate."""
    expected_fields = {
        "group_rank",
        "group_day",
        "pinned",
        "schedule_day",
        "precision_rank",
        "due_at",
        "created_at",
        "id",
    }
    if not isinstance(last, dict) or set(last) != expected_fields:
        raise InvalidTaskCursor("invalid cursor position")
    if not isinstance(last["pinned"], bool):
        raise InvalidTaskCursor("invalid cursor pin value")
    for field in ("group_rank", "precision_rank"):
        if isinstance(last[field], bool) or not isinstance(last[field], int):
            raise InvalidTaskCursor(f"invalid cursor {field}")

    try:
        task_id = UUID(str(last["id"]))
    except ValueError as error:
        raise InvalidTaskCursor("invalid cursor id") from error
    if not isinstance(last["id"], str) or str(task_id) != last["id"]:
        raise InvalidTaskCursor("cursor id is not canonical")
    _parse_cursor_instant(last["created_at"], "created_at")

    group_day = (
        None if last["group_day"] is None else _parse_cursor_day(last["group_day"], "group_day")
    )
    schedule_day = (
        None
        if last["schedule_day"] is None
        else _parse_cursor_day(last["schedule_day"], "schedule_day")
    )
    due_at = None if last["due_at"] is None else _parse_cursor_instant(last["due_at"], "due_at")
    precision_rank = last["precision_rank"]
    if precision_rank == 0:
        if schedule_day is None or due_at is None:
            raise InvalidTaskCursor("datetime cursor shape is incomplete")
        if due_at.astimezone(VIETNAM_TZ).date() != schedule_day:
            raise InvalidTaskCursor("datetime cursor day does not match due_at")
    elif precision_rank == 1:
        if schedule_day is None or due_at is not None:
            raise InvalidTaskCursor("date cursor shape is invalid")
    elif precision_rank == 2:
        if schedule_day is not None or due_at is not None:
            raise InvalidTaskCursor("unscheduled cursor shape is invalid")
    else:
        raise InvalidTaskCursor("invalid cursor precision rank")

    group_rank = last["group_rank"]
    if bucket == "overdue":
        valid_group = group_rank == 0 and group_day is None and precision_rank in {0, 1}
    elif bucket == "dated":
        valid_group = group_rank == 1 and group_day == schedule_day and precision_rank in {0, 1}
    elif bucket == "undated":
        valid_group = (
            group_rank == 2 and group_day is None and schedule_day is None and precision_rank == 2
        )
    else:
        valid_group = (
            group_rank == 1 and group_day == schedule_day and precision_rank in {0, 1}
        ) or (
            group_rank == 2 and group_day is None and schedule_day is None and precision_rank == 2
        )
    if not valid_group:
        raise InvalidTaskCursor("cursor group does not match bucket")
    return last


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
            "from": _scope_instant(from_instant),
            "to": _scope_instant(to_instant),
            "bucket": bucket,
            "private": can_see_private,
            "direction": "forward",
        }
        if any(payload.get(key) != value for key, value in scope.items()):
            raise InvalidTaskCursor("cursor scope mismatch")
        payload["last"] = _validate_cursor_last(payload.get("last"), bucket)
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
    precision, due_on, due_at = _stored_schedule(task)
    if precision == "date":
        schedule_day = due_on
        precision_rank = 1
    elif precision == "datetime":
        assert due_at is not None
        schedule_day = due_at.astimezone(VIETNAM_TZ).date()
        precision_rank = 0
    else:
        schedule_day = None
        precision_rank = 2

    if bucket == "overdue":
        group_rank, group_day = 0, None
    elif bucket == "dated":
        group_rank, group_day = 1, schedule_day
    elif bucket == "undated":
        group_rank, group_day = 2, None
    elif schedule_day is None:
        group_rank, group_day = 2, None
    else:
        group_rank, group_day = 1, schedule_day
    if task.created_at is None:
        raise InvalidTaskCursor("cannot cursor a task without created_at")
    return _cursor_encode(
        {
            "v": _CURSOR_VERSION,
            "status": status,
            "from": _scope_instant(from_instant),
            "to": _scope_instant(to_instant),
            "bucket": bucket,
            "private": can_see_private,
            "direction": "forward",
            "expires": (datetime.now(UTC) + _CURSOR_TTL).timestamp(),
            "last": {
                "group_rank": group_rank,
                "group_day": group_day.isoformat() if group_day else None,
                "pinned": task.pinned,
                "schedule_day": schedule_day.isoformat() if schedule_day else None,
                "precision_rank": precision_rank,
                "due_at": _canonical_instant(due_at) if due_at else None,
                "created_at": _canonical_instant(task.created_at),
                "id": str(task.id),
            },
        }
    )


class TaskIdConflict(Exception):
    """A client-selected ID belongs to a row hidden by a reading gate."""


class PrivateWriteLocked(Exception):
    """A write tried to create private data while the display gate was closed."""


class TaskScheduleShapeError(RuntimeError):
    """A physical row violates the expand-phase application invariant."""


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


def _stored_schedule(task: Task) -> tuple[TaskDuePrecision, date | None, datetime | None]:
    """Dual-read the expand schema and fail closed for an impossible V2 shape."""
    precision = task.due_precision
    if precision is None:
        # A row created before 0010, or caught in the expand/deploy window.
        return ("datetime", None, task.due_at) if task.due_at is not None else ("none", None, None)
    if precision == "none" and task.due_on is None and task.due_at is None:
        return "none", None, None
    if precision == "date" and task.due_on is not None and task.due_at is None:
        return "date", task.due_on, None
    if precision == "datetime" and task.due_on is None and task.due_at is not None:
        if task.due_at.tzinfo is None:
            raise TaskScheduleShapeError("stored datetime task has a naive due_at")
        return "datetime", None, task.due_at
    raise TaskScheduleShapeError("stored task has an invalid due schedule shape")


def _dual_write_stored_schedule(task: Task) -> None:
    """Canonicalize the full triad whenever this V2 binary updates a task row."""
    precision, due_on, due_at = _stored_schedule(task)
    task.due_precision = precision
    task.due_on = due_on
    task.due_at = due_at


async def _mark_v2_due_writer(db: AsyncSession) -> None:
    """Mark only the current transaction so legacy triggers never rewrite V2."""
    await db.execute(text("SELECT set_config('microsched.task_due_writer', 'v2', true)"))


def _schedule_sql(task_cls: type[Task]):
    """Build the single dual-read SQL representation used by filter/order/cursor."""
    precision = case(
        (
            task_cls.due_precision.is_(None),
            case(
                (task_cls.due_at.is_not(None), literal("datetime")),
                else_=literal("none"),
            ),
        ),
        else_=task_cls.due_precision,
    )
    schedule_day = case(
        (precision == "date", task_cls.due_on),
        (
            precision == "datetime",
            cast(func.timezone("Asia/Ho_Chi_Minh", task_cls.due_at), Date),
        ),
        else_=None,
    )
    precision_rank = case(
        (precision == "datetime", 0),
        (precision == "date", 1),
        else_=2,
    )
    return precision, schedule_day, precision_rank


def _order_fields(task_cls: type[Task], bucket: TaskBucket):
    """Return the exact variable suffix of the normalized Task schedule key."""
    precision, schedule_day, precision_rank = _schedule_sql(task_cls)
    pinned_rank = case((task_cls.pinned.is_(True), 1), else_=0)
    group_rank = case((precision == "none", 2), else_=1)
    group_day = case((precision == "none", None), else_=schedule_day)
    common_tail = [
        ("precision_rank", precision_rank, "asc", False),
        ("due_at", task_cls.due_at, "asc", True),
        ("created_at", task_cls.created_at, "desc", False),
        ("id", task_cls.id, "asc", False),
    ]
    if bucket == "dated":
        return [
            ("schedule_day", schedule_day, "asc", True),
            ("pinned", pinned_rank, "desc", False),
            *common_tail,
        ]
    if bucket == "overdue":
        return [
            ("pinned", pinned_rank, "desc", False),
            ("schedule_day", schedule_day, "asc", True),
            *common_tail,
        ]
    if bucket == "undated":
        return [
            ("pinned", pinned_rank, "desc", False),
            ("created_at", task_cls.created_at, "desc", False),
            ("id", task_cls.id, "asc", False),
        ]
    return [
        ("group_rank", group_rank, "asc", False),
        ("group_day", group_day, "asc", True),
        ("pinned", pinned_rank, "desc", False),
        ("schedule_day", schedule_day, "asc", True),
        *common_tail,
    ]


def _cursor_sql_value(field: str, value: object):
    if field in {"group_day", "schedule_day"}:
        return None if value is None else date.fromisoformat(str(value))
    if field in {"due_at", "created_at"}:
        return None if value is None else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if field == "id":
        return UUID(str(value))
    if field == "pinned":
        return 1 if value is True else 0
    return value


def _equal_expression(expression, value):
    return expression.is_(None) if value is None else expression == value


def _relative_expression(expression, value, *, direction: str, nulls_last: bool, after: bool):
    """Compare one ordered field while preserving explicit NULLS LAST semantics."""
    if value is None:
        if not nulls_last:
            raise InvalidTaskCursor("unexpected null in cursor order key")
        return false() if after else expression.is_not(None)
    if after:
        comparison = expression > value if direction == "asc" else expression < value
        return or_(comparison, expression.is_(None)) if nulls_last else comparison
    return expression < value if direction == "asc" else expression > value


def _keyset_relative(
    task_cls: type[Task], last: dict[str, object], bucket: TaskBucket, *, after: bool
):
    """Build a mixed-direction lexicographic predicate from the shared order spec."""
    prefixes = []
    branches = []
    for field, expression, direction, nulls_last in _order_fields(task_cls, bucket):
        value = _cursor_sql_value(field, last[field])
        relative = _relative_expression(
            expression,
            value,
            direction=direction,
            nulls_last=nulls_last,
            after=after,
        )
        branches.append(and_(*prefixes, relative))
        prefixes.append(_equal_expression(expression, value))
    return or_(*branches)


def _ordered(stmt, task_cls: type[Task], bucket: TaskBucket):
    expressions = []
    for _field, expression, direction, nulls_last in _order_fields(task_cls, bucket):
        ordered = expression.asc() if direction == "asc" else expression.desc()
        if nulls_last:
            ordered = ordered.nulls_last()
        expressions.append(ordered)
    return stmt.order_by(*expressions)


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
        due_precision, due_on, due_at = _stored_schedule(task)
        return TaskRead(
            id=task.id,
            title=_clear(task.title),
            body_md=_clear(task.body_md),
            status=task.status,
            priority=task.priority,
            due_precision=due_precision,
            due_on=due_on,
            due_at=due_at,
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
        stmt = _ordered(stmt, Task, "open_picker")
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
        if from_instant and to_instant and to_instant <= from_instant:
            raise InvalidTaskCursor("invalid range")
        now_value = now or datetime.now(UTC)
        if now_value.tzinfo is None:
            raise InvalidTaskCursor("now must be timezone-aware")
        from_day = from_instant.astimezone(VIETNAM_TZ).date() if from_instant else None
        to_day = to_instant.astimezone(VIETNAM_TZ).date() if to_instant else None
        today = now_value.astimezone(VIETNAM_TZ).date()
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
        precision, _schedule_day, _precision_rank = _schedule_sql(Task)
        if bucket == "open_picker":
            # Calendar move selection is a bounded open-work view across both
            # dated and undated tasks. It deliberately has its own cursor scope
            # so a calendar continuation can never be replayed as a timeline
            # bucket cursor.
            stmt = stmt.where(Task.status == "open")
        elif bucket == "undated":
            stmt = stmt.where(precision == "none")
        elif bucket == "overdue":
            if from_instant is None or from_day is None:
                raise InvalidTaskCursor("overdue bucket requires range start")
            # The overdue bucket is a navigation aid for open work. A caller
            # asking for ``status=all`` must not let completed historical rows
            # consume its bounded page and hide still-open work.
            stmt = stmt.where(
                Task.status == "open",
                or_(
                    and_(precision == "date", Task.due_on < today, Task.due_on < from_day),
                    and_(
                        precision == "datetime",
                        Task.due_at < now_value,
                        Task.due_at < from_instant,
                    ),
                ),
            )
        else:
            date_conditions = [precision == "date"]
            datetime_conditions = [precision == "datetime"]
            if from_instant is not None and from_day is not None:
                date_conditions.append(Task.due_on >= from_day)
                datetime_conditions.append(Task.due_at >= from_instant)
            if to_instant is not None and to_day is not None:
                date_conditions.append(Task.due_on < to_day)
                datetime_conditions.append(Task.due_at < to_instant)
            stmt = stmt.where(or_(and_(*date_conditions), and_(*datetime_conditions)))
        total = int(
            await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        )
        base_stmt = stmt
        has_previous = False
        if last:
            has_previous = bool(
                await db.scalar(
                    select(func.count()).select_from(
                        base_stmt.where(_keyset_relative(Task, last, bucket, after=False))
                        .order_by(None)
                        .subquery()
                    )
                )
            )
            stmt = stmt.where(_keyset_relative(Task, last, bucket, after=True))
        ordered = _ordered(stmt, Task, bucket)
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
        # Navigation metadata describes rows outside the requested date window,
        # after status/privacy/deleted filtering. It is deliberately independent
        # of the bounded bucket page, so a page-full overdue/undated bucket
        # cannot make the adjacent date CTA lie about terminal history.
        dated_scope = readable(select(Task), Task, auth)
        if status != "all":
            dated_scope = dated_scope.where(Task.status == status)
        precision, _schedule_day, _precision_rank = _schedule_sql(Task)
        from_day = from_instant.astimezone(VIETNAM_TZ).date()
        to_day = to_instant.astimezone(VIETNAM_TZ).date()
        dated_scope = dated_scope.where(precision.in_(("date", "datetime")))
        has_previous = bool(
            await db.scalar(
                select(func.count()).select_from(
                    dated_scope.where(
                        or_(
                            and_(precision == "date", Task.due_on < from_day),
                            and_(precision == "datetime", Task.due_at < from_instant),
                        )
                    ).subquery()
                )
            )
        )
        has_next = bool(
            await db.scalar(
                select(func.count()).select_from(
                    dated_scope.where(
                        or_(
                            and_(precision == "date", Task.due_on >= to_day),
                            and_(precision == "datetime", Task.due_at >= to_instant),
                        )
                    ).subquery()
                )
            )
        )
        return TaskTimeline(
            items=items,
            bucket_cursors=bucket_cursors,
            has_previous=has_previous,
            has_next=has_next,
            loaded_range_start=from_day,
            loaded_range_end=to_day - timedelta(days=1),
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
        await _mark_v2_due_writer(db)
        values = {
            "title": _sealed(payload.title) if payload.is_private else payload.title,
            "body_md": _sealed(payload.body_md) if payload.is_private else payload.body_md,
            "status": payload.status,
            "completed_at": datetime.now(UTC) if payload.status == "completed" else None,
            "priority": payload.priority,
            "due_precision": payload.due_precision,
            "due_on": payload.due_on,
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
        schedule_supplied = bool(payload.model_fields_set & _SCHEDULE_FIELDS)
        wants_toggle = "is_private" in changes
        task = await self._parent(db, auth, task_id, for_update=wants_toggle or "status" in changes)
        if task is None:
            return None
        items = await self._items(db, task_id)
        target_private = changes.get("is_private", task.is_private)
        if target_private and not can_see_private(auth):
            raise PrivateWriteLocked
        await _mark_v2_due_writer(db)

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

        for field in ("status", "priority", "pinned"):
            if field in changes:
                setattr(task, field, changes[field])
        if schedule_supplied:
            task.due_precision = payload.due_precision
            task.due_on = payload.due_on
            task.due_at = payload.due_at
        else:
            _dual_write_stored_schedule(task)
        await db.flush()
        return self._task_read(task, items)

    async def soft_delete(self, db: AsyncSession, auth: AuthSession, task_id: UUID) -> bool:
        """Mark a visible task deleted; its children become unreachable through it."""
        task = await self._parent(db, auth, task_id)
        if task is None:
            return False
        await _mark_v2_due_writer(db)
        _dual_write_stored_schedule(task)
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
            await _mark_v2_due_writer(db)
            _dual_write_stored_schedule(task)
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
