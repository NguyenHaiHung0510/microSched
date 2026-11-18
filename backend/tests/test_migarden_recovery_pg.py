"""A166 recovery and presence tests on the explicitly supplied disposable cell."""

import pytest
from test_migarden_pg import ROOT
from test_migarden_pg import run_cell as run_cell

pytestmark = pytest.mark.pg


async def interrupted(cell, source="local_button", reason="REBOOT_INTERRUPTED", suffix="one"):
    ref = await cell.configured()
    request = "button-" + suffix if source == "local_button" else None
    if source == "remote":
        request = await cell.preview()
        assert (await cell.confirm(request)).status_code == 200
        await cell.device_post(ref=ref)
        received = cell.report(
            "request_received", ref, {}, request_id=request, trigger_source=source
        )
        assert (await cell.device_post(ref=ref, reports=[received])).json()["grants"]
    start = cell.time.now.isoformat()
    context = dict(session_id="interrupted-" + suffix, request_id=request, trigger_source=source)
    began = cell.report(
        "session_started", ref, {"started_at": start, "duration_seconds": 45}, **context
    )
    cell.tick()
    await cell.device_post(ref=ref, reports=[began])
    cell.tick(3)
    terminal = cell.report(
        "session_ended",
        ref,
        {
            "started_at": start,
            "ended_at": None,
            "output_duration_seconds": None,
            "outcome": "unknown",
            "reason": reason,
        },
        boot="boot-recovery",
        **context,
    )
    response = await cell.device_post(ref=ref, boot="boot-recovery", reports=[terminal])
    assert response.json()["acked_event_ids"] == [terminal["event_id"]]
    assert (await cell.state())["start_block_reason"] == "unresolved_execution"
    cell.tick()
    recovered = cell.report(
        "recovered",
        ref,
        {"reason": "REBOOT_INTERRUPTED_RECOVERED"},
        boot="boot-recovery",
        **context,
    )
    return ref, terminal, recovered


@pytest.mark.parametrize("source", ["local_button", "remote"])
def test_pg_recovery_specific_interruption_allows_only_new_intent(run_cell, source):
    async def case(cell, admin, _):
        ref, terminal, recovered = await interrupted(cell, source)
        result = await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])
        assert result.json()["acked_event_ids"] == [recovered["event_id"]]
        assert result.json()["candidates"] == result.json()["grants"] == []
        state = await cell.state()
        assert state["start_block_reason"] is None
        if source == "remote":
            assert state["start_request"]["status"] == "recovered"
        row = await admin.fetchrow(
            "SELECT outcome,reason,output_duration_seconds,ended_event_id "
            "FROM microsched.migarden_session WHERE session_id=$1",
            recovered["session_id"],
        )
        assert dict(row) == dict(
            outcome="unknown",
            reason="REBOOT_INTERRUPTED",
            output_duration_seconds=None,
            ended_event_id=terminal["event_id"],
        )
        raw = await admin.fetchval(
            "SELECT body->'payload'->>'reason' FROM microsched.migarden_report WHERE event_id=$1",
            terminal["event_id"],
        )
        assert raw == "REBOOT_INTERRUPTED"
        history = (await cell.human.get(ROOT + "/history")).json()["items"]
        unknown = next(row for row in history if row["kind"] == "session_ended")
        assert unknown["result"] == "unknown" and unknown["duration_seconds"] is None
        assert any(
            row["kind"] == "recovered" and row["session_id"] == recovered["session_id"]
            for row in history
        )
        assert (await cell.human.get(ROOT + "/daily")).json()["days"][-1][
            source + "_seconds"
        ] is None
        # Exact retry has no replay; a newly confirmed intent has a different ID.
        again = (await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])).json()
        assert again["acked_event_ids"] == [recovered["event_id"]] and not again["grants"]
        new_request = await cell.preview()
        assert new_request != recovered["request_id"]
        assert (await cell.confirm(new_request)).json()["status"] == "pending"
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM microsched.migarden_report WHERE event_id=$1",
                recovered["event_id"],
            )
            == 1
        )

    run_cell(case)


@pytest.mark.parametrize(
    "mismatch",
    [
        "session_id",
        "request_id",
        "config_ref",
        "trigger_source",
        "boot_id",
        "sequence",
        "occurred_at",
        "terminal",
    ],
)
def test_pg_recovery_mismatch_is_not_acknowledged_or_settled(run_cell, mismatch):
    async def case(cell, admin, _):
        ref, terminal, recovered = await interrupted(
            cell, reason="STORAGE_FAULT" if mismatch == "terminal" else "REBOOT_INTERRUPTED"
        )
        changes = {
            "session_id": "different-session",
            "request_id": "different-request",
            "config_ref": "different-config",
            "trigger_source": "remote",
            "boot_id": "boot-1",
            "sequence": terminal["sequence"] - 1,
            "occurred_at": "2026-11-17T00:00:00Z",
        }
        if mismatch != "terminal":
            recovered[mismatch] = changes[mismatch]
        result = (await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])).json()
        assert result["acked_event_ids"] == result["grants"] == result["candidates"] == []
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"
        assert not await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", recovered["event_id"]
        )

    run_cell(case)


