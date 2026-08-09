"""Tests for Web Push subscription endpoints and endpoint validation."""

import asyncio
import base64
import os
import time
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.domain.push import PushResult, validate_push_endpoint
from app.domain.reminder import dispatcher
from app.main import create_app
from app.web.deps import get_session, require_session

VN_TZ = timezone(timedelta(hours=7))


def test_validate_push_endpoint_ssrf_guard():
    """Verify validate_push_endpoint rejects non-HTTPS and SSRF target URLs."""
    # Valid HTTPS push service endpoints
    assert validate_push_endpoint("https://fcm.googleapis.com/fcm/send/foo") is True
    assert validate_push_endpoint("https://updates.push.services.mozilla.com/wpush/v2/bar") is True

    # Invalid schemes
    assert validate_push_endpoint("http://fcm.googleapis.com/fcm/send/foo") is False
    assert validate_push_endpoint("ftp://example.com/push") is False
    assert validate_push_endpoint("javascript:alert(1)") is False

    # Loopback / internal IPs
    assert validate_push_endpoint("https://localhost/push") is False
    assert validate_push_endpoint("https://localhost.localdomain/push") is False
    assert validate_push_endpoint("https://127.0.0.1/push") is False
    assert validate_push_endpoint("https://10.0.0.1/push") is False
    assert validate_push_endpoint("https://192.168.1.1/push") is False
    assert validate_push_endpoint("https://169.254.169.254/latest/meta-data") is False
    assert validate_push_endpoint("https://::1/push") is False


@pytest.mark.anyio
async def test_vapid_public_key_unauthenticated():
    """Verify unauthenticated calls to GET /api/push/vapid-public-key return 401."""
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/push/vapid-public-key")
        assert res.status_code == 401


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
        token_hash=f"push-api-test-{_uuid7()}",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "push-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _make_client(pg_dsn: str, auth_state: dict):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

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
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), engine


def _today_vn() -> str:
    return datetime.now(VN_TZ).date().isoformat()


async def _create_tracker(client, *, kind="finance", input_mode="money", **overrides):
    payload = {"name": f"Tracker {_uuid7()}", "kind": kind, "input_mode": input_mode, **overrides}
    resp = await client.post("/api/tracker/trackers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _cleanup(dsn: str, *, tracker_ids=None, subscription_ids=None, dispatch_ids=None):
    conn = await asyncpg.connect(dsn)
    try:
        if dispatch_ids:
            await conn.execute(
                "DELETE FROM microsched.reminder_dispatch WHERE id = ANY($1::uuid[])",
                dispatch_ids,
            )
        if tracker_ids:
            await conn.execute(
                "DELETE FROM microsched.reminder_dispatch WHERE subject_id = ANY($1::uuid[])",
                tracker_ids,
            )
            await conn.execute(
                "DELETE FROM microsched.entry WHERE tracker_id = ANY($1::uuid[])", tracker_ids
            )
            await conn.execute(
                "DELETE FROM microsched.subscription WHERE tracker_id = ANY($1::uuid[])",
                tracker_ids,
            )
            await conn.execute(
                "DELETE FROM microsched.tracker WHERE id = ANY($1::uuid[])", tracker_ids
            )
        if subscription_ids:
            await conn.execute(
                "DELETE FROM microsched.push_subscription WHERE id = ANY($1::uuid[])",
                subscription_ids,
            )
    finally:
        await conn.close()


@pytest.mark.pg
def test_push_subscription_create_update_and_unsubscribe(pg_dsn: str):
    """POST is endpoint-idempotent and DELETE removes the persisted device subscription."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        endpoint = f"https://fcm.googleapis.com/fcm/send/push-api-{_uuid7()}"
        try:
            created = await client.post(
                "/api/push/subscribe",
                json={
                    "endpoint": endpoint,
                    "p256dh": "p256dh-created",
                    "auth": "auth-created",
                    "user_agent": "microSched-test-device-created",
                },
            )
            assert created.status_code == 201, created.text
            created_body = created.json()
            assert created_body["status"] == "created"

            updated = await client.post(
                "/api/push/subscribe",
                json={
                    "endpoint": endpoint,
                    "p256dh": "p256dh-updated",
                    "auth": "auth-updated",
                    "user_agent": "microSched-test-device-updated",
                },
            )
            assert updated.status_code == 201, updated.text
            updated_body = updated.json()
            assert updated_body == {"id": created_body["id"], "status": "updated"}

            conn = await asyncpg.connect(pg_dsn)
            try:
                rows = await conn.fetch(
                    "SELECT id, p256dh, auth, user_agent "
                    "FROM microsched.push_subscription WHERE endpoint = $1",
                    endpoint,
                )
                assert len(rows) == 1
                assert str(rows[0]["id"]) == created_body["id"]
                assert dict(rows[0]) == {
                    "id": rows[0]["id"],
                    "p256dh": "p256dh-updated",
                    "auth": "auth-updated",
                    "user_agent": "microSched-test-device-updated",
                }
            finally:
                await conn.close()

            deleted = await client.request(
                "DELETE", "/api/push/subscribe", json={"endpoint": endpoint}
            )
            assert deleted.status_code == 200, deleted.text
            assert deleted.json() == {"status": "deleted"}

            conn = await asyncpg.connect(pg_dsn)
            try:
                count = await conn.fetchval(
                    "SELECT count(*) FROM microsched.push_subscription WHERE endpoint = $1",
                    endpoint,
                )
                assert count == 0
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "DELETE FROM microsched.push_subscription WHERE endpoint = $1", endpoint
                )
            finally:
                await conn.close()

    asyncio.run(scenario())


@pytest.mark.pg
def test_two_devices_confirm_same_dispatch_create_one_entry(pg_dsn: str):
    """F1: two concurrent confirms (different entry ids) ⇒ exactly ONE Entry."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        dispatch_ids = []
        try:
            tracker = await _create_tracker(client, kind="health", input_mode="event")
            tracker_ids.append(UUID(tracker["id"]))
            dispatch_id = _uuid7()
            dispatch_ids.append(dispatch_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.reminder_dispatch "
                    "(id, subject_type, subject_id, dispatched_on, status, "
                    "attempt_count, created_at) "
                    "VALUES ($1, 'tracker', $2, $3::date, 'pending', 0, NOW())",
                    dispatch_id,
                    UUID(tracker["id"]),
                    datetime.now(VN_TZ).date(),
                )
            finally:
                await conn.close()

            entry_id_a = _uuid7()
            entry_id_b = _uuid7()
            occurred = datetime.now(UTC).isoformat()
            r1, r2 = await asyncio.gather(
                client.post(
                    f"/api/reminder-dispatch/{dispatch_id}/confirm",
                    json={"entry_id": str(entry_id_a), "occurred_at": occurred},
                ),
                client.post(
                    f"/api/reminder-dispatch/{dispatch_id}/confirm",
                    json={"entry_id": str(entry_id_b), "occurred_at": occurred},
                ),
            )
            assert r1.status_code == 200, r1.text
            assert r2.status_code == 200, r2.text
            flags = sorted(item.json()["created"] for item in (r1, r2))
            assert flags == [False, True]
            confirmed = {item.json()["confirmed_entry_id"] for item in (r1, r2)}
            assert len(confirmed) == 1
            conn = await asyncpg.connect(pg_dsn)
            try:
                count = await conn.fetchval(
                    "SELECT count(*) FROM microsched.entry WHERE tracker_id = $1",
                    UUID(tracker["id"]),
                )
                assert count == 1
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids, dispatch_ids=dispatch_ids)

    asyncio.run(scenario())


