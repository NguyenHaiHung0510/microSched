"""One-shot bootstrap, seed and role-attestation helper for QA025.

Every credential is read from a mounted file.  The helper prints only stable,
non-secret facts and never renders a DSN.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg

SCHEMA = "microsched"
APP_ROLE = "microsched_app"
MIGRATOR_ROLE = "microsched_migrator"
DB_HOST = "db"
DB_PORT = 5432
DB_NAME = "microsched"


def read_secret(name: str) -> str:
    secret_path = Path("/run/secrets") / name
    value = secret_path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"required mounted secret is empty: {name}")
    return value


async def connect(role: str, password_name: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=role,
        password=read_secret(password_name),
        timeout=20,
    )


async def quoted_literal(connection: asyncpg.Connection, value: str) -> str:
    result = await connection.fetchval("SELECT quote_literal($1)", value)
    if not isinstance(result, str):
        raise TypeError("Postgres did not quote a role password")
    return result


async def create_login_role(
    connection: asyncpg.Connection,
    role_name: str,
    password: str,
) -> None:
    if await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=$1)", role_name
    ):
        raise RuntimeError(f"throwaway database already contains role {role_name}")
    password_sql = await quoted_literal(connection, password)
    await connection.execute(
        f"CREATE ROLE {role_name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"NOREPLICATION NOBYPASSRLS PASSWORD {password_sql}"
    )


async def bootstrap() -> None:
    owner = await connect("postgres", "postgres_owner_password")
    try:
        app_password = read_secret("app_password")
        migrator_password = read_secret("migrator_password")
        await create_login_role(owner, MIGRATOR_ROLE, migrator_password)
        await create_login_role(owner, APP_ROLE, app_password)
        await owner.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await owner.execute(f"CREATE SCHEMA {SCHEMA} AUTHORIZATION {MIGRATOR_ROLE}")
        await owner.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC")
        await owner.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        await owner.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}")
        await owner.execute(f"ALTER ROLE {APP_ROLE} SET search_path = {SCHEMA}, public")
        await owner.execute(f"ALTER ROLE {MIGRATOR_ROLE} SET search_path = public")
    finally:
        await owner.close()

    migrator = await connect(MIGRATOR_ROLE, "migrator_password")
    try:
        await migrator.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
        )
        await migrator.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
        )
    finally:
        await migrator.close()
    print("bootstrap=PASS roles=microsched_app,microsched_migrator schema=microsched")


async def revoke_alembic() -> None:
    migrator = await connect(MIGRATOR_ROLE, "migrator_password")
    try:
        await migrator.execute(
            f"REVOKE ALL ON TABLE {SCHEMA}.alembic_version FROM {APP_ROLE}"
        )
    finally:
        await migrator.close()
    print("alembic_app_grants=revoked")


async def seed() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.readline())
    except json.JSONDecodeError as error:
        raise RuntimeError("seed stdin payload is invalid") from error
    if not isinstance(payload, dict) or set(payload) != {"session_token", "email"}:
        raise RuntimeError("seed stdin payload fields are invalid")
    token = payload["session_token"]
    email = payload["email"]
    if not isinstance(token, str) or len(token) < 32:
        raise RuntimeError("synthetic session token is invalid")
    if not isinstance(email, str) or not email.endswith("@example.invalid"):
        raise RuntimeError("synthetic session email must use example.invalid")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    app = await connect(APP_ROLE, "app_password")
    try:
        async with app.transaction():
            await app.execute(
                f"INSERT INTO {SCHEMA}.session "
                "(id, token_hash, user_email, last_seen_at, expires_at, private_until) "
                "VALUES (gen_random_uuid(), $1, $2, $3, $4, NULL)",
                digest,
                email,
                datetime.now(UTC),
                datetime.now(UTC) + timedelta(days=1),
            )
        facts = await attest_roles(app)
    finally:
        await app.close()
    print("seed=PASS session_digest_only=true synthetic_domain=example.invalid")
    print(json.dumps(facts, sort_keys=True, separators=(",", ":")))


async def attest_roles(app: asyncpg.Connection) -> dict[str, object]:
    current_user = await app.fetchval("SELECT current_user")
    if current_user != APP_ROLE:
        raise RuntimeError("app connection role mismatch")
    table_rows = await app.fetch(
        "SELECT tablename, tableowner FROM pg_tables WHERE schemaname=$1",
        SCHEMA,
    )
    if not table_rows or any(row["tableowner"] != MIGRATOR_ROLE for row in table_rows):
        raise RuntimeError("application tables are not owned by the migrator")
    expected_dml = ("SELECT", "INSERT", "UPDATE", "DELETE")
    dml_checks = [
        await app.fetchval(
            "SELECT has_table_privilege(current_user, $1, $2)",
            f"{SCHEMA}.session",
            privilege,
        )
        for privilege in expected_dml
    ]
    schema_create = await app.fetchval(
        "SELECT has_schema_privilege(current_user, $1, 'CREATE')", SCHEMA
    )
    if not all(dml_checks) or schema_create:
        raise RuntimeError("app DML/DDL privilege split is invalid")
    ddl_denied = False
    try:
        async with app.transaction():
            await app.execute(f"CREATE TABLE {SCHEMA}.__qa025_forbidden(value int)")
            raise RuntimeError("app role unexpectedly created a table")
    except asyncpg.InsufficientPrivilegeError:
        ddl_denied = True
    alembic_update = await app.fetchval(
        "SELECT has_table_privilege(current_user, $1, 'UPDATE')",
        f"{SCHEMA}.alembic_version",
    )
    alembic_delete = await app.fetchval(
        "SELECT has_table_privilege(current_user, $1, 'DELETE')",
        f"{SCHEMA}.alembic_version",
    )
    if alembic_update or alembic_delete:
        raise RuntimeError("app role can write alembic_version")
    return {
        "status": "PASS",
        "current_user_app": True,
        "tables_owned_by_migrator": True,
        "app_dml": True,
        "app_schema_create": False,
        "ddl_denied": ddl_denied,
        "alembic_write_denied": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("bootstrap", "revoke-alembic", "seed"))
    return parser.parse_args()


async def main() -> None:
    mode = parse_args().mode
    handlers = {
        "bootstrap": bootstrap,
        "revoke-alembic": revoke_alembic,
        "seed": seed,
    }
    await handlers[mode]()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"helper=FAIL type={type(error).__name__}", file=sys.stderr)
        raise SystemExit(20) from error
