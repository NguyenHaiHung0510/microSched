"""Canonical receipt construction for every QA025 terminal status."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contract import SERVICES, canonical_json

ZERO_SHA40 = "0" * 40
ZERO_SHA256 = "0" * 64


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def initial_receipt(run_id: str, started_at: str) -> dict[str, Any]:
    return {
        "schema": "microsched.qa025.receipt.v1",
        "run_id": run_id,
        "target_class": "local_disposable",
        "git_sha": ZERO_SHA40,
        "image_id": None,
        "started_at": started_at,
        "ended_at": started_at,
        "final_status": "INFRA_ERROR",
        "phases": [],
        "docker_target": None,
        "command_envelope": {
            "status": "NOT_RUN",
            "docker_executable_sha256": ZERO_SHA256,
            "git_executable_sha256": ZERO_SHA256,
            "sanitized_env_keys_sha256": ZERO_SHA256,
            "rejected_parent_variable_names": [],
            "docker_call_count": 0,
            "compose_call_count": 0,
            "all_calls_used_sanitized_env": True,
            "all_calls_used_explicit_context": True,
            "all_calls_used_absolute_executable": True,
            "all_compose_calls_used_absolute_owned_files": True,
            "all_compose_calls_used_exact_project": True,
            "all_calls_used_shell_false": True,
        },
        "compose": {
            "project_name": run_id,
            "project_directory_sha256": ZERO_SHA256,
            "files": [
                {"role": "base", "sha256": ZERO_SHA256},
                {"role": "generated_override", "sha256": ZERO_SHA256},
            ],
            "config_sha256": ZERO_SHA256,
            "network_name": "cell",
        },
        "safety": {
            "browser_origin": None,
            "ports_by_service": {service: 0 for service in SERVICES},
            "total_ports_published": 0,
            "networks_by_service": {service: 0 for service in SERVICES},
            "network_count": 0,
            "network_internal": None,
            "network_id_sha256": None,
            "unexpected_networks": 0,
            "env_file_disabled": True,
            "outbound_requests": 0,
        },
        "roles": {
            "status": "NOT_RUN",
            "app": None,
            "migrator": None,
            "ddl_denied": None,
            "alembic_write_denied": None,
            "app_role_only": None,
        },
        "fixtures": {
            "status": "NOT_RUN",
            "prefix": f"[QA025:{run_id}]",
            "task_count": 0,
            "note_count": 0,
            "synthetic_domain": "example.invalid",
        },
        "migration_gate": {
            "status": "NOT_RUN",
            "fault_case": "not_run",
            "exit_code": None,
            "service_completed_successfully": False,
            "app_create_command_issued": False,
            "app_created_before_success": False,
            "app_container_created": False,
            "app_container_running": False,
        },
        "acceptance": {
            "025-SAFE-01": "NOT_RUN",
            "025-SAFE-02": "NOT_RUN",
            "025-SAFE-03": "NOT_RUN",
            "025-SAFE-04": "NOT_RUN",
            "025-SAFE-05": "NOT_RUN",
            "025-SAFE-06": "NOT_RUN",
            "025-SAFE-07": "NOT_RUN",
            "025-CELL-01": "NOT_RUN",
            "025-CELL-02": "NOT_RUN",
            "025-CELL-03": "NOT_RUN",
            "025-CELL-04": "NOT_RUN",
            "025-CELL-05": "NOT_RUN",
            "025-CELL-06": "NOT_RUN",
            "025-RED-01": "PASS",
            "025-CI-01": "NOT_APPLICABLE",
            "025-DEP-017": "NOT_APPLICABLE",
        },
        "cleanup": {
            "status": "NOT_RUN",
            "manifest_verified": False,
            "manifest_schema": None,
            "manifest_sha256": None,
            "manifest_resource_ids_sha256": None,
            "run_id": None,
            "project_name": None,
            "daemon_identity_sha256": None,
            "delete_selection": "exact_manifest_resource_ids",
            "delete_command_count": 0,
            "tamper_detected": False,
            "residual_counts": {
                "containers": 0,
                "networks": 0,
                "volumes": 0,
                "images": 0,
                "helper_processes": 0,
            },
            "foreign_sentinel": None,
        },
        "physical_iphone": {
            "acceptance_id": "Q025-DEVICE-IPHONE-01",
            "status": "NOT_RUN",
            "reason": "Physical iPhone acceptance is separate from the disposable local cell",
            "production_commit": None,
            "executed_at": None,
            "evidence": [],
        },
    }


def atomic_write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(receipt))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_receipt(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("receipt root is not an object")
    return value
