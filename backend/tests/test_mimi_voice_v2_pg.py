"""Real auth, socket, preview, receipts and transaction on disposable PG; Google is a double."""

import asyncio
import base64
import json
import os
from concurrent.futures import Future
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from starlette.websockets import WebSocketDisconnect
from test_mimi_voice_pg import HEADERS, endpoint, mint, new_conversation
from test_mimi_voice_v2 import PCM, proposal, speech

from app.agent import voice_bridge, voice_v2_bridge, voice_v2_store
from app.agent.compaction import VOICE_HISTORY_MARKER
from app.agent.owner_workspace import OWNER_WORKSPACE_ID
from app.agent.service import _provider_history
from app.core import crypto
from app.core.db import get_engine, get_sessionmaker
from app.core.sessions import hash_session_token
from app.core.settings import get_settings
from app.main import create_app

pytestmark = pytest.mark.pg
CSRF = HEADERS


@pytest.fixture
def v2_runtime(pg_dsn, monkeypatch):
    app_url = os.environ.get("CI_APP_DATABASE_URL")
    if not app_url:
        pytest.skip("requires isolated app-role URL for migrated PG")
    app_target, pg_target = make_url(app_url), make_url(pg_dsn)
    assert (app_target.host, app_target.port, app_target.database) == (
        pg_target.host,
        pg_target.port,
        pg_target.database,
    )
    stem = f"voice103-{uuid4().hex[:12]}"
    emails = [f"{stem}-{i}@example.test" for i in range(3)]
    tokens = [uuid4().hex for _ in emails]
    for key, value in {
        "MIMI_P0_DISABLE_DOTENV": "1",
        "APP_ENV": "local",
        "DATABASE_URL": app_url,
        "OAUTH_STATE_SECRET": uuid4().hex,
        "MIMI_PUBLIC_ORIGIN": "http://testserver",
        "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
        "ALLOWED_EMAILS": ",".join(emails[:2]),
        "MIMI_OWNER_WORKSPACE_ENABLED": "true",
        "MIMI_VOICE_ENABLED": "true",
        "MIMI_VOICE_V2_ENABLED": "true",
        "MIMI_GEMINI_API_KEY": "synthetic-deterministic-fixture",
        "MIMI_CALENDAR_READ_ENABLED": "true",
        "MIMI_COLLECTION_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "false",
        "MIMI_CONTEXT_V1_ENABLED": "false",
        "SESSION_COOKIE_SECURE": "false",
        "MIMI_NOTIFICATIONS_ENABLED": "false",
        "ENABLE_INPROCESS_CRON": "false",
    }.items():
        monkeypatch.setenv(key, value)
    caches = (get_settings, get_engine, get_sessionmaker, crypto._cipher)
    for item in caches:
        item.cache_clear()

    async def sql(query, *args):
        conn = await asyncpg.connect(pg_dsn)
        try:
            return await conn.fetch(query, *args)
        finally:
            await conn.close()

    ids = []
    for account, token in zip(emails, tokens, strict=True):
        asyncio.run(
            sql(
                "insert into microsched.session (token_hash,user_email,last_seen_at,expires_at) "
                "values ($1,$2,now(),now()+interval '1 day')",
                hash_session_token(token),
                account,
            )
        )
    pref_key = f"mimi.voice.fast_apply.v1:{OWNER_WORKSPACE_ID}"
    assert not asyncio.run(sql("select 1 from microsched.app_setting where key=$1", pref_key))
    try:
        with TestClient(create_app(), cookies={"ms_session": tokens[0]}) as client:
            yield SimpleNamespace(
                client=client,
                sql=sql,
                ids=ids,
                stem=stem,
                tokens=tokens,
                emails=emails,
            )
            client.portal.call(get_engine().dispose)
    finally:
        for cid in ids:
            asyncio.run(sql("delete from microsched.mimi_conversation where id=$1", UUID(cid)))
        asyncio.run(
            sql(
                "delete from microsched.task where title like $1 or title=$2",
                f"{stem}%",
                f"enc:v1:{stem}",
            )
        )
        asyncio.run(sql("delete from microsched.app_setting where key=$1", pref_key))
        asyncio.run(sql("delete from microsched.session where user_email=any($1::text[])", emails))
        for item in caches:
            item.cache_clear()


