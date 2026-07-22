"""Prepare the ephemeral Postgres service with prerequisites owned outside Alembic."""

import asyncio
from pathlib import Path

import asyncpg
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_urls import asyncpg_dsn


class PrepareSettings(BaseSettings):
    """CI database URL; local fallback is useful for reproducing the job."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    neon_migrator_url: str


async def main() -> None:
    """Create pgvector and the application schema before Alembic runs."""
    connection = await asyncpg.connect(
        asyncpg_dsn(PrepareSettings().neon_migrator_url),
        timeout=20,
    )
    try:
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await connection.execute("CREATE SCHEMA IF NOT EXISTS microsched")
        await connection.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'microsched_app') THEN
                    CREATE ROLE microsched_app NOLOGIN;
                END IF;
            END;
            $$
            """
        )
    finally:
        await connection.close()
    print("migration_prerequisites=ok")


if __name__ == "__main__":
    asyncio.run(main())
