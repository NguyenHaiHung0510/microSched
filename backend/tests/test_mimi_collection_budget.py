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
        mimi_route_billing_prompt_ceiling=1_048_576,
        mimi_route_capacity_source="synthetic-native-capacity-receipt",
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
        mimi_route_billing_prompt_ceiling=1_048_576,
        mimi_route_capacity_source="synthetic-native-capacity-receipt",
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
        mimi_route_billing_prompt_ceiling=1_048_576,
        mimi_route_capacity_source="synthetic-native-capacity-receipt",
    )
    with pytest.raises(RouteContractError, match="dispatch_cap_exhausted"):
        b.reserve(settings, [], agent_contract=True)
    assert len(json.loads(ledger.read_text())["calls"]) == 16


@pytest.fixture
def historical_budget(tmp_path, monkeypatch):
    path = tmp_path / "owner232-budget.json"
    ledger = {
        "grant_key_name": "MIMI_DEMO_1",
        "cap_usd": "3",
        "baseline_key_usage": "0.5",
        "historical_accounted_usd": "0.00457674",
        # Full unresolved reservation, additional to the settled known cost.
        "historical_reserved_usd": "0.38928384",
        "historical_dispatch_count": 4,
        "historical_max_dispatch_count": 0,
        "max_paid_dispatches": 92,
        "max_conditional_max_dispatches": 8,
        "expires_at_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "calls": [],
    }
    path.write_text(json.dumps(ledger), encoding="utf-8")
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(path))
    meters = []

    def meter(_):
        meters.append(1)
        return Decimal("0.50457674"), Decimal("3")

    monkeypatch.setattr(b, "key_meter", meter)
    settings = Settings(
        _env_file=None,
        app_env="local",
        mimi_route_reasoning_effort="high",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
        mimi_route_max_output_tokens=8192,
        mimi_route_billing_prompt_ceiling=1_048_576,
        mimi_route_capacity_source="synthetic-native-capacity-receipt",
    )
    return path, ledger, settings, meters


def test_history_full_hold_is_added_to_known_cost_without_fabricated_old_calls(historical_budget):
    path, ledger, settings, meters = historical_budget
    maximum = Decimal("0.2146304")
    ledger["cap_usd"] = str(Decimal("0.00457674") + Decimal("0.38928384") + maximum)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    call_id = b.reserve(settings, [], agent_contract=True)
    b.account(settings, call_id, {"cost": 0.001}, "synthetic-distinct-new-call")
    actual = json.loads(path.read_text())
    assert len(actual["calls"]) == len(meters) == 1
    assert actual["calls"][0]["id"] == call_id
    assert actual["calls"][0]["charged_or_reserved_usd"] == "0.001"
    assert {key: actual[key] for key in ledger if key != "calls"} == {
        key: value for key, value in ledger.items() if key != "calls"
    }
    # The original full hold survives settlement of a distinct new request.
    with pytest.raises(RouteContractError, match="local_budget_exhausted"):
        b.reserve(settings, [], agent_contract=True)
    assert len(json.loads(path.read_text())["calls"]) == 1


def test_history_hold_refuses_before_a_new_dispatch_when_no_headroom(historical_budget):
    path, ledger, settings, _ = historical_budget
    ledger["cap_usd"] = "0.6"  # .00457674 + .38928384 + .2146304 > .6
    path.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(RouteContractError, match="local_budget_exhausted"):
        b.reserve(settings, [], agent_contract=True)
    assert json.loads(path.read_text())["calls"] == []


@pytest.mark.parametrize("effort", ["high", "max"])
def test_history_counts_share_the_original_caps_with_new_dispatches(historical_budget, effort):
    path, ledger, settings, meters = historical_budget
    settings = settings.model_copy(update={"mimi_route_reasoning_effort": effort})
    if effort == "high":
        ledger["historical_dispatch_count"] = 91
        reason = "dispatch_cap_exhausted"
    else:
        ledger["historical_dispatch_count"] = 7
        ledger["historical_max_dispatch_count"] = 7
        reason = "MAX_cap_exhausted"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    call_id = b.reserve(settings, [], agent_contract=True)
    b.account(settings, call_id, {"cost": 0.001}, "synthetic-final-allowed-call")
    with pytest.raises(RouteContractError, match=reason):
        b.reserve(settings, [], agent_contract=True)
    assert len(json.loads(path.read_text())["calls"]) == len(meters) == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"historical_reserved_usd": -1},
        {"historical_reserved_usd": True},
        {"historical_reserved_usd": None},
        {"historical_reserved_usd": "NaN"},
        {"historical_reserved_usd": "Infinity"},
        {"historical_reserved_usd": "not-a-cost"},
        {"historical_reserved_usd": "3"},  # known + held exceeds original cap
        {"historical_dispatch_count": True},
        {"historical_dispatch_count": "4"},
        {"historical_dispatch_count": 4.0},
        {"historical_dispatch_count": -1},
        {"historical_dispatch_count": 93},
        {"historical_dispatch_count": 5, "max_paid_dispatches": 4},
        {"historical_max_dispatch_count": True},
        {"historical_max_dispatch_count": "0"},
        {"historical_max_dispatch_count": -1},
        {"historical_dispatch_count": 9, "historical_max_dispatch_count": 9},
        {"historical_max_dispatch_count": 5},  # MAX count exceeds all historical calls
        {"historical_max_dispatch_count": 1, "max_conditional_max_dispatches": 0},
    ],
)
def test_invalid_history_fails_before_meter_or_ledger_mutation(historical_budget, updates):
    path, ledger, settings, meters = historical_budget
    ledger.update(updates)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(RouteContractError, match="local_budget_history_invalid"):
        b.reserve(settings, [], agent_contract=True)
    assert path.read_bytes() == before and not meters


def test_new_unknown_cost_and_cost_over_reservation_still_stop_with_history(historical_budget):
    path, _, settings, meters = historical_budget
    call_id = b.reserve(settings, [], agent_contract=True)
    with pytest.raises(RouteContractError, match="current_spend_unknown"):
        b.account(settings, call_id, {}, None)
    with pytest.raises(RouteContractError, match="prior_spend_unknown"):
        b.reserve(settings, [], agent_contract=True)
    unknown = json.loads(path.read_text())
    assert unknown["calls"][0]["state"] == "reserved_unknown"
    assert unknown["calls"][0]["response_id"] is None
    with pytest.raises(RouteContractError, match="provider_cost_exceeded_reservation"):
        b.account(settings, call_id, {"cost": 0.22}, "synthetic-expensive-call")
    with pytest.raises(RouteContractError, match="prior_reservation_exceeded"):
        b.reserve(settings, [], agent_contract=True)
    assert len(meters) == 1


def test_settlement_total_retains_full_historical_hold(historical_budget):
    path, ledger, settings, _ = historical_budget
    # Seed a synthetic reserved request to exercise settlement independently of admission.
    ledger["cap_usd"] = "0.6"
    ledger["calls"] = [
        {"id": "synthetic-reserved", "state": "reserved_unknown", "reservation_usd": "0.3"}
    ]
    path.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(RouteContractError, match="provider_cost_exceeded_reservation"):
        b.account(settings, "synthetic-reserved", {"cost": 0.21}, "synthetic-observed-cost")
    actual = json.loads(path.read_text())
    assert actual["historical_reserved_usd"] == "0.38928384"
    assert actual["calls"][0]["state"] == "accounted"
    assert actual["calls"][0]["charged_or_reserved_usd"] == "0.21"
