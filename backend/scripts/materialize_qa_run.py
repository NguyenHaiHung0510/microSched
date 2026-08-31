"""Materialize Task 037 runtime contracts without starting a QA command."""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
from pathlib import Path
from typing import Any

from scripts.qa_contracts import (
    EXPECTED_AUTHORITY_HASHES,
    STRATEGY_RECEIPT_SHA256,
    QaContractError,
    argv_sha256,
    ensure_clean_contract,
    failure_mapping,
    find_repo_root,
    load_json,
    resolve_inside,
    sha256_file,
    sha256_json,
    utc_now,
    validate_run_id,
    verify_expected_authority_hashes,
)

FRAMEWORK_LOADED_STATE = "loaded"
NONE = "NONE"


def expand_matrix(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the immutable orthogonal union into exact matrix rows."""
    if inventory.get("schema_version") != "037-matrix-inventory/v1":
        raise QaContractError("BLOCK_MATRIX_VERSION")
    profiles = inventory["state_profiles"]
    viewport_profiles = inventory["viewport_device_profiles"]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scenario in inventory["scenarios"]:
        scenario_id = scenario["scenario_id"]
        for group in scenario["groups"]:
            group_id = group["group_id"]
            state_profile = profiles[group["state_profile"]]
            pairs = viewport_profiles[group["viewport_device_profile"]]
            condition = group.get("condition")
            applicable = not bool(condition)
            na_reason = "" if applicable else condition
            for surface in group["surfaces"]:
                for state in state_profile:
                    for pair in pairs:
                        rows.append(
                            _matrix_row(
                                scenario_id,
                                group_id,
                                surface,
                                state,
                                NONE,
                                pair,
                                group["required"],
                                applicable,
                                na_reason,
                            )
                        )
                pair_state = FRAMEWORK_LOADED_STATE if state_profile else NONE
                for domain_state in group["required_states"]:
                    for pair in pairs:
                        rows.append(
                            _matrix_row(
                                scenario_id,
                                group_id,
                                surface,
                                pair_state,
                                domain_state,
                                pair,
                                group["required"],
                                applicable,
                                na_reason,
                            )
                        )
    for cell in inventory["production_device_cells"]:
        rows.append(
            {
                "scenario_id": cell["scenario_id"],
                "coverage_group_id": f"external-{cell['authority_type']}",
                "surface": cell["surface"],
                "framework_state": cell["framework_state"],
                "domain_state": cell["domain_state"],
                "viewport": cell["viewport"],
                "device_token": cell["device_token"],
                "required": str(cell["required"]).lower(),
                "applicable": "false",
                "na_reason_code": f"AUTHORITY_REQUIRED:{cell['authority_type']}",
                "acceptance_id": cell["acceptance_id"],
            }
        )
    for row in rows:
        acceptance_id = row["acceptance_id"]
        if acceptance_id in seen:
            raise QaContractError("BLOCK_MATRIX_DUPLICATE", acceptance_id)
        seen.add(acceptance_id)
    return sorted(rows, key=lambda row: row["acceptance_id"])


def _matrix_row(
    scenario_id: str,
    group_id: str,
    surface: str,
    framework_state: str,
    domain_state: str,
    pair: dict[str, str],
    required: bool,
    applicable: bool,
    na_reason: str,
) -> dict[str, str]:
    acceptance_id = (
        f"037-s{scenario_id}-{group_id}-{surface}-fw-{framework_state}-"
        f"domain-{domain_state}-{pair['viewport']}-{pair['device_token']}"
    )
    return {
        "scenario_id": scenario_id,
        "coverage_group_id": group_id,
        "surface": surface,
        "framework_state": framework_state,
        "domain_state": domain_state,
        "viewport": pair["viewport"],
        "device_token": pair["device_token"],
        "required": str(required).lower(),
        "applicable": str(applicable).lower(),
        "na_reason_code": na_reason,
        "acceptance_id": acceptance_id,
    }


def matrix_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    fields = [
        "scenario_id",
        "coverage_group_id",
        "surface",
        "framework_state",
        "domain_state",
        "viewport",
        "device_token",
        "required",
        "applicable",
        "na_reason_code",
        "acceptance_id",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def materialize_commands(
    *, repo_root: Path, run_id: str, candidate_sha: str, contract_dir: Path
) -> dict[str, Any]:
    contract = load_json(contract_dir / "command-contract.v1.json")
    if contract.get("schema_version") != "037-command-contract/v1":
        raise QaContractError("BLOCK_COMMAND_CONTRACT_VERSION")
    bindings = contract["command_bindings"]
    commands_by_id = {item["id"]: item for item in contract["commands"]}
    if len(commands_by_id) != len(contract["commands"]):
        raise QaContractError("BLOCK_COMMAND_DUPLICATE")
    if set(bindings) != set(commands_by_id):
        raise QaContractError("BLOCK_COMMAND_BINDING_BIJECTION")

    commands: list[dict[str, Any]] = []
    for command_id in sorted(commands_by_id):
        item = commands_by_id[command_id]
        binding = bindings[command_id]
        cwd = item["cwd"]
        resolved = resolve_inside(repo_root, cwd).as_posix()
        failure_status, severity = failure_mapping(item["oracle"])
        commands.append(
            {
                "command_id": command_id,
                "contract_command_version": contract["schema_version"],
                "cwd": cwd,
                "resolved_cwd": resolved,
                "argv": item["argv"],
                "argv_sha256": argv_sha256(item["argv"]),
                "env_names": [],
                "timeout_seconds": contract["timeout_seconds_by_capability"][item["capability"]],
                "capability": item["capability"],
                "required": binding["required"],
                "expected_exit_codes": item["expected_exit"],
                "oracle_ids": [item["oracle"]],
                "failure_status": failure_status,
                "failure_severity": severity,
                "stdout_path": f"raw/commands/{command_id}.stdout",
                "stderr_path": f"raw/commands/{command_id}.stderr",
            }
        )
    return {
        "schema_version": "037-commands/v1",
        "run_id": run_id,
        "candidate_sha": candidate_sha,
        "candidate_worktree": repo_root.as_posix(),
        "contract_command_version": contract["schema_version"],
        "command_contract_sha256": EXPECTED_AUTHORITY_HASHES["command-contract.v1.json"],
        "generated_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "commands": commands,
        "command_bindings": bindings,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-provenance", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--contract-dir", default="../qa/contracts/037")
    parser.add_argument("--executor-lane", required=True)
    parser.add_argument("--executor-identity", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh", "max", "ultra"],
        required=True,
    )
    parser.add_argument("--manual-t1-gate-checked-at", required=True)
    parser.add_argument("--expected-production-sha")
    return parser


def main() -> None:
    args = _parser().parse_args()
    validate_run_id(args.run_id)
    if len(args.candidate_sha) != 40:
        raise SystemExit("FAIL_CANDIDATE_SHA")
    repo_root = find_repo_root()
    contract_dir = Path(args.contract_dir).resolve(strict=True)
    verify_expected_authority_hashes(contract_dir)
    actual_candidate = (
        __import__("subprocess")
        .run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    if actual_candidate != args.candidate_sha:
        raise SystemExit("FAIL_CANDIDATE_SHA_BINDING")
    if (
        args.expected_production_sha is not None
        and args.expected_production_sha != args.candidate_sha
    ):
        raise SystemExit("FAIL_EXPECTED_PRODUCTION_SHA_BINDING")
    run_dir = Path(args.run_dir).resolve(strict=False)
    expected = repo_root / "output" / "qa-runs" / args.run_id
    if run_dir != expected:
        raise SystemExit("FAIL_RUN_DIR_SCOPE")
    run_dir.mkdir(parents=True, exist_ok=False)
    for child in ("raw/commands", "raw/github", "raw/reviews", "authority", "screenshots"):
        (run_dir / child).mkdir(parents=True, exist_ok=True)
    commands = materialize_commands(
        repo_root=repo_root,
        run_id=args.run_id,
        candidate_sha=args.candidate_sha,
        contract_dir=contract_dir,
    )
    (run_dir / "commands.json").write_text(
        json.dumps(commands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    inventory = load_json(contract_dir / "matrix-inventory.v1.json")
    (run_dir / "matrix.csv").write_bytes(matrix_csv_bytes(expand_matrix(inventory)))
    provenance_source = Path(args.candidate_provenance).resolve(strict=True)
    provenance = load_json(provenance_source)
    if provenance.get("candidate_sha") != args.candidate_sha:
        raise SystemExit("FAIL_PROVENANCE_CANDIDATE_BINDING")
    shutil.copyfile(provenance_source, run_dir / "candidate-provenance.json")
    strategy_source = load_json(repo_root / "agent-tasks" / "037-owner-strategy-approval.json")
    spec_paths = {
        "035A": repo_root / "agent-tasks" / "035-reminder-batching.md",
        "035B": repo_root / "agent-tasks" / "035-reminder-batching.md",
        "036": repo_root / "agent-tasks" / "036-dogfooding-ui-ux.md",
        "037": repo_root / "agent-tasks" / "037-comprehensive-qa-baseline.md",
    }
    spec_hashes = {key: sha256_file(path) for key, path in spec_paths.items()}
    strategy_binding = {
        "schema_version": "037-strategy-approval-binding/v1",
        "source_receipt_path": "agent-tasks/037-owner-strategy-approval.json",
        "source_receipt_sha256": STRATEGY_RECEIPT_SHA256,
        "source_message_id": strategy_source["source"]["message_id"],
        "run_id": args.run_id,
        "candidate_sha": args.candidate_sha,
        "spec_037_sha256": spec_hashes["037"],
        "scope_ids": strategy_source["structured_consent"]["scope_ids"],
        "source_qa_execution_status": strategy_source["qa_execution_status"],
        "source_scope_expires": strategy_source["approved_scope"]["expires"],
        "execution_authority": False,
        "manual_owner_t1_process_gate": {
            "recorded": True,
            "checked_at_utc": args.manual_t1_gate_checked_at,
            "checked_by": "T1",
            "audit_only": True,
        },
    }
    candidate_tree = (
        __import__("subprocess")
        .run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    candidate_ref = (
        __import__("subprocess")
        .run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        .stdout.strip()
    )
    manifest = {
        "schema_version": "037-run-manifest/v1",
        "run_id": args.run_id,
        "candidate_sha": args.candidate_sha,
        "candidate_tree_sha": candidate_tree,
        "candidate_ref": candidate_ref,
        "candidate_worktree": repo_root.as_posix(),
        "expected_production_sha": args.expected_production_sha,
        "started_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "executor": {
            "lane": args.executor_lane,
            "identity": args.executor_identity,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
        },
        "spec_hashes": spec_hashes,
        "expected_authority_hashes": EXPECTED_AUTHORITY_HASHES,
        "commands_sha256": sha256_file(run_dir / "commands.json"),
        "candidate_provenance_sha256": sha256_file(run_dir / "candidate-provenance.json"),
        "strategy_approval_binding": strategy_binding,
        "manifest_core_sha256": "0" * 64,
        "git_status_porcelain_z_sha256": ensure_clean_contract(repo_root, args.run_id),
    }
    manifest["manifest_core_sha256"] = sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_core_sha256"}
    )
    (run_dir / "run-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "scope.md").write_text(
        "# Task 037 approved strategy scope\n\n"
        + "\n".join(f"- `{scope_id}`" for scope_id in strategy_binding["scope_ids"])
        + "\n\nExecution authority: `false`; runtime gates remain mandatory.\n",
        encoding="utf-8",
    )
    print(f"materialized_run_id={args.run_id}")
    print(f"commands_sha256={sha256_file(run_dir / 'commands.json')}")
    print(f"matrix_sha256={sha256_file(run_dir / 'matrix.csv')}")


if __name__ == "__main__":
    main()
