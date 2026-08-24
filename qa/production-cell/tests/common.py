from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path
from typing import Any

CELL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CELL_ROOT.parents[1]
if str(CELL_ROOT) not in sys.path:
    sys.path.insert(0, str(CELL_ROOT))

from contract import PASS_PHASES, SERVICES
from receipt import initial_receipt

RUN_ID = "msqa025-20260824t000000z-00000000"
SHA40 = "0" * 40
SHA256 = "0" * 64


def workspace_temporary_directory() -> tempfile.TemporaryDirectory[str]:
    parent = CELL_ROOT / ".runs" / "unit-tests"
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


def compose_config() -> dict[str, Any]:
    base = {
        "ports": [],
        "networks": ["cell"],
        "restart": "no",
    }
    services = {name: copy.deepcopy(base) for name in SERVICES}
    services["app"].update(
        {
            "environment": {
                "APP_ENV": "local",
                "SESSION_COOKIE_SECURE": "false",
                "ENABLE_INPROCESS_CRON": "false",
            },
            "depends_on": {"migrate": {"condition": "service_completed_successfully"}},
        }
    )
    services["seed"]["depends_on"] = {
        "migrate": {"condition": "service_completed_successfully"}
    }
    services["browser"]["depends_on"] = {
        "app": {"condition": "service_healthy"},
        "seed": {"condition": "service_completed_successfully"},
    }
    return {
        "services": services,
        "networks": {"cell": {"internal": True}},
    }


def valid_receipt() -> dict[str, Any]:
    receipt = initial_receipt(RUN_ID, "2026-08-24T00:00:00Z")
    receipt.update(
        {
            "git_sha": SHA40,
            "image_id": f"sha256:{SHA256}",
            "ended_at": "2026-08-24T00:01:00Z",
            "final_status": "PASS",
            "phases": [
                {"name": name, "status": "PASS", "duration_ms": 1, "exit_code": 0}
                for name in PASS_PHASES
            ],
            "docker_target": {
                "context_name": "default",
                "endpoint_kind": "unix",
                "endpoint_sha256": SHA256,
                "daemon_id_sha256": SHA256,
                "daemon_name_sha256": SHA256,
                "server_version": "28.0.0",
                "os_type": "linux",
                "daemon_identity_sha256": SHA256,
            },
        }
    )
    receipt["command_envelope"].update(
        {
            "status": "PASS",
            "docker_executable_sha256": SHA256,
            "git_executable_sha256": SHA256,
            "sanitized_env_keys_sha256": SHA256,
            "docker_call_count": 20,
            "compose_call_count": 10,
        }
    )
    receipt["compose"].update(
        {
            "project_directory_sha256": SHA256,
            "files": [
                {"role": "base", "sha256": SHA256},
                {"role": "generated_override", "sha256": SHA256},
            ],
            "config_sha256": SHA256,
        }
    )
    receipt["safety"].update(
        {
            "browser_origin": "runner-loopback:<redacted-ephemeral-port>",
            "networks_by_service": {service: 1 for service in SERVICES},
            "network_count": 1,
            "network_internal": True,
            "network_id_sha256": SHA256,
        }
    )
    receipt["roles"] = {
        "status": "PASS",
        "app": "microsched_app",
        "migrator": "microsched_migrator",
        "ddl_denied": True,
        "alembic_write_denied": True,
        "app_role_only": True,
    }
    receipt["fixtures"].update({"status": "PASS", "task_count": 2, "note_count": 1})
    receipt["migration_gate"] = {
        "status": "PASS",
        "fault_case": "none",
        "exit_code": 0,
        "service_completed_successfully": True,
        "app_create_command_issued": True,
        "app_created_before_success": False,
        "app_container_created": True,
        "app_container_running": True,
    }
    for key in receipt["acceptance"]:
        receipt["acceptance"][key] = (
            "NOT_APPLICABLE" if key in {"025-CI-01", "025-DEP-017"} else "PASS"
        )
    receipt["cleanup"] = {
        "status": "PASS",
        "manifest_verified": True,
        "manifest_schema": "microsched.qa025.run-manifest.v1",
        "manifest_sha256": SHA256,
        "manifest_resource_ids_sha256": SHA256,
        "run_id": RUN_ID,
        "project_name": RUN_ID,
        "daemon_identity_sha256": SHA256,
        "delete_selection": "exact_manifest_resource_ids",
        "delete_command_count": 6,
        "tamper_detected": False,
        "residual_counts": {
            "containers": 0,
            "networks": 0,
            "volumes": 0,
            "images": 0,
            "helper_processes": 0,
        },
        "foreign_sentinel": {
            "project_name_sha256": SHA256,
            "resource_ids_sha256": SHA256,
            "config_sha256_before": SHA256,
            "config_sha256_after": SHA256,
            "survived_cell_cleanup": True,
            "separate_cleanup_status": "PASS",
        },
    }
    return receipt
