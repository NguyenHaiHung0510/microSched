"""Tests for provider URL normalization at the asyncpg boundary."""

import pytest
from sqlalchemy.engine import make_url

from app.core.database_urls import SchedulerLockUrlError, async_postgres_url, scheduler_lock_dsn


def test_async_sqlalchemy_url_translates_neon_tls_options() -> None:
    """Neon libpq query options become kwargs accepted by SQLAlchemy asyncpg."""
    normalized = make_url(
        async_postgres_url(
            "postgresql://role:password@example.invalid/database"
            "?sslmode=require&channel_binding=require"
        )
    )

    assert normalized.drivername == "postgresql+asyncpg"
    assert normalized.query == {"ssl": "require"}


def test_scheduler_lock_dsn_keeps_direct_neon_crud_connection_shape() -> None:
    """A direct Neon app URL is already safe for the dedicated lock session."""
    source = (
        "postgresql+asyncpg://app_role:fixture-password@ep-blue.aws.neon.tech:5432/appdb"
        "?ssl=require&application_name=microsched"
    )

    lock_url = make_url(scheduler_lock_dsn(source))

    assert lock_url.drivername == "postgresql"
    assert lock_url.username == "app_role"
    assert lock_url.password == "fixture-password"
    assert lock_url.host == "ep-blue.aws.neon.tech"
    assert lock_url.port == 5432
    assert lock_url.database == "appdb"
    assert lock_url.query == {"ssl": "require", "application_name": "microsched"}


def test_scheduler_lock_dsn_converts_only_neon_pooler_hostname() -> None:
    """The lock uses the matching Neon direct endpoint, never the pooler."""
    source = (
        "postgresql+asyncpg://app_role:fixture-password@ep-blue-pooler.aws.neon.tech/appdb"
        "?ssl=require&application_name=microsched"
    )

    lock_url = make_url(scheduler_lock_dsn(source))

    assert lock_url.host == "ep-blue.aws.neon.tech"
    assert lock_url.username == "app_role"
    assert lock_url.password == "fixture-password"
    assert lock_url.database == "appdb"
    assert lock_url.query == {"ssl": "require", "application_name": "microsched"}


@pytest.mark.parametrize(
    "source",
    (
        "postgresql://app_role:fixture-password@pooler.example.invalid/appdb",
        "postgresql://app_role:fixture-password@ep-blue-pooler.example.invalid/appdb",
        "postgresql://app_role:fixture-password@-pooler.aws.neon.tech/appdb",
    ),
)
def test_scheduler_lock_dsn_rejects_unsupported_pooled_topology(source: str) -> None:
    """Unknown poolers cannot safely hold the process-wide ownership fence."""
    with pytest.raises(SchedulerLockUrlError, match="supported direct endpoint"):
        scheduler_lock_dsn(source)
