"""Owner84 selection/persistence/admission/helper contracts without a DB or egress."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid7

import pytest
from fastapi import HTTPException

from app.agent import local_budget, service
from app.agent.openrouter import build_request
from app.agent.route_config import (
    PROFILES,
    ConfigurationChange,
    bind_configuration,
    default_configuration,
    profiles_for_ui,
    validate_configuration,
)
from app.agent.route_pool import ADMITTED_MODEL, NoEligibleEndpoint, eligible_pool
from app.core.settings import Settings


def settings(**updates):
    return Settings(
        _env_file=None,
        **(
            dict(
                app_env="local",
                oauth_state_secret="synthetic-only",
                mimi_real_chat_enabled=True,
                mimi_live_provider_enabled=True,
                mimi_context_v1_enabled=True,
                mimi_collection_enabled=True,
                mimi_standard_api_key="synthetic-never-sent",
                mimi_route_model=ADMITTED_MODEL,
                mimi_route_provider="deepinfra",
                mimi_route_quantization="fp8",
                mimi_route_max_input_price=0.2,
                mimi_route_max_output_price=0.6,
            )
            | updates
        ),
    )


@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_saved_effort_roundtrips_and_next_run_cannot_mutate_prior_snapshot(effort, monkeypatch):
    base = settings()
    active = uuid7()
    row = SimpleNamespace(route_config={}, route_config_version=1)
    db = SimpleNamespace(
        flush=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: active)),
    )
    monkeypatch.setattr(service, "get_settings", lambda: base)
    monkeypatch.setattr(service, "_conversation", AsyncMock(return_value=row))
    prior = bind_configuration(base, default_configuration(base))

    async def scenario():
        change = ConfigurationChange(
            profile_id="deepseek", effort=effort, input_tokens=100_000, expected_version=1
        )
        saved = await service.conversation_configuration(db, None, uuid7(), change)
        assert saved["version"] == 2 and saved["applies_to"] == "next_run"
        assert saved["active_run_id"] == str(active)
        # Exercise the service persistence seam; no SQL/DB connection is opened.
        row.route_config = json.loads(json.dumps(row.route_config))
        reread = await service.conversation_configuration(db, None, uuid7())
        assert reread["stored_config"]["effort"] == reread["config"]["effort"] == effort
        selected = bind_configuration(base, reread["stored_config"])
        assert selected.mimi_route_reasoning_effort == effort
        assert prior.mimi_route_reasoning_effort == base.mimi_route_reasoning_effort == "low"
        assert selected.model_dump(exclude={"mimi_route_reasoning_effort"}) == prior.model_dump(
            exclude={"mimi_route_reasoning_effort"}
        )
        for helper in (False, True):
            admitted = selected.model_copy(update={"mimi_route_allowed_providers": "deepinfra/fp8"})
            wire = build_request([], admitted, agent_contract=not helper, summary_mode=helper)
            assert wire["reasoning"] == {"effort": effort, "exclude": True}
            assert wire["model"] == ADMITTED_MODEL and wire["max_tokens"] == 8192
            assert wire["provider"]["zdr"] is True
            assert wire["provider"]["data_collection"] == "deny"
            assert wire["provider"]["require_parameters"] is True
            assert wire["provider"]["max_price"] == {"prompt": 0.2, "completion": 0.6}
            if helper:
                assert "tools" not in wire and "tool_choice" not in wire
        with pytest.raises(HTTPException, match="mimi_route_config_stale"):
            await service.conversation_configuration(db, None, uuid7(), change)
        assert row.route_config_version == 2 and row.route_config["effort"] == effort
        db.flush.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("effort", ["medium", "xhigh", "ultra", "MAX", "default", "none", ""])
def test_deepseek_unsupported_values_are_rejected_without_aliasing(effort):
    with pytest.raises(HTTPException, match="mimi_route_selection_not_supported"):
        validate_configuration(dict(profile_id="deepseek", effort=effort, input_tokens=100_000))
    with pytest.raises(NoEligibleEndpoint, match="selected_model_or_effort_not_admitted"):
        eligible_pool({}, model=ADMITTED_MODEL, effort=effort)


@pytest.mark.parametrize("profile", ["luna", "mimo", "glm"])
def test_max_does_not_admit_other_families(profile):
    with pytest.raises(HTTPException, match="mimi_route_selection_not_supported"):
        validate_configuration(dict(profile_id=profile, effort="max", input_tokens=100_000))
    with pytest.raises(NoEligibleEndpoint, match="selected_model_or_effort_not_admitted"):
        eligible_pool({}, model=PROFILES[profile]["model"], effort="max")


def test_defaults_limits_and_profile_availability_are_unchanged():
    base = settings()
    assert default_configuration(base) == dict(
        profile_id="deepseek", effort="low", input_tokens=100_000
    )
    assert Settings.model_fields["mimi_route_reasoning_effort"].default == "low"
    assert base.mimi_route_max_output_tokens == 4096
    selected = bind_configuration(
        base, dict(profile_id="deepseek", effort="max", input_tokens=100_000)
    )
    assert selected.mimi_route_context_tokens == 1_048_576
    assert selected.mimi_compaction_trigger_tokens == 100_000
    assert selected.mimi_route_max_output_tokens == 8192
    assert (selected.mimi_run_max_turns, selected.mimi_run_max_tool_calls) == (32, 64)
    assert selected.mimi_run_deadline_seconds == base.mimi_run_deadline_seconds == 1800
    assert selected.mimi_max_payload_bytes == base.mimi_max_payload_bytes == 2_097_152
    profiles = profiles_for_ui(base)
    assert [p["id"] for p in profiles if p["available"]] == ["deepseek"]
    assert next(p for p in profiles if p["id"] == "deepseek")["supported_efforts"] == [
        "low",
        "high",
        "max",
    ]
    assert default_configuration(settings(mimi_route_reasoning_effort="max"))["effort"] == "max"


@pytest.mark.parametrize("effort", ["low", "high", "max"])
def test_actual_compaction_helper_dispatch_and_journal_keep_selected_effort(effort, monkeypatch):
    class CapturedDispatch(RuntimeError):
        pass

    selected = bind_configuration(
        settings(),
        dict(profile_id="deepseek", effort=effort, input_tokens=100_000, routing_mode="exact"),
    )
    conversation = SimpleNamespace(
        id=uuid7(), route_config_version=2, context_frontier_sequence=0, generation=1
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: 0)),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(local_budget, "reserve", lambda *args, **kwargs: None)
    captured = []

    async def invoke(messages, **kwargs):
        captured.append(
            build_request(messages, kwargs["settings"], summary_mode=kwargs["summary_mode"])
        )
        raise CapturedDispatch()

    monkeypatch.setattr(service, "openrouter_complete", invoke)
    with pytest.raises(CapturedDispatch):
        asyncio.run(
            service._semantic_checkpoint(db, conversation, uuid7(), [], None, None, None, selected)
        )
    wire = captured[0]
    assert wire["reasoning"] == {"effort": effort, "exclude": True}
    assert wire["model"] == ADMITTED_MODEL and wire["max_tokens"] == 8192
    assert "tools" not in wire and "tool_choice" not in wire
    call = db.add.call_args.args[0]
    assert call.route["reasoning_effort"] == effort and call.route["purpose"] == "compaction"
    assert call.route["context_limit"] == 1_048_576 and call.route["output_reserve"] == 8192
    assert call.state == "dispatched" and db.commit.await_count == 2
