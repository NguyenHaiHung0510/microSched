"""Tests for Web Push subscription endpoints and endpoint validation."""

import asyncio
import base64
import ipaddress
import os
import time
from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.domain.push as push_module
import app.domain.reminder as reminder_module
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession, PushSubscription
from app.domain.push import PushResult, validate_push_endpoint
from app.domain.reminder import DispatchOutcome, ReminderDispatcher
from app.main import create_app
from app.web.deps import get_session, require_session

VN_TZ = timezone(timedelta(hours=7))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("resolved", "expected"),
    [
        (("8.8.8.8",), True),
        (("10.0.0.1",), False),
        (("8.8.8.8", "10.0.0.1"), False),
    ],
)
async def test_validate_push_endpoint_resolves_every_answer(monkeypatch, resolved, expected):
    """A hostname is valid only when every DNS answer is globally routable."""

    def fake_getaddrinfo(host, port, *, type):
        assert host == "push.example"
        assert port == 443
        assert type == push_module.socket.SOCK_STREAM
        return [(0, 0, 0, "", (ip, 443)) for ip in resolved]

    monkeypatch.setattr(push_module.socket, "getaddrinfo", fake_getaddrinfo)

    assert await validate_push_endpoint("https://push.example/send") is expected


@pytest.mark.anyio
async def test_validate_push_endpoint_rejects_internal_and_literal_private_targets(monkeypatch):
    """Internal DNS names and literal private addresses never reach DNS/send."""

    def unexpected_dns(*_args, **_kwargs):
        raise AssertionError("pre-DNS SSRF guard should have rejected this host")

    monkeypatch.setattr(push_module.socket, "getaddrinfo", unexpected_dns)

    assert await validate_push_endpoint("https://api.internal/push") is False
    assert await validate_push_endpoint("https://127.0.0.1/push") is False
    assert await validate_push_endpoint("https://169.254.169.254/latest/meta-data") is False
    assert await validate_push_endpoint("https://[::1]/push") is False
    assert await validate_push_endpoint("http://push.example/send") is False


