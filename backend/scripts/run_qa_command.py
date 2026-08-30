"""Execute one materialized Task 037 command with dependency and receipt guards."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.qa_contracts import (
    QaContractError,
    find_repo_root,
    load_json,
    resolve_inside,
    sha256_bytes,
    validate_schema,
)

PROTECTED_PLACEHOLDERS = {
    "<run-id>",
    "<candidate-sha>",
    "<manifest-core-sha256>",
    "<activation-receipt-path>",
    "<owner-sync-receipt-path>",
    "<synthetic-host-env-path>",
    "<synthetic-container-env-path>",
    "<synthetic-dsn-receipt-path>",
}
EXTERNAL_PLACEHOLDERS = {"<pgvector-pg18-ref>"}
ALLOWED_PLACEHOLDERS = PROTECTED_PLACEHOLDERS | EXTERNAL_PLACEHOLDERS


def _utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = load_json(path)
    if not isinstance(value, list):
        raise QaContractError("FAIL_COMMAND_RESULTS_SHAPE")
    return value


def _write_results(path: Path, results: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(results, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _parse_values(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise QaContractError("FAIL_PLACEHOLDER_ARGUMENT", item)
        key, value = item.split("=", 1)
        placeholder = f"<{key}>"
        if placeholder not in EXTERNAL_PLACEHOLDERS or placeholder in values or not value:
            raise QaContractError("FAIL_PLACEHOLDER_ARGUMENT", key)
        values[placeholder] = value
    return values


def _validate_caller_values(values: dict[str, str]) -> None:
    invalid = [
        placeholder
        for placeholder, value in values.items()
        if placeholder not in EXTERNAL_PLACEHOLDERS or not isinstance(value, str) or not value
    ]
    if invalid:
        raise QaContractError("FAIL_PLACEHOLDER_ARGUMENT", sorted(invalid)[0])


def substitute(argv: list[str], values: dict[str, str]) -> list[str]:
    result = []
    for argument in argv:
        value = argument
        for placeholder in ALLOWED_PLACEHOLDERS:
            if placeholder in value:
                if placeholder not in values:
                    raise QaContractError("BLOCK_PLACEHOLDER_UNRESOLVED", placeholder)
                value = value.replace(placeholder, values[placeholder])
        if "<" in value or ">" in value:
            raise QaContractError("BLOCK_PLACEHOLDER_UNKNOWN", value)
        result.append(value)
    return result


def _record_blocked(
    *,
    command: dict[str, Any],
    attempt: int,
    blocker: str,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    started = _utc()
    stdout_path.write_bytes(b"")
    stderr = f"command_blocked={blocker}\n".encode()
    stderr_path.write_bytes(stderr)
    return {
        "command_id": command["command_id"],
        "attempt": attempt,
        "cwd": command["cwd"],
        "argv_sha256": command["argv_sha256"],
        "started_at_utc": started,
        "ended_at_utc": _utc(),
        "status": "BLOCKED",
        "actual_exit": None,
        "stdout_path": command["stdout_path"],
        "stdout_sha256": sha256_bytes(b""),
        "stderr_path": command["stderr_path"],
        "stderr_sha256": sha256_bytes(stderr),
        "oracle_results": [
            {
                "oracle_id": command["oracle_ids"][0],
                "result": "BLOCKED",
                "detail": blocker,
            }
        ],
    }


def execute(
    *,
    run_dir: Path,
    command_id: str,
    attempt: int,
    placeholder_values: dict[str, str],
) -> dict[str, Any]:
    # Programmatic callers must receive the same boundary as CLI --value.
    # Validate before loading run artifacts and long before subprocess start.
    _validate_caller_values(placeholder_values)
    repo_root = find_repo_root()
    contract_dir = repo_root / "qa" / "contracts" / "037"
    manifest = load_json(run_dir / "run-manifest.json")
    commands = load_json(run_dir / "commands.json")
    validate_schema(commands, contract_dir / "commands.schema.json", label="commands")
    command_by_id = {item["command_id"]: item for item in commands["commands"]}
    if command_id not in command_by_id:
        raise QaContractError("FAIL_COMMAND_ID", command_id)
    command = command_by_id[command_id]
    binding = commands["command_bindings"][command_id]
    results_path = run_dir / "command-results.json"
    prior = _load_results(results_path)
    attempts = [item["attempt"] for item in prior if item["command_id"] == command_id]
    expected_attempt = max(attempts, default=0) + 1
    if attempt != expected_attempt:
        raise QaContractError("FAIL_COMMAND_ATTEMPT_SEQUENCE", command_id)
    stdout_relative = command["stdout_path"]
    stderr_relative = command["stderr_path"]
    if attempt > 1:
        stdout_relative = f"{stdout_relative}.attempt-{attempt}"
        stderr_relative = f"{stderr_relative}.attempt-{attempt}"
    runtime_command = {
        **command,
        "stdout_path": stdout_relative,
        "stderr_path": stderr_relative,
    }
    stdout_path = resolve_inside(run_dir, stdout_relative, must_exist=False)
    stderr_path = resolve_inside(run_dir, stderr_relative, must_exist=False)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    passed = {item["command_id"] for item in prior if item["status"] == "PASS"}
    missing = [dependency for dependency in binding["depends_on"] if dependency not in passed]
    if missing:
        return _record_blocked(
            command=runtime_command,
            attempt=attempt,
            blocker=f"DEPENDENCY_NOT_PASS:{','.join(missing)}",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
    attempted = {item["command_id"] for item in prior}
    missing_terminal = [
        dependency
        for dependency in binding.get("depends_on_terminal", [])
        if dependency not in attempted
    ]
    if missing_terminal:
        return _record_blocked(
            command=runtime_command,
            attempt=attempt,
            blocker=f"DEPENDENCY_NOT_TERMINAL:{','.join(missing_terminal)}",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
    values = {
        "<run-id>": manifest["run_id"],
        "<candidate-sha>": manifest["candidate_sha"],
        "<manifest-core-sha256>": manifest["manifest_core_sha256"],
        "<activation-receipt-path>": str(
            run_dir / "authority" / "production-device-activation.json"
        ),
        "<owner-sync-receipt-path>": str(run_dir / "authority" / "owner-sync-receipt.json"),
        "<synthetic-host-env-path>": str(run_dir / "synthetic-host.env"),
        "<synthetic-container-env-path>": str(run_dir / "synthetic-container.env"),
        "<synthetic-dsn-receipt-path>": str(run_dir / "synthetic-dsn-receipt.json"),
        **placeholder_values,
    }
    argv = substitute(command["argv"], values)
    executable = shutil.which(argv[0])
    runtime_argv = [executable or argv[0], *argv[1:]]
    started = _utc()
    try:
        completed = subprocess.run(
            runtime_argv,
            cwd=Path(command["resolved_cwd"]),
            env=os.environ.copy(),
            check=False,
            capture_output=True,
            timeout=command["timeout_seconds"],
        )
        actual_exit: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        oracle_pass = actual_exit in command["expected_exit_codes"]
        status = "PASS" if oracle_pass else command["failure_status"]
        oracle_result = "PASS" if oracle_pass else "FAIL"
        detail = (
            "expected exit and self-validating oracle passed" if oracle_pass else "exit mismatch"
        )
    except subprocess.TimeoutExpired as error:
        actual_exit = None
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        status = command["failure_status"]
        oracle_result = "FAIL"
        detail = "timeout"
    except OSError as error:
        actual_exit = None
        stdout = b""
        stderr = f"executable_launch_error={type(error).__name__}\n".encode()
        status = command["failure_status"]
        oracle_result = "FAIL"
        detail = "executable launch failed"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return {
        "command_id": command_id,
        "attempt": attempt,
        "cwd": command["cwd"],
        "argv_sha256": command["argv_sha256"],
        "started_at_utc": started,
        "ended_at_utc": _utc(),
        "status": status,
        "actual_exit": actual_exit,
        "stdout_path": stdout_relative,
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_path": stderr_relative,
        "stderr_sha256": sha256_bytes(stderr),
        "oracle_results": [
            {
                "oracle_id": command["oracle_ids"][0],
                "result": oracle_result,
                "detail": detail,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--command-id", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--value", action="append", default=[])
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve(strict=True)
    result = execute(
        run_dir=run_dir,
        command_id=args.command_id,
        attempt=args.attempt,
        placeholder_values=_parse_values(args.value),
    )
    results_path = run_dir / "command-results.json"
    results = _load_results(results_path)
    results.append(result)
    _write_results(results_path, results)
    print(f"command_id={args.command_id}")
    print(f"attempt={args.attempt}")
    print(f"status={result['status']}")
    if result["actual_exit"] is not None:
        print(f"exit={result['actual_exit']}")
    if result["status"] not in {"PASS", "BLOCKED"}:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"qa_command_guard={error.code}")
        raise SystemExit(2) from error
