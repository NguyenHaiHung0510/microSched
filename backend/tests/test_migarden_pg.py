"""N01's real Postgres/app-role wire and Owner route tests; disposable DB only."""

import asyncio
import os
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.auth import PostgresSessionStore
from app.domain.migarden.credentials import digest
from app.main import create_app

pytestmark = pytest.mark.pg

ORIGIN = "http://127.0.0.1"
HUMAN = {"Origin": ORIGIN, "X-MiGarden-CSRF": "1", "Sec-Fetch-Site": "same-origin"}
ROOT = "/api/migarden"
OWNER_PATH = ROOT + "/config"
DEVICE = ROOT + "/device/exchange"
NOW = datetime(2026, 11, 17, 17, 1, tzinfo=UTC)
DEVICE_ID = "qa-n01-test"

CONFIG = {
    "expected_config_ref": None,
    "policy": {
        "manual_duration_seconds": 900,
        "max_session_seconds": 1800,
        "max_window_seconds": 7200,
        "window_seconds": 10800,
    },
    "schedule": {
        "enabled": True,
        "duration_seconds": 45,
        "effective_from": "2026-11-17T00:00:00Z",
        "effective_until": None,
        "recurrence": {"kind": "daily", "at_local_time": "07:00"},
    },
}


class Cell:
    def __init__(self, human, device, time):
        self.human, self.device, self.time = human, device, time
        self.sequence = 0

    def tick(self, seconds=1):
        self.time.now += timedelta(seconds=seconds)
        return self.time.now

    def report(self, kind, ref, payload, *, boot="boot-1", **more):
        self.sequence += 1
        return {
            "event_id": f"event-{self.sequence}",
            "boot_id": boot,
            "sequence": self.sequence,
            "kind": kind,
            "occurred_at": self.time.now.isoformat(),
            "time_quality": "synced",
            "zone_id": "zone-a",
            "binding_ref": "zone-a-v1",
            "config_ref": ref,
            "payload": payload,
            **more,
        }

    async def device_post(self, *, ref=None, boot="boot-1", epoch=0, reports=(), **overrides):
        return await self.device.post(
            DEVICE,
            json={
                "protocol": "migarden.zone-a.v1",
                "device_id": DEVICE_ID,
                "boot_id": boot,
                "control_epoch": epoch,
                "reports": list(reports),
                "snapshot": {
                    "observed_at": self.time.now.isoformat(),
                    "time_quality": "synced",
                    "output": "off",
                    "active_session": None,
                    "applied_config_ref": ref,
                    "ready": bool(ref),
                    "blocked_reason": None,
                }
                | overrides,
            },
        )

    async def configured(self):
        result = await self.human.put(OWNER_PATH, json=CONFIG, headers=HUMAN)
        assert result.status_code == 200, result.text
        ref = result.json()["desired"]["config_ref"]
        assert result.json()["application_status"] == "pending"
        result = await self.device_post()
        assert result.status_code == 200, result.text
        assert result.json()["desired_config"]["config_ref"] == ref
        self.tick()
        report = self.report("config_applied", ref, {})
        result = await self.device_post(ref=ref, reports=[report])
        assert result.status_code == 200, result.text
        assert result.json()["acked_event_ids"] == [report["event_id"]]
        assert (await self.human.get(OWNER_PATH)).json()["application_status"] == "applied"
        return ref

    async def state(self):
        result = await self.human.get(ROOT + "/state")
        assert result.status_code == 200, result.text
        return result.json()

    async def preview(self):
        res = await self.human.post(
            ROOT + "/start/preview", json={"duration_seconds": 45}, headers=HUMAN
        )
        assert res.status_code == 200, res.text
        return res.json()["preview_id"]

    async def confirm(self, preview):
        return await self.human.post(
            ROOT + "/start/confirm", json={"preview_id": preview}, headers=HUMAN
        )

    async def stop(self):
        return await self.human.post(ROOT + "/stop", json={}, headers=HUMAN)