def test_webpush_passes_the_delivery_timeout(monkeypatch):
    """The socket-level timeout must match the timer's outer deadline."""
    captured: dict[str, object] = {}

    def fake_webpush(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(push_module, "webpush", fake_webpush)

    status_code = push_module._do_webpush_sync(
        "https://push.example/send",
        "p256dh",
        "auth",
        "{}",
        "vapid-private-key",
        "mailto:owner@example.com",
        17.5,
    )

    assert status_code == 201
    assert captured["timeout"] == 17.5


@pytest.mark.anyio
async def test_send_push_revalidates_dns_before_webpush(monkeypatch, caplog):
    """A DNS answer that turns private after save blocks delivery without leaking the URL."""
    webpush_calls: list[dict[str, object]] = []

    class NoCommitDB:
        async def commit(self):
            raise AssertionError("a rejected send must not write state")

    monkeypatch.setattr(
        push_module,
        "get_settings",
        lambda: SimpleNamespace(
            vapid_private_key="test-vapid-private-key",
            vapid_claims_sub="mailto:owner@example.com",
        ),
    )
    monkeypatch.setattr(
        push_module,
        "_resolve_endpoint_ips",
        lambda _hostname: {ipaddress.ip_address("10.0.0.1")},
    )
    monkeypatch.setattr(push_module, "webpush", lambda **kwargs: webpush_calls.append(kwargs))
    subscription = PushSubscription(
        id=_uuid7(),
        endpoint="https://rebound.example/send",
        p256dh="p256dh",
        auth="auth",
    )

    result = await push_module.send_push(NoCommitDB(), subscription, {"title": "test"})

    assert result == PushResult.TEMPORARY_FAILURE
    assert webpush_calls == []
    assert subscription.endpoint not in caplog.text


@pytest.mark.anyio
async def test_vapid_public_key_unauthenticated():
    """Verify unauthenticated calls to GET /api/push/vapid-public-key return 401."""
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/push/vapid-public-key")
        assert res.status_code == 401


@pytest.mark.anyio
async def test_confirm_router_passes_the_verified_auth_session(monkeypatch):
    """The confirmation service must receive the real session, never a fabricated gate."""
    auth = _auth(unlocked=True)
    captured: dict[str, object] = {}
    entry_id = _uuid7()

    async def fake_confirm(*args, **kwargs):
        captured["auth"] = kwargs["auth"]
        return SimpleNamespace(id=entry_id), False

    app = create_app()

    async def request_session():
        yield object()

    async def current_session():
        return auth

    app.dependency_overrides[get_session] = request_session
    app.dependency_overrides[require_session] = current_session
    monkeypatch.setattr("app.web.routers.push.confirm_reminder_dispatch", fake_confirm)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/reminder-dispatch/{_uuid7()}/confirm",
            json={"entry_id": str(entry_id), "occurred_at": datetime.now(UTC).isoformat()},
        )

    assert response.status_code == 200, response.text
    assert captured["auth"] is auth


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
def test_push_subscription_create_update_and_unsubscribe(pg_dsn: str, monkeypatch):
    """POST is endpoint-idempotent and DELETE removes the persisted device subscription."""

    monkeypatch.setattr(
        push_module,
        "_resolve_endpoint_ips",
        lambda _hostname: {ipaddress.ip_address("8.8.8.8")},
    )

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
def test_private_dispatch_requires_unlock_then_accepts_same_body(pg_dsn: str):
    """011b §6: locked private confirm writes nothing; same unlocked retry confirms once."""

    async def scenario():
        auth = _auth(unlocked=True)
        auth_state = {"value": auth}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        dispatch_ids = []
        try:
            tracker = await _create_tracker(
                client, kind="health", input_mode="event", is_private=True
            )
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            dispatch_id = _uuid7()
            dispatch_ids.append(dispatch_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.reminder_dispatch "
                    "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                    "created_at) "
                    "VALUES ($1, 'tracker', $2, $3::date, 'pending', 0, NOW())",
                    dispatch_id,
                    tracker_id,
                    datetime.now(VN_TZ).date(),
                )
            finally:
                await conn.close()

            body = {"entry_id": str(_uuid7()), "occurred_at": datetime.now(UTC).isoformat()}
            auth.private_until = None
            locked = await client.post(f"/api/reminder-dispatch/{dispatch_id}/confirm", json=body)
            assert locked.status_code == 403, locked.text
            assert locked.json()["detail"]["code"] == "PRIVATE_UNLOCK_REQUIRED"

            conn = await asyncpg.connect(pg_dsn)
            try:
                locked_state = await conn.fetchrow(
                    "SELECT confirmed_entry_id IS NULL AS unconfirmed, "
                    "(SELECT count(*) FROM microsched.entry WHERE tracker_id = $1) AS entry_count "
                    "FROM microsched.reminder_dispatch WHERE id = $2",
                    tracker_id,
                    dispatch_id,
                )
                assert dict(locked_state) == {"unconfirmed": True, "entry_count": 0}
            finally:
                await conn.close()

            auth.private_until = datetime.now(UTC) + timedelta(minutes=15)
            unlocked = await client.post(f"/api/reminder-dispatch/{dispatch_id}/confirm", json=body)
            assert unlocked.status_code == 200, unlocked.text
            assert unlocked.json() == {
                "confirmed_entry_id": body["entry_id"],
                "created": True,
            }

            conn = await asyncpg.connect(pg_dsn)
            try:
                unlocked_state = await conn.fetchrow(
                    "SELECT confirmed_entry_id, "
                    "(SELECT count(*) FROM microsched.entry WHERE tracker_id = $1) AS entry_count "
                    "FROM microsched.reminder_dispatch WHERE id = $2",
                    tracker_id,
                    dispatch_id,
                )
                assert str(unlocked_state["confirmed_entry_id"]) == body["entry_id"]
                assert unlocked_state["entry_count"] == 1
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids, dispatch_ids=dispatch_ids)

    asyncio.run(scenario())


