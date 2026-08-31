"""Fail-closed helpers shared by the Task 037 QA harness."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

EXPECTED_AUTHORITY_HASHES = {
    "authority-receipts.schema.json": (
        "6d70251c57b1f1e5f82113583005e4307523874db596c98a64fc2c7a7bda7266"
    ),
    "review-envelope.schema.json": (
        "3b01043108c6908edf67004c97a9a3e54bea547ea63b67515ac644ff9e4ad74d"
    ),
    "expected-authority-review.schema.json": (
        "c80d46278c633e1dda576141ff45618379ed4c97c92fcb0fbc773d921541e700"
    ),
    "strategy-approval-source.schema.json": (
        "f373d408735c9661719837620981755c11911cc166ab76c251239e469c30b4af"
    ),
    "command-contract.v1.json": "76702fc352a13f8b8ad79d523025060ba82ffc3d2d5af72ad878e244c90d7f83",
    "matrix-inventory.v1.json": "605b8a51e97af23031424110f660e8087113c5d91fab6dda45858aa409b2ffd1",
    "expected-catalog-fixtures.v1.json": (
        "fa43eaeb8026fb131f99008bd1108a05d558099c8cdd2a2afdd52c92b5c31470"
    ),
    "catalog-queries.v1.sql": "dd61cd02e2d2fcfeeaba04ca6d12677fc9c58f3165499c43e518b1daf2418b9c",
}
STRATEGY_RECEIPT_SHA256 = "b800bc1a713b914f20f0128ecc5d3296ed649064dc4d5609a4e229346c3329b5"
STATUS = frozenset({"PASS", "FAIL", "NOT_RUN", "BLOCKED", "SKIPPED_OPTIONAL"})
P0_ORACLE_TOKENS = frozenset(
    {"privacy", "private", "schema", "catalog", "backup", "migration", "dsn", "production"}
)
DISALLOWED_DB_ENV_NAMES = frozenset(
    {
        "DATABASE_URL",
        "NEON_OWNER_URL",
        "NEON_MIGRATOR_URL",
        "NEON_DEVELOP_BRANCH_KEY",
        "DATABASE_URL_DEVELOP",
        "CI_PG_BOOTSTRAP_URL",
        "CI_APP_DATABASE_URL",
    }
)


class QaContractError(ValueError):
    """A stable-code fail-closed validation error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise QaContractError("FAIL_SCHEMA_UTC", "invalid UTC timestamp") from error
    if parsed.tzinfo is None:
        raise QaContractError("FAIL_SCHEMA_UTC", "timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def strict_json_loads(value: str, *, source: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise QaContractError("FAIL_DUPLICATE_JSON_KEY", f"{source}:{key}")
            result[key] = item
        return result

    try:
        return json.loads(value, object_pairs_hook=pairs_hook)
    except QaContractError:
        raise
    except json.JSONDecodeError as error:
        raise QaContractError("FAIL_JSON_PARSE", f"{source}:{error.lineno}") from error


def load_json(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"), source=path.as_posix())
    except OSError as error:
        raise QaContractError("FAIL_ARTIFACT_MISSING", path.as_posix()) from error


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path, *, normalize_lf: bool = False) -> str:
    try:
        value = path.read_bytes()
    except OSError as error:
        raise QaContractError("FAIL_ARTIFACT_MISSING", path.as_posix()) from error
    if normalize_lf:
        value = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return sha256_bytes(value)


def validate_schema(instance: Any, schema_path: Path, *, label: str) -> None:
    schema = load_json(schema_path)
    registry = Registry()
    for candidate in schema_path.parent.glob("*.schema.json"):
        contents = load_json(candidate)
        if "$id" in contents:
            registry = registry.with_resource(contents["$id"], Resource.from_contents(contents))
    validator = Draft202012Validator(schema, format_checker=FormatChecker(), registry=registry)
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    if errors:
        first = errors[0]
        path = ".".join(str(item) for item in first.absolute_path) or "$"
        raise QaContractError("FAIL_SCHEMA", f"{label}:{path}:{first.message}")


def resolve_inside(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not relative or "\\" in relative or Path(relative).is_absolute():
        raise QaContractError("FAIL_PATH_SCOPE", relative)
    parts = Path(relative).parts
    if ".." in parts or "." in parts[1:]:
        raise QaContractError("FAIL_PATH_SCOPE", relative)
    root_resolved = root.resolve(strict=True)
    candidate = (root_resolved / relative).resolve(strict=must_exist)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as error:
        raise QaContractError("FAIL_PATH_SCOPE", relative) from error
    for parent in [candidate, *candidate.parents]:
        if parent == root_resolved:
            break
        if parent.is_symlink():
            raise QaContractError("FAIL_PATH_REPARSE", relative)
    return candidate


def find_repo_root(start: Path | None = None) -> Path:
    candidate = (start or Path.cwd()).resolve()
    for directory in [candidate, *candidate.parents]:
        if (directory / "CLAUDE.md").is_file() and (
            directory / "qa" / "contracts" / "037"
        ).is_dir():
            return directory
    raise QaContractError("FAIL_REPO_ROOT", candidate.as_posix())


def git_output(repo_root: Path, *args: str, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise QaContractError("FAIL_GIT_QUERY", " ".join(args))
    return completed.stdout if binary else completed.stdout.decode("utf-8", errors="strict").strip()


def verify_expected_authority_hashes(contract_dir: Path) -> dict[str, str]:
    actual: dict[str, str] = {}
    for name, expected in EXPECTED_AUTHORITY_HASHES.items():
        digest = sha256_file(contract_dir / name, normalize_lf=True)
        if digest != expected:
            raise QaContractError("BLOCK_EXPECTED_AUTHORITY_DRIFT", name)
        actual[name] = digest
    return actual


def argv_sha256(argv: list[str]) -> str:
    return sha256_json(argv)


def failure_mapping(oracle_id: str) -> tuple[str, str]:
    lowered = oracle_id.lower()
    if any(token in lowered for token in P0_ORACLE_TOKENS):
        return "FAIL_P0", "P0"
    return "FAIL", "P1"


def ensure_clean_contract(repo_root: Path, run_id: str) -> str:
    raw = git_output(repo_root, "status", "--porcelain=v1", "-z", binary=True)
    assert isinstance(raw, bytes)
    allowed_prefix = f"output/qa-runs/{run_id}/"
    for item in raw.split(b"\0"):
        if not item:
            continue
        text = item.decode("utf-8", errors="strict")
        status, path = text[:2], text[3:]
        if status != "??" or not path.replace("\\", "/").startswith(allowed_prefix):
            raise QaContractError("BLOCK_DIRTY_CANDIDATE", path)
    return sha256_bytes(raw)


def scan_forbidden_environment() -> None:
    names = sorted(name for name in DISALLOWED_DB_ENV_NAMES if os.environ.get(name))
    if names:
        raise QaContractError("FAIL_P0_PROCESS_DB_ENV_PRESENT", ",".join(names))


def validate_run_id(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value):
        raise QaContractError("FAIL_RUN_ID", "expected lowercase UUID")
