"""Bounded STANDARD Task reads with explicit coverage and source versions."""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.models import Task

MAX_PAGE = 50
MAX_BATCH = 50
_FIELDS = ("id", "title", "status", "priority", "due_precision", "due_on", "due_at")
_OWNER_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class TaskFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "completed"] | None = None
    priority: Literal["p1", "p2", "p3"] | None = None
    due_from: date | None = None
    due_through: date | None = None
    title_contains: str | None = Field(default=None, min_length=2, max_length=120)

    @model_validator(mode="after")
    def validate_dates(self) -> TaskFilter:
        if self.due_from and self.due_through and self.due_from > self.due_through:
            raise ValueError("task_query_invalid_date_range")
        return self


class TaskQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter: TaskFilter = Field(default_factory=TaskFilter)
    projection: tuple[Literal[*_FIELDS], ...] = ("id", "title", "status", "due_on", "due_at")
    sort: Literal["updated_desc"] = "updated_desc"
    limit: int = Field(default=20, ge=1, le=MAX_PAGE)
    cursor: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_projection(self) -> TaskQuery:
        if not self.projection or len(set(self.projection)) != len(self.projection):
            raise ValueError("task_query_projection_invalid")
        return self


class TaskAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter: TaskFilter = Field(default_factory=TaskFilter)
    group_by: Literal["status", "priority", "due_precision"]


class TaskInspectBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: tuple[UUID, ...] = Field(min_length=1, max_length=MAX_BATCH)
    projection: tuple[Literal[*_FIELDS], ...] = _FIELDS

    @model_validator(mode="after")
    def validate_projection_and_ids(self) -> TaskInspectBatch:
        if not self.projection or len(set(self.projection)) != len(self.projection):
            raise ValueError("task_inspect_projection_invalid")
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("task_inspect_duplicate_ids")
        return self


