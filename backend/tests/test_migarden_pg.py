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

    async def run(case, *, raise_app_exceptions):
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
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
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

    def execute(case, *, raise_app_exceptions=True):
        return asyncio.run(run(case, raise_app_exceptions=raise_app_exceptions))

    return execute


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
        assert (await cell.state())["stop_request"]["status"] == "stop_requested"
        stop = await cell.stop()
        stop_id = stop.json()["request_id"]
        processed = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            boot="boot-2",
            request_id=stop_id,
            trigger_source="remote",
        )
        assert (
            await cell.device_post(ref=ref, boot="boot-2", reports=[processed])
        ).status_code == 200
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


def test_pg_history_midnight_unknown_disposition_and_isolated_ack(run_cell):
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
        conflict = await cell.device_post(ref=ref, reports=[extra, changed])
        assert conflict.status_code == 200
        assert conflict.json()["acked_event_ids"] == [extra["event_id"]]
        assert conflict.json()["grants"] == []
        assert await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", extra["event_id"]
        )
        assert (
            await admin.fetchval(
                "SELECT body->'payload'->>'outcome' FROM microsched.migarden_report "
                "WHERE event_id=$1",
                stopped["event_id"],
            )
            == "already_off"
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


@pytest.mark.parametrize("poison_kind", ["schema", "conflict"])
def test_pg_review_stop_bypasses_poison_without_poison_ack_or_grant(run_cell, poison_kind):
    async def case(cell, admin, _):
        ref = await cell.configured()
        key = await cell.preview()
        await cell.confirm(key)
        await cell.device_post(ref=ref)
        existing = cell.report("fault", ref, {"reason": "original"})
        await cell.device_post(ref=ref, reports=[existing])
        if poison_kind == "schema":
            poison = cell.report(
                "stop_processed",
                ref,
                {"outcome": "not-a-wire-outcome"},
                trigger_source="local_button",
            )
        else:
            poison = existing | {"payload": {"reason": "conflicting-content"}}
        stop = (await cell.stop()).json()["request_id"]
        received = cell.report("request_received", ref, {}, request_id=key, trigger_source="remote")
        for _ in range(2):
            response = await cell.device_post(ref=ref, reports=[received, poison])
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["stops"][0]["request_id"] == stop
            assert data["acked_event_ids"] == [received["event_id"]]
            assert data["grants"] == data["candidates"] == []
            assert (
                await admin.fetchval(
                    "SELECT count(*) FROM microsched.migarden_report WHERE event_id=$1",
                    received["event_id"],
                )
                == 1
            )
        closed = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=stop,
            trigger_source="remote",
        )
        await cell.device_post(ref=ref, epoch=1, reports=[closed])
        assert (await cell.state())["start_request"]["status"] == "canceled"
        assert (await cell.state())["stop_request"]["status"] == "stop_confirmed"
        cell.tick(46)
        await cell.device_post(ref=ref, epoch=1)
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"

    run_cell(case)


def test_pg_review_unconfirmed_stop_stays_pending_until_positive_correlated_receipt(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        stop = (await cell.stop()).json()["request_id"]
        unconfirmed = cell.report(
            "stop_processed",
            ref,
            {"outcome": "unconfirmed"},
            trigger_source="remote",
            request_id=stop,
        )
        result = await cell.device_post(ref=ref, reports=[unconfirmed])
        assert result.json()["stops"][0]["request_id"] == stop
        assert (await cell.state())["stop_request"]["status"] == "stop_unconfirmed"
        assert (await cell.state())["start_block_reason"] == "stop_pending"
        cell.tick(60)
        result = await cell.device_post(ref=ref, epoch=1)
        assert result.json()["stops"][0]["request_id"] == stop
        assert (await cell.stop()).json()["request_id"] == stop
        assert (await cell.state())["start_block_reason"] == "stop_pending"
        positive = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            trigger_source="remote",
            request_id=stop,
        )
        result = await cell.device_post(ref=ref, epoch=1, reports=[positive])
        assert result.json()["stops"] == []
        assert (await cell.state())["start_block_reason"] is None

    run_cell(case)


