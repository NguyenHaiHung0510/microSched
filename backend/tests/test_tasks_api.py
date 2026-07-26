"""Postgres-backed HTTP coverage for the task CRUD slice."""

import asyncio
import base64
import contextlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.domain.tasks import TaskCreate, TaskItemCreate, TaskStore, TaskUpdate
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg


def _auth(*, unlocked: bool = True) -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="api-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    """Keep API tests independent of developer and production secrets."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "task-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


async def _cleanup(dsn: str, task_ids: list[UUID]) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        for task_id in task_ids:
            await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
    finally:
        await conn.close()


async def _wait_until_blocked(monitor: asyncpg.Connection, pid: int, timeout: float = 10.0) -> None:
    """Wait until a competing store request is parked on the parent-row lock."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await monitor.fetchval(
            "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = $1",
            pid,
        ):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("expected item write to block on the parent task row")


def test_store_serializes_toggle_and_item_write_on_the_parent_row(pg_dsn):
    """The real store emits FOR UPDATE, so a competing item write sees the new flag."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(os.environ["NEON_MIGRATOR_URL"]))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monitor = await asyncpg.connect(pg_dsn)
        store = TaskStore()
        auth = _auth()
        task_id = None
        writer = None
        try:
            async with maker() as setup:
                created = await store.create(setup, auth, TaskCreate(title="Khoá dòng cha"))
                task_id = created.id
                await setup.commit()

            async with maker() as toggler, maker() as item_writer:
                writer_pid = (
                    await item_writer.execute(
                        # A harmless scalar query also pins this session's connection.
                        text("SELECT pg_backend_pid()")
                    )
                ).scalar_one()
                await store.update(toggler, auth, task_id, TaskUpdate(is_private=True))

                async def add_after_lock():
                    item = await store.add_item(
                        item_writer,
                        auth,
                        task_id,
                        TaskItemCreate(content="Nội dung đến sau"),
                    )
                    await item_writer.commit()
                    return item

                writer = asyncio.create_task(add_after_lock())
                await _wait_until_blocked(monitor, writer_pid)
                await toggler.commit()
                added = await asyncio.wait_for(writer, timeout=10.0)
                assert added is not None
                assert added.content == "Nội dung đến sau"

            conn = await asyncpg.connect(pg_dsn)
            try:
                stored = await conn.fetchval(
                    "SELECT content FROM microsched.task_item WHERE task_id = $1",
                    task_id,
                )
                assert stored.startswith("enc:v1:")
            finally:
                await conn.close()
        finally:
            if writer is not None and not writer.done():
                writer.cancel()
                with contextlib.suppress(BaseException):
                    await writer
            await _cleanup(pg_dsn, [task_id] if task_id is not None else [])
            await monitor.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_task_crud_and_nested_items_through_http(pg_dsn):
    """Happy path covers the list envelope, updates, filters, children, and deletes."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(os.environ["NEON_MIGRATOR_URL"]))
        maker = async_sessionmaker(engine, expire_on_commit=False)
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
                created_response = await client.post(
                    "/api/tasks",
                    json={
                        "title": "Chuẩn bị buổi họp",
                        "body_md": "Mang theo tài liệu.",
                        "priority": "p1",
                        "items": ["In tài liệu"],
                    },
                )
                assert created_response.status_code == 201
                created = created_response.json()
                task_id = UUID(created["id"])
                created_ids.append(task_id)
                first_item_id = created["items"][0]["id"]

                listed = await client.get("/api/tasks?status=open")
                assert listed.status_code == 200
                assert task_id in {UUID(task["id"]) for task in listed.json()["items"]}

                changed = await client.patch(
                    f"/api/tasks/{task_id}",
                    json={"title": "Chuẩn bị họp tuần", "body_md": None},
                )
                assert changed.status_code == 200
                assert changed.json()["title"] == "Chuẩn bị họp tuần"
                assert changed.json()["body_md"] is None

                checked = await client.patch(
                    f"/api/tasks/{task_id}/items/{first_item_id}",
                    json={"is_completed": True},
                )
                assert checked.status_code == 200
                assert checked.json()["is_completed"] is True

                appended = await client.post(
                    f"/api/tasks/{task_id}/items",
                    json={"content": "Gửi agenda", "position": 1},
                )
                assert appended.status_code == 201
                second_item_id = appended.json()["id"]

                items = await client.get(f"/api/tasks/{task_id}/items")
                assert [item["content"] for item in items.json()] == [
                    "In tài liệu",
                    "Gửi agenda",
                ]

                removed_item = await client.delete(f"/api/tasks/{task_id}/items/{second_item_id}")
                assert removed_item.status_code == 204

                completed = await client.patch(
                    f"/api/tasks/{task_id}", json={"status": "completed"}
                )
                assert completed.status_code == 200
                open_ids = {
                    UUID(task["id"])
                    for task in (await client.get("/api/tasks?status=open")).json()["items"]
                }
                completed_ids = {
                    UUID(task["id"])
                    for task in (await client.get("/api/tasks?status=completed")).json()["items"]
                }
                assert task_id not in open_ids
                assert task_id in completed_ids

                deleted = await client.delete(f"/api/tasks/{task_id}")
                assert deleted.status_code == 204
                assert (await client.get(f"/api/tasks/{task_id}")).status_code == 404
                assert (await client.get(f"/api/tasks/{task_id}/items")).status_code == 404
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_task_http_rejections_cover_401_404_422_and_locked_parent(pg_dsn):
    """Refusal paths stay generic and never let nested item access bypass the parent."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(os.environ["NEON_MIGRATOR_URL"]))
        maker = async_sessionmaker(engine, expire_on_commit=False)
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
                missing = uuid4()
                assert (await client.get(f"/api/tasks/{missing}")).status_code == 404
                assert (await client.post("/api/tasks", json={"title": ""})).status_code == 422
                assert (
                    await client.post("/api/tasks", json={"title": "x", "priority": "urgent"})
                ).status_code == 422
                assert (
                    await client.patch(f"/api/tasks/{missing}", json={"status": None})
                ).status_code == 422

                private_response = await client.post(
                    "/api/tasks",
                    json={
                        "title": "Nội dung riêng",
                        "is_private": True,
                        "items": ["Không được lộ"],
                    },
                )
                assert private_response.status_code == 201
                private_task = private_response.json()
                private_id = UUID(private_task["id"])
                created_ids.append(private_id)
                private_item_id = private_task["items"][0]["id"]

                reparent = await client.patch(
                    f"/api/tasks/{private_id}/items/{private_item_id}",
                    json={"task_id": str(uuid4())},
                )
                assert reparent.status_code == 422

                auth_state["value"] = _auth(unlocked=False)
                assert (await client.get(f"/api/tasks/{private_id}")).status_code == 404
                assert (await client.get(f"/api/tasks/{private_id}/items")).status_code == 404
                assert (
                    await client.post(
                        f"/api/tasks/{private_id}/items",
                        json={"content": "Không được ghi xuyên cổng"},
                    )
                ).status_code == 404

            unauthenticated_app = create_app()
            unauthenticated_transport = httpx.ASGITransport(app=unauthenticated_app)
            async with httpx.AsyncClient(
                transport=unauthenticated_transport, base_url="http://test"
            ) as client:
                response = await client.get("/api/tasks")
                assert response.status_code == 401
                assert response.json() == {"detail": "Not authenticated"}
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_restore_is_idempotent_and_preserves_items_and_privacy_gate(pg_dsn):
    """Restore recovers children, stays idempotent, and hides locked private rows."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(os.environ["NEON_MIGRATOR_URL"]))
        maker = async_sessionmaker(engine, expire_on_commit=False)
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
                created = (
                    await client.post(
                        "/api/tasks",
                        json={"title": "Có thể hoàn tác", "items": ["Mục một", "Mục hai"]},
                    )
                ).json()
                task_id = UUID(created["id"])
                created_ids.append(task_id)

                assert (await client.delete(f"/api/tasks/{task_id}")).status_code == 204
                assert task_id not in {
                    UUID(task["id"])
                    for task in (await client.get("/api/tasks?status=all")).json()["items"]
                }

                restored = await client.post(f"/api/tasks/{task_id}/restore")
                assert restored.status_code == 200
                assert restored.json() == {"id": str(task_id), "status": "restored"}
                assert set(restored.json()) == {"id", "status"}

                listed = (await client.get("/api/tasks?status=all")).json()["items"]
                restored_task = next(task for task in listed if UUID(task["id"]) == task_id)
                assert [item["content"] for item in restored_task["items"]] == [
                    "Mục một",
                    "Mục hai",
                ]

                second_restore = await client.post(f"/api/tasks/{task_id}/restore")
                assert second_restore.status_code == 200
                assert second_restore.content == restored.content

                live = (
                    await client.post("/api/tasks", json={"title": "Chưa từng xoá"})
                ).json()
                live_id = UUID(live["id"])
                created_ids.append(live_id)
                live_restore = await client.post(f"/api/tasks/{live_id}/restore")
                assert live_restore.status_code == 200
                assert live_restore.json() == {"id": str(live_id), "status": "restored"}

                missing_response = await client.post(f"/api/tasks/{uuid4()}/restore")
                assert missing_response.status_code == 404

                private = (
                    await client.post(
                        "/api/tasks",
                        json={
                            "title": "Không được lộ",
                            "body_md": "Nội dung riêng",
                            "is_private": True,
                        },
                    )
                ).json()
                private_id = UUID(private["id"])
                created_ids.append(private_id)
                assert (await client.delete(f"/api/tasks/{private_id}")).status_code == 204

                auth_state["value"] = _auth(unlocked=False)
                hidden_response = await client.post(f"/api/tasks/{private_id}/restore")
                missing_twin = await client.post(f"/api/tasks/{uuid4()}/restore")
                assert hidden_response.status_code == 404
                assert (
                    hidden_response.status_code,
                    hidden_response.content,
                ) == (
                    missing_twin.status_code,
                    missing_twin.content,
                )

                async with maker() as inspection:
                    deleted_at = (
                        await inspection.execute(
                            text(
                                "SELECT deleted_at FROM microsched.task "
                                "WHERE id = :task_id"
                            ),
                            {"task_id": private_id},
                        )
                    ).scalar_one()
                    assert deleted_at is not None

            unauthenticated_app = create_app()
            unauthenticated_transport = httpx.ASGITransport(app=unauthenticated_app)
            async with httpx.AsyncClient(
                transport=unauthenticated_transport, base_url="http://test"
            ) as client:
                response = await client.post(f"/api/tasks/{uuid4()}/restore")
                assert response.status_code == 401
                assert response.json() == {"detail": "Not authenticated"}
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())
