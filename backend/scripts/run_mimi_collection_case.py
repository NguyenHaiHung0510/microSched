"""Run one finite frozen backend case with raw output; verdict needs independent review."""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[2]
    packet = json.loads(
        (base / "docs/qa-specs/mimi-task-collection-execution.json").read_text(encoding="utf-8")
    )
    case = next((c for c in packet["cases"] if c["id"] == args.case_id), None)
    if case is None:
        raise SystemExit("undeclared case ID")
    env = dict(os.environ)
    env["MIMI_P0_DISABLE_DOTENV"] = "1"
    env.pop("MIMI_LOCAL_BUDGET_LEDGER", None)
    for name in ("NEON_QA_BRANCH", "ALLOW_REMOTE_PG_TESTS"):
        env.pop(name, None)
    if not args.collect_only:
        raw = env.get("NEON_MIGRATOR_URL")
        if not raw:
            raise SystemExit("explicit synthetic NEON_MIGRATOR_URL required")
        url = make_url(raw)
        if (url.host, url.port, url.database) not in {
            ("127.0.0.1", 21886, "microsched_mimi086_ci2"),
            ("127.0.0.1", 21887, "mimi086_qa"),
        }:
            raise SystemExit("case runner refuses undeclared/nonlocal database")
    args.output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", *case["pytest_selectors"], "-q", "--tb=short"]
    if args.collect_only:
        command += ["--collect-only"]
    start = datetime.now(UTC)
    transcript = args.output / (args.case_id + ".txt")
    with transcript.open("w", encoding="utf-8") as out:
        try:
            code = subprocess.run(
                command,
                cwd=base / "backend",
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=case["timeout_seconds"],
            ).returncode
        except subprocess.TimeoutExpired:
            code = "TIMEOUT"
    receipt = {
        "case_id": args.case_id,
        "command": command,
        "exit": code,
        "started_at": start.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "raw_output": str(transcript),
        "oracle": case["oracle"],
        "case_verdict": "NOT_GRADED_SELECTOR_RESULT_ONLY",
        "paid_calls": 0,
        "collection_only": args.collect_only,
    }
    (args.output / (args.case_id + ".json")).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({"case_id": args.case_id, "exit": code, "case_verdict": receipt["case_verdict"]})
    )
    raise SystemExit(0 if code == 0 else 1)


if __name__ == "__main__":
    main()
