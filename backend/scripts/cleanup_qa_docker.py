"""Remove one exact, label-verified Task 037 Docker resource, or prove it absent."""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

from scripts.qa_contracts import QaContractError, validate_run_id


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=False, capture_output=True, text=True)


def _query_ids(kind: str, reference: str) -> list[str]:
    if kind in {"app", "pg"}:
        completed = _run(
            "container", "ls", "--all", "--filter", f"name=^/{reference}$", "--format", "{{.ID}}"
        )
    elif kind == "network":
        completed = _run("network", "ls", "--filter", f"name=^{reference}$", "--format", "{{.ID}}")
    else:
        completed = _run("image", "ls", "--filter", f"reference={reference}", "--format", "{{.ID}}")
    if completed.returncode != 0:
        raise QaContractError("BLOCK_DOCKER_QUERY", kind)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _inspect(kind: str, resource_id: str) -> dict[str, Any]:
    docker_kind = "container" if kind in {"app", "pg"} else kind
    completed = _run(docker_kind, "inspect", resource_id)
    if completed.returncode != 0:
        raise QaContractError("BLOCK_DOCKER_INSPECT", kind)
    try:
        inspected = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise QaContractError("BLOCK_DOCKER_INSPECT_JSON", kind) from error
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise QaContractError("BLOCK_DOCKER_INSPECT_COUNT", kind)
    return inspected[0]


def expected_reference(*, kind: str, run_id: str, candidate_sha: str) -> str:
    if kind == "app":
        return f"microsched-qa-app-{run_id}"
    if kind == "pg":
        return f"microsched-qa-pg-{run_id}"
    if kind == "network":
        return f"microsched-qa-{run_id}"
    if kind == "image":
        return f"microsched-qa:{candidate_sha}-{run_id}"
    raise QaContractError("FAIL_CLEANUP_KIND", kind)


def inspect_exact_resource(
    *, kind: str, run_id: str, candidate_sha: str
) -> tuple[str, dict[str, Any]] | None:
    validate_run_id(run_id)
    if len(candidate_sha) != 40 or any(ch not in "0123456789abcdef" for ch in candidate_sha):
        raise QaContractError("FAIL_CANDIDATE_SHA")
    reference = expected_reference(kind=kind, run_id=run_id, candidate_sha=candidate_sha)
    ids = _query_ids(kind, reference)
    if not ids:
        return None
    if len(ids) != 1:
        raise QaContractError("FAIL_P0_CLEANUP_RESOURCE_COUNT", kind)
    inspected = _inspect(kind, ids[0])
    if kind in {"app", "pg"}:
        name = inspected.get("Name", "").lstrip("/")
        labels = inspected.get("Config", {}).get("Labels") or {}
        if name != reference:
            raise QaContractError("FAIL_P0_CLEANUP_NAME", kind)
    elif kind == "network":
        labels = inspected.get("Labels") or {}
        if inspected.get("Name") != reference:
            raise QaContractError("FAIL_P0_CLEANUP_NAME", kind)
    else:
        labels = inspected.get("Config", {}).get("Labels") or {}
        repo_tags = inspected.get("RepoTags") or []
        if reference not in repo_tags:
            raise QaContractError("FAIL_P0_CLEANUP_NAME", kind)
        if labels.get("org.opencontainers.image.revision") != candidate_sha:
            raise QaContractError("FAIL_P0_CLEANUP_REVISION", kind)
    if labels.get("microsched.qa.run_id") != run_id:
        raise QaContractError("FAIL_P0_CLEANUP_LABEL", kind)
    return ids[0], inspected


def cleanup_exact_resource(*, kind: str, run_id: str, candidate_sha: str) -> str:
    found = inspect_exact_resource(kind=kind, run_id=run_id, candidate_sha=candidate_sha)
    if found is None:
        return "already-absent"
    resource_id, _inspected = found
    reference = expected_reference(kind=kind, run_id=run_id, candidate_sha=candidate_sha)
    if kind in {"app", "pg"}:
        completed = _run("container", "rm", "--force", resource_id)
    elif kind == "network":
        completed = _run("network", "rm", resource_id)
    else:
        completed = _run("image", "rm", reference)
    if completed.returncode != 0:
        raise QaContractError("FAIL_CLEANUP_REMOVE", kind)
    if inspect_exact_resource(kind=kind, run_id=run_id, candidate_sha=candidate_sha) is not None:
        raise QaContractError("FAIL_CLEANUP_NOT_ABSENT", kind)
    return "removed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["app", "pg", "network", "image"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    outcome = cleanup_exact_resource(
        kind=args.kind, run_id=args.run_id, candidate_sha=args.candidate_sha
    )
    print(f"cleanup_kind={args.kind}")
    print(f"cleanup_result={outcome}")


if __name__ == "__main__":
    try:
        main()
    except QaContractError as error:
        print(f"qa_cleanup_guard={error.code}")
        raise SystemExit(2) from error
