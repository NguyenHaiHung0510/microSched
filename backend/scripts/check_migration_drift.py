"""Run Alembic's autogenerate comparison and require an empty diff."""

import asyncio
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import app.domain.models  # noqa: F401 - importing registers every table
from app.core.database_urls import async_postgres_url
from app.domain.models import SCHEMA


class DriftSettings(BaseSettings):
    """Migration credentials for local or CI drift checks."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    neon_migrator_url: str


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Compare only the application schema."""
    if type_ == "schema":
        return name == SCHEMA
    return parent_names.get("schema_name") in {None, SCHEMA}


def compare(connection) -> list:
    """Return the same model/database differences Alembic autogenerate sees."""
    context = MigrationContext.configure(
        connection,
        opts={
            "target_metadata": SQLModel.metadata,
            "include_schemas": True,
            "include_name": include_name,
            "compare_type": True,
            "compare_server_default": True,
            "version_table_schema": SCHEMA,
        },
    )
    return compare_metadata(context, SQLModel.metadata)


async def main() -> None:
    """Connect, compare, and fail with the structural diff when drift exists."""
    engine = create_async_engine(async_postgres_url(DriftSettings().neon_migrator_url))
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(compare)
    finally:
        await engine.dispose()

    if differences:
        for difference in differences:
            print(repr(difference))
        raise SystemExit("migration_drift=detected")
    print("migration_drift=empty")


if __name__ == "__main__":
    asyncio.run(main())
