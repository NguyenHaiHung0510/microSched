"""Measure a single app-role query after Neon has autosuspended."""

import asyncio
import time
from pathlib import Path

import asyncpg
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_urls import asyncpg_dsn


class MeasureSettings(BaseSettings):
    """Runtime URL for the one-shot cold-start measurement."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    database_url: str


async def main() -> None:
    """Measure connect plus the first SELECT without issuing a warm-up query."""
    started = time.perf_counter()
    connection = await asyncpg.connect(
        asyncpg_dsn(MeasureSettings().database_url),
        timeout=20,
    )
    try:
        await connection.fetchval("SELECT 1")
    finally:
        await connection.close()
    elapsed = time.perf_counter() - started
    print(f"first_query_seconds={elapsed:.3f}")
    print(f"cold_start_alarm={'yes' if elapsed > 3 else 'no'}")


if __name__ == "__main__":
    asyncio.run(main())
