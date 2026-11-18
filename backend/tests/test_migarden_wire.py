"""Frozen shape and deterministic time/config oracles (no real device)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.migarden.credentials import allows, digest
from app.domain.migarden.queries import allocate_reported
from app.domain.migarden.schedule import forecast
from app.domain.migarden.wire import (
    ConfigurationBundle,
    ExchangeOut,
    Policy,
    Report,
    Schedule,
)

NOW = datetime(2026, 11, 17, 22, tzinfo=UTC)


def bundle(recurrence, **extras):
    return ConfigurationBundle(
        config_ref="config-1",
        policy=Policy(),
        schedule=Schedule(
            **(
                {
                    "enabled": True,
                    "effective_from": "2026-11-17T00:00:00Z",
                    "effective_until": None,
                    "duration_seconds": 45,
                    "recurrence": recurrence,
                }
                | extras
            )
        ),
    )


@pytest.mark.parametrize(
    ("recurrence", "expected", "seconds"),
    [
        ({"kind": "once", "at": "2026-11-18T01:00:00Z"}, "2026-11-18T01:00:00Z", 45),
        ({"kind": "daily", "at_local_time": "07:00"}, "2026-11-18T00:00:00Z", 45),
        (
            {"kind": "weekly", "at_local_time": "06:00", "days_of_week": [4]},
            "2026-11-18T23:00:00Z",
            45,
        ),
        (
            {"kind": "interval", "anchor_at": "2026-11-17T17:00:00Z", "interval_minutes": 240},
            "2026-11-18T01:00:00Z",
            180,
        ),
    ],
)
def test_forecast_from_applied_pattern(recurrence, expected, seconds):
    result = forecast(bundle(recurrence), NOW)
    assert result.next_at == datetime.fromisoformat(expected)
    assert result.day_total_seconds == seconds


def test_forecast_effective_edges_and_pause():
    recurrence = {"kind": "daily", "at_local_time": "07:00"}
    result = forecast(bundle(recurrence, effective_until="2026-11-18T00:00:00Z"), NOW)
    assert result.status == "no_future_occurrence"
    result = forecast(bundle(recurrence, effective_from="2026-11-18T00:00:00Z"), NOW)
    assert result.next_at == datetime(2026, 11, 18, tzinfo=UTC)
    assert forecast(bundle(recurrence, enabled=False), NOW).status == "paused"
    assert forecast(None, NOW).status == "no_applied_config"


@pytest.mark.parametrize(
    "update",
    [
        {"manual_duration_seconds": 901},
        {"manual_duration_seconds": False},
        {"window_seconds": 10500},
        {"max_window_seconds": 1790},
        {"manual_duration_seconds": 1815},
    ],
)
def test_policy_rejects_incompatible_limits(update):
    assert Policy().model_dump() == {
        "manual_duration_seconds": 900,
        "max_session_seconds": 1800,
        "max_window_seconds": 7200,
        "window_seconds": 10800,
    }
    with pytest.raises(ValidationError):
        Policy.model_validate(Policy().model_dump() | update)


def test_config_rejects_incompatible_duration_clock_and_weekdays():
    with pytest.raises(ValidationError):
        bundle({"kind": "weekly", "at_local_time": "07:00", "days_of_week": [3, 3]})
    with pytest.raises(ValidationError):
        bundle({"kind": "daily", "at_local_time": "07:00"}, duration_seconds=1815)
    with pytest.raises(ValidationError):
        bundle({"kind": "once", "at": "2026-11-18T07:00:13Z"})
    with pytest.raises(ValidationError):
        bundle(
            {"kind": "interval", "anchor_at": "2026-11-18T07:00:00+07:00", "interval_minutes": 1}
        )


def test_closed_duration_allocates_by_hanoi_midnight_and_preserves_unknown():
    start = datetime.fromisoformat("2026-11-17T16:59:30Z")
    end = datetime.fromisoformat("2026-11-17T17:00:15Z")
    assert [(str(day), seconds) for day, seconds in allocate_reported(start, end, 45)] == [
        ("2026-11-17", 30),
        ("2026-11-18", 15),
    ]
    assert allocate_reported(start, end, None) == []
    assert allocate_reported(start, end, 15) == []


def test_wire_exact_response_root_and_clarification_a_null_ref_rules():
    assert set(ExchangeOut(server_time=NOW).model_dump()) == {
        "protocol",
        "server_time",
        "desired_config",
        "candidates",
        "grants",
        "stops",
        "acked_event_ids",
        "retry_after_seconds",
    }
    common = dict(
        event_id="one",
        boot_id="boot",
        sequence=1,
        occurred_at=None,
        time_quality="unknown",
        zone_id="zone-a",
        binding_ref="zone-a-v1",
        config_ref=None,
        kind="stop_processed",
        payload={"outcome": "already_off"},
    )
    validate = TypeAdapter(Report).validate_python
    validate(common | {"trigger_source": "local_button"})
    with pytest.raises(ValidationError):
        validate(common | {"trigger_source": "remote"})
    validate(common | {"trigger_source": "remote", "request_id": "stop-1"})
    with pytest.raises(ValidationError):
        validate(common | {"kind": "config_applied", "payload": {}})


def test_token_matches_only_its_environment_and_revocation():
    token_hash = digest("synthetic-independent-fixture")
    zone = SimpleNamespace(
        device_id="qa-fixture", device_environment="qa", token_hash=token_hash, revoked_at=None
    )
    assert allows(zone, token_hash, False)
    assert not allows(zone, token_hash, True)
    assert not allows(zone, digest("different"), False)
    zone.revoked_at = NOW
    assert not allows(zone, token_hash, False)
