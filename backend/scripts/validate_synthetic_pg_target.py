"""Validate dual-context synthetic Postgres targets and write a credential-free receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sqlalchemy.engine import URL, make_url

from scripts.qa_contracts import (
    QaContractError,
    find_repo_root,
    load_json,
    scan_forbidden_environment,
    sha256_bytes,
    sha256_file,
    utc_now,
    validate_run_id,
    validate_schema,
)

ALLOWED_ENV_NAMES = {
    "APP_ENV",
    "DATABASE_URL",
    "NEON_MIGRATOR_URL",
    "CI_PG_BOOTSTRAP_URL",
    "CI_APP_DATABASE_URL",
    "ENCRYPTION_MASTER_KEY",
    "OAUTH_STATE_SECRET",
    "ENABLE_INPROCESS_CRON",
    "GIT_SHA",
    "QA_RUN_ID",
    "QA_PG_CONTAINER",
    "QA_DOCKER_NETWORK",
    "QA_DSN_CONTEXT",
    "QA_PG_HOST_PORT",
}
DSN_NAMES = (
    "CI_PG_BOOTSTRAP_URL",
    "NEON_MIGRATOR_URL",
    "CI_APP_DATABASE_URL",
    "DATABASE_URL",
)
FORBIDDEN_HOST_MARKERS = ("neon", "prod", "main", ".com", ".net", ".org")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            raise QaContractError("FAIL_SYNTHETIC_ENV_PARSE", str(line_number))
        name, value = raw.split("=", 1)
        if name in values or name not in ALLOWED_ENV_NAMES or not value:
            raise QaContractError("FAIL_SYNTHETIC_ENV_FIELD", name)
        values[name] = value
    if set(values) != ALLOWED_ENV_NAMES:
        raise QaContractError("FAIL_SYNTHETIC_ENV_SET")
    return values


def _docker_json(*args: str) -> list[dict]:
    completed = subprocess.run(["docker", *args], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise QaContractError("BLOCK_DOCKER_INSPECT", " ".join(args))
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise QaContractError("BLOCK_DOCKER_INSPECT_JSON") from error
    if not isinstance(value, list) or len(value) != 1:
        raise QaContractError("BLOCK_DOCKER_INSPECT_COUNT")
    return value


def _parse_targets(
    values: dict[str, str], *, expected_host: str, expected_port: int, expected_database: str
) -> tuple[dict[str, dict[str, object]], dict[str, URL]]:
    expected_users = {
        "CI_PG_BOOTSTRAP_URL": "postgres",
        "NEON_MIGRATOR_URL": "microsched_migrator",
        "CI_APP_DATABASE_URL": "microsched_app",
        "DATABASE_URL": "microsched_app",
    }
    targets: dict[str, dict[str, object]] = {}
    parsed_urls: dict[str, URL] = {}
    for name, expected_user in expected_users.items():
        try:
            url = make_url(values[name])
        except Exception:
            raise QaContractError("FAIL_P0_SYNTHETIC_DSN_PARSE", name) from None
        host = (url.host or "").lower()
        if host != expected_host or any(marker in host for marker in FORBIDDEN_HOST_MARKERS):
            raise QaContractError("FAIL_P0_SYNTHETIC_HOST", name)
        if (
            url.database != expected_database
            or url.username != expected_user
            or url.port != expected_port
        ):
            raise QaContractError("FAIL_P0_SYNTHETIC_DSN_BINDING", name)
        targets[name] = {
            "host": host,
            "port": expected_port,
            "database": url.database,
            "role": url.username,
        }
        parsed_urls[name] = url
    return targets, parsed_urls


def _validate_env_binding(
    values: dict[str, str],
    *,
    run_id: str,
    candidate_sha: str,
    network: str,
    pg_container: str,
    context: str,
    host_port: int,
) -> None:
    expected = {
        "APP_ENV": "local",
        "ENABLE_INPROCESS_CRON": "0",
        "GIT_SHA": candidate_sha,
        "QA_RUN_ID": run_id,
        "QA_PG_CONTAINER": pg_container,
        "QA_DOCKER_NETWORK": network,
        "QA_DSN_CONTEXT": context,
        "QA_PG_HOST_PORT": str(host_port),
    }
    if any(values[name] != value for name, value in expected.items()):
        raise QaContractError("FAIL_SYNTHETIC_ENV_BINDING", context)


def _docker_bindings(*, run_id: str, network: str, pg_container: str) -> tuple[int, dict[str, str]]:
    container = _docker_json("container", "inspect", pg_container)[0]
    if container.get("Name", "").lstrip("/") != pg_container:
        raise QaContractError("FAIL_P0_CONTAINER_NAME")
    labels = container.get("Config", {}).get("Labels") or {}
    if labels.get("microsched.qa.run_id") != run_id:
        raise QaContractError("FAIL_P0_CONTAINER_LABEL")
    networks = container.get("NetworkSettings", {}).get("Networks") or {}
    if set(networks) != {network}:
        raise QaContractError("FAIL_P0_CONTAINER_NETWORK")
    ports = container.get("NetworkSettings", {}).get("Ports") or {}
    bindings = ports.get("5432/tcp")
    if (
        not isinstance(bindings, list)
        or len(bindings) != 1
        or bindings[0].get("HostIp") != "127.0.0.1"
    ):
        raise QaContractError("FAIL_P0_CONTAINER_PORT_BINDING")
    try:
        host_port = int(bindings[0]["HostPort"])
    except (KeyError, TypeError, ValueError) as error:
        raise QaContractError("FAIL_P0_CONTAINER_PORT_BINDING") from error
    if not 1 <= host_port <= 65535:
        raise QaContractError("FAIL_P0_CONTAINER_PORT_BINDING")

    inspected_network = _docker_json("network", "inspect", network)[0]
    if inspected_network.get("Name") != network:
        raise QaContractError("FAIL_P0_NETWORK_NAME")
    network_labels = inspected_network.get("Labels") or {}
    if network_labels.get("microsched.qa.run_id") != run_id:
        raise QaContractError("FAIL_P0_NETWORK_LABEL")
    container_id = container.get("Id")
    network_id = inspected_network.get("Id")
    if not isinstance(container_id, str) or not container_id:
        raise QaContractError("FAIL_P0_CONTAINER_ID")
    if not isinstance(network_id, str) or not network_id:
        raise QaContractError("FAIL_P0_NETWORK_ID")
    return host_port, {
        "container_id_sha256": sha256_bytes(container_id.encode()),
        "network_id_sha256": sha256_bytes(network_id.encode()),
    }


def validate_target(
    *,
    run_id: str,
    candidate_sha: str,
    network: str,
    pg_container: str,
    host_env_file: Path,
    container_env_file: Path,
    inspect_docker: bool = True,
    inspected_host_port: int | None = None,
    inspected_ids: dict[str, str] | None = None,
    expected_run_dir: Path | None = None,
) -> dict[str, object]:
    validate_run_id(run_id)
    if network != f"microsched-qa-{run_id}" or pg_container != f"microsched-qa-pg-{run_id}":
        raise QaContractError("FAIL_SYNTHETIC_RESOURCE_BINDING")
    if len(candidate_sha) != 40 or any(ch not in "0123456789abcdef" for ch in candidate_sha):
        raise QaContractError("FAIL_CANDIDATE_SHA")
    run_dir = expected_run_dir or find_repo_root() / "output" / "qa-runs" / run_id
    expected_host_env = (run_dir / "synthetic-host.env").resolve(strict=False)
    expected_container_env = (run_dir / "synthetic-container.env").resolve(strict=False)
    if (
        host_env_file.resolve() != expected_host_env
        or container_env_file.resolve() != expected_container_env
    ):
        raise QaContractError("FAIL_SYNTHETIC_ENV_SCOPE")
    if host_env_file.resolve() == container_env_file.resolve():
        raise QaContractError("FAIL_SYNTHETIC_ENV_PATH_COLLISION")
    scan_forbidden_environment()
    host_values = load_env_file(host_env_file)
    container_values = load_env_file(container_env_file)
    if inspect_docker:
        host_port, docker_binding = _docker_bindings(
            run_id=run_id, network=network, pg_container=pg_container
        )
    else:
        if inspected_host_port is None or inspected_ids is None:
            raise QaContractError("FAIL_SYNTHETIC_INSPECT_FIXTURE")
        host_port, docker_binding = inspected_host_port, inspected_ids
    _validate_env_binding(
        host_values,
        run_id=run_id,
        candidate_sha=candidate_sha,
        network=network,
        pg_container=pg_container,
        context="host-loopback",
        host_port=host_port,
    )
    _validate_env_binding(
        container_values,
        run_id=run_id,
        candidate_sha=candidate_sha,
        network=network,
        pg_container=pg_container,
        context="container-network",
        host_port=host_port,
    )
    expected_database = f"microsched_qa_{run_id.replace('-', '')[:20]}"
    host_targets, host_urls = _parse_targets(
        host_values,
        expected_host="127.0.0.1",
        expected_port=host_port,
        expected_database=expected_database,
    )
    container_targets, container_urls = _parse_targets(
        container_values,
        expected_host=pg_container,
        expected_port=5432,
        expected_database=expected_database,
    )
    for name in DSN_NAMES:
        if host_urls[name].password != container_urls[name].password:
            raise QaContractError("FAIL_P0_SYNTHETIC_CREDENTIAL_CONTEXT", name)
    for name in ("ENCRYPTION_MASTER_KEY", "OAUTH_STATE_SECRET"):
        if host_values[name] != container_values[name]:
            raise QaContractError("FAIL_P0_SYNTHETIC_SECRET_CONTEXT", name)
    receipt = {
        "schema_version": "037-synthetic-dsn-receipt/v2",
        "run_id": run_id,
        "candidate_sha": candidate_sha,
        "network": network,
        "pg_container": pg_container,
        "host_binding": {
            "context": "host-loopback",
            "env_file_path": host_env_file.resolve().as_posix(),
            "env_file_sha256": sha256_file(host_env_file),
            "loopback_host": "127.0.0.1",
            "published_port": host_port,
            "targets": host_targets,
        },
        "container_binding": {
            "context": "container-network",
            "env_file_path": container_env_file.resolve().as_posix(),
            "env_file_sha256": sha256_file(container_env_file),
            "network_host": pg_container,
            "container_port": 5432,
            "targets": container_targets,
        },
        "docker_binding": docker_binding,
        "validated_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "dotenv_loaded": False,
        "process_db_env_present": False,
    }
    validate_schema(
        receipt,
        find_repo_root() / "qa" / "contracts" / "037" / "synthetic-dsn-receipt.schema.json",
        label="synthetic-dsn-receipt",
    )
    return receipt


def load_validated_receipt(
    *, receipt_path: Path, run_id: str, candidate_sha: str
) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
    receipt = load_json(receipt_path)
    validate_schema(
        receipt,
        find_repo_root() / "qa" / "contracts" / "037" / "synthetic-dsn-receipt.schema.json",
        label="synthetic-dsn-receipt",
    )
    if receipt["run_id"] != run_id or receipt["candidate_sha"] != candidate_sha:
        raise QaContractError("FAIL_SYNTHETIC_RECEIPT_BINDING")
    host_env = Path(receipt["host_binding"]["env_file_path"]).resolve(strict=True)
    container_env = Path(receipt["container_binding"]["env_file_path"]).resolve(strict=True)
    if sha256_file(host_env) != receipt["host_binding"]["env_file_sha256"]:
        raise QaContractError("FAIL_P0_SYNTHETIC_HOST_ENV_STALE")
    if sha256_file(container_env) != receipt["container_binding"]["env_file_sha256"]:
        raise QaContractError("FAIL_P0_SYNTHETIC_CONTAINER_ENV_STALE")
    fresh = validate_target(
        run_id=run_id,
        candidate_sha=candidate_sha,
        network=receipt["network"],
        pg_container=receipt["pg_container"],
        host_env_file=host_env,
        container_env_file=container_env,
    )
    for key in (
        "schema_version",
        "run_id",
        "candidate_sha",
        "network",
        "pg_container",
        "host_binding",
        "container_binding",
        "docker_binding",
        "dotenv_loaded",
        "process_db_env_present",
    ):
        if fresh[key] != receipt[key]:
            raise QaContractError("FAIL_P0_SYNTHETIC_RECEIPT_STALE", key)
    return receipt, load_env_file(host_env), load_env_file(container_env)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--pg-container", required=True)
    parser.add_argument("--host-env-file", required=True)
    parser.add_argument("--container-env-file", required=True)
    parser.add_argument("--receipt", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    receipt_path = Path(args.receipt).resolve(strict=False)
    if receipt_path.exists():
        raise QaContractError("FAIL_SYNTHETIC_RECEIPT_EXISTS")
    receipt = validate_target(
        run_id=args.run_id,
        candidate_sha=args.candidate_sha,
        network=args.network,
        pg_container=args.pg_container,
        host_env_file=Path(args.host_env_file).resolve(strict=True),
        container_env_file=Path(args.container_env_file).resolve(strict=True),
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("synthetic_dsn_provenance=PASS")
    print(f"receipt_sha256={sha256_file(receipt_path)}")


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"synthetic_dsn_guard={error.code}")
        raise SystemExit(2) from error
