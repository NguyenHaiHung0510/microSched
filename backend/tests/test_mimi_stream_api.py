"""Postgres proof for Mimi's normalized, durable streaming path."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.models import MimiEvent, MimiProviderCall
from app.agent.openrouter import ProviderCompletion, ProviderDispatchError
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.db import get_engine, get_sessionmaker
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg

CSRF_HEADERS = {
    "Origin": "http://test",
    "Sec-Fetch-Site": "same-origin",
    "X-Mimi-CSRF": "1",
}


def test_stream_normalizes_events_and_encrypts_partial_text(pg_dsn, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-stream-api-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    monkeypatch.setenv("MIMI_REAL_CHAT_ENABLED", "true")
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("MIMI_STANDARD_API_KEY", "synthetic-key")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "synthetic/model")
    monkeypatch.setenv("MIMI_ROUTE_PROVIDER", "Synthetic")
    monkeypatch.setenv("MIMI_ROUTE_QUANTIZATION", "fp8")
    monkeypatch.setenv("MIMI_ROUTE_MAX_INPUT_PRICE", "1")
    monkeypatch.setenv("MIMI_ROUTE_MAX_OUTPUT_PRICE", "1")
    monkeypatch.setenv("DATABASE_URL", async_postgres_url(pg_dsn))
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    crypto._cipher.cache_clear()

    retry_attempts = 0
    cancel_started = asyncio.Event()

    async def fake_complete_stream(messages, *, settings, session_id, on_event, client=None):
        nonlocal retry_attempts
        del settings, session_id, client
        assert on_event is not None
        await on_event("provider.connected", {"status": 200})
        if messages[-1]["content"] == "cancel me":
            cancel_started.set()
            await asyncio.Event().wait()
        if messages[-1]["content"] == "retry me" and retry_attempts == 0:
            retry_attempts += 1
            raise ProviderDispatchError("retryable", 503)
        if messages[-1]["content"] == "unknown me":
            raise ProviderDispatchError("unknown", None, response_id="gen-unknown")
        await on_event("assistant.delta", {"text": "Xin "})
        await on_event("assistant.delta", {"text": "chào"})
        return ProviderCompletion(
            kind="text",
            task=None,
            text="Xin chào",
            response_id="gen-synthetic",
            usage={"prompt_tokens": 12, "completion_tokens": 2},
            provider="Synthetic",
            model="synthetic/model",
        )

    monkeypatch.setattr("app.agent.service.openrouter_complete_stream", fake_complete_stream)

    async def fake_get_generation(response_id, *, settings=None, client=None):
        del settings, client
        assert response_id == "gen-unknown"
        return {
            "id": response_id,
            "provider_name": "Synthetic",
            "total_cost": 0.001,
            "tokens_prompt": 12,
            "tokens_completion": 2,
        }

    monkeypatch.setattr("app.agent.service.openrouter_get_generation", fake_get_generation)

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash="mimi-stream-session",
            user_email="stream-owner@example.test",
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
        app = create_app()

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
        conversation_ids: list[str] = []
        conversation_id = None
        run_id = None
        try:
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    started = await client.post(
                        "/api/mimi/conversations", json={}, headers=CSRF_HEADERS
                    )
                    assert started.status_code == 201
                    conversation_id = started.json()["id"]
                    conversation_ids.append(conversation_id)
                    response = await client.post(
                        f"/api/mimi/conversations/{conversation_id}/messages/stream",
                        json={
                            "client_id": "stream-message-1",
                            "content": "hello",
                            "expected_generation": 1,
                        },
                        headers=CSRF_HEADERS,
                    )
                    assert response.status_code == 200
                    assert response.headers["content-type"].startswith("text/event-stream")
                    assert "event: provider.connected" in response.text
                    assert "event: assistant.delta" in response.text
                    assert "event: conversation.snapshot" in response.text
                    view = await client.get(f"/api/mimi/conversations/{conversation_id}")
                    assert view.json()["runs"][0]["state"] == "completed"
                    run_id = view.json()["runs"][0]["id"]
                    assert view.json()["messages"][-1]["content"] == "Xin chào"
                    assert any(
                        item["payload"].get("text") == "Xin chào"
                        for item in view.json()["events"]
                        if item["kind"] == "assistant.delta"
                    )

                    retry_conversation = await client.post(
                        "/api/mimi/conversations", json={}, headers=CSRF_HEADERS
                    )
                    retry_id = retry_conversation.json()["id"]
                    conversation_ids.append(retry_id)
                    failed = await client.post(
                        f"/api/mimi/conversations/{retry_id}/messages/stream",
                        json={
                            "client_id": "stream-message-retry",
                            "content": "retry me",
                            "expected_generation": 1,
                        },
                        headers=CSRF_HEADERS,
                    )
                    assert "event: provider.retryable" in failed.text
                    failed_view = await client.get(f"/api/mimi/conversations/{retry_id}")
                    failed_run_id = failed_view.json()["runs"][0]["id"]
                    assert failed_view.json()["runs"][0]["state"] == "retryable"

                    resumed = await client.post(
                        f"/api/mimi/runs/{failed_run_id}/resume",
                        json={},
                        headers=CSRF_HEADERS,
                    )
                    assert resumed.status_code == 200
                    assert "event: conversation.snapshot" in resumed.text
                    resumed_view = await client.get(f"/api/mimi/conversations/{retry_id}")
                    resumed_json = resumed_view.json()
                    assert [item["role"] for item in resumed_json["messages"]] == [
                        "user",
                        "assistant",
                        "assistant",
                    ]
                    assert [item["state"] for item in resumed_json["runs"]] == [
                        "retryable",
                        "completed",
                    ]
                    successor_id = resumed_json["runs"][-1]["id"]

                    async with maker() as db:
                        successor_call = (
                            await db.execute(
                                select(MimiProviderCall).where(
                                    MimiProviderCall.run_id == UUID(successor_id)
                                )
                            )
                        ).scalar_one()
                        assert successor_call.route["parent_run_id"] == failed_run_id
                        assert successor_call.route["checkpoint"] == "provider_dispatch"

                    cancel_conversation = await client.post(
                        "/api/mimi/conversations", json={}, headers=CSRF_HEADERS
                    )
                    cancel_id = cancel_conversation.json()["id"]
                    conversation_ids.append(cancel_id)
                    streaming = asyncio.create_task(
                        client.post(
                            f"/api/mimi/conversations/{cancel_id}/messages/stream",
                            json={
                                "client_id": "stream-message-cancel",
                                "content": "cancel me",
                                "expected_generation": 1,
                            },
                            headers=CSRF_HEADERS,
                        )
                    )
                    await asyncio.wait_for(cancel_started.wait(), timeout=3)
                    active = await client.get(f"/api/mimi/conversations/{cancel_id}")
                    active_run_id = active.json()["runs"][0]["id"]
                    cancelled = await client.post(
                        f"/api/mimi/runs/{active_run_id}/cancel",
                        json={},
                        headers=CSRF_HEADERS,
                    )
                    assert cancelled.status_code == 202
                    completed_stream = await asyncio.wait_for(streaming, timeout=3)
                    assert "event: run.cancelled" in completed_stream.text
                    cancelled_view = await client.get(
                        f"/api/mimi/conversations/{cancel_id}"
                    )
                    assert cancelled_view.json()["runs"][0]["state"] == "cancelled"
                    assert cancelled_view.json()["runs"][0]["provider_outcome"] == "unknown"

                    unknown_conversation = await client.post(
                        "/api/mimi/conversations", json={}, headers=CSRF_HEADERS
                    )
                    unknown_id = unknown_conversation.json()["id"]
                    conversation_ids.append(unknown_id)
                    unknown = await client.post(
                        f"/api/mimi/conversations/{unknown_id}/messages/stream",
                        json={
                            "client_id": "stream-message-unknown",
                            "content": "unknown me",
                            "expected_generation": 1,
                        },
                        headers=CSRF_HEADERS,
                    )
                    assert "event: provider.unknown" in unknown.text
                    unknown_view = await client.get(
                        f"/api/mimi/conversations/{unknown_id}"
                    )
                    unknown_run = unknown_view.json()["runs"][0]
                    assert unknown_run["state"] == "outcome_unknown"
                    refused_resume = await client.post(
                        f"/api/mimi/runs/{unknown_run['id']}/resume",
                        json={},
                        headers=CSRF_HEADERS,
                    )
                    assert refused_resume.status_code == 409
                    assert (
                        refused_resume.json()["detail"]
                        == "mimi_run_outcome_unknown_reconciliation_required"
                    )
                    reconciled = await client.post(
                        f"/api/mimi/runs/{unknown_run['id']}/reconcile",
                        json={},
                        headers=CSRF_HEADERS,
                    )
                    assert reconciled.status_code == 200
                    assert reconciled.json() == {
                        "run_id": unknown_run["id"],
                        "state": "halted",
                        "provider_outcome": "succeeded",
                        "result_available": False,
                    }
                    reconciled_view = await client.get(
                        f"/api/mimi/conversations/{unknown_id}"
                    )
                    assert reconciled_view.json()["runs"][0]["state"] == "halted"
                    assert any(
                        item["kind"] == "run.reconciled"
                        for item in reconciled_view.json()["events"]
                    )

            async with maker() as db:
                raw = (
                    await db.execute(
                        select(MimiEvent).where(
                            MimiEvent.run_id == UUID(run_id),
                            MimiEvent.kind == "assistant.delta",
                        )
                    )
                ).scalars().all()
                event = raw[0]
                assert "content_ciphertext" in event.payload
                assert "Xin chào" not in str(event.payload)
        finally:
            if conversation_ids:
                conn = await asyncpg.connect(pg_dsn)
                try:
                    for item in conversation_ids:
                        await conn.execute(
                            "DELETE FROM microsched.mimi_conversation WHERE id = $1",
                            UUID(item),
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
