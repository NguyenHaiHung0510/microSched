"""Offline proof that only a known Task query cursor error is recoverable."""

import asyncio
import base64
import copy
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.context import ToolRequest, ToolRequests
from app.agent.langgraph_runner import run_langgraph
from app.agent.loop import LoopLimits, run_read_loop
from app.agent.openrouter import AgentCompletion
from app.agent.selection import SelectionCandidate, bind_selection
from app.agent.tools import registry
from app.agent.tools.task_reads import TaskQuery, _encode_cursor
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task


@pytest.fixture
def cursor_arguments(monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(b"s" * 32).decode())
    get_settings.cache_clear()
    query = TaskQuery(limit=1)
    row = Task(id=uuid4(), title="Synthetic cursor source", updated_at=datetime.now(UTC))
    cursor = _encode_cursor(query, row)
    arguments = query.model_dump(mode="json") | {"cursor": cursor}
    arguments["filter"]["lifecycle"] = "all"
    yield arguments
    get_settings.cache_clear()


def test_exact_cursor_error_returns_no_data_or_authority(cursor_arguments):
    db = AsyncMock()
    before = copy.deepcopy(cursor_arguments)
    result = asyncio.run(registry.execute_read_tool(db, "task.query.v1", cursor_arguments))
    assert result["error"]["code"] == "invalid_task_query_cursor"
    assert result["coverage"] == "unavailable" and result["rows"] == []
    assert set(result) == {"error", "coverage", "rows"}
    assert len(json.dumps(result)) < 1000
    assert cursor_arguments == before
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "name,arguments,error",
    [
        ("task.query.v1", {}, ValueError("mimi_cursor_key_unavailable")),
        ("task.query.v1", {}, RuntimeError("database unavailable")),
        ("task.query.v1", {}, ValueError("private_read_forbidden")),
        ("task.query.v1", {}, ValueError("invalid_task_query_cursor", "extra")),
        ("task.aggregate.v1", {"group_by": "status"}, ValueError("invalid_task_query_cursor")),
    ],
)
def test_other_errors_are_not_recoverable(monkeypatch, name, arguments, error):
    reader = AsyncMock(side_effect=error)
    monkeypatch.setattr(registry, "query_tasks", reader)
    monkeypatch.setattr(registry, "aggregate_tasks", reader)
    invoke = AsyncMock(
        return_value=AgentCompletion(
            outcome=ToolRequests(
                requests=(ToolRequest(call_id="halt", name=name, arguments=arguments),)
            ),
            response_id="synthetic-halt",
            usage={},
            provider="Synthetic",
            model="synthetic",
        )
    )

    async def execute(tool, args):
        return await registry.execute_read_tool(AsyncMock(), tool, args)

    with pytest.raises(type(error)) as raised:
        asyncio.run(
            run_read_loop(
                [],
                limits=LoopLimits(4, 3, 100_000, datetime.now(UTC) + timedelta(seconds=10)),
                invoke_model=invoke,
                execute_read=execute,
            )
        )
    assert raised.value is error
    invoke.assert_awaited_once()


@pytest.mark.parametrize("runner", ["current", "langgraph"])
def test_repeated_bad_cursor_is_bounded_by_existing_fingerprint(cursor_arguments, runner):
    turns = []
    db = AsyncMock()

    async def invoke(messages, turn):
        turns.append(turn)
        if turn == 2:
            assert json.loads(messages[-1]["content"])["error"]["code"] == (
                "invalid_task_query_cursor"
            )
        return AgentCompletion(
            outcome=ToolRequests(
                requests=(
                    ToolRequest(
                        call_id=f"read-{turn}", name="task.query.v1", arguments=cursor_arguments
                    ),
                )
            ),
            response_id=f"synthetic-{turn}",
            usage={},
            provider="Synthetic",
            model="synthetic",
        )

    async def execute(name, arguments):
        return await registry.execute_read_tool(db, name, arguments)

    common = dict(
        limits=LoopLimits(4, 3, 100_000, datetime.now(UTC) + timedelta(seconds=10)),
        invoke_model=invoke,
        execute_read=execute,
    )
    if runner == "current":
        result = asyncio.run(run_read_loop([], **common))
    else:
        result = asyncio.run(
            run_langgraph(
                [],
                **common,
                run_id=uuid4(),
                generation=1,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=InMemorySaver(),
            ),
            loop_factory=selector_loop_factory,
        )
    assert result.stop_code == "no_progress" and result.tool_calls == 3
    assert turns == [1, 2, 3]
    db.execute.assert_not_awaited()


def test_error_receipt_cannot_close_selection_page_obligation(cursor_arguments):
    tid = uuid4()
    candidate = SelectionCandidate.model_validate(
        {
            "intent": "Synthetic subset",
            "variants_considered": ["synthetic"],
            "variants_pending": [],
            "explicitly_named_subset": True,
            "members": [{"id": str(tid), "classification": "included", "reason": "Synthetic"}],
        }
    )
    query = TaskQuery(limit=1).model_dump(mode="json")
    cursor = cursor_arguments["cursor"]
    receipts = [
        {
            "event_id": "first",
            "tool": "task.query.v1",
            "arguments": query,
            "result": {
                "rows": [
                    {
                        "id": str(tid),
                        "collection_version": 1,
                        "source_version": datetime.now(UTC).isoformat(),
                    }
                ],
                "coverage": "partial",
                "next_cursor": cursor,
            },
        }
    ]
    error = asyncio.run(registry.execute_read_tool(AsyncMock(), "task.query.v1", cursor_arguments))
    # Even an error with the exact pending cursor must not discharge its obligation.
    receipts.append(
        {
            "event_id": "failed",
            "tool": "task.query.v1",
            "arguments": query | {"cursor": cursor},
            "result": error,
        }
    )
    frozen = bind_selection(candidate, receipts)
    assert not frozen["query_complete"] and not frozen["semantic_complete"]
    assert frozen["queries"][0]["open_cursors"] == [cursor]
    assert frozen["queries"][0]["pages"] == ["first"]
