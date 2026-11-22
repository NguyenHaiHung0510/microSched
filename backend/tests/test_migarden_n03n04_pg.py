"""Synthetic PostgreSQL oracles for idle SQL, telemetry and immutable trace."""

import json
from datetime import timedelta, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from test_migarden_pg import CONFIG, DEVICE, HUMAN, ROOT
from test_migarden_pg import run_cell as base_cell

from app.domain.migarden.credentials import digest
from app.web import deps
from app.web.migarden_quiet import EXTENSION

pytestmark = pytest.mark.pg


@pytest.fixture
def run_cell(pg_dsn, monkeypatch):
    return base_cell.__wrapped__(pg_dsn, monkeypatch)


def health(cell, **updates):
    return {
        "build_id": "synthetic-n03n04",
        "boot_id": "boot-1",
        "sampled_at": cell.time.now.isoformat(),
        "time_quality": "synced",
        "uptime_seconds": 12345,
        "reset_reason": 1,
        "free_heap": 180000,
        "minimum_heap": 150000,
        "wifi_phase": "CONNECTED",
        "sync_status": "OK",
        "pending_reports": 0,
        "evidence_gaps": 0,
    } | updates


async def post(cell, ref, *, reports=(), sample=None, boot="boot-1", epoch=0):
    packet = {
        "protocol": "migarden.zone-a.v1",
        "device_id": "qa-n01-test",
        "boot_id": boot,
        "control_epoch": epoch,
        "reports": list(reports),
        "snapshot": {
            "observed_at": cell.time.now.isoformat(),
            "time_quality": "synced",
            "output": "off",
            "active_session": None,
            "applied_config_ref": ref,
            "ready": True,
            "blocked_reason": None,
        },
    }
    if sample is not None:
        packet["health"] = sample
    return await cell.device.post(DEVICE, json=packet, headers={"X-MiGarden-Extension": EXTENSION})


def test_idle_zero_sql_connections_lease_restart_reconnect_and_six_hour_boundary(
    run_cell, monkeypatch
):
    async def case(cell, admin, _):
        ref = await cell.configured()
        assert (await post(cell, ref)).json()["extension"] == EXTENSION
        gate = cell.device._transport.app.state.migarden_quiet
        clock = [gate.now() + 301]
        gate.clock = lambda: clock[0]
        from app.web.routers import migarden_device

        monkeypatch.setattr(migarden_device, "monotonic", lambda: clock[0])
        counts = {"sql": 0, "connections": 0, "checkout": 0}
        engine = deps.get_sessionmaker().kw["bind"].sync_engine

        def sql(*_):
            counts["sql"] += 1

        def connect(*_):
            counts["connections"] += 1

        def checkout(*_):
            counts["checkout"] += 1

        for name, fn in (
            ("before_cursor_execute", sql),
            ("connect", connect),
            ("checkout", checkout),
        ):
            event.listen(engine, name, fn)
        try:
            for _ in range(70):  # 350 seconds, visible firmware keeps asking Fly
                clock[0] += 5
                cell.tick(5)
                response = await post(cell, ref, sample=health(cell))
                assert response.status_code == 202
                assert response.json() == {"protocol": "migarden.wait.v1", "retry_after_seconds": 5}
            assert counts == {"sql": 0, "connections": 0, "checkout": 0}
            clock[0] = gate.reconcile_at
            assert (await post(cell, ref)).status_code == 200
            assert counts["sql"] > 0 and counts["checkout"] > 0
            gate.present()
            assert (await post(cell, ref)).status_code == 200
            clock[0] += 301
            assert (await post(cell, ref)).status_code == 202
            del cell.device._transport.app.state.migarden_quiet
            assert (await post(cell, ref)).status_code == 200  # finite cold hydrate
            new_gate = cell.device._transport.app.state.migarden_quiet
            new_gate.clock = lambda: clock[0]
            new_gate.human_until = 0
            new_gate.reconcile_at = clock[0] + 21600
            assert (await post(cell, ref)).status_code == 202
            await admin.execute("UPDATE microsched.migarden_zone SET revoked_at=now()")
            assert (await post(cell, ref, epoch=1)).status_code == 401
            assert (await post(cell, ref, boot="real-new-boot", epoch=2)).status_code == 503
        finally:
            for name, fn in (
                ("before_cursor_execute", sql),
                ("connect", connect),
                ("checkout", checkout),
            ):
                event.remove(engine, name, fn)

    run_cell(case)


