"""B1 exact receipt/diff/Undo integration against grant71's disposable database."""

import asyncio
from uuid import UUID, uuid4

import pytest
import test_mimi_voice_v2_pg as voice_fixtures
from test_mimi_voice_pg import HEADERS, endpoint
from test_mimi_voice_v2 import proposal, speech
from test_mimi_voice_v2_pg import (
    confirm,
    receive_to,
    say,
    snapshot,
    start,
    tool,
    turn,
)

pytestmark = pytest.mark.pg
v2_runtime = voice_fixtures.v2_runtime


def applied(rt, monkeypatch, names=None):
    names = names or [f"{rt.stem} alpha"]
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(
            "Tạo các việc " + ", ".join(names) + "." if len(names) > 1 else f"Tạo việc {names[0]}.",
            proposal("apply", names),
        ),
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["applied"]
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    view = snapshot(rt, cid)
    assert len(view["receipts"]) == 1
    receipt = view["receipts"][0]
    return cid, receipt, view


def test_exact_applied_marker_diff_and_typed_chat_undo_of_voice(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    markers = [m for m in view["messages"] if m.get("applied_receipt_id")]
    assert len(markers) == 1
    assert markers[0]["provenance"]["producer_code"] == "collection_committed"
    assert markers[0]["applied_receipt_id"] == receipt["id"]
    diff = rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff")
    assert diff.status_code == 200, diff.text
    payload = diff.json()
    assert set(payload) == {"receipt_id", "plan", "undo_available", "executed_at"}
    assert payload["undo_available"] is True
    (entry,) = payload["plan"]["entries"]
    assert entry["id"] == receipt["task_id"]
    assert entry["before"] is None and entry["after"]["fields"]["title"] == f"{rt.stem} alpha"
    client_id = f"b1-typed-undo-{uuid4()}"
    request = {
        "content": "Hoàn tác cái vừa làm",
        "client_id": client_id,
        "expected_generation": view["generation"],
    }
    typed = rt.client.post(f"/api/mimi/conversations/{cid}/messages", headers=HEADERS, json=request)
    assert typed.status_code == 200, typed.text
    inverse = next(c for c in typed.json()["change_sets"] if c["state"] == "pending")
    assert inverse["operation"]["args"]["undo_receipt_id"] == receipt["id"]
    assert inverse["operation"]["args"]["entries"][0]["id"] == receipt["task_id"]
    # Retry same authenticated text is observation, never another preview.
    retry = rt.client.post(f"/api/mimi/conversations/{cid}/messages", headers=HEADERS, json=request)
    assert retry.status_code == 200, retry.text
    assert [c["id"] for c in retry.json()["change_sets"] if c["state"] == "pending"] == [
        inverse["id"]
    ]
    result = confirm(rt, inverse)
    assert result.is_success, result.text
    state = snapshot(rt, cid)
    assert len(state["receipts"]) == 2
    assert len([m for m in state["messages"] if m.get("applied_receipt_id")]) == 2
    (row,) = asyncio.run(
        rt.sql("select deleted_at from microsched.task where id=$1", UUID(receipt["task_id"]))
    )
    assert row["deleted_at"] is not None


@pytest.mark.parametrize("mutation", ["private", "aba", "missing"])
def test_diff_never_returns_hidden_stale_or_missing_historical_plaintext(
    v2_runtime, monkeypatch, mutation
):
    rt = v2_runtime
    _, receipt, _ = applied(rt, monkeypatch)
    tid = UUID(receipt["task_id"])
    if mutation == "private":
        # Flip privacy without exposing a plaintext field to the response.
        asyncio.run(
            rt.sql(
                "update microsched.task set title=$2,body_md=null,is_private=true where id=$1",
                tid,
                f"enc:v1:{rt.stem}",
            )
        )
    elif mutation == "aba":
        asyncio.run(rt.sql("update microsched.task set priority='p1' where id=$1", tid))
        asyncio.run(rt.sql("update microsched.task set priority=null where id=$1", tid))
    else:
        asyncio.run(rt.sql("delete from microsched.task where id=$1", tid))
    result = rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff")
    if mutation == "aba":
        assert result.status_code == 200, result.text
        assert result.json()["undo_available"] is False
    else:
        assert result.status_code in {404, 409, 410}, result.text
        assert f"{rt.stem} alpha" not in result.text


def test_latest_receipt_is_not_skipped_after_source_change(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    asyncio.run(
        rt.sql("update microsched.task set priority='p1' where id=$1", UUID(receipt["task_id"]))
    )
    result = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": "Hoàn tác",
            "client_id": f"stale-{uuid4()}",
            "expected_generation": view["generation"],
        },
    )
    assert result.status_code == 409
    assert len(snapshot(rt, cid)["receipts"]) == 1


