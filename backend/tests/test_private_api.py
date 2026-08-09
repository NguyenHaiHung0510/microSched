"""Real-Postgres HTTP contract for the protected private-gate endpoints."""

import asyncio
import base64
import os
import secrets

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import get_session, get_session_store, require_session

pytestmark = pytest.mark.pg


def generated_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "private-api-test-state-secret")
    # Empty overrides the developer's real backend/.env without revealing it.
    monkeypatch.setenv("PRIVATE_PIN_BOOTSTRAP", "")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


async def api_client(pg_dsn: str, auth: AuthSession):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def current_session():
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
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    return client, engine


def test_private_api_error_envelopes_me_fields_and_retry_header(
    pg_dsn,
    seed_auth_session: AuthSession,
    monkeypatch,
):
    bootstrap = generated_pin()
    wrong = generated_pin()
    while wrong == bootstrap:
        wrong = generated_pin()

    async def scenario():
        client, engine = await api_client(pg_dsn, seed_auth_session)
        try:
            async with client:
                no_pin = await client.post("/api/private/unlock", json={"pin": wrong})
                assert no_pin.status_code == 409
                assert no_pin.json() == {"detail": "Chưa đặt PIN"}

                invalid = await client.post("/api/private/unlock", json={"pin": "12345"})
                assert invalid.status_code == 422

                monkeypatch.setenv("PRIVATE_PIN_BOOTSTRAP", bootstrap)
                get_settings.cache_clear()
                first_wrong = await client.post("/api/private/unlock", json={"pin": wrong})
                assert first_wrong.status_code == 401
                assert first_wrong.json() == {"detail": "Sai PIN", "remaining": 9}
                assert not isinstance(first_wrong.json()["detail"], dict)

                for _ in range(8):
                    response = await client.post("/api/private/unlock", json={"pin": wrong})
                    assert response.status_code == 401
                locked = await client.post("/api/private/unlock", json={"pin": wrong})
                assert locked.status_code == 429
                body = locked.json()
                assert body["detail"] == "Đang khoá tạm"
                assert isinstance(body["retry_after_seconds"], int)
                assert locked.headers["Retry-After"] == str(body["retry_after_seconds"])
                assert locked.headers["Retry-After"].isdigit()

                me = await client.get("/api/me")
                assert me.status_code == 200
                assert {
                    "private_until",
                    "private_locked_until",
                    "pin_is_set",
                    "pin_is_bootstrap",
                } <= me.json().keys()
                assert me.json()["pin_is_set"] is True
                assert me.json()["pin_is_bootstrap"] is True
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_private_endpoints_are_all_guarded_without_a_cookie(monkeypatch):
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_session_store] = lambda: None
    with TestClient(app) as client:
        for path, payload in (
            ("/api/private/unlock", {"pin": generated_pin()}),
            ("/api/private/lock", None),
            ("/api/private/pin", {"current_pin": None, "new_pin": generated_pin()}),
        ):
            response = client.post(path, json=payload)
            assert response.status_code == 401
            assert response.json() == {"detail": "Not authenticated"}


def test_first_pin_can_be_set_without_current_pin_and_then_rotated(
    pg_dsn,
    seed_auth_session: AuthSession,
):
    first_pin = generated_pin()
    changed_pin = generated_pin()
    wrong_pin = generated_pin()
    while len({first_pin, changed_pin, wrong_pin}) != 3:
        changed_pin = generated_pin()
        wrong_pin = generated_pin()

    async def scenario():
        client, engine = await api_client(pg_dsn, seed_auth_session)
        try:
            async with client:
                first = await client.post(
                    "/api/private/pin",
                    json={"current_pin": None, "new_pin": first_pin},
                )
                assert first.status_code == 204

                wrong = await client.post(
                    "/api/private/pin",
                    json={"current_pin": wrong_pin, "new_pin": changed_pin},
                )
                assert wrong.status_code == 401
                assert wrong.json() == {"detail": "Sai PIN", "remaining": 9}

                changed = await client.post(
                    "/api/private/pin",
                    json={"current_pin": first_pin, "new_pin": changed_pin},
                )
                assert changed.status_code == 204

                me = await client.get("/api/me")
                assert me.json()["pin_is_set"] is True
                assert me.json()["pin_is_bootstrap"] is False
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_locked_task_writes_return_403_without_echoing_private_content(
    pg_dsn,
    seed_auth_session: AuthSession,
):
    private_title = "private response redaction probe"
    public_id = None

    async def scenario():
        nonlocal public_id
        client, engine = await api_client(pg_dsn, seed_auth_session)
        try:
            async with client:
                create_private = await client.post(
                    "/api/tasks",
                    json={"title": private_title, "is_private": True},
                )
                assert create_private.status_code == 403
                assert private_title not in create_private.text

                created = await client.post(
                    "/api/tasks",
                    json={"title": "public task before locked toggle"},
                )
                assert created.status_code == 201
                public_id = created.json()["id"]

                toggle = await client.patch(
                    f"/api/tasks/{public_id}",
                    json={"title": private_title, "is_private": True},
                )
                assert toggle.status_code == 403
                assert private_title not in toggle.text
        finally:
            await engine.dispose()

        conn = await asyncpg.connect(pg_dsn)
        try:
            row = await conn.fetchrow(
                "SELECT title, is_private FROM microsched.task WHERE id = $1",
                public_id,
            )
            assert row["title"] == "public task before locked toggle"
            assert row["is_private"] is False
        finally:
            await conn.execute("DELETE FROM microsched.task WHERE id = $1", public_id)
            await conn.close()

    asyncio.run(scenario())