def test_wrong_auth_cold_start_cannot_poison_valid_event_or_stop(run_cell, monkeypatch):
    async def case(cell, admin, __):
        ref = await cell.configured()
        app = cell.device._transport.app
        if hasattr(app.state, "migarden_quiet"):
            del app.state.migarden_quiet
        headers = {"Authorization": "Bearer " + "w" * 43, "X-MiGarden-Extension": EXTENSION}
        # First malformed/unknown credential cannot fill the genuine retry clock.
        response = await cell.device.post(DEVICE, json={"bad": True}, headers=headers)
        assert response.status_code == 422
        packet = {
            "protocol": "migarden.zone-a.v1",
            "device_id": "qa-n01-test",
            "boot_id": "boot-1",
            "control_epoch": 0,
            "reports": [],
            "snapshot": {
                "observed_at": cell.time.now.isoformat(),
                "time_quality": "synced",
                "output": "off",
                "active_session": None,
                "applied_config_ref": ref,
                "ready": True,
                "blocked_reason": None,
            },
        }
        assert (await cell.device.post(DEVICE, json=packet, headers=headers)).status_code == 401
        quiet = app.state.migarden_quiet
        assert quiet.retry_at == 0 and quiet.failures == 0
        clock = [quiet.now()]
        quiet.clock = lambda: clock[0]
        from app.web.routers import migarden_device

        monkeypatch.setattr(migarden_device, "monotonic", lambda: clock[0])
        engine = deps.get_sessionmaker().kw["bind"].sync_engine
        sql_calls = []

        def sql(*_):
            sql_calls.append(1)

        event.listen(engine, "before_cursor_execute", sql)
        try:
            for _ in range(40):
                clock[0] += 5
                assert (
                    await cell.device.post(DEVICE, json=packet, headers=headers)
                ).status_code == 503
            assert sql_calls == []
            report = cell.report("config_applied", ref, {})
            response = await post(cell, ref, reports=[report])
            assert response.status_code == 200 and response.json()["acked_event_ids"] == [
                report["event_id"]
            ]
            assert quiet.retry_at == 0
            stop = (await cell.stop()).json()
            response = await post(cell, ref)
            assert response.status_code == 200
            assert response.json()["stops"][0]["request_id"] == stop["request_id"]

            # A credential bound out of band must recover without leaving the
            # firmware permanently blocked by an earlier routing hint.
            await admin.execute(
                "UPDATE microsched.migarden_zone SET token_hash=$1", digest("w" * 43)
            )
            response = await cell.device.post(DEVICE, json=packet, headers=headers)
            assert response.status_code == 503
            assert response.headers["retry-after"] == "5"
            clock[0] = quiet.routing_until
            response = await cell.device.post(DEVICE, json=packet, headers=headers)
            assert response.status_code == 200 and response.json()["extension"] == EXTENSION
        finally:
            event.remove(engine, "before_cursor_execute", sql)

    run_cell(case)


def test_known_db_fault_retries_within_sixty_seconds_and_recovers_ack(run_cell, monkeypatch):
    async def case(cell, admin, _):
        ref = await cell.configured()
        assert (await post(cell, ref)).status_code == 200
        quiet = cell.device._transport.app.state.migarden_quiet
        clock = [quiet.now()]
        quiet.clock = lambda: clock[0]
        report = cell.report("config_applied", ref, {})

        async def fail_commit(_):
            raise RuntimeError("synthetic_db_down")

        for delay in (5, 15, 30, 60):
            with monkeypatch.context() as patch:
                patch.setattr(AsyncSession, "commit", fail_commit)
                assert (await post(cell, ref, reports=[report])).status_code == 500
            assert quiet.retry_at == clock[0] + delay
            assert (await post(cell, ref, reports=[report])).status_code == 202
            clock[0] += delay
        response = await post(cell, ref, reports=[report])
        assert response.status_code == 200 and response.json()["acked_event_ids"] == [
            report["event_id"]
        ]
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM microsched.migarden_report WHERE event_id=$1",
                report["event_id"],
            )
            == 1
        )

    run_cell(case, raise_app_exceptions=False)