@pytest.fixture
def run_cell(pg_dsn, monkeypatch):
    app_url = os.getenv("CI_APP_DATABASE_URL")
    if not app_url:
        pytest.skip("requires the configured disposable app role (CI_APP_DATABASE_URL)")
    assert httpx.URL(app_url).host in {"localhost", "127.0.0.1", "::1", "postgres", "db"}
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("MIGARDEN_ENABLED", "true")
    monkeypatch.setenv("MIGARDEN_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    from app.web import deps
    from app.web.routers import migarden_device, migarden_human

    clock = SimpleNamespace(now=NOW)
    for route in (migarden_device, migarden_human):
        monkeypatch.setattr(route, "now_utc", lambda: clock.now)

    async def run(case):
        admin = await asyncpg.connect(pg_dsn)
        await admin.execute(
            "TRUNCATE microsched.migarden_zone, microsched.migarden_report,"
            " microsched.migarden_session, microsched.migarden_command,"
            " microsched.migarden_config, microsched.migarden_boot"
        )
        engine = create_async_engine(async_postgres_url(app_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(deps, "get_sessionmaker", lambda: factory)
        get_settings.cache_clear()
        raw = secrets.token_urlsafe(32)
        await admin.execute(
            "INSERT INTO microsched.migarden_zone "
            "(zone_id, device_id, token_hash, device_environment)"
            " VALUES ('zone-a', $1, $2, 'qa')",
            DEVICE_ID,
            digest(raw),
        )
        ids = []
        try:
            app = create_app()
            store = PostgresSessionStore(factory, 90)
            token = await store.create("garden-n01@example.test")
            ids.append(token)
            transport = httpx.ASGITransport(app=app)
            async with (
                httpx.AsyncClient(
                    transport=transport, base_url=ORIGIN, cookies={"ms_session": token}
                ) as human,
                httpx.AsyncClient(
                    transport=transport, base_url=ORIGIN, headers={"Authorization": "Bearer " + raw}
                ) as device,
            ):
                await case(Cell(human, device, clock), admin, app_url)
        finally:
            for token in ids:
                await store.delete(token)
            await engine.dispose()
            await admin.close()
            get_settings.cache_clear()

    return lambda case: asyncio.run(run(case))


def test_pg_owner_cas_applied_and_immutable_role(run_cell):
    async def case(cell, _, app_url):
        ref1 = await cell.configured()
        modified = CONFIG | {
            "expected_config_ref": ref1,
            "schedule": CONFIG["schedule"]
            | {
                "recurrence": {"kind": "weekly", "at_local_time": "08:00", "days_of_week": [1, 3]},
            },
        }
        result, concurrent = await asyncio.gather(
            cell.human.put(OWNER_PATH, json=modified, headers=HUMAN),
            cell.human.put(OWNER_PATH, json=modified, headers=HUMAN),
        )
        assert sorted([result.status_code, concurrent.status_code]) == [200, 409]
        saved = (await cell.human.get(OWNER_PATH)).json()
        ref2 = saved["desired"]["config_ref"]
        assert saved["applied"]["config_ref"] == ref1 != ref2
        assert (await cell.state())["next_schedule"]["config_ref"] == ref1
        same = await cell.human.put(
            OWNER_PATH, json=modified | {"expected_config_ref": ref2}, headers=HUMAN
        )
        assert same.json()["desired"]["config_ref"] == ref2
        cell.tick(47)
        assert (await cell.state())["connection"] == "stale"
        response = await cell.device_post(ref=ref1)
        assert response.json()["desired_config"]["config_ref"] == ref2
        cell.tick()
        reject = cell.report("config_rejected", ref2, {"reason": "storage_unavailable"})
        await cell.device_post(ref=ref1, reports=[reject])
        assert (await cell.human.get(OWNER_PATH)).json()["application_status"] == "rejected"
        cell.tick()
        applied = cell.report("config_applied", ref2, {})
        assert (await cell.device_post(ref=ref2, reports=[applied])).status_code == 200
        delayed = cell.report("config_applied", ref1, {}, boot="boot-old")
        await cell.device_post(ref=ref2, reports=[delayed])
        assert (await cell.state())["config"]["applied"]["config_ref"] == ref2
        user = await asyncpg.connect(app_url)
        try:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await user.execute("UPDATE microsched.migarden_config SET bundle = bundle")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await user.execute("DELETE FROM microsched.migarden_report")
        finally:
            await user.close()

    run_cell(case)


def test_pg_auth_origin_scope_body_bounds_and_revoke(run_cell):
    async def case(cell, admin, _):
        assert (await cell.device.get(ROOT + "/state")).status_code == 401
        assert (await cell.human.post(DEVICE, json={})).status_code == 401
        assert (await cell.human.put(OWNER_PATH, json=CONFIG)).status_code == 403
        assert (
            await cell.human.put(
                OWNER_PATH, json=CONFIG, headers=HUMAN | {"Origin": "https://elsewhere.invalid"}
            )
        ).status_code == 403
        wrong = await cell.device.post(
            DEVICE,
            json={
                "protocol": "migarden.zone-a.v1",
                "device_id": "qa-different",
                "boot_id": "boot",
                "control_epoch": 0,
                "snapshot": {
                    "observed_at": None,
                    "time_quality": "unknown",
                    "output": "off",
                    "active_session": None,
                    "applied_config_ref": None,
                    "ready": False,
                    "blocked_reason": None,
                },
                "reports": [],
            },
        )
        assert wrong.status_code == 401
        too_many = await cell.device_post(
            reports=[cell.report("fault", None, {"reason": "sample"})] * 17
        )
        assert too_many.status_code == 422
        assert await admin.fetchval("SELECT count(*) FROM microsched.migarden_report") == 0

        async def oversize():
            for _ in range(9):
                yield b" " * 4096

        response = await cell.device.post(
            DEVICE, headers={"Content-Type": "application/json"}, content=oversize()
        )
        assert response.status_code == 413
        await admin.execute("UPDATE microsched.migarden_zone SET revoked_at = now()")
        assert (await cell.device_post()).status_code == 401

    run_cell(case)


def test_pg_received_grant_once_stop_and_dedup(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        key = await cell.preview()
        assert (await cell.state())["start_request"] is None
        first = await cell.confirm(key)
        assert first.status_code == 200 and first.json()["status"] == "pending", first.text
        assert (await cell.confirm(key)).json()["request_id"] == key
        res = (await cell.device_post(ref=ref)).json()
        (candidate,) = res["candidates"]
        assert candidate["request_id"] == key and not res["grants"]
        assert set(candidate) == {
            "request_id",
            "kind",
            "zone_id",
            "binding_ref",
            "config_ref",
            "boot_id",
            "control_epoch",
            "confirmed_at",
            "expires_at",
            "duration_seconds",
        }
        received = cell.report("request_received", ref, {}, trigger_source="remote", request_id=key)
        res = (await cell.device_post(ref=ref, reports=[received])).json()
        (grant,) = res["grants"]
        assert {k: v for k, v in grant.items() if k != "grant_id"} == candidate
        assert (
            await admin.fetchval(
                "SELECT grant_id FROM microsched.migarden_command WHERE request_id=$1", key
            )
            == grant["grant_id"]
        )
        res = (await cell.device_post(ref=ref, reports=[received])).json()
        assert res["acked_event_ids"] == [received["event_id"]]
        assert res["grants"] == res["candidates"] == []
        cell.tick()
        t = cell.time.now.isoformat()
        started = cell.report(
            "session_started",
            ref,
            {"started_at": t, "duration_seconds": 45},
            session_id="session-1",
            request_id=key,
            trigger_source="remote",
        )
        active = {
            "session_id": "session-1",
            "request_id": key,
            "config_ref": ref,
            "duration_seconds": 45,
            "elapsed_seconds": 0,
            "started_at": t,
            "trigger_source": "remote",
        }
        assert (
            await cell.device_post(ref=ref, reports=[started], output="on", active_session=active)
        ).status_code == 200
        assert (await cell.state())["start_request"]["status"] == "started"
        stop = await cell.stop()
        assert stop.status_code == 200 and stop.json()["status"] == "stop_requested"
        stop_id = stop.json()["request_id"]
        assert (await cell.stop()).json()["request_id"] == stop_id
        response = await cell.device_post(
            ref=ref,
            output="on",
            active_session=active,
            observed_at=None,
            time_quality="unknown",
            ready=False,
        )
        assert response.json()["stops"][0]["request_id"] == stop_id
        cell.tick(17)
        ended = cell.report(
            "session_ended",
            ref,
            {
                "started_at": t,
                "ended_at": cell.time.now.isoformat(),
                "output_duration_seconds": 17,
                "outcome": "stopped",
                "reason": "remote_stop",
            },
            session_id="session-1",
            request_id=key,
            trigger_source="remote",
        )
        closed = cell.report(
            "stop_processed",
            ref,
            {"outcome": "close_requested"},
            request_id=stop_id,
            trigger_source="remote",
        )
        res = (await cell.device_post(ref=ref, epoch=1, reports=[closed, ended])).json()
        assert (
            res["acked_event_ids"] == [closed["event_id"], ended["event_id"]] and not res["stops"]
        )
        state = await cell.state()
        assert state["start_request"]["status"] == "stopped"
        assert state["stop_request"]["status"] == "stop_confirmed"
        assert state["start_block_reason"] is None
        daily = (await cell.human.get(ROOT + "/daily")).json()
        assert daily["days"][-1]["remote_seconds"] == 17

    run_cell(case)


def test_pg_expiry_unknown_boot_epoch_and_stop_cancellation(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        preview = await cell.preview()
        cell.tick()
        assert (await cell.device_post(ref=ref, epoch=1)).status_code == 200
        assert (await cell.confirm(preview)).status_code == 409
        key = await cell.preview()
        assert (await cell.confirm(key)).status_code == 200
        assert (await cell.device_post(ref=ref, epoch=1)).json()["candidates"]
        stop = await cell.stop()
        assert stop.status_code == 200
        received = cell.report("request_received", ref, {}, trigger_source="remote", request_id=key)
        res = (await cell.device_post(ref=ref, epoch=1, reports=[received])).json()
        assert res["stops"] and not res["grants"]
        assert (await cell.state())["start_request"]["status"] == "canceled"
        cell.tick()
        res = (await cell.device_post(ref=ref, boot="boot-2")).json()
        assert not res["stops"]
        assert (await cell.state())["stop_request"]["status"] == "stop_stale"
        key = await cell.preview()
        assert (await cell.confirm(key)).status_code == 200
        cell.tick(46)
        late = cell.report("request_received", ref, {}, boot="boot-2", request_id=key)
        res = (await cell.device_post(ref=ref, boot="boot-2", reports=[late])).json()
        assert not res["grants"] and not res["candidates"]
        assert (await cell.state())["start_request"]["status"] == "expired"
        key = await cell.preview()
        assert (await cell.confirm(key)).status_code == 200
        assert (await cell.device_post(ref=ref, boot="boot-2")).json()["candidates"]
        received = cell.report("request_received", ref, {}, boot="boot-2", request_id=key)
        assert (await cell.device_post(ref=ref, boot="boot-2", reports=[received])).json()["grants"]
        cell.tick(50)
        await cell.device_post(ref=ref, boot="boot-3")
        state = await cell.state()
        assert state["start_request"]["status"] == "unknown"
        assert state["start_block_reason"] == "unresolved_execution"
        stop = await cell.stop()
        assert stop.status_code == 200
        stale = await cell.device_post(ref=ref, boot="boot-2", epoch=55)
        assert not stale.json()["grants"] and not stale.json()["stops"]
        assert (await cell.device_post(ref=ref, boot="boot-3")).json()["stops"]

    run_cell(case)


def test_pg_history_midnight_unknown_disposition_and_atomic_ack(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        s, e = "2026-11-17T16:59:30Z", "2026-11-17T17:00:15Z"
        report = cell.report(
            "session_ended",
            ref,
            {
                "started_at": s,
                "ended_at": e,
                "output_duration_seconds": 45,
                "outcome": "completed",
                "reason": None,
            },
            session_id="water-1",
            request_id="local-1",
            trigger_source="local_button",
        )
        report["occurred_at"] = e
        skipped = cell.report(
            "occurrence_decided",
            ref,
            {
                "occurrence_id": "occurrence-1",
                "scheduled_at": "2026-11-17T17:01:00Z",
                "disposition": "skipped",
                "reason": "budget",
            },
            trigger_source="schedule",
        )
        stopped = cell.report(
            "stop_processed", None, {"outcome": "already_off"}, trigger_source="local_button"
        )
        events = [report, skipped, stopped]
        packet = (await cell.device_post(ref=ref, reports=events)).json()
        assert packet["acked_event_ids"] == [e["event_id"] for e in events]
        cell.tick()
        assert (await cell.device_post(ref=ref, reports=[report])).json()["acked_event_ids"] == [
            report["event_id"]
        ]
        assert await admin.fetchval("SELECT count(*) FROM microsched.migarden_session") == 1
        extra = cell.report("fault", None, {"reason": "sample"})
        changed = stopped | {"payload": {"outcome": "unconfirmed"}}
        assert (await cell.device_post(ref=ref, reports=[extra, changed])).status_code == 409
        assert not await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", extra["event_id"]
        )
        daily = (await cell.human.get(ROOT + "/daily", params={"days": 7})).json()["days"]
        assert daily[-2]["local_button_seconds"] == 30 and daily[-1]["local_button_seconds"] == 15
        assert daily[-1]["schedule_seconds"] is None and daily[-3]["coverage"] == "unknown"
        page = (await cell.human.get(ROOT + "/history", params={"limit": 2})).json()
        next_page = (
            await cell.human.get(ROOT + "/history", params={"cursor": page["next_cursor"]})
        ).json()
        assert {x["kind"] for x in page["items"] + next_page["items"]} == {
            "occurrence_decided",
            "stop_processed",
            "session_ended",
        }
        filtered = (
            await cell.human.get(
                ROOT + "/history", params={"source": "schedule", "result": "skipped"}
            )
        ).json()
        assert len(filtered["items"]) == 1
        assert filtered["items"][0]["scheduled_at"] == "2026-11-17T17:01:00Z"
        assert (
            await cell.human.get(ROOT + "/history", params={"cursor": "bad"})
        ).status_code == 422

    run_cell(case)


def test_pg_terminal_loss_after_active_snapshot_blocks_start(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        cell.tick()
        start = cell.time.now.isoformat()
        active = {
            "session_id": "local-possibly-active",
            "request_id": "button-request",
            "trigger_source": "local_button",
            "started_at": start,
            "elapsed_seconds": 3,
            "duration_seconds": 900,
            "config_ref": ref,
        }
        await cell.device_post(ref=ref, output="on", active_session=active)
        assert (await cell.state())["start_block_reason"] == "busy"
        cell.tick(4)
        await cell.device_post(ref=ref)
        assert (await cell.state())["start_block_reason"] == "unresolved_execution"
        terminal = cell.report(
            "session_ended",
            ref,
            {
                "started_at": start,
                "ended_at": cell.time.now.isoformat(),
                "output_duration_seconds": 4,
                "outcome": "stopped",
                "reason": "local_stop",
            },
            request_id="button-request",
            session_id=active["session_id"],
            trigger_source="local_button",
        )
        assert (await cell.device_post(ref=ref, reports=[terminal])).status_code == 200
        assert (await cell.state())["start_block_reason"] is None

    run_cell(case)
