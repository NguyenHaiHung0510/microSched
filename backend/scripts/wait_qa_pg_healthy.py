"""Wait for the exact run-scoped PG18 container to become safely usable."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

from scripts.qa_contracts import QaContractError, validate_run_id

PGVECTOR_DIGEST_RE = re.compile(r"pgvector/pgvector@sha256:([0-9a-f]{64})\Z")
POLL_INTERVAL_SECONDS = 1.0
INSPECT_TIMEOUT_SECONDS = 10


def _expected_image_digest(expected_image: str) -> str:
    match = PGVECTOR_DIGEST_RE.fullmatch(expected_image)
    if match is None:
        raise QaContractError("FAIL_P0_PG_IMAGE_BINDING")
    return match.group(1)


def _validate_expected_resources(
    *, run_id: str, network: str, pg_container: str, expected_image: str
) -> str:
    validate_run_id(run_id)
    if network != f"microsched-qa-{run_id}":
        raise QaContractError("FAIL_P0_PG_NETWORK_BINDING")
    if pg_container != f"microsched-qa-pg-{run_id}":
        raise QaContractError("FAIL_P0_PG_CONTAINER_BINDING")
    return _expected_image_digest(expected_image)


def _docker_inspect(kind: str, target: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["docker", kind, "inspect", target],
            check=False,
            capture_output=True,
            text=True,
            timeout=INSPECT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise QaContractError("BLOCK_DOCKER_INSPECT") from error
    if completed.returncode != 0:
        raise QaContractError("BLOCK_DOCKER_INSPECT")
    try:
        inspected = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise QaContractError("FAIL_P0_PG_INSPECT_SHAPE") from error
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise QaContractError("FAIL_P0_PG_INSPECT_SHAPE")
    snapshot = inspected[0]
    if not isinstance(snapshot, dict):
        raise QaContractError("FAIL_P0_PG_INSPECT_SHAPE")
    return snapshot


def _docker_container_inspect(pg_container: str) -> dict[str, Any]:
    return _docker_inspect("container", pg_container)


def _docker_image_inspect(expected_image: str) -> dict[str, Any]:
    return _docker_inspect("image", expected_image)


def _required_mapping(value: Any, *, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QaContractError(code)
    return value


def _published_loopback_port(snapshot: dict[str, Any]) -> int:
    network_settings = _required_mapping(
        snapshot.get("NetworkSettings"), code="FAIL_P0_PG_NETWORK_BINDING"
    )
    ports = _required_mapping(network_settings.get("Ports"), code="FAIL_P0_PG_PORT_BINDING")
    if set(ports) != {"5432/tcp"}:
        raise QaContractError("FAIL_P0_PG_PORT_BINDING")
    bindings = ports["5432/tcp"]
    if not isinstance(bindings, list) or len(bindings) != 1:
        raise QaContractError("FAIL_P0_PG_PORT_BINDING")
    binding = _required_mapping(bindings[0], code="FAIL_P0_PG_PORT_BINDING")
    if set(binding) != {"HostIp", "HostPort"} or binding.get("HostIp") != "127.0.0.1":
        raise QaContractError("FAIL_P0_PG_PORT_BINDING")
    host_port = binding.get("HostPort")
    if not isinstance(host_port, str) or not host_port.isdecimal():
        raise QaContractError("FAIL_P0_PG_PORT_BINDING")
    port = int(host_port)
    if not 1 <= port <= 65535:
        raise QaContractError("FAIL_P0_PG_PORT_BINDING")
    return port


def validate_pg_snapshot(
    snapshot: dict[str, Any],
    *,
    run_id: str,
    network: str,
    pg_container: str,
    expected_image: str,
    expected_image_id: str,
) -> int | None:
    """Return the host port when healthy, or None only while health is starting."""
    _validate_expected_resources(
        run_id=run_id,
        network=network,
        pg_container=pg_container,
        expected_image=expected_image,
    )
    config = _required_mapping(snapshot.get("Config"), code="FAIL_P0_PG_INSPECT_SHAPE")
    labels = _required_mapping(config.get("Labels"), code="FAIL_P0_PG_LABEL_BINDING")
    network_settings = _required_mapping(
        snapshot.get("NetworkSettings"), code="FAIL_P0_PG_NETWORK_BINDING"
    )
    networks = _required_mapping(
        network_settings.get("Networks"), code="FAIL_P0_PG_NETWORK_BINDING"
    )
    if snapshot.get("Name") != f"/{pg_container}":
        raise QaContractError("FAIL_P0_PG_CONTAINER_BINDING")
    if labels.get("microsched.qa.run_id") != run_id:
        raise QaContractError("FAIL_P0_PG_LABEL_BINDING")
    if set(networks) != {network}:
        raise QaContractError("FAIL_P0_PG_NETWORK_BINDING")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_id):
        raise QaContractError("FAIL_P0_PG_IMAGE_BINDING")
    if snapshot.get("Image") != expected_image_id or config.get("Image") != expected_image:
        raise QaContractError("FAIL_P0_PG_IMAGE_BINDING")

    state = _required_mapping(snapshot.get("State"), code="FAIL_P0_PG_STATE_SHAPE")
    status = state.get("Status")
    if (
        status in {"exited", "dead", "removing"}
        or state.get("Dead") is True
        or (state.get("Running") is False and status != "created")
    ):
        raise QaContractError("FAIL_P0_PG_TERMINAL_STATE")
    if state.get("OOMKilled") is not False or state.get("Restarting") is not False:
        raise QaContractError("FAIL_P0_PG_UNSAFE_STATE")
    if status != "running" or state.get("Running") is not True:
        raise QaContractError("FAIL_P0_PG_NOT_RUNNING")
    try:
        exit_code = int(state.get("ExitCode"))
    except (TypeError, ValueError) as error:
        raise QaContractError("FAIL_P0_PG_STATE_SHAPE") from error
    if exit_code != 0:
        raise QaContractError("FAIL_P0_PG_TERMINAL_STATE")

    port = _published_loopback_port(snapshot)
    health = _required_mapping(state.get("Health"), code="FAIL_P0_PG_HEALTH_SHAPE")
    health_status = health.get("Status")
    if health_status == "starting":
        return None
    if health_status != "healthy":
        raise QaContractError("FAIL_P0_PG_UNHEALTHY")
    return port


def validate_image_snapshot(snapshot: dict[str, Any], *, expected_image: str) -> str:
    _expected_image_digest(expected_image)
    image_id = snapshot.get("Id")
    repo_digests = snapshot.get("RepoDigests")
    if (
        not isinstance(image_id, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        or not isinstance(repo_digests, list)
        or expected_image not in repo_digests
    ):
        raise QaContractError("FAIL_P0_PG_IMAGE_BINDING")
    return image_id


def inspect_healthy_target(
    *, run_id: str, network: str, pg_container: str, expected_image: str
) -> int:
    """Revalidate an already-healthy target immediately before dependent work."""
    expected_image_id = validate_image_snapshot(
        _docker_image_inspect(expected_image), expected_image=expected_image
    )
    port = validate_pg_snapshot(
        _docker_container_inspect(pg_container),
        run_id=run_id,
        network=network,
        pg_container=pg_container,
        expected_image=expected_image,
        expected_image_id=expected_image_id,
    )
    if port is None:
        raise QaContractError("FAIL_P0_PG_NOT_HEALTHY")
    return port


def wait_for_healthy(
    *,
    run_id: str,
    network: str,
    pg_container: str,
    expected_image: str,
    timeout_seconds: int,
    container_inspect_fn: Callable[[str], dict[str, Any]] = _docker_container_inspect,
    image_inspect_fn: Callable[[str], dict[str, Any]] = _docker_image_inspect,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> int:
    if not 1 <= timeout_seconds <= 300:
        raise QaContractError("FAIL_P0_PG_HEALTH_TIMEOUT_BOUND")
    expected_image_id = validate_image_snapshot(
        image_inspect_fn(expected_image), expected_image=expected_image
    )
    deadline = monotonic_fn() + timeout_seconds
    while True:
        port = validate_pg_snapshot(
            container_inspect_fn(pg_container),
            run_id=run_id,
            network=network,
            pg_container=pg_container,
            expected_image=expected_image,
            expected_image_id=expected_image_id,
        )
        if port is not None:
            return port
        if monotonic_fn() >= deadline:
            raise QaContractError("FAIL_P0_PG_HEALTH_TIMEOUT")
        sleep_fn(POLL_INTERVAL_SECONDS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--pg-container", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--timeout-seconds", required=True, type=int)
    return parser


def main() -> None:
    args = _parser().parse_args()
    port = wait_for_healthy(
        run_id=args.run_id,
        network=args.network,
        pg_container=args.pg_container,
        expected_image=args.expected_image,
        timeout_seconds=args.timeout_seconds,
    )
    digest = _validate_expected_resources(
        run_id=args.run_id,
        network=args.network,
        pg_container=args.pg_container,
        expected_image=args.expected_image,
    )
    print("qa_pg_health=PASS")
    print(f"run_id={args.run_id}")
    print(f"pg_container={args.pg_container}")
    print(f"network={args.network}")
    print(f"image_digest_sha256={digest}")
    print("published_host=127.0.0.1")
    print(f"published_port={port}")
    print("state=running")
    print("health=healthy")


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"qa_pg_health=FAIL code={error.code}")
        raise SystemExit(2) from error