def test_pg_recovery_does_not_clear_other_uncertainty_or_later_conflict(run_cell):
    async def case(cell, admin, _):
        ref, terminal, recovered = await interrupted(cell, "remote")
        other = cell.report(
            "session_ended",
            ref,
            {
                "started_at": None,
                "ended_at": None,
                "output_duration_seconds": None,
                "outcome": "unknown",
                "reason": "STORAGE_FAULT",
            },
            boot="boot-recovery",
            session_id="unrelated-storage",
            trigger_source="local_button",
        )
        await cell.device_post(ref=ref, boot="boot-recovery", reports=[other])
        result = (await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])).json()
        assert result["acked_event_ids"] == [recovered["event_id"]]
        assert (await cell.state())["start_block_reason"] == "unresolved_execution"
        assert (await cell.state())["start_request"]["status"] == "recovered"
        assert (
            await admin.fetchval(
                "SELECT outcome FROM microsched.migarden_session "
                "WHERE session_id='unrelated-storage'"
            )
            == "unknown"
        )
        # A contradictory later terminal cannot manufacture a measured completion.
        contradiction = terminal | {
            "event_id": "contradictory-terminal",
            "sequence": cell.sequence + 1,
            "payload": terminal["payload"]
            | {
                "outcome": "completed",
                "reason": None,
                "ended_at": cell.time.now.isoformat(),
                "output_duration_seconds": 45,
            },
        }
        response = await cell.device_post(ref=ref, boot="boot-recovery", reports=[contradiction])
        assert response.json()["acked_event_ids"] == []
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"
        assert (await cell.state())["start_request"]["status"] == "recovered"
        assert (
            await admin.fetchval(
                "SELECT ended_event_id FROM microsched.migarden_session WHERE session_id=$1",
                terminal["session_id"],
            )
            == terminal["event_id"]
        )

    run_cell(case)


def test_pg_recovery_dependency_retries_across_boot_order_without_losing_proof(run_cell):
    async def case(cell, _, __):
        ref, _, original = await interrupted(cell)
        # Previous valid evidence belongs to boot-recovery; a new boot may settle it.
        cell.tick()
        recovery = cell.report(
            "recovered",
            ref,
            {"reason": "REBOOT_INTERRUPTED_RECOVERED"},
            boot="aaa-next",
            session_id=original["session_id"],
            request_id=original["request_id"],
            trigger_source=original["trigger_source"],
        )
        result = (await cell.device_post(ref=ref, boot="aaa-next", reports=[recovery])).json()
        assert result["acked_event_ids"] == [recovery["event_id"]]
        assert (await cell.state())["start_block_reason"] is None
        cell.tick()
        await cell.device_post(ref=ref, boot="last-boot")
        retry = (await cell.device_post(ref=ref, boot="last-boot", reports=[recovery])).json()
        assert retry["acked_event_ids"] == [recovery["event_id"]]
        assert retry["grants"] == retry["candidates"] == []

    run_cell(case)


def test_pg_presence_expires_without_activity_and_skips_drain_stop_and_grant(run_cell, monkeypatch):
    from app.web import migarden_presence

    seconds = [100.0]
    monkeypatch.setattr(migarden_presence, "monotonic", lambda: seconds[0])

    async def case(cell, _, __):
        ref = await cell.configured()
        seconds[0] += 31
        for _ in range(3):
            assert (await cell.human.get(ROOT + "/state")).status_code == 200
            assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] is None
        await cell.human.get(ROOT + "/state", headers={"X-MiGarden-Visible": "1"})
        assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] == 2
        event = cell.report("fault", ref, {"reason": "synthetic-receipt"})
        assert (await cell.device_post(ref=ref, reports=[event])).json()[
            "retry_after_seconds"
        ] is None
        assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] == 2
        seconds[0] += 30
        assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] is None
        request = await cell.preview()
        await cell.confirm(request)
        candidate = (await cell.device_post(ref=ref)).json()
        assert candidate["candidates"] and candidate["retry_after_seconds"] is None
        receipt = cell.report(
            "request_received", ref, {}, request_id=request, trigger_source="remote"
        )
        grant = (await cell.device_post(ref=ref, reports=[receipt])).json()
        assert grant["grants"] and grant["retry_after_seconds"] is None
        assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] is None
        stop = (await cell.stop()).json()["request_id"]
        result = (await cell.device_post(ref=ref)).json()
        assert result["stops"][0]["request_id"] == stop and result["retry_after_seconds"] is None
        poison = cell.report("fault", ref, {})
        result = (await cell.device_post(ref=ref, reports=[poison])).json()
        assert result["retry_after_seconds"] == 30 and result["stops"][0]["request_id"] == stop

    run_cell(case)