def test_state_read_actual_activity_deadline_and_short_legacy_lease(run_cell, monkeypatch):
    async def case(cell, _, __):
        ref = await cell.configured()
        assert (await post(cell, ref)).status_code == 200
        quiet = cell.device._transport.app.state.migarden_quiet
        clock = [quiet.now()]
        quiet.clock = lambda: clock[0]
        quiet.human_until = 0
        start = clock[0]
        from app.web.routers import migarden_device

        monkeypatch.setattr(migarden_device, "monotonic", lambda: clock[0])
        # Browser sends the remaining actual activity window, not a new lease.
        for elapsed in range(0, 300, 5):
            clock[0] = start + elapsed
            response = await cell.human.get(
                ROOT + "/state",
                headers={"X-MiGarden-Visible": "1", "X-MiGarden-Active-For": str(300 - elapsed)},
            )
            assert response.status_code == 200
            assert quiet.human_until == start + 300
            assert (await post(cell, ref)).status_code == 200
        clock[0] = start + 301
        assert (await post(cell, ref)).status_code == 202
        response = await cell.human.get(ROOT + "/state", headers={"X-MiGarden-Visible": "1"})
        assert response.status_code == 200 and quiet.human_until == clock[0] + 30
        clock[0] += 31
        assert (await post(cell, ref)).status_code == 202

    run_cell(case)


def test_health_max_hour_no_ack_on_outer_failure_and_optional_fault_isolation(
    run_cell, monkeypatch
):
    async def case(cell, admin, _):
        await admin.execute("TRUNCATE microsched.migarden_health")
        ref = await cell.configured()
        assert (await post(cell, ref, sample=health(cell))).status_code == 200
        for _ in range(10):
            cell.tick()
            assert (await post(cell, ref, sample=health(cell, free_heap=170000))).status_code == 200
        assert await admin.fetchval("SELECT count(*) FROM microsched.migarden_health") == 1
        assert (await post(cell, ref, sample={"invalid": "optional"})).status_code == 200
        cell.time.now += timedelta(hours=1)
        await admin.execute("""CREATE FUNCTION public.synthetic_health_fail() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic_health_fault'; END $$;
            CREATE TRIGGER synthetic_health_fail BEFORE INSERT ON microsched.migarden_health
            FOR EACH ROW EXECUTE FUNCTION public.synthetic_health_fail()""")
        try:
            report = cell.report("config_applied", ref, {})
            response = await post(cell, ref, reports=[report], sample=health(cell))
            assert (
                response.status_code == 200
                and report["event_id"] in response.json()["acked_event_ids"]
            )
            assert await admin.fetchval("SELECT count(*) FROM microsched.migarden_health") == 1
        finally:
            await admin.execute(
                "DROP TRIGGER synthetic_health_fail ON microsched.migarden_health; "
                "DROP FUNCTION public.synthetic_health_fail()"
            )
        assert (await post(cell, ref, sample=health(cell))).status_code == 200
        assert await admin.fetchval("SELECT count(*) FROM microsched.migarden_health") == 2
        report = cell.report("config_applied", ref, {})

        async def fail_commit(_):
            raise RuntimeError("synthetic_outer_commit_failure")

        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", fail_commit)
            response = await post(cell, ref, reports=[report], sample=health(cell))
            assert response.status_code == 500 and "acked_event_ids" not in response.text
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM microsched.migarden_report WHERE event_id=$1",
                report["event_id"],
            )
            == 0
        )

    run_cell(case, raise_app_exceptions=False)


