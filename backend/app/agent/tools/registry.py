"""Versioned, validated provider-facing Mimi tool registry."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.task_reads import (
    TaskAggregate,
    TaskInspectBatch,
    TaskQuery,
    aggregate_tasks,
    inspect_tasks,
    query_tasks,
)

READ_TOOLS = frozenset({"task.query.v1", "task.aggregate.v1", "task.inspect_batch.v1"})
CREATE_CANDIDATE_TOOL = "task.create_candidate.v2"

_FILTER = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "priority", "due_from", "due_through", "title_contains"],
    "properties": {
        "status": {"type": ["string", "null"], "enum": ["open", "completed", None]},
        "priority": {"type": ["string", "null"], "enum": ["p1", "p2", "p3", None]},
        "due_from": {"type": ["string", "null"], "format": "date"},
        "due_through": {"type": ["string", "null"], "format": "date"},
        "title_contains": {"type": ["string", "null"], "minLength": 2, "maxLength": 120},
    },
}
_PROJECTION = {
    "type": "array",
    "minItems": 1,
    "maxItems": 7,
    "uniqueItems": True,
    "items": {
        "type": "string",
        "enum": ["id", "title", "status", "priority", "due_precision", "due_on", "due_at"],
    },
}
_TASK_CANDIDATE = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "title",
        "body_md",
        "status",
        "priority",
        "due_precision",
        "due_on",
        "due_at",
        "is_private",
        "items",
    ],
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "body_md": {"type": ["string", "null"], "maxLength": 20_000},
        "status": {"const": "open"},
        "priority": {"type": ["string", "null"], "enum": ["p1", "p2", "p3", None]},
        "due_precision": {"enum": ["none", "date", "datetime"]},
        "due_on": {"type": ["string", "null"], "format": "date"},
        "due_at": {"type": ["string", "null"], "format": "date-time"},
        "is_private": {"const": False},
        "items": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
        },
    },
}


def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": parameters,
        },
    }


TOOLS: tuple[dict[str, Any], ...] = (
    _tool(
        "task.query.v1",
        "Read a bounded page of authorized STANDARD Tasks. "
        "Use the cursor until coverage is complete.",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["filter", "projection", "sort", "limit", "cursor"],
            "properties": {
                "filter": _FILTER,
                "projection": _PROJECTION,
                "sort": {"const": "updated_desc"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "cursor": {"type": ["string", "null"], "maxLength": 1000},
            },
        },
    ),
    _tool(
        "task.aggregate.v1",
        "Count authorized STANDARD Tasks by one declared facet after an explicit filter.",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["filter", "group_by"],
            "properties": {
                "filter": _FILTER,
                "group_by": {"type": "string", "enum": ["status", "priority", "due_precision"]},
            },
        },
    ),
    _tool(
        "task.inspect_batch.v1",
        "Read up to 50 authorized STANDARD Task IDs in one call, including missing IDs.",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["ids", "projection"],
            "properties": {
                "ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {"type": "string", "format": "uuid"},
                },
                "projection": _PROJECTION,
            },
        },
    ),
    _tool(
        CREATE_CANDIDATE_TOOL,
        "Propose one STANDARD Task create. This never writes; "
        "the server freezes a preview for Owner confirmation.",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["task"],
            "properties": {"task": _TASK_CANDIDATE},
        },
    ),
)

REGISTRY_SHA256 = hashlib.sha256(
    json.dumps(TOOLS, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()


async def execute_read_tool(
    db: AsyncSession, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Only the allowlisted read registry can execute automatically."""

    if name not in READ_TOOLS:
        raise ValueError("mimi_tool_not_read_only")
    try:
        if name == "task.query.v1":
            return await query_tasks(db, TaskQuery.model_validate(arguments))
        if name == "task.aggregate.v1":
            return await aggregate_tasks(db, TaskAggregate.model_validate(arguments))
        return await inspect_tasks(db, TaskInspectBatch.model_validate(arguments))
    except ValidationError as error:
        raise ValueError("mimi_tool_arguments_invalid") from error
