"""Authorized local-QA metering is finite and unknown spend stops dispatch."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.agent import local_budget as b
from app.agent.openrouter import RouteContractError
from app.core.settings import Settings


def test_meter_refresh_reservation_account_and_unknown_spend_stop(tmp_path, monkeypatch):
    ledger = tmp_path / "mimi086-budget.json"
    ledger.write_text(
        json.dumps(
            {
                "grant_key_name": "MIMI_DEMO_1",
                "cap_usd": "0.973631539",
                "baseline_key_usage": "0.526368461",
                "historical_accounted_usd": "0",
                "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(ledger))
    meters = []

    def meter(_):
        meters.append(1)
        return Decimal("0.526368461"), Decimal("0.973631539")

    monkeypatch.setattr(b, "key_meter", meter)
    settings = Settings(
        _env_file=None,
        app_env="local",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
    )
    rid = b.reserve(settings, [], agent_contract=True)
    assert rid and len(meters) == 1
    with pytest.raises(RouteContractError, match="prior_spend_unknown"):
        b.reserve(settings, [], agent_contract=True)
    b.account(settings, rid, {"cost": 0.001}, "synthetic-cost-1")
    rid2 = b.reserve(settings, [], agent_contract=True)
    assert len(meters) == 2
    with pytest.raises(RouteContractError, match="current_spend_unknown"):
        b.account(settings, rid2, {}, "synthetic-cost-unknown")
    assert json.loads(ledger.read_text())["calls"][-1]["state"] == "reserved_unknown"
    with pytest.raises(RouteContractError, match="prior_spend_unknown"):
        b.reserve(settings, [], agent_contract=True)


def test_actual_remaining_or_unknown_meter_blocks_before_call(tmp_path, monkeypatch):
    ledger = tmp_path / "mimi086-budget.json"
    ledger.write_text(
        json.dumps(
            {
                "grant_key_name": "MIMI_DEMO_1",
                "cap_usd": ".97",
                "baseline_key_usage": ".53",
                "historical_accounted_usd": "0",
                "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(ledger))
    settings = Settings(
        _env_file=None,
        app_env="local",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
    )
    monkeypatch.setattr(b, "key_meter", lambda _: (Decimal("1.49"), Decimal(".00001")))
    with pytest.raises(RouteContractError, match="exhausted"):
        b.reserve(settings, [], agent_contract=True)
    assert json.loads(ledger.read_text())["calls"] == []

    def unknown(_):
        raise RouteContractError("local_budget_key_meter_unknown")

    monkeypatch.setattr(b, "key_meter", unknown)
    with pytest.raises(RouteContractError, match="meter_unknown"):
        b.reserve(settings, [], agent_contract=True)
    assert json.loads(ledger.read_text())["calls"] == []


def test_finite_dispatch_cap_includes_accounted_main_and_helper_calls(tmp_path, monkeypatch):
    ledger = tmp_path / "finite16.json"
    ledger.write_text(
        json.dumps(
            {
                "grant_key_name": "MIMI_DEMO_1",
                "cap_usd": "1",
                "baseline_key_usage": "0",
                "historical_accounted_usd": "0",
                "max_paid_dispatches": 16,
                "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "calls": [
                    {"state": "accounted", "charged_or_reserved_usd": "0"} for _ in range(16)
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(ledger))
    monkeypatch.setattr(b, "key_meter", lambda _: pytest.fail("cap must stop before network"))
    settings = Settings(
        _env_file=None,
        app_env="local",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
    )
    with pytest.raises(RouteContractError, match="dispatch_cap_exhausted"):
        b.reserve(settings, [], agent_contract=True)
    assert len(json.loads(ledger.read_text())["calls"]) == 16