def test_pg_presence_only_visible_state_enables_idle_hint(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        cell.human._transport.app.state.migarden_present_until = 0
        assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] is None
        response = await cell.human.get(ROOT + "/state", headers={"X-MiGarden-Visible": "1"})
        assert response.status_code == 200
        assert (await cell.device_post(ref=ref)).json()["retry_after_seconds"] == 2

    run_cell(case)


def test_pg_recovery_crossboot_dependency_is_retryable_and_never_false_acked(run_cell):
    async def case(cell, _, __):
        ref = await cell.configured()
        start = cell.time.now.isoformat()
        common = dict(session_id="crossboot", trigger_source="local_button")
        began = cell.report(
            "session_started", ref, {"started_at": start, "duration_seconds": 45}, **common
        )
        await cell.device_post(ref=ref, reports=[began])
        cell.tick()
        terminal = cell.report(
            "session_ended",
            ref,
            {
                "started_at": start,
                "ended_at": None,
                "output_duration_seconds": None,
                "outcome": "unknown",
                "reason": "REBOOT_INTERRUPTED",
            },
            boot="zzz-terminal",
            **common,
        )
        recovered = cell.report(
            "recovered",
            ref,
            {"reason": "REBOOT_INTERRUPTED_RECOVERED"},
            boot="aaa-current",
            **common,
        )
        result = (
            await cell.device_post(ref=ref, boot="aaa-current", reports=[recovered, terminal])
        ).json()
        assert result["acked_event_ids"] == [terminal["event_id"]]
        assert result["retry_after_seconds"] == 30 and not result["grants"]
        result = (await cell.device_post(ref=ref, boot="aaa-current", reports=[recovered])).json()
        assert result["acked_event_ids"] == [recovered["event_id"]]
        assert (await cell.state())["start_block_reason"] is None

    run_cell(case)


def test_pg_recovery_outer_commit_failure_retains_both_fences(run_cell, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    async def fail_commit(_):
        raise RuntimeError("synthetic_outer_commit_failure")

    async def case(cell, admin, _):
        ref, _, recovered = await interrupted(cell, "remote")
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, "commit", fail_commit)
            response = await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])
            assert response.status_code == 500 and "acked_event_ids" not in response.text
        assert (await cell.state())["start_block_reason"] == "unresolved_execution"
        assert (await cell.state())["start_request"]["status"] == "unknown"
        assert not await admin.fetchval(
            "SELECT 1 FROM microsched.migarden_report WHERE event_id=$1", recovered["event_id"]
        )
        response = await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])
        assert response.json()["acked_event_ids"] == [recovered["event_id"]]
        assert (await cell.state())["start_block_reason"] is None

    run_cell(case, raise_app_exceptions=False)


@pytest.mark.parametrize("boundary", ["active", "stale", "epoch", "unknown_clock"])
def test_pg_recovery_requires_current_fresh_off_context(run_cell, boundary):
    async def case(cell, _, __):
        ref, _, recovered = await interrupted(cell)
        changes = {}
        epoch = 0
        if boundary == "active":
            changes["output"] = "on"
        elif boundary == "stale":
            changes["observed_at"] = "2026-11-17T00:00:00Z"
        elif boundary == "epoch":
            await cell.device_post(ref=ref, boot="boot-recovery", epoch=2)
        else:
            changes.update(observed_at=None, time_quality="unknown")
        response = await cell.device_post(
            ref=ref, boot="boot-recovery", epoch=epoch, reports=[recovered], **changes
        )
        assert response.json()["acked_event_ids"] == []
        assert (await cell.state())["start_block_reason"] == "reports_need_reconciliation"

    run_cell(case)


def test_pg_recovery_never_clears_unidentified_execution(run_cell):
    async def case(cell, admin, _):
        ref, _, recovered = await interrupted(cell)
        await admin.execute("UPDATE microsched.migarden_zone SET unidentified_execution=true")
        result = await cell.device_post(ref=ref, boot="boot-recovery", reports=[recovered])
        assert result.json()["acked_event_ids"] == [recovered["event_id"]]
        assert (await cell.state())["start_block_reason"] == "unresolved_execution"
        assert await admin.fetchval("SELECT unidentified_execution FROM microsched.migarden_zone")

    run_cell(case)