@pytest.mark.pg
def test_confirmed_dispatch_returns_its_soft_deleted_entry_before_tracker_lookup(pg_dsn: str):
    """§3.6 fast path returns the original Entry after Entry and Tracker soft-delete."""

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

            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "UPDATE microsched.entry SET deleted_at = NOW() WHERE id = $1", entry_id
                )
                await conn.execute(
                    "UPDATE microsched.tracker SET deleted_at = NOW() WHERE id = $1", tracker_id
                )
            finally:
                await conn.close()

            auth_state["value"] = _auth(unlocked=False)
            response = await client.post(
                f"/api/reminder-dispatch/{dispatch_id}/confirm",
                json={"entry_id": str(_uuid7()), "occurred_at": datetime.now(UTC).isoformat()},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"confirmed_entry_id": str(entry_id), "created": False}

            conn = await asyncpg.connect(pg_dsn)
            try:
                deleted = await conn.fetchrow(
                    "SELECT "
                    "(SELECT deleted_at IS NOT NULL FROM microsched.entry WHERE id = $1) "
                    "AS entry_deleted, "
                    "(SELECT deleted_at IS NOT NULL FROM microsched.tracker WHERE id = $2) "
                    "AS tracker_deleted",
                    entry_id,
                    tracker_id,
                )
                assert dict(deleted) == {"entry_deleted": True, "tracker_deleted": True}
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids, dispatch_ids=dispatch_ids)

    asyncio.run(scenario())


