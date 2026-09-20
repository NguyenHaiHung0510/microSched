"""Fast guards for Mimi P1 encryption, configuration, and CSRF."""

import asyncio
import base64
import os
from datetime import UTC, datetime
from uuid import uuid7

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from fastapi import Depends, FastAPI

from app.agent import crypto as mimi_crypto
from app.agent.models import MimiConversation
from app.agent.service import (
    ConversationRename,
    _decode_conversation_cursor,
    _encode_conversation_cursor,
    _open_conversation_title,
    _seal_conversation_title,
)
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


def test_stream_event_content_is_bound_to_run_sequence_and_kind() -> None:
    dek = mimi_crypto.unwrap_dek(mimi_crypto.create_wrapped_dek())
    run_id = uuid7()
    aad = mimi_crypto.event_content_aad(run_id, 3, "assistant.delta")
    ciphertext = mimi_crypto.seal_content(dek, "đang xử lý", aad=aad)
    assert "đang xử lý" not in ciphertext
    assert mimi_crypto.open_content(dek, ciphertext, aad=aad) == "đang xử lý"
    with pytest.raises(InvalidTag):
        mimi_crypto.open_content(
            dek,
            ciphertext,
            aad=mimi_crypto.event_content_aad(run_id, 4, "assistant.delta"),
        )


def test_conversation_title_is_normalized_bounded_and_resource_bound() -> None:
    conversation = MimiConversation(
        id=uuid7(),
        owner_id=uuid7(),
        sensitivity="standard",
        dek_wrapped=mimi_crypto.create_wrapped_dek(),
    )
    payload = ConversationRename(title="  Lịch   học tuần tới  ", expected_metadata_version=1)
    assert payload.title == "Lịch học tuần tới"
    conversation.title_ciphertext = _seal_conversation_title(conversation, payload.title)
    assert payload.title not in conversation.title_ciphertext
    assert _open_conversation_title(conversation) == payload.title
    other = conversation.model_copy(update={"id": uuid7()})
    with pytest.raises(InvalidTag):
        _open_conversation_title(other)


def test_conversation_cursor_round_trips_and_rejects_invalid_input() -> None:
    updated_at = datetime.now(UTC)
    conversation_id = uuid7()
    assert _decode_conversation_cursor(
        _encode_conversation_cursor(updated_at, conversation_id)
    ) == (updated_at, conversation_id)
    with pytest.raises(Exception, match="422"):
        _decode_conversation_cursor("not-a-cursor")


def test_live_route_cannot_be_enabled_without_real_chat_gate() -> None:
    with pytest.raises(ValueError, match="MIMI_LIVE_PROVIDER_ENABLED"):
        Settings(
            app_env="local",
            oauth_state_secret="test",
            mimi_live_provider_enabled=True,
        )


def test_adaptive_live_route_requires_nonempty_bounded_allowlists() -> None:
    with pytest.raises(ValueError, match="MIMI_ROUTE_ALLOWED_PROVIDERS"):
        Settings(
            app_env="local",
            oauth_state_secret="test",
            mimi_real_chat_enabled=True,
            mimi_live_provider_enabled=True,
            mimi_standard_api_key="synthetic",
            mimi_route_mode="adaptive",
            mimi_route_model="vendor/model",
            mimi_route_allowed_providers="  ",
            mimi_route_allowed_quantizations="fp8",
            mimi_route_max_input_price=1,
            mimi_route_max_output_price=1,
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


def test_message_create_binds_preview_revision() -> None:
    from uuid import uuid4

    from app.agent.service import FeedbackCreate, MessageCreate

    msg = MessageCreate(client_id="c1", content="hello")
    assert msg.intent == "auto"

    cs_id = uuid4()
    digest = "a" * 64
    msg_rev = MessageCreate(
        client_id="c2",
        content="fix title",
        intent="revise_pending_preview",
        expected_change_set_id=cs_id,
        expected_change_set_digest=digest,
    )
    assert msg_rev.intent == "revise_pending_preview"

    fb = FeedbackCreate(
        client_id="fb1",
        target_type="turn",
        target_id="t1",
        comment="good response",
    )
    assert fb.target_type == "turn"
