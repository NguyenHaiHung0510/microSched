"""Drop only the database and roles bound to one validated synthetic QA receipt."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn
from scripts.qa_contracts import scan_forbidden_environment
from scripts.validate_synthetic_pg_target import load_validated_receipt


async def cleanup(bootstrap_url: str, expected_database: str) -> None:
    parsed = make_url(bootstrap_url)
    if parsed.database != expected_database or not expected_database.startswith("microsched_qa_"):
        raise ValueError("FAIL_P0_CLEANUP_DATABASE_BINDING")
    service_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    connection = await asyncpg.connect(asyncpg_dsn(service_url), timeout=20)
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            expected_database,
        )
        quoted = await connection.fetchval("SELECT quote_ident($1)", expected_database)
        await connection.execute(f"DROP DATABASE IF EXISTS {quoted}")
        # Roles are static by catalog contract but live only inside the run-bound
        # throwaway container. Refuse cleanup if another database still owns data.
        remaining = await connection.fetchval(
            "SELECT count(*) FROM pg_database WHERE datallowconn AND datname NOT IN "
            "('postgres', 'template0', 'template1')"
        )
        if remaining:
            raise ValueError("BLOCK_CLEANUP_OTHER_DATABASE_PRESENT")
        await connection.execute("DROP ROLE IF EXISTS microsched_app")
        await connection.execute("DROP ROLE IF EXISTS microsched_migrator")
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--synthetic-dsn-receipt", required=True)
    parser.add_argument("--require-container", required=True)
    parser.add_argument("--require-network", required=True)
    args = parser.parse_args()
    receipt_path = Path(args.synthetic_dsn_receipt).resolve(strict=True)
    receipt, values, _container_values = load_validated_receipt(
        receipt_path=receipt_path,
        run_id=args.run_id,
        candidate_sha=args.candidate_sha,
    )
    if receipt.get("run_id") != args.run_id:
        raise SystemExit("FAIL_CLEANUP_RUN_BINDING")
    if receipt.get("pg_container") != args.require_container:
        raise SystemExit("FAIL_CLEANUP_CONTAINER_BINDING")
    if receipt.get("network") != args.require_network:
        raise SystemExit("FAIL_CLEANUP_NETWORK_BINDING")
    scan_forbidden_environment()
    bootstrap = values["CI_PG_BOOTSTRAP_URL"]
    database = make_url(bootstrap).database or ""
    host_env = Path(receipt["host_binding"]["env_file_path"])
    container_env = Path(receipt["container_binding"]["env_file_path"])
    try:
        asyncio.run(cleanup(bootstrap, database))
    finally:
        host_env.unlink(missing_ok=True)
        container_env.unlink(missing_ok=True)
    print("qa_database_cleanup=PASS")


if __name__ == "__main__":
    main()
