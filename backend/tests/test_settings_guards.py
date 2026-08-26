"""Fail-closed guards for environment-driven database and cookie settings."""

import pytest
from pydantic import ValidationError

from app.core.database_urls import async_postgres_url
from app.core.settings import Settings

DEVELOP_URL = "postgresql://dev:pw@ep-develop-pooler.example.neon.tech/db?sslmode=require"
PROD_URL = "postgresql://prod:pw@ep-prod.example.neon.tech/db?sslmode=require"
LOOPBACK_DB_URL = "postgresql://user:pass@localhost:5432/microsched"
STAGING_URL = "postgresql://dev@ep-staging.example.neon.tech/db"


def _settings(monkeypatch, **env: str) -> Settings:
    """Build Settings from an explicit env dict, isolated from machine and .env."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEON_DEVELOP_BRANCH_KEY", raising=False)
    monkeypatch.delenv("ALLOW_PROD_DB_IN_LOCAL", raising=False)
    monkeypatch.delenv("NEON_OWNER_URL", raising=False)
    monkeypatch.delenv("NEON_MIGRATOR_URL", raising=False)
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
        NEON_OWNER_URL=PROD_URL,
    )
    assert settings.database_url == async_postgres_url(DEVELOP_URL)


def test_local_without_branch_key_refuses_declared_prod_url(monkeypatch) -> None:
    """Local boot must fail closed when the only URL is the production host."""
    with pytest.raises(ValidationError, match="only accepts a loopback"):
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
    with pytest.raises(ValidationError, match="only accepts a loopback"):
        _settings(
            monkeypatch,
            APP_ENV="local",
            DATABASE_URL=PROD_URL,
            NEON_DEVELOP_BRANCH_KEY=PROD_URL,
        )


def test_local_loopback_database_needs_no_prod_reference(monkeypatch) -> None:
    """A plain developer Postgres on loopback boots without any Neon reference."""
    settings = _settings(
        monkeypatch,
        APP_ENV="local",
        DATABASE_URL=LOOPBACK_DB_URL,
    )
    assert settings.database_url.endswith("localhost:5432/microsched")


def test_local_redirect_with_owner_reference_passes_guard(monkeypatch) -> None:
    """Branch redirect with an explicit prod reference lands on the develop host."""
    settings = _settings(
        monkeypatch,
        APP_ENV="local",
        NEON_DEVELOP_BRANCH_KEY=DEVELOP_URL,
        NEON_OWNER_URL=PROD_URL,
    )
    assert settings.database_url == async_postgres_url(DEVELOP_URL)


def test_local_branch_key_without_any_prod_reference_fails_closed(monkeypatch) -> None:
    """With no prod reference the guard cannot recognize prod, so it refuses."""
    with pytest.raises(ValidationError, match="requires at least one production"):
        _settings(monkeypatch, APP_ENV="local", NEON_DEVELOP_BRANCH_KEY=DEVELOP_URL)


def test_local_missing_declared_url_with_prod_key_still_fails(monkeypatch) -> None:
    """No DATABASE_URL plus a mis-pointed branch key must not reach prod."""
    with pytest.raises(ValidationError, match="production DATABASE_URL"):
        _settings(
            monkeypatch,
            APP_ENV="local",
            NEON_DEVELOP_BRANCH_KEY=PROD_URL,
            NEON_OWNER_URL=PROD_URL,
        )


def test_local_prod_key_over_loopback_db_fails_closed(monkeypatch) -> None:
    """A loopback DATABASE_URL must not launder a prod-pointed branch key."""
    with pytest.raises(ValidationError, match="production DATABASE_URL"):
        _settings(
            monkeypatch,
            APP_ENV="local",
            DATABASE_URL=LOOPBACK_DB_URL,
            NEON_DEVELOP_BRANCH_KEY=PROD_URL,
            NEON_OWNER_URL=PROD_URL,
        )


def test_local_staging_url_with_prod_key_fails_closed(monkeypatch) -> None:
    """A staging DATABASE_URL must never define what prod means for the key."""
    with pytest.raises(ValidationError, match="only accepts a loopback"):
        _settings(
            monkeypatch,
            APP_ENV="local",
            DATABASE_URL=STAGING_URL,
            NEON_DEVELOP_BRANCH_KEY=PROD_URL,
        )


def test_local_pooler_spelling_of_prod_key_is_caught(monkeypatch) -> None:
    """The -pooler spelling of a referenced prod endpoint must still fail."""
    with pytest.raises(ValidationError, match="production DATABASE_URL"):
        _settings(
            monkeypatch,
            APP_ENV="local",
            NEON_DEVELOP_BRANCH_KEY=("postgresql://prod@ep-prod-pooler.example.neon.tech/db"),
            NEON_OWNER_URL=PROD_URL,
        )


def test_local_declared_prod_with_develop_redirect_passes(monkeypatch) -> None:
    """The owner-standard flow: prod declared in .env, key redirects to develop."""
    settings = _settings(
        monkeypatch,
        APP_ENV="local",
        DATABASE_URL=PROD_URL,
        NEON_DEVELOP_BRANCH_KEY=DEVELOP_URL,
        NEON_OWNER_URL=PROD_URL,
    )
    assert settings.database_url == async_postgres_url(DEVELOP_URL)


@pytest.mark.parametrize(
    "host",
    ["::ffff:127.0.0.1", "0:0:0:0:0:0:0:1"],
)
def test_local_ipv6_mapped_loopback_urls_are_accepted(monkeypatch, host) -> None:
    """Canonical IPv6 loopback spellings count as local, not as prod refs."""
    settings = _settings(
        monkeypatch,
        APP_ENV="local",
        DATABASE_URL=f"postgresql://u:p@[{host}]:5432/db",
    )
    assert "5432/db" in settings.database_url
