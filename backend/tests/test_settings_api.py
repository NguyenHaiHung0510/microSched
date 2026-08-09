"""Allowlist tests for the public settings API (011c §2.1 — the most important test)."""

import asyncio
import base64
import json
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

PRIVATE_KEYS = (
    "private_pin",
    "private_unlock_throttle",
    "private_unlock_ttl_minutes",
)


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
        token_hash=f"settings-api-test-{_uuid7()}",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "settings-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _make_client(pg_dsn: str):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

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
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), engine


async def _seed_private_rows(pg_dsn: str) -> dict[str, str | None]:
    """Insert realistic secret rows; return the raw ``value::text`` before/after."""
    conn = await asyncpg.connect(pg_dsn)
    try:
        await conn.execute(
            "INSERT INTO microsched.app_setting (key, value) VALUES "
            "('private_pin', $1::jsonb), "
            "('private_unlock_throttle', $2::jsonb), "
            "('private_unlock_ttl_minutes', $3::jsonb) "
            "ON CONFLICT (key) DO NOTHING",
            json.dumps({"hash": "argon2id$dummy$hash", "bootstrap": False}),
            json.dumps({"fail_count": 3, "locked_until": None}),
            json.dumps({"value": 36}),
        )
        rows = await conn.fetch(
            "SELECT key, value::text FROM microsched.app_setting WHERE key = ANY($1::text[])",
            list(PRIVATE_KEYS),
        )
        return {row["key"]: row["value"] for row in rows}
    finally:
        await conn.close()


async def _value_text(pg_dsn: str, key: str) -> str | None:
    conn = await asyncpg.connect(pg_dsn)
    try:
        return await conn.fetchval(
            "SELECT value::text FROM microsched.app_setting WHERE key = $1", key
        )
    finally:
        await conn.close()


def test_settings_allowlist_never_leaks_or_touches_secret_keys(pg_dsn: str):
    async def scenario():
        client, engine = _make_client(pg_dsn)
        try:
            before = await _seed_private_rows(pg_dsn)

            listed = await client.get("/api/settings")
            assert listed.status_code == 200, listed.text
            keys = [item["key"] for item in listed.json()["items"]]
            assert keys == ["subscription_expiry_lead_days", "show_list_price"]
            assert not set(keys) & set(PRIVATE_KEYS)
            by_key = {item["key"]: item["value"] for item in listed.json()["items"]}
            assert by_key["subscription_expiry_lead_days"] == 3  # default, row absent
            assert by_key["show_list_price"] is True

            # GET AND PATCH on every secret key ⇒ 404 (one code, no oracle).
            for key in PRIVATE_KEYS:
                resp = await client.get(f"/api/settings/{key}")
                assert resp.status_code == 404, (key, resp.text)
                resp = await client.patch(f"/api/settings/{key}", json={"value": 1})
                assert resp.status_code == 404, (key, resp.text)

            # A made-up key is byte-identical in response to the real secrets.
            resp = await client.get("/api/settings/key_bia")
            assert resp.status_code == 404
            resp = await client.patch("/api/settings/key_bia", json={"value": True})
            assert resp.status_code == 404

            # The secret rows did not change by a single byte.
            for key, original in before.items():
                assert await _value_text(pg_dsn, key) == original
        finally:
            await client.aclose()
            await engine.dispose()

    asyncio.run(scenario())


def test_settings_valid_keys_validate_values(pg_dsn: str):
    async def scenario():
        client, engine = _make_client(pg_dsn)
        try:
            # Valid key + wrong type ⇒ 422 (only this case is 422).
            resp = await client.patch(
                "/api/settings/subscription_expiry_lead_days", json={"value": True}
            )
            assert resp.status_code == 422, resp.text
            resp = await client.patch("/api/settings/show_list_price", json={"value": "yes"})
            assert resp.status_code == 422, resp.text
            # Out of bounds ⇒ 422.
            resp = await client.patch(
                "/api/settings/subscription_expiry_lead_days", json={"value": 31}
            )
            assert resp.status_code == 422, resp.text
            resp = await client.patch(
                "/api/settings/subscription_expiry_lead_days", json={"value": -1}
            )
            assert resp.status_code == 422, resp.text

            # Valid write persists and reads back.
            resp = await client.patch(
                "/api/settings/subscription_expiry_lead_days", json={"value": 7}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json() == {"key": "subscription_expiry_lead_days", "value": 7}
            resp = await client.patch("/api/settings/show_list_price", json={"value": False})
            assert resp.status_code == 200, resp.text
            resp = await client.get("/api/settings")
            assert resp.status_code == 200
            by_key = {item["key"]: item["value"] for item in resp.json()["items"]}
            assert by_key["subscription_expiry_lead_days"] == 7
            assert by_key["show_list_price"] is False
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "DELETE FROM microsched.app_setting WHERE key IN "
                    "('subscription_expiry_lead_days', 'show_list_price', "
                    "'private_pin', 'private_unlock_throttle', "
                    "'private_unlock_ttl_minutes')"
                )
            finally:
                await conn.close()
            await client.aclose()
            await engine.dispose()

    asyncio.run(scenario())


def test_settings_corrupt_stored_value_is_loud_on_read_path(pg_dsn: str):
    """A corrupt allowlisted row 422s the settings API (loud), not a silent guess."""

    async def scenario():
        client, engine = _make_client(pg_dsn)
        try:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "INSERT INTO microsched.app_setting (key, value) VALUES "
                    "('subscription_expiry_lead_days', $1::jsonb) ON CONFLICT (key) DO NOTHING",
                    json.dumps({"value": "không phải số"}),
                )
            finally:
                await conn.close()
            resp = await client.get("/api/settings/subscription_expiry_lead_days")
            assert resp.status_code == 422, resp.text
            resp = await client.get("/api/settings")
            assert resp.status_code == 422, resp.text
        finally:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "DELETE FROM microsched.app_setting WHERE key = 'subscription_expiry_lead_days'"
                )
            finally:
                await conn.close()
            await client.aclose()
            await engine.dispose()

    asyncio.run(scenario())
