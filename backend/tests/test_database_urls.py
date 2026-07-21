"""Tests for provider URL normalization at the asyncpg boundary."""

from sqlalchemy.engine import make_url

from app.core.database_urls import async_postgres_url


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