@pytest.mark.pg
def test_confirmed_private_dispatch_still_requires_unlock(pg_dsn: str):
    """The idempotent fast path must not disclose a private confirmed entry while locked."""

    async def scenario():
        auth_state = {"value": _auth(unlocked=True)}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        dispatch_ids = []
        try:
            tracker = await _create_tracker(
                client, kind="health", input_mode="event", is_private=True
            )
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            entry_id = _uuid7()
            entry = await client.post(
                "/api/tracker/entries",
                json={"id": str(entry_id), "tracker_id": str(tracker_id)},
            )
            assert entry.status_code == 201, entry.text

            dispatch_id = _uuid7()
            dispatch_ids.append(dispatch_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.reminder_dispatch "
                    "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                    "confirmed_entry_id, confirmed_at, created_at) "
                    "VALUES ($1, 'tracker', $2, $3::date, 'sent', 1, $4, NOW(), NOW())",
                    dispatch_id,
                    tracker_id,
                    datetime.now(VN_TZ).date(),
                    entry_id,
                )
            finally:
                await conn.close()

            auth_state["value"] = _auth(unlocked=False)
            response = await client.post(
                f"/api/reminder-dispatch/{dispatch_id}/confirm",
                json={"entry_id": str(_uuid7()), "occurred_at": datetime.now(UTC).isoformat()},
            )
            assert response.status_code == 403, response.text
            assert response.json()["detail"]["code"] == "PRIVATE_UNLOCK_REQUIRED"
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids, dispatch_ids=dispatch_ids)

    asyncio.run(scenario())


@pytest.mark.pg
def test_dispatch_item_never_sends_concurrently(pg_dsn: str, monkeypatch):
    """F12: two workers on the same occurrence ⇒ one send, one attempt claimed."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub_id = _uuid7()
            subscription_ids.append(sub_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.push_subscription "
                    "(id, endpoint, p256dh, auth, last_seen_at) "
                    "VALUES ($1, $2, $3, $4, NOW())",
                    sub_id,
                    f"https://fcm.googleapis.com/fcm/send/test-{sub_id}",
                    "dGVzdA",
                    "dGVzdA",
                )
            finally:
                await conn.close()

            calls = {"n": 0}

            async def slow_send(db, subscription, payload, timeout_seconds=20.0):
                calls["n"] += 1
                await asyncio.sleep(0.4)
                return PushResult.SENT

            import app.domain.reminder as reminder_module

            monkeypatch.setattr(reminder_module, "send_push", slow_send)

            maker = async_sessionmaker(engine, expire_on_commit=False)

            async def worker() -> str:
                async with maker() as db:
                    outcome = await dispatcher.dispatch_item(
                        db,
                        "tracker",
                        UUID(tracker["id"]),
                        date.today(),
                        lambda d_id: {"title": "t", "body": "b", "url": "/"},
                    )
                    return outcome.value

            outcomes = await asyncio.gather(worker(), worker())
            assert sorted(outcomes) == ["sent", "sent"]
            assert calls["n"] == 1, "two workers sent the same occurrence in parallel"
            conn = await asyncpg.connect(pg_dsn)
            try:
                attempt_count = await conn.fetchval(
                    "SELECT attempt_count FROM microsched.reminder_dispatch "
                    "WHERE subject_type = 'tracker' AND subject_id = $1",
                    UUID(tracker["id"]),
                )
                assert attempt_count == 1
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids)

    asyncio.run(scenario())
