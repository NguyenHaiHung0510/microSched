"""Plan or execute exact-label recovery of stranded Task 037 Docker resources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.cleanup_qa_docker import cleanup_exact_resource, inspect_exact_resource
from scripts.qa_contracts import (
    QaContractError,
    load_json,
    resolve_inside,
    sha256_file,
    utc_now,
    validate_run_id,
)
from scripts.verify_qa_cleanup import resources

RECOVERY_ORDER = ("app", "pg", "network", "image")
AUTHORIZATION_RELATIVE_PATH = "recovery/authorization.json"


def _resolve_authorization_inside_run(run_dir: Path, authority_path: Path) -> Path:
    try:
        relative = authority_path.relative_to(run_dir).as_posix()
    except ValueError:
        raise QaContractError("FAIL_RECOVERY_PATH_SCOPE") from None
    if relative != AUTHORIZATION_RELATIVE_PATH:
        raise QaContractError("FAIL_RECOVERY_PATH_SCOPE")
    return resolve_inside(run_dir, relative)


def _validate_authorization(path: Path, *, run_id: str, candidate_sha: str) -> dict[str, str]:
    value = load_json(path)
    required = {"run_id", "candidate_sha", "decision", "authorized_by", "authorized_at_utc"}
    if set(value) != required:
        raise QaContractError("FAIL_RECOVERY_AUTHORITY_SHAPE")
    if value["run_id"] != run_id or value["candidate_sha"] != candidate_sha:
        raise QaContractError("FAIL_RECOVERY_AUTHORITY_BINDING")
    if value["decision"] != "APPROVE_STRANDED_RESOURCE_CLEANUP":
        raise QaContractError("BLOCK_RECOVERY_NOT_APPROVED")
    if not isinstance(value["authorized_by"], str) or not value["authorized_by"]:
        raise QaContractError("FAIL_RECOVERY_AUTHORITY_IDENTITY")
    if not isinstance(value["authorized_at_utc"], str) or not value["authorized_at_utc"].endswith(
        "Z"
    ):
        raise QaContractError("FAIL_RECOVERY_AUTHORITY_TIME")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-receipt")
    args = parser.parse_args()
    validate_run_id(args.run_id)
    run_dir = Path(args.run_dir).resolve(strict=True)
    if run_dir.name != args.run_id:
        raise QaContractError("FAIL_RECOVERY_RUN_DIR_BINDING")
    if len(args.candidate_sha) != 40 or any(
        ch not in "0123456789abcdef" for ch in args.candidate_sha
    ):
        raise QaContractError("FAIL_CANDIDATE_SHA")
    authority_sha256 = None
    if args.execute:
        if not args.authorization_receipt:
            raise QaContractError("BLOCK_RECOVERY_AUTHORITY_MISSING")
        authority_path = Path(args.authorization_receipt).resolve(strict=True)
        authority_path = _resolve_authorization_inside_run(run_dir, authority_path)
        _validate_authorization(
            authority_path, run_id=args.run_id, candidate_sha=args.candidate_sha
        )
        authority_sha256 = sha256_file(authority_path)
    elif args.authorization_receipt:
        raise QaContractError("FAIL_RECOVERY_AUTHORITY_WITHOUT_EXECUTE")

    inspected_before = {
        kind: inspect_exact_resource(
            kind=kind, run_id=args.run_id, candidate_sha=args.candidate_sha
        )
        for kind in RECOVERY_ORDER
    }
    before = {kind: inspected is not None for kind, inspected in inspected_before.items()}
    labeled_before = resources(args.run_id)
    expected_labeled_ids = {
        "containers": {
            inspected_before[kind][0]
            for kind in ("app", "pg")
            if inspected_before[kind] is not None
        },
        "networks": (
            {inspected_before["network"][0]} if inspected_before["network"] is not None else set()
        ),
        "images": (
            {inspected_before["image"][0]} if inspected_before["image"] is not None else set()
        ),
    }
    if any(set(labeled_before[kind]) != ids for kind, ids in expected_labeled_ids.items()):
        raise QaContractError("FAIL_RECOVERY_UNEXPECTED_RESOURCE")
    outcomes = {
        kind: "planned" if present else "already-absent" for kind, present in before.items()
    }
    if args.execute:
        outcomes = {
            kind: cleanup_exact_resource(
                kind=kind, run_id=args.run_id, candidate_sha=args.candidate_sha
            )
            for kind in RECOVERY_ORDER
        }
        for env_name in ("synthetic-host.env", "synthetic-container.env", "synthetic.env"):
            resolve_inside(run_dir, env_name, must_exist=False).unlink(missing_ok=True)
    after = {
        kind: inspect_exact_resource(
            kind=kind, run_id=args.run_id, candidate_sha=args.candidate_sha
        )
        is not None
        for kind in RECOVERY_ORDER
    }
    if args.execute and (any(after.values()) or any(resources(args.run_id).values())):
        raise QaContractError("FAIL_RECOVERY_RESIDUAL_RESOURCE")
    receipt = {
        "schema_version": "037-docker-recovery/v1",
        "run_id": args.run_id,
        "candidate_sha": args.candidate_sha,
        "mode": "execute" if args.execute else "plan",
        "authorization_receipt_sha256": authority_sha256,
        "exact_cleanup_order": list(RECOVERY_ORDER),
        "present_before": before,
        "outcomes": outcomes,
        "present_after": after,
        "recorded_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
    }
    recovery_dir = resolve_inside(run_dir, "recovery", must_exist=False)
    recovery_dir.mkdir(parents=True, exist_ok=True)
    receipt_name = "recovery-receipt.json" if args.execute else "recovery-plan.json"
    receipt_path = resolve_inside(recovery_dir, receipt_name, must_exist=False)
    if receipt_path.exists():
        raise QaContractError("FAIL_RECOVERY_RECEIPT_EXISTS")
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"recovery_mode={receipt['mode']}")
    print(f"recovery_receipt_sha256={sha256_file(receipt_path)}")


if __name__ == "__main__":
    try:
        main()
    except (QaContractError, ValueError) as error:
        code = error.code if isinstance(error, QaContractError) else "FAIL_RECOVERY_PATH_SCOPE"
        print(f"qa_recovery_guard={code}")
        raise SystemExit(2) from error
