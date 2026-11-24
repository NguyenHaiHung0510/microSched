"""B1 exact receipt/diff/Undo integration against grant71's disposable database."""

import asyncio
import json
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


def native_chat_undo(
    monkeypatch, rt, *, target="latest", receipt_id=None, text=None, before_response=None
):
    """Real native SDK parser and app pipeline; only its HTTP peer is a synthetic double."""
    import json

    import httpx2

    from app.agent import langgraph_runner, service
    from app.core.settings import get_settings

    for key, value in {
        "MIMI_REAL_CHAT_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_COLLECTION_ENABLED": "true",
        "MIMI_TRANSPORT": "openai_sdk",
        "MIMI_RUNNER": "langgraph",
        "MIMI_ROUTE_MODE": "native",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.8",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_TEXT_RESPONSE_FORMAT": "natural",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("MIMI_OWNER_MEMORY_V1", "MIMI_LOCAL_BUDGET_LEDGER"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    # Harness-only DB binding. Do not change the application's local checkpoint guard.
    import os

    from sqlalchemy.engine import make_url

    parsed = make_url(settings.database_url)
    target_db = make_url(os.environ["NEON_MIGRATOR_URL"])
    assert parsed.host in {"localhost", "127.0.0.1", "::1"} and parsed.username == "microsched_app"
    assert (parsed.host, parsed.port, parsed.database) == (
        target_db.host,
        target_db.port,
        target_db.database,
    )
    monkeypatch.setattr(
        langgraph_runner,
        "_authorized_local_database",
        lambda p: (p.host, p.port, p.database) == (parsed.host, parsed.port, parsed.database),
    )
    requests = []

    async def handler(request):
        assert request.url.path == "/api/v1/chat/completions"
        wire = json.loads(request.content)
        requests.append(wire)
        if before_response:
            await before_response()
        message = (
            {"role": "assistant", "content": text}
            if text is not None
            else {
                "role": "assistant",
                "content": "Untrusted narration must not become an applied claim.",
                "tool_calls": [
                    {
                        "id": f"synthetic-undo-{len(requests)}",
                        "type": "function",
                        "function": {
                            "name": "task.undo_candidate.v1",
                            "arguments": json.dumps({"target": target, "receipt_id": receipt_id}),
                        },
                    }
                ],
            }
        )
        common = {
            "id": f"synthetic-chat-undo-{len(requests)}",
            "created": 1,
            "model": wire["model"],
            "provider": "synthetic-provider",
        }
        usage = {
            "prompt_tokens": 800,
            "completion_tokens": 60,
            "total_tokens": 860,
            "cost": 0,
            "prompt_tokens_details": {"cached_tokens": 0},
        }
        finish = "stop" if text is not None else "tool_calls"
        if not wire["stream"]:
            return httpx2.Response(
                200,
                json={
                    **common,
                    "object": "chat.completion",
                    "choices": [{"index": 0, "finish_reason": finish, "message": message}],
                    "usage": usage,
                },
            )
        delta = (
            {"content": text}
            if text is not None
            else {
                "tool_calls": [{**call, "index": i} for i, call in enumerate(message["tool_calls"])]
            }
        )
        chunks = [
            {
                **common,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            },
            {**common, "object": "chat.completion.chunk", "choices": [], "usage": usage},
        ]
        body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})

    base_complete, base_stream = service.openrouter_complete, service.openrouter_complete_stream

    async def invoke(messages, *, streaming=False, **kwargs):
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            method = base_stream if streaming else base_complete
            return await method(messages, client=client, **kwargs)

    async def http(messages, **kwargs):
        return await invoke(messages, **kwargs)

    async def stream(messages, **kwargs):
        return await invoke(messages, streaming=True, **kwargs)

    # Keep service/context/LangGraph/run accounting and SDK normalization real.
    monkeypatch.setattr(service, "openrouter_complete", http)
    monkeypatch.setattr(service, "openrouter_complete_stream", stream)
    return requests