def test_pending_off_shared_projection_versions_pagination_policy_only_and_late_ack(run_cell):
    async def case(cell, _, __):
        ref1 = await cell.configured()
        cell.tick()
        form = CONFIG | {
            "expected_config_ref": ref1,
            "schedule": CONFIG["schedule"] | {"enabled": False},
        }
        saved = (await cell.human.put(ROOT + "/config", json=form, headers=HUMAN)).json()
        ref2 = saved["desired"]["config_ref"]
        state = await cell.state()
        daily = (await cell.human.get(ROOT + "/daily")).json()
        assert state["config"]["schedule_projection"] == daily["schedule_projection"]
        assert daily["schedule_projection"]["saved"]["status"] == "paused"
        assert daily["schedule_projection"]["possible_previous_run"] is True
        events = (await cell.human.get(ROOT + "/history?view=sessions&category=all&limit=1")).json()
        ids = []
        while True:
            ids += [row["id"] for row in events["items"]]
            if not events["next_cursor"]:
                break
            events = (
                await cell.human.get(
                    ROOT + "/history",
                    params={
                        "view": "sessions",
                        "category": "all",
                        "limit": 1,
                        "cursor": events["next_cursor"],
                    },
                )
            ).json()
        assert len(ids) == len(set(ids)) and "v:" + ref2 in ids
        detail = (await cell.human.get(ROOT + "/config/versions/" + ref2)).json()
        assert detail["previous_ref"] == ref1 and detail["evidence"] == []
        cell.tick()
        applied = cell.report("config_applied", ref2, {})
        await cell.device_post(ref=ref2, reports=[applied])
        assert (await cell.state())["config"]["schedule_projection"]["last_confirmed"][
            "status"
        ] == "paused"
        # A current-timestamp old-ref snapshot with a late report cannot regress.
        cell.tick()
        old = cell.report("config_applied", ref1, {})
        await cell.device_post(ref=ref1, reports=[old])
        assert (await cell.state())["config"]["applied"]["config_ref"] == ref2
        policy_form = form | {
            "expected_config_ref": ref2,
            "policy": CONFIG["policy"] | {"manual_duration_seconds": 300},
        }
        policy = (await cell.human.put(ROOT + "/config", json=policy_form, headers=HUMAN)).json()
        ref3 = policy["desired"]["config_ref"]
        versions = (await cell.human.get(ROOT + "/config/versions")).json()
        assert {row["config_ref"] for row in versions["items"]} == {ref1, ref2}
        policy_detail = (await cell.human.get(ROOT + "/config/versions/" + ref3)).json()
        assert policy_detail["schedule_changed"] is False
        assert (await cell.human.get(ROOT + "/config/versions/missing-version")).status_code == 404

    run_cell(case)


def test_config_trace_preserves_raw_future_clock_without_claiming_application_time(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        cell.tick()
        reported = cell.time.now + timedelta(days=2)
        future = cell.report("config_applied", ref, {}) | {"occurred_at": reported.isoformat()}
        response = await cell.device_post(ref=ref, reports=[future])
        assert future["event_id"] in response.json()["acked_event_ids"]
        data = (await cell.human.get(ROOT + "/config/versions/" + ref)).json()
        evidence = next(item for item in data["evidence"] if item["event_id"] == future["event_id"])
        assert evidence["occurred_at"] is not None
        assert evidence["applied_at"] is None
        assert evidence["received_at"] is not None

        timezone_vn = timezone(timedelta(hours=7))
        criteria = {"view": "sessions", "category": "configuration"}
        event_id = "a:" + future["event_id"]
        today = cell.time.now.astimezone(timezone_vn).date().isoformat()
        events = (
            await cell.human.get(
                ROOT + "/history", params=criteria | {"from_day": today, "to_day": today}
            )
        ).json()
        event = next(item for item in events["items"] if item["id"] == event_id)
        assert event["occurred_at"] is None and event["received_at"] is not None
        other = reported.astimezone(timezone_vn).date().isoformat()
        events = (
            await cell.human.get(
                ROOT + "/history", params=criteria | {"from_day": other, "to_day": other}
            )
        ).json()
        assert all(item["id"] != event_id for item in events["items"])

    run_cell(case)


def test_health_history_retains_each_row_when_receive_times_tie(run_cell):
    async def case(cell, admin, _):
        await admin.execute("TRUNCATE microsched.migarden_health")
        now = cell.time.now
        hour = now.replace(minute=0, second=0, microsecond=0)
        for offset in range(3):
            await admin.execute(
                "INSERT INTO microsched.migarden_health "
                "(zone_id,hour_start,received_at,boot_id,sample) "
                "VALUES ('zone-a',$1,$2,'boot-1',$3::jsonb)",
                hour - timedelta(hours=offset),
                now,
                json.dumps(health(cell, uptime_seconds=1200 + offset)),
            )
        payload = (await cell.human.get(ROOT + "/health", params={"limit": 1})).json()
        samples = []
        while True:
            samples.extend(row["sample"]["uptime_seconds"] for row in payload["items"])
            cursor = payload["next_cursor"]
            if cursor is None:
                break
            assert len(samples) <= 3
            payload = (
                await cell.human.get(ROOT + "/health", params={"limit": 1, "cursor": cursor})
            ).json()
        assert sorted(samples) == [1200, 1201, 1202]

    run_cell(case)
