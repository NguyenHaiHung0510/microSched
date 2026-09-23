"""Postgres walking-skeleton proof for durable Mimi preview and execution."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.service import reconcile_refresh_markers
from app.core import crypto
from app.core.database_urls import async_postgres_url
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


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-p1-api-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="mimi-p1-session",
        user_email="owner@example.test",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(minutes=15),
    )


def test_preview_confirm_reload_feedback_and_recovery_are_durable(pg_dsn) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth = _auth()
        created_task_ids: list[str] = []
        conversation_ids: list[str] = []
        conversation_id = None

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
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                refused = await client.post("/api/mimi/conversations", json={})
                assert refused.status_code == 403

                started = await client.post(
                    "/api/mimi/conversations", json={}, headers=CSRF_HEADERS
                )
                assert started.status_code == 201
                conversation_id = started.json()["id"]
                conversation_ids.append(conversation_id)
                assert started.json()["sensitivity"] == "standard"
                assert started.json()["title"].startswith("Hội thoại mới ·")

                created_again = await client.post(
                    "/api/mimi/conversations",
                    json={"client_id": "create-idempotency-1"},
                    headers=CSRF_HEADERS,
                )
                repeated_create = await client.post(
                    "/api/mimi/conversations",
                    json={"client_id": "create-idempotency-1"},
                    headers=CSRF_HEADERS,
                )
                assert created_again.status_code == 201
                assert repeated_create.status_code == 201
                assert repeated_create.json()["id"] == created_again.json()["id"]
                conversation_ids.append(created_again.json()["id"])

                conversations = await client.get("/api/mimi/conversations?state=active&limit=1")
                assert conversations.status_code == 200
                assert len(conversations.json()["items"]) == 1
                assert conversations.json()["next_cursor"] is not None
                second_page = await client.get(
                    "/api/mimi/conversations?state=active&limit=1",
                    params={"cursor": conversations.json()["next_cursor"]},
                )
                assert second_page.status_code == 200
                assert (
                    second_page.json()["items"][0]["id"] != conversations.json()["items"][0]["id"]
                )

                renamed = await client.patch(
                    f"/api/mimi/conversations/{conversation_id}",
                    json={
                        "title": "  Kế hoạch Mimi tuần này  ",
                        "expected_metadata_version": 1,
                    },
                    headers=CSRF_HEADERS,
                )
                assert renamed.status_code == 200
                assert renamed.json()["title"] == "Kế hoạch Mimi tuần này"
                assert renamed.json()["title_locked"] is True

                archived = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/archive",
                    json={"expected_metadata_version": 2},
                    headers=CSRF_HEADERS,
                )
                assert archived.status_code == 200
                assert archived.json()["archived_at"] is not None
                archived_retry = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/archive",
                    json={"expected_metadata_version": 2},
                    headers=CSRF_HEADERS,
                )
                assert archived_retry.status_code == 200
                restored = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/restore",
                    json={"expected_metadata_version": 3},
                    headers=CSRF_HEADERS,
                )
                assert restored.status_code == 200
                assert restored.json()["archived_at"] is None

                message_body = {
                    "client_id": "message-1",
                    "content": "Tạo task Chuẩn bị demo Mimi",
                    "expected_generation": 1,
                }
                preview = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/messages",
                    json=message_body,
                    headers=CSRF_HEADERS,
                )
                assert preview.status_code == 200
                view = preview.json()
                assert [item["role"] for item in view["messages"]] == ["user", "assistant"]
                assert view["title"] == "Kế hoạch Mimi tuần này"
                assert view["runs"][0]["state"] == "waiting_confirmation"
                change_set = view["change_sets"][0]
                assert change_set["operation"]["tool"] == "task.create.v1"
                assert change_set["operation"]["args"]["is_private"] is False

                retried_message = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/messages",
                    json=message_body,
                    headers=CSRF_HEADERS,
                )
                assert retried_message.status_code == 200
                assert len(retried_message.json()["messages"]) == 2
                changed_message = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/messages",
                    json={**message_body, "content": "Nội dung khác"},
                    headers=CSRF_HEADERS,
                )
                assert changed_message.status_code == 409

                wrong_binding = await client.post(
                    f"/api/mimi/change-sets/{change_set['id']}/decision",
                    json={
                        "digest": "0" * 64,
                        "nonce": change_set["nonce"],
                        "decision": "confirm",
                    },
                    headers={**CSRF_HEADERS, "Idempotency-Key": "confirm-1"},
                )
                assert wrong_binding.status_code == 409

                confirmed = await client.post(
                    f"/api/mimi/change-sets/{change_set['id']}/decision",
                    json={
                        "digest": change_set["digest"],
                        "nonce": change_set["nonce"],
                        "decision": "confirm",
                    },
                    headers={**CSRF_HEADERS, "Idempotency-Key": "confirm-1"},
                )
                assert confirmed.status_code == 200
                receipt = confirmed.json()
                created_task_ids.append(receipt["task_id"])

                repeated = await client.post(
                    f"/api/mimi/change-sets/{change_set['id']}/decision",
                    json={
                        "digest": change_set["digest"],
                        "nonce": change_set["nonce"],
                        "decision": "confirm",
                    },
                    headers={**CSRF_HEADERS, "Idempotency-Key": "confirm-1"},
                )
                assert repeated.status_code == 200
                assert repeated.json() == receipt

                loaded = await client.get(f"/api/mimi/conversations/{conversation_id}")
                assert loaded.status_code == 200
                assert loaded.json()["runs"][0]["state"] == "completed"
                assert loaded.json()["receipts"][0]["task_id"] == receipt["task_id"]

                task = await client.get(f"/api/tasks/{receipt['task_id']}")
                assert task.status_code == 200
                assert task.json()["title"] == "Chuẩn bị demo Mimi"

                feedback_body = {
                    "client_id": "feedback-1",
                    "target_type": "receipt",
                    "target_id": receipt["id"],
                    "comment": "Preview cần rõ hơn",
                    "expected": "Hiện ngày hết hạn",
                    "evidence_bundle_ids": [],
                }
                feedback = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/feedback",
                    json=feedback_body,
                    headers=CSRF_HEADERS,
                )
                assert feedback.status_code == 201
                assert feedback.json()["unresolved"] is True
                feedback_retry = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/feedback",
                    json=feedback_body,
                    headers=CSRF_HEADERS,
                )
                assert feedback_retry.json()["id"] == feedback.json()["id"]
                feedback_conflict = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/feedback",
                    json={**feedback_body, "comment": "Nội dung feedback khác"},
                    headers=CSRF_HEADERS,
                )
                assert feedback_conflict.status_code == 409

                private = await client.post(
                    "/api/tasks", json={"title": "Bí mật", "is_private": True}
                )
                assert private.status_code == 201
                created_task_ids.append(private.json()["id"])
                context = await client.get("/api/mimi/context/tasks?limit=25")
                assert context.status_code == 200
                assert private.json()["id"] not in {item["id"] for item in context.json()}

            conn = await asyncpg.connect(pg_dsn)
            try:
                ciphertexts = await conn.fetch(
                    "SELECT content_ciphertext FROM microsched.mimi_message "
                    "WHERE conversation_id = $1",
                    UUID(conversation_id),
                )
                assert ciphertexts
                assert all(row["content_ciphertext"].startswith("mimi:v1:") for row in ciphertexts)
                assert all(
                    "Chuẩn bị demo Mimi" not in row["content_ciphertext"] for row in ciphertexts
                )
                title_ciphertext = await conn.fetchval(
                    "SELECT title_ciphertext FROM microsched.mimi_conversation WHERE id = $1",
                    UUID(conversation_id),
                )
                assert title_ciphertext.startswith("mimi:v1:")
                assert "Kế hoạch Mimi tuần này" not in title_ciphertext
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM microsched.mimi_execution_receipt r "
                        "JOIN microsched.mimi_change_set c ON c.id = r.change_set_id "
                        "JOIN microsched.mimi_run u ON u.id = c.run_id "
                        "WHERE u.conversation_id = $1",
                        UUID(conversation_id),
                    )
                    == 1
                )
                assert (
                    await conn.fetchval(
                        "SELECT state FROM microsched.mimi_refresh_marker WHERE receipt_id = $1",
                        UUID(receipt["id"]),
                    )
                    == "pending"
                )
            finally:
                await conn.close()

            async with maker() as db:
                assert await reconcile_refresh_markers(db) >= 1
                await db.commit()
            conn = await asyncpg.connect(pg_dsn)
            try:
                assert (
                    await conn.fetchval(
                        "SELECT state FROM microsched.mimi_refresh_marker WHERE receipt_id = $1",
                        UUID(receipt["id"]),
                    )
                    == "reconciled"
                )
            finally:
                await conn.close()
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                if conversation_id is not None:
                    await conn.execute(
                        "DELETE FROM microsched.audit_log WHERE trace_id = $1",
                        UUID(conversation_id),
                    )
                for stored_conversation_id in conversation_ids:
                    await conn.execute(
                        "DELETE FROM microsched.mimi_conversation WHERE id = $1",
                        UUID(stored_conversation_id),
                    )
                for task_id in created_task_ids:
                    await conn.execute("DELETE FROM microsched.task WHERE id = $1", UUID(task_id))
            finally:
                await conn.close()
            await engine.dispose()

    asyncio.run(scenario())
