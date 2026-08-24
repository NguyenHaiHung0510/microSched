"""Hash-bound run manifest and exact resource inventory for QA025."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from contract import CleanupGuardDenied, canonical_json, sha256_bytes, sha256_file

MANIFEST_SCHEMA = "microsched.qa025.run-manifest.v1"
RESOURCE_KINDS = ("containers", "networks", "volumes", "images")


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(value))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def manifest_wrapper(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical_payload = json.loads(canonical_json(payload))
    return {
        "payload": canonical_payload,
        "manifest_sha256": sha256_bytes(canonical_json(canonical_payload)),
    }


def write_manifest(path: Path, payload: Mapping[str, Any]) -> str:
    wrapper = manifest_wrapper(payload)
    _atomic_json_write(path, wrapper)
    return str(wrapper["manifest_sha256"])


def read_verified_manifest(path: Path) -> dict[str, Any]:
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CleanupGuardDenied("run manifest is missing or invalid JSON") from error
    if not isinstance(wrapper, dict) or set(wrapper) != {"payload", "manifest_sha256"}:
        raise CleanupGuardDenied("run manifest wrapper has unexpected fields")
    payload = wrapper.get("payload")
    supplied_hash = wrapper.get("manifest_sha256")
    if not isinstance(payload, dict) or not isinstance(supplied_hash, str):
        raise CleanupGuardDenied("run manifest wrapper types are invalid")
    expected_hash = sha256_bytes(canonical_json(payload))
    if supplied_hash != expected_hash:
        raise CleanupGuardDenied("run manifest hash mismatch")
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise CleanupGuardDenied("run manifest schema mismatch")
    resources = payload.get("resources")
    if not isinstance(resources, dict) or set(resources) != set(RESOURCE_KINDS):
        raise CleanupGuardDenied("run manifest resource inventory is invalid")
    for kind in RESOURCE_KINDS:
        values = resources[kind]
        if not isinstance(values, list) or any(
            not isinstance(item, str) for item in values
        ):
            raise CleanupGuardDenied(f"run manifest {kind} inventory is invalid")
        if len(values) != len(set(values)):
            raise CleanupGuardDenied(
                f"run manifest {kind} inventory contains duplicates"
            )
    return payload


def verify_manifest_bindings(
    payload: Mapping[str, Any],
    *,
    run_id: str,
    project_name: str,
    daemon_identity_sha256: str,
    git_sha: str | None = None,
    docker_executable_sha256: str | None = None,
    project_directory: Path | None = None,
    compose_files: tuple[Path, Path] | None = None,
) -> None:
    if payload.get("run_id") != run_id or payload.get("project_name") != project_name:
        raise CleanupGuardDenied("run manifest project/run binding mismatch")
    if payload.get("daemon_identity_sha256") != daemon_identity_sha256:
        raise CleanupGuardDenied("run manifest daemon identity mismatch")
    if git_sha is not None and payload.get("git_sha") != git_sha:
        raise CleanupGuardDenied("run manifest candidate SHA mismatch")
    if (
        docker_executable_sha256 is not None
        and payload.get("docker_executable_sha256") != docker_executable_sha256
    ):
        raise CleanupGuardDenied("run manifest Docker executable mismatch")
    compose = payload.get("compose")
    if not isinstance(compose, dict):
        raise CleanupGuardDenied("run manifest Compose binding is invalid")
    if project_directory is not None:
        try:
            recorded_project_directory = Path(
                str(compose.get("project_directory"))
            ).resolve(strict=True)
        except OSError as error:
            raise CleanupGuardDenied(
                "run manifest project directory is invalid"
            ) from error
        if recorded_project_directory != project_directory.resolve(strict=True):
            raise CleanupGuardDenied("run manifest project directory mismatch")
    files = compose.get("files")
    if not isinstance(files, list) or len(files) != 2:
        raise CleanupGuardDenied("run manifest must bind exactly two Compose files")
    resolved_files: list[Path] = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise CleanupGuardDenied("run manifest Compose file entry is invalid")
        path = Path(str(entry["path"]))
        if not path.is_file() or sha256_file(path) != entry["sha256"]:
            raise CleanupGuardDenied("run manifest Compose file hash mismatch")
        resolved_files.append(path.resolve(strict=True))
    if compose_files is not None and tuple(resolved_files) != tuple(
        path.resolve(strict=True) for path in compose_files
    ):
        raise CleanupGuardDenied("run manifest Compose file path mismatch")


def update_resources(path: Path, resources: Mapping[str, list[str]]) -> str:
    payload = read_verified_manifest(path)
    normalized: dict[str, list[str]] = {}
    for kind in RESOURCE_KINDS:
        values = resources.get(kind, [])
        normalized[kind] = sorted(set(values))
    payload["resources"] = normalized
    return write_manifest(path, payload)


def resource_ids_sha256(payload: Mapping[str, Any]) -> str:
    resources = payload.get("resources", {})
    return sha256_bytes(canonical_json(resources))


@contextmanager
def locked_run_directory(run_directory: Path) -> Iterator[None]:
    """Acquire a non-waiting cleanup lock owned by this exact run directory."""

    lock_path = run_directory / ".cleanup.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise CleanupGuardDenied(
            "run directory cleanup lock is already held"
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock_path.unlink(missing_ok=True)