def use(rt, login):
    rt.client.cookies.set("ms_session", rt.tokens[login])


def rows(rt):
    return asyncio.run(
        rt.sql(
            "select id,title,collection_version,deleted_at from microsched.task "
            "where title like $1 order by title",
            f"{rt.stem}%",
        )
    )


def snapshot(rt, cid):
    response = rt.client.get(f"/api/mimi/conversations/{cid}")
    assert response.is_success, response.text
    return response.json()


def tool(name, identity, arguments):
    return {"toolCall": {"functionCalls": [{"id": identity, "name": name, "args": arguments}]}}


def start(rt, monkeypatch, *turns, on_tool=None, cid=None, on_send=None):
    client = rt.client
    if cid is None:
        cid, generation = new_conversation(client, rt.ids)
    else:
        generation = snapshot(rt, cid)["generation"]
    issued = mint(client, cid, generation)
    assert issued["max_seconds"] == 5400
    dials = []

    class Live:
        def __init__(self):
            self.events = asyncio.Queue()
            self.events.put_nowait({"setupComplete": {}})
            self.turns = iter(turns)

        async def send(self, raw):
            value = json.loads(raw)
            if on_send is not None:
                on_send(value)
            if "audio" in value.get("realtimeInput", {}):
                batch = next(self.turns, ())
                if callable(batch):
                    batch = batch()
                for event in batch:
                    self.events.put_nowait(event)
            if on_tool and "toolResponse" in value:
                for response in value["toolResponse"]["functionResponses"]:
                    for event in on_tool(response) or ():
                        self.events.put_nowait(event)

        async def recv(self):
            return json.dumps(await asyncio.wait_for(self.events.get(), 5))

    @asynccontextmanager
    async def connect(settings, *, run_id):
        assert str(run_id) == issued["run_id"]
        dials.append(run_id)
        yield Live()

    monkeypatch.setattr(voice_bridge, "connect_provider", connect)
    return cid, issued, dials


def turn(text, *calls, base=0.0, proven=True):
    parts = speech(text, base=base)
    if not proven:
        parts = [{"serverContent": {"inputTranscription": {"text": text}}}, parts[-1]]
    return [*parts[:-1], *calls, parts[-1]]


def receive_to(ws, event_type):
    values = []
    for _ in range(20):
        value = ws.receive_json()
        values.append(value)
        if value["type"] == event_type:
            return values
        assert value["type"] != "ended", values
    pytest.fail(f"did not receive {event_type}")


def say(ws):
    ws.send_bytes(PCM)
    return [
        event["status"]
        for event in receive_to(ws, "turn_complete")
        if event["type"] == "action_updated"
    ]


def confirm(rt, change):
    return rt.client.post(
        f"/api/mimi/change-sets/{change['id']}/decision",
        headers={**CSRF, "Idempotency-Key": f"voice103-preview-{uuid4()}"},
        json={"decision": "confirm", "digest": change["digest"], "nonce": change["nonce"]},
    )


def test_v2_preferences_shared_and_csrf_but_mic_ticket_remains_same_session(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    client = rt.client
    assert client.get("/api/mimi/capabilities").json()["voice_v2_enabled"] is True
    assert client.get("/api/mimi/voice-preferences").json() == {"fast_apply": True}
    assert (
        client.patch("/api/mimi/voice-preferences", json={"fast_apply": False}).status_code == 403
    )
    assert client.patch(
        "/api/mimi/voice-preferences", json={"fast_apply": False}, headers=CSRF
    ).json() == {"fast_apply": False}
    cid, issued, dials = start(rt, monkeypatch)
    use(rt, 1)
    assert client.get("/api/mimi/voice-preferences").json() == {"fast_apply": False}
    assert snapshot(rt, cid)["id"] == cid
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            endpoint(cid, issued), headers={"origin": "http://testserver"}
        ) as socket,
    ):
        socket.send_json({"type": "ticket", "ticket": issued["ticket"]})
        socket.receive_json()
    assert not dials
    use(rt, 2)
    assert client.get("/api/mimi/voice-preferences").status_code == 404
    assert client.get(f"/api/mimi/conversations/{cid}").status_code == 404
    use(rt, 0)
    with client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        assert receive_to(ws, "ready")[-1]["run_id"] == issued["run_id"]
        ws.send_json({"type": "microphone_lost"})
        assert receive_to(ws, "ended")[-1]["reason"] == "voice_microphone_lost"
    assert len(dials) == 1