def test_pg_review_new_unknown_boot_stop_is_separate_from_verified_open_boot(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        cell.tick()
        response = await cell.device_post(
            ref=ref,
            boot="boot-new",
            observed_at=None,
            time_quality="unknown",
            ready=False,
        )
        assert response.status_code == 200
        assert await admin.fetchval("SELECT boot_id FROM microsched.migarden_zone") == "boot-1"
        assert (await cell.state())["start_block_reason"] == "controller_boot_unconfirmed"
        stop = (await cell.stop()).json()["request_id"]
        response = await cell.device_post(
            ref=ref,
            boot="boot-new",
            observed_at=None,
            time_quality="unknown",
            ready=False,
        )
        assert response.json()["stops"][0]["boot_id"] == "boot-new"
        assert response.json()["stops"][0]["request_id"] == stop
        assert response.json()["grants"] == response.json()["candidates"] == []
        response = await cell.device_post(ref=ref, boot="boot-1", epoch=12)
        assert not response.json()["stops"]
        assert (
            await admin.fetchval("SELECT stop_target_boot_id FROM microsched.migarden_zone")
            == "boot-new"
        )
        cell.tick()
        await cell.device_post(ref=ref, boot="boot-new")
        assert await admin.fetchval("SELECT boot_id FROM microsched.migarden_zone") == "boot-new"
        processed = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            boot="boot-new",
            request_id=stop,
            trigger_source="remote",
        )
        await cell.device_post(ref=ref, boot="boot-new", reports=[processed])
        assert (await cell.state())["start_block_reason"] is None
        # Retired boot with a fresh-looking timestamp cannot replace the current one.
        cell.tick()
        await cell.device_post(ref=ref, boot="boot-1", epoch=13)
        assert await admin.fetchval("SELECT boot_id FROM microsched.migarden_zone") == "boot-new"
        assert (
            await admin.fetchval("SELECT stop_target_boot_id FROM microsched.migarden_zone")
            == "boot-new"
        )

    run_cell(case)


def test_pg_review_unknown_snapshot_never_regresses_applied_or_forecast(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        changed = CONFIG | {
            "expected_config_ref": ref,
            "schedule": CONFIG["schedule"]
            | {
                "recurrence": {"kind": "daily", "at_local_time": "09:00"},
            },
        }
        result = await cell.human.put(OWNER_PATH, json=changed, headers=HUMAN)
        newer_ref = result.json()["desired"]["config_ref"]
        cell.tick()
        report = cell.report("config_applied", newer_ref, {})
        await cell.device_post(ref=newer_ref, reports=[report])
        for epoch in (0, 1):
            cell.tick()
            await cell.device_post(ref=ref, epoch=epoch, observed_at=None, time_quality="unknown")
            state = await cell.state()
            assert state["config"]["applied"]["config_ref"] == newer_ref
            assert state["next_schedule"]["config_ref"] == newer_ref
            assert state["start_block_reason"] is not None

    run_cell(case)


def test_pg_review_unidentified_execution_is_not_cleared_by_off_ttl_or_unrelated_terminal(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        cell.tick()
        await cell.device_post(ref=ref, output="on", active_session=None)
        cell.tick(60)
        terminal = cell.report(
            "session_ended",
            ref,
            {
                "started_at": cell.time.now.isoformat(),
                "ended_at": cell.time.now.isoformat(),
                "output_duration_seconds": 0,
                "outcome": "stopped",
                "reason": "unrelated",
            },
            trigger_source="local_button",
            session_id="unrelated",
        )
        await cell.device_post(ref=ref, reports=[terminal])
        assert (await cell.state())["start_block_reason"] == "unresolved_execution"
        assert (await cell.stop()).status_code == 200

    run_cell(case)


@pytest.mark.parametrize("poison_kind", ["schema", "conflict"])
def test_pg_groupfix_positive_stop_receipt_with_poison(run_cell, poison_kind):
    async def case(cell, admin, _):
        ref = await cell.configured()
        stop = (await cell.stop()).json()["request_id"]
        initial = await cell.device_post(ref=ref)
        assert initial.json()["stops"][0]["request_id"] == stop
        receipt = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=stop,
            trigger_source="remote",
        )
        poison = cell.report("fault", ref, {"reason": "fixture"})
        if poison_kind == "schema":
            poison["payload"] = {}
        else:
            # The immutable event sequence belongs to the configured report.
            poison["sequence"] = 1
        for _ in range(2):
            response = await cell.device_post(ref=ref, epoch=1, reports=[poison, receipt])
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["acked_event_ids"] == [receipt["event_id"]]
            assert data["stops"] == data["grants"] == data["candidates"] == []
            assert data["desired_config"] is None and data["retry_after_seconds"] == 30
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM microsched.migarden_report WHERE event_id=$1",
                receipt["event_id"],
            )
            == 1
        )
        assert not await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", poison["event_id"]
        )
        state = await cell.state()
        assert state["stop_request"]["status"] == "stop_confirmed"
        assert state["start_block_reason"] == "reports_need_reconciliation"

    run_cell(case)


