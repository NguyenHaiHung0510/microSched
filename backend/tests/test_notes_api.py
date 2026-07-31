"""Postgres-backed coverage for the note CRUD slice."""

import asyncio
import base64
import contextlib
import os
import time
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
from app.domain.notes import NoteCreate, NoteItemCreate, NoteStore, NoteUpdate
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg


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
        token_hash="note-api-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    """Keep API tests independent of developer and production secrets."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "note-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


async def _cleanup(dsn: str, note_ids: list[UUID]) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        for note_id in note_ids:
            await conn.execute("DELETE FROM microsched.note WHERE id = $1", note_id)
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
    raise AssertionError("expected item write to block on the parent note row")


def test_store_serializes_note_toggle_and_item_write_on_the_parent_row(pg_dsn):
    """A competing item write waits for the toggle and encrypts under the new flag."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monitor = await asyncpg.connect(pg_dsn)
        store = NoteStore()
        auth = _auth()
        note_id = None
        writer = None
        try:
            async with maker() as setup:
                created = await store.create(setup, auth, NoteCreate(title="Khoá dòng cha"))
                note_id = created.id
                await setup.commit()

            async with maker() as toggler, maker() as item_writer:
                writer_pid = (
                    await item_writer.execute(text("SELECT pg_backend_pid()"))
                ).scalar_one()
                await store.update(toggler, auth, note_id, NoteUpdate(is_private=True))

                async def add_after_lock():
                    item = await store.add_item(
                        item_writer,
                        auth,
                        note_id,
                        NoteItemCreate(content="Nội dung đến sau"),
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
                    "SELECT content FROM microsched.note_item WHERE note_id = $1",
                    note_id,
                )
                assert stored.startswith("enc:v1:")
            finally:
                await conn.close()
        finally:
            if writer is not None and not writer.done():
                writer.cancel()
                with contextlib.suppress(BaseException):
                    await writer
            await _cleanup(pg_dsn, [note_id] if note_id is not None else [])
            await monitor.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_note_crud_nullable_title_checklist_restore_and_dto_boundary(pg_dsn):
    """HTTP CRUD keeps title nullable, supports checklist changes, and excludes embedding."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        created_ids: list[UUID] = []

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
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created_response = await client.post(
                    "/api/notes",
                    json={
                        "title": None,
                        "body_md": "Nội dung không cần tiêu đề.",
                        "items": ["Mục đầu", "Mục sau"],
                    },
                )
                assert created_response.status_code == 201
                created = created_response.json()
                note_id = UUID(created["id"])
                created_ids.append(note_id)
                first_item_id = created["items"][0]["id"]
                second_item_id = created["items"][1]["id"]
                assert created["title"] is None
                assert "embedding" not in created
                assert not {"status", "priority", "due_at", "pinned"} & set(created)

                conn = await asyncpg.connect(pg_dsn)
                try:
                    await conn.execute(
                        "UPDATE microsched.note SET embedding = $2::vector WHERE id = $1",
                        note_id,
                        "[0.25,0.5]",
                    )
                finally:
                    await conn.close()
                read_back = await client.get(f"/api/notes/{note_id}")
                assert read_back.status_code == 200
                assert "embedding" not in read_back.json()

                titled = await client.patch(
                    f"/api/notes/{note_id}",
                    json={"title": "Tiêu đề tạm", "body_md": None},
                )
                assert titled.status_code == 200
                assert titled.json()["title"] == "Tiêu đề tạm"
                cleared = await client.patch(f"/api/notes/{note_id}", json={"title": None})
                assert cleared.status_code == 200
                assert cleared.json()["title"] is None

                changed = await client.patch(
                    f"/api/notes/{note_id}/items/{first_item_id}",
                    json={"content": "Mục đầu đã sửa", "is_completed": True, "position": 2},
                )
                assert changed.status_code == 200
                assert changed.json()["content"] == "Mục đầu đã sửa"
                assert changed.json()["is_completed"] is True

                appended = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"content": "Mục giữa", "position": 1},
                )
                assert appended.status_code == 201
                appended_id = appended.json()["id"]

                items = await client.get(f"/api/notes/{note_id}/items")
                assert [item["content"] for item in items.json()] == [
                    "Mục sau",
                    "Mục giữa",
                    "Mục đầu đã sửa",
                ]
                assert (
                    await client.patch(
                        f"/api/notes/{note_id}/items/{second_item_id}",
                        json={"position": 3},
                    )
                ).status_code == 200
                assert (
                    await client.delete(f"/api/notes/{note_id}/items/{appended_id}")
                ).status_code == 204

                assert (await client.delete(f"/api/notes/{note_id}")).status_code == 204
                assert (await client.get(f"/api/notes/{note_id}")).status_code == 404
                assert (await client.get(f"/api/notes/{note_id}/items")).status_code == 404

                conn = await asyncpg.connect(pg_dsn)
                try:
                    assert (
                        await conn.fetchval(
                            "SELECT deleted_at IS NOT NULL FROM microsched.note WHERE id = $1",
                            note_id,
                        )
                        is True
                    )
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM microsched.note_item WHERE note_id = $1",
                            note_id,
                        )
                        == 2
                    )
                finally:
                    await conn.close()

                restored = await client.post(f"/api/notes/{note_id}/restore")
                assert restored.status_code == 200
                assert restored.json() == {"id": str(note_id), "status": "restored"}
                assert (
                    await client.post(f"/api/notes/{note_id}/restore")
                ).json() == restored.json()

                conn = await asyncpg.connect(pg_dsn)
                try:
                    await conn.execute("DELETE FROM microsched.note WHERE id = $1", note_id)
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM microsched.note_item WHERE note_id = $1",
                            note_id,
                        )
                        == 0
                    )
                finally:
                    await conn.close()
                created_ids.remove(note_id)
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_note_privacy_idempotency_and_rejections(pg_dsn):
    """Private reads, UUIDv7 retries, hidden conflicts, and refusal paths stay bounded."""

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
                note_id = _uuid7()
                created_ids.append(note_id)
                payload = {
                    "id": str(note_id),
                    "title": None,
                    "body_md": "Payload đầu",
                    "items": ["Mục đầu"],
                }
                first = await client.post("/api/notes", json=payload)
                repeated = await client.post("/api/notes", json=payload)
                changed_retry = await client.post(
                    "/api/notes",
                    json={**payload, "title": "Không ghi đè", "body_md": "Không đổi"},
                )
                assert first.status_code == 201
                assert repeated.status_code == changed_retry.status_code == 200
                assert first.json() == repeated.json() == changed_retry.json()

                assert (
                    await client.post(
                        "/api/notes", json={"id": str(uuid4()), "body_md": "Sai version"}
                    )
                ).status_code == 422
                assert (
                    await client.patch(f"/api/notes/{note_id}", json={"is_private": None})
                ).status_code == 422
                item_id = first.json()["items"][0]["id"]
                assert (
                    await client.patch(
                        f"/api/notes/{note_id}/items/{item_id}",
                        json={"note_id": str(_uuid7())},
                    )
                ).status_code == 422

                private_id = _uuid7()
                created_ids.append(private_id)
                private = await client.post(
                    "/api/notes",
                    json={
                        "id": str(private_id),
                        "title": None,
                        "body_md": "Nội dung riêng",
                        "is_private": True,
                        "items": ["Mục riêng"],
                    },
                )
                assert private.status_code == 201

                conn = await asyncpg.connect(pg_dsn)
                try:
                    stored = await conn.fetchrow(
                        "SELECT title, body_md FROM microsched.note WHERE id = $1",
                        private_id,
                    )
                    item_content = await conn.fetchval(
                        "SELECT content FROM microsched.note_item WHERE note_id = $1",
                        private_id,
                    )
                    assert stored["title"] is None
                    assert stored["body_md"].startswith("enc:v1:")
                    assert item_content.startswith("enc:v1:")
                finally:
                    await conn.close()

                auth_state["value"] = _auth(unlocked=False)
                listed_ids = {
                    UUID(note["id"]) for note in (await client.get("/api/notes")).json()["items"]
                }
                assert private_id not in listed_ids
                assert (await client.get(f"/api/notes/{private_id}")).status_code == 404
                assert (await client.get(f"/api/notes/{private_id}/items")).status_code == 404
                hidden_conflict = await client.post(
                    "/api/notes", json={"id": str(private_id), "body_md": "Không được lộ"}
                )
                assert hidden_conflict.status_code == 409
                assert hidden_conflict.content == b""
                locked_private_create = await client.post(
                    "/api/notes", json={"body_md": "Không được tạo", "is_private": True}
                )
                assert locked_private_create.status_code == 403

                auth_state["value"] = _auth()
                assert (await client.delete(f"/api/notes/{note_id}")).status_code == 204
                deleted_conflict = await client.post("/api/notes", json=payload)
                assert deleted_conflict.status_code == 409
                assert deleted_conflict.content == b""
                conn = await asyncpg.connect(pg_dsn)
                try:
                    assert (
                        await conn.fetchval(
                            "SELECT deleted_at IS NOT NULL FROM microsched.note WHERE id = $1",
                            note_id,
                        )
                        is True
                    )
                finally:
                    await conn.close()

            unauthenticated_app = create_app()
            unauthenticated_transport = httpx.ASGITransport(app=unauthenticated_app)
            async with httpx.AsyncClient(
                transport=unauthenticated_transport, base_url="http://test"
            ) as client:
                response = await client.get("/api/notes")
                assert response.status_code == 401
                assert response.json() == {"detail": "Not authenticated"}
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_notes_list_newest_first(pg_dsn):
    """The note list uses the spec's created-at descending order."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = NoteStore()
        auth = _auth()
        created_ids: list[UUID] = []
        try:
            async with maker() as db:
                older = await store.create(db, auth, NoteCreate(title="Cũ hơn"))
                await db.commit()
                await asyncio.sleep(0.01)
                newer = await store.create(db, auth, NoteCreate(title="Mới hơn"))
                await db.commit()
                created_ids.extend([older.id, newer.id])
                listed = await store.list(db, auth)
                relevant = [note.id for note in listed if note.id in set(created_ids)]
                assert relevant == [newer.id, older.id]
        finally:
            await _cleanup(pg_dsn, created_ids)
            await engine.dispose()

    asyncio.run(scenario())
