"""Task 017 response-loss coverage using the real PostgreSQL test lane.

The ASGI dependency commits before the test transport returns. The first response
is then deliberately discarded before its simulated caller can observe it. Auth
uses an explicit synthetic dependency override; it does not prove browser/OAuth
authentication behavior.
"""

import asyncio
import base64
import os
import time
from datetime import UTC, datetime, timedelta, timezone
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


def _uuid7() -> UUID:
    timestamp = int(time.time() * 1000)
    random_bits = int.from_bytes(os.urandom(10), "big") & ((1 << 74) - 1)
    value = (timestamp << 80) | (0x7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


def _auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash=f"outbox017-loss-{_uuid7()}",
        user_email="owner@example.test",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(minutes=15),
    )


class _CommittedResponseDropped(Exception):
    """The request committed, but its response did not reach the simulated caller."""


async def _post_then_drop(client: httpx.AsyncClient, path: str, payload: dict) -> None:
    response = await client.post(path, json=payload)
    assert 200 <= response.status_code < 300, (path, response.text)
    raise _CommittedResponseDropped


@pytest.fixture(autouse=True)
def synthetic_local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "outbox017-response-loss-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


@pytest.mark.parametrize(
    "operation",
    [
        "task.create",
        "note.create",
        "task_item.create",
        "note_item.create",
        "calendar_source.create",
        "calendar_event.create",
        "day_annotation.create",
        "tracker_group.create",
        "tracker.create",
        "entry.create",
        "subscription.create",
    ],
)
@pytest.mark.pg
def test_post_create_replays_after_committed_response_loss(pg_dsn: str, operation: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth = _auth()

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
        created: list[tuple[str, UUID]] = []

        async def post_new(path: str, payload: dict, table: str, entity_id: UUID) -> dict:
            created.append((table, entity_id))
            response = await client.post(path, json=payload)
            assert response.status_code == 201, (path, response.text)
            return response.json()

        async def retry_after_lost_response(path: str, payload: dict, entity_id: UUID) -> dict:
            with pytest.raises(_CommittedResponseDropped):
                await _post_then_drop(client, path, payload)
            response = await client.post(path, json=payload)
            assert response.status_code == 200, (path, response.text)
            assert response.json()["id"] == str(entity_id), (path, response.text)
            return response.json()

        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                entity_id = _uuid7()
                parent_id: UUID | None = None
                payload: dict
                path: str
                table: str

                if operation == "task.create":
                    path, table = "/api/tasks", "task"
                    parent_id = entity_id
                    payload = {
                        "id": str(entity_id),
                        "title": f"response-loss task {entity_id}",
                        "items": ["one initial child"],
                    }
                elif operation == "note.create":
                    path, table = "/api/notes", "note"
                    parent_id = entity_id
                    payload = {
                        "id": str(entity_id),
                        "title": f"response-loss note {entity_id}",
                        "items": ["one initial child"],
                    }
                elif operation in ("task_item.create", "note_item.create"):
                    is_task = operation == "task_item.create"
                    parent_table = "task" if is_task else "note"
                    parent_path = "/api/tasks" if is_task else "/api/notes"
                    parent_id = _uuid7()
                    parent_payload = {
                        "id": str(parent_id),
                        "title": f"response-loss parent {parent_id}",
                    }
                    await post_new(parent_path, parent_payload, parent_table, parent_id)
                    path = f"{parent_path}/{parent_id}/items"
                    table = "task_item" if is_task else "note_item"
                    payload = {
                        "id": str(entity_id),
                        "content": "survives response loss",
                        "position": 0,
                    }
                elif operation == "calendar_source.create":
                    path, table = "/api/calendar/sources", "calendar_source"
                    payload = {
                        "id": str(entity_id),
                        "name": f"response-loss source {entity_id}",
                        "kind": "manual",
                    }
                elif operation == "calendar_event.create":
                    parent_id = _uuid7()
                    await post_new(
                        "/api/calendar/sources",
                        {
                            "id": str(parent_id),
                            "name": f"event source {parent_id}",
                            "kind": "manual",
                        },
                        "calendar_source",
                        parent_id,
                    )
                    path, table = "/api/calendar/events", "calendar_event"
                    payload = {
                        "id": str(entity_id),
                        "source_id": str(parent_id),
                        "title": "response-loss event",
                        "starts_at": "2026-10-01T09:00:00+07:00",
                        "ends_at": "2026-10-01T10:00:00+07:00",
                    }
                elif operation == "day_annotation.create":
                    path, table = "/api/calendar/annotations", "day_annotation"
                    payload = {
                        "id": str(entity_id),
                        "starts_on": "2026-10-01",
                        "label": "response-loss annotation",
                    }
                elif operation == "tracker_group.create":
                    path, table = "/api/tracker/groups", "tracker_group"
                    payload = {
                        "id": str(entity_id),
                        "name": f"response-loss group {entity_id}",
                        "kind": "health",
                    }
                elif operation == "tracker.create":
                    path, table, payload = (
                        "/api/tracker/trackers",
                        "tracker",
                        {
                            "id": str(entity_id),
                            "name": f"response-loss tracker {entity_id}",
                            "kind": "health",
                            "input_mode": "event",
                        },
                    )
                elif operation in ("entry.create", "subscription.create"):
                    tracker_id = _uuid7()
                    finance = operation in ("entry.create", "subscription.create")
                    tracker_payload = {
                        "id": str(tracker_id),
                        "name": f"response-loss tracker {tracker_id}",
                        "kind": "finance" if finance else "health",
                        "input_mode": "money" if finance else "event",
                    }
                    await post_new("/api/tracker/trackers", tracker_payload, "tracker", tracker_id)
                    parent_id = tracker_id
                    if operation == "entry.create":
                        path, table, payload = (
                            "/api/tracker/entries",
                            "entry",
                            {
                                "id": str(entity_id),
                                "tracker_id": str(tracker_id),
                                "amount": "12500",
                            },
                        )
                    else:
                        path, table = "/api/subscriptions", "subscription"
                        today = datetime.now(timezone(timedelta(hours=7))).date()
                        payload = {
                            "id": str(entity_id),
                            "name": f"response-loss subscription {entity_id}",
                            "tracker_id": str(tracker_id),
                            "amount": "12500",
                            "period_count": 1,
                            "period_unit": "month",
                            "started_on": today.isoformat(),
                            "expires_on": today.isoformat(),
                        }
                else:  # pragma: no cover - the parameter list is the registry here.
                    raise AssertionError(f"unmapped outbox create kind: {operation}")

                created.append((table, entity_id))
                created_response = await retry_after_lost_response(path, payload, entity_id)
                assert created_response["id"] == str(entity_id)
                assert await _row_count(pg_dsn, table, entity_id) == 1

                if operation in ("task.create", "note.create"):
                    child_table = "task_item" if operation == "task.create" else "note_item"
                    fk = "task_id" if operation == "task.create" else "note_id"
                    assert await _row_count(pg_dsn, child_table, parent_id, fk) == 1
                elif operation in ("task_item.create", "note_item.create"):
                    child_route = "tasks" if operation == "task_item.create" else "notes"
                    child_path = f"/api/{child_route}/{parent_id}/items"
                    items = (await client.get(child_path)).json()
                    assert len(items) == 1
                    assert items[0]["id"] == str(entity_id)
                    assert items[0]["content"] == "survives response loss"

        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                for table, entity_id in reversed(created):
                    await conn.execute(f"DELETE FROM microsched.{table} WHERE id = $1", entity_id)
            finally:
                await conn.close()
                await engine.dispose()

    asyncio.run(scenario())


async def _row_count(
    pg_dsn: str,
    table: str,
    value: UUID,
    column: str = "id",
) -> int:
    allowed_tables = {
        "task",
        "task_item",
        "note",
        "note_item",
        "calendar_source",
        "calendar_event",
        "day_annotation",
        "tracker_group",
        "tracker",
        "entry",
        "subscription",
    }
    allowed_columns = {"id", "task_id", "note_id", "source_id", "subscription_id"}
    assert table in allowed_tables and column in allowed_columns
    conn = await asyncpg.connect(pg_dsn)
    try:
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM microsched.{table} WHERE {column} = $1", value
            )
        )
    finally:
        await conn.close()