def assert_chat_manual(rt, cid, receipt, state):
    pending = [c for c in state["change_sets"] if c["state"] == "pending"]
    assert len(pending) == 1
    change = pending[0]
    assert change["operation"]["args"]["undo_receipt_id"] == receipt["id"]
    assert len(state["receipts"]) == 1
    assert state["runs"][-1]["state"] == "waiting_confirmation"
    assert state["messages"][-1]["provenance"]["producer_code"] == "undo_prepared"
    assert "Chưa áp dụng" in state["messages"][-1]["content"]
    target_ids = [entry["id"] for entry in change["operation"]["args"]["entries"]]
    rows = asyncio.run(
        rt.sql(
            "select id,deleted_at from microsched.task where id=any($1::uuid[])",
            [UUID(identity) for identity in target_ids],
        )
    )
    assert len(rows) == len(target_ids) and all(row["deleted_at"] is None for row in rows)
    return change


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
    calls = native_chat_undo(monkeypatch, rt)
    client_id = f"b1-typed-undo-{uuid4()}"
    request = {
        "content": "Hoàn tác cái vừa làm",
        "client_id": client_id,
        "expected_generation": view["generation"],
    }
    typed = rt.client.post(f"/api/mimi/conversations/{cid}/messages", headers=HEADERS, json=request)
    assert typed.status_code == 200, typed.text
    assert len(calls) == 1
    inverse = assert_chat_manual(rt, cid, receipt, typed.json())
    assert inverse["operation"]["args"]["undo_receipt_id"] == receipt["id"]
    assert inverse["operation"]["args"]["entries"][0]["id"] == receipt["task_id"]
    # Retry same authenticated text is observation, never another preview.
    retry = rt.client.post(f"/api/mimi/conversations/{cid}/messages", headers=HEADERS, json=request)
    assert retry.status_code == 200, retry.text
    assert [c["id"] for c in retry.json()["change_sets"] if c["state"] == "pending"] == [
        inverse["id"]
    ]
    assert len(calls) == 1
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
    calls = native_chat_undo(monkeypatch, rt)
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
    assert result.status_code == 200, result.text
    assert len(calls) == 1
    assert result.json()["runs"][-1]["error_code"] == "undo_post_version_stale"
    assert not [c for c in result.json()["change_sets"] if c["state"] == "pending"]
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


