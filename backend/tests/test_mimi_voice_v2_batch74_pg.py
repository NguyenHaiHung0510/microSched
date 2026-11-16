"""Repair74 full socket/store matrix; only the leased disposable synthetic PG."""

import asyncio
import json
from concurrent.futures import Future
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
import test_mimi_voice_v2_pg as fixtures
from test_mimi_voice_pg import HEADERS, endpoint
from test_mimi_voice_v2 import proposal, speech
from test_mimi_voice_v2_pg import confirm, receive_to, rows, say, snapshot, start, tool, turn

from app.agent import voice_bridge, voice_v2_store
from app.agent.voice_v2_store import receipt_ref

pytestmark = pytest.mark.pg
v2_runtime = fixtures.v2_runtime


def open_voice(rt, issued, cid):
    return rt.client.websocket_connect(endpoint(cid, issued), headers=HEADERS)


def hello(ws, issued):
    ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
    receive_to(ws, "ready")


def stop(ws):
    ws.send_json({"type": "stop"})
    receive_to(ws, "ended")


def created(rt, monkeypatch, titles, *, cid=None, fast=True):
    assert rt.client.patch(
        "/api/mimi/voice-preferences", headers=HEADERS, json={"fast_apply": fast}
    ).is_success
    sent, responses = [], []
    manual_sent = Future()

    def on_send(value):
        sent.append(value)
        if value.get("clientContent", {}).get("turnComplete") is False and not manual_sent.done():
            manual_sent.set_result(True)

    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Mimi chuẩn bị giúp mình nguyên nhóm việc này nhé.", proposal("batch", titles)),
        cid=cid,
        on_send=on_send,
        on_tool=responses.append,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        expected = "applied" if fast and len(titles) <= 5 else "preview"
        assert say(ws) == [expected]
        state = snapshot(rt, cid)
        if expected == "preview":
            (pending,) = [c for c in state["change_sets"] if c["state"] == "pending"]
            assert len(pending["operation"]["args"]["entries"]) == len(titles)
            assert len(state["receipts"]) == len(state["change_sets"]) - 1
            response = confirm(rt, pending)
            assert response.is_success, response.text
            event = receive_to(ws, "action_updated")[-1]
            assert event["status"] == "applied"
            assert event["receipt_id"] == response.json()["id"]
            assert manual_sent.result(timeout=4)
        stop(ws)
    return cid, snapshot(rt, cid)["receipts"][-1], sent, responses


@pytest.mark.parametrize("count", [1, 5, 6])
def test_auto_off_freezes_one_full_plan_then_manual_status_is_post_commit(
    v2_runtime, monkeypatch, count
):
    rt = v2_runtime
    cid, receipt, sent, responses = created(
        rt, monkeypatch, [f"{rt.stem} off {i}" for i in range(count)], fast=False
    )
    assert receipt["result"]["count"] == count
    assert len(rows(rt)) == count
    final = responses[0]["response"]["result"]
    assert final["status"] == "preview_required" and final["applied"] is False
    notes = [
        f["clientContent"] for f in sent if f.get("clientContent", {}).get("turnComplete") is False
    ]
    assert len(notes) == 1
    assert '"status":"applied"' in str(notes) and "receipt_ref" in str(notes)
    assert receipt["id"] not in str(notes)
    assert len(snapshot(rt, cid)["receipts"]) == 1


@pytest.mark.parametrize("count", [1, 5, 6])
def test_exact_inverse_uses_cardinality_and_one_frozen_preview(v2_runtime, monkeypatch, count):
    rt = v2_runtime
    titles = [f"{rt.stem} inverse {i}" for i in range(count)]
    cid, receipt, _, _ = created(rt, monkeypatch, titles)
    captured = []
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(
            "Actually roll back that whole batch for me.",
            tool("voice_undo_latest_v1", "inverse", {"target": "latest"}),
        ),
        cid=cid,
        on_tool=captured.append,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["undone" if count <= 5 else "preview"]
        state = snapshot(rt, cid)
        if count > 5:
            (change,) = [c for c in state["change_sets"] if c["state"] == "pending"]
            plan = change["operation"]["args"]
            assert plan["undo_receipt_id"] == receipt["id"] and len(plan["entries"]) == count
            assert all(r["deleted_at"] is None for r in rows(rt))
            response = confirm(rt, change)
            assert response.is_success, response.text
            assert receive_to(ws, "action_updated")[-1]["status"] == "undone"
        stop(ws)
    assert all(r["deleted_at"] is not None for r in rows(rt))
    state = snapshot(rt, cid)
    assert len(state["receipts"]) == 2
    assert state["receipts"][-1]["result"]["task_ids"] == receipt["result"]["task_ids"]
    assert captured[0]["response"]["result"]["status"] == (
        "undone" if count <= 5 else "preview_required"
    )


