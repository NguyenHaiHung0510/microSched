"""Grant71 grouped-repair witnesses: full bridge + real store, synthetic PG only."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import test_mimi_voice_v2_pg as voice_fixtures
from test_mimi_b1_receipts_pg import applied
from test_mimi_voice_pg import HEADERS, endpoint
from test_mimi_voice_v2 import proposal, speech
from test_mimi_voice_v2_pg import confirm, receive_to, say, snapshot, start, tool

pytestmark = pytest.mark.pg
v2_runtime = voice_fixtures.v2_runtime


def undo_receipt(rt, cid, receipt):
    response = rt.client.post(
        f"/api/mimi/receipts/{receipt['id']}/undo-preview",
        headers=HEADERS,
        json={},
    )
    assert response.is_success, response.text
    (change,) = [c for c in response.json()["change_sets"] if c["state"] == "pending"]
    result = confirm(rt, change)
    assert result.is_success, result.text
    return result.json()


def test_receipt_backed_undo_create_keeps_original_and_inverse_diff(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)
    inverse = undo_receipt(rt, cid, receipt)
    before = asyncio.run(
        rt.sql(
            "select id,collection_version,deleted_at,title from microsched.task where id=$1",
            UUID(receipt["task_id"]),
        )
    )
    for selected in (receipt, inverse):
        response = rt.client.get(f"/api/mimi/receipts/{selected['id']}/diff")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["receipt_id"] == selected["id"]
        (entry,) = body["plan"]["entries"]
        assert entry["id"] == receipt["task_id"]
        assert entry["after"]["fields"]["title"] == f"{rt.stem} alpha"
        if selected is receipt:
            assert entry["before"] is None and entry["after"]["deleted_at"] is None
            assert body["undo_available"] is False
        else:
            assert entry["before"]["deleted_at"] is None
            assert entry["after"]["deleted_at"] is not None
    after = asyncio.run(
        rt.sql(
            "select id,collection_version,deleted_at,title from microsched.task where id=$1",
            UUID(receipt["task_id"]),
        )
    )
    assert before == after and after[0]["deleted_at"] is not None
    assert len([m for m in snapshot(rt, cid)["messages"] if m["applied_receipt_id"]]) == 2


@pytest.mark.parametrize("mutation", ["private", "missing", "unproven_delete", "other_scope"])
def test_tombstone_diff_still_requires_current_private_and_deletion_proof(
    v2_runtime,
    monkeypatch,
    mutation,
):
    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)
    inverse = undo_receipt(rt, cid, receipt)
    tid = UUID(receipt["task_id"])
    if mutation == "private":
        asyncio.run(
            rt.sql(
                "update microsched.task set title=$2,body_md=null,is_private=true where id=$1",
                tid,
                f"enc:v1:{rt.stem}",
            )
        )
    elif mutation == "missing":
        asyncio.run(rt.sql("delete from microsched.task where id=$1", tid))
    elif mutation == "unproven_delete":
        # Same visible lifecycle after an ABA does not prove our committed deletion.
        asyncio.run(rt.sql("update microsched.task set deleted_at=null where id=$1", tid))
        asyncio.run(rt.sql("update microsched.task set deleted_at=now() where id=$1", tid))
    else:
        asyncio.run(
            rt.sql(
                "update microsched.mimi_conversation set owner_id=$2 where id=$1",
                UUID(cid),
                uuid4(),
            )
        )
    for selected in (receipt, inverse):
        response = rt.client.get(f"/api/mimi/receipts/{selected['id']}/diff")
        assert response.status_code in {404, 409, 410}, response.text
        assert f"{rt.stem} alpha" not in response.text


def committed_mixed(rt, cid, existing_id):
    from sqlalchemy import select

    from app.agent import crypto
    from app.agent.models import MimiConversation, MimiRun
    from app.agent.service import _confirm_collection, freeze_change_set_row
    from app.agent.task_collection import (
        COLLECTION_TOOL,
        CollectionCandidate,
        TaskCommand,
        freeze_collection,
    )
    from app.core.db import get_sessionmaker
    from app.domain.models import AuthSession, Task

    async def run():
        async with get_sessionmaker()() as db:
            actor = await db.scalar(
                select(AuthSession).where(AuthSession.user_email == rt.emails[0])
            )
            conversation = await db.get(MimiConversation, UUID(cid), with_for_update=True)
            current = await db.get(Task, UUID(existing_id))
            plan = await freeze_collection(
                db,
                CollectionCandidate(
                    selection_id=uuid4(),
                    entries=(
                        TaskCommand(action="create", fields={"title": f"{rt.stem} mixed new"}),
                        TaskCommand(
                            action="edit",
                            id=current.id,
                            expected_collection_version=current.collection_version,
                            fields={"priority": "p1"},
                        ),
                    ),
                ),
                covered_versions={current.id: current.collection_version},
            )
            run = MimiRun(
                id=uuid4(),
                conversation_id=conversation.id,
                generation=conversation.generation,
                state="waiting_confirmation",
                deadline=datetime.now(UTC) + timedelta(minutes=5),
                execution_lease={"capabilities": [COLLECTION_TOOL], "sensitivity": "standard"},
            )
            dek = crypto.unwrap_dek(conversation.dek_wrapped)
            change, operation = freeze_change_set_row(
                conversation.id,
                run.id,
                dek,
                COLLECTION_TOOL,
                plan.model_dump(mode="json"),
                run.deadline,
                "synthetic-b1-repair",
            )
            db.add(run)
            conversation.generation += 1
            await db.flush()
            db.add(change)
            await db.flush()

            async def invalidate(reason):
                raise AssertionError(reason)

            receipt = await _confirm_collection(
                db,
                actor,
                conversation,
                run,
                change,
                operation,
                f"mixed-{uuid4()}",
                dek,
                invalidate,
            )
            await db.commit()
            return receipt

    return rt.client.portal.call(run)


def test_receipt_backed_mixed_batch_tombstone_and_active_diffs(v2_runtime):
    from test_mimi_voice_pg import new_conversation

    rt = v2_runtime
    cid, _ = new_conversation(rt.client, rt.ids)
    task = rt.client.post("/api/tasks", json={"title": f"{rt.stem} mixed existing"})
    assert task.is_success, task.text
    original = committed_mixed(rt, cid, task.json()["id"])
    inverse = undo_receipt(rt, cid, original)
    for selected in (original, inverse):
        response = rt.client.get(f"/api/mimi/receipts/{selected['id']}/diff")
        assert response.status_code == 200, response.text
        entries = response.json()["plan"]["entries"]
        assert len(entries) == 2 and [e["id"] for e in entries] == original["result"]["task_ids"]
        if selected is inverse:
            deleted, edited = entries
            assert deleted["after"]["deleted_at"] is not None
            assert edited["before"]["fields"]["priority"] == "p1"
            assert edited["after"]["fields"]["priority"] is None
            assert edited["after"]["deleted_at"] is None
    records = asyncio.run(
        rt.sql(
            "select id,deleted_at,priority from microsched.task where id=any($1::uuid[])",
            [UUID(value) for value in original["result"]["task_ids"]],
        )
    )
    assert len(records) == 2 and sum(row["deleted_at"] is not None for row in records) == 1


def test_prior_missing_caption_does_not_disable_a_fresh_structured_turn(v2_runtime, monkeypatch):
    rt = v2_runtime
    name = f"{rt.stem} fresh-b"
    prior = [
        e for e in speech("No caption A.") if "inputTranscription" not in e.get("serverContent", {})
    ]
    current = [
        {"voiceActivity": {"type": "ACTIVITY_START", "audioOffset": "0.210s"}},
        {"serverContent": {"inputTranscription": {"text": "Unlabelled caption."}}},
        proposal("fresh-proposal", [name]),
        {"voiceActivity": {"type": "ACTIVITY_END", "audioOffset": "0.350s"}},
    ]
    cid, issued, sockets = reconnect_script(rt, monkeypatch, prior, current)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == []
        assert say(ws) == ["applied"]
        state = snapshot(rt, cid)
        assert len(state["receipts"]) == 1
        assert state["change_sets"][0]["state"] == "executed"
        assert asyncio.run(rt.sql("select id from microsched.task where title=$1", name))
        assert len(sockets) == 1
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")


@pytest.mark.parametrize("prior", ["settled", "late_before_new_vad", "known_replay"])
def test_repeated_or_late_caption_cannot_remove_current_activity_authority(
    v2_runtime, monkeypatch, prior
):
    rt = v2_runtime
    name = f"{rt.stem} ordinary-b"
    old_text = f"Tạo việc {rt.stem} retired-a."
    first = speech(old_text)
    if prior == "late_before_new_vad":
        first = [
            event for event in first if "inputTranscription" not in event.get("serverContent", {})
        ]
    command = old_text if prior == "known_replay" else f"Tạo việc {name}."
    targets = [f"{rt.stem} retired-a"] if prior == "known_replay" else [name]
    current = [
        {"voiceActivity": {"type": "ACTIVITY_START", "audioOffset": "0.210s"}},
        {"serverContent": {"inputTranscription": {"text": command}}},
        proposal("new-ordinary", targets),
        {"voiceActivity": {"type": "ACTIVITY_END", "audioOffset": "0.350s"}},
    ]
    if prior == "late_before_new_vad":
        # New B PCM already exists; absence of B VAD cannot settle A.
        # Input transcription is not ordered after the activity event.
        current.insert(0, {"serverContent": {"inputTranscription": {"text": old_text}}})
    cid, issued, _ = start(rt, monkeypatch, first, current)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == []
        expected = "applied"
        assert say(ws) == [expected]
        state = snapshot(rt, cid)
        assert len(state["receipts"]) == int(expected == "applied")
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")


def reconnect_script(rt, monkeypatch, *batches):
    from test_mimi_voice_pg import mint, new_conversation

    from app.agent import voice_bridge

    cid, generation = new_conversation(rt.client, rt.ids)
    issued = mint(rt.client, cid, generation)
    turns = iter(batches)
    sockets = []

    class Live:
        def __init__(self):
            self.events = asyncio.Queue()
            self.events.put_nowait({"setupComplete": {}})
            self.sent = []

        async def send(self, raw):
            value = json.loads(raw)
            self.sent.append(value)
            if "audio" in value.get("realtimeInput", {}):
                for event in next(turns, ()):
                    self.events.put_nowait(event)

        async def recv(self):
            return json.dumps(await asyncio.wait_for(self.events.get(), 5))

    @asynccontextmanager
    async def connect(settings, *, run_id):
        assert str(run_id) == issued["run_id"]
        socket = Live()
        sockets.append(socket)
        yield socket

    monkeypatch.setattr(voice_bridge, "connect_provider", connect)
    return cid, issued, sockets


def offsetless_batch(text, *calls, base=0.0):
    events = speech(text, base=base)
    final = next(
        e["serverContent"]["inputTranscription"]
        for e in events
        if "inputTranscription" in e.get("serverContent", {})
    )
    final.pop("startOffset")
    final.pop("endOffset")
    return [*events[:-1], *calls, events[-1]]


def test_unbound_proposal_clarifies_then_a_fresh_bound_command_is_fast(v2_runtime, monkeypatch):
    rt = v2_runtime
    old_name, new_name = f"{rt.stem} unbound", f"{rt.stem} fresh"
    unbound = [
        {"serverContent": {"inputTranscription": {"text": "Unbound caption."}}},
        proposal("unbound", [old_name]),
        {"serverContent": {"turnComplete": True}},
    ]
    fresh = offsetless_batch(
        "Please handle this new task.", proposal("fresh", [new_name]), base=0.2
    )
    cid, issued, sockets = reconnect_script(rt, monkeypatch, unbound, fresh)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["needs_clarification"]
        assert snapshot(rt, cid)["change_sets"] == []
        assert say(ws) == ["applied"]
        assert len(snapshot(rt, cid)["receipts"]) == 1
        assert len(sockets) == 1
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")


def test_same_undo_words_after_new_receipt_are_a_new_bound_action(
    v2_runtime,
    monkeypatch,
):
    rt = v2_runtime
    first, second = f"{rt.stem} first", f"{rt.stem} second"
    undo = "Hoàn tác cái vừa làm."
    batches = [
        offsetless_batch(f"Tạo việc {first}.", proposal("first", [first])),
        offsetless_batch(undo, tool("voice_undo_latest_v1", "undo-first", {}), base=0.2),
        offsetless_batch(f"Tạo việc {second}.", proposal("second", [second]), base=0.4),
        offsetless_batch(undo, tool("voice_undo_latest_v1", "undo-second", {}), base=0.6),
    ]
    cid, issued, sockets = reconnect_script(rt, monkeypatch, *batches)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert [say(ws) for _ in range(3)] == [["applied"], ["undone"], ["applied"]]
        assert say(ws) == ["undone"]
        assert len(snapshot(rt, cid)["receipts"]) == 4
        assert len(sockets) == 1
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
