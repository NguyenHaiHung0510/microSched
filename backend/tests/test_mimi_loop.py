"""No-network tests for Mimi terminal parsing and bounded read orchestration."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.context import TERMINAL_ADAPTER, AssistantText, Blocked, ToolRequest, ToolRequests
from app.agent.loop import LoopLimits, run_read_loop
from app.agent.openrouter import AgentCompletion, RouteContractError


def _completion(outcome):
    return AgentCompletion(
        outcome=outcome,
        response_id="synthetic-response",
        usage={},
        provider=None,
        model=None,
    )


def _limits(*, turns: int = 4, calls: int = 4, deadline=None, max_bytes: int = 50_000):
    return LoopLimits(
        max_turns=turns,
        max_tool_calls=calls,
        max_serialized_bytes=max_bytes,
        deadline=deadline or datetime.now(UTC) + timedelta(seconds=10),
    )


def test_terminal_union_parses_read_request_and_rejects_unknown_shape() -> None:
    parsed = TERMINAL_ADAPTER.validate_python(
        {
            "kind": "tool_requests",
            "requests": [
                {"call_id": "c1", "name": "task.query.v1", "arguments": {"status": "open"}}
            ],
        }
    )
    assert isinstance(parsed, ToolRequests)
    assert parsed.requests[0].name == "task.query.v1"
    with pytest.raises(Exception):
        TERMINAL_ADAPTER.validate_python({"kind": "pretend_write_succeeded", "text": "done"})


def test_read_loop_executes_one_read_then_returns_terminal_answer() -> None:
    async def scenario() -> None:
        model_calls = []
        reads = []
        updates = []
        responses = [
            _completion(
                ToolRequests(
                    requests=(
                        ToolRequest(call_id="read-1", name="task.query.v1", arguments={"page": 1}),
                    )
                )
            ),
            _completion(AssistantText(text="Có 3 việc đang mở.")),
        ]

        async def invoke(messages, turn):
            model_calls.append((turn, len(messages)))
            return responses.pop(0)

        async def execute(name, arguments):
            reads.append((name, arguments))
            return {"count": 3, "coverage": "complete"}

        async def update(
            messages, name, call_id, arguments, result, remaining_turns, remaining_calls
        ):
            updates.append((name, call_id, remaining_turns, remaining_calls))
            return messages

        result = await run_read_loop(
            [{"role": "system", "content": "policy"}],
            limits=_limits(),
            invoke_model=invoke,
            execute_read=execute,
            on_context_update=update,
        )
        assert result.outcome.text == "Có 3 việc đang mở."
        assert result.turns == 2
        assert result.tool_calls == 1
        assert len(model_calls) == 2
        assert reads == [("task.query.v1", {"page": 1})]
        assert updates == [("task.query.v1", "read-1", 3, 3)]
        assert len(result.messages) == 3

    asyncio.run(scenario())


def test_read_loop_stops_repeated_equivalent_tool_call_without_second_read() -> None:
    async def scenario() -> None:
        request = ToolRequests(
            requests=(
                ToolRequest(call_id="same", name="task.query.v1", arguments={"status": "open"}),
            )
        )
        responses = [
            _completion(request),
            _completion(request),
            _completion(AssistantText(text="wrong")),
        ]
        reads = 0

        async def invoke(messages, turn):
            return responses.pop(0)

        async def execute(name, arguments):
            nonlocal reads
            reads += 1
            return {"rows": []}

        result = await run_read_loop(
            [], limits=_limits(), invoke_model=invoke, execute_read=execute
        )
        assert isinstance(result.outcome, Blocked)
        assert "lặp lại" in result.outcome.reason
        assert result.stop_code == "no_progress"
        assert result.turns == 2
        assert result.tool_calls == 1
        assert reads == 1

    asyncio.run(scenario())


def test_read_loop_enforces_deadline_tool_limit_and_input_byte_limit() -> None:
    async def scenario() -> None:
        calls = 0
        reads = 0

        async def invoke(messages, turn):
            nonlocal calls
            calls += 1
            return _completion(AssistantText(text="ok"))

        async def execute(name, arguments):
            nonlocal reads
            reads += 1
            return {}

        expired = await run_read_loop(
            [],
            limits=_limits(deadline=datetime.now(UTC) - timedelta(seconds=1)),
            invoke_model=invoke,
            execute_read=execute,
        )
        assert isinstance(expired.outcome, Blocked)
        assert expired.stop_code == "deadline_exceeded"
        assert expired.turns == 0
        assert calls == 0

        too_large = await run_read_loop(
            [{"role": "user", "content": "x" * 1000}],
            limits=_limits(max_bytes=10),
            invoke_model=invoke,
            execute_read=execute,
        )
        assert isinstance(too_large.outcome, Blocked)
        assert too_large.stop_code == "budget_exceeded"
        assert "Ngữ cảnh vượt" in too_large.outcome.reason
        assert calls == 0

        over_budget = await run_read_loop(
            [],
            limits=_limits(calls=1),
            invoke_model=lambda messages, turn: _async_value(
                _completion(
                    ToolRequests(
                        requests=(
                            ToolRequest(call_id="a", name="task.query.v1", arguments={"a": 1}),
                            ToolRequest(call_id="b", name="task.query.v1", arguments={"b": 2}),
                        )
                    )
                )
            ),
            execute_read=execute,
        )
        assert isinstance(over_budget.outcome, Blocked)
        assert over_budget.stop_code == "budget_exceeded"
        assert "hết số lần đọc" in over_budget.outcome.reason
        assert over_budget.tool_calls == 0
        assert reads == 0

    asyncio.run(scenario())


async def _async_value(value):
    return value


def test_read_loop_refuses_write_tool_even_if_model_requests_it() -> None:
    async def scenario() -> None:
        async def invoke(messages, turn):
            return _completion(
                ToolRequests(
                    requests=(
                        ToolRequest(call_id="w", name="task.create_candidate.v2", arguments={}),
                    )
                )
            )

        async def execute(name, arguments):
            pytest.fail("non-read tool must never execute")

        with pytest.raises(RouteContractError, match="non_read_tool"):
            await run_read_loop([], limits=_limits(), invoke_model=invoke, execute_read=execute)

    asyncio.run(scenario())