@pytest.mark.parametrize("count", [0, 40])
def test_voice_day_milestones_are_visible_even_when_task_page_is_full(v2_runtime, count):
    from app.agent.voice_v2_store import execute_voice_read
    from app.core.db import get_sessionmaker
    from app.core.settings import get_settings

    rt = v2_runtime
    marker = uuid4()
    try:
        asyncio.run(
            rt.sql(
                "insert into microsched.day_annotation(id,starts_on,ends_on,label) "
                "values ($1,'2092-05-06','2092-05-06',$2)",
                marker,
                f"{rt.stem} milestone",
            )
        )
        for index in range(count):
            response = rt.client.post(
                "/api/tasks",
                json={
                    "title": f"{rt.stem} page {index}",
                    "due_precision": "date",
                    "due_on": "2092-05-06",
                },
            )
            assert response.is_success, response.text

        async def read():
            async with get_sessionmaker()() as db:
                return await execute_voice_read(
                    db,
                    "calendar.read.v1",
                    {"date": "2092-05-06"},
                    settings=get_settings(),
                )

        result = rt.client.portal.call(read)
        assert len(result["rows"]) == min(count + 1, 40)
        assert any(row["id"] == str(marker) for row in result["day_milestones"]["rows"])
        if count == 40:
            assert result["has_more"] is True
            assert result["day_milestones"]["coverage"] == "complete"
    finally:
        asyncio.run(rt.sql("delete from microsched.day_annotation where id=$1", marker))


def test_historical_diff_a_after_committed_b_keeps_actual_a_and_disables_undo(
    v2_runtime, monkeypatch
):
    from datetime import UTC, datetime, timedelta

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

    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)
    tid = UUID(receipt["task_id"])

    async def apply_b():
        async with get_sessionmaker()() as db:
            actor = await db.scalar(
                select(AuthSession).where(AuthSession.user_email == rt.emails[0])
            )
            conversation = await db.get(MimiConversation, UUID(cid), with_for_update=True)
            task = await db.get(Task, tid)
            plan = await freeze_collection(
                db,
                CollectionCandidate(
                    selection_id=uuid4(),
                    entries=(
                        TaskCommand(
                            action="edit",
                            id=tid,
                            expected_collection_version=task.collection_version,
                            fields={"priority": "p1"},
                        ),
                    ),
                ),
                covered_versions={tid: task.collection_version},
            )
            run = MimiRun(
                id=uuid4(),
                conversation_id=conversation.id,
                generation=conversation.generation,
                state="waiting_confirmation",
                deadline=datetime.now(UTC) + timedelta(minutes=5),
                execution_lease={"capabilities": [COLLECTION_TOOL], "sensitivity": "standard"},
            )
            change, operation = freeze_change_set_row(
                conversation.id,
                run.id,
                crypto.unwrap_dek(conversation.dek_wrapped),
                COLLECTION_TOOL,
                plan.model_dump(mode="json"),
                run.deadline,
                "synthetic-b1",
            )
            db.add(run)
            conversation.generation += 1
            await db.flush()
            db.add(change)
            await db.flush()

            async def invalidate(reason):
                raise AssertionError(reason)

            result = await _confirm_collection(
                db,
                actor,
                conversation,
                run,
                change,
                operation,
                f"b1-b-{uuid4()}",
                crypto.unwrap_dek(conversation.dek_wrapped),
                invalidate,
            )
            await db.commit()
            return result

    receipt_b = rt.client.portal.call(apply_b)
    diff_a = rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff")
    assert diff_a.status_code == 200, diff_a.text
    (entry_a,) = diff_a.json()["plan"]["entries"]
    assert entry_a["before"] is None
    assert entry_a["after"]["fields"]["priority"] is None
    assert diff_a.json()["undo_available"] is False
    diff_b = rt.client.get(f"/api/mimi/receipts/{receipt_b['id']}/diff")
    assert diff_b.status_code == 200, diff_b.text
    (entry_b,) = diff_b.json()["plan"]["entries"]
    assert entry_b["before"]["fields"]["priority"] is None
    assert entry_b["after"]["fields"]["priority"] == "p1"
    assert diff_b.json()["undo_available"] is True
    # Displaying A never weakens the version fence on explicit/manual Undo A.
    undo_a = rt.client.post(
        f"/api/mimi/receipts/{receipt['id']}/undo-preview", headers=HEADERS, json={}
    )
    assert undo_a.status_code == 409


