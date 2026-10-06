"""Alpha receipt/admission contracts. All provider receipts are deterministic doubles."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid7

import pytest
from fastapi import HTTPException

from app.agent import runtime
from app.agent.observations import context_revision, prompt_observation, run_costs
from app.agent.openrouter import RouteContractError, build_request
from app.agent.route_config import bind_configuration, profiles_for_ui, validate_configuration
from app.core.settings import Settings


def alpha_settings(**updates):
    values = dict(
        _env_file=None,
        app_env="production",
        oauth_state_secret="synthetic-only",
        mimi_public_origin="https://alpha.example.invalid",
        mimi_real_chat_enabled=True,
        mimi_live_provider_enabled=True,
        mimi_context_v1_enabled=True,
        mimi_standard_api_key="synthetic-only-no-dispatch",
        mimi_transport="openai_sdk",
        mimi_text_response_format="natural",
        mimi_runner="langgraph",
        mimi_route_model="deepseek/deepseek-v4.1-flash",
        mimi_route_provider="deepinfra",
        mimi_route_quantization="fp8",
        mimi_route_reasoning_effort="high",
        mimi_route_max_input_price=0.20,
        mimi_route_max_output_price=0.60,
    )
    return Settings(**(values | updates))


def receipt(**updates):
    values = dict(
        id=uuid7(),
        state="succeeded",
        result={"response_id": str(uuid7())},
        usage={"prompt_tokens": 100_001, "total_tokens": 190_000, "cost": 0.2},
        route={
            "kind": "openrouter",
            "purpose": "main",
            "model": "model",
            "actual_model": "model",
            "providers": ["deepinfra"],
            "actual_provider": "DeepInfra",
            "context_revision": "epoch",
        },
    )
    return SimpleNamespace(**(values | updates))


def test_payload_guard_is_independent_of_token_threshold():
    settings = alpha_settings(mimi_max_payload_bytes=65_536)
    with pytest.raises(RouteContractError, match="payload_bytes_exceeded"):
        build_request([{"role": "user", "content": "x" * 70_000}], settings)
    roomy = alpha_settings()
    for old_limit in (32_000, 100_000, 131_072):
        wire = build_request(
            [{"role": "user", "content": "x" * 180_000}],
            roomy.model_copy(update={"mimi_route_context_tokens": old_limit}),
            agent_contract=True,
        )
        assert len(wire["messages"][0]["content"]) == 180_000


def test_production_alpha_keeps_origin_egress_and_resource_guards():
    settings = alpha_settings()
    assert settings.is_production and settings.mimi_runner == "langgraph"
    with pytest.raises(ValueError, match="MIMI_PUBLIC_ORIGIN"):
        alpha_settings(mimi_public_origin=None)
    with pytest.raises(ValueError, match="MIMI_LIVE_PROVIDER_ENABLED"):
        alpha_settings(mimi_real_chat_enabled=False)
    for value in (0, 5):
        with pytest.raises(ValueError, match="MIMI_MAX_ACTIVE_RUNS"):
            alpha_settings(mimi_max_active_runs=value)
    for value in (65_535, 4_194_305):
        with pytest.raises(ValueError, match="MIMI_MAX_PAYLOAD_BYTES"):
            alpha_settings(mimi_max_payload_bytes=value)
    with pytest.raises(ValueError, match="mimi_compaction_trigger_tokens"):
        alpha_settings(mimi_compaction_trigger_tokens=200_000)


def test_alpha_has_one_trigger_separate_from_hard_route_limit():
    settings = alpha_settings()
    bound = bind_configuration(
        settings, {"profile_id": "deepseek", "effort": "high", "input_tokens": 100_000}
    )
    assert bound.mimi_compaction_trigger_tokens == 100_000
    assert bound.mimi_route_context_tokens == 1_048_576
    assert bound.mimi_route_max_output_tokens == 8192
    for legacy in (32_000, 200_000):
        with pytest.raises(HTTPException, match="mimi_alpha_trigger_requires_100k"):
            validate_configuration(
                {"profile_id": "deepseek", "effort": "high", "input_tokens": legacy}, alpha=True
            )
        # Historical saved config can be interpreted without rewriting receipts.
        assert (
            bind_configuration(
                settings, {"profile_id": "deepseek", "effort": "high", "input_tokens": legacy}
            ).mimi_compaction_trigger_tokens
            == 100_000
        )


def test_route_metadata_does_not_enable_unqualified_shortlist():
    settings = alpha_settings()
    profiles = {p["id"]: p for p in profiles_for_ui(settings)}
    assert profiles["deepseek"]["available"]
    assert not profiles["luna"]["available"]
    assert profiles["mimo"]["context_limit"] == 1_048_576
    for profile, effort in (("luna", "high"), ("mimo", "default"), ("glm", "high")):
        with pytest.raises(HTTPException, match="mimi_route_not_alpha_qualified"):
            bind_configuration(
                settings, {"profile_id": profile, "effort": effort, "input_tokens": 100_000}
            )


def test_delayed_main_prompt_triggers_once_without_request_hash_binding():
    settings = alpha_settings()
    revision = context_revision(settings, 1, None)
    call = receipt()
    call.route["context_revision"] = revision
    # New suffix/request fingerprint has no bearing on stable active epoch.
    call.route["request_fingerprint"] = "previous-request"
    first = prompt_observation(call, context_revision(settings, 1, None))
    assert first["should_compact"] and first["prompt_tokens"] == 100_001
    consumed = prompt_observation(call, revision, consumed=True)
    assert not consumed["should_compact"] and consumed["compaction_blocked"]
    for changed in (
        context_revision(settings, 1, uuid7()),
        context_revision(settings, 2, None),
        context_revision(settings.model_copy(update={"mimi_route_model": "other"}), 1, None),
    ):
        stale = prompt_observation(call, changed)
        assert not stale["eligible"] and not stale["should_compact"]
        assert stale["reason"] == "stale_context_revision"


@pytest.mark.parametrize(
    "violation", ["helper", "missing", "total", "reused", "route", "unknown", "providers-null"]
)
def test_only_bound_main_prompt_usage_can_trigger(violation):
    call = receipt()
    if violation == "helper":
        call.route["purpose"] = "compaction"
    elif violation in {"missing", "total"}:
        call.usage = (
            {}
            if violation == "missing"
            else {
                "total_tokens": 200_000,
                "completion_tokens": 180_000,
                "completion_tokens_details": {"reasoning_tokens": 100_001},
            }
        )
    elif violation == "reused":
        call.route["paid_dispatch"] = False
    elif violation == "route":
        call.route["actual_model"] = "other"
    elif violation == "unknown":
        call.state = "unknown"
    elif violation == "providers-null":
        call.route["providers"] = None
    result = prompt_observation(call, "epoch")
    assert not result["eligible"] and not result["should_compact"]
    assert result["prompt_tokens"] is None


def test_run_billing_deduplicates_helper_main_reuse_and_preserves_unknown():
    main = receipt(usage={"cost": 0.3})
    helper = receipt(usage={"cost": 0.05})
    helper.route["purpose"] = "compaction"
    reused = receipt(usage={"cost": 0.3})
    reused.route["paid_dispatch"] = False
    unknown = receipt(usage={}, state="unknown")
    duplicate = receipt(result=main.result, usage={"cost": 0.3})
    totals = run_costs([main, helper, reused, unknown, duplicate])
    assert totals["known_cost_usd"] == 0.35
    assert totals["helper_known_cost_usd"] == 0.05
    assert totals["main_calls"] == 2 and totals["helper_calls"] == 1
    assert totals["reused_calls"] == 1 and totals["unknown_cost_calls"] == 1
    assert not totals["cost_complete"]
    helper_only = run_costs([helper])
    assert helper_only["main_calls"] == 0 and helper_only["known_cost_usd"] == 0.05


def test_admission_rejects_before_work_and_recovers_after_failure(monkeypatch):
    monkeypatch.setattr(runtime, "get_settings", lambda: alpha_settings())
    guard_active = set()

    @asynccontextmanager
    async def guard(run_id):
        guard_active.add(run_id)
        try:
            yield
        finally:
            guard_active.remove(run_id)

    monkeypatch.setattr(runtime, "hold_run_guard", guard)

    async def scenario():
        first, second, rejected = uuid7(), uuid7(), uuid7()
        async with runtime.hold_run_guard_if_enabled(first):
            with pytest.raises(HTTPException, match="mimi_run_already_admitted"):
                runtime.admit_run(first)
            async with runtime.hold_run_guard_if_enabled(second):
                with pytest.raises(HTTPException, match="mimi_busy_try_later"):
                    async with runtime.hold_run_guard_if_enabled(rejected):
                        pytest.fail("overloaded worker must not run")
                # Session commit must not release the separate dispatch guard.
                await asyncio.sleep(0)
                assert guard_active == {first, second}
            with pytest.raises(RuntimeError, match="ordinary provider failure"):
                async with runtime.hold_run_guard_if_enabled(rejected):
                    raise RuntimeError("ordinary provider failure")
            assert guard_active == {first}
        assert not guard_active and not runtime._admitted_runs

    asyncio.run(scenario())


def test_admission_is_released_when_worker_is_cancelled_before_start(monkeypatch):
    monkeypatch.setattr(runtime, "get_settings", lambda: alpha_settings())

    async def scenario():
        run_id = uuid7()
        runtime.admit_run(run_id)
        supervisor = runtime.MimiRunSupervisor()

        async def work():
            pytest.fail("cancelled worker must never start")

        supervisor.start(run_id, work())
        assert supervisor.cancel(run_id)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert run_id not in runtime._admitted_runs
        await supervisor.stop()

    asyncio.run(scenario())


def test_production_graph_uses_only_explicitly_bound_app_database(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.agent.context import AssistantText
    from app.agent.langgraph_runner import run_langgraph
    from app.agent.loop import LoopLimits
    from app.agent.openrouter import AgentCompletion

    calls = []

    @asynccontextmanager
    async def saver(connection_string):
        calls.append(connection_string)
        yield InMemorySaver()

    monkeypatch.setattr(AsyncPostgresSaver, "from_conn_string", saver)
    configured = "postgresql+asyncpg://app:synthetic@alpha.example.invalid/alpha"

    async def invoke(messages, turn):
        return AgentCompletion(
            outcome=AssistantText(text="Xin chào"),
            response_id="synthetic",
            usage={},
            model=None,
            provider=None,
        )

    async def read(name, arguments):
        pytest.fail("text-only turn must not read")

    async def scenario():
        settings = alpha_settings(database_url=configured)
        args = dict(
            limits=LoopLimits(
                max_turns=1,
                max_tool_calls=1,
                max_serialized_bytes=65_536,
                deadline=datetime.now(UTC) + timedelta(minutes=1),
            ),
            invoke_model=invoke,
            execute_read=read,
            generation=1,
            policy_sha256="a" * 64,
            tool_registry_sha256="b" * 64,
            output_schema_sha256="c" * 64,
            deployment_settings=settings,
        )
        for other in (
            None,
            settings.model_copy(update={"app_env": "local"}),
            settings.model_copy(update={"database_url": configured + "other"}),
        ):
            with pytest.raises(RouteContractError, match="requires_authorized_app_database"):
                await run_langgraph(
                    [],
                    run_id=uuid7(),
                    database_url=configured,
                    **(args | {"deployment_settings": other}),
                )
        assert calls == []
        result = await run_langgraph([], run_id=uuid7(), database_url=configured, **args)
        assert result.outcome.text == "Xin chào" and len(calls) == 1

    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)