@pytest.mark.parametrize("action", ["edit", "soft_delete"])
@pytest.mark.parametrize("count", [1, 5, 6])
def test_versioned_selection_whole_action_and_inverse(v2_runtime, monkeypatch, count, action):
    rt = v2_runtime
    ids = []
    for index in range(count):
        # Two equal titles still require exact server-read IDs/versions.
        response = rt.client.post(
            "/api/tasks",
            json={
                "title": f"{rt.stem} same title",
                "body_md": f"Original {index}",
            },
        )
        assert response.is_success, response.text
        ids.append(response.json()["id"])
    responses = []

    def on_tool(response):
        responses.append(response)
        result = response["response"]["result"]
        if response["name"] == "task_inspect_batch_v1":
            return [
                tool(
                    "task_freeze_selection_v1",
                    "selection",
                    {
                        "intent": "Whole explicit synthetic batch",
                        "variants_considered": ["all inspected IDs"],
                        "explicitly_named_subset": True,
                        "members": [
                            {
                                "id": item["id"],
                                "classification": "included",
                                "reason": "Exact read ID",
                            }
                            for item in result["rows"]
                        ],
                    },
                )
            ]
        if response["name"] == "task_freeze_selection_v1":
            return [
                tool(
                    "task_collection_candidate_v1",
                    "whole",
                    {
                        "selection_id": result["selection_id"],
                        "entries": [
                            {
                                "id": member["id"],
                                "action": action,
                                "expected_collection_version": member["collection_version"],
                                **(
                                    {
                                        "fields": {
                                            "body_md": "Updated by natural speech",
                                            "priority": "p1",
                                        }
                                    }
                                    if action == "edit"
                                    else {}
                                ),
                            }
                            for member in result["members"]
                            if member["classification"] == "included"
                        ],
                    },
                ),
                {"serverContent": {"turnComplete": True}},
            ]
        return []

    initial = [
        *speech("Please handle all those selected tasks.", outputs=False),
        tool("task_inspect_batch_v1", "read", {"ids": ids}),
    ]
    cid, issued, _ = start(rt, monkeypatch, initial, on_tool=on_tool)
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["applied" if count <= 5 else "preview"]
        if count == 6:
            (pending,) = [c for c in snapshot(rt, cid)["change_sets"] if c["state"] == "pending"]
            assert len(pending["operation"]["args"]["entries"]) == count
            assert confirm(rt, pending).is_success
            receive_to(ws, "action_updated")
        stop(ws)
    (receipt,) = snapshot(rt, cid)["receipts"]
    assert set(receipt["result"]["task_ids"]) == set(ids)
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(
            "Hoàn lại toàn bộ thay đổi này giúp mình.",
            tool("voice_undo_latest_v1", "undo", {"target": "latest"}),
        ),
        cid=cid,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["undone" if count <= 5 else "preview"]
        if count == 6:
            (pending,) = [c for c in snapshot(rt, cid)["change_sets"] if c["state"] == "pending"]
            assert pending["operation"]["args"]["undo_receipt_id"] == receipt["id"]
            assert confirm(rt, pending).is_success
            receive_to(ws, "action_updated")
        stop(ws)
    current = asyncio.run(
        rt.sql(
            "select id,body_md,priority,deleted_at from microsched.task where id=any($1::uuid[])",
            [UUID(value) for value in ids],
        )
    )
    assert len(current) == count and all(
        r["deleted_at"] is None and r["priority"] is None for r in current
    )
    assert {r["body_md"] for r in current} == {f"Original {i}" for i in range(count)}
    assert len(snapshot(rt, cid)["receipts"]) == 2


