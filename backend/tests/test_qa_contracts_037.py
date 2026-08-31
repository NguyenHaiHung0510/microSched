"""RED/GREEN self-tests for the Task 037 fail-closed runtime contracts."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import re
import struct
import subprocess
import sys
import urllib.error
import uuid
import zlib
from datetime import date, time
from pathlib import Path

import pytest

from scripts.cleanup_qa_docker import cleanup_exact_resource
from scripts.create_synthetic_qa_env import ENV_NAMES, build_env_pair
from scripts.materialize_qa_run import expand_matrix, materialize_commands
from scripts.qa_contracts import (
    EXPECTED_AUTHORITY_HASHES,
    QaContractError,
    find_repo_root,
    git_output,
    load_json,
    sha256_json,
    strict_json_loads,
    validate_schema,
    verify_expected_authority_hashes,
)
from scripts.recover_qa_docker_resources import main as recovery_main
from scripts.run_qa_command import _parse_values, execute, substitute
from scripts.validate_qa_run import (
    _aggregate,
    _verify_commands,
    _verify_provenance,
    _verify_strategy_binding,
    validate_activation,
    validate_command_results,
    validate_expected_authority_review_receipt,
    validate_final,
    validate_owner_sync,
    validate_redaction,
    validate_screenshots,
    validate_strategy_source_semantics,
)
from scripts.validate_synthetic_pg_target import validate_target
from scripts.verify_qa_catalog import (
    validate_bootstrap_default_acl_raw,
    validate_catalog_structure,
    validate_explicit_grants,
)

REPO_ROOT = find_repo_root(Path(__file__))
CONTRACT_DIR = REPO_ROOT / "qa" / "contracts" / "037"
RUN_ID = "019d0000-0000-7000-8000-000000000037"
CANDIDATE = "a" * 40
SHA256 = "b" * 64


def _manifest() -> dict:
    return {
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "candidate_tree_sha": "c" * 40,
        "manifest_core_sha256": SHA256,
        "started_at_utc": "2026-08-29T23:59:00Z",
        "spec_hashes": {"037": SHA256},
        "executor": {
            "lane": "fixture",
            "identity": "fixture-executor",
            "model": "fixture-model",
            "reasoning_effort": "high",
        },
    }


def _source_message() -> dict:
    return {
        "thread_id": "thread",
        "turn_id": "turn",
        "message_id": "message",
        "created_at_utc": "2026-08-29T00:00:00Z",
        "exact_text_sha256_utf8": SHA256,
        "capture_method": "codex_app.read_thread+uuidv7_timestamp",
    }


def _owner_sync() -> dict:
    return {
        "schema_version": "037-owner-sync-receipt/v1",
        "receipt_id": "019d0000-0000-7000-8000-000000000038",
        "authority_type": "owner_neon_develop_sync_confirmation",
        "source_message": _source_message(),
        "structured_consent": {
            "decision": "CONFIRM_NEON_MAIN_TO_DEVELOP_SYNC_COMPLETED",
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "spec_037_sha256": SHA256,
            "allowed_command_ids": ["tier2.prepare-qa-branch"],
        },
        "run_binding": {
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "spec_037_sha256": SHA256,
            "manifest_core_sha256": SHA256,
        },
        "neon_sync": {
            "project_id_sha256": SHA256,
            "source_branch_name": "main",
            "source_branch_id_sha256": SHA256,
            "target_branch_name": "develop",
            "target_branch_id_sha256": SHA256,
            "production_parent_git_sha": "d" * 40,
            "production_parent_source_receipt_sha256": SHA256,
            "sync_completed_at_utc": "2026-08-29T00:00:00Z",
            "console_operation_receipt_sha256": SHA256,
        },
        "allowed_next_command_id": "tier2.prepare-qa-branch",
        "explicitly_denied_authorities": [
            "neon_create_delete_restore_sync",
            "production_or_device_activation",
            "real_web_push",
            "merge",
            "deploy",
        ],
        "audit_only": True,
        "manual_gate_required": True,
    }


def _activation() -> dict:
    return {
        "schema_version": "037-production-device-activation/v1",
        "receipt_id": "019d0000-0000-7000-8000-000000000039",
        "authority_type": "production_read_only_smoke",
        "source_message": _source_message(),
        "structured_consent": {
            "decision": "ACTIVATE_PRODUCTION_READ_ONLY_SMOKE",
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "spec_037_sha256": SHA256,
            "allowed_command_ids": ["prod.readyz", "prod.fly-topology"],
        },
        "run_binding": {
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "spec_037_sha256": SHA256,
            "manifest_core_sha256": SHA256,
        },
        "target": {
            "origin": "https://microsched.fly.dev",
            "fly_app": "microsched",
            "region": "sin",
            "database_branch_name": "main",
            "device_token": "NONE",
        },
        "allowed_command_ids": ["prod.readyz", "prod.fly-topology"],
        "executor": {
            "lane": "fixture",
            "identity": "fixture-executor",
            "model": "fixture-model",
            "reasoning_effort": "high",
        },
        "issued_at_utc": "2026-08-28T23:00:00Z",
        "expires_at_utc": "2026-08-29T02:00:00Z",
        "single_use": True,
        "read_only": True,
        "explicitly_denied_mutations": [
            "production_data_write",
            "production_migration",
            "production_seed",
            "fault_injection",
            "neon_branch_operation",
            "deploy",
            "merge",
            "oauth_permission_change",
        ],
        "audit_only": True,
        "manual_gate_required": True,
    }


def _expected_authority_review(command_ids: set[str]) -> dict:
    command_digest = sha256_json(sorted(command_ids))
    return {
        "schema_version": "037-expected-authority-review/v1",
        "approval_mode": "DIRECT_OWNER",
        "run_binding": {
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "spec_037_sha256": SHA256,
        },
        "contract_hashes": {
            "command_contract_sha256": EXPECTED_AUTHORITY_HASHES["command-contract.v1.json"],
            "matrix_inventory_sha256": EXPECTED_AUTHORITY_HASHES["matrix-inventory.v1.json"],
            "expected_catalog_fixtures_sha256": EXPECTED_AUTHORITY_HASHES[
                "expected-catalog-fixtures.v1.json"
            ],
            "catalog_queries_sha256": EXPECTED_AUTHORITY_HASHES["catalog-queries.v1.sql"],
        },
        "approved_command_ids": sorted(command_ids),
        "approved_command_ids_sha256": command_digest,
        "independent_review": {
            "reviewer_identity": "fixture-independent-reviewer",
            "model": "fixture-model",
            "reasoning_effort": "high",
            "verdict": "PASS_EXPECTED_AUTHORITY",
            "reviewed_at_utc": "2026-08-30T00:00:00Z",
            "raw_review_sha256": SHA256,
        },
        "owner_review": {
            "thread_id": "fixture-thread",
            "turn_id": "fixture-turn",
            "message_id": "fixture-message",
            "created_at_utc": "2026-08-30T00:01:00Z",
            "exact_text_sha256_utf8": SHA256,
            "capture_method": "codex_app.read_thread+uuidv7_timestamp",
            "verdict": "APPROVE_EXPECTED_AUTHORITY_ONLY",
            "structured_consent": {
                "decision": "APPROVE_EXPECTED_AUTHORITY_ONLY",
                "run_id": RUN_ID,
                "candidate_sha": CANDIDATE,
                "spec_037_sha256": SHA256,
                "approved_command_ids_sha256": command_digest,
            },
        },
        "executor_identity": "fixture-executor",
        "t1_process_check": {
            "recorded": True,
            "t1_identity": "fixture-t1",
            "checked_reviewer_distinct_from_executor": True,
            "checked_reviewer_distinct_from_t1": True,
            "checked_authority_source": True,
            "checked_at_utc": "2026-08-30T00:02:00Z",
            "audit_only": True,
        },
        "audit_only": True,
        "manual_gate_required": True,
    }


def _delegated_expected_authority_review(command_ids: set[str]) -> dict:
    review = _expected_authority_review(command_ids)
    command_digest = review["approved_command_ids_sha256"]
    review["approval_mode"] = "T1_DELEGATED"
    del review["owner_review"]
    review["independent_review"]["reviewed_at_utc"] = "2026-08-30T09:01:00Z"
    review["owner_delegation"] = {
        "thread_id": "01a0439a-145f-7740-a33e-bff6e0b97661",
        "turn_id": "01a051df-bda3-7d52-a3e5-101b93ff0f25",
        "message_id": "msg_01a051df-bdfa-72c3-80d9-7ae6248315e6",
        "created_at_utc": "2026-08-30T08:53:32.794Z",
        "exact_text_sha256_utf8": (
            "7170603cc9f7dbcb75b65419e3bddb6dba3899f75ce9461e4ef30bd1a405031a"
        ),
        "capture_method": "codex_app.read_thread+uuidv7_timestamp",
        "decision": "DELEGATE_EXPECTED_AUTHORITY_DECISION_TO_T1",
        "scope": {
            "task_id": "037",
            "authority_scope": "EXPECTED_AUTHORITY_TECHNICAL_APPROVAL_ONLY",
            "delegated_role": "T1",
            "explicitly_excluded": [
                "COMMAND_EXECUTION",
                "NEON",
                "PRODUCTION",
                "DEVICE",
                "MERGE",
                "DEPLOY",
            ],
        },
        "audit_only": True,
    }
    review["t1_technical_decision"] = {
        "t1_identity": "fixture-t1",
        "decision": "APPROVE_EXPECTED_AUTHORITY_ONLY",
        "decided_at_utc": "2026-08-30T09:02:00Z",
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "spec_037_sha256": SHA256,
        "approved_command_ids_sha256": command_digest,
        "independent_review_raw_sha256": SHA256,
        "audit_only": True,
    }
    review["t1_process_check"]["checked_at_utc"] = "2026-08-30T09:03:00Z"
    return review


def _post_delegation_manifest() -> dict:
    manifest = _manifest()
    manifest["started_at_utc"] = "2026-08-30T09:00:00Z"
    return manifest


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_frozen_expected_authority_hashes_are_exact() -> None:
    assert verify_expected_authority_hashes(CONTRACT_DIR) == EXPECTED_AUTHORITY_HASHES


def test_task_037_frozen_table_matches_runtime_hash_constants_and_stays_draft() -> None:
    spec = (REPO_ROOT / "agent-tasks" / "037-comprehensive-qa-baseline.md").read_text(
        encoding="utf-8"
    )
    assert "Trạng thái: **DRAFT" in spec
    for name, digest in EXPECTED_AUTHORITY_HASHES.items():
        assert re.search(rf"^{re.escape(name)}\s+{digest}$", spec, re.M)


def test_task_036_frontend_receipt_uses_the_canonical_package_script() -> None:
    spec = (REPO_ROOT / "agent-tasks" / "036-dogfooding-ui-ux.md").read_text(encoding="utf-8")
    package = load_json(REPO_ROOT / "frontend" / "package.json")
    assert "e2e" in package["scripts"]
    assert "frontend: npm run e2e" in spec
    assert "npm run test:e2e" not in spec


def test_expected_authority_command_ids_use_canonical_command_grammar() -> None:
    review_schema = CONTRACT_DIR / "expected-authority-review.schema.json"
    canonical_pattern = load_json(CONTRACT_DIR / "commands.schema.json")["properties"]["commands"][
        "items"
    ]["properties"]["command_id"]["pattern"]
    expected_review_pattern = load_json(review_schema)["properties"]["approved_command_ids"][
        "items"
    ]["pattern"]

    for command_id in ("dep.035A.precommit", "dep.035B.active-endpoints-unit"):
        validate_schema(
            _expected_authority_review({command_id}),
            review_schema,
            label="expected-authority-review",
        )
    assert expected_review_pattern == canonical_pattern

    for command_id in ("dep.035A_precommit", "dep/035B/precommit", "dep 035A precommit", ""):
        with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
            validate_schema(
                _expected_authority_review({command_id}),
                review_schema,
                label="expected-authority-review",
            )


def test_repo_root_expected_review_cannot_satisfy_runtime_gate(tmp_path) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "run"
    repo_root.mkdir()
    run_dir.mkdir()
    _write_json(
        repo_root / "agent-tasks" / "037-expected-authority-review.json",
        _expected_authority_review(command_ids),
    )
    with pytest.raises(QaContractError, match="BLOCK_EXPECTED_AUTHORITY_REVIEW_MISSING"):
        validate_expected_authority_review_receipt(run_dir, _manifest(), command_ids, CONTRACT_DIR)


def test_missing_runtime_expected_review_blocks(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(QaContractError, match="BLOCK_EXPECTED_AUTHORITY_REVIEW_MISSING"):
        validate_expected_authority_review_receipt(
            run_dir, _manifest(), {"qa.preflight"}, CONTRACT_DIR
        )


def test_runtime_expected_review_binding_mutants_block(tmp_path) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    mutations = {
        "run": lambda review: review["run_binding"].update(run_id="wrong-run"),
        "candidate": lambda review: review["run_binding"].update(candidate_sha="d" * 40),
        "spec": lambda review: review["run_binding"].update(spec_037_sha256="e" * 64),
        "commands": lambda review: (
            review.update(approved_command_ids=["qa.preflight"]),
            review.update(approved_command_ids_sha256=sha256_json(["qa.preflight"])),
            review["owner_review"]["structured_consent"].update(
                approved_command_ids_sha256=sha256_json(["qa.preflight"])
            ),
        ),
    }
    for label, mutate in mutations.items():
        run_dir = tmp_path / label / "run"
        run_dir.mkdir(parents=True)
        review = _expected_authority_review(command_ids)
        mutate(review)
        _write_json(run_dir / "authority" / "expected-authority-review.json", review)
        with pytest.raises(QaContractError, match="FAIL_SCHEMA|BLOCK_BINDING_MISMATCH"):
            validate_expected_authority_review_receipt(
                run_dir, _manifest(), command_ids, CONTRACT_DIR
            )


def test_exact_runtime_expected_review_passes_without_self_reference(tmp_path) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_json(
        run_dir / "authority" / "expected-authority-review.json",
        _expected_authority_review(command_ids),
    )
    validate_expected_authority_review_receipt(run_dir, _manifest(), command_ids, CONTRACT_DIR)


def test_delegation_before_materialization_and_t1_decision_after_review_passes(
    tmp_path,
) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_json(
        run_dir / "authority" / "expected-authority-review.json",
        _delegated_expected_authority_review(command_ids),
    )
    validate_expected_authority_review_receipt(
        run_dir, _post_delegation_manifest(), command_ids, CONTRACT_DIR
    )


@pytest.mark.parametrize("mutant", ["missing-delegation", "out-of-scope-delegation"])
def test_delegated_expected_authority_requires_exact_narrow_source(tmp_path, mutant: str) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    review = _delegated_expected_authority_review(command_ids)
    if mutant == "missing-delegation":
        del review["owner_delegation"]
    else:
        review["owner_delegation"]["scope"]["explicitly_excluded"].remove("NEON")
    run_dir = tmp_path / mutant
    _write_json(run_dir / "authority" / "expected-authority-review.json", review)
    with pytest.raises(QaContractError, match="FAIL_SCHEMA|BLOCK_EXPECTED_DELEGATION_SCOPE"):
        validate_expected_authority_review_receipt(
            run_dir, _post_delegation_manifest(), command_ids, CONTRACT_DIR
        )


@pytest.mark.parametrize(
    ("mutant", "expected_error"),
    [
        ("decision-before-materialization", "BLOCK_EXPECTED_AUTHORITY_REVIEW_ORDER"),
        ("decision-before-review", "BLOCK_EXPECTED_AUTHORITY_REVIEW_ORDER"),
        ("decision-run-mismatch", "BLOCK_BINDING_MISMATCH"),
        ("decision-hash-mismatch", "BLOCK_BINDING_MISMATCH"),
        ("decision-review-hash-mismatch", "BLOCK_BINDING_MISMATCH"),
        ("reviewer-is-t1", "BLOCK_EXPECTED_REVIEWER_NOT_INDEPENDENT"),
        ("reviewer-is-executor", "BLOCK_EXPECTED_REVIEWER_NOT_INDEPENDENT"),
    ],
)
def test_delegated_t1_decision_binding_order_and_independence_mutants_are_red(
    tmp_path, mutant: str, expected_error: str
) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    review = _delegated_expected_authority_review(command_ids)
    if mutant == "decision-before-materialization":
        review["t1_technical_decision"]["decided_at_utc"] = "2026-08-30T08:59:00Z"
    elif mutant == "decision-before-review":
        review["t1_technical_decision"]["decided_at_utc"] = "2026-08-30T09:00:30Z"
    elif mutant == "decision-run-mismatch":
        review["t1_technical_decision"]["run_id"] = "019d0000-0000-7000-8000-000000000038"
    elif mutant == "decision-hash-mismatch":
        review["t1_technical_decision"]["approved_command_ids_sha256"] = "d" * 64
    elif mutant == "decision-review-hash-mismatch":
        review["t1_technical_decision"]["independent_review_raw_sha256"] = "e" * 64
    elif mutant == "reviewer-is-t1":
        review["independent_review"]["reviewer_identity"] = "fixture-t1"
    else:
        review["independent_review"]["reviewer_identity"] = "fixture-executor"
    run_dir = tmp_path / mutant
    _write_json(run_dir / "authority" / "expected-authority-review.json", review)
    with pytest.raises(QaContractError, match=expected_error):
        validate_expected_authority_review_receipt(
            run_dir, _post_delegation_manifest(), command_ids, CONTRACT_DIR
        )


def test_direct_owner_mode_rejects_delegation_message_as_exact_hash_approval(tmp_path) -> None:
    command_ids = {"qa.preflight", "backend.ruff-check"}
    review = _expected_authority_review(command_ids)
    review["owner_review"].update(
        thread_id="01a0439a-145f-7740-a33e-bff6e0b97661",
        turn_id="01a051df-bda3-7d52-a3e5-101b93ff0f25",
        message_id="msg_01a051df-bdfa-72c3-80d9-7ae6248315e6",
        exact_text_sha256_utf8=("7170603cc9f7dbcb75b65419e3bddb6dba3899f75ce9461e4ef30bd1a405031a"),
    )
    run_dir = tmp_path / "run"
    _write_json(run_dir / "authority" / "expected-authority-review.json", review)
    with pytest.raises(QaContractError, match="BLOCK_EXPECTED_DIRECT_OWNER_SOURCE_IS_DELEGATION"):
        validate_expected_authority_review_receipt(run_dir, _manifest(), command_ids, CONTRACT_DIR)


def _provenance_fixture(tmp_path: Path) -> tuple[Path, dict, dict]:
    run_dir = tmp_path / "run"
    (run_dir / "raw" / "github").mkdir(parents=True)
    (run_dir / "raw" / "reviews").mkdir(parents=True)
    head = git_output(REPO_ROOT, "rev-parse", "HEAD")
    tree = git_output(REPO_ROOT, "show", "-s", "--format=%T", "HEAD")
    assert isinstance(head, str) and isinstance(tree, str)
    checks = [
        {"name": "Backend checks", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "Migration QA", "status": "COMPLETED", "conclusion": "SUCCESS"},
    ]

    def pr_receipt(number: int, label: str, *, state: str) -> dict:
        raw_relative = f"raw/github/pr-{number}.json"
        raw = {
            "number": number,
            "url": f"https://github.com/owner/repo/pull/{number}",
            "headRefName": f"feat/{label}",
            "headRefOid": head,
            "baseRefName": "develop",
            "baseRefOid": head,
            "state": state,
            "isDraft": False,
            "statusCheckRollup": copy.deepcopy(checks),
        }
        raw_path = run_dir / raw_relative
        _write_json(raw_path, raw)
        return {
            "number": number,
            "url": raw["url"],
            "headRefName": raw["headRefName"],
            "headRefOid": head,
            "baseRefName": "develop",
            "baseRefOid": head,
            "state": state,
            "isDraft": False,
            "required_checks": copy.deepcopy(checks),
            "queried_at_utc": "2026-08-30T02:40:00Z",
            "raw_receipt_path": raw_relative,
            "raw_receipt_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        }

    dependencies = []
    for dependency_id, number, spec_path in (
        ("035A", 185, "agent-tasks/035-reminder-batching.md"),
        ("035B", 190, "agent-tasks/035-reminder-batching.md"),
        ("036", 186, "agent-tasks/036-dogfooding-ui-ux.md"),
    ):
        pr = pr_receipt(number, dependency_id.lower(), state="MERGED")
        spec_bytes = git_output(REPO_ROOT, "show", f"{head}:{spec_path}", binary=True)
        assert isinstance(spec_bytes, bytes)
        spec_sha256 = hashlib.sha256(spec_bytes).hexdigest()
        raw_review_relative = f"raw/reviews/{dependency_id.lower()}-raw.json"
        raw_review_path = run_dir / raw_review_relative
        _write_json(
            raw_review_path,
            {"message_id": f"review-{dependency_id}", "verdict": "PASS_REVIEW"},
        )
        envelope_relative = f"raw/reviews/{dependency_id.lower()}-envelope.json"
        envelope_path = run_dir / envelope_relative
        envelope = {
            "schema_version": "037-review-envelope/v1",
            "dependency_id": dependency_id,
            "reviewed_head_oid": head,
            "base_oid": head,
            "reviewed_spec_sha256": spec_sha256,
            "executor_identity": f"executor-{dependency_id}",
            "reviewer": {
                "identity": f"reviewer-{dependency_id}",
                "model": "fixture-reviewer",
                "reasoning_effort": "high",
                "independent_from_executor": True,
            },
            "verdict": "PASS_REVIEW",
            "reviewed_at_utc": "2026-08-30T02:41:00Z",
            "source": {
                "thread_id": "fixture-thread",
                "turn_id": f"turn-{dependency_id}",
                "message_id": f"review-{dependency_id}",
                "created_at_utc": "2026-08-30T02:41:00Z",
                "raw_review_path": raw_review_relative,
                "raw_review_sha256": hashlib.sha256(raw_review_path.read_bytes()).hexdigest(),
                "identity_binding": {
                    "reviewer_identity": f"reviewer-{dependency_id}",
                    "executor_identity": f"executor-{dependency_id}",
                    "comparison": "REQUIRE_DISTINCT_EXACT_STRINGS",
                },
            },
            "t1_process_check": {
                "recorded": True,
                "checked_reviewer_distinct_from_executor": True,
                "checked_review_bound_to_head": True,
                "checked_at_utc": "2026-08-30T02:42:00Z",
                "audit_only": True,
            },
            "github_pr_receipt": {
                "queried_at_utc": pr["queried_at_utc"],
                "raw_api_path": pr["raw_receipt_path"],
                "raw_api_sha256": pr["raw_receipt_sha256"],
                "pr_number": pr["number"],
                "state": pr["state"],
                "is_draft": pr["isDraft"],
                "head_ref_name": pr["headRefName"],
                "head_ref_oid": pr["headRefOid"],
                "base_ref_name": pr["baseRefName"],
                "base_ref_oid": pr["baseRefOid"],
                "required_checks_terminal_success": True,
            },
        }
        _write_json(envelope_path, envelope)
        dependencies.append(
            {
                "dependency_id": dependency_id,
                "spec_path": spec_path,
                "spec_sha256": spec_sha256,
                "head_oid": head,
                "base_oid": head,
                "review_envelope_path": envelope_relative,
                "review_envelope_sha256": hashlib.sha256(envelope_path.read_bytes()).hexdigest(),
                "pr": pr,
                "lineage_verified": True,
            }
        )

    provenance = {
        "schema_version": "037-candidate-provenance/v1",
        "repo": "owner/repo",
        "remote_url": "https://github.com/owner/repo.git",
        "candidate_ref": "feat/037-comprehensive-qa-baseline",
        "candidate_sha": head,
        "candidate_tree_sha": tree,
        "queried_at_utc": "2026-08-30T02:40:00Z",
        "candidate_pr": pr_receipt(191, "037", state="OPEN"),
        "dependencies": dependencies,
    }
    manifest = _manifest()
    manifest.update(candidate_sha=head, candidate_tree_sha=tree)
    return run_dir, provenance, manifest


@pytest.mark.parametrize("mutation", ["missing", "failed"])
def test_provenance_missing_or_failed_raw_pr_checks_block(tmp_path, mutation) -> None:
    run_dir, provenance, manifest = _provenance_fixture(tmp_path)
    pr = provenance["dependencies"][0]["pr"]
    raw_path = run_dir / pr["raw_receipt_path"]
    raw = load_json(raw_path)
    if mutation == "missing":
        raw["statusCheckRollup"] = []
    else:
        raw["statusCheckRollup"][0]["conclusion"] = "FAILURE"
    _write_json(raw_path, raw)
    pr["raw_receipt_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()

    with pytest.raises(QaContractError, match="BLOCK_PR_CHECKS_NOT_SUCCESS"):
        _verify_provenance(provenance, manifest, run_dir, REPO_ROOT, CONTRACT_DIR)


@pytest.mark.parametrize("mutation", ["head", "base", "spec", "review", "review-digest"])
def test_provenance_bad_pr_or_review_binding_blocks(tmp_path, mutation) -> None:
    run_dir, provenance, manifest = _provenance_fixture(tmp_path)
    dependency = provenance["dependencies"][0]
    if mutation in {"head", "base"}:
        key = "headRefOid" if mutation == "head" else "baseRefOid"
        dependency["pr"][key] = "d" * 40
    elif mutation == "spec":
        dependency["spec_sha256"] = "d" * 64
    elif mutation == "review-digest":
        raw_review = run_dir / "raw/reviews/035a-raw.json"
        _write_json(raw_review, {"message_id": "mutant", "verdict": "PASS_REVIEW"})
    else:
        envelope_path = run_dir / dependency["review_envelope_path"]
        envelope = load_json(envelope_path)
        envelope["reviewed_head_oid"] = "d" * 40
        _write_json(envelope_path, envelope)
        dependency["review_envelope_sha256"] = hashlib.sha256(
            envelope_path.read_bytes()
        ).hexdigest()

    with pytest.raises(QaContractError, match="BLOCK_|FAIL_"):
        _verify_provenance(provenance, manifest, run_dir, REPO_ROOT, CONTRACT_DIR)


def test_provenance_lineage_failure_blocks(tmp_path, monkeypatch) -> None:
    run_dir, provenance, manifest = _provenance_fixture(tmp_path)
    monkeypatch.setattr("scripts.validate_qa_run._git_is_ancestor", lambda *_args: False)
    with pytest.raises(QaContractError, match="BLOCK_DEPENDENCY_LINEAGE"):
        _verify_provenance(provenance, manifest, run_dir, REPO_ROOT, CONTRACT_DIR)


def test_exact_historical_provenance_passes_without_command_stream_summaries(tmp_path) -> None:
    run_dir, provenance, manifest = _provenance_fixture(tmp_path)
    _verify_provenance(provenance, manifest, run_dir, REPO_ROOT, CONTRACT_DIR)


def test_historical_command_summary_cannot_replace_current_command_result(tmp_path) -> None:
    run_dir, provenance, manifest = _provenance_fixture(tmp_path)
    provenance["dependencies"][0]["command_receipts"] = [
        {
            "command_id": "dep.035A.ruff-check",
            "stdout_sha256": SHA256,
            "stderr_sha256": SHA256,
            "exit_code": 0,
            "oracle_passed": True,
        }
    ]
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        _verify_provenance(provenance, manifest, run_dir, REPO_ROOT, CONTRACT_DIR)

    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=manifest["candidate_sha"],
        contract_dir=CONTRACT_DIR,
    )
    _write_json(run_dir / "commands.json", commands)
    _write_json(run_dir / "command-results.json", [])
    with pytest.raises(QaContractError, match="FAIL_COMMAND_RESULT_BIJECTION"):
        validate_command_results(run_dir, CONTRACT_DIR)


def test_all_runtime_schemas_reject_unknown_fields() -> None:
    schema_names = [
        "run-manifest.schema.json",
        "strategy-approval-binding.schema.json",
        "candidate-provenance.schema.json",
        "commands.schema.json",
        "acceptance.schema.json",
        "screenshot-record.schema.json",
        "catalog-receipt.schema.json",
        "backup-receipt.schema.json",
        "migration-receipt.schema.json",
        "synthetic-dsn-receipt.schema.json",
    ]
    for name in schema_names:
        schema = load_json(CONTRACT_DIR / name)
        assert schema["additionalProperties"] is False, name


def test_run_manifest_resolves_local_strategy_binding_schema() -> None:
    manifest = {
        "schema_version": "037-run-manifest/v1",
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "candidate_tree_sha": "c" * 40,
        "candidate_ref": "feat/037-comprehensive-qa-baseline",
        "candidate_worktree": REPO_ROOT.as_posix(),
        "expected_production_sha": None,
        "started_at_utc": "2026-08-29T00:00:00Z",
        "executor": {
            "lane": "fixture",
            "identity": "fixture",
            "model": "fixture",
            "reasoning_effort": "high",
        },
        "spec_hashes": {"035A": SHA256, "035B": SHA256, "036": SHA256, "037": SHA256},
        "expected_authority_hashes": EXPECTED_AUTHORITY_HASHES,
        "commands_sha256": SHA256,
        "candidate_provenance_sha256": SHA256,
        "strategy_approval_binding": {
            "schema_version": "037-strategy-approval-binding/v1",
            "source_receipt_path": "agent-tasks/037-owner-strategy-approval.json",
            "source_receipt_sha256": (
                "b800bc1a713b914f20f0128ecc5d3296ed649064dc4d5609a4e229346c3329b5"
            ),
            "source_message_id": "01a04655-0e97-7560-94dd-47cb95d9fbe2",
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "spec_037_sha256": SHA256,
            "scope_ids": [
                "037.strategy.risk_based_baseline",
                "037.order.freeze_review_then_tier1_then_owner_gate_then_tier2",
                "037.tier1.local_ci_synthetic",
                "037.tier2.owner_sync_then_scrubbed_neon_develop",
                "037.tier3.narrow_read_only_smoke_when_separately_authorized",
                "037.physical_iphone.separate_acceptance",
            ],
            "source_qa_execution_status": "NOT_RUN",
            "source_scope_expires": None,
            "execution_authority": False,
            "manual_owner_t1_process_gate": {
                "recorded": True,
                "checked_at_utc": "2026-08-29T00:00:00Z",
                "checked_by": "T1",
                "audit_only": True,
            },
        },
        "manifest_core_sha256": SHA256,
        "git_status_porcelain_z_sha256": SHA256,
    }
    validate_schema(manifest, CONTRACT_DIR / "run-manifest.schema.json", label="manifest")


def test_matrix_expansion_is_deterministic_and_includes_external_cells() -> None:
    inventory = load_json(CONTRACT_DIR / "matrix-inventory.v1.json")
    first = expand_matrix(inventory)
    second = expand_matrix(copy.deepcopy(inventory))
    assert sha256_json(first) == sha256_json(second)
    ids = {row["acceptance_id"] for row in first}
    assert len(first) == len(ids)
    assert {
        "037-prod-readyz",
        "037-prod-topology",
        "037-device-iphone-layout",
        "037-device-ios-pwa",
        "037-device-real-push-single",
        "037-device-real-push-grouped",
    }.issubset(ids)
    checkpoints = load_json(CONTRACT_DIR / "screenshot-checkpoints.v1.json")
    assert {item["acceptance_id"] for item in checkpoints["checkpoints"]}.issubset(ids)


def test_matrix_duplicate_mutant_is_red_then_original_is_green() -> None:
    inventory = load_json(CONTRACT_DIR / "matrix-inventory.v1.json")
    mutant = copy.deepcopy(inventory)
    mutant["scenarios"].append(copy.deepcopy(mutant["scenarios"][0]))
    with pytest.raises(QaContractError, match="BLOCK_MATRIX_DUPLICATE"):
        expand_matrix(mutant)
    assert expand_matrix(inventory)


def test_commands_materialize_exact_bijection() -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    contract = load_json(CONTRACT_DIR / "command-contract.v1.json")
    assert {item["command_id"] for item in commands["commands"]} == {
        item["id"] for item in contract["commands"]
    }
    assert commands["command_bindings"] == contract["command_bindings"]


def test_command_argv_mutant_is_red_then_original_is_green() -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    manifest = _manifest()
    mutant = copy.deepcopy(commands)
    mutant["commands"][0]["argv"].append("--drift")
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        _verify_commands(mutant, manifest, REPO_ROOT, CONTRACT_DIR)
    assert _verify_commands(commands, manifest, REPO_ROOT, CONTRACT_DIR)


def test_owner_sync_candidate_mutant_is_red_then_original_is_green(monkeypatch) -> None:
    receipt = _owner_sync()
    monkeypatch.setattr(
        "scripts.validate_qa_run.utc_now",
        lambda: __import__("datetime").datetime(2026, 8, 29, 1, tzinfo=__import__("datetime").UTC),
    )
    mutant = copy.deepcopy(receipt)
    mutant["run_binding"]["candidate_sha"] = "e" * 40
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        validate_owner_sync(mutant, _manifest(), CONTRACT_DIR)
    validate_owner_sync(receipt, _manifest(), CONTRACT_DIR)


def test_activation_expiry_mutant_is_red_then_original_is_green(monkeypatch) -> None:
    activation = _activation()
    dt = __import__("datetime")
    monkeypatch.setattr(
        "scripts.validate_qa_run.utc_now", lambda: dt.datetime(2026, 8, 29, 1, tzinfo=dt.UTC)
    )
    mutant = copy.deepcopy(activation)
    mutant["expires_at_utc"] = "2026-08-29T00:30:00Z"
    with pytest.raises(QaContractError, match="BLOCK_ACTIVATION_EXPIRED"):
        validate_activation(mutant, _manifest(), CONTRACT_DIR)
    validate_activation(activation, _manifest(), CONTRACT_DIR)


def test_activation_structured_binding_and_executor_mutants_are_red_then_original_is_green(
    monkeypatch,
) -> None:
    activation = _activation()
    dt = __import__("datetime")
    monkeypatch.setattr(
        "scripts.validate_qa_run.utc_now", lambda: dt.datetime(2026, 8, 29, 1, tzinfo=dt.UTC)
    )
    structured_mutant = copy.deepcopy(activation)
    structured_mutant["structured_consent"]["spec_037_sha256"] = "e" * 64
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        validate_activation(structured_mutant, _manifest(), CONTRACT_DIR)
    executor_mutant = copy.deepcopy(activation)
    executor_mutant["executor"]["identity"] = "different-executor"
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        validate_activation(executor_mutant, _manifest(), CONTRACT_DIR)
    validate_activation(activation, _manifest(), CONTRACT_DIR)


def test_activation_profiles_require_each_exact_full_command_set(monkeypatch) -> None:
    dt = __import__("datetime")
    monkeypatch.setattr(
        "scripts.validate_qa_run.utc_now", lambda: dt.datetime(2026, 8, 29, 1, tzinfo=dt.UTC)
    )
    profiles = {
        "production_read_only_smoke": (
            "ACTIVATE_PRODUCTION_READ_ONLY_SMOKE",
            "NONE",
            ["prod.readyz", "prod.fly-topology"],
        ),
        "physical_iphone_layout_acceptance": (
            "ACTIVATE_PHYSICAL_IPHONE_LAYOUT",
            "IPHONE_PHYSICAL",
            ["device.iphone-acceptance"],
        ),
        "ios_pwa_acceptance": (
            "ACTIVATE_IOS_PWA",
            "IOS_PWA",
            ["device.ios-pwa-acceptance"],
        ),
        "real_web_push_acceptance": (
            "ACTIVATE_REAL_WEB_PUSH",
            "REAL_WEB_PUSH",
            ["device.real-web-push"],
        ),
    }
    for authority_type, (decision, device_token, command_ids) in profiles.items():
        activation = _activation()
        activation["authority_type"] = authority_type
        activation["structured_consent"]["decision"] = decision
        activation["structured_consent"]["allowed_command_ids"] = command_ids
        activation["target"]["device_token"] = device_token
        activation["allowed_command_ids"] = command_ids
        validate_activation(activation, _manifest(), CONTRACT_DIR)
        mutant = copy.deepcopy(activation)
        mutant["structured_consent"]["allowed_command_ids"] = ["prod.readyz"]
        with pytest.raises(QaContractError, match="FAIL_SCHEMA|BLOCK_ACTIVATION_COMMANDS"):
            validate_activation(mutant, _manifest(), CONTRACT_DIR)


def test_strategy_scope_expiry_and_schema_completeness_mutants_are_red() -> None:
    source = load_json(REPO_ROOT / "agent-tasks" / "037-owner-strategy-approval.json")
    scope_mutant = copy.deepcopy(source)
    scope_mutant["approved_scope"]["scope_ids"] = scope_mutant["approved_scope"]["scope_ids"][:-1]
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        validate_schema(
            scope_mutant,
            CONTRACT_DIR / "strategy-approval-source.schema.json",
            label="strategy",
        )
    expiry_mutant = copy.deepcopy(source)
    expiry_mutant["approved_scope"]["expires"] = "2026-08-30T00:00:00Z"
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        validate_schema(
            expiry_mutant,
            CONTRACT_DIR / "strategy-approval-source.schema.json",
            label="strategy",
        )
    order_mutant = copy.deepcopy(source)
    order_mutant["approved_scope"]["scope_ids"] = list(
        reversed(order_mutant["approved_scope"]["scope_ids"])
    )
    validate_schema(
        order_mutant,
        CONTRACT_DIR / "strategy-approval-source.schema.json",
        label="strategy",
    )
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        validate_strategy_source_semantics(order_mutant)
    validate_strategy_source_semantics(source)


def test_strategy_runtime_binding_status_expiry_and_scope_mutants_are_red_then_green() -> None:
    source = load_json(REPO_ROOT / "agent-tasks" / "037-owner-strategy-approval.json")
    manifest = _manifest()
    manifest["strategy_approval_binding"] = {
        "schema_version": "037-strategy-approval-binding/v1",
        "source_receipt_path": "agent-tasks/037-owner-strategy-approval.json",
        "source_receipt_sha256": (
            "b800bc1a713b914f20f0128ecc5d3296ed649064dc4d5609a4e229346c3329b5"
        ),
        "source_message_id": "01a04655-0e97-7560-94dd-47cb95d9fbe2",
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "spec_037_sha256": SHA256,
        "scope_ids": source["structured_consent"]["scope_ids"],
        "source_qa_execution_status": "NOT_RUN",
        "source_scope_expires": None,
        "execution_authority": False,
        "manual_owner_t1_process_gate": {
            "recorded": True,
            "checked_at_utc": "2026-08-29T00:00:00Z",
            "checked_by": "T1",
            "audit_only": True,
        },
    }
    scope_mutant = copy.deepcopy(manifest)
    scope_mutant["strategy_approval_binding"]["scope_ids"] = list(
        reversed(scope_mutant["strategy_approval_binding"]["scope_ids"])
    )
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        _verify_strategy_binding(scope_mutant, source, CONTRACT_DIR)
    status_mutant = copy.deepcopy(manifest)
    status_mutant["strategy_approval_binding"]["source_qa_execution_status"] = "PASS"
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        _verify_strategy_binding(status_mutant, source, CONTRACT_DIR)
    expiry_mutant = copy.deepcopy(manifest)
    expiry_mutant["strategy_approval_binding"]["source_scope_expires"] = "never"
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        _verify_strategy_binding(expiry_mutant, source, CONTRACT_DIR)
    _verify_strategy_binding(manifest, source, CONTRACT_DIR)


def test_catalog_authority_contains_full_rows_and_constraint_backing_indexes() -> None:
    catalog = load_json(CONTRACT_DIR / "expected-catalog-fixtures.v1.json")["catalog_expected"]
    assert all(
        isinstance(column, dict)
        and {
            "name",
            "data_type",
            "not_null",
            "default_expr",
        }.issubset(column)
        for table in catalog["tables"]
        for column in table["columns"]
    )
    assert all(
        isinstance(item, dict) and {"name", "type", "validated", "definition"}.issubset(item)
        for item in catalog["constraints"]
    )
    assert all(
        isinstance(item, dict) and {"name", "table", "definition"}.issubset(item)
        for item in catalog["indexes"]
    )
    assert {"alembic_version_pkc", "pk_app_setting", "uq_app_setting_key"}.issubset(
        {item["name"] for item in catalog["indexes"]}
    )
    assert all(
        isinstance(item, dict)
        and {"name", "table", "function_schema", "function_name", "enabled", "definition"}.issubset(
            item
        )
        for item in catalog["triggers"]
    )


def _catalog_structure_raw() -> tuple[dict, dict]:
    expected = load_json(CONTRACT_DIR / "expected-catalog-fixtures.v1.json")["catalog_expected"]
    type_codes = {"CHECK": "c", "FOREIGN_KEY": "f", "PRIMARY_KEY": "p", "UNIQUE": "u"}
    raw = {
        "objects": [
            {
                "schema_name": expected["schema"],
                "relkind": "r",
                "relname": table["name"],
                "owner": table["owner"],
            }
            for table in expected["tables"]
        ],
        "columns": [
            {
                "schema_name": expected["schema"],
                "table_name": table["name"],
                "attnum": attnum,
                "attname": column["name"],
                "data_type": column["data_type"],
                "attnotnull": column["not_null"],
                "default_expr": column["default_expr"],
            }
            for table in expected["tables"]
            for attnum, column in enumerate(table["columns"], 1)
        ],
        "constraints": [
            {
                "schema_name": expected["schema"],
                "table_name": item["table"],
                "conname": item["name"],
                "contype": type_codes[item["type"]],
                "convalidated": item["validated"],
                "definition": item["definition"],
            }
            for item in expected["constraints"]
        ],
        "indexes": [
            {
                "schemaname": expected["schema"],
                "tablename": item["table"],
                "indexname": item["name"],
                "indexdef": item["definition"],
            }
            for item in expected["indexes"]
        ],
        "triggers": [
            {
                "schema_name": expected["schema"],
                "table_name": item["table"],
                "tgname": item["name"],
                "function_schema": item["function_schema"],
                "function_name": item["function_name"],
                "tgenabled": item["enabled"],
                "definition": item["definition"],
            }
            for item in expected["triggers"]
        ],
    }
    return raw, expected


def test_catalog_full_field_mutants_are_red_then_frozen_authority_is_green() -> None:
    raw, expected = _catalog_structure_raw()
    index_mutant = copy.deepcopy(raw)
    index_mutant["indexes"] = [
        item for item in index_mutant["indexes"] if item["indexname"] != "pk_app_setting"
    ]
    with pytest.raises(QaContractError, match="FAIL_P0_CATALOG_INDEXES"):
        validate_catalog_structure(index_mutant, expected)
    column_mutant = copy.deepcopy(raw)
    column_mutant["columns"][0]["data_type"] = "text"
    with pytest.raises(QaContractError, match="FAIL_P0_CATALOG_COLUMNS"):
        validate_catalog_structure(column_mutant, expected)
    constraint_mutant = copy.deepcopy(raw)
    constraint_mutant["constraints"][0]["definition"] = "PRIMARY KEY (wrong_column)"
    with pytest.raises(QaContractError, match="FAIL_P0_CATALOG_CONSTRAINTS"):
        validate_catalog_structure(constraint_mutant, expected)
    trigger_mutant = copy.deepcopy(raw)
    trigger_mutant["triggers"][0]["tgenabled"] = "D"
    with pytest.raises(QaContractError, match="FAIL_P0_CATALOG_TRIGGERS"):
        validate_catalog_structure(trigger_mutant, expected)
    validate_catalog_structure(raw, expected)


def _explicit_grants_raw() -> tuple[list[dict], dict]:
    expected = load_json(CONTRACT_DIR / "expected-catalog-fixtures.v1.json")["catalog_expected"]
    grants = expected["grants"]
    rows = []
    for table in expected["tables"]:
        for privilege in grants["microsched_migrator_table_privileges"]:
            rows.append(
                {
                    "schema_name": expected["schema"],
                    "relkind": "r",
                    "relname": table["name"],
                    "grantee": "microsched_migrator",
                    "privilege_type": privilege,
                    "is_grantable": False,
                }
            )
    for table_name in grants["microsched_app_tables"]:
        for privilege in grants["microsched_app_table_privileges"]:
            rows.append(
                {
                    "schema_name": expected["schema"],
                    "relkind": "r",
                    "relname": table_name,
                    "grantee": "microsched_app",
                    "privilege_type": privilege,
                    "is_grantable": False,
                }
            )
    for sequence in expected["sequences"]:
        for privilege in grants["microsched_migrator_sequence_privileges"]:
            rows.append(
                {
                    "schema_name": expected["schema"],
                    "relkind": "S",
                    "relname": sequence["name"],
                    "grantee": "microsched_migrator",
                    "privilege_type": privilege,
                    "is_grantable": False,
                }
            )
    for sequence_name in grants["microsched_app_sequences"]:
        for privilege in grants["microsched_app_sequence_privileges"]:
            rows.append(
                {
                    "schema_name": expected["schema"],
                    "relkind": "S",
                    "relname": sequence_name,
                    "grantee": "microsched_app",
                    "privilege_type": privilege,
                    "is_grantable": False,
                }
            )
    return rows, expected


def test_explicit_grants_extra_object_grant_mutant_is_red() -> None:
    rows, expected = _explicit_grants_raw()
    mutant = copy.deepcopy(rows)
    mutant.append(
        {
            "schema_name": expected["schema"],
            "relkind": "r",
            "relname": "alembic_version",
            "grantee": "microsched_app",
            "privilege_type": "SELECT",
            "is_grantable": False,
        }
    )
    with pytest.raises(QaContractError, match="FAIL_P0_EXPLICIT_GRANTS"):
        validate_explicit_grants(mutant, expected)


def test_explicit_grants_migrator_privilege_drift_mutant_is_red() -> None:
    rows, expected = _explicit_grants_raw()
    mutant = [
        copy.deepcopy(item)
        for item in rows
        if not (
            item["relname"] == "app_setting"
            and item["grantee"] == "microsched_migrator"
            and item["privilege_type"] == "MAINTAIN"
        )
    ]
    with pytest.raises(QaContractError, match="FAIL_P0_EXPLICIT_GRANTS"):
        validate_explicit_grants(mutant, expected)


def test_explicit_grants_grantable_mutant_is_red() -> None:
    rows, expected = _explicit_grants_raw()
    mutant = copy.deepcopy(rows)
    next(item for item in mutant if item["grantee"] == "microsched_app")["is_grantable"] = True
    with pytest.raises(QaContractError, match="FAIL_P0_EXPLICIT_GRANTS"):
        validate_explicit_grants(mutant, expected)


def test_explicit_grants_duplicate_mutant_is_red_then_exact_authority_is_green() -> None:
    rows, expected = _explicit_grants_raw()
    mutant = copy.deepcopy(rows)
    mutant.append(copy.deepcopy(mutant[0]))
    with pytest.raises(QaContractError, match="FAIL_P0_EXPLICIT_GRANT_DUPLICATE"):
        validate_explicit_grants(mutant, expected)
    validate_explicit_grants(rows, expected)


def test_cleanup_bindings_encode_exact_reverse_order() -> None:
    bindings = load_json(CONTRACT_DIR / "command-contract.v1.json")["command_bindings"]
    assert bindings["docker.cleanup-app"]["depends_on"] == ["docker.cleanup-scope"]
    assert bindings["pg.cleanup-db-roles"]["depends_on"] == [
        "docker.cleanup-scope",
        "docker.cleanup-app",
        "pg.synthetic-dsn-provenance",
    ]
    assert bindings["docker.cleanup-pg"]["depends_on"] == [
        "docker.cleanup-scope",
        "docker.cleanup-app",
    ]
    assert bindings["docker.cleanup-pg"]["depends_on_terminal"] == ["pg.cleanup-db-roles"]
    assert bindings["docker.cleanup-network"]["depends_on"] == [
        "docker.cleanup-scope",
        "docker.cleanup-pg",
    ]
    assert bindings["docker.cleanup-image"]["depends_on"] == [
        "docker.cleanup-scope",
        "docker.cleanup-network",
    ]
    assert bindings["docker.cleanup-zero"]["depends_on"] == ["docker.cleanup-image"]


def test_bootstrap_empty_acl_tuple_mutant_is_red_then_original_is_green() -> None:
    expected = {"raw_row_count": 0, "raw_tuples": []}
    mutant = {
        "raw_row_count": 1,
        "raw_tuples": [
            {
                "owner": "postgres",
                "schema_name": "GLOBAL",
                "object_kind": "r",
                "acl_item_count": 0,
                "acl_text": "{}",
            }
        ],
    }
    with pytest.raises(QaContractError, match="FAIL_P0_EXTRA_BOOTSTRAP_DEFAULT_ACL_TUPLE"):
        validate_bootstrap_default_acl_raw(mutant, expected)
    validate_bootstrap_default_acl_raw(expected, expected)


def test_schema_unknown_field_mutant_is_red() -> None:
    receipt = _owner_sync()
    receipt["unexpected"] = True
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        validate_schema(receipt, CONTRACT_DIR / "authority-receipts.schema.json", label="receipt")


def test_strategy_approval_mutant_is_red_then_frozen_source_is_green() -> None:
    source = load_json(REPO_ROOT / "agent-tasks" / "037-owner-strategy-approval.json")
    mutant = copy.deepcopy(source)
    mutant["structured_consent"]["execution_authority"] = True
    with pytest.raises(QaContractError, match="FAIL_SCHEMA"):
        validate_schema(
            mutant,
            CONTRACT_DIR / "strategy-approval-source.schema.json",
            label="strategy",
        )
    validate_schema(
        source,
        CONTRACT_DIR / "strategy-approval-source.schema.json",
        label="strategy",
    )


def test_command_cwd_and_oracle_mutants_are_red_then_original_is_green() -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    manifest = _manifest()
    cwd_mutant = copy.deepcopy(commands)
    cwd_mutant["commands"][0]["cwd"] = "."
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        _verify_commands(cwd_mutant, manifest, REPO_ROOT, CONTRACT_DIR)
    oracle_mutant = copy.deepcopy(commands)
    oracle_mutant["commands"][0]["oracle_ids"] = ["self-authored-oracle"]
    with pytest.raises(QaContractError, match="BLOCK_BINDING_MISMATCH"):
        _verify_commands(oracle_mutant, manifest, REPO_ROOT, CONTRACT_DIR)
    assert _verify_commands(commands, manifest, REPO_ROOT, CONTRACT_DIR)


def test_duplicate_json_receipt_key_mutant_is_red_then_unique_is_green() -> None:
    with pytest.raises(QaContractError, match="FAIL_DUPLICATE_JSON_KEY"):
        strict_json_loads('{"receipt_id":"a","receipt_id":"b"}', source="fixture")
    assert strict_json_loads('{"receipt_id":"a"}', source="fixture") == {"receipt_id": "a"}


def test_docker_label_mutant_is_red_then_run_binding_is_green(tmp_path, monkeypatch) -> None:
    host_values, container_values = build_env_pair(
        run_id=RUN_ID,
        network=f"microsched-qa-{RUN_ID}",
        pg_container=f"microsched-qa-pg-{RUN_ID}",
        candidate_sha=CANDIDATE,
        host_port=55432,
    )
    host_env_file = tmp_path / "synthetic-host.env"
    container_env_file = tmp_path / "synthetic-container.env"
    host_env_file.write_text(
        "".join(f"{name}={host_values[name]}\n" for name in ENV_NAMES), encoding="utf-8"
    )
    container_env_file.write_text(
        "".join(f"{name}={container_values[name]}\n" for name in ENV_NAMES), encoding="utf-8"
    )
    monkeypatch.setattr(
        "scripts.validate_synthetic_pg_target.scan_forbidden_environment", lambda: None
    )
    container_result = [
        {
            "Id": "container-id",
            "Name": f"/microsched-qa-pg-{RUN_ID}",
            "Config": {"Labels": {"microsched.qa.run_id": "wrong-run"}},
            "NetworkSettings": {
                "Networks": {f"microsched-qa-{RUN_ID}": {}},
                "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]},
            },
        }
    ]
    network_result = [
        {
            "Id": "network-id",
            "Name": f"microsched-qa-{RUN_ID}",
            "Labels": {"microsched.qa.run_id": RUN_ID},
        }
    ]
    monkeypatch.setattr(
        "scripts.validate_synthetic_pg_target._docker_json",
        lambda *args: container_result if args[0] == "container" else network_result,
    )
    with pytest.raises(QaContractError, match="FAIL_P0_CONTAINER_LABEL"):
        validate_target(
            run_id=RUN_ID,
            candidate_sha=CANDIDATE,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            host_env_file=host_env_file,
            container_env_file=container_env_file,
            expected_run_dir=tmp_path,
        )
    container_result[0]["Config"]["Labels"]["microsched.qa.run_id"] = RUN_ID
    receipt = validate_target(
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        network=f"microsched-qa-{RUN_ID}",
        pg_container=f"microsched-qa-pg-{RUN_ID}",
        host_env_file=host_env_file,
        container_env_file=container_env_file,
        expected_run_dir=tmp_path,
    )
    assert receipt["run_id"] == RUN_ID
    assert receipt["host_binding"]["loopback_host"] == "127.0.0.1"
    assert receipt["container_binding"]["network_host"] == f"microsched-qa-pg-{RUN_ID}"
    serialized_receipt = json.dumps(receipt)
    assert "postgresql" not in serialized_receipt
    assert host_values["ENCRYPTION_MASTER_KEY"] not in serialized_receipt
    assert container_values["OAUTH_STATE_SECRET"] not in serialized_receipt

    host_mutant = dict(host_values)
    host_mutant["DATABASE_URL"] = host_mutant["DATABASE_URL"].replace(
        "127.0.0.1", f"microsched-qa-pg-{RUN_ID}"
    )
    host_env_file.write_text(
        "".join(f"{name}={host_mutant[name]}\n" for name in ENV_NAMES), encoding="utf-8"
    )
    with pytest.raises(QaContractError, match="FAIL_P0_SYNTHETIC_HOST"):
        validate_target(
            run_id=RUN_ID,
            candidate_sha=CANDIDATE,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            host_env_file=host_env_file,
            container_env_file=container_env_file,
            expected_run_dir=tmp_path,
        )
    host_env_file.write_text(
        "".join(f"{name}={host_values[name]}\n" for name in ENV_NAMES), encoding="utf-8"
    )
    container_result[0]["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(QaContractError, match="FAIL_P0_CONTAINER_PORT_BINDING"):
        validate_target(
            run_id=RUN_ID,
            candidate_sha=CANDIDATE,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            host_env_file=host_env_file,
            container_env_file=container_env_file,
            expected_run_dir=tmp_path,
        )


def test_command_dependency_blocks_before_subprocess(tmp_path) -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    (tmp_path / "raw" / "commands").mkdir(parents=True)
    (tmp_path / "commands.json").write_text(json.dumps(commands), encoding="utf-8")
    (tmp_path / "run-manifest.json").write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "candidate_sha": CANDIDATE,
                "manifest_core_sha256": SHA256,
            }
        ),
        encoding="utf-8",
    )
    result = execute(
        run_dir=tmp_path,
        command_id="backend.ruff-check",
        attempt=1,
        placeholder_values={},
    )
    assert result["status"] == "BLOCKED"
    assert result["actual_exit"] is None
    assert "qa.preflight" in result["oracle_results"][0]["detail"]


def test_executable_launch_oserror_becomes_terminal_receipt(tmp_path, monkeypatch) -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    (tmp_path / "raw" / "commands").mkdir(parents=True)
    _write_json(tmp_path / "commands.json", commands)
    _write_json(
        tmp_path / "run-manifest.json",
        {
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "manifest_core_sha256": SHA256,
        },
    )
    (tmp_path / "command-results.json").write_text(
        json.dumps([{"command_id": "qa.preflight", "status": "PASS", "attempt": 1}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.run_qa_command.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("missing executable")),
    )
    result = execute(
        run_dir=tmp_path,
        command_id="frontend.lint",
        attempt=1,
        placeholder_values={},
    )
    assert result["status"] == "FAIL"
    assert result["actual_exit"] is None
    assert result["oracle_results"][0]["detail"] == "executable launch failed"
    assert (
        (tmp_path / result["stderr_path"])
        .read_text(encoding="utf-8")
        .startswith("executable_launch_error=FileNotFoundError")
    )


def test_windows_command_resolution_uses_cmd_without_changing_approved_argv(
    tmp_path, monkeypatch
) -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    command = next(item for item in commands["commands"] if item["command_id"] == "frontend.lint")
    approved_argv_sha = command["argv_sha256"]
    (tmp_path / "raw" / "commands").mkdir(parents=True)
    _write_json(tmp_path / "commands.json", commands)
    _write_json(
        tmp_path / "run-manifest.json",
        {"run_id": RUN_ID, "candidate_sha": CANDIDATE, "manifest_core_sha256": SHA256},
    )
    _write_json(
        tmp_path / "command-results.json",
        [{"command_id": "qa.preflight", "status": "PASS", "attempt": 1}],
    )
    observed: list[list[str]] = []
    monkeypatch.setattr("scripts.run_qa_command.shutil.which", lambda _name: "C:/tools/npm.CMD")

    def fake_run(argv, **_kwargs):
        observed.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=b"ok\n", stderr=b"")

    monkeypatch.setattr("scripts.run_qa_command.subprocess.run", fake_run)
    result = execute(run_dir=tmp_path, command_id="frontend.lint", attempt=1, placeholder_values={})
    assert result["status"] == "PASS"
    assert observed[0][0] == "C:/tools/npm.CMD"
    assert command["argv"] == ["npm", "run", "lint"]
    assert result["argv_sha256"] == approved_argv_sha


def test_dual_context_pg_topology_is_explicit_in_command_contract() -> None:
    contract = load_json(CONTRACT_DIR / "command-contract.v1.json")
    commands = {item["id"]: item for item in contract["commands"]}
    pg_create = commands["docker.pg-create"]["argv"]
    assert ["--publish", "127.0.0.1::5432"] == pg_create[
        pg_create.index("--publish") : pg_create.index("--publish") + 2
    ]
    assert {
        "<synthetic-host-env-path>",
        "<synthetic-container-env-path>",
        "<synthetic-dsn-receipt-path>",
    }.issubset(contract["allowed_placeholders"])
    env_create = commands["docker.synthetic-env-create"]["argv"]
    assert "<synthetic-host-env-path>" in env_create
    assert "<synthetic-container-env-path>" in env_create
    assert (
        commands["docker.app-create"]["argv"][
            commands["docker.app-create"]["argv"].index("--env-file") + 1
        ]
        == "<synthetic-container-env-path>"
    )


def test_pytest_pg_privilege_elevation_is_explicit_and_bounded() -> None:
    module = importlib.import_module("scripts.run_qa_pg_command")
    values = {
        "CI_PG_BOOTSTRAP_URL": "postgresql://bootstrap/qa",
        "NEON_MIGRATOR_URL": "postgresql://migrator/qa",
        "CI_APP_DATABASE_URL": "postgresql://app/qa",
        "DATABASE_URL": "postgresql://app/qa",
    }
    command = ["uv", "run", "pytest", "-m", "pg"]

    default_env = module.build_child_environment(
        validated_values=values,
        command=command,
        use_validated_bootstrap_as_pytest_migrator=False,
        process_environment={},
    )
    assert default_env["NEON_MIGRATOR_URL"] == values["NEON_MIGRATOR_URL"]

    pytest_env = module.build_child_environment(
        validated_values=values,
        command=command,
        use_validated_bootstrap_as_pytest_migrator=True,
        process_environment={},
    )
    assert pytest_env["NEON_MIGRATOR_URL"] == values["CI_PG_BOOTSTRAP_URL"]
    assert pytest_env["CI_PG_BOOTSTRAP_URL"] == values["CI_PG_BOOTSTRAP_URL"]

    with pytest.raises(QaContractError, match="FAIL_PG_WRAPPER_PYTEST_ELEVATION_SCOPE"):
        module.build_child_environment(
            validated_values=values,
            command=["uv", "run", "alembic", "upgrade", "head"],
            use_validated_bootstrap_as_pytest_migrator=True,
            process_environment={},
        )

    with pytest.raises(SystemExit):
        module._parser().parse_args(
            [
                "--synthetic-dsn-receipt",
                "receipt.json",
                "--run-id",
                RUN_ID,
                "--pytest-use-validated-bootstrap-as-migrator=postgresql://foreign/qa",
                "--",
                *command,
            ]
        )


def test_only_materialized_pytest_pg_commands_request_bounded_elevation() -> None:
    contract = load_json(CONTRACT_DIR / "command-contract.v1.json")
    elevated = {
        item["id"]
        for item in contract["commands"]
        if "--pytest-use-validated-bootstrap-as-migrator" in item["argv"]
    }
    assert elevated == {
        "backend.pytest-pg",
        "dep.035A.pytest-pg",
        "dep.035B.pytest-pg",
    }
    for item in contract["commands"]:
        if item["id"] in elevated:
            marker = item["argv"].index("--")
            assert item["argv"][marker + 1 :] == ["uv", "run", "pytest", "-m", "pg"]


def test_negative_0012_fixture_values_are_type_decoded() -> None:
    module = importlib.import_module("scripts.verify_migration_0012_negative")
    decoded = module.decode_fixture_row(
        {
            "table": "tracker_reminder_batch",
            "id": "019d0000-0000-7000-8000-000000000001",
            "occurrence_on": "2026-08-28",
            "reminder_time": "08:00:00",
            "generation": 1,
        }
    )
    assert decoded["id"] == uuid.UUID("019d0000-0000-7000-8000-000000000001")
    assert decoded["occurrence_on"] == date(2026, 8, 28)
    assert decoded["reminder_time"] == time(8, 0)
    assert decoded["generation"] == 1


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("uuid", "not-a-uuid"),
        ("date", "2026-02-30"),
        ("time", "25:00:00"),
        ("uuid", 123),
        ("unsupported-type", "value"),
    ],
)
def test_negative_0012_typed_fixture_values_fail_closed(kind, value) -> None:
    module = importlib.import_module("scripts.verify_migration_0012_negative")
    with pytest.raises(QaContractError, match="FAIL_P0_FIXTURE_TYPED_VALUE"):
        module.decode_typed_fixture_value(kind, value)


class _ReadyResponse:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_readyz_wait_retries_only_transient_startup_then_passes() -> None:
    module = importlib.import_module("scripts.qa_readyz_probe")
    calls = 0
    sleeps: list[float] = []

    def opening(url: str, *, timeout: float):
        nonlocal calls
        calls += 1
        assert url == "http://127.0.0.1:8000/api/readyz"
        assert 0 < timeout <= 10
        if calls == 1:
            raise urllib.error.URLError(ConnectionRefusedError())
        if calls == 2:
            raise urllib.error.HTTPError(url, 503, "unavailable", None, None)
        return _ReadyResponse({"status": "ok", "db": "up", "commit": CANDIDATE})

    module.wait_for_readyz(
        expected_commit=CANDIDATE,
        url="http://127.0.0.1:8000/api/readyz",
        timeout_seconds=90,
        open_fn=opening,
        sleep_fn=sleeps.append,
        monotonic_fn=lambda: 0.0,
    )
    assert calls == 3
    assert sleeps == [1.0, 1.0]


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"status": "ok", "db": "up", "commit": "f" * 40}, "FAIL_COMMIT"),
        ({"status": "starting", "db": "down", "commit": CANDIDATE}, "FAIL_HEALTH"),
    ],
)
def test_readyz_wait_fails_immediately_on_terminal_payload(payload, expected_error) -> None:
    module = importlib.import_module("scripts.qa_readyz_probe")
    opened = 0

    def opening(_url: str, *, timeout: float):
        nonlocal opened
        opened += 1
        return _ReadyResponse(payload)

    with pytest.raises(module.ReadyzProbeError, match=expected_error):
        module.wait_for_readyz(
            expected_commit=CANDIDATE,
            url="http://127.0.0.1:8000/api/readyz",
            timeout_seconds=90,
            open_fn=opening,
            sleep_fn=lambda _seconds: pytest.fail("terminal payload must not retry"),
            monotonic_fn=lambda: 0.0,
        )
    assert opened == 1


def test_readyz_wait_fails_immediately_on_malformed_payload() -> None:
    module = importlib.import_module("scripts.qa_readyz_probe")
    response = _ReadyResponse({})
    response._payload = b"{"
    with pytest.raises(module.ReadyzProbeError, match="FAIL_PAYLOAD"):
        module.wait_for_readyz(
            expected_commit=CANDIDATE,
            url="http://127.0.0.1:8000/api/readyz",
            timeout_seconds=90,
            open_fn=lambda _url, timeout: response,
            sleep_fn=lambda _seconds: pytest.fail("malformed payload must not retry"),
            monotonic_fn=lambda: 0.0,
        )


def test_readyz_wait_is_bounded_to_90_seconds_and_times_out_without_payload_leak() -> None:
    module = importlib.import_module("scripts.qa_readyz_probe")
    with pytest.raises(module.ReadyzProbeError, match="FAIL_TIMEOUT_BOUND"):
        module.wait_for_readyz(
            expected_commit=CANDIDATE,
            url="http://127.0.0.1:8000/api/readyz",
            timeout_seconds=91,
            open_fn=lambda *_args, **_kwargs: pytest.fail("invalid bound must fail before probe"),
            sleep_fn=lambda _seconds: None,
            monotonic_fn=lambda: 0.0,
        )

    clock = iter([0.0, 0.0, 90.0])
    with pytest.raises(module.ReadyzProbeError, match="FAIL_STARTUP_TIMEOUT") as error:
        module.wait_for_readyz(
            expected_commit=CANDIDATE,
            url="http://127.0.0.1:8000/api/readyz",
            timeout_seconds=90,
            open_fn=lambda _url, timeout: (_ for _ in ()).throw(
                urllib.error.URLError(ConnectionRefusedError("sensitive-target"))
            ),
            sleep_fn=lambda _seconds: pytest.fail("deadline reached before retry"),
            monotonic_fn=lambda: next(clock),
        )
    assert "sensitive-target" not in str(error.value)


def test_pg18_mount_and_health_contract_are_self_validating() -> None:
    contract = load_json(CONTRACT_DIR / "command-contract.v1.json")
    commands = {item["id"]: item for item in contract["commands"]}
    pg_create = commands["docker.pg-create"]["argv"]
    assert pg_create[pg_create.index("--tmpfs") + 1] == "/var/lib/postgresql"
    assert pg_create.count("--tmpfs") == 1
    assert "--volume" not in pg_create
    assert "--mount" not in pg_create
    assert "/var/lib/postgresql/data" not in pg_create
    health = commands["docker.pg-health"]
    assert health["cwd"] == "backend"
    assert health["argv"][:5] == ["uv", "run", "python", "-m", "scripts.wait_qa_pg_healthy"]
    assert "<pgvector-pg18-ref>" in health["argv"]
    assert health["argv"][health["argv"].index("--timeout-seconds") + 1] == "90"
    env_create = commands["docker.synthetic-env-create"]
    assert "<pgvector-pg18-ref>" in env_create["argv"]
    assert contract["command_bindings"]["docker.synthetic-env-create"]["depends_on"] == [
        "docker.pg-health"
    ]


def _pg_health_snapshot(*, state: str = "running", health: str = "healthy") -> dict:
    running = state == "running"
    return {
        "Id": "container-id",
        "Name": f"/microsched-qa-pg-{RUN_ID}",
        "Image": "sha256:" + "e" * 64,
        "Config": {
            "Image": "pgvector/pgvector@sha256:" + "d" * 64,
            "Labels": {"microsched.qa.run_id": RUN_ID},
        },
        "State": {
            "Status": state,
            "Running": running,
            "OOMKilled": False,
            "Dead": False,
            "Restarting": False,
            "ExitCode": 0 if running else 1,
            "Health": {"Status": health},
        },
        "NetworkSettings": {
            "Networks": {f"microsched-qa-{RUN_ID}": {}},
            "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]},
        },
    }


def test_pg_health_validator_rejects_terminal_exit_immediately() -> None:
    module = importlib.import_module("scripts.wait_qa_pg_healthy")
    snapshot = _pg_health_snapshot(state="exited", health="unhealthy")
    with pytest.raises(QaContractError, match="FAIL_P0_PG_TERMINAL_STATE"):
        module.validate_pg_snapshot(
            snapshot,
            run_id=RUN_ID,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            expected_image="pgvector/pgvector@sha256:" + "d" * 64,
            expected_image_id="sha256:" + "e" * 64,
        )


def test_pg_health_validator_accepts_only_exact_healthy_loopback_binding() -> None:
    module = importlib.import_module("scripts.wait_qa_pg_healthy")
    snapshot = _pg_health_snapshot()
    assert (
        module.validate_pg_snapshot(
            snapshot,
            run_id=RUN_ID,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            expected_image="pgvector/pgvector@sha256:" + "d" * 64,
            expected_image_id="sha256:" + "e" * 64,
        )
        == 55432
    )
    snapshot["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(QaContractError, match="FAIL_P0_PG_PORT_BINDING"):
        module.validate_pg_snapshot(
            snapshot,
            run_id=RUN_ID,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            expected_image="pgvector/pgvector@sha256:" + "d" * 64,
            expected_image_id="sha256:" + "e" * 64,
        )


@pytest.mark.parametrize(
    ("mutant", "error_code"),
    [
        ("wrong-label", "FAIL_P0_PG_LABEL_BINDING"),
        ("wrong-network", "FAIL_P0_PG_NETWORK_BINDING"),
        ("wrong-image", "FAIL_P0_PG_IMAGE_BINDING"),
        ("restarting", "FAIL_P0_PG_UNSAFE_STATE"),
        ("empty-port", "FAIL_P0_PG_PORT_BINDING"),
    ],
)
def test_pg_health_validator_rejects_identity_state_and_port_mutants(
    mutant: str, error_code: str
) -> None:
    module = importlib.import_module("scripts.wait_qa_pg_healthy")
    snapshot = _pg_health_snapshot()
    if mutant == "wrong-label":
        snapshot["Config"]["Labels"]["microsched.qa.run_id"] = (
            "019ba312-6a10-7000-8000-000000000002"
        )
    elif mutant == "wrong-network":
        snapshot["NetworkSettings"]["Networks"] = {"foreign-network": {}}
    elif mutant == "wrong-image":
        snapshot["Image"] = "sha256:" + "f" * 64
    elif mutant == "restarting":
        snapshot["State"]["Restarting"] = True
    else:
        snapshot["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = ""
    with pytest.raises(QaContractError, match=error_code):
        module.validate_pg_snapshot(
            snapshot,
            run_id=RUN_ID,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            expected_image="pgvector/pgvector@sha256:" + "d" * 64,
            expected_image_id="sha256:" + "e" * 64,
        )


def test_pg_health_wait_is_bounded_and_accepts_only_after_healthy() -> None:
    module = importlib.import_module("scripts.wait_qa_pg_healthy")
    snapshots = iter(
        [_pg_health_snapshot(health="starting"), _pg_health_snapshot(health="healthy")]
    )
    clock = iter([0.0, 0.0, 0.5])
    image = {
        "Id": "sha256:" + "e" * 64,
        "RepoDigests": ["pgvector/pgvector@sha256:" + "d" * 64],
    }
    assert (
        module.wait_for_healthy(
            run_id=RUN_ID,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            expected_image="pgvector/pgvector@sha256:" + "d" * 64,
            timeout_seconds=90,
            container_inspect_fn=lambda _target: next(snapshots),
            image_inspect_fn=lambda _target: image,
            sleep_fn=lambda _seconds: None,
            monotonic_fn=lambda: next(clock),
        )
        == 55432
    )


def test_pg_health_wait_does_not_poll_after_terminal_exit() -> None:
    module = importlib.import_module("scripts.wait_qa_pg_healthy")
    inspect_count = 0

    def terminal_inspect(_target: str) -> dict:
        nonlocal inspect_count
        inspect_count += 1
        return _pg_health_snapshot(state="exited", health="unhealthy")

    image = {
        "Id": "sha256:" + "e" * 64,
        "RepoDigests": ["pgvector/pgvector@sha256:" + "d" * 64],
    }
    with pytest.raises(QaContractError, match="FAIL_P0_PG_TERMINAL_STATE"):
        module.wait_for_healthy(
            run_id=RUN_ID,
            network=f"microsched-qa-{RUN_ID}",
            pg_container=f"microsched-qa-pg-{RUN_ID}",
            expected_image="pgvector/pgvector@sha256:" + "d" * 64,
            timeout_seconds=90,
            container_inspect_fn=terminal_inspect,
            image_inspect_fn=lambda _target: image,
            sleep_fn=lambda _seconds: pytest.fail("terminal state must not sleep"),
            monotonic_fn=lambda: 0.0,
        )
    assert inspect_count == 1


def test_cleanup_pg_waits_for_db_cleanup_attempt_but_not_pass() -> None:
    binding = load_json(CONTRACT_DIR / "command-contract.v1.json")["command_bindings"][
        "docker.cleanup-pg"
    ]
    assert binding["depends_on"] == ["docker.cleanup-scope", "docker.cleanup-app"]
    assert binding["depends_on_terminal"] == ["pg.cleanup-db-roles"]


def test_cleanup_pg_is_blocked_until_db_cleanup_terminal_then_runs_after_failure(
    tmp_path, monkeypatch
) -> None:
    commands = materialize_commands(
        repo_root=REPO_ROOT,
        run_id=RUN_ID,
        candidate_sha=CANDIDATE,
        contract_dir=CONTRACT_DIR,
    )
    (tmp_path / "raw" / "commands").mkdir(parents=True)
    _write_json(tmp_path / "commands.json", commands)
    _write_json(
        tmp_path / "run-manifest.json",
        {"run_id": RUN_ID, "candidate_sha": CANDIDATE, "manifest_core_sha256": SHA256},
    )
    prerequisites = [
        {"command_id": command_id, "status": "PASS", "attempt": 1}
        for command_id in ("docker.cleanup-scope", "docker.cleanup-app")
    ]
    _write_json(tmp_path / "command-results.json", prerequisites)
    blocked = execute(
        run_dir=tmp_path, command_id="docker.cleanup-pg", attempt=1, placeholder_values={}
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["oracle_results"][0]["detail"].startswith("DEPENDENCY_NOT_TERMINAL")

    prerequisites.append({"command_id": "pg.cleanup-db-roles", "status": "FAIL_P0", "attempt": 1})
    _write_json(tmp_path / "command-results.json", prerequisites)
    monkeypatch.setattr("scripts.run_qa_command.shutil.which", lambda name: name)
    monkeypatch.setattr(
        "scripts.run_qa_command.subprocess.run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, stdout=b"removed\n", stderr=b""
        ),
    )
    allowed = execute(
        run_dir=tmp_path, command_id="docker.cleanup-pg", attempt=1, placeholder_values={}
    )
    assert allowed["status"] == "PASS"


def test_exact_cleanup_rejects_wrong_label_before_remove_then_exact_is_green(monkeypatch) -> None:
    inspected = {
        "Name": f"/microsched-qa-app-{RUN_ID}",
        "Config": {"Labels": {"microsched.qa.run_id": "wrong-run"}},
    }
    monkeypatch.setattr("scripts.cleanup_qa_docker._query_ids", lambda *_args: ["resource-id"])
    monkeypatch.setattr("scripts.cleanup_qa_docker._inspect", lambda *_args: inspected)
    remove_calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        "scripts.cleanup_qa_docker._run",
        lambda *args: (
            remove_calls.append(args) or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )
    with pytest.raises(QaContractError, match="FAIL_P0_CLEANUP_LABEL"):
        cleanup_exact_resource(kind="app", run_id=RUN_ID, candidate_sha=CANDIDATE)
    assert remove_calls == []

    inspected["Config"]["Labels"]["microsched.qa.run_id"] = RUN_ID
    query_count = 0

    def query_then_absent(*_args):
        nonlocal query_count
        query_count += 1
        return ["resource-id"] if query_count == 1 else []

    monkeypatch.setattr("scripts.cleanup_qa_docker._query_ids", query_then_absent)
    assert cleanup_exact_resource(kind="app", run_id=RUN_ID, candidate_sha=CANDIDATE) == "removed"
    assert remove_calls == [("container", "rm", "--force", "resource-id")]


def test_recovery_execute_authorization_path_is_scoped_string_and_reaches_mock_cleanup(
    tmp_path, monkeypatch
) -> None:
    run_dir = tmp_path / RUN_ID
    authority_path = run_dir / "recovery" / "authorization.json"
    authority_path.parent.mkdir(parents=True)
    _write_json(
        authority_path,
        {
            "run_id": RUN_ID,
            "candidate_sha": CANDIDATE,
            "decision": "APPROVE_STRANDED_RESOURCE_CLEANUP",
            "authorized_by": "fixture-t1",
            "authorized_at_utc": "2026-08-30T00:00:00Z",
        },
    )
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        "scripts.recover_qa_docker_resources.inspect_exact_resource", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        "scripts.recover_qa_docker_resources.resources",
        lambda _run_id: {"containers": [], "networks": [], "images": []},
    )
    monkeypatch.setattr(
        "scripts.recover_qa_docker_resources.cleanup_exact_resource",
        lambda **kwargs: cleanup_calls.append(kwargs["kind"]) or "already-absent",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "recover_qa_docker_resources",
            "--run-dir",
            str(run_dir),
            "--run-id",
            RUN_ID,
            "--candidate-sha",
            CANDIDATE,
            "--execute",
            "--authorization-receipt",
            str(authority_path),
        ],
    )

    recovery_main()

    assert cleanup_calls == ["app", "pg", "network", "image"]
    receipt = load_json(run_dir / "recovery" / "recovery-receipt.json")
    assert receipt["mode"] == "execute"
    assert receipt["authorization_receipt_sha256"]


@pytest.mark.parametrize("location", ["outside", "wrong-inside"])
def test_recovery_execute_rejects_wrong_or_outside_authorization_before_inspection(
    tmp_path, monkeypatch, location
) -> None:
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    authority_path = (
        tmp_path / "outside-authorization.json"
        if location == "outside"
        else run_dir / "authority" / "authorization.json"
    )
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(authority_path, {"not": "trusted"})
    inspected = False

    def unexpected_inspection(**_kwargs):
        nonlocal inspected
        inspected = True

    monkeypatch.setattr(
        "scripts.recover_qa_docker_resources.inspect_exact_resource", unexpected_inspection
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "recover_qa_docker_resources",
            "--run-dir",
            str(run_dir),
            "--run-id",
            RUN_ID,
            "--candidate-sha",
            CANDIDATE,
            "--execute",
            "--authorization-receipt",
            str(authority_path),
        ],
    )

    with pytest.raises(QaContractError, match="FAIL_RECOVERY_PATH_SCOPE"):
        recovery_main()
    assert inspected is False


def test_unknown_placeholder_mutant_is_red_then_known_value_is_green() -> None:
    with pytest.raises(QaContractError, match="BLOCK_PLACEHOLDER_UNKNOWN"):
        substitute(["tool", "<unknown>"], {})
    assert substitute(["tool", "<run-id>"], {"<run-id>": RUN_ID}) == ["tool", RUN_ID]


@pytest.mark.parametrize(
    "placeholder",
    [
        "run-id",
        "candidate-sha",
        "manifest-core-sha256",
        "activation-receipt-path",
        "owner-sync-receipt-path",
        "synthetic-host-env-path",
        "synthetic-container-env-path",
        "synthetic-dsn-receipt-path",
    ],
)
def test_caller_cannot_override_run_derived_placeholder(placeholder) -> None:
    with pytest.raises(QaContractError, match="FAIL_PLACEHOLDER_ARGUMENT"):
        _parse_values([f"{placeholder}=foreign-value"])


@pytest.mark.parametrize(
    ("placeholder", "value"),
    [
        ("<run-id>", "foreign-run"),
        ("<candidate-sha>", "f" * 40),
        ("<synthetic-host-env-path>", "foreign/synthetic-host.env"),
        ("<synthetic-container-env-path>", "foreign/synthetic-container.env"),
        ("<synthetic-dsn-receipt-path>", "foreign/dsn.json"),
    ],
)
def test_execute_rejects_programmatic_protected_override_before_io(
    tmp_path, placeholder, value
) -> None:
    with pytest.raises(QaContractError, match="FAIL_PLACEHOLDER_ARGUMENT"):
        execute(
            run_dir=tmp_path,
            command_id="never-loaded",
            attempt=1,
            placeholder_values={placeholder: value},
        )


def test_only_external_pgvector_placeholder_is_caller_supplied() -> None:
    digest = "sha256:" + "d" * 64
    values = _parse_values([f"pgvector-pg18-ref={digest}"])
    assert values == {"<pgvector-pg18-ref>": digest}
    assert substitute(["tool", "--image", "<pgvector-pg18-ref>"], values) == [
        "tool",
        "--image",
        digest,
    ]
    with pytest.raises(QaContractError, match="FAIL_PLACEHOLDER_ARGUMENT"):
        _parse_values([f"pgvector-pg18-ref={digest}", f"pgvector-pg18-ref={digest}"])
    with pytest.raises(QaContractError, match="FAIL_PLACEHOLDER_ARGUMENT"):
        _parse_values(["unknown=value"])


def _final_command(command_id: str, *, required: bool = True) -> dict:
    return {
        "command_id": command_id,
        "contract_command_version": "037-command-contract/v1",
        "cwd": "frontend",
        "resolved_cwd": REPO_ROOT.as_posix(),
        "argv": ["fixture", command_id],
        "argv_sha256": SHA256,
        "env_names": [],
        "timeout_seconds": 30,
        "capability": "host",
        "required": required,
        "expected_exit_codes": [0],
        "oracle_ids": [f"{command_id}-oracle"],
        "failure_status": "FAIL",
        "failure_severity": "P1",
        "stdout_path": f"raw/commands/{command_id}.stdout",
        "stderr_path": f"raw/commands/{command_id}.stderr",
    }


def _final_commands(*commands: dict) -> dict:
    return {
        "schema_version": "037-commands/v1",
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "candidate_worktree": REPO_ROOT.as_posix(),
        "contract_command_version": "037-command-contract/v1",
        "command_contract_sha256": SHA256,
        "generated_at_utc": "2026-08-30T00:00:00Z",
        "commands": list(commands),
        "command_bindings": {
            command["command_id"]: {
                "phase": "fixture",
                "required": command["required"],
                "conditional": "ALWAYS",
                "activation": "NONE",
                "depends_on": [],
            }
            for command in commands
        },
    }


def _final_result(run_dir: Path, command: dict, *, attempt: int, status: str) -> dict:
    suffix = "" if attempt == 1 else f".attempt-{attempt}"
    stdout_path = f"{command['stdout_path']}{suffix}"
    stderr_path = f"{command['stderr_path']}{suffix}"
    stdout = f"{command['command_id']} attempt={attempt} status={status}\n".encode()
    stderr = b"" if status == "PASS" else f"status={status}\n".encode()
    for relative, content in ((stdout_path, stdout), (stderr_path, stderr)):
        path = run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if status == "PASS":
        actual_exit = 0
        oracle_result = "PASS"
    elif status == "BLOCKED":
        actual_exit = None
        oracle_result = "BLOCKED"
    else:
        actual_exit = 1
        oracle_result = "FAIL"
    return {
        "command_id": command["command_id"],
        "attempt": attempt,
        "cwd": command["cwd"],
        "argv_sha256": command["argv_sha256"],
        "started_at_utc": f"2026-08-30T00:00:0{attempt}Z",
        "ended_at_utc": f"2026-08-30T00:00:1{attempt}Z",
        "status": status,
        "actual_exit": actual_exit,
        "stdout_path": stdout_path,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_path": stderr_path,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "oracle_results": [
            {
                "oracle_id": command["oracle_ids"][0],
                "result": oracle_result,
                "detail": f"fixture {status}",
            }
        ],
    }


def _acceptance_cell(acceptance_id: str, command: dict, result: dict) -> dict:
    status = result["status"]
    cell_status = "FAIL" if status == command["failure_status"] else status
    return {
        "run_id": RUN_ID,
        "manifest_sha256": SHA256,
        "acceptance_id": acceptance_id,
        "candidate_sha": CANDIDATE,
        "spec_hashes": {"037": SHA256},
        "lane": "fixture",
        "status": cell_status,
        "required": command["required"],
        "command_id": command["command_id"],
        "expected_exit": command["expected_exit_codes"],
        "actual_exit": result["actual_exit"],
        "expected_oracle_id": command["oracle_ids"][0],
        "actual_oracle_id": result["oracle_results"][0]["oracle_id"],
        "oracle_result": result["oracle_results"][0]["result"],
        "failure_status": command["failure_status"],
        "failure_severity": command["failure_severity"],
        "started_at_utc": result["started_at_utc"],
        "ended_at_utc": result["ended_at_utc"],
        "stdout_path": result["stdout_path"],
        "stdout_sha256": result["stdout_sha256"],
        "stderr_path": result["stderr_path"],
        "stderr_sha256": result["stderr_sha256"],
        "evidence": [],
        "authority_receipt_id": None,
        "authority_receipt_sha256": None,
        "screenshot_sidecar_ids": [],
        "cleanup_link": None,
    }


def _validate_final_fixture(
    tmp_path: Path,
    monkeypatch,
    commands: dict,
    results: list[dict],
    cells: list[dict],
    *,
    final_status: str = "PASS_BASELINE",
) -> None:
    (tmp_path / "commands.json").write_text(json.dumps(commands), encoding="utf-8")
    (tmp_path / "command-results.json").write_text(json.dumps(results), encoding="utf-8")
    acceptance = {
        "schema_version": "037-acceptance/v1",
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "manifest_sha256": SHA256,
        "generated_at_utc": "2026-08-30T00:01:00Z",
        "cells": cells,
        "optional_findings": [],
        "final_status": final_status,
    }
    (tmp_path / "acceptance.json").write_text(json.dumps(acceptance), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.validate_qa_run._verify_matrix",
        lambda *_args: {cell["acceptance_id"] for cell in cells},
    )
    monkeypatch.setattr("scripts.validate_qa_run.validate_screenshots", lambda *_args: None)
    monkeypatch.setattr("scripts.validate_qa_run.validate_redaction", lambda *_args: None)
    validate_final(tmp_path, _manifest(), CONTRACT_DIR)


@pytest.mark.parametrize("terminal_status", ["FAIL", "BLOCKED"])
def test_fabricated_all_pass_cannot_mask_terminal_non_pass(
    tmp_path, monkeypatch, terminal_status
) -> None:
    command = _final_command("frontend.e2e")
    terminal = _final_result(tmp_path, command, attempt=1, status=terminal_status)
    fabricated = _acceptance_cell("037-fixture-pass", command, terminal)
    fabricated.update(actual_exit=0, status="PASS", oracle_result="PASS")
    with pytest.raises(QaContractError, match="FAIL_ACCEPTANCE_TERMINAL"):
        _validate_final_fixture(
            tmp_path,
            monkeypatch,
            _final_commands(command),
            [terminal],
            [fabricated],
        )


def test_acceptance_missing_terminal_result_is_red(tmp_path, monkeypatch) -> None:
    command = _final_command("frontend.e2e")
    synthetic = _final_result(tmp_path, command, attempt=1, status="PASS")
    cell = _acceptance_cell("037-fixture-missing", command, synthetic)
    with pytest.raises(QaContractError, match="FAIL_COMMAND_RESULT_BIJECTION"):
        _validate_final_fixture(tmp_path, monkeypatch, _final_commands(command), [], [cell])


@pytest.mark.parametrize("mutation", ["metadata", "raw-binding", "terminal-attempt"])
def test_acceptance_metadata_hash_and_terminal_attempt_drift_are_red(
    tmp_path, monkeypatch, mutation
) -> None:
    command = _final_command("frontend.e2e")
    first = _final_result(tmp_path, command, attempt=1, status="PASS")
    terminal = first
    results = [first]
    cell = _acceptance_cell("037-fixture-drift", command, first)
    if mutation == "metadata":
        cell.update(expected_exit=[1], actual_exit=1)
    elif mutation == "raw-binding":
        alternate = tmp_path / "raw" / "acceptance" / "fabricated.stdout"
        alternate.parent.mkdir(parents=True)
        alternate.write_bytes(b"fabricated acceptance stdout\n")
        cell.update(
            stdout_path="raw/acceptance/fabricated.stdout",
            stdout_sha256=hashlib.sha256(alternate.read_bytes()).hexdigest(),
        )
    else:
        terminal = _final_result(tmp_path, command, attempt=2, status="FAIL")
        results.append(terminal)
    with pytest.raises(QaContractError, match="FAIL_ACCEPTANCE_TERMINAL"):
        _validate_final_fixture(tmp_path, monkeypatch, _final_commands(command), results, [cell])


def test_exact_terminal_ledger_allows_multiple_cells_per_command(tmp_path, monkeypatch) -> None:
    command = _final_command("frontend.e2e")
    terminal = _final_result(tmp_path, command, attempt=1, status="PASS")
    cells = [
        _acceptance_cell("037-fixture-a", command, terminal),
        _acceptance_cell("037-fixture-b", command, terminal),
    ]
    _validate_final_fixture(tmp_path, monkeypatch, _final_commands(command), [terminal], cells)


def test_required_flag_downgrade_cannot_mask_blocked_required_command(
    tmp_path, monkeypatch
) -> None:
    command = _final_command("frontend.e2e", required=True)
    terminal = _final_result(tmp_path, command, attempt=1, status="BLOCKED")
    downgraded = _acceptance_cell("037-fixture-required-downgrade", command, terminal)
    downgraded.update(required=False, status="SKIPPED_OPTIONAL")
    fabricated_acceptance = {"cells": [downgraded]}

    assert _aggregate(fabricated_acceptance) == "PASS_BASELINE"
    with pytest.raises(QaContractError, match="FAIL_ACCEPTANCE_REQUIRED_BINDING"):
        _validate_final_fixture(
            tmp_path,
            monkeypatch,
            _final_commands(command),
            [terminal],
            [downgraded],
        )


@pytest.mark.parametrize(
    ("required", "cell_status", "final_status"),
    [(True, "BLOCKED", "BLOCKED"), (False, "SKIPPED_OPTIONAL", "PASS_BASELINE")],
)
def test_exact_required_flag_preserves_required_and_optional_blocked_cells(
    tmp_path, monkeypatch, required, cell_status, final_status
) -> None:
    command = _final_command("frontend.e2e", required=required)
    terminal = _final_result(tmp_path, command, attempt=1, status="BLOCKED")
    cell = _acceptance_cell("037-fixture-required-exact", command, terminal)
    cell["status"] = cell_status

    _validate_final_fixture(
        tmp_path,
        monkeypatch,
        _final_commands(command),
        [terminal],
        [cell],
        final_status=final_status,
    )


def test_required_command_without_acceptance_coverage_is_red(tmp_path, monkeypatch) -> None:
    first_command = _final_command("frontend.e2e")
    missing_command = _final_command("backend.ruff-check")
    first = _final_result(tmp_path, first_command, attempt=1, status="PASS")
    missing = _final_result(tmp_path, missing_command, attempt=1, status="PASS")
    cell = _acceptance_cell("037-fixture-covered", first_command, first)
    with pytest.raises(QaContractError, match="FAIL_ACCEPTANCE_COMMAND_COVERAGE"):
        _validate_final_fixture(
            tmp_path,
            monkeypatch,
            _final_commands(first_command, missing_command),
            [first, missing],
            [cell],
        )


def test_redaction_secret_mutant_is_red_then_clean_artifact_is_green(tmp_path) -> None:
    receipt = tmp_path / "receipt.txt"
    receipt.write_text("status=PASS\n", encoding="utf-8")
    validate_redaction(tmp_path, CONTRACT_DIR)
    receipt.write_text("cookie=non-public-value\n", encoding="utf-8")
    with pytest.raises(QaContractError, match="FAIL_REDACTION_CONTENT"):
        validate_redaction(tmp_path, CONTRACT_DIR)


def _png(width: int, height: int, color: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes((color, color, color)) * width
    pixels = zlib.compress(row * height, level=9)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


def _write_screenshot_fixture(run_dir: Path, *, duplicate: bool) -> None:
    checkpoints = load_json(CONTRACT_DIR / "screenshot-checkpoints.v1.json")["checkpoints"]
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    records = []
    first_content = b""
    for index, checkpoint in enumerate(checkpoints, 1):
        width, height = (390, 844) if checkpoint["viewport"] == "390x844" else (1280, 800)
        content = _png(width, height, index)
        if index == 1:
            first_content = content
        elif index == 2 and duplicate:
            content = first_content
            width, height = 390, 844
        image_path = f"screenshots/{checkpoint['checkpoint_id']}.png"
        (run_dir / image_path).write_bytes(content)
        records.append(
            {
                "screenshot_id": f"037-shot-{checkpoint['checkpoint_id']}",
                "checkpoint_id": checkpoint["checkpoint_id"],
                "run_id": RUN_ID,
                "candidate_sha": CANDIDATE,
                "spec_hashes": {"037": SHA256},
                "scenario_id": checkpoint["scenario_id"],
                "acceptance_id": checkpoint["acceptance_id"],
                "matrix_row_sha256": SHA256,
                "lane": "local",
                "device_token": checkpoint["device_token"],
                "viewport": checkpoint["viewport"],
                "pixel_width": width,
                "pixel_height": height,
                "app_crop": {"x": 0, "y": 0, "width": width, "height": height},
                "image_path": image_path,
                "captured_at_utc": "2026-08-29T00:00:00Z",
                "visible_selector": checkpoint["visible_selector"],
                "accessible_text_sha256": SHA256,
                "top_banner_or_heading": "Synthetic app heading",
                "taste_notes": ["Spacing observation.", "Density observation."],
                "md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "capture_command_raw_sha256": SHA256,
            }
        )
    (run_dir / "screenshot-records.json").write_text(json.dumps(records), encoding="utf-8")
    md5_lines = sorted(f"{item['md5']}  {item['image_path']}" for item in records)
    sha_lines = sorted(f"{item['sha256']}  {item['image_path']}" for item in records)
    (run_dir / "screenshots.md5").write_text("\n".join(md5_lines) + "\n", encoding="utf-8")
    (run_dir / "screenshots.sha256").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")


def test_screenshot_duplicate_mutant_is_red_then_unique_set_is_green(tmp_path) -> None:
    _write_screenshot_fixture(tmp_path, duplicate=True)
    with pytest.raises(QaContractError, match="FAIL_SCREENSHOT_DUPLICATE_HASH"):
        validate_screenshots(tmp_path, CONTRACT_DIR)
    _write_screenshot_fixture(tmp_path, duplicate=False)
    validate_screenshots(tmp_path, CONTRACT_DIR)
