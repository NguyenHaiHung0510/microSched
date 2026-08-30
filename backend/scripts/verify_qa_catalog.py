"""Verify the exact Task 037 PostgreSQL catalog against frozen authority."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import asyncpg

from app.core.database_urls import asyncpg_dsn
from scripts.qa_contracts import (
    EXPECTED_AUTHORITY_HASHES,
    QaContractError,
    find_repo_root,
    load_json,
    sha256_json,
    validate_schema,
)

QUERY_LABELS = [
    "roles",
    "objects",
    "columns",
    "constraints",
    "indexes",
    "triggers",
    "schema_grants",
    "explicit_grants",
    "bootstrap_default_acl_raw",
    "default_grants",
    "bootstrap_default_acl_residue",
    "bootstrap_residual_grants",
    "revision",
]


def _queries(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    statements = [item.strip() for item in re.split(r";\s*(?:\r?\n|$)", text) if "SELECT" in item]
    if len(statements) != len(QUERY_LABELS):
        raise QaContractError("FAIL_CATALOG_QUERY_COUNT", str(len(statements)))
    return statements


def validate_bootstrap_default_acl_raw(summary: dict[str, Any], expected: dict[str, Any]) -> None:
    if summary != expected:
        raise QaContractError("FAIL_P0_EXTRA_BOOTSTRAP_DEFAULT_ACL_TUPLE")


def validate_explicit_grants(rows: list[dict[str, Any]], expected: dict[str, Any]) -> None:
    grants = expected["grants"]
    table_names = [table["name"] for table in expected["tables"]]
    sequence_names = [sequence["name"] for sequence in expected["sequences"]]
    app_tables = grants["microsched_app_tables"]
    app_sequences = grants["microsched_app_sequences"]
    privilege_lists = (
        grants["microsched_migrator_table_privileges"],
        grants["microsched_migrator_sequence_privileges"],
        grants["microsched_app_table_privileges"],
        grants["microsched_app_sequence_privileges"],
    )
    if (
        len(table_names) != len(set(table_names))
        or len(sequence_names) != len(set(sequence_names))
        or len(app_tables) != len(set(app_tables))
        or len(app_sequences) != len(set(app_sequences))
        or not set(app_tables).issubset(table_names)
        or not set(app_sequences).issubset(sequence_names)
        or set(grants["allowed_object_acl_grantees"]) != {"microsched_app", "microsched_migrator"}
        or any(len(privileges) != len(set(privileges)) for privileges in privilege_lists)
    ):
        raise QaContractError("BLOCK_CATALOG_AUTHORITY_EXPLICIT_GRANTS")

    expected_rows = []
    authority_sets = (
        (
            "table",
            table_names,
            "microsched_migrator",
            grants["microsched_migrator_table_privileges"],
        ),
        (
            "sequence",
            sequence_names,
            "microsched_migrator",
            grants["microsched_migrator_sequence_privileges"],
        ),
        ("table", app_tables, "microsched_app", grants["microsched_app_table_privileges"]),
        (
            "sequence",
            app_sequences,
            "microsched_app",
            grants["microsched_app_sequence_privileges"],
        ),
    )
    for object_kind, object_names, grantee, privileges in authority_sets:
        for object_name in object_names:
            for privilege in privileges:
                expected_rows.append(
                    {
                        "schema": expected["schema"],
                        "object_kind": object_kind,
                        "name": object_name,
                        "grantee": grantee,
                        "privilege": privilege,
                        "is_grantable": False,
                    }
                )

    kind_map = {"r": "table", "p": "table", "S": "sequence"}
    actual_rows = []
    for row in rows:
        object_kind = kind_map.get(row["relkind"])
        if object_kind is None:
            raise QaContractError("FAIL_P0_EXPLICIT_GRANTS", "object-kind")
        actual_rows.append(
            {
                "schema": row["schema_name"],
                "object_kind": object_kind,
                "name": row["relname"],
                "grantee": row["grantee"],
                "privilege": row["privilege_type"],
                "is_grantable": row["is_grantable"],
            }
        )

    def grant_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["schema"],
            item["object_kind"],
            item["name"],
            item["grantee"],
            item["privilege"],
            item["is_grantable"],
        )

    actual_keys = [grant_key(item) for item in actual_rows]
    expected_keys = [grant_key(item) for item in expected_rows]
    if len(actual_keys) != len(set(actual_keys)):
        raise QaContractError("FAIL_P0_EXPLICIT_GRANT_DUPLICATE")
    if len(expected_keys) != len(set(expected_keys)):
        raise QaContractError("BLOCK_CATALOG_AUTHORITY_EXPLICIT_GRANTS")
    if sorted(actual_keys) != sorted(expected_keys):
        raise QaContractError("FAIL_P0_EXPLICIT_GRANTS")


def _normalize_rows(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        item = dict(row)
        for key, value in list(item.items()):
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        result.append(item)
    return result


def _group_default_grants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, bool], list[str]] = {}
    kind_map = {"r": "table", "S": "sequence"}
    for row in rows:
        key = (
            row["owner"],
            row["schema_name"],
            kind_map[row["defaclobjtype"]],
            row["grantee"],
            row["is_grantable"],
        )
        grouped.setdefault(key, []).append(row["privilege_type"])
    return sorted(
        [
            {
                "owner": key[0],
                "schema": key[1],
                "object_kind": key[2],
                "grantee": key[3],
                "privileges": sorted(privileges),
                "is_grantable": key[4],
            }
            for key, privileges in grouped.items()
        ],
        key=lambda item: (item["owner"], item["schema"], item["object_kind"], item["grantee"]),
    )


def validate_catalog_structure(raw: dict[str, Any], expected: dict[str, Any]) -> None:
    expected_objects = sorted(
        [
            {
                "schema_name": expected["schema"],
                "relkind": "r",
                "relname": table["name"],
                "owner": table["owner"],
            }
            for table in expected["tables"]
        ]
        + [
            {
                "schema_name": expected["schema"],
                "relkind": "S",
                "relname": sequence["name"],
                "owner": sequence["owner"],
            }
            for sequence in expected["sequences"]
        ],
        key=lambda item: (item["relkind"], item["relname"]),
    )
    actual_objects = sorted(raw["objects"], key=lambda item: (item["relkind"], item["relname"]))
    if actual_objects != expected_objects:
        raise QaContractError("FAIL_P0_CATALOG_OBJECTS")

    actual_columns_by_table: dict[str, list[dict[str, Any]]] = {}
    for row in raw["columns"]:
        actual_columns_by_table.setdefault(row["table_name"], []).append(row)
    actual_tables = []
    for object_row in actual_objects:
        if object_row["relkind"] not in {"r", "p"}:
            continue
        raw_columns = sorted(
            actual_columns_by_table.get(object_row["relname"], []), key=lambda row: row["attnum"]
        )
        if [row["attnum"] for row in raw_columns] != list(range(1, len(raw_columns) + 1)):
            raise QaContractError("FAIL_P0_CATALOG_COLUMN_ORDER", object_row["relname"])
        actual_tables.append(
            {
                "name": object_row["relname"],
                "owner": object_row["owner"],
                "columns": [
                    {
                        "name": row["attname"],
                        "data_type": row["data_type"],
                        "not_null": row["attnotnull"],
                        "default_expr": row["default_expr"],
                    }
                    for row in raw_columns
                ],
            }
        )
    if sorted(actual_tables, key=lambda item: item["name"]) != expected["tables"]:
        raise QaContractError("FAIL_P0_CATALOG_COLUMNS")

    type_names = {"c": "CHECK", "f": "FOREIGN_KEY", "p": "PRIMARY_KEY", "u": "UNIQUE"}
    actual_constraints = sorted(
        [
            {
                "name": row["conname"],
                "table": row["table_name"],
                "type": type_names.get(row["contype"], row["contype"]),
                "validated": row["convalidated"],
                "definition": row["definition"],
            }
            for row in raw["constraints"]
        ],
        key=lambda item: (item["table"], item["name"]),
    )
    if actual_constraints != sorted(
        expected["constraints"], key=lambda item: (item["table"], item["name"])
    ):
        raise QaContractError("FAIL_P0_CATALOG_CONSTRAINTS")

    actual_indexes = sorted(
        [
            {"name": row["indexname"], "table": row["tablename"], "definition": row["indexdef"]}
            for row in raw["indexes"]
        ],
        key=lambda item: (item["table"], item["name"]),
    )
    if actual_indexes != sorted(
        expected["indexes"], key=lambda item: (item["table"], item["name"])
    ):
        raise QaContractError("FAIL_P0_CATALOG_INDEXES")

    actual_triggers = sorted(
        [
            {
                "name": row["tgname"],
                "table": row["table_name"],
                "function_schema": row["function_schema"],
                "function_name": row["function_name"],
                "enabled": row["tgenabled"],
                "definition": row["definition"],
            }
            for row in raw["triggers"]
        ],
        key=lambda item: (item["table"], item["name"]),
    )
    if actual_triggers != sorted(
        expected["triggers"], key=lambda item: (item["table"], item["name"])
    ):
        raise QaContractError("FAIL_P0_CATALOG_TRIGGERS")


async def _ddl_denials(app_url: str) -> list[dict[str, Any]]:
    statements = {
        "CREATE TABLE": "CREATE TABLE microsched.qa_forbidden_create (id integer)",
        "ALTER TABLE": "ALTER TABLE microsched.task ADD COLUMN qa_forbidden integer",
        "DROP TABLE": "DROP TABLE microsched.task",
    }
    results = []
    for label, sql in statements.items():
        connection = await asyncpg.connect(asyncpg_dsn(app_url), timeout=20)
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(sql)
        except asyncpg.PostgresError as error:
            if error.sqlstate != "42501":
                raise QaContractError("FAIL_P0_DDL_DENIAL_SQLSTATE", label) from error
            results.append({"statement": label, "sqlstate": error.sqlstate, "rolled_back": True})
        else:
            raise QaContractError("FAIL_P0_APP_DDL_ALLOWED", label)
        finally:
            await transaction.rollback()
            await connection.close()
    return results


async def collect_catalog(migrator_url: str, app_url: str, query_path: Path) -> dict[str, Any]:
    connection = await asyncpg.connect(asyncpg_dsn(migrator_url), timeout=20)
    try:
        raw: dict[str, Any] = {}
        for label, query in zip(QUERY_LABELS, _queries(query_path), strict=True):
            rows = await connection.fetch(query)
            if label == "bootstrap_default_acl_raw":
                row = dict(rows[0])
                tuples = row["raw_tuples"]
                if isinstance(tuples, str):
                    tuples = json.loads(tuples)
                raw[label] = {"raw_row_count": row["raw_row_count"], "raw_tuples": tuples}
            else:
                raw[label] = _normalize_rows(rows)
    finally:
        await connection.close()
    raw["ddl_denials"] = await _ddl_denials(app_url)
    return raw


def verify_catalog(raw: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
    expected = authority["catalog_expected"]
    if sha256_json(expected) != authority["catalog_expected_sha256"]:
        raise QaContractError("BLOCK_CATALOG_AUTHORITY_INTERNAL_HASH")
    role_rows = [
        {
            "name": row["rolname"],
            "login": row["rolcanlogin"],
            "superuser": row["rolsuper"],
            "createdb": row["rolcreatedb"],
            "createrole": row["rolcreaterole"],
            "replication": row["rolreplication"],
            "bypassrls": row["rolbypassrls"],
        }
        for row in raw["roles"]
    ]
    if role_rows != expected["roles"]:
        raise QaContractError("FAIL_P0_CATALOG_ROLES")
    validate_catalog_structure(raw, expected)
    revision = [row["version_num"] for row in raw["revision"]]
    if revision != [expected["alembic_revision"]]:
        raise QaContractError("FAIL_P0_CATALOG_REVISION")
    grants = expected["grants"]
    validate_bootstrap_default_acl_raw(
        raw["bootstrap_default_acl_raw"], grants["bootstrap_default_acl_raw_summary"]
    )
    if raw["bootstrap_default_acl_residue"] or raw["bootstrap_residual_grants"]:
        raise QaContractError("FAIL_P0_BOOTSTRAP_GRANT_RESIDUE")
    schema_grants = sorted(
        [
            {
                "grantee": row["grantee"],
                "privilege": row["privilege_type"],
                "is_grantable": row["is_grantable"],
            }
            for row in raw["schema_grants"]
        ],
        key=lambda item: (item["grantee"], item["privilege"]),
    )
    if schema_grants != sorted(
        grants["schema_acl_exact"], key=lambda item: (item["grantee"], item["privilege"])
    ):
        raise QaContractError("FAIL_P0_SCHEMA_GRANTS")
    default_grants = _group_default_grants(raw["default_grants"])
    expected_defaults = sorted(
        grants["default_acl_exact"],
        key=lambda item: (item["owner"], item["schema"], item["object_kind"], item["grantee"]),
    )
    if default_grants != expected_defaults:
        raise QaContractError("FAIL_P0_DEFAULT_GRANTS")
    validate_explicit_grants(raw["explicit_grants"], expected)
    return raw


async def run(fixture: str) -> dict[str, Any]:
    repo_root = find_repo_root()
    contract_dir = repo_root / "qa" / "contracts" / "037"
    query_path = contract_dir / "catalog-queries.v1.sql"
    authority_path = contract_dir / "expected-catalog-fixtures.v1.json"
    authority = load_json(authority_path)
    migrator_url = os.environ.get("NEON_MIGRATOR_URL")
    app_url = os.environ.get("CI_APP_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not migrator_url or not app_url:
        raise QaContractError("FAIL_CATALOG_SYNTHETIC_ENV")
    raw = verify_catalog(await collect_catalog(migrator_url, app_url, query_path), authority)
    run_id = os.environ.get("QA_RUN_ID", "ci")
    receipt = {
        "schema_version": "037-catalog-receipt/v1",
        "run_id": run_id,
        "fixture_id": fixture,
        "revision": authority["catalog_expected"]["alembic_revision"],
        "raw_query_sha256": EXPECTED_AUTHORITY_HASHES["catalog-queries.v1.sql"],
        "authority_sha256": EXPECTED_AUTHORITY_HASHES["expected-catalog-fixtures.v1.json"],
        "catalog_sha256": sha256_json(raw),
        "roles": raw["roles"],
        "objects": raw["objects"],
        "columns": raw["columns"],
        "constraints": raw["constraints"],
        "indexes": raw["indexes"],
        "triggers": raw["triggers"],
        "explicit_grants": raw["explicit_grants"],
        "schema_grants": raw["schema_grants"],
        "default_grants": raw["default_grants"],
        "bootstrap_default_acl_raw": raw["bootstrap_default_acl_raw"],
        "bootstrap_default_acl_residue": raw["bootstrap_default_acl_residue"],
        "bootstrap_residual_grants": raw["bootstrap_residual_grants"],
        "ddl_denials": raw["ddl_denials"],
    }
    validate_schema(receipt, contract_dir / "catalog-receipt.schema.json", label="catalog-receipt")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=["canonical-head"], required=True)
    args = parser.parse_args()
    receipt = asyncio.run(run(args.fixture))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"catalog_verification={error.code}")
        raise SystemExit(2) from error
