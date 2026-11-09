"""Small egress contracts, without provider/database access."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agent.compaction import active_constraint_context
from app.agent.service import _compaction_messages
from app.agent.working_context import (
    checkpoint_for_egress,
    preview_sources_current,
    read_requirements,
)


def pair(tool, arguments, result):
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "synthetic",
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps(arguments)},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "synthetic", "content": json.dumps(result)},
    ]


@pytest.mark.parametrize("count", [0, 1])
@pytest.mark.parametrize("mixed", [False, True])
def test_historical_aggregate_is_opaque_even_mixed_with_recheckable_rows(count, mixed):
    pairs = [
        pair(
            "task.aggregate.v1",
            {"group_by": "status"},
            {"groups": [{"value": "open", "count": count}]},
        )
    ]
    if mixed:
        pairs.append(pair("task.query.v1", {}, {"rows": [{"id": str(uuid4())}]}))
    with pytest.raises(ValueError, match="unrecheckable_aggregate"):
        read_requirements(pairs)
    read_requirements(pairs, historical=False)  # immediate current-run read remains usable


@pytest.mark.parametrize(
    "tool,args",
    [
        ("task.read_content.v1", {"include_deleted": True}),
        ("task.query.v1", {"filter": {"lifecycle": "all"}}),
        ("task.query.v1", {"filter": {"lifecycle": "deleted"}}),
    ],
)
def test_explicit_deleted_snapshot_keeps_scope_but_former_active_snapshot_does_not(tool, args):
    identity = str(uuid4())
    result = {"rows": [{"id": identity, "deleted_at": "2026-10-29T00:00:00+07:00"}]}
    assert read_requirements([pair(tool, args, result)]) == ({identity}, set())
    if args.get("filter", {}).get("lifecycle") != "deleted":
        result["rows"][0]["deleted_at"] = None
        assert read_requirements([pair(tool, args, result)]) == ({identity}, {identity})


def test_withheld_checkpoint_cannot_reintroduce_derived_constraint_text_to_helper_or_main():
    marker = "synthetic-sensitive-derived-marker"
    checkpoint = {
        "frontier": 3,
        "summary_kind": "semantic_model",
        "summary": marker,
        "constraint_ledger": [{"status": "active", "text": marker}],
        "decisions": [marker],
        "unresolved": [marker],
        "working_sources": [{"event_id": "old"}],
    }
    safe = checkpoint_for_egress(checkpoint, False)
    assert marker not in json.dumps(active_constraint_context(safe))
    assert marker not in json.dumps(
        _compaction_messages(checkpoint, [], prior_working_allowed=False)
    )
    assert safe["working_sources"] == [] and checkpoint["summary"] == marker


def test_pure_create_has_no_existing_source_eligibility_requirement():
    db = AsyncMock()
    operation = {
        "tool": "task.collection.v1",
        "args": {
            "entries": [
                {
                    "id": str(uuid4()),
                    "before": None,
                    "command": {"action": "create", "fields": {"title": "Undated"}},
                }
            ]
        },
    }
    assert asyncio.run(preview_sources_current(db, [operation], {}))
    db.execute.assert_not_awaited()
