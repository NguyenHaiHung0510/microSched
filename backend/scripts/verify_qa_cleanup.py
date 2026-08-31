"""Enumerate exact Task 037 Docker resources before and after cleanup."""

from __future__ import annotations

import argparse
import json
import subprocess

from scripts.qa_contracts import QaContractError, validate_run_id


def _lines(*args: str) -> list[str]:
    completed = subprocess.run(["docker", *args], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise QaContractError("BLOCK_DOCKER_QUERY", " ".join(args))
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _inspect(kind: str, resource_id: str) -> dict:
    completed = subprocess.run(
        ["docker", kind, "inspect", resource_id], check=False, capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise QaContractError("BLOCK_DOCKER_INSPECT", resource_id)
    return json.loads(completed.stdout)[0]


def resources(run_id: str) -> dict[str, list[str]]:
    validate_run_id(run_id)
    selector = f"label=microsched.qa.run_id={run_id}"
    return {
        "containers": _lines(
            "container", "ls", "--all", "--filter", selector, "--format", "{{.ID}}"
        ),
        "networks": _lines("network", "ls", "--filter", selector, "--format", "{{.ID}}"),
        "images": _lines("image", "ls", "--filter", selector, "--format", "{{.ID}}"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["pre-cleanup", "post-cleanup"], default="post-cleanup")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-tag")
    parser.add_argument("--expected-containers", type=int)
    parser.add_argument("--expected-networks", type=int)
    parser.add_argument("--expected-images", type=int)
    parser.add_argument("--expected-databases", type=int, default=0)
    parser.add_argument("--expected-schemas", type=int, default=0)
    parser.add_argument("--expected-roles", type=int, default=0)
    args = parser.parse_args()
    found = resources(args.run_id)
    for kind, ids in found.items():
        for resource_id in ids:
            singular = {"containers": "container", "networks": "network", "images": "image"}[kind]
            inspected = _inspect(singular, resource_id)
            labels = inspected.get("Config", {}).get("Labels") or inspected.get("Labels") or {}
            if labels.get("microsched.qa.run_id") != args.run_id:
                raise SystemExit("cleanup_scope=BLOCK_LABEL_MISMATCH")
    if args.phase == "pre-cleanup":
        if args.candidate_tag and not args.candidate_tag.endswith(args.run_id):
            raise SystemExit("cleanup_scope=BLOCK_CANDIDATE_TAG")
        print(json.dumps({"cleanup_scope": "PASS", "resources": found}, sort_keys=True))
        return
    expected = {
        "containers": args.expected_containers,
        "networks": args.expected_networks,
        "images": args.expected_images,
    }
    for kind, count in expected.items():
        if count is None or len(found[kind]) != count:
            raise SystemExit(f"cleanup_zero=FAIL_{kind.upper()}")
    if any((args.expected_databases, args.expected_schemas, args.expected_roles)):
        raise SystemExit("cleanup_zero=BLOCK_DB_COUNTS_REQUIRE_PG_RECEIPT")
    print("cleanup_zero=PASS")


if __name__ == "__main__":
    main()
