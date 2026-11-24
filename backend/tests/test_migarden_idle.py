"""Pre-SQL boundaries use the real ASGI route without any database."""

import asyncio

import httpx

from app.core.settings import get_settings
from app.domain.migarden.wire import ExchangeEnvelope
from app.main import create_app
from app.web import deps
from app.web.migarden_quiet import QuietGate


def envelope(**changes):
    data = {
        "protocol": "migarden.zone-a.v1",
        "device_id": "synthetic-controller",
        "boot_id": "synthetic-boot",
        "control_epoch": 0,
        "reports": [],
        "snapshot": {
            "observed_at": "2026-11-22T00:00:00Z",
            "time_quality": "synced",
            "output": "off",
            "active_session": None,
            "applied_config_ref": None,
            "ready": False,
            "blocked_reason": None,
        },
    }
    return ExchangeEnvelope.model_validate(data | changes)


def test_quiet_idle_restart_lease_six_hours_and_event_bypass():
    clock = [0.0]
    gate = QuietGate(clock=lambda: clock[0])
    packet = envelope()
    assert gate.enter("synthetic-hash", packet, True)
    assert not gate.enter("synthetic-hash", packet, True)  # single flight
    gate.committed("synthetic-hash", packet, terminal=False)
    for second in range(5, 700, 5):
        clock[0] = second
        assert not gate.enter("synthetic-hash", packet, True)
    gate.present()
    assert gate.enter("synthetic-hash", packet, True)
    gate.committed("synthetic-hash", packet, terminal=False)
    clock[0] += 301
    assert not gate.enter("synthetic-hash", packet, True)
    clock[0] = gate.reconcile_at
    assert gate.enter("synthetic-hash", packet, True)
    gate.committed("synthetic-hash", packet, terminal=False)
    assert gate.enter("synthetic-hash", envelope(boot_id="new-boot"), True)
    restarted = QuietGate(clock=lambda: clock[0])
    assert restarted.enter("synthetic-hash", packet, True)
    restarted.committed("synthetic-hash", packet, terminal=False)
    assert not restarted.enter("synthetic-hash", packet, True)


def test_authentic_work_bypasses_soft_wait_but_not_finite_retry():
    clock = [0.0]
    gate = QuietGate(clock=lambda: clock[0])
    packet = envelope()
    gate.committed("synthetic-hash", packet, terminal=False)
    event = envelope(reports=[{"event_id": "synthetic-event"}])
    for delay in (5, 15, 30, 60, 60):
        assert gate.enter("synthetic-hash", event, True)
        gate.failed()
        clock[0] += delay - 1
        assert not gate.enter("synthetic-hash", event, True)
        clock[0] += 1
    assert gate.enter("synthetic-hash", event, True)


def test_only_new_terminal_can_extend_tail_not_repeated_off_or_health():
    clock = [0.0]
    gate = QuietGate(clock=lambda: clock[0])
    packet = envelope()
    gate.committed("synthetic-hash", packet, terminal=True)
    deadline = gate.tail_until
    for second in range(5, 600, 5):
        clock[0] = second
        assert gate.enter("synthetic-hash", packet, True)
        gate.committed("synthetic-hash", packet, terminal=False)
        assert gate.tail_until == deadline
    clock[0] = 601
    assert not gate.enter("synthetic-hash", envelope(health={"changed": "ignored"}), True)


def test_payload_guard_precedes_database(monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("MIGARDEN_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()
    calls = []

    def forbidden():
        calls.append("database_factory")
        raise AssertionError("database reached before payload guard")

    monkeypatch.setattr(deps, "get_sessionmaker", forbidden)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(), raise_app_exceptions=False),
            base_url="http://127.0.0.1",
        ) as client:
            response = await client.post(
                "/api/migarden/device/exchange",
                headers={"Authorization": "Bearer " + "s" * 43},
                json={"not": "an exchange"},
            )
            assert response.status_code == 422, response.text
            assert calls == []

    try:
        asyncio.run(run())
    finally:
        get_settings.cache_clear()