@pytest.mark.pg
def test_unconfirmed_dispatch_with_soft_deleted_tracker_is_generic_conflict(pg_dsn: str):
    """An unconfirmed occurrence must not create an Entry after its subject is deleted."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        dispatch_ids = []
        try:
            tracker = await _create_tracker(client, kind="health", input_mode="event")
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            dispatch_id = _uuid7()
            dispatch_ids.append(dispatch_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.reminder_dispatch "
                    "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                    "created_at) "
                    "VALUES ($1, 'tracker', $2, $3::date, 'pending', 0, NOW())",
                    dispatch_id,
                    tracker_id,
                    datetime.now(VN_TZ).date(),
                )
                await conn.execute(
                    "UPDATE microsched.tracker SET deleted_at = NOW() WHERE id = $1", tracker_id
                )
            finally:
                await conn.close()

            response = await client.post(
                f"/api/reminder-dispatch/{dispatch_id}/confirm",
                json={"entry_id": str(_uuid7()), "occurred_at": datetime.now(UTC).isoformat()},
            )
            assert response.status_code == 409, response.text

            conn = await asyncpg.connect(pg_dsn)
            try:
                state = await conn.fetchrow(
                    "SELECT confirmed_entry_id IS NULL AS unconfirmed, "
                    "(SELECT count(*) FROM microsched.entry WHERE tracker_id = $1) AS entry_count "
                    "FROM microsched.reminder_dispatch WHERE id = $2",
                    tracker_id,
                    dispatch_id,
                )
                assert dict(state) == {"unconfirmed": True, "entry_count": 0}
            finally:
                await conn.close()
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

            dispatcher = ReminderDispatcher()

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


@pytest.mark.pg
@pytest.mark.parametrize(
    ("expected_outcome", "seed_attempts", "push_result", "expected_status"),
    [
        (DispatchOutcome.SENT, 0, PushResult.SENT, "sent"),
        (DispatchOutcome.NO_DEVICE, 0, None, "no_device"),
        (DispatchOutcome.TEMPORARY_FAILURE, 0, PushResult.TEMPORARY_FAILURE, "pending"),
        (DispatchOutcome.EXHAUSTED, 4, None, "pending"),
    ],
)
def test_dispatch_receipts_cover_durable_outcomes(
    pg_dsn: str,
    monkeypatch,
    expected_outcome: DispatchOutcome,
    seed_attempts: int,
    push_result: PushResult | None,
    expected_status: str,
):
    """O-02: telemetry carries the committed attempt count for every outcome."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids: list[UUID] = []
        subscription_ids: list[UUID] = []
        occurrence_on = date(2026, 8, 16)
        try:
            tracker = await _create_tracker(client)
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            if seed_attempts:
                conn = await asyncpg.connect(pg_dsn)
                try:
                    await conn.execute(
                        "INSERT INTO microsched.reminder_dispatch "
                        "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                        "last_attempt_at, created_at) "
                        "VALUES ($1, 'tracker', $2, $3, 'pending', $4, NOW(), NOW())",
                        _uuid7(),
                        tracker_id,
                        occurrence_on,
                        seed_attempts,
                    )
                finally:
                    await conn.close()

            if push_result is not None:
                subscription_id = _uuid7()
                subscription_ids.append(subscription_id)
                conn = await asyncpg.connect(pg_dsn)
                try:
                    await conn.execute(
                        "INSERT INTO microsched.push_subscription "
                        "(id, endpoint, p256dh, auth, last_seen_at) "
                        "VALUES ($1, $2, 'dGVzdA', 'dGVzdA', NOW())",
                        subscription_id,
                        f"https://push.example.test/send/{subscription_id}",
                    )
                finally:
                    await conn.close()

                async def fake_send(db, subscription, payload, timeout_seconds=20.0):
                    return push_result

                monkeypatch.setattr(reminder_module, "send_push", fake_send)

            telemetry = []
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                outcome = await ReminderDispatcher().dispatch_item(
                    db,
                    "tracker",
                    tracker_id,
                    occurrence_on,
                    lambda dispatch_id: {"title": "test"},
                    telemetry=telemetry.append,
                )

            conn = await asyncpg.connect(pg_dsn)
            try:
                row = await conn.fetchrow(
                    "SELECT status, attempt_count FROM microsched.reminder_dispatch "
                    "WHERE subject_type = 'tracker' AND subject_id = $1 AND dispatched_on = $2",
                    tracker_id,
                    occurrence_on,
                )
            finally:
                await conn.close()

            expected_attempts = 4 if expected_outcome == DispatchOutcome.EXHAUSTED else 1
            assert outcome is expected_outcome
            assert dict(row) == {
                "status": expected_status,
                "attempt_count": expected_attempts,
            }
            assert len(telemetry) == 2
            assert telemetry[0].attempt_count == expected_attempts
            assert telemetry[0].outcome is None
            assert telemetry[1].attempt_count == expected_attempts
            assert telemetry[1].outcome is expected_outcome
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn,
                tracker_ids=tracker_ids,
                subscription_ids=subscription_ids,
            )

    asyncio.run(scenario())


