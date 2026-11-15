"""Actual app, sessions, WebSocket routes and migrated fixture Postgres; upstream fake only."""

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from starlette.websockets import WebSocketDisconnect

from app.agent import voice_bridge
from app.agent.compaction import CALENDAR_HISTORY_MARKER
from app.core import crypto
from app.core.db import get_engine, get_sessionmaker
from app.core.sessions import hash_session_token
from app.core.settings import get_settings
from app.main import create_app

pytestmark = pytest.mark.pg
HEADERS = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}
DATE = "2091-09-21"


def tool(kind, args):
    return {
        "toolCall": {"functionCalls": [{"id": kind, "name": f"calendar_{kind}_v1", "args": args}]}
    }


@pytest.fixture
def runtime(pg_dsn, monkeypatch):
    # The PG fixture supplies the migrated schema owner; app requests use the
    # actual restricted app role. Never look up an .env or an external endpoint.
    import os

    app_url = os.environ.get("CI_APP_DATABASE_URL")
    if not app_url:
        pytest.skip("requires isolated app-role URL for migrated PG")
    app_target, admin_target = make_url(app_url), make_url(pg_dsn)
    if (app_target.host, app_target.port, app_target.database) != (
        admin_target.host,
        admin_target.port,
        admin_target.database,
    ):
        pytest.fail("voice app and fixture Postgres must refer to the same database")
    token, other_token = uuid4().hex, uuid4().hex
    account = f"mimi-voice-{uuid4()}@example.test"
    conversation_ids, connected = [], []
    for key, value in {
        "MIMI_P0_DISABLE_DOTENV": "1",
        "APP_ENV": "local",
        "DATABASE_URL": app_url,
        "OAUTH_STATE_SECRET": "synthetic-mimi-voice",
        "MIMI_PUBLIC_ORIGIN": "http://testserver",
        "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
        "MIMI_VOICE_ENABLED": "true",
        "MIMI_GEMINI_API_KEY": "synthetic-deterministic-fixture",
        "MIMI_CALENDAR_READ_ENABLED": "true",
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

    async def sql(query, *params):
        db = await asyncpg.connect(pg_dsn)
        try:
            return await db.fetch(query, *params)
        finally:
            await db.close()

    now = datetime.now(UTC)
    for session_token in (token, other_token):
        asyncio.run(
            sql(
                "INSERT INTO microsched.session (token_hash,user_email,last_seen_at,expires_at) "
                "VALUES ($1,$2,$3,$4)",
                hash_session_token(session_token),
                account,
                now,
                now + timedelta(days=1),
            )
        )
    app = create_app()
    try:
        with TestClient(app, cookies={"ms_session": token}) as client:
            yield client, sql, conversation_ids, connected, other_token
            client.portal.call(get_engine().dispose)
    finally:
        for cid in conversation_ids:
            asyncio.run(sql("DELETE FROM microsched.mimi_conversation WHERE id=$1", UUID(cid)))
        asyncio.run(sql("DELETE FROM microsched.session WHERE user_email=$1", account))
        for item in caches:
            item.cache_clear()


def new_conversation(client, ids):
    value = client.post("/api/mimi/conversations", headers=HEADERS, json={}).json()
    ids.append(value["id"])
    return value["id"], value["generation"]


def mint(client, cid, gen):
    response = client.post(
        f"/api/mimi/conversations/{cid}/voice-ticket",
        headers=HEADERS,
        json={"expected_generation": gen},
    )
    assert response.is_success, response.text
    return response.json()


def endpoint(cid, value):
    return f"/api/mimi/conversations/{cid}/voice/{value['run_id']}"


def test_voice_wire_calendar_and_encrypted_same_conversation(runtime, monkeypatch):
    client, sql, ids, connections, _ = runtime
    cid, generation = new_conversation(client, ids)
    target = uuid4()
    asyncio.run(
        sql(
            "INSERT INTO microsched.day_annotation (id, starts_on, ends_on, label, is_private) "
            "VALUES ($1,$2::text::date,$2::text::date,$3,false)",
            target,
            DATE,
            "Voice visible fixture",
        )
    )
    private_target = uuid4()
    asyncio.run(
        sql(
            "INSERT INTO microsched.day_annotation (id, starts_on, ends_on, label, is_private) "
            "VALUES ($1,$2::text::date,$2::text::date,$3,true)",
            private_target,
            DATE,
            "PRIVATE sentinel voice fixture",
        )
    )

    @asynccontextmanager
    async def fake_connector(settings, *, run_id):
        sent = []
        connections.append(sent)
        queue = asyncio.Queue()

        class Fake:
            async def send(self, raw):
                value = json.loads(raw)
                sent.append(value)
                if "setup" in value:
                    await queue.put({"setupComplete": {}})
                elif "realtimeInput" in value and "audio" in value["realtimeInput"]:
                    await queue.put(tool("read", {"date": DATE, "kinds": ["annotation"]}))
                elif "toolResponse" in value:
                    response = value["toolResponse"]["functionResponses"][0]
                    if response["id"] == "read":
                        await queue.put(tool("inspect", {"kind": "annotation", "id": str(target)}))
                    else:
                        encoded = base64.b64encode(b"\x01\x00" * 480).decode()
                        await queue.put(
                            {
                                "serverContent": {
                                    "inputTranscription": {"text": "What is on my calendar?"},
                                }
                            }
                        )
                        await queue.put(
                            {
                                "serverContent": {
                                    "modelTurn": {
                                        "parts": [
                                            {
                                                "inlineData": {
                                                    "data": encoded,
                                                    "mimeType": "audio/pcm;rate=24000",
                                                }
                                            }
                                        ]
                                    },
                                    "outputTranscription": {
                                        "text": "Voice visible fixture is on the calendar."
                                    },
                                }
                            }
                        )
                        await queue.put(
                            {
                                "serverContent": {"turnComplete": True},
                                "usageMetadata": {
                                    "promptTokenCount": 5,
                                    "responseTokensDetails": [
                                        {"modality": "AUDIO", "tokenCount": 6},
                                    ],
                                },
                            }
                        )

            async def recv(self):
                return json.dumps(await queue.get())

        yield Fake()

    monkeypatch.setattr(voice_bridge, "connect_provider", fake_connector)
    try:
        response = client.get("/api/mimi/capabilities")
        assert (
            response.json()["voice_enabled"] is True
            and "synthetic-deterministic" not in response.text
        )
        value = mint(client, cid, generation)
        with client.websocket_connect(endpoint(cid, value), headers=HEADERS) as socket:
            socket.send_json({"type": "ticket", "ticket": value["ticket"]})
            assert socket.receive_json()["type"] == "ready"
            assert "historyConfig" not in connections[0][0]["setup"]
            conversation = client.get(f"/api/mimi/conversations/{cid}").json()
            blocked = client.post(
                f"/api/mimi/conversations/{cid}/messages",
                headers=HEADERS,
                json={
                    "client_id": "text-vs-voice",
                    "content": "blocked text turn",
                    "expected_generation": conversation["generation"],
                },
            )
            assert (
                blocked.status_code == 409
                and blocked.json()["detail"] == "finish_voice_before_text"
            )
            socket.send_bytes(b"\x00\x01" * 640)
            assert socket.receive_json()["role"] == "user"
            assert len(socket.receive_bytes()) == 960
            assert socket.receive_json()["role"] == "assistant"
            assert socket.receive_json()["type"] == "transcript_saved"
            assert socket.receive_json()["type"] == "turn_complete"
            socket.send_json({"type": "stop"})
            assert socket.receive_json() == {"type": "ended", "reason": "voice_stopped"}
        transcript = client.get(f"/api/mimi/conversations/{cid}").json()
        assert transcript["runs"][-1]["state"] == "completed"
        assert transcript["runs"][-1]["mode"] == "voice"
        assert transcript["provider_calls"][-1]["actual_model"] == "gemini-3.8-live"
        assert transcript["provider_calls"][-1]["cost_state"] == "unknown"
        assert [msg["role"] for msg in transcript["messages"]] == ["user", "assistant"]
        assert transcript["messages"][-1]["provenance"]["producer_code"] == "provider_voice"
        assert transcript["change_sets"] == []
        assert str(target) in json.dumps(connections[0]) and str(private_target) not in json.dumps(
            connections[0]
        )
        stored = asyncio.run(
            sql(
                "SELECT content_ciphertext FROM microsched.mimi_message WHERE conversation_id=$1",
                UUID(cid),
            )
        )
        assert len(stored) == 2 and all(
            row["content_ciphertext"].startswith("mimi:v1:") for row in stored
        )
        receipt = asyncio.run(
            sql(
                "SELECT usage FROM microsched.mimi_provider_call WHERE run_id=$1",
                UUID(value["run_id"]),
            )
        )
        assert json.loads(receipt[0]["usage"])["google_live_samples"][0]["promptTokenCount"] == 5

        # Reload into the same conversation; old Calendar-derived assistant
        # prose is replaced even when starting a fresh Google Live connection.
        second = mint(client, cid, transcript["generation"])
        with client.websocket_connect(endpoint(cid, second), headers=HEADERS) as socket:
            socket.send_json({"type": "ticket", "ticket": second["ticket"]})
            assert socket.receive_json()["type"] == "ready"
            assert (
                connections[1][0]["setup"]["historyConfig"]["initialHistoryInClientContent"] is True
            )
            seed = connections[1][1]["clientContent"]
            assert seed["turnComplete"] is True
            assert seed["turns"][-1]["parts"][0]["text"] == CALENDAR_HISTORY_MARKER
            assert "Voice visible fixture" not in json.dumps(seed)
            socket.send_json({"type": "stop"})
            assert socket.receive_json()["type"] == "ended"
        with client.websocket_connect(endpoint(cid, second), headers=HEADERS) as socket:
            socket.send_json({"type": "ticket", "ticket": second["ticket"]})
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
        assert len(connections) == 2
    finally:
        asyncio.run(
            sql(
                "DELETE FROM microsched.day_annotation WHERE id=ANY($1::uuid[])",
                [target, private_target],
            )
        )


def test_ticket_csrf_origin_session_and_expiry_before_dispatch(runtime, monkeypatch):
    client, sql, ids, connections, other = runtime

    @asynccontextmanager
    async def forbidden(*args, **kwargs):
        connections.append(True)
        raise AssertionError("unexpected provider invocation")
        yield  # pragma: no cover

    monkeypatch.setattr(voice_bridge, "connect_provider", forbidden)
    cid, generation = new_conversation(client, ids)
    assert (
        client.post(
            f"/api/mimi/conversations/{cid}/voice-ticket", json={"expected_generation": generation}
        ).status_code
        == 403
    )
    value = mint(client, cid, generation)
    path = endpoint(cid, value)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers={**HEADERS, "Origin": "http://elsewhere.test"}):
            pytest.fail("accepted cross-origin socket")
    with client.websocket_connect(
        path, headers={**HEADERS, "Cookie": f"ms_session={other}"}
    ) as socket:
        socket.send_json({"type": "ticket", "ticket": value["ticket"]})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    asyncio.run(
        sql(
            "UPDATE microsched.mimi_run SET execution_lease = jsonb_set(execution_lease, "
            "'{ticket_expires_at}', to_jsonb($2::text)) WHERE id=$1",
            UUID(value["run_id"]),
            (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        )
    )
    with client.websocket_connect(path, headers=HEADERS) as socket:
        socket.send_json({"type": "ticket", "ticket": value["ticket"]})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    assert not connections
    assert client.post(path + "/stop", headers=HEADERS, json={}).is_success
    assert client.get(f"/api/mimi/conversations/{cid}").json()["runs"][-1]["state"] == "cancelled"


@pytest.mark.parametrize("change", ["archive", "frontier"])
def test_actual_connect_revalidates_the_conversation(runtime, monkeypatch, change):
    client, sql, ids, connected, _ = runtime

    @asynccontextmanager
    async def forbidden(*args, **kwargs):
        connected.append(True)
        raise AssertionError("unexpected provider invocation")
        yield  # pragma: no cover

    monkeypatch.setattr(voice_bridge, "connect_provider", forbidden)
    cid, generation = new_conversation(client, ids)
    value = mint(client, cid, generation)
    update = "archived_at=now()" if change == "archive" else "context_frontier_sequence=1"
    asyncio.run(sql(f"UPDATE microsched.mimi_conversation SET {update} WHERE id=$1", UUID(cid)))
    with client.websocket_connect(endpoint(cid, value), headers=HEADERS) as socket:
        socket.send_json({"type": "ticket", "ticket": value["ticket"]})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    assert not connected


def test_logout_fences_transcript_persistence_and_keeps_dispatched_outcome_unknown(
    runtime, monkeypatch
):
    client, sql, ids, connected, _ = runtime

    @asynccontextmanager
    async def fake_connector(settings, *, run_id):
        queue = asyncio.Queue()

        class Fake:
            async def send(self, raw):
                value = json.loads(raw)
                if "setup" in value:
                    await queue.put({"setupComplete": {}})
                else:
                    await queue.put(
                        {
                            "serverContent": {
                                "outputTranscription": {"text": "Should not persist after logout"},
                                "turnComplete": True,
                            }
                        }
                    )

            async def recv(self):
                return json.dumps(await queue.get())

        connected.append(run_id)
        yield Fake()

    monkeypatch.setattr(voice_bridge, "connect_provider", fake_connector)
    cid, generation = new_conversation(client, ids)
    value = mint(client, cid, generation)
    with client.websocket_connect(endpoint(cid, value), headers=HEADERS) as socket:
        socket.send_json({"type": "ticket", "ticket": value["ticket"]})
        assert socket.receive_json()["type"] == "ready"
        assert client.post("/auth/logout").status_code == 204
        socket.send_bytes(b"\x00\x00" * 640)
        while True:
            message = socket.receive_json()
            assert message["type"] != "transcript_saved"
            if message["type"] == "ended":
                assert message["reason"] == "voice_session_expired"
                break
    rows = asyncio.run(
        sql(
            "SELECT state, provider_outcome FROM microsched.mimi_run WHERE id=$1",
            UUID(value["run_id"]),
        )
    )
    assert len(connected) == 1 and dict(rows[0]) == {
        "state": "outcome_unknown",
        "provider_outcome": "unknown",
    }
    assert not asyncio.run(
        sql("SELECT id FROM microsched.mimi_message WHERE conversation_id=$1", UUID(cid))
    )