@pytest.mark.pg
def test_calendar_import_same_whole_request_is_atomic_after_response_loss(pg_dsn: str) -> None:
    """Retry the existing content-replacement operation without inventing a batch ID."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth = _auth()

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
        source_id = _uuid7()
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                source = await client.post(
                    "/api/calendar/sources",
                    json={"id": str(source_id), "name": f"ICS {source_id}", "kind": "ics"},
                )
                assert source.status_code == 201, source.text
                path = f"/api/calendar/sources/{source_id}/import"
                payload = {
                    "filename": "one-event.ics",
                    "content": (
                        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\n"
                        "UID:outbox017-response-loss\nDTSTART:20261001T090000Z\n"
                        "DTEND:20261001T100000Z\nSUMMARY:Imported once\n"
                        "END:VEVENT\nEND:VCALENDAR"
                    ),
                }
                with pytest.raises(_CommittedResponseDropped):
                    await _post_then_drop(client, path, payload)
                replay = await client.post(path, json=payload)
                assert replay.status_code == 200, replay.text
                report = replay.json()
                assert report["parsed"] == 1 and report["inserted"] == 1
                # Existing contract is atomic replacement by content. Its report
                # legitimately differs on retry (removed=1); byte-identical
                # historical responses are not promised for this endpoint.
                assert report["removed"] == 1
                count = await _row_count(pg_dsn, "calendar_event", source_id, "source_id")
                assert count == 1
                conn = await asyncpg.connect(pg_dsn)
                try:
                    titles = await conn.fetch(
                        "SELECT title FROM microsched.calendar_event WHERE source_id = $1",
                        source_id,
                    )
                    assert [row["title"] for row in titles] == ["Imported once"]
                finally:
                    await conn.close()
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "DELETE FROM microsched.calendar_source WHERE id = $1", source_id
                )
            finally:
                await conn.close()
                await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_subscription_renew_same_entry_id_replays_after_response_loss(pg_dsn: str) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth = _auth()

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
        tracker_id, subscription_id, entry_id = _uuid7(), _uuid7(), _uuid7()
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                tracker = await client.post(
                    "/api/tracker/trackers",
                    json={
                        "id": str(tracker_id),
                        "name": f"renew tracker {tracker_id}",
                        "kind": "finance",
                        "input_mode": "money",
                    },
                )
                assert tracker.status_code == 201, tracker.text
                today = datetime.now(timezone(timedelta(hours=7))).date()
                month_end = today.replace(day=28) + timedelta(days=4)
                month_end = month_end - timedelta(days=month_end.day)
                subscription = await client.post(
                    "/api/subscriptions",
                    json={
                        "id": str(subscription_id),
                        "name": f"renew subscription {subscription_id}",
                        "tracker_id": str(tracker_id),
                        "amount": "12500",
                        "period_count": 1,
                        "period_unit": "month",
                        "started_on": month_end.isoformat(),
                        "expires_on": month_end.isoformat(),
                        "auto_renew": True,
                    },
                )
                assert subscription.status_code == 201, subscription.text
                path = f"/api/subscriptions/{subscription_id}/renew"
                payload = {"entry_id": str(entry_id), "amount": "12500"}
                with pytest.raises(_CommittedResponseDropped):
                    await _post_then_drop(client, path, payload)
                replay = await client.post(path, json=payload)
                assert replay.status_code == 200, replay.text
                assert replay.json()["created"] is False
                assert replay.json()["entry_id"] == str(entry_id)
                assert await _row_count(pg_dsn, "entry", entry_id) == 1
                assert await _row_count(pg_dsn, "entry", subscription_id, "subscription_id") == 1
                assert await _row_count(pg_dsn, "subscription", subscription_id) == 1
                stored_expiry = await _stored_expiry(pg_dsn, subscription_id)
                assert stored_expiry == replay.json()["subscription"]["expires_on"]
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute("DELETE FROM microsched.entry WHERE id = $1", entry_id)
                await conn.execute(
                    "DELETE FROM microsched.subscription WHERE id = $1", subscription_id
                )
                await conn.execute("DELETE FROM microsched.tracker WHERE id = $1", tracker_id)
            finally:
                await conn.close()
                await engine.dispose()

    asyncio.run(scenario())


async def _stored_expiry(pg_dsn: str, subscription_id: UUID) -> str:
    conn = await asyncpg.connect(pg_dsn)
    try:
        return await conn.fetchval(
            "SELECT expires_on::text FROM microsched.subscription WHERE id = $1",
            subscription_id,
        )
    finally:
        await conn.close()
