"""Actual PostgreSQL/API contracts for the bounded V1 outbox slice."""

import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession, Entry, Task, Tracker
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def synthetic_settings(monkeypatch):
    for key, value in {
        "APP_ENV": "local",
        "MIMI_P0_DISABLE_DOTENV": "1",
        "OAUTH_STATE_SECRET": "r2-local-api-test",
        "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(
            b"r2-api-synthetic-key-32-bytes!!!!!"[:32]
        ).decode(),
        "ENABLE_INPROCESS_CRON": "false",
        "MIMI_LIVE_PROVIDER_ENABLED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


@asynccontextmanager
async def api(pg_dsn):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    auth = AuthSession(
        token_hash="r2-test",
        user_email="owner@test.local",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(hours=1),
    )
    app = create_app()

    async def database():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[require_session] = lambda: auth
    ids = {"tasks": [], "trackers": [], "entries": []}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, auth, ids
    finally:
        async with maker() as session:
            for model, key in [(Entry, "entries"), (Task, "tasks"), (Tracker, "trackers")]:
                if ids[key]:
                    await session.execute(delete(model).where(model.id.in_(ids[key])))
            await session.commit()
        await engine.dispose()


def test_initial_checklist_replay_and_atomic_collision(pg_dsn):
    async def run():
        async with api(pg_dsn) as (client, _, ids):
            parent, other, child = uuid7(), uuid7(), uuid7()
            ids["tasks"] += [parent, other]
            payload = {
                "id": str(parent),
                "title": "R2 initial",
                "items": ["one"],
                "item_ids": [str(child)],
            }
            first = await client.post("/api/tasks", json=payload)
            assert first.status_code == 201
            assert first.json()["items"][0]["id"] == str(child)
            changed = await client.patch(
                f"/api/tasks/{parent}/items/{child}", json={"content": "two"}
            )
            assert changed.status_code == 200
            replay = await client.post("/api/tasks", json=payload)
            assert replay.status_code == 200
            assert replay.json()["items"][0]["content"] == "two"
            collision = await client.post("/api/tasks", json={**payload, "id": str(other)})
            assert collision.status_code == 409
            assert (await client.get(f"/api/tasks/{other}")).status_code == 404
            invalid = await client.post("/api/tasks", json={**payload, "item_ids": []})
            assert invalid.status_code == 422

    asyncio.run(run())


def test_child_uuid_replay_collision_and_tombstone(pg_dsn):
    async def run():
        async with api(pg_dsn) as (client, _, ids):
            parent, other, child = uuid7(), uuid7(), uuid7()
            ids["tasks"] += [parent, other]
            for task_id in (parent, other):
                assert (
                    await client.post("/api/tasks", json={"id": str(task_id), "title": "R2 parent"})
                ).status_code == 201
            path = f"/api/tasks/{parent}/items"
            payload = {"id": str(child), "content": "one"}
            assert (await client.post(path, json=payload)).status_code == 201
            replay = await client.post(path, json={**payload, "content": "changed"})
            assert replay.status_code == 200 and replay.json()["content"] == "one"
            assert (await client.post(f"/api/tasks/{other}/items", json=payload)).status_code == 409
            assert (await client.delete(path + f"/{child}")).status_code == 204
            repeated = await client.delete(path + f"/{child}")
            assert repeated.status_code == 404
            assert repeated.headers.get("X-MicroSched-Error-Code") == "TASK_ITEM_ALREADY_DELETED"
            assert (await client.post(path, json=payload)).status_code == 409
            missing = await client.delete(path + f"/{uuid7()}")
            assert missing.status_code == 404 and "X-MicroSched-Error-Code" not in missing.headers

    asyncio.run(run())