def test_chat_create_diff_then_new_voice_undo_uses_same_exact_receipt(v2_runtime, monkeypatch):
    from test_mimi_voice_pg import new_conversation

    rt = v2_runtime
    cid, generation = new_conversation(rt.client, rt.ids)
    typed = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": f"Tạo việc {rt.stem} chat-to-voice",
            "client_id": uuid4().hex,
            "expected_generation": generation,
        },
    )
    assert typed.is_success, typed.text
    (preview,) = typed.json()["change_sets"]
    assert preview["operation"]["tool"] == "task.create.v1" and not typed.json()["receipts"]
    accepted = confirm(rt, preview)
    assert accepted.is_success, accepted.text
    receipt = accepted.json()
    diff = rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff")
    assert diff.is_success, diff.text
    assert diff.json()["plan"]["entries"][0]["id"] == receipt["task_id"]
    assert diff.json()["undo_available"] is True
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Hoàn tác cái vừa làm.", tool("voice_undo_latest_v1", "undo-chat", {})),
        cid=cid,
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff").is_success
        active = rt.client.post(
            f"/api/mimi/receipts/{receipt['id']}/undo-preview", headers=HEADERS, json={}
        )
        assert (
            active.status_code == 409 and active.json()["detail"] == "finish_active_run_before_undo"
        )
        assert say(ws) == ["undone"]
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    records = snapshot(rt, cid)
    assert len(records["receipts"]) == 2
    assert [r["task_id"] for r in records["receipts"]] == [receipt["task_id"]] * 2
    assert [
        m["provenance"]["producer_code"] for m in records["messages"] if m["applied_receipt_id"]
    ] == ["operation_committed", "collection_committed"]


def test_stop_reopen_seeds_stable_voice_history_and_pending_state(v2_runtime, monkeypatch):
    rt = v2_runtime
    user_phrase = "Ghi nhớ quyết định thử nghiệm: chọn phương án B."
    stable = "Đã ghi nhận quyết định chọn phương án B."
    chat_phrase = "Mở lại bối cảnh thử nghiệm."
    anchor = f"{rt.stem} pending"
    civil = speech(user_phrase)
    civil[-1]["serverContent"]["outputTranscription"]["text"] = stable
    rt.client.patch("/api/mimi/voice-preferences", headers=HEADERS, json={"fast_apply": False})
    cid, issued, _ = start(
        rt,
        monkeypatch,
        civil,
        turn(f"Tạo việc {anchor}.", proposal("pending", [anchor]), base=0.2),
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == []
        assert say(ws) == ["preview"]
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    posted = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": chat_phrase,
            "client_id": uuid4().hex,
        },
    )
    assert posted.is_success, posted.text
    wire = []
    cid, issued, _ = start(rt, monkeypatch, cid=cid, on_send=wire.append)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        seed = next(f["clientContent"] for f in wire if "clientContent" in f)
        text = " ".join(part["text"] for item in seed["turns"] for part in item["parts"])
        assert user_phrase in text and stable in text and chat_phrase in text
        assert "SERVER CONVERSATION STATE" in text and '"state":"pending"' in text
        assert seed["turnComplete"] is True
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")


@pytest.mark.parametrize("count", [1, 5, 6])
def test_actual_unoffset_asr_yields_one_commit_or_preview(v2_runtime, monkeypatch, count):
    rt = v2_runtime
    names = [f"{rt.stem} asr {index}" for index in range(count)]
    cmd = ("Tạo các việc " if count > 1 else "Tạo việc ") + ", ".join(names)
    batch = turn(cmd, proposal("offsetless", names))
    final = next(
        x["serverContent"]["inputTranscription"]
        for x in batch
        if "inputTranscription" in x.get("serverContent", {})
    )
    final.pop("startOffset")
    final.pop("endOffset")
    results = []
    cid, issued, _ = start(rt, monkeypatch, batch, on_tool=results.append)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["preview" if count == 6 else "applied"]
        (answer,) = results
        assert answer["response"]["result"]["final"] is True
        assert answer["response"]["result"]["applied"] == (count <= 5)
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    state = snapshot(rt, cid)
    assert len(state["receipts"]) == (count <= 5)
    assert len([m for m in state["messages"] if m["applied_receipt_id"]]) == (count <= 5)
    assert len([c for c in state["change_sets"] if c["state"] == "pending"]) == (count == 6)


