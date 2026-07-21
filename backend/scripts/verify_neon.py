"""Verify the live schema, trigger, vector placeholder, and runtime role boundary."""

import asyncio
import json
from pathlib import Path

import asyncpg
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_urls import asyncpg_dsn
from app.domain.models import SCHEMA

EXPECTED_TABLES = {
    "alembic_version",
    "app_setting",
    "audit_log",
    "calendar_event",
    "calendar_source",
    "entry",
    "message",
    "note",
    "note_item",
    "session",
    "subscription",
    "task",
    "task_item",
    "tracker",
    "tracker_group",
}


class VerifySettings(BaseSettings):
    """The two non-owner URLs used to prove privilege separation."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    database_url: str
    neon_migrator_url: str


async def create_is_denied(connection: asyncpg.Connection, qualified_table: str) -> bool:
    """Try DDL inside a rolled-back transaction and require insufficient privilege."""
    transaction = connection.transaction()
    await transaction.start()
    try:
        await connection.execute(f"CREATE TABLE {qualified_table} (id integer)")
    except asyncpg.InsufficientPrivilegeError:
        return True
    finally:
        await transaction.rollback()
    return False


async def main() -> None:
    """Run acceptance checks while emitting no connection details or user data."""
    settings = VerifySettings()
    migrator = await asyncpg.connect(asyncpg_dsn(settings.neon_migrator_url), timeout=20)
    app = await asyncpg.connect(asyncpg_dsn(settings.database_url), timeout=20)
    try:
        tables = {
            row["tablename"]
            for row in await migrator.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = $1", SCHEMA
            )
        }
        if tables != EXPECTED_TABLES:
            raise RuntimeError(f"unexpected tables: {sorted(tables)}")

        restricted_roles = await migrator.fetch(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname = ANY($1::text[]) "
            "AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)",
            ["microsched_app", "microsched_migrator"],
        )
        if restricted_roles:
            raise RuntimeError("application database roles have elevated attributes")

        wrong_owners = await migrator.fetch(
            "SELECT tablename, tableowner FROM pg_tables "
            "WHERE schemaname = $1 AND tablename <> 'alembic_version' "
            "AND tableowner <> 'microsched_migrator'",
            SCHEMA,
        )
        if wrong_owners:
            raise RuntimeError("application tables are not owned by microsched_migrator")

        vector_type = await migrator.fetchval(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = $1 AND c.relname = 'note' AND a.attname = 'embedding'",
            SCHEMA,
        )
        if vector_type != "vector":
            raise RuntimeError(f"note.embedding must be dimensionless vector, got {vector_type}")

        hnsw_count = await migrator.fetchval(
            "SELECT count(*) FROM pg_indexes "
            "WHERE schemaname = $1 AND indexdef ILIKE '%USING hnsw%'",
            SCHEMA,
        )
        if hnsw_count != 0:
            raise RuntimeError("HNSW index must remain deferred")

        trigger_tables = {
            row["table_name"]
            for row in await migrator.fetch(
                "SELECT c.relname AS table_name "
                "FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = $1 AND t.tgname = 'set_updated_at' AND NOT t.tgisinternal",
                SCHEMA,
            )
        }
        expected_trigger_tables = EXPECTED_TABLES - {"alembic_version"}
        if trigger_tables != expected_trigger_tables:
            raise RuntimeError("updated_at trigger is not attached to every application table")

        row = await app.fetchrow(
            f"INSERT INTO {SCHEMA}.app_setting (key, value) "
            "VALUES ('__migration_qa_updated_at__', $1::jsonb) "
            "RETURNING id, updated_at",
            json.dumps({"step": 1}),
        )
        await asyncio.sleep(0.02)
        updated_at = await app.fetchval(
            f"UPDATE {SCHEMA}.app_setting SET value = $1::jsonb WHERE id = $2 RETURNING updated_at",
            json.dumps({"step": 2}),
            row["id"],
        )
        await app.execute(f"DELETE FROM {SCHEMA}.app_setting WHERE id = $1", row["id"])
        if row["id"].version != 7:
            raise RuntimeError("server-generated primary key is not UUIDv7")
        if updated_at <= row["updated_at"]:
            raise RuntimeError("updated_at trigger did not advance")

        if not await create_is_denied(app, "public.__microsched_forbidden_qa"):
            raise RuntimeError("runtime role can create tables in public")
        if not await create_is_denied(app, f"{SCHEMA}.__microsched_forbidden_qa"):
            raise RuntimeError("runtime role can create tables in the app schema")
    finally:
        await app.close()
        await migrator.close()

    print(f"tables={','.join(sorted(tables))}")
    print("role_attributes=least_privilege")
    print("table_owner=microsched_migrator")
    print(f"updated_at_triggers={len(trigger_tables)}")
    print("uuid_version=7")
    print("runtime_ddl=denied")
    print("note_embedding=vector_without_dimension")
    print("hnsw_indexes=0")


if __name__ == "__main__":
    asyncio.run(main())
