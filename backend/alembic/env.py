"""Alembic environment for the dedicated schema-owner role."""

import asyncio
from logging.config import fileConfig
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

import app.domain.models  # noqa: F401 - importing registers every table
from alembic import context
from app.core.database_urls import async_postgres_url
from app.domain.models import SCHEMA


class MigrationSettings(BaseSettings):
    """Local-only Alembic credentials; this URL never belongs in Fly."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    neon_migrator_url: str


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    async_postgres_url(MigrationSettings().neon_migrator_url).replace("%", "%%"),
)
target_metadata = SQLModel.metadata


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Keep autogenerate scoped to the application schema and out of pgvector internals."""
    if type_ == "schema":
        return name == SCHEMA
    schema_name = parent_names.get("schema_name")
    return schema_name in {None, SCHEMA}


def run_migrations_offline() -> None:
    """Run migrations without creating a live connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        version_table_schema=SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure and execute migrations on a synchronous bridge connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        version_table_schema=SCHEMA,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create the async engine and bridge Alembic's synchronous migration API."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
