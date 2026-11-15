"""Typed, provider-independent Calendar tool dispatch for authenticated STANDARD callers."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.task_reads import _cursor_key
from app.core.settings import Settings
from app.domain.calendar_read import (
    KINDS,
    CalendarInspectRequest,
    CalendarInspectResult,
    CalendarKind,
    CalendarReadRequest,
    CalendarReadResult,
    CalendarVersion,
    calendar_versions,
    inspect_calendar,
    read_calendar_page,
)

CALENDAR_READ_TOOL = "calendar.read.v1"
CALENDAR_INSPECT_TOOL = "calendar.inspect.v1"
CALENDAR_READ_MODELS = {
    CALENDAR_READ_TOOL: CalendarReadRequest,
    CALENDAR_INSPECT_TOOL: CalendarInspectRequest,
}
CALENDAR_READ_TOOLS = frozenset(CALENDAR_READ_MODELS)
CALENDAR_SOURCE_TYPE = "microsched.calendar.standard"
CalendarBindings = dict[tuple[CalendarKind, UUID], CalendarVersion]


class CalendarCursorError(BaseModel):
    code: Literal["invalid_calendar_cursor"] = "invalid_calendar_cursor"
    message: str = (
        "No Calendar data was read. Use the returned cursor with the same dates and kinds, "
        "or omit it to start a fresh query. This result cannot prove absence or completeness."
    )


class CalendarReadUnavailable(BaseModel):
    schema_version: Literal["calendar.read.v1"] = "calendar.read.v1"
    error: CalendarCursorError = CalendarCursorError()
    coverage: Literal["unavailable"] = "unavailable"
    rows: tuple[()] = ()


def _query_digest(request: CalendarReadRequest) -> str:
    return hashlib.sha256(
        json.dumps(
            [[day.isoformat() for day in request.days()], sorted(request.kinds)],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _sign(settings: Settings, request: CalendarReadRequest, position: str) -> str:
    key = _cursor_key(b"microsched.mimi.calendar-cursor.v1", settings=settings)
    bound_position = f"{_query_digest(request)}:{position}".encode()
    return hmac.new(key, bound_position, hashlib.sha256).hexdigest()


def _read_cursor(
    settings: Settings, request: CalendarReadRequest
) -> tuple[CalendarKind, UUID] | None:
    if request.cursor is None:
        return None
    try:
        kind, raw_id, signature = request.cursor.split(":")
        position = f"{kind}:{raw_id}"
        if kind not in request.kinds or not hmac.compare_digest(
            _sign(settings, request, position), signature
        ):
            raise ValueError
        return kind, UUID(raw_id)
    except ValueError:
        raise ValueError("invalid_calendar_cursor") from None


async def execute_calendar_read(
    db: AsyncSession,
    request: CalendarReadRequest | CalendarInspectRequest,
    *,
    settings: Settings,
) -> CalendarReadResult | CalendarInspectResult | CalendarReadUnavailable:
    """Call after the transport authenticates and leases this STANDARD read."""
    if not settings.mimi_calendar_read_enabled:
        raise ValueError("mimi_calendar_read_disabled")
    if isinstance(request, CalendarInspectRequest):
        return await inspect_calendar(db, request)
    try:
        after = _read_cursor(settings, request)
    except ValueError:
        return CalendarReadUnavailable()
    rows, has_more = await read_calendar_page(db, request, after=after)
    next_cursor = None
    if has_more:
        last = rows[-1]
        position = f"{last.kind}:{last.id}"
        next_cursor = f"{position}:{_sign(settings, request, position)}"
    return CalendarReadResult(
        requested_dates=request.days(),
        kinds=tuple(kind for kind in KINDS if kind in request.kinds),
        rows=rows,
        count=len(rows),
        # A live keyset continuation can skip inserted/newly-visible rows before
        # its cursor. Exhausting that suffix never certifies the whole range.
        coverage="partial" if has_more or request.cursor is not None else "complete",
        has_more=has_more,
        continued=request.cursor is not None,
        next_cursor=next_cursor,
        data_as_of=datetime.now(UTC),
    )


async def execute_calendar_tool(
    db: AsyncSession, name: str, arguments: dict[str, Any], *, settings: Settings
) -> dict[str, Any]:
    """Validate an allowlisted Calendar tool call and serialize the typed result."""
    model = CALENDAR_READ_MODELS.get(name)
    if model is None:
        raise ValueError("mimi_tool_not_read_only")
    try:
        request = model.model_validate(arguments)
    except ValidationError as error:
        raise ValueError("mimi_tool_arguments_invalid") from error
    return (await execute_calendar_read(db, request, settings=settings)).model_dump(mode="json")


def calendar_result_bindings(name: str, result: dict[str, Any]) -> CalendarBindings:
    """Only identity and versions of emitted rows, never requested range or prose."""
    if name not in CALENDAR_READ_TOOLS or "error" in result:
        return {}
    model = CalendarReadResult if name == CALENDAR_READ_TOOL else CalendarInspectResult
    return {
        (row.kind, row.id): (
            row.source_version,
            (row.source.id, row.source.source_version) if row.kind == "event" else None,
        )
        for row in model.model_validate(result).rows
    }


async def calendar_bindings_current(
    db: AsyncSession, bindings: CalendarBindings, *, lock: bool = False
) -> bool:
    """Recheck emitted rows only, never range completeness or snapshot stability."""
    expected: dict[CalendarKind, dict[UUID, CalendarVersion]] = {}
    for (kind, row_id), version in bindings.items():
        expected.setdefault(kind, {})[row_id] = version
    for kind in KINDS:
        if (versions := expected.get(kind)) and await calendar_versions(
            db, kind, set(versions), lock=lock
        ) != versions:
            return False
    return True


async def calendar_pairs_current(db: AsyncSession, pairs: list[list[dict[str, Any]]]) -> bool:
    expected: CalendarBindings = {}
    for assistant, result_message in pairs:
        name = assistant["tool_calls"][0]["function"]["name"]
        if name not in CALENDAR_READ_TOOLS:
            continue
        for key, version in calendar_result_bindings(
            name, json.loads(result_message["content"])
        ).items():
            if expected.setdefault(key, version) != version:
                return False
    return await calendar_bindings_current(db, expected)