def test_explicit_older_receipt_three_does_not_undo_newer_seven(v2_runtime, monkeypatch):
    rt = v2_runtime
    first = [f"{rt.stem} old {i}" for i in range(3)]
    newer = [f"{rt.stem} new {i}" for i in range(7)]
    cid, old, _, _ = created(rt, monkeypatch, first)
    cid, latest, _, _ = created(rt, monkeypatch, newer, cid=cid)
    ref = receipt_ref(UUID(cid), UUID(old["id"]))
    captured = []
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(
            "Undo the older group of three, keep the seven.",
            tool("voice_undo_latest_v1", "specific", {"target": "receipt", "receipt_ref": ref}),
        ),
        cid=cid,
        on_send=captured.append,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        seed = [f for f in captured if f.get("clientContent", {}).get("turnComplete") is True]
        assert ref in str(seed)
        assert all(
            value not in str(seed)
            for value in (old["id"], latest["id"], *old["result"]["task_ids"])
        )
        assert say(ws) == ["undone"]
        stop(ws)
    state = snapshot(rt, cid)
    inverse = state["receipts"][-1]
    assert inverse["result"]["task_ids"] == old["result"]["task_ids"]
    current = rows(rt)
    assert all(r["deleted_at"] is not None for r in current if r["title"] in first)
    assert all(r["deleted_at"] is None for r in current if r["title"] in newer)


