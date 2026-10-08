"""Synthetic parity/fault contracts for the real LangGraph progression."""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
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
from app.agent.graph_support import RestoredFrame
from app.agent.langgraph_runner import (
    _authorized_local_database,
    checkpoint_thread_id,
    run_langgraph,
    validate_checkpoint_values,
)
from app.agent.loop import LoopLimits, messages_final_only, run_read_loop
from app.agent.openrouter import AgentCompletion, ProviderDispatchError, RouteContractError
from app.agent.service import _checkpoint_failure_outcome
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import Settings


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
        "max_serialized_bytes": 100_000,
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
    restore_frame=None,
    terminal_checkpoint_safe=None,
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
        restore_frame=restore_frame,
        terminal_checkpoint_safe=terminal_checkpoint_safe,
    )
    snapshots = list(saver.list({"configurable": {"thread_id": checkpoint_thread_id(run_id, 1)}}))
    return result, calls, snapshots


def test_langgraph_replaces_loop_and_matches_read_then_terminal_control() -> None:
    async def scenario():
        request = ToolRequests(
            requests=(ToolRequest(call_id="read-1", name="task.query.v1", arguments={"limit": 1}),)
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
        assert graph.messages[-2]["content"] is None
        assert graph.messages[-2]["tool_calls"][0]["function"]["arguments"] == '{"limit":1}'
        assert graph.messages[-1]["role"] == "tool"
        assert graph.messages[-1]["tool_call_id"] == "read-1"
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
                requests=(
                    ToolRequest(call_id="same", name="task.query.v1", arguments={"limit": 1}),
                )
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

        final = _completion(AssistantText(text="Partial answer; no further reads."))

        async def final_invoke(messages, turn):
            assert messages_final_only(messages)
            return final

        control = await run_read_loop(
            [], limits=_limits(max_turns=1), invoke_model=final_invoke, execute_read=_read_value
        )
        graph, calls, _ = await _run_graph([final], _read_value, limits=_limits(max_turns=1))
        assert graph.outcome == control.outcome == final.outcome
        assert graph.tool_calls == control.tool_calls == 0
        assert graph.turns == control.turns == 1
        assert len(calls) == 1

        two_reads = _completion(
            ToolRequests(
                requests=(
                    ToolRequest(call_id="one", name="task.query.v1", arguments={"limit": 1}),
                    ToolRequest(call_id="two", name="task.query.v1", arguments={"limit": 2}),
                )
            )
        )

        async def over_tool_budget(messages, turn):
            return two_reads if turn == 1 else final

        tight_calls = _limits(max_tool_calls=1)
        initial = [{"role": "system", "content": "synthetic policy"}]
        control = await run_read_loop(
            initial, limits=tight_calls, invoke_model=over_tool_budget, execute_read=_read_value
        )
        graph, calls, _ = await _run_graph([two_reads, final], _read_value, limits=tight_calls)
        assert graph.outcome == control.outcome == final.outcome
        assert graph.messages == control.messages
        assert graph.tool_calls == control.tool_calls == 1
        assert len(calls) == 2
        assert "not_run_reads" in str(control.messages)

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


def test_restart_after_read_reuses_journaled_result_without_second_read() -> None:
    class SimulatedProcessLoss(Exception):
        pass

    async def scenario():
        saver = InMemorySaver()
        run_id = uuid4()
        request = ToolRequests(
            requests=(
                ToolRequest(call_id="cached-call", name="task.query.v1", arguments={"limit": 1}),
            )
        )
        completion = _completion(request)
        initial_messages = [{"role": "user", "content": "synthetic question"}]
        provider_calls = 0
        read_calls = 0
        cached = {"count": 7, "coverage": "complete"}
        fingerprint = hashlib.sha256(
            json.dumps(
                {"name": "task.query.v1", "arguments": {"limit": 1}},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        async def first_invoke(messages, turn):
            nonlocal provider_calls
            provider_calls += 1
            return completion

        async def first_read(name, arguments):
            nonlocal read_calls
            read_calls += 1
            return cached

        async def interrupt_after_read(*args):
            raise SimulatedProcessLoss()

        with pytest.raises(SimulatedProcessLoss):
            await run_langgraph(
                initial_messages,
                limits=_limits(),
                invoke_model=first_invoke,
                execute_read=first_read,
                run_id=run_id,
                generation=1,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                on_context_update=interrupt_after_read,
                checkpointer_for_test=saver,
            )
        assert read_calls == 1
        config = {"configurable": {"thread_id": checkpoint_thread_id(run_id, 1)}}
        saved = await saver.aget_tuple(config)
        assert saved.checkpoint["channel_values"]["phase"] == "read"

        async def restore(saved_state):
            assert saved_state["phase"] == "read"
            return RestoredFrame(
                messages=tuple(initial_messages),
                last_completion=completion,
                seen_calls=frozenset({fingerprint}),
                read_results={"cached-call": cached},
                read_result_fingerprints={"cached-call": fingerprint},
            )

        async def restarted_invoke(messages, turn):
            nonlocal provider_calls
            provider_calls += 1
            assert turn == 2
            assert "count" in messages[-1]["content"]
            return _completion(AssistantText(text="Đã tìm thấy 7 việc."))

        async def must_not_read(name, arguments):
            pytest.fail("restart must reuse the durable cached tool result")

        result = await run_langgraph(
            initial_messages,
            limits=_limits(),
            invoke_model=restarted_invoke,
            execute_read=must_not_read,
            run_id=run_id,
            generation=1,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            database_url="",
            checkpointer_for_test=saver,
            restore_frame=restore,
        )
        assert result.outcome == AssistantText(text="Đã tìm thấy 7 việc.")
        assert result.tool_calls == 1
        assert read_calls == 1
        assert provider_calls == 2

    _run(scenario())


def test_restart_after_provider_terminal_uses_journal_without_redispatch() -> None:
    class SimulatedProcessLoss(Exception):
        pass

    async def scenario():
        saver = InMemorySaver()
        run_id = uuid4()
        terminal = _completion(AssistantText(text="terminal from app journal"))
        journal = {}
        dispatches = 0

        async def interrupted_provider(messages, turn):
            nonlocal dispatches
            dispatches += 1
            journal["provider_terminal"] = terminal
            raise SimulatedProcessLoss()

        with pytest.raises(SimulatedProcessLoss):
            await run_langgraph(
                [{"role": "user", "content": "synthetic"}],
                limits=_limits(),
                invoke_model=interrupted_provider,
                execute_read=_read_value,
                run_id=run_id,
                generation=4,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=saver,
            )
        saved = await saver.aget_tuple(
            {"configurable": {"thread_id": checkpoint_thread_id(run_id, 4)}}
        )
        assert saved.checkpoint["channel_values"]["phase"] == "model"

        async def restore(saved_state):
            assert saved_state["turn"] == 0
            return RestoredFrame(
                messages=({"role": "user", "content": "synthetic"},),
                pending_completion=journal["provider_terminal"],
            )

        async def restore_unknown(saved_state):
            return RestoredFrame(messages=({"role": "user", "content": "synthetic"},))

        with pytest.raises(ProviderDispatchError) as raised:
            await run_langgraph(
                [{"role": "user", "content": "synthetic"}],
                limits=_limits(),
                invoke_model=lambda messages, turn: pytest.fail("unknown dispatch cannot retry"),
                execute_read=_read_value,
                run_id=run_id,
                generation=4,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=saver,
                restore_frame=restore_unknown,
            )
        assert raised.value.outcome == "unknown"
        assert dispatches == 1

        async def must_not_dispatch(messages, turn):
            nonlocal dispatches
            dispatches += 1
            pytest.fail("provider terminal in the app journal must be replayed")

        result = await run_langgraph(
            [{"role": "user", "content": "synthetic"}],
            limits=_limits(),
            invoke_model=must_not_dispatch,
            execute_read=_read_value,
            run_id=run_id,
            generation=4,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            database_url="",
            checkpointer_for_test=saver,
            restore_frame=restore,
        )
        assert result.outcome == terminal.outcome
        assert dispatches == 1

    _run(scenario())


def test_restart_requires_frozen_policy_and_schema_identity() -> None:
    async def scenario():
        saver = InMemorySaver()
        run_id = uuid4()
        calls = 0

        async def invoke(messages, turn):
            nonlocal calls
            calls += 1
            return _completion(AssistantText(text="durable result"))

        args = dict(
            limits=_limits(),
            invoke_model=invoke,
            execute_read=_read_value,
            run_id=run_id,
            generation=1,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            database_url="",
            checkpointer_for_test=saver,
        )
        await run_langgraph([], **args)
        restore_calls = 0

        async def restore(saved_state):
            nonlocal restore_calls
            restore_calls += 1
            return RestoredFrame(messages=())

        for identity in ("policy_sha256", "tool_registry_sha256", "output_schema_sha256"):
            changed = dict(args)
            changed[identity] = "d" * 64
            with pytest.raises(RouteContractError, match="checkpoint_identity_mismatch"):
                await run_langgraph([], **(changed | {"restore_frame": restore}))
        assert calls == 1
        assert restore_calls == 0

    _run(scenario())


def test_terminal_cleanup_deletes_only_own_graph_thread_after_durable_result() -> None:
    async def scenario():
        saver = InMemorySaver()
        retained_run = uuid4()
        terminal_run = uuid4()

        async def invoke(messages, turn):
            return _completion(AssistantText(text="synthetic terminal"))

        common = dict(
            limits=_limits(),
            invoke_model=invoke,
            execute_read=_read_value,
            generation=2,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            database_url="",
            checkpointer_for_test=saver,
        )
        await run_langgraph([], run_id=retained_run, **common)
        durable_results = []

        async def durable_terminal(run_id, generation, result):
            durable_results.append((run_id, generation, result))
            return True

        await run_langgraph(
            [],
            run_id=terminal_run,
            terminal_checkpoint_safe=durable_terminal,
            **common,
        )
        assert durable_results[0][0:2] == (terminal_run, 2)
        assert (
            await saver.aget_tuple(
                {"configurable": {"thread_id": checkpoint_thread_id(terminal_run, 2)}}
            )
            is None
        )
        assert (
            await saver.aget_tuple(
                {"configurable": {"thread_id": checkpoint_thread_id(retained_run, 2)}}
            )
            is not None
        )

    _run(scenario())


def test_restored_terminal_returns_app_result_and_releases_only_own_thread() -> None:
    async def scenario():
        saver = InMemorySaver()
        run_id = uuid4()

        async def invoke(messages, turn):
            return _completion(AssistantText(text="terminal answer"))

        async def must_not_dispatch(messages, turn):
            pytest.fail("terminal app result must be returned without model dispatch")

        args = dict(
            limits=_limits(),
            execute_read=_read_value,
            run_id=run_id,
            generation=5,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            database_url="",
            checkpointer_for_test=saver,
        )
        first = await run_langgraph([], invoke_model=invoke, **args)
        terminal_thread = checkpoint_thread_id(run_id, 5)
        saved = await saver.aget_tuple({"configurable": {"thread_id": terminal_thread}})
        assert saved.checkpoint["channel_values"]["phase"] == "terminal"

        async def restore(saved_state):
            assert saved_state["phase"] == "terminal"
            return RestoredFrame(messages=(), terminal_result=first)

        async def durable_terminal(restored_run_id, generation, result):
            assert (restored_run_id, generation, result) == (run_id, 5, first)
            return True

        restarted = await run_langgraph(
            [],
            invoke_model=must_not_dispatch,
            restore_frame=restore,
            terminal_checkpoint_safe=durable_terminal,
            **args,
        )
        assert restarted == first
        assert await saver.aget_tuple({"configurable": {"thread_id": terminal_thread}}) is None

    _run(scenario())


def test_langgraph_database_allowlist_is_exact_local_mimi078() -> None:
    from sqlalchemy.engine import make_url

    assert _authorized_local_database(
        make_url("postgresql://u:p@localhost:55478/microsched_mimi078")
    )
    for url in (
        "postgresql://u:p@localhost:55478/microsched_p1ca_066",
        "postgresql://u:p@localhost:55479/microsched_mimi078",
        "postgresql://u:p@example.invalid:55478/microsched_mimi078",
        "postgresql://u:p@localhost:55478/microsched_mimi078_other",
    ):
        assert not _authorized_local_database(make_url(url))


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
        if hasattr(asyncio, "ProactorEventLoop"):
            assert not isinstance(loop, asyncio.ProactorEventLoop)
    finally:
        loop.close()


@pytest.mark.parametrize("runner", ["current", "langgraph"])
@pytest.mark.parametrize("boundary", ["turns", "tools"])
def test_emergency_bounds_stop_before_over_limit_dispatch_or_read(runner, boundary):
    async def scenario():
        settings = Settings(_env_file=None)
        limits = _limits(
            max_turns=settings.mimi_run_max_turns,
            max_tool_calls=settings.mimi_run_max_tool_calls,
            max_serialized_bytes=100_000,
        )
        invocations, reads = [], []

        async def invoke(messages, turn):
            invocations.append(turn)
            if messages_final_only(messages):
                return _completion(
                    AssistantText(text="Honest partial result from completed reads.")
                )
            # Last fitting read executes; omitted reads are reported before finalization.
            count = (2 if turn == 22 else 3) if boundary == "tools" else 1
            return _completion(
                ToolRequests(
                    requests=tuple(
                        ToolRequest(
                            call_id=f"step-{turn}-{index}",
                            name="task.query.v1",
                            arguments={"filter": {"title_contains": f"synthetic-{turn}-{index}"}},
                        )
                        for index in range(count)
                    )
                )
            )

        async def read(name, arguments):
            reads.append(arguments)
            return {"count": 0, "coverage": "complete"}

        common = dict(limits=limits, invoke_model=invoke, execute_read=read)
        if runner == "current":
            result = await run_read_loop([{"role": "system", "content": "synthetic"}], **common)
        else:
            result = await run_langgraph(
                [{"role": "system", "content": "synthetic"}],
                **common,
                run_id=uuid4(),
                generation=1,
                policy_sha256="a" * 64,
                tool_registry_sha256="b" * 64,
                output_schema_sha256="c" * 64,
                database_url="",
                checkpointer_for_test=InMemorySaver(),
            )
        assert result.stop_code is None
        assert isinstance(result.outcome, AssistantText)
        if boundary == "turns":
            assert invocations == list(range(1, 33))
            assert len(reads) == 31
        else:
            assert invocations == list(range(1, 24))
            assert len(reads) == 64
            assert "not_run_reads" in str(result.messages)

    _run(scenario())


@pytest.mark.parametrize("tls_mode", ["require", "verify-full"])
def test_real_saver_handoff_accepts_normalized_production_tls(monkeypatch, tls_mode):
    """The real libpq parser accepts the DSN handed off by the production runner."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.conninfo import conninfo_to_dict

    settings = Settings(
        _env_file=None,
        app_env="production",
        enable_inprocess_cron=False,
        database_url=(
            "postgresql://app_role:fixture-password@example.invalid:5432/appdb"
            f"?sslmode={tls_mode}&application_name=mimi-fixture"
            "&sslrootcert=/synthetic/ca.pem"
        ),
        mimi_real_chat_enabled=True,
        mimi_live_provider_enabled=True,
        mimi_context_v1_enabled=True,
        mimi_runner="langgraph",
        mimi_public_origin="https://app.example.invalid",
        mimi_standard_api_key="synthetic-not-a-key",
        mimi_route_model="synthetic/no-key",
        mimi_route_provider="synthetic",
        mimi_route_quantization="fp8",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
    )
    captured = []

    @asynccontextmanager
    async def saver_factory(dsn):
        # Parsing is real; there is deliberately no DB connection or network.
        captured.append(conninfo_to_dict(dsn))
        yield InMemorySaver()

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", staticmethod(saver_factory))

    async def scenario():
        async def invoke(messages, turn):
            return _completion(AssistantText(text="synthetic terminal"))

        result = await run_langgraph(
            [{"role": "system", "content": "synthetic policy"}],
            limits=_limits(),
            invoke_model=invoke,
            execute_read=_read_value,
            run_id=uuid4(),
            generation=1,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            database_url=settings.database_url,
            deployment_settings=settings,
        )
        assert result.outcome == AssistantText(text="synthetic terminal")

    _run(scenario())
    assert len(captured) == 1
    assert captured[0] == {
        "user": "app_role",
        "password": "fixture-password",
        "host": "example.invalid",
        "port": "5432",
        "dbname": "appdb",
        "sslmode": tls_mode,
        "application_name": "mimi-fixture",
        "sslrootcert": "/synthetic/ca.pem",
    }
