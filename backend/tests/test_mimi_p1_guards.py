"""Fast guards for Mimi P1 encryption, configuration, and CSRF."""

import asyncio
import base64
import os

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from fastapi import Depends, FastAPI

from app.agent import crypto as mimi_crypto
from app.core import crypto
from app.core.settings import Settings, get_settings
from app.web.mimi_csrf import require_mimi_csrf


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-p1-guard-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_conversation_dek_is_wrapped_and_content_is_resource_bound() -> None:
    wrapped = mimi_crypto.create_wrapped_dek()
    assert wrapped.startswith("enc:v1:")
    dek = mimi_crypto.unwrap_dek(wrapped)
    ciphertext = mimi_crypto.seal_content(dek, "nội dung", aad="message:1")
    assert ciphertext.startswith("mimi:v1:")
    assert "nội dung" not in ciphertext
    assert mimi_crypto.open_content(dek, ciphertext, aad="message:1") == "nội dung"
    with pytest.raises(InvalidTag):
        mimi_crypto.open_content(dek, ciphertext, aad="message:2")


def test_live_route_cannot_be_enabled_without_real_chat_gate() -> None:
    with pytest.raises(ValueError, match="MIMI_LIVE_PROVIDER_ENABLED"):
        Settings(
            app_env="local",
            oauth_state_secret="test",
            mimi_live_provider_enabled=True,
        )


def test_production_real_chat_requires_exact_public_origin() -> None:
    with pytest.raises(ValueError, match="MIMI_PUBLIC_ORIGIN"):
        Settings(
            app_env="production",
            oauth_state_secret="test",
            mimi_real_chat_enabled=True,
        )


def test_mimi_csrf_requires_json_header_fetch_metadata_and_exact_origin() -> None:
    app = FastAPI()

    @app.post("/write", dependencies=[Depends(require_mimi_csrf)])
    async def write() -> dict[str, bool]:
        return {"ok": True}

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            missing = await client.post("/write", json={})
            assert missing.status_code == 403
            cross_site = await client.post(
                "/write",
                json={},
                headers={
                    "Origin": "http://evil.test",
                    "Sec-Fetch-Site": "cross-site",
                    "X-Mimi-CSRF": "1",
                },
            )
            assert cross_site.status_code == 403
            allowed = await client.post(
                "/write",
                json={},
                headers={
                    "Origin": "http://test",
                    "Sec-Fetch-Site": "same-origin",
                    "X-Mimi-CSRF": "1",
                },
            )
            assert allowed.status_code == 200

    asyncio.run(scenario())
