"""Focused Postgres acceptance for Task 070 backend idempotency seams."""

import asyncio
import base64
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
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
        token_hash="outbox070-test-session",
        user_email="owner@example.test",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "outbox070-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_client_id_replays_atomic_note_reorder_and_calendar_creates(pg_dsn: str) -> None:
    """New creates are replay-safe, and invalid reorder input changes no rows."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth_state = {"value": _auth()}

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
        note_ids: list[UUID] = []
        task_ids: list[UUID] = []
        source_ids: list[UUID] = []
        group_ids: list[UUID] = []
        annotation_ids: list[UUID] = []
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                note = await client.post("/api/notes", json={"title": "outbox070 note"})
                assert note.status_code == 201
                note_id = UUID(note.json()["id"])
                note_ids.append(note_id)

                item_ids = [_uuid7() for _ in range(4)]
                first = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"id": str(item_ids[0]), "content": "initial", "position": 0},
                )
                assert first.status_code == 201
                replay = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"id": str(item_ids[0]), "content": "must not overwrite", "position": 99},
                )
                assert replay.status_code == 200
                assert replay.json()["content"] == "initial"
                assert len((await client.get(f"/api/notes/{note_id}/items")).json()) == 1

                second = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"id": str(item_ids[1]), "content": "middle", "position": 1},
                )
                third = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"id": str(item_ids[2]), "content": "last before delete", "position": 2},
                )
                assert (second.status_code, third.status_code) == (201, 201)
                assert [
                    first.json()["position"],
                    second.json()["position"],
                    third.json()["position"],
                ] == [0, 1, 2]
                replay_with_middle_position = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"id": str(item_ids[0]), "content": "still initial", "position": 1},
                )
                assert replay_with_middle_position.status_code == 200
                assert replay_with_middle_position.json()["content"] == "initial"
                before_delete = await client.get(f"/api/notes/{note_id}/items")
                assert [item["position"] for item in before_delete.json()] == [0, 1, 2]
                removed = await client.delete(f"/api/notes/{note_id}/items/{item_ids[1]}")
                assert removed.status_code == 204
                appended = await client.post(
                    f"/api/notes/{note_id}/items",
                    json={"id": str(item_ids[3]), "content": "append after gap", "position": 2},
                )
                assert appended.status_code == 201
                assert appended.json()["position"] == 3

                reorder_path = f"/api/notes/{note_id}/items/positions"
                reorder = await client.patch(
                    reorder_path,
                    json={
                        "items": [
                            {"id": str(item_ids[0]), "position": 8},
                            {"id": str(item_ids[2]), "position": 6},
                            {"id": str(item_ids[3]), "position": 7},
                        ]
                    },
                )
                assert reorder.status_code == 200
                assert [item["id"] for item in reorder.json()] == [
                    str(item_ids[2]),
                    str(item_ids[3]),
                    str(item_ids[0]),
                ]
                before_bad_reorder = {
                    item["id"]: item["position"]
                    for item in (await client.get(f"/api/notes/{note_id}/items")).json()
                }
                duplicate_positions = await client.patch(
                    reorder_path,
                    json={
                        "items": [
                            {"id": str(item_ids[0]), "position": 1},
                            {"id": str(item_ids[2]), "position": 1},
                        ]
                    },
                )
                assert duplicate_positions.status_code == 422

                other_note = await client.post("/api/notes", json={"title": "outbox070 other"})
                assert other_note.status_code == 201
                other_note_id = UUID(other_note.json()["id"])
                note_ids.append(other_note_id)
                foreign_id = _uuid7()
                foreign = await client.post(
                    f"/api/notes/{other_note_id}/items",
                    json={"id": str(foreign_id), "content": "foreign", "position": 0},
                )
                assert foreign.status_code == 201
                hidden_item_collision = await client.post(
                    f"/api/notes/{other_note_id}/items",
                    json={
                        "id": str(item_ids[0]),
                        "content": "must not cross parent",
                        "position": 1,
                    },
                )
                assert hidden_item_collision.status_code == 409
                assert hidden_item_collision.content == b""
                foreign_reorder = await client.patch(
                    reorder_path,
                    json={
                        "items": [
                            {"id": str(item_ids[0]), "position": 11},
                            {"id": str(foreign_id), "position": 12},
                        ]
                    },
                )
                assert foreign_reorder.status_code == 422
                after_bad_reorder = {
                    item["id"]: item["position"]
                    for item in (await client.get(f"/api/notes/{note_id}/items")).json()
                }
                assert after_bad_reorder == before_bad_reorder

                task = await client.post("/api/tasks", json={"title": "outbox070 task"})
                assert task.status_code == 201
                task_id = UUID(task.json()["id"])
                task_ids.append(task_id)
                task_item_id = _uuid7()
                task_item = await client.post(
                    f"/api/tasks/{task_id}/items",
                    json={"id": str(task_item_id), "content": "task child", "position": 0},
                )
                task_replay = await client.post(
                    f"/api/tasks/{task_id}/items",
                    json={"id": str(task_item_id), "content": "changed replay", "position": 7},
                )
                assert task_item.status_code == 201 and task_replay.status_code == 200
                assert task_replay.json()["content"] == "task child"
                assert len((await client.get(f"/api/tasks/{task_id}/items")).json()) == 1

                source_id = _uuid7()
                source_ids.append(source_id)
                source = await client.post(
                    "/api/calendar/sources",
                    json={"id": str(source_id), "name": "outbox070 source", "kind": "manual"},
                )
                source_replay = await client.post(
                    "/api/calendar/sources",
                    json={"id": str(source_id), "name": "changed source payload", "kind": "manual"},
                )
                assert source.status_code == 201 and source_replay.status_code == 200
                assert source_replay.json()["name"] == "outbox070 source"
                event_id = _uuid7()
                event_payload = {
                    "id": str(event_id),
                    "source_id": str(source_id),
                    "title": "original event",
                    "starts_at": "2026-10-01T09:00:00+07:00",
                    "ends_at": "2026-10-01T10:00:00+07:00",
                }
                event = await client.post("/api/calendar/events", json=event_payload)
                event_replay = await client.post(
                    "/api/calendar/events", json={**event_payload, "title": "changed event"}
                )
                assert event.status_code == 201 and event_replay.status_code == 200
                assert event_replay.json()["title"] == "original event"

                group_id = _uuid7()
                group_ids.append(group_id)
                group = await client.post(
                    "/api/tracker/groups",
                    json={"id": str(group_id), "name": "outbox070 group", "kind": "health"},
                )
                group_replay = await client.post(
                    "/api/tracker/groups",
                    json={"id": str(group_id), "name": "changed group", "kind": "health"},
                )
                assert group.status_code == 201 and group_replay.status_code == 200
                assert group_replay.json()["name"] == "outbox070 group"

                annotation_id = _uuid7()
                annotation_ids.append(annotation_id)
                annotation_payload = {
                    "id": str(annotation_id),
                    "starts_on": "2026-10-01",
                    "label": "outbox070 private annotation",
                    "is_private": True,
                }
                annotation = await client.post("/api/calendar/annotations", json=annotation_payload)
                assert annotation.status_code == 201
                auth_state["value"] = _auth(unlocked=False)
                hidden_collision = await client.post(
                    "/api/calendar/annotations", json=annotation_payload
                )
                assert hidden_collision.status_code == 409
                assert hidden_collision.content == b""

                locked_note = await client.post(
                    "/api/notes", json={"title": "private while locked", "is_private": True}
                )
                assert locked_note.status_code == 403
                assert locked_note.json()["detail"]["code"] == "PRIVATE_UNLOCK_REQUIRED"
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                for annotation_id in annotation_ids:
                    await conn.execute(
                        "DELETE FROM microsched.day_annotation WHERE id = $1", annotation_id
                    )
                for note_id in note_ids:
                    await conn.execute("DELETE FROM microsched.note WHERE id = $1", note_id)
                for task_id in task_ids:
                    await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
                for source_id in source_ids:
                    await conn.execute(
                        "DELETE FROM microsched.calendar_source WHERE id = $1", source_id
                    )
                for group_id in group_ids:
                    await conn.execute(
                        "DELETE FROM microsched.tracker_group WHERE id = $1", group_id
                    )
            finally:
                await conn.close()
                await engine.dispose()

    asyncio.run(scenario())


def test_tracker_create_replays_same_uuidv7_before_name_conflict(pg_dsn: str) -> None:
    """A readable same-ID retry returns the stored tracker, including same-name retries."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth_state = {"value": _auth()}

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
        tracker_id = _uuid7()
        hidden_tracker_id = _uuid7()
        tracker_ids = [tracker_id, hidden_tracker_id]
        payload = {
            "id": str(tracker_id),
            "name": f"outbox070 replay {tracker_id}",
            "kind": "health",
            "input_mode": "event",
        }
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                first = await client.post("/api/tracker/trackers", json=payload)
                replay = await client.post("/api/tracker/trackers", json=payload)
                assert first.status_code == 201
                assert replay.status_code == 200
                assert replay.json() == first.json()

                changed_replay = await client.post(
                    "/api/tracker/trackers",
                    json={**payload, "name": "different retry title", "kind": "finance"},
                )
                assert changed_replay.status_code == 200
                assert changed_replay.json() == first.json()

                duplicate_name = await client.post(
                    "/api/tracker/trackers",
                    json={**payload, "id": str(_uuid7())},
                )
                assert duplicate_name.status_code == 409

                private = await client.post(
                    "/api/tracker/trackers",
                    json={
                        "id": str(hidden_tracker_id),
                        "name": f"outbox070 hidden {hidden_tracker_id}",
                        "kind": "health",
                        "input_mode": "event",
                        "is_private": True,
                    },
                )
                assert private.status_code == 201
                auth_state["value"] = _auth(unlocked=False)
                hidden_collision = await client.post(
                    "/api/tracker/trackers",
                    json={
                        "id": str(hidden_tracker_id),
                        "name": f"outbox070 collision {hidden_tracker_id}",
                        "kind": "health",
                        "input_mode": "event",
                    },
                )
                assert hidden_collision.status_code == 409
                assert hidden_collision.content == b""
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute("DELETE FROM microsched.tracker WHERE id = ANY($1)", tracker_ids)
            finally:
                await conn.close()
                await engine.dispose()

    asyncio.run(scenario())