def test_typed_undo_stream_is_observable_and_dispatches_one_native_proposal(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    calls = native_chat_undo(monkeypatch, rt)
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
    assert len(calls) == 1
    assert (
        len([call for call in state["provider_calls"] if call["run_id"] == pending["run_id"]]) == 1
    )
    assert_chat_manual(rt, cid, receipt, state)


def test_stale_typed_undo_stream_records_honest_terminal(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    calls = native_chat_undo(monkeypatch, rt)
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
    assert len(calls) == 1


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


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("target", ["latest", "exact", "stale_latest"])
def test_native_chat_selects_old_three_or_latest_seven(v2_runtime, monkeypatch, streaming, target):
    rt = v2_runtime
    cid, older, _ = applied(rt, monkeypatch, [f"{rt.stem} old{i}" for i in range(3)])
    newer_names = [f"{rt.stem} new{i}" for i in range(7)]
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Tạo các việc " + ", ".join(newer_names) + ".", proposal("new-seven", newer_names)),
        cid=cid,
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["preview"]
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    (newer_preview,) = [c for c in snapshot(rt, cid)["change_sets"] if c["state"] == "pending"]
    confirmed = confirm(rt, newer_preview)
    assert confirmed.is_success, confirmed.text
    newer = confirmed.json()
    selected = older if target == "exact" else newer
    if target == "stale_latest":
        asyncio.run(
            rt.sql("update microsched.task set priority='p1' where id=$1", UUID(newer["task_id"]))
        )
    calls = native_chat_undo(
        monkeypatch,
        rt,
        target="exact" if target == "exact" else "latest",
        receipt_id=older["id"] if target == "exact" else None,
    )
    before = snapshot(rt, cid)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages" + ("/stream" if streaming else ""),
        headers=HEADERS,
        json={
            "content": "Trả lại nhóm ba việc cũ giúp mình."
            if target == "exact"
            else "Please reverse my last change.",
            "client_id": uuid4().hex,
            "expected_generation": before["generation"],
        },
    )
    assert response.is_success, response.text
    state = snapshot(rt, cid)
    if target == "stale_latest":
        assert state["runs"][-1]["error_code"] == "undo_post_version_stale"
        assert not [c for c in state["change_sets"] if c["state"] == "pending"]
        assert len(calls) == 1 and len(state["receipts"]) == 2
        rows = asyncio.run(
            rt.sql("select deleted_at from microsched.task where title like $1", f"{rt.stem}%")
        )
        assert len(rows) == 10 and all(row["deleted_at"] is None for row in rows)
        return
    (change,) = [c for c in state["change_sets"] if c["state"] == "pending"]
    assert change["operation"]["args"]["undo_receipt_id"] == selected["id"]
    assert len(change["operation"]["args"]["entries"]) == (3 if target == "exact" else 7)
    assert len(calls) == 1 and len(state["receipts"]) == 2
    authority = next(
        json.loads(m["content"])
        for m in calls[0]["messages"]
        if m["role"] == "system" and "authority_envelope" in m["content"]
    )
    facts = authority["pending_state"]["preview_lifecycle"]["historical_outcomes"]
    assert {f["count"] for f in facts} == {3, 7}
    assert {f["receipt_id"] for f in facts} == {older["id"], newer["id"]}
    assert all(set(f).issuperset({"executed_at", "changes", "receipt_id", "count"}) for f in facts)
    assert "task.undo_candidate.v1" in authority["authority_envelope"]["allowed_tools"]
    assert "recovery" not in json.dumps(authority["pending_state"])
    rows_before = asyncio.run(
        rt.sql("select id,deleted_at from microsched.task where title like $1", f"{rt.stem}%")
    )
    assert len(rows_before) == 10 and all(row["deleted_at"] is None for row in rows_before)
    result = confirm(rt, change)
    assert result.is_success, result.text
    diff = rt.client.get(f"/api/mimi/receipts/{selected['id']}/diff").json()
    selected_ids = {UUID(e["id"]) for e in diff["plan"]["entries"]}
    rows_after = asyncio.run(
        rt.sql("select id,deleted_at from microsched.task where title like $1", f"{rt.stem}%")
    )
    assert {r["id"] for r in rows_after if r["deleted_at"] is not None} == selected_ids


@pytest.mark.parametrize(
    "content",
    [
        "Hoàn tác là gì?",
        "Đừng hoàn tác nhé.",
        'Tôi chỉ trích dẫn câu "hoàn tác cái vừa làm".',
    ],
)
def test_chat_semantics_come_from_provider_and_do_not_create_preview(
    v2_runtime, monkeypatch, content
):
    rt = v2_runtime
    cid, _, view = applied(rt, monkeypatch)
    calls = native_chat_undo(monkeypatch, rt, text="Mình chỉ giải thích, chưa thay đổi dữ liệu.")
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": content,
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.is_success, response.text
    state = response.json()
    assert len(calls) == 1 and len(state["receipts"]) == 1
    assert not [c for c in state["change_sets"] if c["state"] == "pending"]
    assert state["messages"][-1]["content"] == "Mình chỉ giải thích, chưa thay đổi dữ liệu."


def test_chat_undo_keeps_pending_preview_and_does_not_confirm_or_replace_it(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)
    pending_response = rt.client.post(
        f"/api/mimi/receipts/{receipt['id']}/undo-preview", headers=HEADERS, json={}
    )
    assert pending_response.is_success, pending_response.text
    pending = next(c for c in pending_response.json()["change_sets"] if c["state"] == "pending")
    calls = native_chat_undo(monkeypatch, rt)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": "Hoàn tác",
            "client_id": uuid4().hex,
            "expected_generation": pending_response.json()["generation"],
        },
    )
    assert response.is_success, response.text
    state = response.json()
    assert [c["id"] for c in state["change_sets"] if c["state"] == "pending"] == [pending["id"]]
    assert len(calls) == 1 and len(state["receipts"]) == 1
    assert state["runs"][-1]["error_code"] == "finish_active_run_before_undo"
    assert "Chưa hoàn tác" in state["messages"][-1]["content"]


@pytest.mark.parametrize("source", ["private", "missing", "legacy"])
def test_chat_undo_rejects_unavailable_sources_without_new_receipt(v2_runtime, monkeypatch, source):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    if source == "private":
        asyncio.run(
            rt.sql(
                "update microsched.task set title=$2,body_md=null,is_private=true where id=$1",
                UUID(receipt["task_id"]),
                f"enc:v1:{rt.stem}",
            )
        )
    elif source == "missing":
        asyncio.run(rt.sql("delete from microsched.task where id=$1", UUID(receipt["task_id"])))
    else:
        asyncio.run(
            rt.sql(
                "update microsched.mimi_execution_receipt set result_ciphertext=null where id=$1",
                UUID(receipt["id"]),
            )
        )
    calls = native_chat_undo(monkeypatch, rt)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": "Hoàn tác",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.is_success, response.text
    state = response.json()
    assert len(calls) == 1 and len(state["receipts"]) == 1
    assert state["runs"][-1]["state"] == "halted"
    assert not [c for c in state["change_sets"] if c["state"] == "pending"]


