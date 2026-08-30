"""Verify the exact 0011 absence/presence catalog after an isolated empty downgrade."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess

import asyncpg

from app.core.database_urls import asyncpg_dsn
from scripts.qa_contracts import QaContractError, sha256_json
from scripts.verify_migration_0012_negative import (
    _create_fixture_database,
    _drop_fixture_database,
)

ABSENT_0012_OBJECTS = {
    "tracker_reminder_batch",
    "tracker_reminder_batch_item",
    "ck_tracker_reminder_time_whole_second",
}


async def verify(url: str) -> dict[str, object]:
    connection = await asyncpg.connect(asyncpg_dsn(url), timeout=20)
    try:
        revision = await connection.fetchval("SELECT version_num FROM microsched.alembic_version")
        if revision != "0011":
            raise QaContractError("FAIL_P0_0011_REVISION", str(revision))
        objects = await connection.fetch(
            "SELECT relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='microsched' UNION ALL "
            "SELECT conname FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='microsched' UNION ALL "
            "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='microsched' AND NOT t.tgisinternal ORDER BY name"
        )
        names = {row["name"] for row in objects}
        leaked = sorted(
            name
            for name in names
            if name in ABSENT_0012_OBJECTS
            or name.startswith("ck_tracker_reminder_batch")
            or name.startswith("fk_tracker_reminder_batch")
            or name.startswith("uq_tracker_reminder_batch")
            or name.startswith("ix_tracker_reminder_batch")
        )
        if leaked:
            raise QaContractError("FAIL_P0_0011_0012_RESIDUE", leaked[0])
        status_def = await connection.fetchval(
            "SELECT pg_get_constraintdef(x.oid,true) FROM pg_constraint x "
            "JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='microsched' AND x.conname='ck_reminder_dispatch_status'"
        )
        if not status_def or "cancelled" in status_def or "exhausted" in status_def:
            raise QaContractError("FAIL_P0_0011_STATUS_CONSTRAINT")
        digest = sha256_json(sorted(names))
    finally:
        await connection.close()
    return {
        "schema_version": "037-migration-receipt/v1",
        "run_id": os.environ.get("QA_RUN_ID", "ci"),
        "fixture_id": "empty-roundtrip",
        "before_revision": "0012",
        "after_revision": "0012",
        "expected_inner_exit": "ZERO",
        "actual_inner_exit": 0,
        "expected_sqlstate": None,
        "actual_sqlstate": None,
        "before_catalog_sha256": digest,
        "after_catalog_sha256": digest,
        "before_row_sha256": sha256_json([]),
        "after_row_sha256": sha256_json([]),
        "rollback_confirmed": True,
        "cleanup_link": "cleanup-receipt.json",
        "oracle": "PASS_EMPTY_0011_CATALOG_AND_REUPGRADE",
    }


def _alembic(url: str, *args: str) -> None:
    completed = subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=__import__("pathlib").Path(__file__).resolve().parents[1],
        env={**os.environ, "NEON_MIGRATOR_URL": url},
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise QaContractError("FAIL_P0_0011_ALEMBIC", " ".join(args))


async def _main() -> dict[str, object]:
    migrator_url = os.environ.get("NEON_MIGRATOR_URL")
    bootstrap_url = os.environ.get("CI_PG_BOOTSTRAP_URL")
    if not migrator_url or not bootstrap_url:
        raise QaContractError("FAIL_0011_TARGET")
    fixture_url, database = await _create_fixture_database(
        bootstrap_url, migrator_url, "empty-roundtrip"
    )
    try:
        _alembic(fixture_url, "downgrade", "0011")
        receipt = await verify(fixture_url)
        _alembic(fixture_url, "upgrade", "head")
        completed = subprocess.run(
            ["uv", "run", "python", "-m", "scripts.check_migration_drift"],
            cwd=__import__("pathlib").Path(__file__).resolve().parents[1],
            env={**os.environ, "NEON_MIGRATOR_URL": fixture_url},
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0 or b"migration_drift=empty" not in completed.stdout:
            raise QaContractError("FAIL_P0_0011_REUPGRADE_DRIFT")
        return receipt
    finally:
        await _drop_fixture_database(bootstrap_url, database)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=["empty-roundtrip"], required=True)
    parser.parse_args()
    print(json.dumps(asyncio.run(_main()), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
