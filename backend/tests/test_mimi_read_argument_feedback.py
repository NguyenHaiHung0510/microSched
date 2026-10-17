"""No-egress argument repair, whole-batch safety and evidence exclusion."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_mimi_context import _context

from app.agent.context import AssistantText, PreviewCandidate, ToolRequest, ToolRequests
from app.agent.context_builder import rebind_after_read
from app.agent.langgraph_runner import run_langgraph
from app.agent.loop import LoopLimits, messages_final_only, run_read_loop
from app.agent.openrouter import AgentCompletion, RouteContractError
from app.agent.selection import SELECTION_TOOL, SelectionCandidate, bind_selection
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL, CollectionCandidate
from app.agent.tools import registry
from app.core.qa_event_loop import selector_loop_factory


def completion(outcome):
    return AgentCompletion(
        outcome=outcome, response_id="synthetic-repair", usage={}, provider="Synthetic", model=None
    )


def request(name, arguments, call_id="synthetic-call"):
    return ToolRequest(call_id=call_id, name=name, arguments=arguments)


@pytest.fixture(params=["current", "langgraph"])
def run_runner(request):
    def run(invoke, execute, *, turns=5, calls=8, update=None):
        common = dict(
            limits=LoopLimits(turns, calls, 100_000, datetime.now(UTC) + timedelta(seconds=10)),
            invoke_model=invoke,
            execute_read=execute,
            on_context_update=update,
        )
        if request.param == "current":
            coroutine = run_read_loop([], **common)
        else:
            coroutine = run_langgraph(
                [],
                **common,
                run_id=uuid4(),
                generation=1,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=InMemorySaver(),
            )
        return asyncio.run(coroutine, loop_factory=selector_loop_factory)

    return run


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("task.query.v1", {"limit": 51}),
        ("task.aggregate.v1", {"group_by": "unrecognized"}),
        ("task.inspect_batch.v1", {"ids": []}),
        ("task.read_content.v1", {"id": "invalid-uuid"}),
        (SELECTION_TOOL, {"intent": "Synthetic edit", "variants_considered": ["synthetic"]}),
    ],
)
def test_invalid_read_schema_feedback_is_generic_bounded_and_not_a_read(
    run_runner, name, arguments
):
    marker = "synthetic-sensitive-input-do-not-echo"
    arguments = arguments | {marker: marker * 100}
    original = copy.deepcopy(arguments)
    execute, update = AsyncMock(), AsyncMock()
    seen = []

    async def invoke(messages, turn):
        seen.append(turn)
        if turn == 1:
            return completion(ToolRequests(requests=(request(name, arguments),)))
        feedback = json.loads(messages[-1]["content"])
        assert feedback["error"]["code"] == "invalid_read_arguments"
        assert feedback["invalid_tools"] == [name]
        assert feedback["coverage"] == "unavailable"
        assert set(feedback) == {"error", "invalid_tools", "coverage"}
        assert len(messages[-1]["content"]) < 1000
        assert marker not in json.dumps(messages)
        return completion(AssistantText(text="Cần sửa tham số đọc."))

    result = run_runner(invoke, execute, update=update)
    assert result.turns == 2 and result.tool_calls == 0 and seen == [1, 2]
    assert result.stop_code is None and arguments == original
    execute.assert_not_awaited()
    update.assert_not_awaited()


def test_missing_members_then_corrected_batch_reuses_unexecuted_sibling_and_previews(run_runner):
    tid = str(uuid4())
    query_args = {"filter": {"title_contains": "synthetic"}}
    rows = [{"id": tid, "collection_version": 3, "source_version": datetime.now(UTC).isoformat()}]
    receipt = dict(
        event_id="synthetic-query",
        tool="task.query.v1",
        arguments=query_args,
        result={"rows": rows, "next_cursor": None, "coverage": "complete"},
    )
    missing = {"intent": "Synthetic priority edit", "variants_considered": ["synthetic"]}
    fixed = missing | {
        "members": [{"id": tid, "classification": "included", "reason": "Matches request"}]
    }
    sibling = request("task.aggregate.v1", {"group_by": "status"}, "same-unexecuted-sibling")
    reads, turns = [], []
    frozen = None

    async def execute(name, arguments):
        nonlocal frozen
        reads.append(name)
        if name == "task.query.v1":
            return receipt["result"]
        if name == SELECTION_TOOL:
            frozen = bind_selection(SelectionCandidate.model_validate(arguments), [receipt])
            return {"selection": frozen}
        return {"groups": [], "coverage": "complete"}

    async def invoke(messages, turn):
        turns.append(turn)
        if turn == 1:
            outcome = ToolRequests(requests=(request("task.query.v1", query_args),))
        elif turn == 2:
            outcome = ToolRequests(requests=(sibling, request(SELECTION_TOOL, missing)))
        elif turn == 3:
            assert reads == ["task.query.v1"] and frozen is None
            assert json.loads(messages[-1]["content"])["error"]["code"] == "invalid_read_arguments"
            outcome = ToolRequests(requests=(sibling, request(SELECTION_TOOL, fixed)))
        else:
            assert frozen["semantic_complete"]
            candidate = CollectionCandidate.model_validate(
                {
                    "selection_id": frozen["selection_id"],
                    "entries": [
                        {
                            "action": "edit",
                            "id": tid,
                            "expected_collection_version": 3,
                            "fields": {"priority": "p1"},
                        }
                    ],
                }
            )
            outcome = PreviewCandidate(
                tool=COLLECTION_CANDIDATE_TOOL, arguments=candidate.model_dump(mode="json")
            )
        return completion(outcome)

    result = run_runner(invoke, execute)
    assert result.outcome.kind == "preview_candidate" and result.stop_code is None
    assert result.turns == 4 and result.tool_calls == 3 and turns == [1, 2, 3, 4]
    assert reads == ["task.query.v1", "task.aggregate.v1", SELECTION_TOOL]
    assert "members" not in missing


def test_entire_batch_validates_before_any_sql_or_selection(run_runner, monkeypatch):
    db = AsyncMock()
    validate = registry.validate_read_arguments
    checked = []

    def record(name, arguments):
        checked.append(name)
        return validate(name, arguments)

    monkeypatch.setattr("app.agent.loop.validate_read_arguments", record)
    batch = ToolRequests(
        requests=(
            request("task.query.v1", {}),
            request(
                SELECTION_TOOL,
                {
                    "intent": "Synthetic valid selection",
                    "variants_considered": ["synthetic"],
                    "members": [
                        {"id": str(uuid4()), "classification": "included", "reason": "Synthetic"}
                    ],
                },
            ),
            request(SELECTION_TOOL, {"intent": "Synthetic", "variants_considered": ["synthetic"]}),
            request("task.read_content.v1", {"id": "invalid"}),
        )
    )

    async def invoke(messages, turn):
        return completion(batch if turn == 1 else AssistantText(text="Chưa đọc dữ liệu."))

    async def execute(name, arguments):
        if name == SELECTION_TOOL:
            await db.flush()
            pytest.fail("Rejected batch must not persist a valid selection sibling")
        return await registry.execute_read_tool(db, name, arguments)

    result = run_runner(invoke, execute)
    assert checked == [r.name for r in batch.requests]
    assert result.tool_calls == 0
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "name", ["unleased.read.v1", "task.create_candidate.v2", COLLECTION_CANDIDATE_TOOL]
)
def test_unleased_or_write_name_is_fatal_even_after_bad_read_schema(run_runner, name):
    execute = AsyncMock()
    invoke = AsyncMock(
        return_value=completion(
            ToolRequests(
                requests=(
                    request(SELECTION_TOOL, {}),
                    request(name, {}),
                )
            )
        )
    )
    with pytest.raises(RouteContractError, match="model_requested_non_read_tool_in_loop"):
        run_runner(invoke, execute)
    execute.assert_not_awaited()
    invoke.assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("database unavailable"),
        ValueError("private_read_forbidden"),
        ValueError("authentication_failed"),
        ValueError("mimi_cursor_key_unavailable"),
        ValueError("selection_read_receipt_hash_invalid"),
    ],
)
def test_runtime_failures_remain_fatal_without_model_correction(run_runner, error):
    invoke = AsyncMock(
        return_value=completion(ToolRequests(requests=(request("task.query.v1", {}),)))
    )
    execute = AsyncMock(side_effect=error)
    with pytest.raises(type(error)) as raised:
        run_runner(invoke, execute)
    assert raised.value is error
    invoke.assert_awaited_once()


def test_non_schema_validator_failure_is_fatal(run_runner, monkeypatch):
    error = ValueError("synthetic_registry_corruption")

    def fail(*args):
        raise error

    monkeypatch.setattr("app.agent.loop.validate_read_arguments", fail)
    invoke = AsyncMock(
        return_value=completion(ToolRequests(requests=(request("task.query.v1", {}),)))
    )
    execute = AsyncMock()
    with pytest.raises(ValueError) as raised:
        run_runner(invoke, execute)
    assert raised.value is error
    execute.assert_not_awaited()
    invoke.assert_awaited_once()


def test_repeated_invalid_schema_uses_existing_final_turn_bound(run_runner):
    turns = []
    execute = AsyncMock()

    async def invoke(messages, turn):
        turns.append(turn)
        if messages_final_only(messages):
            return completion(AssistantText(text="Đã chạm giới hạn, chưa đọc dữ liệu."))
        return completion(ToolRequests(requests=(request("task.query.v1", {"limit": 51}),)))

    result = run_runner(invoke, execute, turns=3, calls=1)
    assert turns == [1, 2, 3] and result.tool_calls == 0
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    "code", ["invalid_read_arguments", "invalid_task_query_cursor", "future_server_read_error"]
)
def test_all_read_error_results_supply_no_context_source_or_selection_authority(code):
    tid, forged = str(uuid4()), str(uuid4())
    row = {"id": tid, "collection_version": 1, "source_version": datetime.now(UTC).isoformat()}
    args = {"limit": 1}
    first = dict(
        event_id="first",
        tool="task.query.v1",
        arguments=args,
        result={"rows": [row], "next_cursor": "pending", "coverage": "partial"},
    )
    error = {
        "error": {"code": code, "message": "No data read"},
        "rows": [
            row | {"id": forged, "collection_version": 99},
        ],
        "coverage": "complete",
        "next_cursor": None,
        "data_as_of": datetime.now(UTC).isoformat(),
    }
    failed = dict(
        event_id="failed",
        tool="task.query.v1",
        arguments=args | {"cursor": "pending"},
        result=error,
    )

    def candidate(member):
        return SelectionCandidate.model_validate(
            {
                "intent": "Synthetic subset",
                "variants_considered": ["synthetic"],
                "explicitly_named_subset": True,
                "members": [{"id": member, "classification": "included", "reason": "Synthetic"}],
            }
        )

    frozen = bind_selection(candidate(tid), [first, failed])
    assert not frozen["query_complete"] and not frozen["semantic_complete"]
    assert frozen["queries"][0]["open_cursors"] == ["pending"]
    assert frozen["queries"][0]["pages"] == ["first"]
    with pytest.raises(ValueError, match="no_actual_versioned_receipt"):
        bind_selection(candidate(forged), [first, failed])
    envelope, messages = _context()
    updated, _ = rebind_after_read(
        envelope,
        messages,
        tool_name="task.query.v1",
        call_id="failed",
        arguments=args,
        result=error,
        remaining_turns=2,
        remaining_tool_calls=3,
    )
    assert updated.manifest.sources == envelope.manifest.sources
    assert updated.authority.allowed_tools == envelope.authority.allowed_tools
    assert updated.authority.remaining_turns == 2