def test_pg_groupfix_stop_confirmation_never_reopens(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        stop = (await cell.stop()).json()["request_id"]
        positive = cell.report(
            "stop_processed",
            ref,
            {"outcome": "close_requested"},
            request_id=stop,
            trigger_source="remote",
        )
        response = await cell.device_post(ref=ref, epoch=1, reports=[positive])
        assert response.json()["acked_event_ids"] == [positive["event_id"]]
        assert (await cell.state())["stop_request"]["status"] == "stop_confirmed"
        late = cell.report(
            "request_rejected",
            ref,
            {"reason": "stale_boot"},
            request_id=stop,
            trigger_source="remote",
        )
        response = await cell.device_post(ref=ref, epoch=1, reports=[late])
        assert response.json()["acked_event_ids"] == [late["event_id"]]
        assert response.json()["stops"] == []
        state = await cell.state()
        assert state["stop_request"]["status"] == "stop_confirmed"
        assert state["start_block_reason"] is None
        assert await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", late["event_id"]
        )

    run_cell(case)


def test_pg_groupfix_retains_all_failed_fingerprints_until_each_proven(run_cell, monkeypatch):
    from app.domain.migarden import reports
    from app.domain.migarden.storage import Rejected

    blocked = set()
    original = reports.project

    async def intermittent(db, report, row, command):
        if (report.event_id, report.payload.reason) in blocked:
            raise Rejected("synthetic_unavailable_projection")
        await original(db, report, row, command)

    async def case(cell, admin, _):
        ref = await cell.configured()
        first = cell.report("fault", ref, {"reason": "first"})
        second = cell.report("fault", ref, {"reason": "second"}, boot="boot-backlog")
        blocked.update({(first["event_id"], "first"), (second["event_id"], "second")})
        monkeypatch.setattr(reports, "project", intermittent)
        for report in (first, second):
            response = await cell.device_post(ref=ref, reports=[report])
            assert response.json()["acked_event_ids"] == []
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"

        # An acceptable alternative body under the same ID cannot prove the failed original.
        alternative = first | {
            "event_id": second["event_id"],
            "sequence": second["sequence"],
            "boot_id": second["boot_id"],
        }
        response = await cell.device_post(ref=ref, reports=[alternative])
        assert response.json()["acked_event_ids"] == [second["event_id"]]
        blocked.remove((first["event_id"], "first"))
        response = await cell.device_post(ref=ref, reports=[first])
        assert response.json()["acked_event_ids"] == [first["event_id"]]
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"
        assert await admin.fetchval(
            "SELECT report_reconciliation IS NOT NULL FROM microsched.migarden_zone"
        )

    run_cell(case)


def test_pg_groupfix_exact_subset_recovery_uses_report_boot_not_packet_boot(run_cell, monkeypatch):
    from app.domain.migarden import reports
    from app.domain.migarden.storage import Rejected

    blocked = set()
    project = reports.project

    async def intermittent(db, report, row, command):
        if report.event_id in blocked:
            raise Rejected("synthetic_unavailable_projection")
        await project(db, report, row, command)

    async def case(cell, admin, _):
        ref = await cell.configured()
        first = cell.report("fault", ref, {"reason": "first"})
        second = cell.report("fault", ref, {"reason": "second"}, boot="boot-backlog")
        blocked.update(event["event_id"] for event in (first, second))
        monkeypatch.setattr(reports, "project", intermittent)
        response = await cell.device_post(ref=ref, reports=[first, second])
        assert response.json()["acked_event_ids"] == []
        assert (
            await admin.fetchval(
                "SELECT jsonb_array_length(report_reconciliation->'entries') "
                "FROM microsched.migarden_zone"
            )
            == 2
        )

        cell.tick()
        blocked.remove(first["event_id"])
        response = await cell.device_post(ref=ref, boot="boot-2", reports=[first])
        assert response.json()["acked_event_ids"] == [first["event_id"]]
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"
        retained = await admin.fetchval(
            "SELECT report_reconciliation->'entries'->0->>1 FROM microsched.migarden_zone"
        )
        assert retained == "boot-backlog"

        cell.tick()
        blocked.remove(second["event_id"])
        response = await cell.device_post(ref=ref, boot="boot-2", reports=[second])
        assert response.json()["acked_event_ids"] == [second["event_id"]]
        assert (await cell.state())["start_block_reason"] is None
        assert await admin.fetchval(
            "SELECT report_reconciliation IS NULL FROM microsched.migarden_zone"
        )

    run_cell(case)


