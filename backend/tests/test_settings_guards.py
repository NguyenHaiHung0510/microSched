"""Fail-closed guards for environment-driven database and cookie settings."""

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


def test_local_without_branch_key_keeps_declared_database_url(monkeypatch) -> None:
    """No branch key means the operator owns the URL choice; nothing is invented."""
    settings = _settings(monkeypatch, APP_ENV="local", DATABASE_URL=PROD_URL)
    assert settings.database_url == async_postgres_url(PROD_URL)


def test_cookie_security_defaults_secure_and_overrides_deliberately(monkeypatch) -> None:
    """Missing config means Secure everywhere; relaxing it requires an explicit set."""
    prod = _settings(monkeypatch, APP_ENV="production")
    assert prod.session_cookie_secure is True
    local_default = _settings(monkeypatch, APP_ENV="local")
    assert local_default.session_cookie_secure is False
    local = _settings(monkeypatch, APP_ENV="local", SESSION_COOKIE_SECURE="false")
    assert local.session_cookie_secure is False
