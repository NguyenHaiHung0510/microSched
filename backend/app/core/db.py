"""Async database engine and fail-soft connectivity checks."""

from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine | None:
    """Return the process-wide async engine when the database is configured."""
    database_url = get_settings().database_url
    if database_url is None:
        return None

    return create_async_engine(database_url, pool_pre_ping=True)


async def check_database() -> str:
    """Return a health label without allowing database failures to crash healthz."""
    engine = get_engine()
    if engine is None:
        return "down"

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:  # healthz must remain fail-soft for every driver/network failure
        return "down"

    return "up"
