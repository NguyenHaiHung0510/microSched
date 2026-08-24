"""Postgres-backed HTTP coverage for the task CRUD slice."""

import asyncio
import base64
import contextlib
import hashlib
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
        engine = create_async_engine(async_postgres_url(pg_dsn))
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


def test_store_serializes_concurrent_status_changes_before_reading_completed_at(pg_dsn):
    """A later completion reads the opener's committed status, never a stale one."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monitor = await asyncpg.connect(pg_dsn)
        store = TaskStore()
        auth = _auth()
        task_id = None
        writer = None
        initial_completed_at = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
        try:
            async with maker() as setup:
                created = await store.create(
                    setup, auth, TaskCreate(title="Chuyển trạng thái tuần tự", status="completed")
                )
                task_id = created.id
                await setup.execute(
                    text(
                        "UPDATE microsched.task "
                        "SET completed_at = :completed_at "
                        "WHERE id = :task_id"
                    ),
                    {"completed_at": initial_completed_at, "task_id": task_id},
                )
                await setup.commit()

            async with maker() as opener, maker() as completer:
                completer_pid = (
                    await completer.execute(text("SELECT pg_backend_pid()"))
                ).scalar_one()
                opened = await store.update(opener, auth, task_id, TaskUpdate(status="open"))
                assert opened is not None
                assert opened.completed_at is None

                async def complete_after_lock():
                    completed = await store.update(
                        completer,
                        auth,
                        task_id,
                        TaskUpdate(status="completed", title="Hoàn thành sau khi mở lại"),
                    )
                    await completer.commit()
                    return completed

                writer = asyncio.create_task(complete_after_lock())
                await _wait_until_blocked(monitor, completer_pid)
                await opener.commit()
                completed = await asyncio.wait_for(writer, timeout=10.0)
                assert completed is not None

            conn = await asyncpg.connect(pg_dsn)
            try:
                stored = await conn.fetchrow(
                    "SELECT status, completed_at, title FROM microsched.task WHERE id = $1",
                    task_id,
                )
                assert stored["status"] == "completed"
                assert stored["completed_at"] is not None
                assert stored["completed_at"] != initial_completed_at
                assert stored["title"] == "Hoàn thành sau khi mở lại"
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


def test_task_uuidv7_completed_create_replay_keeps_the_original_data(pg_dsn):
    """A replay keeps the first completed payload and returns the existing HTTP semantics."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth_state = {"value": _auth()}
        task_id = UUID("0190a0b0-c0d0-7e00-8000-000000000020")

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
        initial_payload = {
            "id": str(task_id),
            "title": "Bản gốc đã hoàn thành",
            "body_md": "Nội dung gốc phải được giữ nguyên.",
            "status": "completed",
            "priority": "p1",
            "items": ["Mục gốc"],
        }
        replay_payload = {
            "id": str(task_id),
            "title": "Không được ghi đè",
            "body_md": "Nội dung replay khác.",
            "status": "open",
            "priority": "p3",
            "items": ["Mục replay"],
        }
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post("/api/tasks", json=initial_payload)
                assert created.status_code == 201
                completed_at = created.json()["completed_at"]
                assert completed_at is not None

                replayed = await client.post("/api/tasks", json=replay_payload)
                assert replayed.status_code == 200
                replay = replayed.json()
                assert replay["id"] == str(task_id)
                assert replay["status"] == "completed"
                assert replay["completed_at"] == completed_at
                assert replay["title"] == initial_payload["title"]
                assert replay["body_md"] == initial_payload["body_md"]
                assert replay["priority"] == initial_payload["priority"]
                assert [item["content"] for item in replay["items"]] == initial_payload["items"]

                persisted = await client.get(f"/api/tasks/{task_id}")
                assert persisted.status_code == 200
                assert persisted.json()["status"] == "completed"
                assert persisted.json()["completed_at"] == completed_at
                assert persisted.json()["title"] == initial_payload["title"]
                assert persisted.json()["body_md"] == initial_payload["body_md"]
                assert persisted.json()["priority"] == initial_payload["priority"]
                assert [item["content"] for item in persisted.json()["items"]] == initial_payload[
                    "items"
                ]
        finally:
            await _cleanup(pg_dsn, [task_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_task_crud_and_nested_items_through_http(pg_dsn):
    """Happy path covers the list envelope, updates, filters, children, and deletes."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
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
                assert created["pinned"] is False
                assert created["completed_at"] is None
                assert (created["due_precision"], created["due_on"], created["due_at"]) == (
                    "none",
                    None,
                    None,
                )
                task_id = UUID(created["id"])
                created_ids.append(task_id)
                first_item_id = created["items"][0]["id"]

                listed = await client.get("/api/tasks?status=open&bucket=undated")
                assert listed.status_code == 200
                assert task_id in {UUID(task["id"]) for task in listed.json()["items"]}

                changed = await client.patch(
                    f"/api/tasks/{task_id}",
                    json={"title": "Chuẩn bị họp tuần", "body_md": None},
                )
                assert changed.status_code == 200
                assert changed.json()["title"] == "Chuẩn bị họp tuần"
                assert changed.json()["body_md"] is None

                pinned = await client.patch(
                    f"/api/tasks/{task_id}",
                    json={"pinned": True},
                )
                assert pinned.status_code == 200
                assert pinned.json()["pinned"] is True
                assert (await client.get(f"/api/tasks/{task_id}")).json()["pinned"] is True

                unpinned = await client.patch(
                    f"/api/tasks/{task_id}",
                    json={"pinned": False},
                )
                assert unpinned.status_code == 200
                assert unpinned.json()["pinned"] is False
                assert (await client.get(f"/api/tasks/{task_id}")).json()["pinned"] is False

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
                completed_at = completed.json()["completed_at"]
                assert completed_at is not None
                open_ids = {
                    UUID(task["id"])
                    for task in (await client.get("/api/tasks?status=open&bucket=undated")).json()[
                        "items"
                    ]
                }
                completed_ids = {
                    UUID(task["id"])
                    for task in (
                        await client.get("/api/tasks?status=completed&bucket=undated")
                    ).json()["items"]
                }
                assert task_id not in open_ids
                assert task_id in completed_ids

                same_status = await client.patch(
                    f"/api/tasks/{task_id}", json={"status": "completed"}
                )
                assert same_status.status_code == 200
                assert same_status.json()["completed_at"] == completed_at

                renamed = await client.patch(
                    f"/api/tasks/{task_id}", json={"title": "Giữ nguyên mốc hoàn thành"}
                )
                assert renamed.status_code == 200
                assert renamed.json()["completed_at"] == completed_at

                reopened = await client.patch(f"/api/tasks/{task_id}", json={"status": "open"})
                assert reopened.status_code == 200
                assert reopened.json()["completed_at"] is None

                initially_completed = await client.post(
                    "/api/tasks",
                    json={"title": "Tạo ở trạng thái đã xong", "status": "completed"},
                )
                assert initially_completed.status_code == 201
                assert initially_completed.json()["completed_at"] is not None
                created_ids.append(UUID(initially_completed.json()["id"]))

                deleted = await client.delete(f"/api/tasks/{task_id}")
                assert deleted.status_code == 204
                assert (await client.get(f"/api/tasks/{task_id}")).status_code == 404
                assert (await client.get(f"/api/tasks/{task_id}/items")).status_code == 404
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_task_http_temporal_matrix_and_legacy_replay_bytes(pg_dsn):
    """HTTP keeps legacy payloads valid while V2 writes expose an honest triad."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        created_ids: list[UUID] = []
        legacy_id = UUID("0190a0b0-c0d0-7e00-8000-000000000026")
        legacy_timed_id = UUID("0190a0b0-c0d0-7e00-8000-000000000027")

        async def current_session() -> AuthSession:
            return _auth()

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
        legacy_body = (
            b'{"id":"0190a0b0-c0d0-7e00-8000-000000000026","title":"legacy-none","due_at":null}'
        )
        before_hash = hashlib.sha256(legacy_body).hexdigest()
        before_length = len(legacy_body)
        legacy_timed_body = (
            b'{"id":"0190a0b0-c0d0-7e00-8000-000000000027",'
            b'"title":"legacy-timed","due_at":"2026-08-24T09:30:00+07:00"}'
        )
        timed_hash = hashlib.sha256(legacy_timed_body).hexdigest()
        timed_length = len(legacy_timed_body)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                first = await client.post(
                    "/api/tasks",
                    content=legacy_body,
                    headers={"Content-Type": "application/json"},
                )
                assert first.status_code == 201
                created_ids.append(legacy_id)
                assert first.json()["id"] == str(legacy_id)
                assert (
                    first.json()["due_precision"],
                    first.json()["due_on"],
                    first.json()["due_at"],
                ) == ("none", None, None)

                replay = await client.post(
                    "/api/tasks",
                    content=legacy_body,
                    headers={"Content-Type": "application/json"},
                )
                assert replay.status_code == 200
                assert replay.json()["id"] == str(legacy_id)
                for dispatched in (first.request.content, replay.request.content):
                    assert dispatched == legacy_body
                    assert hashlib.sha256(dispatched).hexdigest() == before_hash
                    assert len(dispatched) == before_length

                legacy_timed = await client.post(
                    "/api/tasks",
                    content=legacy_timed_body,
                    headers={"Content-Type": "application/json"},
                )
                assert legacy_timed.status_code == 201
                created_ids.append(legacy_timed_id)
                assert legacy_timed.json()["id"] == str(legacy_timed_id)
                assert legacy_timed.json()["due_precision"] == "datetime"
                assert legacy_timed.json()["due_on"] is None
                assert datetime.fromisoformat(legacy_timed.json()["due_at"]).astimezone(
                    UTC
                ) == datetime(2026, 8, 24, 2, 30, tzinfo=UTC)
                timed_replay = await client.post(
                    "/api/tasks",
                    content=legacy_timed_body,
                    headers={"Content-Type": "application/json"},
                )
                assert timed_replay.status_code == 200
                assert timed_replay.json()["id"] == str(legacy_timed_id)
                assert timed_replay.json()["due_precision"] == "datetime"
                for dispatched in (legacy_timed.request.content, timed_replay.request.content):
                    assert dispatched == legacy_timed_body
                    assert hashlib.sha256(dispatched).hexdigest() == timed_hash
                    assert len(dispatched) == timed_length

                civil = await client.post(
                    "/api/tasks",
                    json={
                        "title": "civil-date",
                        "due_precision": "date",
                        "due_on": "2026-08-24",
                    },
                )
                assert civil.status_code == 201
                civil_id = UUID(civil.json()["id"])
                created_ids.append(civil_id)
                assert (
                    civil.json()["due_precision"],
                    civil.json()["due_on"],
                    civil.json()["due_at"],
                ) == ("date", "2026-08-24", None)

                renamed = await client.patch(
                    f"/api/tasks/{civil_id}", json={"title": "civil-renamed"}
                )
                assert renamed.status_code == 200
                assert (
                    renamed.json()["due_precision"],
                    renamed.json()["due_on"],
                    renamed.json()["due_at"],
                ) == ("date", "2026-08-24", None)

                timed = await client.patch(
                    f"/api/tasks/{civil_id}",
                    json={
                        "due_precision": "datetime",
                        "due_at": "2026-08-25T14:20:00+07:00",
                    },
                )
                assert timed.status_code == 200
                assert timed.json()["due_precision"] == "datetime"
                assert timed.json()["due_on"] is None

                cleared = await client.patch(f"/api/tasks/{civil_id}", json={"due_at": None})
                assert cleared.status_code == 200
                assert (
                    cleared.json()["due_precision"],
                    cleared.json()["due_on"],
                    cleared.json()["due_at"],
                ) == ("none", None, None)

                invalid_payloads = [
                    {"due_precision": None},
                    {"due_on": "2026-08-24"},
                    {"due_precision": "date"},
                    {"due_precision": "datetime"},
                    {
                        "due_precision": "date",
                        "due_on": "2026-08-24",
                        "due_at": "2026-08-24T09:30:00+07:00",
                    },
                    {
                        "due_precision": "datetime",
                        "due_at": "2026-08-24T09:30:00",
                    },
                ]
                for invalid in invalid_payloads:
                    rejected = await client.post("/api/tasks", json={"title": "invalid", **invalid})
                    assert rejected.status_code == 422
                    assert any(
                        error["type"] == "task_schedule_invalid"
                        for error in rejected.json()["detail"]
                    )
                    rejected_patch = await client.patch(
                        f"/api/tasks/{civil_id}",
                        json=invalid,
                    )
                    assert rejected_patch.status_code == 422
                    assert any(
                        error["type"] == "task_schedule_invalid"
                        for error in rejected_patch.json()["detail"]
                    )
            conn = await asyncpg.connect(pg_dsn)
            try:
                for replayed_id in (legacy_id, legacy_timed_id):
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM microsched.task WHERE id = $1",
                            replayed_id,
                        )
                        == 1
                    )
            finally:
                await conn.close()
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_task_http_rejections_cover_401_404_422_and_locked_parent(pg_dsn):
    """Refusal paths stay generic and never let nested item access bypass the parent."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
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
                assert (
                    await client.patch(f"/api/tasks/{missing}", json={"pinned": None})
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
        engine = create_async_engine(async_postgres_url(pg_dsn))
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
                    for task in (await client.get("/api/tasks?status=all&bucket=undated")).json()[
                        "items"
                    ]
                }

                restored = await client.post(f"/api/tasks/{task_id}/restore")
                assert restored.status_code == 200
                assert restored.json() == {"id": str(task_id), "status": "restored"}
                assert set(restored.json()) == {"id", "status"}

                listed = (await client.get("/api/tasks?status=all&bucket=undated")).json()["items"]
                restored_task = next(task for task in listed if UUID(task["id"]) == task_id)
                assert [item["content"] for item in restored_task["items"]] == [
                    "Mục một",
                    "Mục hai",
                ]

                second_restore = await client.post(f"/api/tasks/{task_id}/restore")
                assert second_restore.status_code == 200
                assert second_restore.content == restored.content

                live = (await client.post("/api/tasks", json={"title": "Chưa từng xoá"})).json()
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
                            text("SELECT deleted_at FROM microsched.task WHERE id = :task_id"),
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