def test_authorized_task_tombstone_never_discloses_hidden_private(pg_dsn):
    async def run():
        async with api(pg_dsn) as (client, auth, ids):
            public, private = uuid7(), uuid7()
            ids["tasks"] += [public, private]
            for task_id, hidden in ((public, False), (private, True)):
                assert (
                    await client.post(
                        "/api/tasks",
                        json={"id": str(task_id), "title": "R2 synthetic", "is_private": hidden},
                    )
                ).status_code == 201
                assert (await client.delete(f"/api/tasks/{task_id}")).status_code == 204
            replay = await client.delete(f"/api/tasks/{public}")
            assert replay.headers.get("X-MicroSched-Error-Code") == "TASK_ALREADY_DELETED"
            auth.private_until = None
            hidden = await client.delete(f"/api/tasks/{private}")
            missing = await client.delete(f"/api/tasks/{uuid7()}")
            assert hidden.status_code == missing.status_code == 404
            assert hidden.json() == missing.json()
            assert "X-MicroSched-Error-Code" not in hidden.headers
            denied = await client.post(
                "/api/tasks", json={"title": "R2 locked", "is_private": True}
            )
            assert denied.status_code == 403
            assert denied.headers.get("X-MicroSched-Error-Code") == "PRIVATE_UNLOCK_REQUIRED"

    asyncio.run(run())


def test_entry_tombstone_requires_current_visible_tracker(pg_dsn):
    async def run():
        async with api(pg_dsn) as (client, auth, ids):
            tracker, entry = uuid7(), uuid7()
            ids["trackers"].append(tracker)
            ids["entries"].append(entry)
            assert (
                await client.post(
                    "/api/tracker/trackers",
                    json={
                        "id": str(tracker),
                        "name": "R2 private synthetic",
                        "kind": "general",
                        "is_private": True,
                    },
                )
            ).status_code == 201
            path = f"/api/tracker/entries/{entry}"
            assert (
                await client.post(
                    "/api/tracker/entries",
                    json={
                        "id": str(entry),
                        "tracker_id": str(tracker),
                        "occurred_at": "2026-10-20T03:00:00Z",
                    },
                )
            ).status_code == 201
            assert (await client.delete(path)).status_code == 204
            replay = await client.delete(path)
            assert replay.headers.get("X-MicroSched-Error-Code") == "ENTRY_ALREADY_DELETED"
            auth.private_until = None
            hidden = await client.delete(path)
            missing = await client.delete(f"/api/tracker/entries/{uuid7()}")
            assert hidden.status_code == missing.status_code == 404
            assert hidden.json() == missing.json()
            assert "X-MicroSched-Error-Code" not in hidden.headers

    asyncio.run(run())


def test_optional_principal_fence_preserves_legacy_and_rejects_cross_account(pg_dsn):
    import hashlib

    async def run():
        async with api(pg_dsn) as (client, auth, ids):
            task_id = uuid7()
            ids["tasks"].append(task_id)
            body = {"id": str(task_id), "title": "R2 principal synthetic"}
            denied = await client.post(
                "/api/tasks",
                json=body,
                headers={
                    "X-MicroSched-Outbox-Principal": "0" * 64,
                    "X-MicroSched-Outbox-Protocol": "1",
                },
            )
            assert denied.status_code == 401
            assert denied.headers.get("X-MicroSched-Error-Code") == "OUTBOX_PRINCIPAL_MISMATCH"
            assert (await client.get(f"/api/tasks/{task_id}")).status_code == 404
            principal = hashlib.sha256(auth.user_email.strip().lower().encode()).hexdigest()
            unsupported = await client.post(
                "/api/tasks",
                json=body,
                headers={
                    "X-MicroSched-Outbox-Principal": principal,
                    "X-MicroSched-Outbox-Protocol": "999",
                },
            )
            assert unsupported.status_code == 409
            assert (
                unsupported.headers.get("X-MicroSched-Error-Code") == "OUTBOX_PROTOCOL_UNSUPPORTED"
            )
            accepted = await client.post(
                "/api/tasks",
                json=body,
                headers={
                    "X-MicroSched-Outbox-Principal": principal,
                    "X-MicroSched-Outbox-Protocol": "1",
                },
            )
            assert accepted.status_code == 201
            # The same old-client body still replays canonically without a new auth requirement.
            assert (await client.post("/api/tasks", json=body)).status_code == 200

    asyncio.run(run())
