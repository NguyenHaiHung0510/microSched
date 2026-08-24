"""Disposable production-image cell lifecycle for QA025."""

from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from contract import (
    SERVICES,
    AssertionFailure,
    BlockedPrerequisite,
    CellError,
    CleanupGuardDenied,
    GuardDenied,
    assert_migration_gate,
    assert_no_runtime_port_bindings,
    assert_zero_residuals,
    canonical_json,
    fixture_label_ledger,
    guard_parent_environment,
    sha256_bytes,
    sha256_file,
    timeout_status_for_phase,
    validate_browser_source,
    validate_compose_config,
    validate_fixture_identity_bindings,
    validate_run_id,
)
from envelope import CommandEnvelope, DockerTarget
from manifest import (
    MANIFEST_SCHEMA,
    locked_run_directory,
    read_verified_manifest,
    resource_ids_sha256,
    update_resources,
    verify_manifest_bindings,
    write_manifest,
)
from receipt import atomic_write_receipt, initial_receipt, read_receipt, utc_now
from receipt_validation import validate_receipt_object

BASE_DB_IMAGE = "pgvector/pgvector:pg18"
BUILD_TIMEOUT = 20 * 60
SETUP_TIMEOUT = 5 * 60
APP_READY_TIMEOUT = 90
BROWSER_TIMEOUT = 10 * 60
CLEANUP_TIMEOUT = 2 * 60


def new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
    return f"msqa025-{timestamp}-{secrets.token_hex(4)}"


@dataclass
class PhaseTracker:
    phases: list[dict[str, Any]] = field(default_factory=list)
    current_name: str | None = None
    current_started: float = 0.0

    def start(self, name: str) -> None:
        if self.current_name is not None:
            raise RuntimeError("a phase is already active")
        self.current_name = name
        self.current_started = time.monotonic()

    def finish(self, status: str = "PASS", exit_code: int | None = 0) -> None:
        if self.current_name is None:
            raise RuntimeError("no phase is active")
        duration = max(0, round((time.monotonic() - self.current_started) * 1000))
        self.phases.append(
            {
                "name": self.current_name,
                "status": status,
                "duration_ms": duration,
                "exit_code": exit_code,
            }
        )
        self.current_name = None

    def fail_current(self, status: str, exit_code: int | None) -> None:
        if self.current_name is not None:
            self.finish(status, exit_code)


@dataclass
class Sentinel:
    project_name: str
    container_id: str
    network_id: str
    config_sha256_before: str
    resource_ids_sha256: str
    project_name_sha256: str
    config_sha256_after: str | None = None
    survived: bool = False
    separate_cleanup_status: str = "NOT_RUN"


