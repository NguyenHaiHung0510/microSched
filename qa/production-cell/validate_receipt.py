"""Executable validator for the committed QA025 receipt schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from receipt_validation import ReceiptValidationError, load_and_validate


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = load_and_validate(args.schema, args.receipt)
    except ReceiptValidationError as error:
        print(f"receipt_validation=FAIL error={error}", file=sys.stderr)
        return 20
    print(f"receipt_schema={receipt['schema']} status={receipt['final_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
