"""Run or verify the QA025 local disposable production-image cell."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cell import (
    guard_or_receipt,
    make_run,
    new_run_id,
    run_full_cell,
    run_preflight_only,
    validate_final_receipt,
    verify_cleanup_receipt,
    write_guard_receipt,
)
from contract import CellError, GuardDenied, denied_parent_variable_names
from receipt import read_receipt
from receipt_validation import ReceiptValidationError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, exit_on_error=False)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--verify-cleanup", type=Path)
    try:
        args, unknown = parser.parse_known_args(argv)
    except argparse.ArgumentError as error:
        raise GuardDenied("conflicting or invalid caller input") from error
    if unknown:
        raise GuardDenied("unsupported caller input")
    return args


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parent_env = dict(os.environ)
    run_id = new_run_id()
    try:
        args = parse_args(argv)
    except GuardDenied:
        path = write_guard_receipt(repo_root, run_id, [])
        print(
            "status=GUARD_DENIED exit=40 rejected_caller_input=true resource_count=0 "
            f"receipt_path={path.relative_to(repo_root).as_posix()}"
        )
        return 40
    guard_receipt = guard_or_receipt(repo_root, parent_env, run_id)
    if guard_receipt is not None:
        names = ",".join(denied_parent_variable_names(parent_env))
        print(
            f"status=GUARD_DENIED exit=40 rejected_parent_variable_names={names} "
            f"resource_count=0 receipt_path={guard_receipt.relative_to(repo_root).as_posix()}"
        )
        return 40

    try:
        if args.verify_cleanup is not None:
            verify_cleanup_receipt(repo_root, parent_env, args.verify_cleanup)
            print("cleanup_verification=PASS residual_resource_count=0")
            return 0
        if args.preflight_only:
            return run_preflight_only(repo_root, parent_env)
        run = make_run(repo_root, parent_env, run_id)
        exit_code = run_full_cell(run)
        receipt = read_receipt(run.receipt_path)
        validate_final_receipt(repo_root, receipt)
        print(f"receipt_schema={receipt['schema']} status={receipt['final_status']}")
        print(
            f"receipt_path=frontend/test-results/production-cell/{run.run_id}/receipt.json"
        )
        return exit_code
    except ReceiptValidationError as error:
        print(f"status=INFRA_ERROR exit=60 receipt_validation={error}", file=sys.stderr)
        return 60
    except CellError as error:
        print(
            f"status={error.status} exit={error.exit_code} error={error}",
            file=sys.stderr,
        )
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - CLI boundary emits a stable safe status
        print(
            f"status=INFRA_ERROR exit=60 type={type(error).__name__}", file=sys.stderr
        )
        return 60


if __name__ == "__main__":
    raise SystemExit(main())
