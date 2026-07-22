"""Reject unreviewed destructive operations from migration upgrade paths."""

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
DROP_CALL = re.compile(r"op\.drop_(?:column|table)\s*\(")
REVIEW_LABEL = "# reviewed: intentional drop"


def upgrade_body(source: str) -> str:
    """Return only the upgrade function, because initial downgrades intentionally drop."""
    match = re.search(r"(?ms)^def upgrade\(\).*?(?=^def downgrade\(|\Z)", source)
    return match.group(0) if match else ""


def main() -> None:
    """Fail when an upgrade drop lacks the required same-line review label."""
    failures: list[str] = []
    for revision in sorted(VERSIONS.glob("*.py")):
        for number, line in enumerate(
            upgrade_body(revision.read_text(encoding="utf-8")).splitlines(), 1
        ):
            if DROP_CALL.search(line) and REVIEW_LABEL not in line:
                failures.append(f"{revision.name}:{number}")

    if failures:
        joined = ", ".join(failures)
        raise SystemExit(f"unreviewed migration drop: {joined}")
    print("migration_drop_guard=ok")


if __name__ == "__main__":
    main()