def test_typed_undo_stream_is_observable_and_never_dispatches_provider(v2_runtime, monkeypatch):
    from app.agent import service

    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)

    async def forbidden(*args, **kwargs):
        raise AssertionError("typed receipt Undo must not dispatch a model")

    monkeypatch.setattr(service, "openrouter_complete", forbidden)
    monkeypatch.setattr(service, "openrouter_complete_stream", forbidden)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages/stream",
        headers=HEADERS,
        json={
            "content": "Hoàn tác cái vừa làm",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.status_code == 200, response.text
    state = snapshot(rt, cid)
    (pending,) = [change for change in state["change_sets"] if change["state"] == "pending"]
    assert pending["operation"]["args"]["undo_receipt_id"] == receipt["id"]
    assert str(pending["run_id"]) in response.text and "change_set.ready" in response.text
    assert not [call for call in state["provider_calls"] if call["run_id"] == pending["run_id"]]


def test_stale_typed_undo_stream_records_honest_terminal(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    asyncio.run(
        rt.sql("update microsched.task set priority='p1' where id=$1", UUID(receipt["task_id"]))
    )
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages/stream",
        headers=HEADERS,
        json={
            "content": "Hoàn tác",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.status_code == 200, response.text
    state = snapshot(rt, cid)
    assert state["runs"][-1]["state"] == "halted"
    assert state["runs"][-1]["error_code"] == "undo_post_version_stale"
    assert "Chưa hoàn tác" in state["messages"][-1]["content"]
    assert "run.terminal" in response.text and len(state["receipts"]) == 1


def test_old_message_marker_survives_recent_run_window_and_legacy_without_inverse(
    v2_runtime, monkeypatch
):
    from datetime import UTC, datetime

    from app.agent.models import MimiConversation, MimiRun
    from app.core.db import get_sessionmaker

    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)

    async def pad():
        async with get_sessionmaker()() as db:
            conversation = await db.get(MimiConversation, UUID(cid))
            for index in range(105):
                db.add(
                    MimiRun(
                        id=uuid4(),
                        conversation_id=conversation.id,
                        generation=conversation.generation + index,
                        state="completed",
                        completed_at=datetime.now(UTC),
                        deadline=datetime.now(UTC),
                        execution_lease={},
                    )
                )
            conversation.generation += 105
            await db.commit()

    rt.client.portal.call(pad)
    state = snapshot(rt, cid)
    assert len(state["runs"]) == 100 and not state["receipts"]
    assert [m["applied_receipt_id"] for m in state["messages"] if m["applied_receipt_id"]] == [
        receipt["id"]
    ]
    assert rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff").is_success
    # A pre-existing receipt that truly lacks recovery must stay scalar-only.
    asyncio.run(
        rt.sql(
            "update microsched.mimi_execution_receipt set result_ciphertext=null where id=$1",
            UUID(receipt["id"]),
        )
    )
    legacy = rt.client.get(f"/api/mimi/receipts/{receipt['id']}/diff")
    assert legacy.status_code == 409 and legacy.json()["detail"] == "receipt_has_no_durable_inverse"
    assert [
        m["applied_receipt_id"] for m in snapshot(rt, cid)["messages"] if m["applied_receipt_id"]
    ] == [receipt["id"]]


def test_source_backed_voice_history_stays_withheld_after_stop(v2_runtime, monkeypatch):
    from app.agent import crypto
    from app.agent.compaction import VOICE_HISTORY_MARKER
    from app.agent.models import MimiConversation
    from app.agent.service import _provider_history
    from app.core.db import get_sessionmaker

    rt = v2_runtime
    source_answer = "Synthetic source-derived fact must be reread."
    head = speech("Đọc lịch ngày 6 tháng 5 năm 2092.", outputs=False)

    def after_read(response):
        if response["name"] == "calendar_read_v1":
            return [
                {
                    "serverContent": {
                        "outputTranscription": {"text": source_answer},
                        "generationComplete": True,
                        "turnComplete": True,
                    }
                }
            ]
        return ()

    cid, issued, _ = start(
        rt,
        monkeypatch,
        [*head, tool("calendar_read_v1", "source", {"date": "2092-05-06"})],
        on_tool=after_read,
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == []
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")

    async def history(voice):
        async with get_sessionmaker()() as db:
            conversation = await db.get(MimiConversation, UUID(cid))
            return await _provider_history(
                db,
                conversation,
                crypto.unwrap_dek(conversation.dek_wrapped),
                voice=voice,
            )

    for voice in (True, False):
        text = str(rt.client.portal.call(history, voice))
        assert source_answer not in text and VOICE_HISTORY_MARKER in text
