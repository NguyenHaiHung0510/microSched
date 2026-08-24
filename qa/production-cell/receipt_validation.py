"""JSON Schema plus semantic and recursive-redaction validation for QA025."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from contract import GuardDenied, PASS_PHASES, parse_fixture_prefix, validate_run_id
from jsonschema import Draft202012Validator, FormatChecker

FORBIDDEN_KEY = re.compile(
    r"database_url|owner_url|migrator_url|password|session_token|pin|aes_key|cookie|"
    r"authorization|container_env|env_dump",
    re.IGNORECASE,
)
FORBIDDEN_STRING = re.compile(
    r"postgres(?:ql)?://|(?:[a-z0-9-]+\.)*neon\.tech|(?:[a-z0-9-]+\.)*fly\.dev",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
ALLOWED_DAEMON_PAIRS = {
    ("default", "unix"),
    ("default", "npipe"),
    ("desktop-linux", "npipe"),
}


class ReceiptValidationError(ValueError):
    """A stable, secret-free validator error."""


def _scan_redaction(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if FORBIDDEN_KEY.search(str(key)):
                raise ReceiptValidationError(f"forbidden key at {path}: {key}")
            _scan_redaction(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _scan_redaction(child, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    if FORBIDDEN_STRING.search(value):
        raise ReceiptValidationError(f"forbidden target/DB string at {path}")
    for match in EMAIL.finditer(value):
        if match.group(1).casefold() != "example.invalid":
            raise ReceiptValidationError(f"non-synthetic email at {path}")


def _parse_timestamp(value: str, *, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReceiptValidationError(f"{field} is not a valid UTC timestamp") from error


def validate_receipt_object(schema: dict[str, Any], receipt: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(receipt), key=lambda item: list(item.absolute_path)
    )
    if errors:
        first = errors[0]
        location = "$" + "".join(f"[{part!r}]" for part in first.absolute_path)
        raise ReceiptValidationError(
            f"schema validation failed at {location}: {first.message}"
        )

    _scan_redaction(receipt)
    started = _parse_timestamp(receipt["started_at"], field="started_at")
    ended = _parse_timestamp(receipt["ended_at"], field="ended_at")
    if ended < started:
        raise ReceiptValidationError("ended_at precedes started_at")

    phases = receipt["phases"]
    names = [phase["name"] for phase in phases]
    if len(names) != len(set(names)):
        raise ReceiptValidationError("phase names must not repeat")
    if receipt["final_status"] == "PASS" and tuple(names) != PASS_PHASES:
        raise ReceiptValidationError(
            "PASS receipt must contain the nine canonical phases in order"
        )

    docker_target = receipt["docker_target"]
    if docker_target is not None:
        pair = (docker_target["context_name"], docker_target["endpoint_kind"])
        if pair not in ALLOWED_DAEMON_PAIRS:
            raise ReceiptValidationError(
                "Docker context/endpoint-kind pair is not allowlisted"
            )

    compose = receipt["compose"]
    roles = [entry["role"] for entry in compose["files"]]
    if sorted(roles) != ["base", "generated_override"]:
        raise ReceiptValidationError(
            "Compose receipt must bind one base and one generated override"
        )
    run_id = receipt["run_id"]
    try:
        validate_run_id(run_id)
        validate_run_id(compose["project_name"], label="compose.project_name")
        fixture_run_id = parse_fixture_prefix(receipt["fixtures"]["prefix"])
    except GuardDenied as error:
        raise ReceiptValidationError("fixture/run ID semantic binding failed") from error
    if fixture_run_id.encode("utf-8") != run_id.encode("utf-8"):
        raise ReceiptValidationError("fixtures.prefix run_id must equal receipt run_id")
    if compose["project_name"].encode("utf-8") != run_id.encode("utf-8"):
        raise ReceiptValidationError("Compose project_name must equal run_id")

    cleanup = receipt["cleanup"]
    for field in ("run_id", "project_name"):
        cleanup_id = cleanup[field]
        if cleanup_id is not None:
            try:
                validate_run_id(cleanup_id, label=f"cleanup.{field}")
            except GuardDenied as error:
                raise ReceiptValidationError(
                    "fixture/run ID semantic binding failed"
                ) from error
            if cleanup_id.encode("utf-8") != run_id.encode("utf-8"):
                raise ReceiptValidationError(
                    f"cleanup {field} must equal receipt run_id"
                )
    if receipt["final_status"] == "PASS" and (
        cleanup["run_id"] is None or cleanup["project_name"] is None
    ):
        raise ReceiptValidationError("PASS receipt must bind cleanup run and project IDs")
    if (
        docker_target is not None
        and cleanup["daemon_identity_sha256"] is not None
        and cleanup["daemon_identity_sha256"] != docker_target["daemon_identity_sha256"]
    ):
        raise ReceiptValidationError(
            "cleanup daemon identity differs from target identity"
        )
    sentinel = cleanup["foreign_sentinel"]
    if (
        sentinel is not None
        and sentinel["config_sha256_before"] != sentinel["config_sha256_after"]
    ):
        raise ReceiptValidationError(
            "foreign sentinel config hash changed during cell cleanup"
        )


def load_and_validate(schema_path: Path, receipt_path: Path) -> dict[str, Any]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReceiptValidationError(
            "schema or receipt is missing/invalid JSON"
        ) from error
    if not isinstance(schema, dict) or not isinstance(receipt, dict):
        raise ReceiptValidationError("schema and receipt roots must be objects")
    validate_receipt_object(schema, receipt)
    return receipt