def _filter_query(query: Any, filters: TaskFilter) -> Any:
    query = query.where(Task.deleted_at.is_(None), Task.is_private == false())
    if filters.status is not None:
        query = query.where(Task.status == filters.status)
    if filters.priority is not None:
        query = query.where(Task.priority == filters.priority)
    if filters.due_from is not None:
        start = datetime.combine(filters.due_from, time.min, tzinfo=_OWNER_TIMEZONE).astimezone(UTC)
        query = query.where(or_(Task.due_on >= filters.due_from, Task.due_at >= start))
    if filters.due_through is not None:
        if filters.due_through == date.max:
            query = query.where(or_(Task.due_on <= filters.due_through, Task.due_at.is_not(None)))
        else:
            end = datetime.combine(
                filters.due_through + timedelta(days=1), time.min, tzinfo=_OWNER_TIMEZONE
            ).astimezone(UTC)
            query = query.where(or_(Task.due_on <= filters.due_through, Task.due_at < end))
    if filters.title_contains is not None:
        escaped = (
            filters.title_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        query = query.where(Task.title.ilike(f"%{escaped}%", escape="\\"))
    return query


def _query_hash(request: TaskQuery) -> str:
    body = request.model_dump(mode="json", exclude={"cursor"})
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cursor_key() -> bytes:
    """Derive a domain-separated MAC key; never expose the app master key."""

    raw = get_settings().encryption_master_key
    try:
        master = urlsafe_b64decode(raw) if raw else b""
    except (TypeError, ValueError) as error:
        raise RuntimeError("mimi_cursor_key_unavailable") from error
    if len(master) != 32:
        raise RuntimeError("mimi_cursor_key_unavailable")
    return hmac.digest(master, b"microsched.mimi.task-cursor.v1", "sha256")


def _encode_cursor(request: TaskQuery, row: Task) -> str:
    payload = {
        "query_sha256": _query_hash(request),
        "updated_at": row.updated_at.isoformat(),
        "id": str(row.id),
    }
    body = (
        urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    )
    signature = hmac.new(_cursor_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _decode_cursor(request: TaskQuery) -> tuple[datetime, UUID] | None:
    if request.cursor is None:
        return None
    try:
        body, signature = request.cursor.rsplit(".", 1)
        if not hmac.compare_digest(
            hmac.new(_cursor_key(), body.encode("ascii"), hashlib.sha256).hexdigest(), signature
        ):
            raise ValueError("cursor_signature_invalid")
        raw = urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if len(raw) > 500:
            raise ValueError("cursor_too_large")
        payload = json.loads(raw)
        if payload["query_sha256"] != _query_hash(request):
            raise ValueError("cursor_query_mismatch")
        updated_at = datetime.fromisoformat(payload["updated_at"])
        if updated_at.tzinfo is None:
            raise ValueError("cursor_timezone_missing")
        return updated_at, UUID(payload["id"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, UnicodeEncodeError) as error:
        raise ValueError("invalid_task_query_cursor") from error


def _project(row: Task, projection: tuple[str, ...]) -> dict[str, Any]:
    # Identity and version are mandatory provenance even when the requested
    # display projection is narrower; confirmation can then bind every row.
    data: dict[str, Any] = {"id": str(row.id)}
    for field in projection:
        value = getattr(row, field)
        data[field] = (
            value.isoformat()
            if isinstance(value, (date, datetime))
            else str(value)
            if isinstance(value, UUID)
            else value
        )
    data["source_version"] = row.updated_at.isoformat() if row.updated_at else "unavailable"
    return data


async def query_tasks(db: AsyncSession, request: TaskQuery) -> dict[str, Any]:
    """Fetch a keyset page; report partial coverage rather than claim a full set."""

    cursor = _decode_cursor(request)
    query = _filter_query(select(Task), request.filter)
    if cursor is not None:
        last_at, last_id = cursor
        query = query.where(
            or_(Task.updated_at < last_at, and_(Task.updated_at == last_at, Task.id < last_id))
        )
    rows = (
        (
            await db.execute(
                query.order_by(Task.updated_at.desc(), Task.id.desc()).limit(request.limit + 1)
            )
        )
        .scalars()
        .all()
    )
    selected = rows[: request.limit]
    more = len(rows) > request.limit
    return {
        "rows": [_project(row, request.projection) for row in selected],
        "count": len(selected),
        "coverage": "partial" if more else "complete",
        "next_cursor": _encode_cursor(request, selected[-1]) if more and selected else None,
        "omitted_fields": sorted(set(_FIELDS) - set(request.projection) - {"id"}),
        "data_as_of": datetime.now(UTC).isoformat(),
        "source": "microsched.task.standard.v1",
    }


async def aggregate_tasks(db: AsyncSession, request: TaskAggregate) -> dict[str, Any]:
    column = getattr(Task, request.group_by)
    rows = (
        await db.execute(
            _filter_query(select(column, func.count(Task.id)).group_by(column), request.filter)
        )
    ).all()
    return {
        "group_by": request.group_by,
        "groups": [{"value": value, "count": count} for value, count in rows],
        "coverage": "complete",
        "data_as_of": datetime.now(UTC).isoformat(),
        "source": "microsched.task.standard.v1",
    }


async def inspect_tasks(db: AsyncSession, request: TaskInspectBatch) -> dict[str, Any]:
    ids = set(request.ids)
    rows = (
        (
            await db.execute(
                select(Task).where(
                    Task.id.in_(ids), Task.deleted_at.is_(None), Task.is_private == false()
                )
            )
        )
        .scalars()
        .all()
    )
    found = {row.id: row for row in rows}
    return {
        "rows": [
            _project(found[item], request.projection) for item in request.ids if item in found
        ],
        "missing_ids": [str(item) for item in request.ids if item not in found],
        "coverage": "complete",
        "omitted_fields": sorted(set(_FIELDS) - set(request.projection) - {"id"}),
        "data_as_of": datetime.now(UTC).isoformat(),
        "source": "microsched.task.standard.v1",
    }
