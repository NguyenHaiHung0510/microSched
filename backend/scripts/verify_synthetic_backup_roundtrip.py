"""Stream an encrypted synthetic pg_dump and compare a throwaway restore inventory."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from typing import Any

import asyncpg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.engine import make_url

from app.core.database_urls import asyncpg_dsn
from scripts.qa_contracts import (
    QaContractError,
    find_repo_root,
    sha256_bytes,
    sha256_json,
    validate_schema,
)

MAGIC = b"MSQA037\x00"


def _docker_exec(container: str, command: list[str], *, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["docker", "exec", "-i", container, *command],
        input=input_bytes,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise QaContractError("FAIL_P0_BACKUP_COMMAND", command[0])
    return completed.stdout


async def _inventory(url: str) -> list[dict[str, Any]]:
    connection = await asyncpg.connect(asyncpg_dsn(url), timeout=20)
    try:
        tables = await connection.fetch(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='microsched' AND c.relkind IN ('r','p') "
            "AND c.relname <> 'alembic_version' ORDER BY c.relname"
        )
        result = []
        for table_row in tables:
            table = table_row["relname"]
            columns = await connection.fetch(
                "SELECT attname FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='microsched' "
                "AND c.relname=$1 AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
                table,
            )
            names = [row["attname"] for row in columns]
            order = "id" if "id" in names else names[0]
            rows = await connection.fetch(f"SELECT * FROM microsched.{table} ORDER BY {order}")
            normalized = [
                {key: str(value) if value is not None else None for key, value in dict(row).items()}
                for row in rows
            ]
            primary = [row.get("id") or row.get(order) for row in normalized]
            result.append(
                {
                    "table": table,
                    "row_count": len(rows),
                    "pk_set_sha256": sha256_json(primary),
                    "invariant_sha256": sha256_json(normalized),
                }
            )
        return result
    finally:
        await connection.close()


async def _database_action(url: str, database: str, *, create: bool) -> None:
    parsed = make_url(url)
    service = await asyncpg.connect(
        asyncpg_dsn(parsed.set(database="postgres").render_as_string(hide_password=False)),
        timeout=20,
    )
    try:
        quoted = await service.fetchval("SELECT quote_ident($1)", database)
        if create:
            exists = await service.fetchval(
                "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname=$1)", database
            )
            if exists:
                raise QaContractError("FAIL_P0_RESTORE_DATABASE_EXISTS")
            await service.execute(f"CREATE DATABASE {quoted}")
        else:
            await service.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=$1 AND pid<>pg_backend_pid()",
                database,
            )
            await service.execute(f"DROP DATABASE IF EXISTS {quoted}")
    finally:
        await service.close()


async def run_backup(run_id: str) -> dict[str, Any]:
    source_url = os.environ.get("CI_PG_BOOTSTRAP_URL")
    container = os.environ.get("QA_PG_CONTAINER")
    if not source_url or not container or container != f"microsched-qa-pg-{run_id}":
        raise QaContractError("FAIL_P0_BACKUP_TARGET")
    source_database = make_url(source_url).database or ""
    if not source_database.startswith("microsched_qa_"):
        raise QaContractError("FAIL_P0_BACKUP_DATABASE")
    dump_bytes = _docker_exec(
        container,
        ["pg_dump", "--format=custom", "--schema=microsched", "--dbname", source_database],
    )
    if not dump_bytes:
        raise QaContractError("FAIL_P0_BACKUP_EMPTY")
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    encrypted = MAGIC + nonce + AESGCM(key).encrypt(nonce, dump_bytes, MAGIC)
    run_dir = find_repo_root() / "output" / "qa-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact = run_dir / "backup-v1.dump.enc"
    artifact.write_bytes(encrypted)
    decrypted = AESGCM(key).decrypt(
        encrypted[len(MAGIC) : len(MAGIC) + 12], encrypted[len(MAGIC) + 12 :], MAGIC
    )
    dump_list = _docker_exec(container, ["pg_restore", "--list"], input_bytes=decrypted)
    restore_database = f"{source_database}_restore"
    await _database_action(source_url, restore_database, create=True)
    source_inventory = await _inventory(source_url)
    restore_url = (
        make_url(source_url).set(database=restore_database).render_as_string(hide_password=False)
    )
    try:
        _docker_exec(
            container,
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--role=microsched_migrator",
                "--dbname",
                restore_database,
            ],
            input_bytes=decrypted,
        )
        restore_inventory = await _inventory(restore_url)
        if source_inventory != restore_inventory:
            raise QaContractError("FAIL_P0_BACKUP_INVENTORY")
    finally:
        await _database_action(source_url, restore_database, create=False)
    catalog_digest = sha256_json(
        [{"table": item["table"], "row_count": item["row_count"]} for item in source_inventory]
    )
    return {
        "schema_version": "037-backup-receipt/v1",
        "run_id": run_id,
        "fixture_id": "backup-v1",
        "seed_manifest_sha256": sha256_json(source_inventory),
        "source_inventory": source_inventory,
        "source_catalog_sha256": catalog_digest,
        "encrypted_artifact_sha256": sha256_bytes(encrypted),
        "dump_list_sha256": sha256_bytes(dump_list),
        "restore_database_opaque_id": hashlib.sha256(restore_database.encode()).hexdigest(),
        "restore_inventory": restore_inventory,
        "restore_catalog_sha256": catalog_digest,
        "dump_exit": 0,
        "decrypt_list_exit": 0,
        "restore_exit": 0,
        "oracle": "PASS_INVENTORY_AND_CATALOG_BYTE_EQUAL",
        "cleanup_link": "cleanup-receipt.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=["backup-v1"], required=True)
    parser.parse_args()
    run_id = os.environ.get("QA_RUN_ID")
    if not run_id:
        raise SystemExit("FAIL_BACKUP_RUN_ID")
    receipt = asyncio.run(run_backup(run_id))
    validate_schema(
        receipt,
        find_repo_root() / "qa" / "contracts" / "037" / "backup-receipt.schema.json",
        label="backup-receipt",
    )
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