def test_stale_latest_is_not_skipped_and_cross_conversation_ref_is_not_accepted(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    cid, old, _, _ = created(rt, monkeypatch, [f"{rt.stem} old"])
    cid, latest, _, _ = created(rt, monkeypatch, [f"{rt.stem} newer"], cid=cid)
    asyncio.run(
        rt.sql(
            "update microsched.task set body_md='Concurrent STANDARD change' where id=$1",
            UUID(latest["task_id"]),
        )
    )
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Roll that back.", tool("voice_undo_latest_v1", "latest", {"target": "latest"})),
        cid=cid,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["rejected"]
        stop(ws)
    assert len(snapshot(rt, cid)["receipts"]) == 2
    ref = receipt_ref(UUID(cid), UUID(old["id"]))
    other, issued, _ = start(
        rt,
        monkeypatch,
        turn(
            "Undo selected.",
            tool("voice_undo_latest_v1", "foreign", {"target": "receipt", "receipt_ref": ref}),
        ),
    )
    with open_voice(rt, issued, other) as ws:
        hello(ws, issued)
        assert say(ws) == ["rejected"]
        stop(ws)
    assert not snapshot(rt, other)["receipts"]


@pytest.mark.parametrize("cancel", ["provider_cancel", "barge_in", "stop"])
def test_cancel_after_domain_flush_before_commit_rolls_back_receipt_and_task(
    v2_runtime, monkeypatch, cancel
):
    from app.agent.voice_v2_bridge import _active_bridges

    rt = v2_runtime
    entered, release = Future(), Future()
    original = voice_v2_store._confirm_collection

    async def delayed(*args):
        result = await original(*args)
        entered.set_result(True)
        await asyncio.shield(asyncio.wrap_future(release))
        return result

    monkeypatch.setattr(voice_v2_store, "_confirm_collection", delayed)
    cid, issued, _ = start(
        rt, monkeypatch, turn("Prepare one task.", proposal("cancel-me", [f"{rt.stem} cancel"]))
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        ws.send_bytes(fixtures.PCM)
        assert entered.result(timeout=4)

        def revoke():
            bridge = _active_bridges[UUID(issued["run_id"])]
            if cancel == "stop":
                bridge._close("voice_stopped")
            elif cancel == "provider_cancel":
                bridge._cancellations({"ids": ["cancel-me"]})
            else:
                bridge.activity_serial += 1
                bridge.action_cancelled = True
                bridge.interrupted = True

        rt.client.portal.call(revoke)
        release.set_result(True)
        if cancel == "stop":
            receive_to(ws, "ended")
        else:
            outcome = receive_to(ws, "action_updated")[-1]
            assert outcome["status"] == "rejected"
            stop(ws)
    assert not rows(rt)
    assert not snapshot(rt, cid)["receipts"]
    assert not snapshot(rt, cid)["change_sets"]


def test_lost_commit_ack_is_unknown_with_one_durable_receipt_and_no_retry(v2_runtime, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    rt = v2_runtime
    original_confirm, original_commit = voice_v2_store._confirm_collection, AsyncSession.commit

    async def mark(*args):
        result = await original_confirm(*args)
        args[0].info["synthetic_voice_commit_ack_loss"] = True
        return result

    async def commit(db):
        lose_ack = db.info.pop("synthetic_voice_commit_ack_loss", False)
        await original_commit(db)
        if lose_ack:
            raise OSError("synthetic response loss after commit")

    monkeypatch.setattr(voice_v2_store, "_confirm_collection", mark)
    monkeypatch.setattr(AsyncSession, "commit", commit)
    replies = []
    cid, issued, dials = start(
        rt,
        monkeypatch,
        turn("Prepare this task.", proposal("uncertain", [f"{rt.stem} committed"])),
        on_tool=replies.append,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        ws.send_bytes(fixtures.PCM)
        events = receive_to(ws, "ended")
        assert events[-1]["reason"] == "voice_action_outcome_unknown"
        assert not any(event["type"] == "action_updated" for event in events)
    assert len(rows(rt)) == len(snapshot(rt, cid)["receipts"]) == 1
    assert not replies and len(dials) == 1


def test_reminder_configuration_always_keeps_the_whole_manual_preview(v2_runtime, monkeypatch):
    rt = v2_runtime
    change = proposal("reminder", [f"{rt.stem} reminder"])
    change["toolCall"]["functionCalls"][0]["args"]["entries"][0]["reminder"] = {
        "action": "configure",
        "configuration": {"mode": "absolute", "due_at": "2091-04-03T07:00:00Z"},
    }
    responses = []
    cid, issued, _ = start(
        rt, monkeypatch, turn("Plan it with a reminder.", change), on_tool=responses.append
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["preview"]
        state = snapshot(rt, cid)
        (pending,) = state["change_sets"]
        (entry,) = pending["operation"]["args"]["entries"]
        assert entry["reminder_effect"]["action"] == "configure"
        assert not state["receipts"] and not rows(rt)
        assert responses[0]["response"]["result"]["status"] == "preview_required"
        stop(ws)


def test_split_plan_has_no_preview_no_fragment_and_no_receipt(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(
            "The whole group.",
            proposal("part-one", [f"{rt.stem} part A"]),
            proposal("part-two", [f"{rt.stem} part B"]),
        ),
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["needs_clarification"]
        stop(ws)
    state = snapshot(rt, cid)
    assert not state["receipts"] and not state["change_sets"] and not rows(rt)


def test_zero_pcm_with_provider_vad_has_no_preview_receipt_or_task(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Fake caption and VAD.", proposal("zero", [f"{rt.stem} zero"])),
        turn("Fresh activity.", proposal("audible", [f"{rt.stem} audible"]), base=0.2),
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        ws.send_bytes(bytes(len(fixtures.PCM)))
        result = receive_to(ws, "turn_complete")
        assert [r["status"] for r in result if r["type"] == "action_updated"] == [
            "needs_clarification"
        ]
        state = snapshot(rt, cid)
        assert not rows(rt) and not state["receipts"] and not state["change_sets"]
        assert say(ws) == ["applied"]
        stop(ws)
    assert len(rows(rt)) == len(snapshot(rt, cid)["receipts"]) == 1


def test_durable_voice_ack_survives_failed_upstream_tool_response(v2_runtime, monkeypatch):
    from test_mimi_voice_v2 import Live

    rt = v2_runtime
    captured = []
    batches = iter([turn("Make the task.", proposal("drop-ack", [f"{rt.stem} ack"]))])
    cid, issued, _ = start(rt, monkeypatch)

    class Socket(Live):
        async def send(self, raw):
            value = json.loads(raw)
            await super().send(raw)
            if "toolResponse" in value and self is captured[0]:
                raise OSError("synthetic link dropped at durable tool result")
            if "audio" in value.get("realtimeInput", {}):
                self.emit(*next(batches, ()))

    @asynccontextmanager
    async def connect(settings, *, run_id):
        assert str(run_id) == issued["run_id"]
        socket = Socket()
        captured.append(socket)
        yield socket

    monkeypatch.setattr(voice_bridge, "connect_provider", connect)
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        ws.send_bytes(fixtures.PCM)
        applied = receive_to(ws, "action_updated")[-1]
        assert applied["status"] == "applied"
        assert not receive_to(ws, "resumed")[-1]["context_retained"]
        assert len(captured) == 2
        notes = [
            f["clientContent"]
            for f in captured[1].frames
            if f.get("clientContent", {}).get("turnComplete") is False
        ]
        assert len(notes) == 1
        assert '"status":"applied"' in str(notes) and "receipt_ref" in str(notes)
        assert applied["receipt_id"] not in str(notes)
        assert not any(
            "realtimeInput" in frame or "toolResponse" in frame for frame in captured[1].frames
        )
        stop(ws)
    (receipt,) = snapshot(rt, cid)["receipts"]
    assert applied["receipt_id"] == receipt["id"] and len(rows(rt)) == 1


def test_cancel_during_commit_submission_preserves_durable_truth(v2_runtime, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from test_mimi_voice_v2 import Live
    from test_mimi_voice_v2_pg import mint, new_conversation

    from app.agent.voice_v2_bridge import _active_bridges

    rt = v2_runtime
    submitted, release = Future(), Future()
    original_confirm, original_commit = voice_v2_store._confirm_collection, AsyncSession.commit

    async def tag(*args):
        result = await original_confirm(*args)
        args[0].info["fixture_voice_commit_barrier"] = True
        return result

    async def commit(db):
        if db.info.pop("fixture_voice_commit_barrier", False):
            # At the app's commit API entry, delay driver execution so the
            # provider can cancel after the final fence but before DB ACK.
            submitted.set_result(True)
            await asyncio.shield(asyncio.wrap_future(release))
        await original_commit(db)

    monkeypatch.setattr(voice_v2_store, "_confirm_collection", tag)
    monkeypatch.setattr(AsyncSession, "commit", commit)
    cid, generation = new_conversation(rt.client, rt.ids)
    issued = mint(rt.client, cid, generation)
    sockets = []

    class Socket(Live):
        async def send(self, raw):
            value = json.loads(raw)
            await super().send(raw)
            if "audio" in value.get("realtimeInput", {}):
                self.emit(*turn("One request.", proposal("in-flight", [f"{rt.stem} durable"])))

    @asynccontextmanager
    async def connect(settings, *, run_id):
        socket = Socket()
        sockets.append(socket)
        yield socket

    monkeypatch.setattr(voice_bridge, "connect_provider", connect)
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        ws.send_bytes(fixtures.PCM)
        assert submitted.result(timeout=4)

        async def cancel_seen():
            sockets[0].emit({"toolCallCancellation": {"ids": ["in-flight"]}})
            async with asyncio.timeout(2):
                while "in-flight" not in _active_bridges[UUID(issued["run_id"])].cancelled_ids:
                    await asyncio.sleep(0)

        rt.client.portal.call(cancel_seen)
        release.set_result(True)
        result = receive_to(ws, "action_updated")[-1]
        assert result["status"] == "applied" and result["receipt_id"]
        stop(ws)
    (receipt,) = snapshot(rt, cid)["receipts"]
    assert result["receipt_id"] == receipt["id"] and len(rows(rt)) == 1
    assert not any("toolResponse" in frame for frame in sockets[0].frames)


def test_latest_rejects_inverse_but_voice_exact_matches_button_cas(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, original, _, _ = created(rt, monkeypatch, [f"{rt.stem} exact inverse"])
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Roll it back.", tool("voice_undo_latest_v1", "inverse", {"target": "latest"})),
        cid=cid,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["undone"]
        stop(ws)
    inverse = snapshot(rt, cid)["receipts"][-1]
    assert inverse["id"] != original["id"] and rows(rt)[0]["deleted_at"] is not None

    # The explicit UI comparison is the existing read-only eligibility oracle.
    diff = rt.client.get(f"/api/mimi/receipts/{inverse['id']}/diff")
    assert diff.is_success and diff.json()["undo_available"] is True
    ref = receipt_ref(UUID(cid), UUID(inverse["id"]))
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Undo latest.", tool("voice_undo_latest_v1", "latest", {"target": "latest"})),
        turn(
            "Undo that exact previous inverse.",
            tool("voice_undo_latest_v1", "exact", {"target": "receipt", "receipt_ref": ref}),
            base=0.2,
        ),
        cid=cid,
    )
    with open_voice(rt, issued, cid) as ws:
        hello(ws, issued)
        assert say(ws) == ["rejected"]
        assert len(snapshot(rt, cid)["receipts"]) == 2
        assert say(ws) == ["undone"]
        stop(ws)
    assert len(snapshot(rt, cid)["receipts"]) == 3
    assert rows(rt)[0]["deleted_at"] is None
