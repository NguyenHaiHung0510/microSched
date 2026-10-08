"""P1C HTTP/SSE proof with a fake model and disposable PostgreSQL."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import service as mimi_service
from app.agent.context import AssistantText, PreviewCandidate
from app.agent.openrouter import AgentCompletion
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.db import get_engine, get_sessionmaker
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg
CSRF_HEADERS = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}


def test_p1c_stream_readonly_then_frozen_preview_without_duplicate_dispatch(
    pg_dsn, monkeypatch
) -> None:
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-p1c-stream-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    )
    monkeypatch.setenv("DATABASE_URL", async_postgres_url(pg_dsn))
    monkeypatch.setenv("MIMI_REAL_CHAT_ENABLED", "1")
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("MIMI_CONTEXT_V1_ENABLED", "1")
    monkeypatch.setenv("MIMI_STANDARD_API_KEY", "synthetic-never-sent")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "synthetic/model")
    monkeypatch.setenv("MIMI_ROUTE_PROVIDER", "Synthetic")
    monkeypatch.setenv("MIMI_ROUTE_QUANTIZATION", "fp16")
    monkeypatch.setenv("MIMI_ROUTE_MAX_INPUT_PRICE", "1")
    monkeypatch.setenv("MIMI_ROUTE_MAX_OUTPUT_PRICE", "1")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    crypto._cipher.cache_clear()
    calls = 0

    async def fake_stream(
        messages, *, settings, session_id, on_event, force_task_tool, agent_contract
    ):
        nonlocal calls
        assert agent_contract and not force_task_tool
        assert settings.mimi_route_model == "synthetic/model"
        calls += 1
        await on_event("provider.connected", {"status": 200})
        await on_event("provider.response_identity", {"response_id": f"synthetic-{calls}"})
        outcome = (
            AssistantText(text="Chào bạn, đây là câu trả lời chỉ đọc.")
            if calls == 1
            else PreviewCandidate(
                tool=CREATE_CANDIDATE_TOOL, arguments={"title": "Task synthetic P1C SSE"}
            )
        )
        return AgentCompletion(
            outcome=outcome,
            response_id=f"synthetic-{calls}",
            usage={"prompt_tokens": 24, "completion_tokens": 12},
            provider="Synthetic",
            model="synthetic/model",
        )

    monkeypatch.setattr(mimi_service, "openrouter_complete_stream", fake_stream)

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash="mimi-p1c-stream-session",
            user_email="owner@example.test",
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
        app = create_app()
        conversation_id = None
        created_task_id = None

        async def current_session() -> AuthSession:
            return auth

        async def request_session():
            async with maker() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        app.dependency_overrides[require_session] = current_session
        app.dependency_overrides[get_session] = request_session
        transport = httpx.ASGITransport(app=app)
        try:
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    created = await client.post(
                        "/api/mimi/conversations", json={}, headers=CSRF_HEADERS
                    )
                    assert created.status_code == 201
                    conversation_id = created.json()["id"]
                    for index, (user_text, expected_state) in enumerate(
                        (
                            ("Chào Mimi", "completed"),
                            ("Tạo Task synthetic P1C SSE", "waiting_confirmation"),
                        ),
                        start=1,
                    ):
                        response = await client.post(
                            f"/api/mimi/conversations/{conversation_id}/messages/stream",
                            json={
                                "client_id": f"p1c-sse-{index}",
                                "content": user_text,
                                "expected_generation": index,
                            },
                            headers=CSRF_HEADERS,
                        )
                        assert response.status_code == 200
                        assert "event: conversation.snapshot" in response.text
                        view_response = await client.get(
                            f"/api/mimi/conversations/{conversation_id}"
                        )
                        assert view_response.status_code == 200
                        view = view_response.json()
                        assert view["runs"][-1]["state"] == expected_state
                        assert len(view["change_sets"]) == index - 1
                        run_id = view["runs"][-1]["id"]
                        replay = await client.get(f"/api/mimi/runs/{run_id}/events?after=0")
                        assert replay.status_code == 200
                        assert any(
                            event["kind"] == "context.manifest" for event in replay.json()["events"]
                        )
                    assert calls == 2
                    assert view["change_sets"][0]["state"] == "pending"
                    conn = await asyncpg.connect(pg_dsn)
                    try:
                        assert (
                            await conn.fetchval(
                                "SELECT count(*) FROM microsched.task WHERE title=$1",
                                "Task synthetic P1C SSE",
                            )
                            == 0
                        )
                    finally:
                        await conn.close()
                    change_set = view["change_sets"][0]
                    confirmed = await client.post(
                        f"/api/mimi/change-sets/{change_set['id']}/decision",
                        json={
                            "digest": change_set["digest"],
                            "nonce": change_set["nonce"],
                            "decision": "confirm",
                        },
                        headers={**CSRF_HEADERS, "Idempotency-Key": "p1c-stream-confirm-1"},
                    )
                    assert confirmed.status_code == 200
                    created_task_id = confirmed.json()["task_id"]
                    repeated = await client.post(
                        f"/api/mimi/change-sets/{change_set['id']}/decision",
                        json={
                            "digest": change_set["digest"],
                            "nonce": change_set["nonce"],
                            "decision": "confirm",
                        },
                        headers={**CSRF_HEADERS, "Idempotency-Key": "p1c-stream-confirm-1"},
                    )
                    assert repeated.status_code == 200
                    assert repeated.json() == confirmed.json()
                    task = await client.get(f"/api/tasks/{created_task_id}")
                    assert task.status_code == 200
                    assert task.json()["title"] == "Task synthetic P1C SSE"
        finally:
            if conversation_id is not None or created_task_id is not None:
                conn = await asyncpg.connect(pg_dsn)
                try:
                    if conversation_id is not None:
                        await conn.execute(
                            "DELETE FROM microsched.audit_log WHERE trace_id=$1",
                            UUID(conversation_id),
                        )
                        await conn.execute(
                            "DELETE FROM microsched.mimi_conversation WHERE id=$1",
                            UUID(conversation_id),
                        )
                    if created_task_id is not None:
                        await conn.execute(
                            "DELETE FROM microsched.task WHERE id=$1", UUID(created_task_id)
                        )
                finally:
                    await conn.close()
            app.dependency_overrides.clear()
            await engine.dispose()

    try:
        asyncio.run(scenario())
    finally:
        engine = get_engine()
        if engine is not None:
            asyncio.run(engine.dispose())
        get_sessionmaker.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()
        crypto._cipher.cache_clear()
