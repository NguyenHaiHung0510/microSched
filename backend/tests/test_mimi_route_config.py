"""Per-conversation controls cannot mutate in-flight snapshots or escape routes."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.agent.local_budget import account, reserve
from app.agent.openrouter import RouteContractError
from app.agent.route_config import bind_configuration, validate_configuration
from app.core.settings import Settings


def settings():
    return Settings(
        app_env="local", oauth_state_secret="synthetic-test", mimi_route_model="openai/gpt-6-luna"
    )


def test_controls_preserve_inflight_snapshot_and_reject_route_escape():
    base = settings()
    first = bind_configuration(
        base, {"profile_id": "luna", "effort": "high", "input_tokens": 32000}
    )
    second = bind_configuration(
        base, {"profile_id": "mimo", "effort": "default", "input_tokens": 100000}
    )
    assert first.mimi_route_model == "openai/gpt-6-luna"
    assert first.mimi_route_reasoning_effort == "high"
    assert first.mimi_route_forced_tool_choice == "function"
    assert second.mimi_route_model == "xiaomi/mimo-v2.6-pro"
    assert base.mimi_route_reasoning_effort == "low"
    with pytest.raises(HTTPException, match="mimi_route_selection_not_supported"):
        validate_configuration({"profile_id": "arbitrary", "effort": "high", "input_tokens": 32000})
    with pytest.raises(HTTPException, match="mimi_route_selection_not_supported"):
        validate_configuration({"profile_id": "mimo", "effort": "high", "input_tokens": 32000})


def test_budget_preserves_unknown_holds_and_blocks_next_dispatch(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(path))
    ledger = {
        "grant_key_name": "MIMI_DEMO_1",
        "cap_usd": "0.01",
        "historical_accounted_usd": "0.009",
        "expires_at_utc": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "calls": [],
    }
    path.write_text(json.dumps(ledger), encoding="utf-8")
    selected = bind_configuration(
        settings(), {"profile_id": "luna", "effort": "medium", "input_tokens": 32000}
    )
    with pytest.raises(RouteContractError, match="local_budget_exhausted"):
        reserve(selected, [{"role": "user", "content": "hi"}], agent_contract=True)
    assert json.loads(path.read_text())["calls"] == []
    ledger["cap_usd"] = "1.0"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    token = reserve(selected, [{"role": "user", "content": "hi"}], agent_contract=True)
    assert token
    account(selected, token, {}, "synthetic-generation")
    call = json.loads(path.read_text())["calls"][0]
    assert call["state"] == "reserved_unknown"
    assert call["charged_or_reserved_usd"] == call["reservation_usd"]
    account(selected, token, {"cost": 0.0001}, "synthetic-generation")
    assert json.loads(path.read_text())["calls"][0]["state"] == "accounted"


def test_budget_expiry_blocks_dispatch_without_changing_ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(path))
    ledger = {
        "grant_key_name": "MIMI_DEMO_1",
        "cap_usd": "1.0",
        "historical_accounted_usd": "0",
        "expires_at_utc": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        "calls": [],
    }
    path.write_text(json.dumps(ledger), encoding="utf-8")
    selected = bind_configuration(
        settings(), {"profile_id": "luna", "effort": "medium", "input_tokens": 32000}
    )
    with pytest.raises(RouteContractError, match="local_budget_grant_expired"):
        reserve(selected, [], agent_contract=True)
    assert json.loads(path.read_text())["calls"] == []
