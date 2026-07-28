"""Postgres proofs for client-selected UUIDv7 task creation."""

import asyncio
import base64
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg


class _CheckThenInsertBarrierSession(AsyncSession):
    """Make a preflight ``SELECT task.id`` race deterministic in the red proof."""

    barrier_active = False
    barrier_count = 0
    barrier = asyncio.Event()

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        if (
            self.barrier_active
            and sql.startswith("SELECT microsched.task.id")
            and "microsched.task.created_at" not in sql
        ):
            result = await super().execute(statement, *args, **kwargs)
            type(self).barrier_count += 1
            if type(self).barrier_count == 2:
                type(self).barrier.set()
            await asyncio.wait_for(type(self).barrier.wait(), timeout=5)
            return result
        return await super().execute(statement, *args, **kwargs)


def _uuid7() -> UUID:
    timestamp = int(time.time() * 1000)
    random_bits = int.from_bytes(os.urandom(10), "big") & ((1 << 74) - 1)
    value = (timestamp << 80) | (0x7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


def _auth(*, unlocked: bool = True) -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="idempotent-create-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "idempotent-create-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_client_selected_id_is_idempotent_and_race_safe(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(
            engine, expire_on_commit=False, class_=_CheckThenInsertBarrierSession
        )
        app = create_app()
        auth_state = {"value": _auth()}
        created_ids: list[UUID] = []

        async def current_session() -> AuthSession:
            return auth_state["value"]

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
                legacy = await client.post("/api/tasks", json={"title": "Server sinh id"})
                assert legacy.status_code == 201
                legacy_id = UUID(legacy.json()["id"])
                created_ids.append(legacy_id)
                assert legacy_id.version == 7

                task_id = _uuid7()
                created_ids.append(task_id)
                payload = {
                    "id": str(task_id),
                    "title": "Payload đầu",
                    "body_md": "Giữ nguyên",
                    "priority": "p1",
                    "items": ["Mục đầu"],
                }
                first = await client.post("/api/tasks", json=payload)
                assert first.status_code == 201
                assert UUID(first.json()["id"]) == task_id

                repeated = await client.post("/api/tasks", json=payload)
                assert repeated.status_code == 200
                assert repeated.json() == first.json()

                changed = await client.post(
                    "/api/tasks",
                    json={
                        **payload,
                        "title": "Không được ghi đè",
                        "body_md": "Không được đổi",
                        "priority": "p3",
                        "items": ["Mục khác", "Mục thứ hai"],
                    },
                )
                assert changed.status_code == 200
                assert changed.json() == first.json()

                conn = await asyncpg.connect(pg_dsn)
                try:
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM microsched.task WHERE id = $1", task_id
                        )
                        == 1
                    )
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM microsched.task_item WHERE task_id = $1",
                            task_id,
                        )
                        == 1
                    )
                finally:
                    await conn.close()

                invalid = await client.post(
                    "/api/tasks", json={"id": str(uuid4()), "title": "Sai version"}
                )
                assert invalid.status_code == 422

                race_id = _uuid7()
                created_ids.append(race_id)
                race_payload = {"id": str(race_id), "title": "Hai request cùng lúc"}
                _CheckThenInsertBarrierSession.barrier_active = True
                _CheckThenInsertBarrierSession.barrier_count = 0
                _CheckThenInsertBarrierSession.barrier = asyncio.Event()
                left, right = await asyncio.gather(
                    client.post("/api/tasks", json=race_payload),
                    client.post("/api/tasks", json=race_payload),
                )
                _CheckThenInsertBarrierSession.barrier_active = False
                assert sorted((left.status_code, right.status_code)) == [200, 201]
                assert left.json() == right.json()

                conn = await asyncpg.connect(pg_dsn)
                try:
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM microsched.task WHERE id = $1", race_id
                        )
                        == 1
                    )
                finally:
                    await conn.close()

                private_id = _uuid7()
                created_ids.append(private_id)
                private = await client.post(
                    "/api/tasks",
                    json={"id": str(private_id), "title": "Riêng tư", "is_private": True},
                )
                assert private.status_code == 201
                auth_state["value"] = _auth(unlocked=False)
                hidden = await client.post(
                    "/api/tasks", json={"id": str(private_id), "title": "Không được lộ"}
                )
                assert hidden.status_code == 409
                assert hidden.content == b""

                auth_state["value"] = _auth()
                deleted_id = _uuid7()
                created_ids.append(deleted_id)
                assert (
                    await client.post(
                        "/api/tasks", json={"id": str(deleted_id), "title": "Đã xoá"}
                    )
                ).status_code == 201
                assert (await client.delete(f"/api/tasks/{deleted_id}")).status_code == 204
                deleted_conflict = await client.post(
                    "/api/tasks", json={"id": str(deleted_id), "title": "Không hồi sinh"}
                )
                assert deleted_conflict.status_code == 409
                assert deleted_conflict.content == b""

                conn = await asyncpg.connect(pg_dsn)
                try:
                    assert (
                        await conn.fetchval(
                            "SELECT deleted_at IS NOT NULL FROM microsched.task WHERE id = $1",
                            deleted_id,
                        )
                        is True
                    )
                finally:
                    await conn.close()
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                for task_id in created_ids:
                    await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
            finally:
                await conn.close()
            await engine.dispose()

    asyncio.run(scenario())