def test_voice_apply_whole_five_then_conditional_undo_uses_existing_receipts(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    names = [f"{rt.stem} việc {n}" for n in range(5)]
    write = turn("Tạo việc: " + ", ".join(names), proposal("create", names))
    undo = {
        "toolCall": {"functionCalls": [{"id": "undo", "name": "voice_undo_latest_v1", "args": {}}]}
    }
    cid, issued, dials = start(
        rt,
        monkeypatch,
        write,
        turn("Hoàn tác cái vừa làm.", undo, base=0.2),
        turn("Hoàn tác cái vừa làm.", {**undo}, base=0.4),
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["applied"]
        before = rows(rt)
        assert len(before) == 5 and all(r["deleted_at"] is None for r in before)
        assert say(ws) == ["undone"]
        after = rows(rt)
        assert [r["id"] for r in after] == [r["id"] for r in before]
        assert all(r["deleted_at"] is not None for r in after)
        assert say(ws) == []  # repeated provider call ID cannot undo or mutate again
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    use(rt, 1)
    view = snapshot(rt, cid)
    assert len(view["receipts"]) == 2 and all(r["result"]["count"] == 5 for r in view["receipts"])
    assert len(dials) == 1
    assert any("Hoàn tác cái vừa làm" in m["content"] for m in view["messages"])

    async def projected_history():
        from app.agent.crypto import unwrap_dek
        from app.agent.models import MimiConversation

        async with get_sessionmaker()() as db:
            conv = await db.get(MimiConversation, UUID(cid))
            return await _provider_history(db, conv, unwrap_dek(conv.dek_wrapped))

    wire = json.dumps(rt.client.portal.call(projected_history), ensure_ascii=False)
    # Source-free responses remain available as context across Voice/Chat.
    assert VOICE_HISTORY_MARKER not in wire and "Đã nghe." in wire


@pytest.mark.parametrize("mode", ["six", "ambiguous", "disabled"])
def test_voice_uses_one_existing_preview_when_fast_apply_is_not_authorized(
    v2_runtime, monkeypatch, mode
):
    rt = v2_runtime
    count = 6 if mode == "six" else 1
    names = [f"{rt.stem} việc {n}" for n in range(count)]
    if mode == "disabled":
        assert rt.client.patch(
            "/api/mimi/voice-preferences", json={"fast_apply": False}, headers=CSRF
        ).is_success
    cmd = ("Tạo các việc sau: " if count == 6 else "Tạo việc: ") + ", ".join(names)
    script = [turn(cmd, proposal("all", names), proven=mode != "ambiguous")]
    cid, issued, _ = start(rt, monkeypatch, *script)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["needs_clarification" if mode == "ambiguous" else "preview"]
        assert not rows(rt)
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    use(rt, 1)
    view = snapshot(rt, cid)
    if mode == "ambiguous":
        assert not view["change_sets"] and not view["receipts"]
        return
    (preview,) = view["change_sets"]
    assert preview["state"] == "pending" and not view["receipts"]
    path = f"/api/mimi/change-sets/{preview['id']}/decision"
    headers = {**CSRF, "Idempotency-Key": f"voice103-preview-{uuid4()}"}
    payload = {"decision": "confirm", "digest": preview["digest"], "nonce": preview["nonce"]}
    first = rt.client.post(path, headers=headers, json=payload)
    assert first.is_success, first.text
    assert first.json()["result"]["count"] == count
    assert rt.client.post(path, headers=headers, json=payload).json() == first.json()
    assert len(rows(rt)) == count


def test_one_natural_date_manual_voice_receipt_can_be_undone_in_same_call(v2_runtime, monkeypatch):
    rt = v2_runtime
    title = f"{rt.stem} nộp bài"
    assert rt.client.patch(
        "/api/mimi/voice-preferences", headers=CSRF, json={"fast_apply": False}
    ).is_success
    undo = {
        "toolCall": {
            "functionCalls": [
                {"id": "undo-preview", "name": "voice_undo_latest_v1", "args": {}},
            ]
        }
    }
    create = proposal("natural-date", [title])
    fields = create["toolCall"]["functionCalls"][0]["args"]["entries"][0]["fields"]
    fields.update(due_precision="date", due_on="2091-04-03", due_at=None)
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(f"Tạo việc {title} hạn 3/4/2091.", create),
        turn("Hoàn tác cái vừa làm.", undo, base=0.2),
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["preview"]
        (preview,) = snapshot(rt, cid)["change_sets"]
        assert not rows(rt)
        use(rt, 1)
        response = confirm(rt, preview)
        assert response.is_success, response.text
        ack = receive_to(ws, "action_updated")[-1]
        assert ack["status"] == "applied" and ack["receipt_id"] == response.json()["id"]
        assert len(rows(rt)) == 1
        assert rt.client.patch(
            "/api/mimi/voice-preferences", headers=CSRF, json={"fast_apply": True}
        ).is_success
        assert say(ws) == ["undone"]
        (undone,) = rows(rt)
        assert undone["deleted_at"] is not None
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    assert len(snapshot(rt, cid)["receipts"]) == 2


def test_default_on_applies_single_natural_date_but_chat_still_needs_confirm(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    title = f"{rt.stem} nộp bài"
    spoken = proposal("date", [title])
    spoken["toolCall"]["functionCalls"][0]["args"]["entries"][0]["fields"].update(
        due_precision="date", due_on="2091-04-03", due_at=None
    )
    cid, issued, _ = start(rt, monkeypatch, turn(f"Tạo việc {title} hạn 3/4/2091.", spoken))
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["applied"]
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    (task,) = asyncio.run(
        rt.sql(
            "select id, due_on from microsched.task where title=$1",
            title,
        )
    )
    assert task["due_on"] == date(2091, 4, 3)
    assert len(snapshot(rt, cid)["receipts"]) == 1

    text_cid, _ = new_conversation(rt.client, rt.ids)
    response = rt.client.post(
        f"/api/mimi/conversations/{text_cid}/messages",
        headers=CSRF,
        json={"client_id": uuid4().hex, "content": f"Tạo việc {rt.stem} nhập text"},
    )
    assert response.is_success, response.text
    state = snapshot(rt, text_cid)
    (preview,) = state["change_sets"]
    assert preview["state"] == "pending" and not state["receipts"]
    assert len(rows(rt)) == 1
    assert confirm(rt, preview).is_success
    assert len(rows(rt)) == 2


def test_authorized_read_selection_and_exact_target_edit_in_voice(v2_runtime, monkeypatch):
    rt = v2_runtime
    exact, other = f"{rt.stem} alpha", f"{rt.stem} beta"
    first = rt.client.post(
        "/api/tasks",
        json={
            "title": exact,
            "body_md": "synthetic body",
            "items": ["synthetic checklist"],
            "due_precision": "date",
            "due_on": "2091-04-03",
        },
    )
    second = rt.client.post("/api/tasks", json={"title": other})
    assert first.is_success and second.is_success, (first.text, second.text)
    valid_id, other_id = first.json()["id"], second.json()["id"]
    (private,) = asyncio.run(
        rt.sql(
            "insert into microsched.task(title,is_private) values ($1,true) returning id",
            f"enc:v1:{rt.stem}",
        )
    )
    hidden_id = str(private["id"])
    replies = {}
    chosen = [valid_id]

    def plan_when_selected(response):
        name = response["name"]
        result = response["response"]["result"]
        replies[name] = result
        if name != "task_freeze_selection_v1" or "selection_id" not in result:
            return ()
        member = next(m for m in result["members"] if m["classification"] == "included")
        action = tool(
            "task_collection_candidate_v1",
            f"plan-{member['id']}",
            {
                "selection_id": result["selection_id"],
                "entries": [
                    {
                        "id": member["id"],
                        "action": "edit",
                        "fields": {"priority": "p2"},
                        "expected_collection_version": member["collection_version"],
                    }
                ],
            },
        )
        return [action, speech("irrelevant")[-1]]

    def utterance(base):
        args = {"filter": {"title_contains": rt.stem}}
        scoped = speech(f"Đặt ưu tiên việc {exact} thành p2.", base=base)
        target = chosen.pop(0) if chosen else valid_id
        suffix = f"{base}"
        return [
            *scoped[:-1],
            tool("task_query_v1", "query-" + suffix, args),
            tool("task_aggregate_v1", "count-" + suffix, {**args, "group_by": "status"}),
            tool(
                "task_inspect_batch_v1",
                "inspect-" + suffix,
                {"ids": [valid_id, other_id, hidden_id]},
            ),
            tool("task_read_content_v1", "content-" + suffix, {"id": valid_id}),
            tool(
                "calendar_read_v1", "calendar-" + suffix, {"date": "2091-04-03", "kinds": ["task"]}
            ),
            tool(
                "task_freeze_selection_v1",
                "selection-" + suffix,
                {
                    "intent": "Explicit named synthetic Task",
                    "variants_considered": [rt.stem],
                    "explicitly_named_subset": True,
                    "members": [
                        {
                            "id": tid,
                            "classification": "included" if tid == target else "excluded",
                            "reason": "Exact named synthetic target",
                        }
                        for tid in (valid_id, other_id)
                    ],
                },
            ),
        ]

    cid, issued, _ = start(
        rt,
        monkeypatch,
        lambda: utterance(0.0),
        on_tool=plan_when_selected,
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["applied"]
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    records = asyncio.run(
        rt.sql(
            "select id,priority from microsched.task where id=any($1::uuid[])",
            [UUID(valid_id), UUID(other_id)],
        )
    )
    assert {str(row["id"]): row["priority"] for row in records} == {valid_id: "p2", other_id: None}
    assert replies["task_aggregate_v1"]["groups"] == [{"value": "open", "count": 2}]
    assert replies["task_inspect_batch_v1"]["missing_ids"] == [hidden_id]
    assert replies["task_read_content_v1"]["rows"][0]["body_md"] == "synthetic body"
    assert (
        replies["task_read_content_v1"]["rows"][0]["items"][0]["content"] == "synthetic checklist"
    )
    assert any(row["id"] == valid_id for row in replies["calendar_read_v1"]["rows"])
    assert f"enc:v1:{rt.stem}" not in json.dumps(replies)
    (receipt,) = snapshot(rt, cid)["receipts"]
    assert receipt["result"]["task_ids"] == [valid_id]


@pytest.mark.parametrize("boundary", ["first_answer", "later_audio", "persist", "next_tool"])
def test_voice_rejects_obsolete_membership_at_source_boundary(v2_runtime, monkeypatch, boundary):
    rt = v2_runtime
    empty = boundary == "persist"
    query = boundary == "later_audio"
    body = "Synthetic answer from the original membership"
    obsolete = "Synthetic tail after membership changed"
    before = None
    if not empty:
        created = rt.client.post("/api/tasks", json={"title": f"{rt.stem} original"})
        assert created.is_success
        before = UUID(created.json()["id"])

    read_name = "task_query_v1" if empty or query else "task_aggregate_v1"
    args = {"filter": {"title_contains": rt.stem}}
    if read_name == "task_aggregate_v1":
        args["group_by"] = "status"
    request = tool(read_name, "first", args)
    first_result = Future()
    later_results = []

    def observe(response):
        result = response["response"]["result"]
        if response["id"] == "first":
            first_result.set_result(result)
        else:
            later_results.append(result)

    def answer(text, *, complete=False):
        return {"serverContent": {"outputTranscription": {"text": text}, "turnComplete": complete}}

    first = [request]
    if boundary in {"later_audio", "persist"}:
        first.append(answer(body))
    if boundary == "later_audio":
        # Cross the byte limit on the second caption without a wall-clock sleep.
        monkeypatch.setattr(voice_v2_bridge, "SOURCE_WINDOW_BYTES", 32)
    if empty:
        second = [{"serverContent": {"turnComplete": True}}]
    elif boundary == "next_tool":
        second = [
            tool("task_inspect_batch_v1", "followup", {"ids": [str(before)]}),
            answer(obsolete, complete=True),
        ]
    else:
        second = [answer(obsolete, complete=True)]
    cid, issued, _ = start(rt, monkeypatch, first, second, on_tool=observe)
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        ws.send_bytes(PCM)
        original = first_result.result(timeout=3)
        if "rows" in original:
            assert len(original["rows"]) == (0 if empty else 1)
        else:
            assert original["groups"] == [{"value": "open", "count": 1}]
        if boundary in {"later_audio", "persist"}:
            assert receive_to(ws, "transcript")[-1]["text"] == body

        if empty or query:
            # The matching set changes without touching any previously returned row.
            assert rt.client.post("/api/tasks", json={"title": f"{rt.stem} new"}).is_success
        else:
            # Previously counted Task is now PRIVATE with an opaque test title.
            changed = asyncio.run(
                rt.sql(
                    "update microsched.task set title=$1,is_private=true where id=$2 returning id",
                    f"enc:v1:{rt.stem}",
                    before,
                )
            )
            assert [row["id"] for row in changed] == [before]

        ws.send_bytes(PCM)
        frames = []
        for _ in range(12):
            event = ws.receive_json()
            frames.append(event)
            if event["type"] in {"reconnecting", "turn_complete", "ended"}:
                break
        if frames[-1]["type"] != "ended":
            ws.send_json({"type": "stop"})
            receive_to(ws, "ended")
    # The bridge drops the stale provider context. The caption sent before
    # drift was valid then, but it must not become an authoritative transcript.
    view = snapshot(rt, cid)
    assert not view["messages"], (boundary, frames, view["messages"])
    assert frames[-1]["type"] == "reconnecting"
    assert not any(f["type"] == "transcript_saved" or obsolete in f.get("text", "") for f in frames)
    assert not later_results


def test_voice_write_rolls_back_task_and_receipt_together_and_undo_refuses_newer_task(
    v2_runtime, monkeypatch
):
    rt = v2_runtime
    name = f"{rt.stem} draft"
    original = voice_v2_store._confirm_collection

    async def reject_after_flush(*args):
        await original(*args)
        raise HTTPException(409, "synthetic_conflict_after_collection_flush")

    monkeypatch.setattr(voice_v2_store, "_confirm_collection", reject_after_flush)
    undo = {
        "toolCall": {"functionCalls": [{"id": "later", "name": "voice_undo_latest_v1", "args": {}}]}
    }
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn(f"Tạo việc {name}", proposal("write1", [name])),
        turn(f"Tạo việc {name}", proposal("write2", [name]), base=0.2),
        turn("Hoàn tác cái vừa làm.", undo, base=0.4),
    )
    with rt.client.websocket_connect(
        endpoint(cid, issued), headers={"origin": "http://testserver"}
    ) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == ["rejected"]
        assert not rows(rt)
        assert snapshot(rt, cid)["receipts"] == []
        assert snapshot(rt, cid)["change_sets"] == []
        monkeypatch.setattr(voice_v2_store, "_confirm_collection", original)
        assert say(ws) == ["applied"]
        asyncio.run(
            rt.sql("update microsched.task set title=$1 where title=$2", name + " updated", name)
        )
        assert say(ws) == ["rejected"]
        (updated,) = rows(rt)
        assert updated["title"] == name + " updated" and updated["deleted_at"] is None
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
    assert len(snapshot(rt, cid)["receipts"]) == 1


@pytest.mark.parametrize(("count", "expected"), [(1, "applied"), (5, "applied"), (6, "preview")])
def test_natural_model_plan_uses_exact_cardinality_without_caption_grammar(
    v2_runtime, monkeypatch, count, expected
):
    rt = v2_runtime
    titles = [f"{rt.stem} natural {n}" for n in range(count)]
    seen = []
    cid, issued, _ = start(
        rt,
        monkeypatch,
        turn("Mimi lên giúp mình nguyên nhóm việc hôm nay nhé.", proposal("natural", titles)),
        on_tool=lambda response: seen.append(response),
    )
    with rt.client.websocket_connect(endpoint(cid, issued), headers=HEADERS) as ws:
        ws.send_json({"type": "ticket", "ticket": issued["ticket"]})
        receive_to(ws, "ready")
        assert say(ws) == [expected]
        view = snapshot(rt, cid)
        if expected == "preview":
            assert rows(rt) == []
            assert len([c for c in view["change_sets"] if c["state"] == "pending"]) == 1
            change = [c for c in view["change_sets"] if c["state"] == "pending"][0]
            assert len(change["operation"]["args"]["entries"]) == count
        else:
            assert [r["title"] for r in rows(rt)] == titles
            assert [c for c in view["change_sets"] if c["state"] == "pending"] == []
            assert len(seen) == 1 and seen[0]["id"] == "natural"
        assert len([c for c in view["change_sets"] if c["state"] == "pending"]) <= 1
        ws.send_json({"type": "stop"})
        receive_to(ws, "ended")
