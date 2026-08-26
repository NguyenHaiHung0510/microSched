"""Fail-closed guards for environment-driven database and cookie settings."""

import pytest
from pydantic import ValidationError

from app.core.database_urls import async_postgres_url
from app.core.settings import Settings

DEVELOP_URL = "postgresql://dev:pw@ep-develop-pooler.example.neon.tech/db?sslmode=require"
PROD_URL = "postgresql://prod:pw@ep-prod.example.neon.tech/db?sslmode=require"


def _settings(monkeypatch, **env: str) -> Settings:
    """Build Settings from an explicit env dict, isolated from machine and .env."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEON_DEVELOP_BRANCH_KEY", raising=False)
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_local_redirects_database_to_develop_branch(monkeypatch) -> None:
    """Local runtime with a branch key must never touch the declared prod URL."""
    settings = _settings(
        monkeypatch,
        APP_ENV="local",
        DATABASE_URL=PROD_URL,
        NEON_DEVELOP_BRANCH_KEY=DEVELOP_URL,
    )
    assert settings.database_url == async_postgres_url(DEVELOP_URL)


def test_local_without_branch_key_refuses_declared_prod_url(monkeypatch) -> None:
    """Local boot must fail closed when the only URL is the production host."""
    with pytest.raises(ValidationError, match="production DATABASE_URL"):
        _settings(monkeypatch, APP_ENV="local", DATABASE_URL=PROD_URL)


def test_cookie_security_defaults_secure_and_overrides_deliberately(monkeypatch) -> None:
    """Missing config means Secure everywhere; relaxing it requires an explicit set."""
    prod = _settings(monkeypatch, APP_ENV="production")
    assert prod.session_cookie_secure is True
    local_default = _settings(monkeypatch, APP_ENV="local")
    assert local_default.session_cookie_secure is False
    local = _settings(monkeypatch, APP_ENV="local", SESSION_COOKIE_SECURE="false")
    assert local.session_cookie_secure is False


def test_local_cookie_override_from_pydantic_source_is_respected() -> None:
    """A value set through pydantic kwargs (like .env parsing) must survive."""
    settings = Settings(_env_file=None, app_env="local", session_cookie_secure=True)
    assert settings.session_cookie_secure is True


def test_local_allows_prod_db_only_with_explicit_opt_in(monkeypatch) -> None:
    """ALLOW_PROD_DB_IN_LOCAL=true is the documented escape hatch."""
    settings = _settings(
        monkeypatch,
        APP_ENV="local",
        DATABASE_URL=PROD_URL,
        ALLOW_PROD_DB_IN_LOCAL="true",
    )
    assert settings.database_url == async_postgres_url(PROD_URL)


def test_local_branch_host_equal_to_prod_host_still_fails_closed(monkeypatch) -> None:
    """A mis-declared branch key pointing at prod must not sneak past the guard."""
    with pytest.raises(ValidationError, match="production DATABASE_URL"):
        _settings(
            monkeypatch,
            APP_ENV="local",
            DATABASE_URL=PROD_URL,
            NEON_DEVELOP_BRANCH_KEY=PROD_URL,
        )
