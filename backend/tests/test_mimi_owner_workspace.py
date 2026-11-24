"""Namespace policy: entrances do not become an arbitrary owner-ID selector."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent.owner_workspace import (
    OWNER_WORKSPACE_ID,
    legacy_owner_id,
    owner_id,
    owner_ids,
    related_owner_ids,
)
from app.core.settings import get_settings
from app.domain.models import AuthSession


def actor(email):
    return AuthSession(
        user_email=email,
        token_hash=uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


@pytest.fixture(autouse=True)
def policy(monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "synthetic-owner-workspace-102")
    monkeypatch.setenv("ALLOWED_EMAILS", " A@example.test, b@example.test ,A@example.test")
    monkeypatch.setenv("MIMI_OWNER_WORKSPACE_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_allowlisted_entrances_share_only_configured_legacy_aliases():
    a, b = actor("a@example.test"), actor(" B@Example.Test ")
    assert owner_id(a) == owner_id(b) == OWNER_WORKSPACE_ID
    assert (
        owner_ids(a)
        == owner_ids(b)
        == (
            OWNER_WORKSPACE_ID,
            legacy_owner_id(a.user_email),
            legacy_owner_id(b.user_email),
        )
    )
    foreign = legacy_owner_id("foreign@example.test")
    assert related_owner_ids(foreign) == (foreign,)
    with pytest.raises(HTTPException) as denied:
        owner_ids(actor("foreign@example.test"))
    assert denied.value.status_code == 404
    # Restoring the allowed identity restores access without changing policy.
    assert owner_ids(a)[0] == OWNER_WORKSPACE_ID


def test_workspace_requires_explicit_activation(monkeypatch):
    monkeypatch.delenv("MIMI_OWNER_WORKSPACE_ENABLED")
    get_settings.cache_clear()
    assert not get_settings().mimi_owner_workspace_enabled
    a = actor("a@example.test")
    assert owner_id(a) == legacy_owner_id(a.user_email)


def test_allowlist_order_normalization_and_removal(monkeypatch):
    original = owner_ids(actor("a@example.test"))
    monkeypatch.setenv("ALLOWED_EMAILS", "b@example.test,A@Example.Test")
    get_settings.cache_clear()
    assert owner_ids(actor("b@example.test")) == original
    monkeypatch.setenv("ALLOWED_EMAILS", "b@example.test")
    get_settings.cache_clear()
    assert legacy_owner_id("a@example.test") not in owner_ids(actor("b@example.test"))
    assert owner_id(actor("b@example.test")) == OWNER_WORKSPACE_ID
    with pytest.raises(HTTPException):
        owner_id(actor("a@example.test"))


def test_empty_local_allowlist_keeps_existing_synthetic_identity_namespaces(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    get_settings.cache_clear()
    a, b = actor("a@example.test"), actor("b@example.test")
    assert owner_ids(a) == (legacy_owner_id(a.user_email),)
    assert owner_id(a) != owner_id(b)
    assert owner_id(a) == owner_id(actor(" A@EXAMPLE.TEST "))
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(HTTPException):
        owner_id(a)


def test_compatibility_rollback_keeps_login_gate_and_exact_legacy_namespaces(monkeypatch):
    monkeypatch.setenv("MIMI_OWNER_WORKSPACE_ENABLED", "false")
    get_settings.cache_clear()
    a = actor("a@example.test")
    assert owner_ids(a) == (legacy_owner_id(a.user_email),)
    assert related_owner_ids(OWNER_WORKSPACE_ID) == (OWNER_WORKSPACE_ID,)
    with pytest.raises(HTTPException):
        owner_id(actor("foreign@example.test"))
    monkeypatch.setenv("MIMI_OWNER_WORKSPACE_ENABLED", "true")
    get_settings.cache_clear()
    assert owner_ids(a)[0] == OWNER_WORKSPACE_ID
