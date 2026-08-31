"""Create separate host/container synthetic env files without reading ambient DB config."""

from __future__ import annotations

import argparse
import secrets
import subprocess
from pathlib import Path

from sqlalchemy.engine import URL

from scripts.qa_contracts import QaContractError, find_repo_root, sha256_file, validate_run_id
from scripts.wait_qa_pg_healthy import inspect_healthy_target

ENV_NAMES = (
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
)


def _safe_resource(value: str, expected: str) -> None:
    if value != expected:
        raise QaContractError("FAIL_SYNTHETIC_RESOURCE_BINDING", value)


def _validate_candidate(candidate_sha: str) -> None:
    if len(candidate_sha) != 40 or any(ch not in "0123456789abcdef" for ch in candidate_sha):
        raise QaContractError("FAIL_CANDIDATE_SHA")


def _dsn(*, user: str, password: str | None, host: str, port: int, database: str) -> str:
    return URL.create(
        "postgresql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def build_env_pair(
    *,
    run_id: str,
    network: str,
    pg_container: str,
    candidate_sha: str,
    host_port: int,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build credentials once, then bind DSNs to their two explicit network contexts."""
    validate_run_id(run_id)
    _safe_resource(network, f"microsched-qa-{run_id}")
    _safe_resource(pg_container, f"microsched-qa-pg-{run_id}")
    _validate_candidate(candidate_sha)
    if not 1 <= host_port <= 65535:
        raise QaContractError("FAIL_SYNTHETIC_HOST_PORT")
    database = f"microsched_qa_{run_id.replace('-', '')[:20]}"
    migrator_password = secrets.token_urlsafe(32)
    app_password = secrets.token_urlsafe(32)
    shared = {
        "APP_ENV": "local",
        "ENCRYPTION_MASTER_KEY": secrets.token_urlsafe(32),
        "OAUTH_STATE_SECRET": secrets.token_urlsafe(32),
        "ENABLE_INPROCESS_CRON": "0",
        "GIT_SHA": candidate_sha,
        "QA_RUN_ID": run_id,
        "QA_PG_CONTAINER": pg_container,
        "QA_DOCKER_NETWORK": network,
        "QA_PG_HOST_PORT": str(host_port),
    }

    def context_values(*, context: str, host: str, port: int) -> dict[str, str]:
        return {
            **shared,
            "DATABASE_URL": _dsn(
                user="microsched_app",
                password=app_password,
                host=host,
                port=port,
                database=database,
            ),
            "NEON_MIGRATOR_URL": _dsn(
                user="microsched_migrator",
                password=migrator_password,
                host=host,
                port=port,
                database=database,
            ),
            "CI_PG_BOOTSTRAP_URL": _dsn(
                user="postgres", password=None, host=host, port=port, database=database
            ),
            "CI_APP_DATABASE_URL": _dsn(
                user="microsched_app",
                password=app_password,
                host=host,
                port=port,
                database=database,
            ),
            "QA_DSN_CONTEXT": context,
        }

    return (
        context_values(context="host-loopback", host="127.0.0.1", port=host_port),
        context_values(context="container-network", host=pg_container, port=5432),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--pg-container", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--host-output", required=True)
    parser.add_argument("--container-output", required=True)
    return parser


def _checked_output(path_value: str, run_id: str, filename: str) -> Path:
    output = Path(path_value).resolve(strict=False)
    expected = (find_repo_root() / "output" / "qa-runs" / run_id / filename).resolve(strict=False)
    if output != expected:
        raise QaContractError("FAIL_SYNTHETIC_ENV_SCOPE")
    if output.exists():
        raise QaContractError("FAIL_SYNTHETIC_ENV_EXISTS")
    return output


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{name}={values[name]}\n" for name in ENV_NAMES),
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    args = _parser().parse_args()
    host_output = _checked_output(args.host_output, args.run_id, "synthetic-host.env")
    container_output = _checked_output(
        args.container_output, args.run_id, "synthetic-container.env"
    )
    if host_output == container_output:
        raise QaContractError("FAIL_SYNTHETIC_ENV_PATH_COLLISION")
    candidate_sha = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=find_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    host_values, container_values = build_env_pair(
        run_id=args.run_id,
        network=args.network,
        pg_container=args.pg_container,
        candidate_sha=candidate_sha,
        host_port=inspect_healthy_target(
            run_id=args.run_id,
            network=args.network,
            pg_container=args.pg_container,
            expected_image=args.expected_image,
        ),
    )
    _write_env(host_output, host_values)
    try:
        _write_env(container_output, container_values)
    except Exception:
        host_output.unlink(missing_ok=True)
        raise
    print("synthetic_env_pair=created")
    print(f"host_env_file_sha256={sha256_file(host_output)}")
    print(f"container_env_file_sha256={sha256_file(container_output)}")


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"synthetic_env_guard={error.code}")
        raise SystemExit(2) from error
