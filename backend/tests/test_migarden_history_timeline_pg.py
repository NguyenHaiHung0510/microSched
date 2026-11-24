"""N02 session pagination and bounded Hanoi-date totals on synthetic PG only."""

import pytest
from test_migarden_pg import ROOT
from test_migarden_pg import run_cell as run_cell

pytestmark = pytest.mark.pg


def test_pg_history_sessions_keep_evidence_and_stops_across_pages(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        started = cell.report(
            "session_started",
            ref,
            {"started_at": "2026-11-17T16:59:40Z", "duration_seconds": 60},
            session_id="cross-midnight",
            trigger_source="schedule",
            occurred_at="2026-11-17T16:59:40Z",
        )
        ended = cell.report(
            "session_ended",
            ref,
            {
                "started_at": "2026-11-17T16:59:40Z",
                "ended_at": "2026-11-17T17:00:40Z",
                "output_duration_seconds": 60,
                "outcome": "completed",
                "reason": None,
            },
            session_id="cross-midnight",
            trigger_source="schedule",
            occurred_at="2026-11-17T17:00:40Z",
        )
        unknown = cell.report(
            "session_ended",
            ref,
            {
                "started_at": None,
                "ended_at": None,
                "output_duration_seconds": None,
                "outcome": "unknown",
                "reason": "REBOOT_INTERRUPTED",
            },
            session_id="unknown-actual",
            trigger_source="local_button",
            occurred_at=None,
            time_quality="unknown",
        )
        local_stop = cell.report(
            "stop_processed",
            None,
            {"outcome": "already_off"},
            trigger_source="local_button",
        )
        remote_stop = (await cell.stop()).json()["request_id"]
        receipt = cell.report(
            "stop_processed",
            ref,
            {"outcome": "already_off"},
            request_id=remote_stop,
            trigger_source="remote",
        )
        packet = await cell.device_post(
            ref=ref, reports=[started, ended, unknown, receipt, local_stop]
        )
        assert len(packet.json()["acked_event_ids"]) == 5
        route = ROOT + "/history"
        params = {"view": "sessions", "limit": 1}
        items = []
        for _ in range(8):
            result = await cell.human.get(route, params=params)
            assert result.status_code == 200, result.text
            page = result.json()
            items.extend(page["items"])
            assert page["totals"] is None
            if page["next_cursor"] is None:
                break
            params["cursor"] = page["next_cursor"]
        else:
            pytest.fail("cursor never reached the final timeline page")
        assert len(items) == len({item["id"] for item in items}) == 4
        sessions = {item["session_id"]: item for item in items if item["kind"] == "session"}
        finished = sessions["cross-midnight"]
        assert finished["duration_seconds"] == 60 and finished["config_known"]
        assert finished["started_at"].startswith("2026-11-17T16:59:40")
        assert finished["ended_at"].startswith("2026-11-17T17:00:40")
        assert {event["kind"] for event in finished["evidence"]} == {
            "session_started",
            "session_ended",
        }
        assert all(event["received_at"] for event in finished["evidence"])
        assert sessions["unknown-actual"]["duration_seconds"] is None
        assert sessions["unknown-actual"]["ended_at"] is None
        stops = {
            item["source"]: item
            for item in items
            if item["kind"] in ("remote_stop", "stop_processed")
        }
        assert stops["local_button"]["result"] == "already_off"
        assert stops["remote"]["evidence"][0]["result"] == "already_off"
        assert all(item["duration_seconds"] is None for item in stops.values())
        filtered = (
            await cell.human.get(route, params={"view": "sessions", "result": "stop_processed"})
        ).json()
        assert len(filtered["items"]) == 2

        legacy = (await cell.human.get(route)).json()
        assert set(legacy) == {"items", "next_cursor", "coverage"}
        assert {item["kind"] for item in legacy["items"]} >= {"session_started", "session_ended"}

    run_cell(case)


def test_pg_history_totals_use_entire_terminal_date_filter_not_cursor(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        for session_id, source, start, end, seconds, outcome in (
            ("crossing", "schedule", "16:59:40", "17:00:40", 60, "completed"),
            ("newest", "local_button", "17:00:40", "17:01:00", 20, "stopped"),
            ("previous", "schedule", "16:59:00", "16:59:30", 30, "completed"),
            ("unknown", "local_button", "17:00:30", "17:00:35", None, "unknown"),
        ):
            report = cell.report(
                "session_ended",
                ref,
                {
                    "started_at": f"2026-11-17T{start}Z",
                    "ended_at": f"2026-11-17T{end}Z",
                    "output_duration_seconds": seconds,
                    "outcome": outcome,
                    "reason": None,
                },
                session_id=session_id,
                trigger_source=source,
                occurred_at=f"2026-11-17T{end}Z",
            )
            response = await cell.device_post(ref=ref, reports=[report])
            assert response.json()["acked_event_ids"] == [report["event_id"]]
        route = ROOT + "/history"
        params = {"view": "sessions", "limit": 1, "from_day": "2026-11-18", "to_day": "2026-11-18"}
        result = await cell.human.get(route, params=params)
        assert result.status_code == 200, result.text
        first = result.json()
        assert len(first["items"]) == 1 and first["next_cursor"]
        assert first["totals"] == dict(
            recorded_seconds=80, schedule_seconds=60, remote_seconds=None, local_button_seconds=20
        )
        next_page = (
            await cell.human.get(route, params=params | {"cursor": first["next_cursor"]})
        ).json()
        assert next_page["totals"] == first["totals"]
        local = (await cell.human.get(route, params=params | {"source": "local_button"})).json()
        assert (
            local["totals"]["recorded_seconds"] == 20
            and local["totals"]["schedule_seconds"] is None
        )
        unknown = (await cell.human.get(route, params=params | {"result": "unknown"})).json()
        assert (
            unknown["items"][0]["duration_seconds"] is None
            and unknown["totals"]["recorded_seconds"] is None
        )
        wide = (await cell.human.get(route, params=params | {"from_day": "2026-10-01"})).json()
        assert wide["totals"] is None

    run_cell(case)
