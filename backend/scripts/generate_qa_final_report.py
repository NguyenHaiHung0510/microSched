"""Append a deterministic narrative report generated only from acceptance.json."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from scripts.qa_contracts import find_repo_root, load_json, sha256_file, utc_now, validate_schema


def render(acceptance: dict) -> str:
    counts = Counter(cell["status"] for cell in acceptance["cells"])
    lines = [
        f"## Task 037 run `{acceptance['run_id']}`",
        "",
        f"- Candidate: `{acceptance['candidate_sha']}`",
        f"- Final status: `{acceptance['final_status']}`",
        f"- Generated UTC: `{utc_now().isoformat().replace('+00:00', 'Z')}`",
        "",
        "| Machine status | Count |",
        "|---|---:|",
    ]
    for status in ("PASS", "FAIL", "BLOCKED", "NOT_RUN", "SKIPPED_OPTIONAL"):
        lines.append(f"| `{status}` | {counts[status]} |")
    lines.extend(["", "### Non-PASS cells", ""])
    non_pass = [cell for cell in acceptance["cells"] if cell["status"] != "PASS"]
    if not non_pass:
        lines.append("- None.")
    else:
        for cell in sorted(non_pass, key=lambda item: item["acceptance_id"]):
            lines.append(
                f"- `{cell['acceptance_id']}` — `{cell['status']}` — "
                f"command `{cell['command_id']}` — severity `{cell['failure_severity']}`."
            )
    lines.extend(["", "### Evidence boundary", ""])
    lines.append(
        "This report is generated from machine receipts. CI, Neon, production, physical-device, "
        "and real-push status remain separate and are not inferred from another lane."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve(strict=True)
    contract_dir = find_repo_root() / "qa" / "contracts" / "037"
    acceptance = load_json(run_dir / "acceptance.json")
    validate_schema(acceptance, contract_dir / "acceptance.schema.json", label="acceptance")
    report = run_dir / "final-report.md"
    with report.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(render(acceptance))
    print("final_report=appended")
    print(f"final_report_sha256={sha256_file(report)}")


if __name__ == "__main__":
    main()