def test_chat_latest_never_undoes_an_inverse(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)
    response = rt.client.post(
        f"/api/mimi/receipts/{receipt['id']}/undo-preview", headers=HEADERS, json={}
    )
    pending = next(c for c in response.json()["change_sets"] if c["state"] == "pending")
    assert confirm(rt, pending).is_success
    calls = native_chat_undo(monkeypatch, rt)
    view = snapshot(rt, cid)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": "Hoàn tác",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.is_success, response.text
    state = response.json()
    assert len(calls) == 1 and len(state["receipts"]) == 2
    assert state["runs"][-1]["error_code"] == "receipt_undo_latest_is_inverse"
    assert not [c for c in state["change_sets"] if c["state"] == "pending"]


@pytest.mark.parametrize("fence", ["generation", "pause", "revoke"])
def test_late_native_undo_cannot_publish_after_run_fence(v2_runtime, monkeypatch, fence):
    rt = v2_runtime
    cid, _, view = applied(rt, monkeypatch)

    async def change_frontier():
        if fence == "generation":
            await rt.sql(
                "update microsched.mimi_conversation set generation=generation+1 where id=$1",
                UUID(cid),
            )
        elif fence == "pause":
            await rt.sql(
                "update microsched.mimi_run set error_code='pause_requested' "
                "where conversation_id=$1 and state='running'",
                UUID(cid),
            )
        else:
            await rt.sql(
                "update microsched.mimi_run set execution_lease=execution_lease || "
                '\'{"revoked_at":"synthetic"}\'::jsonb '
                "where conversation_id=$1 and state='running'",
                UUID(cid),
            )

    calls = native_chat_undo(monkeypatch, rt, before_response=change_frontier)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages/stream",
        headers=HEADERS,
        json={
            "content": "Please reverse that change.",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.is_success, response.text
    state = snapshot(rt, cid)
    assert len(calls) == 1 and len(state["receipts"]) == 1
    assert state["runs"][-1]["state"] == "halted"
    assert not [c for c in state["change_sets"] if c["state"] == "pending"]


def test_explicit_receipt_button_keeps_exact_target_and_never_dispatches(v2_runtime, monkeypatch):
    from app.agent import service

    rt = v2_runtime
    cid, receipt, _ = applied(rt, monkeypatch)

    async def forbidden(*args, **kwargs):
        raise AssertionError("exact receipt button must not dispatch a model")

    monkeypatch.setattr(service, "openrouter_complete", forbidden)
    monkeypatch.setattr(service, "openrouter_complete_stream", forbidden)
    response = rt.client.post(
        f"/api/mimi/receipts/{receipt['id']}/undo-preview", headers=HEADERS, json={}
    )
    assert response.is_success, response.text
    pending = assert_chat_manual(rt, cid, receipt, response.json())
    assert not [
        call for call in response.json()["provider_calls"] if call["run_id"] == pending["run_id"]
    ]


def test_chat_exact_handle_from_other_conversation_cannot_prepare_inverse(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, own, view = applied(rt, monkeypatch)
    _, other, _ = applied(rt, monkeypatch)
    calls = native_chat_undo(monkeypatch, rt, target="exact", receipt_id=other["id"])
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": "Trả lại thay đổi trước giúp mình.",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.is_success, response.text
    state = response.json()
    assert len(calls) == 1 and len(state["receipts"]) == 1
    assert state["receipts"][0]["id"] == own["id"]
    assert state["runs"][-1]["error_code"] == "receipt_undo_target_not_in_context"
    assert not [change for change in state["change_sets"] if change["state"] == "pending"]


def test_chat_undo_confirm_rechecks_cas_after_native_preview(v2_runtime, monkeypatch):
    rt = v2_runtime
    cid, receipt, view = applied(rt, monkeypatch)
    calls = native_chat_undo(monkeypatch, rt)
    response = rt.client.post(
        f"/api/mimi/conversations/{cid}/messages",
        headers=HEADERS,
        json={
            "content": "Undo the last change please.",
            "client_id": uuid4().hex,
            "expected_generation": view["generation"],
        },
    )
    assert response.is_success, response.text
    pending = assert_chat_manual(rt, cid, receipt, response.json())
    asyncio.run(
        rt.sql("update microsched.task set priority='p1' where id=$1", UUID(receipt["task_id"]))
    )
    confirmation = confirm(rt, pending)
    assert confirmation.status_code == 409, confirmation.text
    assert len(calls) == 1 and len(snapshot(rt, cid)["receipts"]) == 1
    (row,) = asyncio.run(
        rt.sql(
            "select deleted_at,priority from microsched.task where id=$1", UUID(receipt["task_id"])
        )
    )
    assert row["deleted_at"] is None and row["priority"] == "p1"
