"""Synthetic parity/fault contracts for the real LangGraph progression."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

pytest.importorskip("langgraph", reason="install the optional prototype dependency group")

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.context import (
    AssistantText,
    Blocked,
    Clarification,
    Draft,
    PreviewCandidate,
    ToolRequest,
    ToolRequests,
)
from app.agent.langgraph_runner import (
    checkpoint_thread_id,
    run_langgraph,
    validate_checkpoint_values,
)
from app.agent.loop import LoopLimits, run_read_loop
from app.agent.openrouter import AgentCompletion, ProviderDispatchError, RouteContractError
from app.agent.service import _checkpoint_failure_outcome
from app.core.qa_event_loop import selector_loop_factory


def _run(coroutine):
    asyncio.run(coroutine, loop_factory=selector_loop_factory)


def _completion(outcome):
    return AgentCompletion(
        outcome=outcome,
        response_id="synthetic-langgraph",
        usage={},
        provider="Synthetic",
        model="synthetic/no-key",
    )


def _limits(**overrides):
    values = {
        "max_turns": 4,
        "max_tool_calls": 3,
        "max_serialized_bytes": 10_000,
        "deadline": datetime.now(UTC) + timedelta(seconds=5),
    }
    values.update(overrides)
    return LoopLimits(**values)


async def _run_graph(
    responses,
    execute_read,
    *,
    limits=None,
    on_context_update=None,
    saver=None,
    run_id=None,
):
    calls = []

    async def invoke(messages, turn):
        calls.append((turn, len(messages)))
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    saver = saver or InMemorySaver()
    run_id = run_id or uuid4()
    result = await run_langgraph(
        [{"role": "system", "content": "synthetic policy"}],
        limits=limits or _limits(),
        invoke_model=invoke,
        execute_read=execute_read,
        run_id=run_id,
        generation=1,
        policy_sha256="a" * 64,
        tool_registry_sha256="b" * 64,
        output_schema_sha256="c" * 64,
        database_url="",
        on_context_update=on_context_update,
        checkpointer_for_test=saver,
    )
    snapshots = list(saver.list({"configurable": {"thread_id": checkpoint_thread_id(run_id, 1)}}))
    return result, calls, snapshots


def test_langgraph_replaces_loop_and_matches_read_then_terminal_control() -> None:
    async def scenario():
        request = ToolRequests(
            requests=(ToolRequest(call_id="read-1", name="task.query.v1", arguments={"page": 1}),)
        )

        async def control_invoke(messages, turn):
            return _completion(request if turn == 1 else AssistantText(text="Có 3 việc."))

        control = await run_read_loop(
            [{"role": "system", "content": "synthetic policy"}],
            limits=_limits(),
            invoke_model=control_invoke,
            execute_read=lambda name, args: _read_value(),
        )
        graph, calls, snapshots = await _run_graph(
            [_completion(request), _completion(AssistantText(text="Có 3 việc."))],
            lambda name, args: _read_value(),
        )
        assert graph.outcome == control.outcome
        assert graph.turns == control.turns == 2
        assert graph.tool_calls == control.tool_calls == 1
        assert graph.messages == control.messages
        assert [call[0] for call in calls] == [1, 2]
        assert checkpoint_thread_id(uuid4(), 1) != checkpoint_thread_id(uuid4(), 2)
        assert snapshots
        checkpoint_values = [snapshot.checkpoint["channel_values"] for snapshot in snapshots]
        assert all("messages" not in values for values in checkpoint_values)
        assert all("Có 3 việc." not in repr(values) for values in checkpoint_values)

    _run(scenario())


async def _read_value(name=None, arguments=None):
    return {"count": 3, "coverage": "complete"}


def test_langgraph_no_progress_and_write_tool_fail_closed() -> None:
    async def scenario():
        same = _completion(
            ToolRequests(
                requests=(ToolRequest(call_id="same", name="task.query.v1", arguments={"p": 1}),)
            )
        )
        graph, calls, _ = await _run_graph([same, same], lambda name, args: _read_value())
        assert isinstance(graph.outcome, Blocked)
        assert graph.stop_code == "no_progress"
        assert graph.tool_calls == 1
        assert [call[0] for call in calls] == [1, 2]

        async def forbidden_read(name, args):
            pytest.fail("write proposal must not execute through the read node")

        with pytest.raises(Exception, match="non_read_tool"):
            await _run_graph(
                [
                    _completion(
                        ToolRequests(
                            requests=(
                                ToolRequest(
                                    call_id="write",
                                    name="task.create_candidate.v2",
                                    arguments={},
                                ),
                            )
                        )
                    )
                ],
                forbidden_read,
            )

    _run(scenario())


@pytest.mark.parametrize(
    "outcome",
    [
        AssistantText(text="synthetic answer"),
        Clarification(question="synthetic question"),
        Draft(text="synthetic draft"),
        PreviewCandidate(tool="task.create_candidate.v2", arguments={"title": "synthetic"}),
        Blocked(reason="synthetic blocked"),
    ],
)
def test_langgraph_terminal_union_matches_current_control(outcome):
    async def scenario():
        async def invoke(messages, turn):
            return _completion(outcome)

        control = await run_read_loop(
            [],
            limits=_limits(),
            invoke_model=invoke,
            execute_read=lambda name, args: _read_value(),
        )
        graph, calls, _ = await _run_graph([_completion(outcome)], lambda name, args: _read_value())
        assert graph.outcome == control.outcome == outcome
        assert graph.turns == control.turns == 1
        assert graph.tool_calls == control.tool_calls == 0
        assert len(calls) == 1

    _run(scenario())


def test_langgraph_deadline_and_turn_budget_match_current_control():
    async def scenario():
        async def should_not_dispatch(messages, turn):
            pytest.fail("expired deadline must stop before dispatch")

        expired = _limits(deadline=datetime.now(UTC) - timedelta(seconds=1))
        control = await run_read_loop(
            [], limits=expired, invoke_model=should_not_dispatch, execute_read=_read_value
        )
        graph, calls, _ = await _run_graph([], _read_value, limits=expired)
        assert graph.outcome == control.outcome
        assert graph.stop_code == control.stop_code == "deadline_exceeded"
        assert calls == []

        repeated = _completion(
            ToolRequests(
                requests=(ToolRequest(call_id="p", name="task.query.v1", arguments={"p": 1}),)
            )
        )
        control_responses = [repeated, repeated]
        graph_responses = [repeated, repeated]

        async def control_invoke(messages, turn):
            return control_responses.pop(0)

        control = await run_read_loop(
            [],
            limits=_limits(max_turns=1),
            invoke_model=control_invoke,
            execute_read=_read_value,
        )
        graph, calls, _ = await _run_graph(
            graph_responses, _read_value, limits=_limits(max_turns=1)
        )
        assert graph.outcome == control.outcome
        assert graph.stop_code == control.stop_code == "budget_exceeded"
        assert graph.turns == control.turns == 1
        assert graph.tool_calls == control.tool_calls == 1
        assert len(calls) == 1

        two_reads = _completion(
            ToolRequests(
                requests=(
                    ToolRequest(call_id="one", name="task.query.v1", arguments={"p": 1}),
                    ToolRequest(call_id="two", name="task.query.v1", arguments={"p": 2}),
                )
            )
        )

        async def over_tool_budget(messages, turn):
            return two_reads

        tight_calls = _limits(max_tool_calls=1)
        control = await run_read_loop(
            [],
            limits=tight_calls,
            invoke_model=over_tool_budget,
            execute_read=_read_value,
        )
        graph, calls, _ = await _run_graph([two_reads], _read_value, limits=tight_calls)
        assert graph.outcome == control.outcome
        assert graph.stop_code == control.stop_code == "budget_exceeded"
        assert graph.tool_calls == control.tool_calls == 0
        assert len(calls) == 1

        tight_bytes = _limits(max_serialized_bytes=8)
        control = await run_read_loop(
            [{"role": "system", "content": "synthetic policy"}],
            limits=tight_bytes,
            invoke_model=over_tool_budget,
            execute_read=_read_value,
        )
        graph, calls, _ = await _run_graph([], _read_value, limits=tight_bytes)
        assert graph.outcome == control.outcome
        assert graph.stop_code == control.stop_code == "budget_exceeded"
        assert calls == []

    _run(scenario())


def test_langgraph_unknown_model_timeout_is_not_replayed() -> None:
    async def scenario():
        dispatches = 0

        async def invoke(messages, turn):
            nonlocal dispatches
            dispatches += 1
            await asyncio.sleep(1)

        with pytest.raises(ProviderDispatchError) as raised:
            await run_langgraph(
                [],
                limits=_limits(deadline=datetime.now(UTC) + timedelta(milliseconds=20)),
                invoke_model=invoke,
                execute_read=lambda name, args: _read_value(),
                run_id=uuid4(),
                generation=1,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=InMemorySaver(),
            )
        assert raised.value.outcome == "unknown"
        assert dispatches == 1

    _run(scenario())


def test_foreign_checkpoint_identity_and_content_channels_fail_closed() -> None:
    expected = {
        "state_schema_version": 1,
        "runner_version": "mimi-langgraph-v1",
        "run_id": "run-ref",
        "generation": 3,
        "policy_sha256": "a" * 64,
        "tool_registry_sha256": "b" * 64,
        "output_schema_sha256": "c" * 64,
        "step": 0,
        "turn": 0,
        "tool_calls": 0,
        "phase": "model",
    }
    validate_checkpoint_values(expected, expected)
    for field, value in (
        ("state_schema_version", 2),
        ("runner_version", "other-runner"),
        ("run_id", "foreign-run"),
        ("generation", 2),
        ("policy_sha256", "d" * 64),
        ("tool_registry_sha256", "e" * 64),
        ("output_schema_sha256", "f" * 64),
    ):
        foreign = {**expected, field: value}
        with pytest.raises(RuntimeError, match="checkpoint_identity_mismatch"):
            validate_checkpoint_values(foreign, expected)
    with pytest.raises(RuntimeError, match="checkpoint_shape_invalid"):
        validate_checkpoint_values({**expected, "messages": ["plaintext"]}, expected)


def test_checkpoint_failure_preserves_unknown_or_succeeded_journal_outcome():
    refusal = RouteContractError("mimi_langgraph_checkpoint_resume_requires_reconcile")
    assert _checkpoint_failure_outcome(refusal, "dispatched") == "unknown"
    assert _checkpoint_failure_outcome(refusal, "succeeded") == "succeeded"
    assert _checkpoint_failure_outcome(refusal, "intent") is None
    assert _checkpoint_failure_outcome(RouteContractError("other_contract"), "dispatched") is None


def test_existing_checkpoint_blocks_dispatch_before_resume() -> None:
    async def scenario():
        saver = InMemorySaver()
        run_id = uuid4()
        dispatches = 0

        async def invoke(messages, turn):
            nonlocal dispatches
            dispatches += 1
            return _completion(AssistantText(text="synthetic result"))

        async def execute(name, args):
            pytest.fail("existing graph checkpoint must block before tool execution")

        async def invoke_once():
            return await run_langgraph(
                [{"role": "user", "content": "synthetic plaintext must not persist"}],
                limits=_limits(),
                invoke_model=invoke,
                execute_read=execute,
                run_id=run_id,
                generation=9,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=saver,
            )

        await invoke_once()
        assert dispatches == 1
        with pytest.raises(RouteContractError, match="resume_requires_reconcile"):
            await invoke_once()
        assert dispatches == 1

    _run(scenario())


def test_local_qa_selector_loop_factory_is_scoped_and_operational():
    from uvicorn import Config

    # Uvicorn passes a custom dotted callable directly to asyncio.Runner.
    factory = Config(
        "unused:app", loop="app.core.qa_event_loop:selector_loop_factory"
    ).get_loop_factory()
    assert factory is not None
    loop = factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
        assert not isinstance(loop, asyncio.ProactorEventLoop)
    finally:
        loop.close()
