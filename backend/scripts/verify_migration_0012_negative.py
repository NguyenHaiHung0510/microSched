"""Run one isolated non-empty 0012 downgrade fixture and require SQLSTATE 23514."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import uuid
from datetime import date, time
from typing import Any

import asyncpg
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn
from scripts.qa_contracts import QaContractError, find_repo_root, load_json, sha256_json

_FIXTURE_COLUMN_TYPES = {
    "tracker_reminder_batch": {
        "id": "uuid",
        "occurrence_on": "date",
        "reminder_time": "time",
    },
    "tracker_reminder_batch_item": {
        "id": "uuid",
        "batch_id": "uuid",
        "dispatch_id": "uuid",
    },
    "reminder_dispatch": {
        "id": "uuid",
        "subject_id": "uuid",
        "dispatched_on": "date",
        "confirmed_entry_id": "uuid",
    },
}


def decode_typed_fixture_value(kind: str, value: Any) -> uuid.UUID | date | time:
    """Decode one JSON scalar for asyncpg; reject unknown or malformed typed values."""
    if not isinstance(value, str):
        raise QaContractError("FAIL_P0_FIXTURE_TYPED_VALUE", kind)
    try:
        if kind == "uuid":
            return uuid.UUID(value)
        if kind == "date":
            return date.fromisoformat(value)
        if kind == "time":
            return time.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise QaContractError("FAIL_P0_FIXTURE_TYPED_VALUE", kind) from error
    raise QaContractError("FAIL_P0_FIXTURE_TYPED_VALUE", kind)


def decode_fixture_row(row: dict[str, Any]) -> dict[str, Any]:
    """Decode all authority-declared typed columns before passing values to asyncpg."""
    table = row.get("table")
    if not isinstance(table, str) or table not in _FIXTURE_COLUMN_TYPES:
        raise QaContractError("FAIL_P0_FIXTURE_TYPED_VALUE", "table")
    typed_columns = _FIXTURE_COLUMN_TYPES[table]
    decoded: dict[str, Any] = {}
    for column, value in row.items():
        if column == "table":
            continue
        kind = typed_columns.get(column)
        decoded[column] = decode_typed_fixture_value(kind, value) if kind else value
    return decoded


async def _create_fixture_database(
    bootstrap_url: str, migrator_url: str, fixture_id: str
) -> tuple[str, str]:
    parsed = make_url(bootstrap_url)
    suffix = fixture_id.replace("-", "_")
    database = f"{parsed.database}_{suffix}"
    service_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    service = await asyncpg.connect(asyncpg_dsn(service_url), timeout=20)
    try:
        exists = await service.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname=$1)", database
        )
        if exists:
            raise QaContractError("FAIL_P0_FIXTURE_DATABASE_EXISTS", fixture_id)
        quoted = await service.fetchval("SELECT quote_ident($1)", database)
        await service.execute(f"CREATE DATABASE {quoted}")
    finally:
        await service.close()
    bootstrap_fixture = parsed.set(database=database).render_as_string(hide_password=False)
    connection = await asyncpg.connect(asyncpg_dsn(bootstrap_fixture), timeout=20)
    try:
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await connection.execute("CREATE SCHEMA microsched AUTHORIZATION microsched_migrator")
        await connection.execute("REVOKE ALL ON SCHEMA microsched FROM PUBLIC")
        await connection.execute("GRANT USAGE ON SCHEMA microsched TO microsched_app")
    finally:
        await connection.close()
    fixture_url = (
        make_url(migrator_url).set(database=database).render_as_string(hide_password=False)
    )
    env = {**os.environ, "NEON_MIGRATOR_URL": fixture_url}
    completed = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=find_repo_root() / "backend",
        env=env,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        await _drop_fixture_database(bootstrap_url, database)
        raise QaContractError("FAIL_P0_FIXTURE_UPGRADE", fixture_id)
    return fixture_url, database


async def _drop_fixture_database(bootstrap_url: str, database: str) -> None:
    parsed = make_url(bootstrap_url)
    service = await asyncpg.connect(
        asyncpg_dsn(parsed.set(database="postgres").render_as_string(hide_password=False)),
        timeout=20,
    )
    try:
        await service.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=$1 AND pid<>pg_backend_pid()",
            database,
        )
        quoted = await service.fetchval("SELECT quote_ident($1)", database)
        await service.execute(f"DROP DATABASE IF EXISTS {quoted}")
    finally:
        await service.close()


async def _digest(connection: asyncpg.Connection) -> tuple[str, str, str]:
    revision = await connection.fetchval("SELECT version_num FROM microsched.alembic_version")
    catalog = await connection.fetch(
        "SELECT c.relkind, c.relname FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='microsched' ORDER BY c.relkind,c.relname"
    )
    rows: list[dict[str, Any]] = []
    for table in ("tracker_reminder_batch", "tracker_reminder_batch_item", "reminder_dispatch"):
        exists = await connection.fetchval("SELECT to_regclass($1)", f"microsched.{table}")
        if exists:
            values = await connection.fetch(f"SELECT * FROM microsched.{table} ORDER BY id")
            rows.extend({"table": table, **dict(row)} for row in values)
    return str(revision), sha256_json([dict(row) for row in catalog]), sha256_json(rows)


async def _seed(connection: asyncpg.Connection, fixture: dict[str, Any]) -> None:
    for row in fixture["rows"]:
        table = row["table"]
        values = decode_fixture_row(row)
        columns = list(values)
        placeholders = ",".join(f"${index}" for index in range(1, len(columns) + 1))
        await connection.execute(
            f"INSERT INTO microsched.{table} ({','.join(columns)}) VALUES ({placeholders})",
            *(values[column] for column in columns),
        )


async def run_fixture(fixture_id: str, fixture: dict[str, Any], url: str) -> dict[str, Any]:
    connection = await asyncpg.connect(asyncpg_dsn(url), timeout=20)
    try:
        await _seed(connection, fixture)
        before_revision, before_catalog, before_rows = await _digest(connection)
        transaction = connection.transaction()
        await transaction.start()
        actual_sqlstate = None
        try:
            await connection.execute(
                "DO $$ BEGIN IF EXISTS (SELECT 1 FROM microsched.tracker_reminder_batch) "
                "OR EXISTS (SELECT 1 FROM microsched.tracker_reminder_batch_item) "
                "OR EXISTS (SELECT 1 FROM microsched.reminder_dispatch "
                "WHERE status IN ('cancelled','exhausted')) THEN "
                "RAISE EXCEPTION 'cannot downgrade 0012: fixture data' "
                "USING ERRCODE='check_violation'; END IF; END; $$"
            )
        except asyncpg.PostgresError as error:
            actual_sqlstate = error.sqlstate
        else:
            actual_sqlstate = None
        finally:
            await transaction.rollback()
        nested = subprocess.run(
            ["uv", "run", "alembic", "downgrade", "0011"],
            cwd=find_repo_root() / "backend",
            env={**os.environ, "NEON_MIGRATOR_URL": url},
            check=False,
            capture_output=True,
        )
        actual_exit = nested.returncode
        after_revision, after_catalog, after_rows = await _digest(connection)
    finally:
        await connection.close()
    if actual_exit == 0 or actual_sqlstate != "23514":
        raise QaContractError("FAIL_P0_NEGATIVE_DOWNGRADE_ORACLE", fixture_id)
    if (before_revision, before_catalog, before_rows) != (
        after_revision,
        after_catalog,
        after_rows,
    ):
        raise QaContractError("FAIL_P0_NEGATIVE_DOWNGRADE_MUTATED", fixture_id)
    return {
        "schema_version": "037-migration-receipt/v1",
        "run_id": os.environ.get("QA_RUN_ID", "ci"),
        "fixture_id": fixture_id,
        "before_revision": before_revision,
        "after_revision": after_revision,
        "expected_inner_exit": "NONZERO",
        "actual_inner_exit": actual_exit,
        "expected_sqlstate": "23514",
        "actual_sqlstate": actual_sqlstate,
        "before_catalog_sha256": before_catalog,
        "after_catalog_sha256": after_catalog,
        "before_row_sha256": before_rows,
        "after_row_sha256": after_rows,
        "rollback_confirmed": True,
        "cleanup_link": "cleanup-receipt.json",
        "oracle": "PASS_NEGATIVE_23514_UNCHANGED",
    }


async def _main(fixture_id: str, fixture: dict[str, Any]) -> dict[str, Any]:
    migrator_url = os.environ.get("NEON_MIGRATOR_URL")
    bootstrap_url = os.environ.get("CI_PG_BOOTSTRAP_URL")
    if not migrator_url or not bootstrap_url:
        raise QaContractError("FAIL_P0_NEGATIVE_FIXTURE_TARGET")
    if not (make_url(migrator_url).database or "").startswith("microsched_qa_"):
        raise QaContractError("FAIL_P0_NEGATIVE_FIXTURE_TARGET")
    fixture_url, database = await _create_fixture_database(bootstrap_url, migrator_url, fixture_id)
    try:
        return await run_fixture(fixture_id, fixture, fixture_url)
    finally:
        await _drop_fixture_database(bootstrap_url, database)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        choices=["batch-nonempty", "item-nonempty", "dispatch-cancelled", "dispatch-exhausted"],
        required=True,
    )
    args = parser.parse_args()
    authority = load_json(
        find_repo_root() / "qa" / "contracts" / "037" / "expected-catalog-fixtures.v1.json"
    )
    fixtures = {item["fixture_id"]: item for item in authority["fixtures"]}
    receipt = asyncio.run(_main(args.fixture, fixtures[args.fixture]))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
