"""Prepare the ephemeral Postgres service with prerequisites owned outside Alembic."""

import argparse
import asyncio
import os
import re
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn
from scripts.qa_contracts import scan_forbidden_environment
from scripts.validate_synthetic_pg_target import load_validated_receipt


async def prepare(*, bootstrap_url: str, migrator_password: str, app_password: str) -> None:
    """Create synthetic CI roles/schema, then hand schema ownership to migrator."""
    parsed_bootstrap = make_url(bootstrap_url)
    database_name = parsed_bootstrap.database or ""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database_name):
        raise ValueError("synthetic database name must be a bounded lowercase identifier")
    service_url = parsed_bootstrap.set(database="postgres").render_as_string(hide_password=False)
    service = await asyncpg.connect(asyncpg_dsn(service_url), timeout=20)
    try:
        exists = await service.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1)", database_name
        )
        if not exists:
            quoted_database = await service.fetchval("SELECT quote_ident($1)", database_name)
            await service.execute(f"CREATE DATABASE {quoted_database}")
    finally:
        await service.close()
    connection = await asyncpg.connect(asyncpg_dsn(bootstrap_url), timeout=20)
    try:
        await connection.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'microsched_migrator') THEN
                    CREATE ROLE microsched_migrator LOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'microsched_app') THEN
                    CREATE ROLE microsched_app LOGIN;
                END IF;
            END;
            $$
            """
        )
        # Parameters cannot represent identifiers. quote_literal keeps these
        # synthetic passwords values rather than executable SQL, and nothing
        # prints them.
        quoted_migrator_password = await connection.fetchval(
            "SELECT quote_literal($1)", migrator_password
        )
        quoted_app_password = await connection.fetchval("SELECT quote_literal($1)", app_password)
        await connection.execute(
            f"ALTER ROLE microsched_migrator PASSWORD {quoted_migrator_password}"
        )
        await connection.execute(f"ALTER ROLE microsched_app PASSWORD {quoted_app_password}")
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await connection.execute("CREATE SCHEMA IF NOT EXISTS microsched")
        await connection.execute("ALTER SCHEMA microsched OWNER TO microsched_migrator")
        await connection.execute("REVOKE ALL ON SCHEMA microsched FROM PUBLIC")
        await connection.execute("GRANT USAGE ON SCHEMA microsched TO microsched_app")
        # pgvector installs its type in public. Keep read-only USAGE so the
        # migrator can resolve ``vector``, while denying public object creation.
        await connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    finally:
        await connection.close()

    parsed = make_url(bootstrap_url)
    migrator_url = parsed.set(
        username="microsched_migrator",
        password=migrator_password,
    ).render_as_string(hide_password=False)
    migrator = await asyncpg.connect(asyncpg_dsn(migrator_url), timeout=20)
    try:
        await migrator.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA microsched "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO microsched_app"
        )
        await migrator.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA microsched REVOKE ALL ON TABLES FROM PUBLIC"
        )
        await migrator.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA microsched "
            "GRANT USAGE, SELECT ON SEQUENCES TO microsched_app"
        )
        await migrator.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA microsched REVOKE ALL ON SEQUENCES FROM PUBLIC"
        )
    finally:
        await migrator.close()
    print("migration_prerequisites=ok")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-url")
    parser.add_argument("--run-id")
    parser.add_argument("--candidate-sha")
    parser.add_argument("--synthetic-dsn-receipt")
    return parser


def main() -> None:
    args = _parser().parse_args()
    bound = (bool(args.run_id), bool(args.candidate_sha), bool(args.synthetic_dsn_receipt))
    if any(bound) and not all(bound):
        raise SystemExit(
            "--run-id, --candidate-sha and --synthetic-dsn-receipt must be supplied together"
        )
    if args.synthetic_dsn_receipt:
        scan_forbidden_environment()
        _receipt, values, _container_values = load_validated_receipt(
            receipt_path=Path(args.synthetic_dsn_receipt).resolve(strict=True),
            run_id=args.run_id,
            candidate_sha=args.candidate_sha,
        )
        bootstrap_url = values["CI_PG_BOOTSTRAP_URL"]
        migrator_password = make_url(values["NEON_MIGRATOR_URL"]).password
        app_password = make_url(values["CI_APP_DATABASE_URL"]).password
    else:
        bootstrap_url = args.bootstrap_url or os.environ.get("CI_PG_BOOTSTRAP_URL")
        migrator_password = os.environ.get("CI_MIGRATOR_PASSWORD")
        app_password = os.environ.get("CI_APP_PASSWORD")
    if not bootstrap_url or not migrator_password or not app_password:
        raise SystemExit(
            "explicit synthetic bootstrap inputs required: --bootstrap-url/"
            "CI_PG_BOOTSTRAP_URL, CI_MIGRATOR_PASSWORD, CI_APP_PASSWORD"
        )
    asyncio.run(
        prepare(
            bootstrap_url=bootstrap_url,
            migrator_password=migrator_password,
            app_password=app_password,
        )
    )


if __name__ == "__main__":
    main()