@pytest.mark.pg
def test_dispatch_item_without_telemetry_keeps_dispatch_outcome_return(pg_dsn: str):
    """The optional observer does not change existing direct callers."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids: list[UUID] = []
        try:
            tracker = await _create_tracker(client)
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                outcome = await ReminderDispatcher().dispatch_item(
                    db,
                    "tracker",
                    tracker_id,
                    date(2026, 8, 16),
                    lambda dispatch_id: {"title": "test"},
                )
            assert outcome is DispatchOutcome.NO_DEVICE
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids)

    asyncio.run(scenario())


@pytest.mark.pg
def test_terminal_dispatch_reentry_receipts_without_attempt_or_network(pg_dsn: str, monkeypatch):
    """Terminal re-entry emits no-op receipts without another attempt or send."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids: list[UUID] = []
        occurrence_on = date(2026, 8, 16)
        try:
            tracker = await _create_tracker(client)
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.reminder_dispatch "
                    "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                    "last_attempt_at, created_at) "
                    "VALUES ($1, 'tracker', $2, $3, 'sent', 2, NOW(), NOW())",
                    _uuid7(),
                    tracker_id,
                    occurrence_on,
                )
            finally:
                await conn.close()

            network_calls = 0

            async def unexpected_send(db, subscription, payload, timeout_seconds=20.0):
                nonlocal network_calls
                network_calls += 1
                return PushResult.SENT

            monkeypatch.setattr(reminder_module, "send_push", unexpected_send)
            telemetry = []
            dispatcher = ReminderDispatcher()
            maker = async_sessionmaker(engine, expire_on_commit=False)
            for _ in range(2):
                async with maker() as db:
                    outcome = await dispatcher.dispatch_item(
                        db,
                        "tracker",
                        tracker_id,
                        occurrence_on,
                        lambda dispatch_id: {"title": "test"},
                        telemetry=telemetry.append,
                    )
                    assert outcome is DispatchOutcome.SENT

            conn = await asyncpg.connect(pg_dsn)
            try:
                attempt_count = await conn.fetchval(
                    "SELECT attempt_count FROM microsched.reminder_dispatch "
                    "WHERE subject_type = 'tracker' AND subject_id = $1 AND dispatched_on = $2",
                    tracker_id,
                    occurrence_on,
                )
            finally:
                await conn.close()

            assert attempt_count == 2
            assert network_calls == 0
            assert [(event.attempt_count, event.outcome) for event in telemetry] == [
                (2, None),
                (2, DispatchOutcome.SENT),
                (2, None),
                (2, DispatchOutcome.SENT),
            ]
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(pg_dsn, tracker_ids=tracker_ids)

    asyncio.run(scenario())


@pytest.mark.pg
def test_dispatch_exception_keeps_started_without_fake_finished(pg_dsn: str, monkeypatch):
    """A network exception leaves the truthful started-only investigation receipt."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids: list[UUID] = []
        subscription_ids: list[UUID] = []
        occurrence_on = date(2026, 8, 16)
        try:
            tracker = await _create_tracker(client)
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            subscription_id = _uuid7()
            subscription_ids.append(subscription_id)
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.push_subscription "
                    "(id, endpoint, p256dh, auth, last_seen_at) "
                    "VALUES ($1, $2, 'dGVzdA', 'dGVzdA', NOW())",
                    subscription_id,
                    f"https://push.example.test/error/{subscription_id}",
                )
            finally:
                await conn.close()

            async def failing_send(db, subscription, payload, timeout_seconds=20.0):
                raise RuntimeError("provider-response-private-sentinel")

            monkeypatch.setattr(reminder_module, "send_push", failing_send)
            telemetry = []
            maker = async_sessionmaker(engine, expire_on_commit=False)
            with pytest.raises(RuntimeError, match="provider-response-private-sentinel"):
                async with maker() as db:
                    await ReminderDispatcher().dispatch_item(
                        db,
                        "tracker",
                        tracker_id,
                        occurrence_on,
                        lambda dispatch_id: {"title": "test"},
                        telemetry=telemetry.append,
                    )

            conn = await asyncpg.connect(pg_dsn)
            try:
                row = await conn.fetchrow(
                    "SELECT status, attempt_count FROM microsched.reminder_dispatch "
                    "WHERE subject_type = 'tracker' AND subject_id = $1 AND dispatched_on = $2",
                    tracker_id,
                    occurrence_on,
                )
            finally:
                await conn.close()

            assert dict(row) == {"status": "pending", "attempt_count": 1}
            assert [(event.attempt_count, event.outcome) for event in telemetry] == [(1, None)]
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn,
                tracker_ids=tracker_ids,
                subscription_ids=subscription_ids,
            )

    asyncio.run(scenario())
