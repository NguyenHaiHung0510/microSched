"""Revalidate a synthetic DSN receipt, replace DB env, then exec one PG command."""

from __future__ import annotations

import argparse
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from scripts.qa_contracts import QaContractError, find_repo_root, scan_forbidden_environment
from scripts.validate_synthetic_pg_target import load_validated_receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-dsn-receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha")
    parser.add_argument(
        "--pytest-use-validated-bootstrap-as-migrator",
        action="store_true",
        help=(
            "For the exact PG pytest command only, set NEON_MIGRATOR_URL to the "
            "already-validated CI_PG_BOOTSTRAP_URL. This flag accepts no URL."
        ),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


_EXACT_PYTEST_PG_COMMAND = ["uv", "run", "pytest", "-m", "pg"]
_DB_ENV_NAMES = {
    "DATABASE_URL",
    "NEON_MIGRATOR_URL",
    "CI_PG_BOOTSTRAP_URL",
    "CI_APP_DATABASE_URL",
}


def build_child_environment(
    *,
    validated_values: Mapping[str, str],
    command: list[str],
    use_validated_bootstrap_as_pytest_migrator: bool,
    process_environment: Mapping[str, str],
) -> dict[str, str]:
    """Build a sanitized child env with one exact, non-parameterized pytest elevation."""
    child_env = {
        key: value for key, value in process_environment.items() if key not in _DB_ENV_NAMES
    }
    child_env.update(validated_values)
    if use_validated_bootstrap_as_pytest_migrator:
        if command != _EXACT_PYTEST_PG_COMMAND:
            raise QaContractError("FAIL_PG_WRAPPER_PYTEST_ELEVATION_SCOPE", "command")
        bootstrap_url = validated_values.get("CI_PG_BOOTSTRAP_URL")
        if not bootstrap_url:
            raise QaContractError("FAIL_PG_WRAPPER_PYTEST_ELEVATION_SCOPE", "validated-target")
        child_env["NEON_MIGRATOR_URL"] = bootstrap_url
    return child_env


def main() -> None:
    args = _parser().parse_args()
    if not args.command or args.command[0] != "--" or len(args.command) < 2:
        raise SystemExit("FAIL_PG_WRAPPER_COMMAND")
    command = args.command[1:]
    if command[0].lower() in {"cmd", "cmd.exe", "powershell", "pwsh", "bash", "sh"}:
        raise SystemExit("FAIL_PG_WRAPPER_SHELL")
    scan_forbidden_environment()
    candidate_sha = (
        args.candidate_sha
        or subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=find_repo_root(),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    _receipt, values, _container_values = load_validated_receipt(
        receipt_path=Path(args.synthetic_dsn_receipt).resolve(strict=True),
        run_id=args.run_id,
        candidate_sha=candidate_sha,
    )
    child_env = build_child_environment(
        validated_values=values,
        command=command,
        use_validated_bootstrap_as_pytest_migrator=(
            args.pytest_use_validated_bootstrap_as_migrator
        ),
        process_environment=os.environ,
    )
    completed = subprocess.run(command, env=child_env, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"qa_pg_guard={error.code}")
        raise SystemExit(2) from error
