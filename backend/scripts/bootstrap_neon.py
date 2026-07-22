"""Provision Neon roles/schema without ever printing connection strings."""

import argparse
import asyncio
import re
import secrets
import time
from pathlib import Path

import asyncpg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn, role_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_ROOT / ".env"
APP_ROLE = "microsched_app"
MIGRATOR_ROLE = "microsched_migrator"
SCHEMA = "microsched"


def parse_args() -> argparse.Namespace:
    """Parse the explicit opt-in for creating missing local role URLs."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provision-local-env",
        action="store_true",
        help="generate missing app/migrator URLs in backend/.env without printing them",
    )
    return parser.parse_args()


def upsert_env(values: dict[str, str]) -> None:
    """Update only named keys while preserving unrelated local configuration."""
    original = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = original.splitlines()

    for key, value in values.items():
        replacement = f"{key}={value}"
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)

    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def ensure_role_urls(provision: bool) -> dict[str, str]:
    """Load role URLs and optionally create missing least-privilege credentials."""
    values = {key: value for key, value in dotenv_values(ENV_PATH).items() if value}
    owner_url = values.get("NEON_OWNER_URL")
    if owner_url is None:
        raise RuntimeError("backend/.env must define NEON_OWNER_URL")
    owner = make_url(owner_url)
    if owner.password in {None, "password"} or owner.host in {None, "host"}:
        raise RuntimeError("backend/.env must contain a real NEON_OWNER_URL")

    updates: dict[str, str] = {}
    expected = {
        "DATABASE_URL": APP_ROLE,
        "NEON_MIGRATOR_URL": MIGRATOR_ROLE,
    }
    for key, username in expected.items():
        current = values.get(key)
        if current is not None:
            current_url = make_url(current)
            if (
                current_url.username == username
                and current_url.password not in {None, "password"}
                and current_url.host == owner.host
                and current_url.port == owner.port
                and current_url.database == owner.database
            ):
                continue
        if not provision:
            raise RuntimeError(f"backend/.env must define a URL for role {username}")
        updates[key] = role_url(owner_url, username, secrets.token_urlsafe(32))

    if updates:
        upsert_env(updates)
        values.update(updates)

    return values


async def quoted_literal(connection: asyncpg.Connection, value: str) -> str:
    """Ask Postgres to quote a secret without exposing it to logs."""
    result = await connection.fetchval("SELECT quote_literal($1)", value)
    if not isinstance(result, str):
        raise RuntimeError("Postgres did not return a quoted role password")
    return result


async def create_or_update_role(
    connection: asyncpg.Connection,
    role_name: str,
    password: str,
) -> None:
    """Create a tightly bounded login role or rotate it to the local password."""
    password_sql = await quoted_literal(connection, password)
    exists = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role_name
    )
    attributes = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    if exists:
        await connection.execute(f"ALTER ROLE {role_name} WITH LOGIN PASSWORD {password_sql}")
    else:
        await connection.execute(
            f"CREATE ROLE {role_name} WITH LOGIN {attributes} PASSWORD {password_sql}"
        )


async def bootstrap(values: dict[str, str]) -> float:
    """Create the extension, roles, schema ownership, and default app grants."""
    owner_url = values["NEON_OWNER_URL"]
    app_url = make_url(values["DATABASE_URL"])
    migrator_url = make_url(values["NEON_MIGRATOR_URL"])
    if app_url.username != APP_ROLE or migrator_url.username != MIGRATOR_ROLE:
        raise RuntimeError("Local URLs do not match the required database roles")
    if app_url.password is None or migrator_url.password is None:
        raise RuntimeError("Role URLs must contain passwords")

    started = time.perf_counter()
    owner = await asyncpg.connect(asyncpg_dsn(owner_url), timeout=20)
    try:
        await owner.fetchval("SELECT 1")
        first_query_seconds = time.perf_counter() - started
        await create_or_update_role(owner, MIGRATOR_ROLE, migrator_url.password)
        await create_or_update_role(owner, APP_ROLE, app_url.password)
        owner_role = await owner.fetchval("SELECT quote_ident(current_user)")
        if not isinstance(owner_role, str):
            raise RuntimeError("Postgres did not return the quoted owner role")
        await owner.execute(f"GRANT {MIGRATOR_ROLE} TO {owner_role} WITH SET TRUE")
        await owner.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        schema_exists = await owner.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = $1)", SCHEMA
        )
        if schema_exists:
            await owner.execute(f"ALTER SCHEMA {SCHEMA} OWNER TO {MIGRATOR_ROLE}")
        else:
            await owner.execute(f"CREATE SCHEMA {SCHEMA} AUTHORIZATION {MIGRATOR_ROLE}")
        await owner.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC")
        await owner.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        await owner.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}")
        await owner.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {SCHEMA} TO {APP_ROLE}"
        )
        await owner.execute(f"ALTER ROLE {APP_ROLE} SET search_path = {SCHEMA}, public")
        await owner.execute(f"ALTER ROLE {MIGRATOR_ROLE} SET search_path = public")
    finally:
        await owner.close()

    migrator = await asyncpg.connect(asyncpg_dsn(values["NEON_MIGRATOR_URL"]), timeout=20)
    try:
        await migrator.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
        )
    finally:
        await migrator.close()

    return first_query_seconds


async def main() -> None:
    """Run bootstrap and print only non-secret verification facts."""
    args = parse_args()
    values = ensure_role_urls(args.provision_local_env)
    first_query_seconds = await bootstrap(values)
    print("bootstrap=ok")
    print(f"owner_first_query_seconds={first_query_seconds:.3f}")
    print(f"roles={APP_ROLE},{MIGRATOR_ROLE}")
    print(f"schema={SCHEMA}")


if __name__ == "__main__":
    asyncio.run(main())