def test_pg_groupfix_conflicting_stop_receipts_cannot_publish_ack(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        key = await cell.preview()
        await cell.confirm(key)
        stop = (await cell.stop()).json()["request_id"]
        unknown = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id="unknown-stop-synthetic",
            trigger_source="remote",
        )
        wrong_boot = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=stop,
            boot="boot-unbound",
            trigger_source="remote",
        )
        wrong_kind = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=key,
            trigger_source="remote",
        )
        good = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=stop,
            trigger_source="remote",
        )
        bad_ids = [item["event_id"] for item in (unknown, wrong_boot, wrong_kind)]
        result = (
            await cell.device_post(ref=ref, reports=[good, wrong_kind, wrong_boot, unknown])
        ).json()
        assert result["acked_event_ids"] == [good["event_id"]]
        assert result["grants"] == result["candidates"] == result["stops"] == []
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM microsched.migarden_report WHERE event_id=ANY($1::text[])",
                bad_ids,
            )
            == 0
        )
        state = await cell.state()
        assert state["stop_request"]["status"] == "stop_confirmed"
        assert state["start_request"]["status"] == "canceled"

    run_cell(case)


def test_pg_groupfix_ambiguous_event_id_is_not_acked(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        first = cell.report("fault", ref, {"reason": "ordinary"})
        other_body = first | {"payload": {"reason": "different"}}
        invalid_variant = first | {"payload": {}}
        unrelated = cell.report("fault", ref, {"reason": "unrelated"})
        response = await cell.device_post(
            ref=ref, reports=[first, other_body, invalid_variant, unrelated, unrelated]
        )
        assert response.json()["acked_event_ids"] == [unrelated["event_id"]]
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM microsched.migarden_report WHERE event_id=$1",
                first["event_id"],
            )
            == 0
        )
        assert (
            await admin.fetchval(
                "SELECT jsonb_array_length(report_reconciliation->'entries') "
                "FROM microsched.migarden_zone"
            )
            == 3
        )

    run_cell(case)


def test_pg_groupfix_outer_commit_failure_has_no_wire_ack(run_cell, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    async def fail_commit(_):
        raise RuntimeError("synthetic_outer_commit_failure")

    async def case(cell, admin, _):
        ref = await cell.configured()
        stop = (await cell.stop()).json()["request_id"]
        receipt = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=stop,
            trigger_source="remote",
        )
        poison = cell.report("fault", ref, {})
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", fail_commit)
            response = await cell.device_post(ref=ref, epoch=1, reports=[receipt, poison])
            assert response.status_code == 500
            assert "acked_event_ids" not in response.text
        assert not await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", receipt["event_id"]
        )
        assert (await cell.state())["stop_request"]["status"] == "stop_requested"
        response = await cell.device_post(ref=ref, epoch=1, reports=[receipt, poison])
        assert response.json()["acked_event_ids"] == [receipt["event_id"]]
        assert (await cell.state())["stop_request"]["status"] == "stop_confirmed"

    run_cell(case, raise_app_exceptions=False)


def test_pg_groupfix_ordered_stop_confirmation_preserves_stale_terminal(run_cell):
    async def case(cell, admin, _):
        ref = await cell.configured()
        old_stop = (await cell.stop()).json()["request_id"]
        cell.tick()
        await cell.device_post(ref=ref, boot="boot-2")
        stop = (await cell.stop()).json()["request_id"]
        assert stop != old_stop
        positive = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            boot="boot-2",
            request_id=stop,
            trigger_source="remote",
        )
        negative = cell.report(
            "stop_processed",
            ref,
            {"outcome": "unconfirmed"},
            boot="boot-2",
            request_id=stop,
            trigger_source="remote",
        )
        cell.tick()
        response = await cell.device_post(
            ref=ref, boot="boot-2", epoch=1, reports=[negative, positive]
        )
        assert response.json()["acked_event_ids"] == [negative["event_id"], positive["event_id"]]
        assert response.json()["stops"] == []
        late = cell.report(
            "request_rejected",
            ref,
            {"reason": "stale_boot"},
            request_id=old_stop,
            trigger_source="remote",
        )
        response = await cell.device_post(ref=ref, boot="boot-2", epoch=1, reports=[late])
        assert response.json()["acked_event_ids"] == [late["event_id"]]
        assert response.json()["stops"] == []
        old = await admin.fetchrow(
            "SELECT status,reason FROM microsched.migarden_command WHERE request_id=$1", old_stop
        )
        assert dict(old) == {"status": "stop_stale", "reason": "reconciled_by_stop:" + stop}
        state = await cell.state()
        assert state["stop_request"]["status"] == "stop_confirmed"
        assert state["start_block_reason"] is None

    run_cell(case)