@dataclass
class CellRun:
    repo_root: Path
    qa_directory: Path
    run_id: str
    run_directory: Path
    secret_directory: Path
    command_temp: Path
    override_file: Path
    receipt_path: Path
    manifest_path: Path
    envelope: CommandEnvelope
    receipt: dict[str, Any]
    phases: PhaseTracker = field(default_factory=PhaseTracker)
    docker_target: DockerTarget | None = None
    candidate_sha: str = "0" * 40
    app_image_id: str | None = None
    resources: dict[str, list[str]] = field(
        default_factory=lambda: {
            "containers": [],
            "networks": [],
            "volumes": [],
            "images": [],
        }
    )
    service_containers: dict[str, str] = field(default_factory=dict)
    sentinel: Sentinel | None = None
    secret_values: dict[str, str] = field(default_factory=dict)
    manifest_exists: bool = False
    cleanup_delete_count: int = 0
    cleanup_delete_permitted: bool = False
    migration_exit_code: int | None = None
    fixture_labels: tuple[str, ...] = ()

    @property
    def base_compose(self) -> Path:
        return self.qa_directory / "compose.yaml"

    @property
    def image_tags(self) -> dict[str, str]:
        return {
            "db": f"{self.run_id}-db:candidate",
            "app": f"{self.run_id}-app:candidate",
            "helper": f"{self.run_id}-helper:candidate",
            "browser": f"{self.run_id}-browser:candidate",
        }

    @property
    def network_name(self) -> str:
        return f"{self.run_id}_cell"

    def _verify_manifest(self) -> dict[str, Any]:
        if not self.manifest_exists or self.docker_target is None:
            raise GuardDenied(
                "mutable operation attempted before manifest/daemon binding"
            )
        payload = read_verified_manifest(self.manifest_path)
        verify_manifest_bindings(
            payload,
            run_id=self.run_id,
            project_name=self.run_id,
            daemon_identity_sha256=self.docker_target.daemon_identity_sha256,
            git_sha=self.candidate_sha,
            docker_executable_sha256=self.envelope.receipt.executable_sha256,
            project_directory=self.qa_directory,
            compose_files=(self.base_compose, self.override_file),
        )
        return payload

    def validate_fixture_contract(self) -> None:
        cleanup = self.receipt["cleanup"]
        cleanup_run_id = cleanup.get("run_id")
        cleanup_project_name = cleanup.get("project_name")
        if not isinstance(cleanup_run_id, str) or not isinstance(
            cleanup_project_name, str
        ):
            raise GuardDenied("preflight cleanup IDs must be bound before mutation")
        validate_fixture_identity_bindings(
            run_id=self.run_id,
            project_name=self.receipt["compose"]["project_name"],
            cleanup_run_id=cleanup_run_id,
            cleanup_project_name=cleanup_project_name,
            fixture_prefix=self.receipt["fixtures"]["prefix"],
            fixture_labels=self.fixture_labels,
        )

    def compose(
        self,
        args: list[str],
        *,
        timeout: float = 120,
        input_bytes: bytes | None = None,
        manifest_required: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        if manifest_required:
            self._verify_manifest()
        return self.envelope.run_compose(
            args,
            project_name=self.run_id,
            base_file=self.base_compose,
            override_file=self.override_file,
            run_temp=self.run_directory,
            timeout=timeout,
            input_bytes=input_bytes,
        )

    def docker(
        self,
        args: list[str],
        *,
        timeout: float = 120,
        input_bytes: bytes | None = None,
        mutable: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        if mutable:
            self._verify_manifest()
        return self.envelope.run_docker(args, timeout=timeout, input_bytes=input_bytes)

    def add_resource(self, kind: str, resource_id: str) -> None:
        if resource_id not in self.resources[kind]:
            self.resources[kind].append(resource_id)
        update_resources(self.manifest_path, self.resources)


def _write_runtime_file(path: Path, value: str, *, secret_file: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(temporary, flags, 0o600 if secret_file else 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if secret_file and os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _generated_override(run: CellRun) -> dict[str, Any]:
    run.validate_fixture_contract()
    labels = {
        "com.docker.compose.project": run.run_id,
        "com.microsched.qa025.run_id": run.run_id,
    }
    tags = run.image_tags
    secret_files = {
        name: {"file": str(run.secret_directory / name)}
        for name in (
            "postgres_owner_password",
            "app_password",
            "migrator_password",
            "migrator_url",
            "app_url",
            "aes_key",
        )
    }
    services: dict[str, Any] = {
        "db": {
            "image": tags["db"],
            "labels": labels,
            "build": {
                "context": str(run.repo_root),
                "dockerfile": "qa/production-cell/db/Dockerfile",
                "labels": labels,
            },
        },
        "bootstrap": {
            "image": tags["helper"],
            "labels": labels,
            "build": {
                "context": str(run.repo_root),
                "dockerfile": "qa/production-cell/helper/Dockerfile",
                "labels": labels,
            },
        },
        "seed": {"image": tags["helper"], "labels": labels},
        "migrate": {"image": tags["app"], "labels": labels},
        "app": {
            "image": tags["app"],
            "labels": labels,
            "build": {
                "context": str(run.repo_root),
                "dockerfile": "Dockerfile",
                "args": {"GIT_SHA": run.candidate_sha},
                "labels": labels,
            },
        },
        "browser": {
            "image": tags["browser"],
            "labels": labels,
            "build": {
                "context": str(run.repo_root),
                "dockerfile": "qa/production-cell/browser/Dockerfile",
                "labels": labels,
            },
        },
    }
    return {
        "services": services,
        "networks": {
            "cell": {
                "name": run.network_name,
                "internal": True,
                "labels": labels,
            }
        },
        "secrets": secret_files,
    }


def _prepare_runtime_files(run: CellRun) -> None:
    run.secret_directory.mkdir(parents=True, exist_ok=True)
    run.command_temp.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(run.run_directory, 0o700)
        os.chmod(run.secret_directory, 0o700)
    # Compose config validation only needs the regular source paths to exist.
    # Values are generated after all build/pull calls, immediately before runtime.
    placeholder_names = (
        "postgres_owner_password",
        "app_password",
        "migrator_password",
        "migrator_url",
        "app_url",
        "aes_key",
    )
    for name in placeholder_names:
        _write_runtime_file(run.secret_directory / name, "x\n", secret_file=True)
    _write_runtime_file(
        run.override_file,
        json.dumps(_generated_override(run), indent=2, sort_keys=True) + "\n",
    )


def _render_and_validate_compose(
    run: CellRun, *, manifest_required: bool
) -> dict[str, Any]:
    result = run.compose(
        ["config", "--format", "json"],
        timeout=30,
        manifest_required=manifest_required,
    )
    if result.returncode != 0:
        raise GuardDenied("Compose config rendering failed")
    try:
        config = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise GuardDenied("Compose config output was not JSON") from error
    if not isinstance(config, dict):
        raise GuardDenied("Compose config root was not an object")
    validate_compose_config(config)
    return config


def preflight(run: CellRun) -> dict[str, Any]:
    # This is deliberately first: fixture/root/Compose/cleanup binding must
    # fail before Git, Docker, directory preparation, acceptance, or resources.
    run.validate_fixture_contract()
    candidate_sha, clean = run.envelope.verify_git_worktree(
        allowed_untracked_prefixes=(
            "qa/production-cell/.runs/",
            "frontend/test-results/production-cell/",
        )
    )
    if not clean:
        raise GuardDenied("candidate worktree must be clean before image build")
    run.candidate_sha = candidate_sha
    run.receipt["git_sha"] = candidate_sha
    _prepare_runtime_files(run)
    run.docker_target = run.envelope.discover_and_attest_context()
    run.receipt["docker_target"] = run.docker_target.receipt()
    version = run.compose(
        ["version", "--short"],
        timeout=30,
        manifest_required=False,
    )
    if version.returncode != 0 or not version.stdout.strip():
        raise BlockedPrerequisite("Docker Compose plugin is unavailable")
    config = _render_and_validate_compose(run, manifest_required=False)
    browser_source = run.repo_root / "frontend" / "e2e" / "production-cell" / "run.mjs"
    validate_browser_source(browser_source.read_text(encoding="utf-8"))
    run.receipt["compose"] = {
        "project_name": run.run_id,
        "project_directory_sha256": sha256_bytes(str(run.qa_directory).encode("utf-8")),
        "files": [
            {"role": "base", "sha256": sha256_file(run.base_compose)},
            {"role": "generated_override", "sha256": sha256_file(run.override_file)},
        ],
        "config_sha256": sha256_bytes(canonical_json(config)),
        "network_name": "cell",
    }
    return {
        "schema": "microsched.qa025.preflight.v1",
        "run_id": run.run_id,
        "git_sha": candidate_sha,
        "worktree_clean": True,
        "docker_executable_sha256": run.envelope.receipt.executable_sha256,
        "git_executable_sha256": run.envelope.git_executable_sha256,
        "sanitized_env_keys_sha256": run.envelope.receipt.env_keys_sha256,
        "docker_target": run.docker_target.receipt(),
        "compose_version": version.stdout.decode("utf-8", errors="replace").strip(),
        "compose_config_sha256": run.receipt["compose"]["config_sha256"],
        "resource_count": 0,
    }


def _create_manifest(run: CellRun) -> None:
    assert run.docker_target is not None
    payload = {
        "schema": MANIFEST_SCHEMA,
        "run_id": run.run_id,
        "project_name": run.run_id,
        "git_sha": run.candidate_sha,
        "docker_executable_sha256": run.envelope.receipt.executable_sha256,
        "daemon_identity_sha256": run.docker_target.daemon_identity_sha256,
        "daemon": {
            "context_name": run.docker_target.context_name,
            "endpoint_kind": run.docker_target.endpoint_kind,
            "endpoint_sha256": run.docker_target.endpoint_sha256,
            "daemon_id": run.docker_target.daemon_id,
            "server_version": run.docker_target.server_version,
            "os_type": run.docker_target.os_type,
        },
        "compose": {
            "project_directory": str(run.qa_directory),
            "files": [
                {
                    "path": str(run.base_compose),
                    "sha256": sha256_file(run.base_compose),
                },
                {
                    "path": str(run.override_file),
                    "sha256": sha256_file(run.override_file),
                },
            ],
        },
        "resources": run.resources,
    }
    write_manifest(run.manifest_path, payload)
    run.manifest_exists = True


def _generate_secrets(run: CellRun) -> None:
    owner_password = secrets.token_urlsafe(32)
    app_password = secrets.token_urlsafe(32)
    migrator_password = secrets.token_urlsafe(32)
    session_token = secrets.token_urlsafe(32)
    pin = f"{secrets.randbelow(1_000_000):06d}"
    aes_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    app_url = (
        f"postgresql://microsched_app:{quote(app_password, safe='')}@db:5432/microsched"
    )
    migrator_url = (
        "postgresql://microsched_migrator:"
        f"{quote(migrator_password, safe='')}@db:5432/microsched"
    )
    file_values = {
        "postgres_owner_password": owner_password,
        "app_password": app_password,
        "migrator_password": migrator_password,
        "migrator_url": migrator_url,
        "app_url": app_url,
        "aes_key": aes_key,
    }
    for name, value in file_values.items():
        _write_runtime_file(run.secret_directory / name, value + "\n", secret_file=True)
    run.secret_values = {
        "session_token": session_token,
        "pin": pin,
        "email": f"qa025-{secrets.token_hex(5)}@example.invalid",
    }


def _image_id(run: CellRun, tag: str) -> str:
    result = run.docker(["image", "inspect", "--format", "{{.Id}}", tag], timeout=30)
    image_id = result.stdout.decode("ascii", errors="replace").strip()
    if (
        result.returncode != 0
        or not image_id.startswith("sha256:")
        or len(image_id) != 71
    ):
        raise AssertionFailure("built image does not have an immutable sha256 ID")
    return image_id


def build_images_and_pull_database(run: CellRun) -> None:
    for service, tag in (
        ("db", run.image_tags["db"]),
        ("app", run.image_tags["app"]),
        ("bootstrap", run.image_tags["helper"]),
        ("browser", run.image_tags["browser"]),
    ):
        result = run.compose(["build", "--pull", service], timeout=BUILD_TIMEOUT)
        if result.returncode != 0:
            raise AssertionFailure(
                f"candidate image build failed for service {service}"
            )
        image_id = _image_id(run, tag)
        run.add_resource("images", image_id)
        if service == "app":
            run.app_image_id = image_id


def _sentinel_config_hash(run: CellRun, container_id: str) -> str:
    result = run.docker(
        ["inspect", "--format", "{{json .Config}}", container_id],
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionFailure("foreign sentinel could not be inspected")
    return sha256_bytes(result.stdout.strip())


def create_foreign_sentinel(run: CellRun) -> None:
    suffix = secrets.token_hex(4)
    project = f"msqa025-sentinel-{suffix}"
    network_name = f"{project}_cell"
    labels = [
        "--label",
        f"com.docker.compose.project={project}",
        "--label",
        f"com.microsched.qa025.run_id={project}",
    ]
    network = run.docker(
        ["network", "create", "--internal", *labels, network_name],
        timeout=30,
        mutable=True,
    )
    network_id = network.stdout.decode("ascii", errors="replace").strip()
    if network.returncode != 0 or not network_id:
        raise AssertionFailure("foreign sentinel network creation failed")
    container = run.docker(
        [
            "create",
            "--name",
            f"{project}-holder",
            "--network",
            network_name,
            *labels,
            BASE_DB_IMAGE,
            "sleep",
            "1800",
        ],
        timeout=30,
        mutable=True,
    )
    container_id = container.stdout.decode("ascii", errors="replace").strip()
    if container.returncode != 0 or not container_id:
        run.docker(["network", "rm", network_id], timeout=30, mutable=True)
        raise AssertionFailure("foreign sentinel container creation failed")
    resource_hash = sha256_bytes(canonical_json(sorted((container_id, network_id))))
    run.sentinel = Sentinel(
        project_name=project,
        container_id=container_id,
        network_id=network_id,
        config_sha256_before="0" * 64,
        resource_ids_sha256=resource_hash,
        project_name_sha256=sha256_bytes(project.encode("utf-8")),
    )
    run.sentinel.config_sha256_before = _sentinel_config_hash(run, container_id)
    started = run.docker(["start", container_id], timeout=30, mutable=True)
    if started.returncode != 0:
        raise AssertionFailure("foreign sentinel did not start")


def _compose_service_id(run: CellRun, service: str) -> str:
    result = run.compose(["ps", "-aq", service], timeout=30)
    values = [
        line.strip()
        for line in result.stdout.decode("ascii", errors="replace").splitlines()
        if line.strip()
    ]
    if result.returncode != 0 or len(values) != 1:
        raise AssertionFailure(
            f"service {service} did not produce exactly one container ID"
        )
    return values[0]


def create_service(run: CellRun, service: str) -> str:
    assert_migration_gate(run.migration_exit_code, service)
    result = run.compose(
        ["create", "--no-build", "--no-deps", service],
        timeout=SETUP_TIMEOUT,
    )
    if result.returncode != 0:
        raise AssertionFailure(f"service {service} could not be created")
    container_id = _compose_service_id(run, service)
    run.service_containers[service] = container_id
    run.add_resource("containers", container_id)
    if not run.resources["networks"]:
        network = run.docker(
            ["network", "inspect", "--format", "{{.Id}}", run.network_name],
            timeout=30,
        )
        network_id = network.stdout.decode("ascii", errors="replace").strip()
        if network.returncode != 0 or not network_id:
            raise AssertionFailure(
                "cell network was not created with the first service"
            )
        run.add_resource("networks", network_id)
    return container_id


def _container_state(run: CellRun, container_id: str) -> dict[str, Any]:
    result = run.docker(
        ["inspect", "--format", "{{json .State}}", container_id], timeout=30
    )
    if result.returncode != 0:
        raise AssertionFailure("recorded container could not be inspected")
    try:
        state = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise AssertionFailure("container state was not JSON") from error
    if not isinstance(state, dict):
        raise AssertionFailure("container state was not an object")
    return state


def start_one_shot(
    run: CellRun,
    service: str,
    *,
    input_payload: dict[str, Any] | None = None,
    timeout: float = SETUP_TIMEOUT,
) -> bytes:
    container_id = run.service_containers[service]
    args = ["start", "--attach"]
    input_bytes = None
    if input_payload is not None:
        args.append("--interactive")
        input_bytes = canonical_json(input_payload) + b"\n"
    args.append(container_id)
    result = run.docker(args, timeout=timeout, input_bytes=input_bytes, mutable=True)
    state = _container_state(run, container_id)
    exit_code = state.get("ExitCode")
    if result.returncode != 0 or exit_code != 0:
        raise AssertionFailure(f"one-shot service {service} exited nonzero")
    return result.stdout


def _record_migration_nonzero(run: CellRun, exit_code: int) -> None:
    """Persist the actual migration fault before blocking every dependent service."""

    if exit_code == 0:
        raise ValueError("migration fault receipt requires a nonzero exit code")
    run.migration_exit_code = exit_code
    run.receipt["migration_gate"].update(
        {
            "status": "FAIL_ASSERTION",
            "fault_case": "migration_nonzero",
            "exit_code": exit_code,
            "service_completed_successfully": False,
            "app_create_command_issued": False,
            "app_created_before_success": False,
            "app_container_created": False,
            "app_container_running": False,
        }
    )


def start_migration(run: CellRun) -> bytes:
    """Run migrate once and make its container exit code the gate receipt."""

    container_id = run.service_containers["migrate"]
    result = run.docker(
        ["start", "--attach", container_id], timeout=SETUP_TIMEOUT, mutable=True
    )
    state = _container_state(run, container_id)
    exit_code = state.get("ExitCode")
    if not isinstance(exit_code, int):
        raise AssertionFailure("migration container did not report an integer exit code")
    if exit_code != 0:
        _record_migration_nonzero(run, exit_code)
        raise AssertionFailure("migration service exited nonzero")
    if result.returncode != 0:
        raise AssertionFailure("migration attach command failed despite zero exit code")
    run.migration_exit_code = 0
    return result.stdout


def start_database(run: CellRun) -> None:
    container_id = run.service_containers["db"]
    result = run.docker(["start", container_id], timeout=30, mutable=True)
    if result.returncode != 0:
        raise AssertionFailure("throwaway database did not start")
    deadline = time.monotonic() + SETUP_TIMEOUT
    while time.monotonic() < deadline:
        state = _container_state(run, container_id)
        health = state.get("Health")
        if isinstance(health, dict) and health.get("Status") == "healthy":
            return
        if state.get("Running") is False:
            raise AssertionFailure("throwaway database exited before becoming healthy")
        time.sleep(1)
    raise subprocess.TimeoutExpired("db-health", SETUP_TIMEOUT)


def start_app(run: CellRun) -> None:
    container_id = run.service_containers["app"]
    started = run.docker(["start", container_id], timeout=30, mutable=True)
    if started.returncode != 0:
        raise AssertionFailure("candidate app container did not start")
    deadline = time.monotonic() + APP_READY_TIMEOUT
    while time.monotonic() < deadline:
        state = _container_state(run, container_id)
        health = state.get("Health")
        if isinstance(health, dict) and health.get("Status") == "healthy":
            return
        if state.get("Running") is False:
            raise AssertionFailure("candidate app exited before readiness")
        time.sleep(1)
    raise subprocess.TimeoutExpired("app-ready", APP_READY_TIMEOUT)


def _last_json_line(output: bytes, *, label: str) -> dict[str, Any]:
    for raw_line in reversed(output.decode("utf-8", errors="replace").splitlines()):
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AssertionFailure(f"{label} did not return a JSON result")


def run_browser(run: CellRun) -> dict[str, Any]:
    payload = {
        "candidate_sha": run.candidate_sha,
        "email": run.secret_values["email"],
        "fixture_labels": list(run.fixture_labels),
        "pin": run.secret_values["pin"],
        "prefix": f"[QA025:{run.run_id}]",
        "run_id": run.run_id,
        "session_token": run.secret_values["session_token"],
    }
    output = start_one_shot(
        run,
        "browser",
        input_payload=payload,
        timeout=BROWSER_TIMEOUT,
    )
    result = _last_json_line(output, label="browser smoke")
    if (
        result.get("status") != "PASS"
        or result.get("ready_commit") != run.candidate_sha
    ):
        raise AssertionFailure("browser smoke did not attest the candidate commit")
    if result.get("task_count") != 2 or result.get("note_count") != 1:
        raise AssertionFailure("browser smoke fixture counts are invalid")
    if result.get("service_worker_controlled") is not True:
        raise AssertionFailure("browser smoke had no controlling Service Worker")
    if result.get("outbound_requests") != 0:
        raise AssertionFailure("browser smoke attempted an outbound request")
    return result


def _inspect_container(run: CellRun, container_id: str) -> dict[str, Any]:
    result = run.docker(["inspect", container_id], timeout=30)
    if result.returncode != 0:
        raise AssertionFailure(
            "recorded service container is absent before attestation"
        )
    try:
        values = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise AssertionFailure("container inspect output was not JSON") from error
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], dict)
    ):
        raise AssertionFailure("container inspect cardinality is invalid")
    return values[0]


def attest_runtime(run: CellRun) -> None:
    if len(run.service_containers) != len(SERVICES):
        raise AssertionFailure("not all six cell services were created")
    network_id = run.resources["networks"][0]
    network = run.docker(["network", "inspect", network_id], timeout=30)
    try:
        network_values = json.loads(network.stdout.decode("utf-8"))
        network_object = network_values[0]
    except (json.JSONDecodeError, IndexError, TypeError) as error:
        raise AssertionFailure("cell network inspect output is invalid") from error
    if network.returncode != 0 or network_object.get("Internal") is not True:
        raise AssertionFailure("runtime cell network is not internal")

    networks_by_service: dict[str, int] = {}
    ports_by_service: dict[str, int] = {}
    for service in SERVICES:
        container = _inspect_container(run, run.service_containers[service])
        labels = container.get("Config", {}).get("Labels", {}) or {}
        if labels.get("com.docker.compose.project") != run.run_id:
            raise AssertionFailure(
                f"service {service} has a foreign Compose project label"
            )
        if labels.get("com.microsched.qa025.run_id") != run.run_id:
            raise AssertionFailure(f"service {service} has a foreign QA run label")
        bindings = container.get("HostConfig", {}).get("PortBindings") or {}
        runtime_ports = container.get("NetworkSettings", {}).get("Ports")
        assert_no_runtime_port_bindings(bindings, runtime_ports, service=service)
        runtime_networks = container.get("NetworkSettings", {}).get("Networks") or {}
        network_ids = {value.get("NetworkID") for value in runtime_networks.values()}
        if network_ids != {network_id}:
            raise AssertionFailure(
                f"service {service} is not isolated to the exact cell network"
            )
        ports_by_service[service] = 0
        networks_by_service[service] = len(network_ids)

    app = _inspect_container(run, run.service_containers["app"])
    app_env = {
        entry.partition("=")[0].upper()
        for entry in app.get("Config", {}).get("Env", [])
        if isinstance(entry, str)
    }
    if app_env & {"NEON_OWNER_URL", "NEON_MIGRATOR_URL", "MIGRATOR_URL"}:
        raise AssertionFailure(
            "app container received an owner or migrator environment key"
        )
    migrate_state = _container_state(run, run.service_containers["migrate"])
    bootstrap_state = _container_state(run, run.service_containers["bootstrap"])
    if migrate_state.get("Running") is not False or migrate_state.get("ExitCode") != 0:
        raise AssertionFailure("migrator was not a successful exited one-shot")
    if (
        bootstrap_state.get("Running") is not False
        or bootstrap_state.get("ExitCode") != 0
    ):
        raise AssertionFailure("owner bootstrap was not a successful exited one-shot")
    run.receipt["safety"].update(
        {
            "browser_origin": "runner-loopback:<redacted-ephemeral-port>",
            "ports_by_service": ports_by_service,
            "total_ports_published": 0,
            "networks_by_service": networks_by_service,
            "network_count": 1,
            "network_internal": True,
            "network_id_sha256": sha256_bytes(network_id.encode("ascii")),
            "unexpected_networks": 0,
            "env_file_disabled": True,
            "outbound_requests": 0,
        }
    )


def _resource_labels(run: CellRun, kind: str, resource_id: str) -> dict[str, str]:
    if kind == "containers":
        args = ["inspect", "--format", "{{json .Config.Labels}}", resource_id]
    elif kind == "networks":
        args = ["network", "inspect", "--format", "{{json .Labels}}", resource_id]
    elif kind == "volumes":
        args = ["volume", "inspect", "--format", "{{json .Labels}}", resource_id]
    elif kind == "images":
        args = ["image", "inspect", "--format", "{{json .Config.Labels}}", resource_id]
    else:
        raise CleanupGuardDenied(f"unsupported cleanup resource kind: {kind}")
    result = run.docker(args, timeout=30)
    if result.returncode != 0:
        raise CleanupGuardDenied(f"manifest resource is absent before cleanup: {kind}")
    try:
        labels = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise CleanupGuardDenied("resource labels were not JSON") from error
    if not isinstance(labels, dict):
        raise CleanupGuardDenied("resource labels were not an object")
    return {str(key): str(value) for key, value in labels.items()}


def _verify_cleanup_ownership(run: CellRun, payload: dict[str, Any]) -> None:
    for kind in ("containers", "networks", "volumes", "images"):
        for resource_id in payload["resources"][kind]:
            labels = _resource_labels(run, kind, resource_id)
            if labels.get("com.docker.compose.project") != run.run_id:
                raise CleanupGuardDenied(
                    "manifest resource has a foreign Compose project label"
                )
            if labels.get("com.microsched.qa025.run_id") != run.run_id:
                raise CleanupGuardDenied("manifest resource has a foreign QA run label")


def _resource_absent(run: CellRun, kind: str, resource_id: str) -> bool:
    commands = {
        "containers": ["inspect", resource_id],
        "networks": ["network", "inspect", resource_id],
        "volumes": ["volume", "inspect", resource_id],
        "images": ["image", "inspect", resource_id],
    }
    return run.docker(commands[kind], timeout=30).returncode != 0


def _verify_sentinel_survived(run: CellRun) -> None:
    sentinel = run.sentinel
    if sentinel is None:
        return
    state = _container_state(run, sentinel.container_id)
    if state.get("Running") is not True:
        raise AssertionFailure("foreign sentinel did not survive cell cleanup")
    sentinel.config_sha256_after = _sentinel_config_hash(run, sentinel.container_id)
    if sentinel.config_sha256_after != sentinel.config_sha256_before:
        raise AssertionFailure(
            "foreign sentinel config hash changed during cell cleanup"
        )
    sentinel.survived = True


def cleanup_cell(run: CellRun) -> None:
    if not run.manifest_exists or run.docker_target is None:
        return
    started = time.monotonic()
    with locked_run_directory(run.run_directory):
        payload = run._verify_manifest()
        run.envelope.reattest_context(run.docker_target)
        payload = run._verify_manifest()
        _verify_cleanup_ownership(run, payload)
        run.cleanup_delete_permitted = True
        if time.monotonic() - started > CLEANUP_TIMEOUT:
            raise subprocess.TimeoutExpired("cleanup-attestation", CLEANUP_TIMEOUT)

        for container_id in reversed(payload["resources"]["containers"]):
            state = _container_state(run, container_id)
            if state.get("Running") is True:
                stopped = run.docker(
                    ["stop", "--time", "5", container_id],
                    timeout=15,
                    mutable=True,
                )
                run.cleanup_delete_count += 1
                if stopped.returncode != 0:
                    raise CellError("CLEANUP_TIMEOUT", "exact container stop failed")
            removed = run.docker(["rm", container_id], timeout=30, mutable=True)
            run.cleanup_delete_count += 1
            if removed.returncode != 0:
                raise CellError("CLEANUP_TIMEOUT", "exact container removal failed")
        for volume_id in payload["resources"]["volumes"]:
            removed = run.docker(["volume", "rm", volume_id], timeout=30, mutable=True)
            run.cleanup_delete_count += 1
            if removed.returncode != 0:
                raise CellError("CLEANUP_TIMEOUT", "exact volume removal failed")
        for network_id in payload["resources"]["networks"]:
            removed = run.docker(
                ["network", "rm", network_id], timeout=30, mutable=True
            )
            run.cleanup_delete_count += 1
            if removed.returncode != 0:
                raise CellError("CLEANUP_TIMEOUT", "exact network removal failed")
        for image_id in payload["resources"]["images"]:
            removed = run.docker(["image", "rm", image_id], timeout=60, mutable=True)
            run.cleanup_delete_count += 1
            if removed.returncode != 0:
                raise CellError("CLEANUP_TIMEOUT", "exact image removal failed")

        residuals = {
            kind: sum(
                not _resource_absent(run, kind, resource_id)
                for resource_id in payload["resources"][kind]
            )
            for kind in ("containers", "networks", "volumes", "images")
        }
        try:
            assert_zero_residuals(residuals)
        except AssertionFailure as error:
            raise CellError("CLEANUP_TIMEOUT", str(error)) from error
        _verify_sentinel_survived(run)
        manifest_hash = sha256_bytes(canonical_json(payload))
        run.receipt["cleanup"].update(
            {
                "status": "PASS",
                "manifest_verified": True,
                "manifest_schema": MANIFEST_SCHEMA,
                "manifest_sha256": manifest_hash,
                "manifest_resource_ids_sha256": resource_ids_sha256(payload),
                "run_id": run.run_id,
                "project_name": run.run_id,
                "daemon_identity_sha256": run.docker_target.daemon_identity_sha256,
                "delete_selection": "exact_manifest_resource_ids",
                "delete_command_count": run.cleanup_delete_count,
                "tamper_detected": False,
                "residual_counts": {**residuals, "helper_processes": 0},
            }
        )


def cleanup_sentinel(run: CellRun) -> None:
    sentinel = run.sentinel
    if sentinel is None or not run.cleanup_delete_permitted:
        return
    try:
        if not _resource_absent(run, "containers", sentinel.container_id):
            state = _container_state(run, sentinel.container_id)
            if state.get("Running") is True:
                run.docker(
                    ["stop", "--time", "5", sentinel.container_id],
                    timeout=15,
                    mutable=True,
                )
            run.docker(["rm", sentinel.container_id], timeout=30, mutable=True)
        if not _resource_absent(run, "networks", sentinel.network_id):
            run.docker(["network", "rm", sentinel.network_id], timeout=30, mutable=True)
        if not _resource_absent(run, "containers", sentinel.container_id):
            raise RuntimeError("sentinel container remains")
        if not _resource_absent(run, "networks", sentinel.network_id):
            raise RuntimeError("sentinel network remains")
        sentinel.separate_cleanup_status = "PASS"
    except Exception:  # noqa: BLE001 - sentinel cleanup must never mask the cell verdict
        sentinel.separate_cleanup_status = "NOT_RUN"


def remove_run_temp_directory(path: Path, *, label: str) -> None:
    """Delete an owned runtime directory and prove that it is gone."""

    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise CellError("INFRA_ERROR", f"{label} could not be removed") from error
    if path.exists():
        raise CellError("INFRA_ERROR", f"{label} remains after removal")


def remove_runtime_temp_directories(run: CellRun) -> None:
    """Attempt both cleanup paths; any residue makes the run non-PASS."""

    failures: list[str] = []
    for path, label in (
        (run.secret_directory, "secret directory"),
        (run.command_temp, "command temporary directory"),
    ):
        try:
            remove_run_temp_directory(path, label=label)
        except CellError as error:
            failures.append(str(error))
    if failures:
        raise CellError("INFRA_ERROR", "; ".join(failures))


def _finalize_sentinel_receipt(run: CellRun) -> None:
    sentinel = run.sentinel
    if sentinel is None:
        return
    run.receipt["cleanup"]["foreign_sentinel"] = {
        "project_name_sha256": sentinel.project_name_sha256,
        "resource_ids_sha256": sentinel.resource_ids_sha256,
        "config_sha256_before": sentinel.config_sha256_before,
        "config_sha256_after": sentinel.config_sha256_after
        or sentinel.config_sha256_before,
        "survived_cell_cleanup": sentinel.survived,
        "separate_cleanup_status": sentinel.separate_cleanup_status,
    }


def _apply_envelope_receipt(run: CellRun, status: str) -> None:
    run.receipt["command_envelope"].update(
        {
            "status": status,
            "docker_executable_sha256": run.envelope.receipt.executable_sha256,
            "git_executable_sha256": run.envelope.git_executable_sha256,
            "sanitized_env_keys_sha256": run.envelope.receipt.env_keys_sha256,
            "rejected_parent_variable_names": [],
            "docker_call_count": run.envelope.receipt.docker_call_count,
            "compose_call_count": run.envelope.receipt.compose_call_count,
            "all_calls_used_sanitized_env": True,
            "all_calls_used_explicit_context": True,
            "all_calls_used_absolute_executable": True,
            "all_compose_calls_used_absolute_owned_files": True,
            "all_compose_calls_used_exact_project": True,
            "all_calls_used_shell_false": True,
        }
    )


def run_full_cell(run: CellRun) -> int:
    final_error: CellError | None = None
    timeout_status: str | None = None
    try:
        run.phases.start("preflight")
        preflight(run)
        _create_manifest(run)
        run.phases.finish()

        run.phases.start("build")
        build_images_and_pull_database(run)
        create_foreign_sentinel(run)
        _generate_secrets(run)
        _render_and_validate_compose(run, manifest_required=True)
        run.phases.finish()

        run.phases.start("database")
        create_service(run, "db")
        start_database(run)
        run.phases.finish()

        run.phases.start("bootstrap")
        create_service(run, "bootstrap")
        start_one_shot(run, "bootstrap")
        run.phases.finish()

        run.phases.start("migrate")
        create_service(run, "migrate")
        migrate_output = start_migration(run)
        del migrate_output
        run.migration_exit_code = 0
        run.receipt["migration_gate"].update(
            {
                "status": "PASS",
                "fault_case": "none",
                "exit_code": 0,
                "service_completed_successfully": True,
                "app_create_command_issued": False,
                "app_created_before_success": False,
                "app_container_created": False,
                "app_container_running": False,
            }
        )
        run.phases.finish()

        run.phases.start("seed")
        create_service(run, "seed")
        seed_output = start_one_shot(
            run,
            "seed",
            input_payload={
                "session_token": run.secret_values["session_token"],
                "email": run.secret_values["email"],
            },
        )
        role_facts = _last_json_line(seed_output, label="role attestation")
        required_role_facts = (
            role_facts.get("status") == "PASS"
            and role_facts.get("current_user_app") is True
            and role_facts.get("tables_owned_by_migrator") is True
            and role_facts.get("app_dml") is True
            and role_facts.get("app_schema_create") is False
            and role_facts.get("ddl_denied") is True
            and role_facts.get("alembic_write_denied") is True
        )
        if not required_role_facts:
            raise AssertionFailure("database role attestation failed")
        run.receipt["roles"] = {
            "status": "PASS",
            "app": "microsched_app",
            "migrator": "microsched_migrator",
            "ddl_denied": True,
            "alembic_write_denied": True,
            "app_role_only": True,
        }
        run.phases.finish()

        run.phases.start("app_ready")
        create_service(run, "app")
        run.receipt["migration_gate"].update(
            {
                "app_create_command_issued": True,
                "app_container_created": True,
            }
        )
        start_app(run)
        run.receipt["migration_gate"]["app_container_running"] = True
        run.phases.finish()

        run.phases.start("browser")
        create_service(run, "browser")
        browser_result = run_browser(run)
        del browser_result
        attest_runtime(run)
        run.receipt["fixtures"].update(
            {"status": "PASS", "task_count": 2, "note_count": 1}
        )
        run.phases.finish()
    except subprocess.TimeoutExpired:
        timeout_status = timeout_status_for_phase(run.phases.current_name)
        final_error = CellError(timeout_status, "phase timeout")
        run.phases.fail_current(timeout_status, None)
    except CellError as error:
        final_error = error
        run.phases.fail_current(error.status, error.exit_code)
    except Exception as error:  # noqa: BLE001 - classify unknown infrastructure failures
        final_error = CellError("INFRA_ERROR", f"unexpected {type(error).__name__}")
        run.phases.fail_current("INFRA_ERROR", 60)
    finally:
        run.phases.start("cleanup")
        cleanup_succeeded = False
        try:
            cleanup_cell(run)
            cleanup_succeeded = True
        except subprocess.TimeoutExpired:
            cleanup_timeout_status = timeout_status_for_phase("cleanup")
            final_error = CellError(cleanup_timeout_status, "cleanup timeout")
            run.receipt["cleanup"]["status"] = cleanup_timeout_status
        except CleanupGuardDenied:
            final_error = CleanupGuardDenied(
                "cleanup manifest/daemon/resource guard denied"
            )
            run.receipt["cleanup"].update(
                {"status": "CLEANUP_GUARD_DENIED", "tamper_detected": True}
            )
        except CellError as error:
            final_error = error
            run.receipt["cleanup"]["status"] = error.status
        except Exception as error:  # noqa: BLE001 - cleanup must emit a stable taxonomy
            final_error = CellError("INFRA_ERROR", f"cleanup {type(error).__name__}")
            run.receipt["cleanup"]["status"] = "INFRA_ERROR"
        finally:
            cleanup_sentinel(run)
            if (
                cleanup_succeeded
                and run.sentinel is not None
                and run.sentinel.separate_cleanup_status != "PASS"
            ):
                final_error = CellError("INFRA_ERROR", "foreign sentinel cleanup failed")
                cleanup_succeeded = False
                run.receipt["cleanup"]["status"] = "INFRA_ERROR"
            try:
                remove_runtime_temp_directories(run)
            except CellError as error:
                # A secret/temp deletion failure is a terminal cleanup failure;
                # it cannot leave a PASS receipt even if Docker cleanup passed.
                if cleanup_succeeded:
                    final_error = error
                    cleanup_succeeded = False
                    run.receipt["cleanup"]["status"] = error.status
            _finalize_sentinel_receipt(run)
            run.secret_values.clear()
            if run.phases.current_name == "cleanup":
                if cleanup_succeeded:
                    run.phases.finish()
                else:
                    failure = final_error or CellError("INFRA_ERROR", "cleanup failed")
                    run.phases.fail_current(failure.status, failure.exit_code)

    success = final_error is None and run.receipt["cleanup"]["status"] == "PASS"
    run.receipt["final_status"] = (
        "PASS" if success else (final_error.status if final_error else "INFRA_ERROR")
    )
    run.receipt["image_id"] = run.app_image_id
    run.receipt["phases"] = run.phases.phases
    run.receipt["ended_at"] = utc_now()
    if success:
        for acceptance_id in (
            "025-SAFE-01",
            "025-SAFE-02",
            "025-SAFE-03",
            "025-SAFE-04",
            "025-SAFE-05",
            "025-SAFE-06",
            "025-SAFE-07",
            "025-CELL-01",
            "025-CELL-02",
            "025-CELL-03",
            "025-CELL-04",
            "025-CELL-05",
            "025-CELL-06",
            "025-RED-01",
        ):
            run.receipt["acceptance"][acceptance_id] = "PASS"
        _apply_envelope_receipt(run, "PASS")
    else:
        _apply_envelope_receipt(run, run.receipt["final_status"])
    atomic_write_receipt(run.receipt_path, run.receipt)
    return 0 if success else final_error.exit_code if final_error else 60


def make_run(
    repo_root: Path, parent_env: dict[str, str], run_id: str | None = None
) -> CellRun:
    selected_run_id = validate_run_id(run_id or new_run_id())
    labels = fixture_label_ledger(selected_run_id)
    fixture_prefix = f"[QA025:{selected_run_id}]"
    validate_fixture_identity_bindings(
        run_id=selected_run_id,
        project_name=selected_run_id,
        cleanup_run_id=selected_run_id,
        cleanup_project_name=selected_run_id,
        fixture_prefix=fixture_prefix,
        fixture_labels=labels,
    )
    qa_directory = repo_root / "qa" / "production-cell"
    run_directory = qa_directory / ".runs" / selected_run_id
    receipt_directory = (
        repo_root / "frontend" / "test-results" / "production-cell" / selected_run_id
    )
    run_directory.mkdir(parents=True, exist_ok=False)
    secret_directory = run_directory / "secrets"
    command_temp = run_directory / "command-temp"
    secret_directory.mkdir()
    command_temp.mkdir()
    started_at = utc_now()
    receipt = initial_receipt(selected_run_id, started_at)
    envelope = CommandEnvelope(repo_root, qa_directory, parent_env, command_temp)
    return CellRun(
        repo_root=repo_root,
        qa_directory=qa_directory,
        run_id=selected_run_id,
        run_directory=run_directory,
        secret_directory=secret_directory,
        command_temp=command_temp,
        override_file=run_directory / "compose.generated.json",
        receipt_path=receipt_directory / "receipt.json",
        manifest_path=run_directory / "run-manifest.json",
        envelope=envelope,
        receipt=receipt,
        fixture_labels=labels,
    )


def run_preflight_only(repo_root: Path, parent_env: dict[str, str]) -> int:
    run = make_run(repo_root, parent_env)
    try:
        run.phases.start("preflight")
        try:
            result = preflight(run)
        except subprocess.TimeoutExpired:
            error = CellError("SETUP_TIMEOUT", "preflight timeout")
        except CellError as caught:
            error = caught
        except Exception as caught:  # noqa: BLE001 - stable preflight taxonomy
            error = CellError("INFRA_ERROR", f"unexpected {type(caught).__name__}")
        else:
            run.phases.finish()
            preflight_path = run.run_directory / "preflight.json"
            _write_runtime_file(
                preflight_path, json.dumps(result, sort_keys=True) + "\n"
            )
            print(
                f"preflight=PASS run_id={run.run_id} resource_count=0 "
                f"git_sha={run.candidate_sha}"
            )
            return 0

        run.phases.fail_current(error.status, error.exit_code)
        run.receipt["final_status"] = error.status
        run.receipt["phases"] = run.phases.phases
        run.receipt["ended_at"] = utc_now()
        _apply_envelope_receipt(run, error.status)
        atomic_write_receipt(run.receipt_path, run.receipt)
        print(
            f"status={error.status} exit={error.exit_code} resource_count=0 "
            f"receipt_path=frontend/test-results/production-cell/{run.run_id}/receipt.json"
        )
        return error.exit_code
    finally:
        remove_runtime_temp_directories(run)


def write_guard_receipt(
    repo_root: Path,
    run_id: str,
    rejected_names: list[str],
) -> Path:
    started_at = utc_now()
    receipt = initial_receipt(run_id, started_at)
    receipt["final_status"] = "GUARD_DENIED"
    receipt["phases"] = [
        {
            "name": "preflight",
            "status": "GUARD_DENIED",
            "duration_ms": 0,
            "exit_code": 40,
        }
    ]
    receipt["command_envelope"]["status"] = "GUARD_DENIED"
    receipt["command_envelope"]["rejected_parent_variable_names"] = rejected_names
    receipt["acceptance"]["025-SAFE-01"] = "GUARD_DENIED"
    receipt["acceptance"]["025-SAFE-07"] = "GUARD_DENIED"
    receipt["ended_at"] = utc_now()
    path = (
        repo_root
        / "frontend"
        / "test-results"
        / "production-cell"
        / run_id
        / "receipt.json"
    )
    atomic_write_receipt(path, receipt)
    return path


def validate_final_receipt(repo_root: Path, receipt: dict[str, Any]) -> None:
    schema_path = repo_root / "agent-tasks" / "025-qa-receipt.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_receipt_object(schema, receipt)


def guard_or_receipt(
    repo_root: Path, parent_env: dict[str, str], run_id: str
) -> Path | None:
    try:
        guard_parent_environment(parent_env)
    except GuardDenied:
        from contract import denied_parent_variable_names

        rejected = denied_parent_variable_names(parent_env)
        return write_guard_receipt(repo_root, run_id, rejected)
    return None


def verify_cleanup_receipt(
    repo_root: Path,
    parent_env: dict[str, str],
    receipt_path: Path,
) -> None:
    artifact_root = (
        repo_root / "frontend" / "test-results" / "production-cell"
    ).resolve()
    try:
        resolved_receipt = receipt_path.resolve(strict=True)
        relative = resolved_receipt.relative_to(artifact_root)
    except (OSError, ValueError) as error:
        raise GuardDenied(
            "cleanup receipt must be inside the QA025 artifact root"
        ) from error
    if (
        resolved_receipt.is_symlink()
        or relative.name != "receipt.json"
        or len(relative.parts) != 2
    ):
        raise GuardDenied("cleanup receipt path shape is invalid")
    receipt = read_receipt(resolved_receipt)
    validate_final_receipt(repo_root, receipt)
    run_id = receipt.get("run_id")
    if not isinstance(run_id, str) or run_id != relative.parts[0]:
        raise GuardDenied("cleanup receipt run_id/path binding mismatch")
    if receipt.get("cleanup", {}).get("status") != "PASS":
        raise AssertionFailure(
            "cleanup receipt does not claim a completed exact-ID cleanup"
        )
    manifest_path = (
        repo_root / "qa" / "production-cell" / ".runs" / run_id / "run-manifest.json"
    )
    payload = read_verified_manifest(manifest_path)
    expected_manifest_hash = sha256_bytes(canonical_json(payload))
    if receipt["cleanup"]["manifest_sha256"] != expected_manifest_hash:
        raise CleanupGuardDenied("cleanup receipt manifest hash mismatch")
    if receipt["cleanup"]["manifest_resource_ids_sha256"] != resource_ids_sha256(
        payload
    ):
        raise CleanupGuardDenied("cleanup receipt resource inventory hash mismatch")
    qa_directory = repo_root / "qa" / "production-cell"
    command_temp = (
        repo_root / "qa" / "production-cell" / ".runs" / run_id / "verify-temp"
    )
    command_temp.mkdir(parents=True, exist_ok=False)
    try:
        envelope = CommandEnvelope(repo_root, qa_directory, parent_env, command_temp)
        target = envelope.discover_and_attest_context()
        verify_manifest_bindings(
            payload,
            run_id=run_id,
            project_name=run_id,
            daemon_identity_sha256=target.daemon_identity_sha256,
            git_sha=receipt["git_sha"],
            docker_executable_sha256=envelope.receipt.executable_sha256,
            project_directory=qa_directory,
            compose_files=(
                qa_directory / "compose.yaml",
                repo_root
                / "qa"
                / "production-cell"
                / ".runs"
                / run_id
                / "compose.generated.json",
            ),
        )
        receipt_target = receipt.get("docker_target")
        if not isinstance(receipt_target, dict):
            raise AssertionFailure("cleanup receipt has no Docker target")
        if (
            receipt_target.get("daemon_identity_sha256")
            != target.daemon_identity_sha256
        ):
            raise CleanupGuardDenied("cleanup verification reached a different daemon")
        commands = {
            "containers": lambda item: ["inspect", item],
            "networks": lambda item: ["network", "inspect", item],
            "volumes": lambda item: ["volume", "inspect", item],
            "images": lambda item: ["image", "inspect", item],
        }
        residuals: dict[str, int] = {}
        for kind, values in payload["resources"].items():
            residuals[kind] = sum(
                envelope.run_docker(commands[kind](resource_id), timeout=30).returncode
                == 0
                for resource_id in values
            )
        if any(residuals.values()):
            raise AssertionFailure(
                "verified manifest still has a residual Docker resource"
            )
    finally:
        shutil.rmtree(command_temp, ignore_errors=True)
