"""Validate a Task 037 run preflight, authority receipt, or final aggregation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import struct
import subprocess
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from scripts.materialize_qa_run import expand_matrix
from scripts.qa_contracts import (
    EXPECTED_AUTHORITY_HASHES,
    STRATEGY_RECEIPT_SHA256,
    QaContractError,
    ensure_clean_contract,
    find_repo_root,
    git_output,
    load_json,
    parse_utc,
    resolve_inside,
    sha256_file,
    sha256_json,
    utc_now,
    validate_schema,
    verify_expected_authority_hashes,
)

EXPECTED_STRATEGY_SCOPES = {
    "037.strategy.risk_based_baseline",
    "037.order.freeze_review_then_tier1_then_owner_gate_then_tier2",
    "037.tier1.local_ci_synthetic",
    "037.tier2.owner_sync_then_scrubbed_neon_develop",
    "037.tier3.narrow_read_only_smoke_when_separately_authorized",
    "037.physical_iphone.separate_acceptance",
}
ACTIVATION_PROFILES = {
    "production_read_only_smoke": {
        "decision": "ACTIVATE_PRODUCTION_READ_ONLY_SMOKE",
        "device_token": "NONE",
        "commands": {"prod.readyz", "prod.fly-topology"},
    },
    "physical_iphone_layout_acceptance": {
        "decision": "ACTIVATE_PHYSICAL_IPHONE_LAYOUT",
        "device_token": "IPHONE_PHYSICAL",
        "commands": {"device.iphone-acceptance"},
    },
    "ios_pwa_acceptance": {
        "decision": "ACTIVATE_IOS_PWA",
        "device_token": "IOS_PWA",
        "commands": {"device.ios-pwa-acceptance"},
    },
    "real_web_push_acceptance": {
        "decision": "ACTIVATE_REAL_WEB_PUSH",
        "device_token": "REAL_WEB_PUSH",
        "commands": {"device.real-web-push"},
    },
}
DEPENDENCY_IDS = {"035A", "035B", "036"}
OWNER_EXPECTED_AUTHORITY_DELEGATION_MESSAGE_ID = "msg_01a051df-bdfa-72c3-80d9-7ae6248315e6"
OWNER_EXPECTED_AUTHORITY_DELEGATION_TEXT_SHA256 = (
    "7170603cc9f7dbcb75b65419e3bddb6dba3899f75ce9461e4ef30bd1a405031a"
)


def _equal(label: str, actual: Any, expected: Any, code: str = "BLOCK_BINDING_MISMATCH") -> None:
    if actual != expected:
        raise QaContractError(code, label)


def validate_strategy_source_semantics(source: dict[str, Any]) -> None:
    exact_text = source["source"]["exact_text"].encode("utf-8")
    _equal(
        "strategy_exact_text",
        hashlib.sha256(exact_text).hexdigest(),
        source["source"]["exact_text_sha256_utf8"],
    )
    _equal(
        "strategy_scope", set(source["structured_consent"]["scope_ids"]), EXPECTED_STRATEGY_SCOPES
    )
    _equal(
        "strategy_approved_scope",
        set(source["approved_scope"]["scope_ids"]),
        EXPECTED_STRATEGY_SCOPES,
    )
    _equal(
        "strategy_scope_equality",
        source["structured_consent"]["scope_ids"],
        source["approved_scope"]["scope_ids"],
    )
    _equal(
        "strategy_execution_authority", source["structured_consent"]["execution_authority"], False
    )
    _equal("strategy_qa_status", source["qa_execution_status"], "NOT_RUN")
    _equal("strategy_scope_expiry", source["approved_scope"]["expires"], None)
    required_denials = {
        "neon_create_delete_restore_sync",
        "neon_scrub_or_query",
        "production_access",
        "production_mutation",
        "real_device_control",
        "real_web_push",
        "git_commit",
        "git_push",
        "pr_merge",
        "deploy",
        "migration_apply_outside_disposable_tier1",
    }
    if not required_denials.issubset(source["explicitly_denied_authorities"]):
        raise QaContractError("BLOCK_STRATEGY_DENIALS")


def _verify_strategy_source(repo_root: Path, contract_dir: Path) -> dict[str, Any]:
    source_path = repo_root / "agent-tasks" / "037-owner-strategy-approval.json"
    _equal("strategy_source_sha256", sha256_file(source_path), STRATEGY_RECEIPT_SHA256)
    source = load_json(source_path)
    validate_schema(source, contract_dir / "strategy-approval-source.schema.json", label="strategy")
    validate_strategy_source_semantics(source)
    return source


def _verify_strategy_binding(
    manifest: dict[str, Any], source: dict[str, Any], contract_dir: Path
) -> None:
    binding = manifest["strategy_approval_binding"]
    validate_schema(
        binding, contract_dir / "strategy-approval-binding.schema.json", label="strategy-binding"
    )
    _equal("binding.run_id", binding["run_id"], manifest["run_id"])
    _equal("binding.candidate_sha", binding["candidate_sha"], manifest["candidate_sha"])
    _equal("binding.spec_037", binding["spec_037_sha256"], manifest["spec_hashes"]["037"])
    _equal("binding.source_message", binding["source_message_id"], source["source"]["message_id"])
    _equal("binding.scope_ids", set(binding["scope_ids"]), EXPECTED_STRATEGY_SCOPES)
    _equal("binding.scope_source", binding["scope_ids"], source["structured_consent"]["scope_ids"])
    _equal("binding.status", binding["source_qa_execution_status"], source["qa_execution_status"])
    _equal("binding.expiry", binding["source_scope_expires"], source["approved_scope"]["expires"])
    _equal("binding.execution_authority", binding["execution_authority"], False)


def _verify_commands(
    commands: dict[str, Any], manifest: dict[str, Any], repo_root: Path, contract_dir: Path
) -> set[str]:
    validate_schema(commands, contract_dir / "commands.schema.json", label="commands")
    contract = load_json(contract_dir / "command-contract.v1.json")
    contract_commands = {item["id"]: item for item in contract["commands"]}
    materialized = {item["command_id"]: item for item in commands["commands"]}
    if len(materialized) != len(commands["commands"]):
        raise QaContractError("BLOCK_COMMAND_DUPLICATE")
    _equal("command.ids", set(materialized), set(contract_commands), "BLOCK_COMMAND_BIJECTION")
    _equal(
        "command.binding.ids",
        set(commands["command_bindings"]),
        set(contract["command_bindings"]),
        "BLOCK_COMMAND_BINDING_BIJECTION",
    )
    _equal("command.bindings", commands["command_bindings"], contract["command_bindings"])
    for command_id, expected in contract_commands.items():
        actual = materialized[command_id]
        binding = contract["command_bindings"][command_id]
        _equal(f"{command_id}.cwd", actual["cwd"], expected["cwd"])
        _equal(f"{command_id}.argv", actual["argv"], expected["argv"])
        _equal(f"{command_id}.capability", actual["capability"], expected["capability"])
        _equal(
            f"{command_id}.expected_exit", actual["expected_exit_codes"], expected["expected_exit"]
        )
        _equal(f"{command_id}.oracle", actual["oracle_ids"], [expected["oracle"]])
        _equal(f"{command_id}.required", actual["required"], binding["required"])
        _equal(
            f"{command_id}.resolved_cwd",
            Path(actual["resolved_cwd"]).resolve(strict=True),
            resolve_inside(repo_root, expected["cwd"]),
        )
        _equal(f"{command_id}.argv_sha", actual["argv_sha256"], sha256_json(expected["argv"]))
    _equal("commands.run_id", commands["run_id"], manifest["run_id"])
    _equal("commands.candidate_sha", commands["candidate_sha"], manifest["candidate_sha"])
    return set(materialized)


def _verify_matrix(run_dir: Path, contract_dir: Path) -> set[str]:
    expected = expand_matrix(load_json(contract_dir / "matrix-inventory.v1.json"))
    with (run_dir / "matrix.csv").open(encoding="utf-8", newline="") as handle:
        actual = list(csv.DictReader(handle))
    key_fields = (
        "scenario_id",
        "coverage_group_id",
        "surface",
        "framework_state",
        "domain_state",
        "viewport",
        "device_token",
        "acceptance_id",
    )
    expected_keys = {tuple(row[field] for field in key_fields) for row in expected}
    actual_keys = {tuple(row[field] for field in key_fields) for row in actual}
    if len(actual) != len(actual_keys):
        raise QaContractError("BLOCK_MATRIX_DUPLICATE")
    _equal("matrix.set", actual_keys, expected_keys, "BLOCK_MATRIX_SET")
    return {row["acceptance_id"] for row in actual}


def _verify_provenance(
    provenance: dict[str, Any],
    manifest: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
    contract_dir: Path,
) -> None:
    validate_schema(
        provenance, contract_dir / "candidate-provenance.schema.json", label="provenance"
    )
    _equal("provenance.sha", provenance["candidate_sha"], manifest["candidate_sha"])
    _equal("provenance.tree", provenance["candidate_tree_sha"], manifest["candidate_tree_sha"])
    candidate_pr = provenance["candidate_pr"]
    _equal("candidate_pr.head", candidate_pr["headRefOid"], manifest["candidate_sha"])
    _verify_pr_receipt(candidate_pr, run_dir, "candidate")
    dependencies = {item["dependency_id"]: item for item in provenance["dependencies"]}
    _equal("dependency.ids", set(dependencies), DEPENDENCY_IDS)
    executor_identity = manifest["executor"]["identity"]
    for dependency_id in sorted(DEPENDENCY_IDS):
        item = dependencies[dependency_id]
        _equal(f"dependency.{dependency_id}.pr-state", item["pr"]["state"], "MERGED")
        _verify_pr_receipt(item["pr"], run_dir, dependency_id)
        spec_bytes = git_output(
            repo_root,
            "show",
            f"{item['head_oid']}:{item['spec_path']}",
            binary=True,
        )
        assert isinstance(spec_bytes, bytes)
        _equal(
            f"dependency.{dependency_id}.spec-hash",
            item["spec_sha256"],
            hashlib.sha256(spec_bytes).hexdigest(),
        )
        review_path = resolve_inside(run_dir, item["review_envelope_path"])
        _equal(
            f"dependency.{dependency_id}.review-hash",
            sha256_file(review_path),
            item["review_envelope_sha256"],
        )
        review = load_json(review_path)
        validate_schema(review, contract_dir / "review-envelope.schema.json", label="review")
        _equal(
            f"dependency.{dependency_id}.review-head", review["reviewed_head_oid"], item["head_oid"]
        )
        _equal(f"dependency.{dependency_id}.review-base", review["base_oid"], item["base_oid"])
        _equal(
            f"dependency.{dependency_id}.review-spec",
            review["reviewed_spec_sha256"],
            item["spec_sha256"],
        )
        _equal(f"dependency.{dependency_id}.pr-head", item["pr"]["headRefOid"], item["head_oid"])
        _equal(f"dependency.{dependency_id}.pr-base", item["pr"]["baseRefOid"], item["base_oid"])
        reviewer_identity = review["reviewer"]["identity"]
        review_executor = review["executor_identity"]
        identity_binding = review["source"]["identity_binding"]
        _equal(
            f"dependency.{dependency_id}.reviewer-identity",
            identity_binding["reviewer_identity"],
            reviewer_identity,
        )
        _equal(
            f"dependency.{dependency_id}.executor-identity",
            identity_binding["executor_identity"],
            review_executor,
        )
        if reviewer_identity in {executor_identity, review_executor}:
            raise QaContractError("BLOCK_REVIEWER_NOT_INDEPENDENT", dependency_id)
        raw_review_path = resolve_inside(run_dir, review["source"]["raw_review_path"])
        if raw_review_path == review_path:
            raise QaContractError("BLOCK_REVIEW_RAW_SELF_REFERENCE", dependency_id)
        load_json(raw_review_path)
        _equal(
            f"dependency.{dependency_id}.raw-review-hash",
            sha256_file(raw_review_path),
            review["source"]["raw_review_sha256"],
        )
        github_review = review["github_pr_receipt"]
        github_expected = {
            "queried_at_utc": item["pr"]["queried_at_utc"],
            "raw_api_path": item["pr"]["raw_receipt_path"],
            "raw_api_sha256": item["pr"]["raw_receipt_sha256"],
            "pr_number": item["pr"]["number"],
            "state": item["pr"]["state"],
            "is_draft": item["pr"]["isDraft"],
            "head_ref_name": item["pr"]["headRefName"],
            "head_ref_oid": item["pr"]["headRefOid"],
            "base_ref_name": item["pr"]["baseRefName"],
            "base_ref_oid": item["pr"]["baseRefOid"],
            "required_checks_terminal_success": True,
        }
        _equal(
            f"dependency.{dependency_id}.review-github",
            github_review,
            github_expected,
        )
        if not _git_is_ancestor(repo_root, item["head_oid"], manifest["candidate_sha"]):
            raise QaContractError("BLOCK_DEPENDENCY_LINEAGE", dependency_id)


def _verify_pr_receipt(pr: dict[str, Any], run_dir: Path, label: str) -> None:
    raw_path = resolve_inside(run_dir, pr["raw_receipt_path"])
    _equal(
        f"pr.{label}.raw-hash",
        sha256_file(raw_path),
        pr["raw_receipt_sha256"],
        "BLOCK_PR_RECEIPT_HASH",
    )
    raw = load_json(raw_path)
    for field in (
        "number",
        "url",
        "headRefName",
        "headRefOid",
        "baseRefName",
        "baseRefOid",
        "state",
        "isDraft",
    ):
        _equal(
            f"pr.{label}.{field}",
            raw.get(field),
            pr[field],
            "BLOCK_PR_RECEIPT_BINDING",
        )
    raw_checks = raw.get("statusCheckRollup")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise QaContractError("BLOCK_PR_CHECKS_NOT_SUCCESS", label)
    normalized_checks: list[dict[str, str]] = []
    for check in raw_checks:
        if not isinstance(check, dict):
            raise QaContractError("BLOCK_PR_CHECKS_NOT_SUCCESS", label)
        normalized = {
            "name": check.get("name"),
            "status": check.get("status"),
            "conclusion": check.get("conclusion"),
        }
        if (
            not isinstance(normalized["name"], str)
            or normalized["status"] != "COMPLETED"
            or normalized["conclusion"] not in {"SUCCESS", "NEUTRAL", "SKIPPED"}
        ):
            raise QaContractError("BLOCK_PR_CHECKS_NOT_SUCCESS", label)
        normalized_checks.append(normalized)
    names = [check["name"] for check in normalized_checks]
    if len(names) != len(set(names)):
        raise QaContractError("BLOCK_PR_CHECK_DUPLICATE", label)
    _equal(
        f"pr.{label}.checks",
        sorted(normalized_checks, key=lambda item: item["name"]),
        sorted(pr["required_checks"], key=lambda item: item["name"]),
        "BLOCK_PR_CHECK_SET",
    )


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def _verify_expected_authority_review(
    review: dict[str, Any], manifest: dict[str, Any], commands: set[str], contract_dir: Path
) -> None:
    validate_schema(
        review,
        contract_dir / "expected-authority-review.schema.json",
        label="expected-authority-review",
    )
    _equal("expected-review.run", review["run_binding"]["run_id"], manifest["run_id"])
    _equal(
        "expected-review.candidate",
        review["run_binding"]["candidate_sha"],
        manifest["candidate_sha"],
    )
    _equal(
        "expected-review.spec",
        review["run_binding"]["spec_037_sha256"],
        manifest["spec_hashes"]["037"],
    )
    hashes = review["contract_hashes"]
    _equal(
        "expected-review.command",
        hashes["command_contract_sha256"],
        EXPECTED_AUTHORITY_HASHES["command-contract.v1.json"],
    )
    _equal(
        "expected-review.matrix",
        hashes["matrix_inventory_sha256"],
        EXPECTED_AUTHORITY_HASHES["matrix-inventory.v1.json"],
    )
    _equal(
        "expected-review.catalog",
        hashes["expected_catalog_fixtures_sha256"],
        EXPECTED_AUTHORITY_HASHES["expected-catalog-fixtures.v1.json"],
    )
    _equal(
        "expected-review.query",
        hashes["catalog_queries_sha256"],
        EXPECTED_AUTHORITY_HASHES["catalog-queries.v1.sql"],
    )
    _equal("expected-review.commands", set(review["approved_command_ids"]), commands)
    _equal(
        "expected-review.commands-sha",
        review["approved_command_ids_sha256"],
        sha256_json(sorted(commands)),
    )
    _equal(
        "expected-review.executor",
        review["executor_identity"],
        manifest["executor"]["identity"],
    )
    materialized_at = parse_utc(manifest["started_at_utc"])
    independent_reviewed_at = parse_utc(review["independent_review"]["reviewed_at_utc"])
    t1_checked_at = parse_utc(review["t1_process_check"]["checked_at_utc"])
    t1_identity = review["t1_process_check"]["t1_identity"]
    reviewer_identity = review["independent_review"]["reviewer_identity"]
    if independent_reviewed_at <= materialized_at or t1_checked_at <= independent_reviewed_at:
        raise QaContractError("BLOCK_EXPECTED_AUTHORITY_REVIEW_ORDER")
    if reviewer_identity in {review["executor_identity"], t1_identity}:
        raise QaContractError("BLOCK_EXPECTED_REVIEWER_NOT_INDEPENDENT")
    if review["approval_mode"] == "DIRECT_OWNER":
        owner_review = review["owner_review"]
        if (
            owner_review["message_id"] == OWNER_EXPECTED_AUTHORITY_DELEGATION_MESSAGE_ID
            or owner_review["exact_text_sha256_utf8"]
            == OWNER_EXPECTED_AUTHORITY_DELEGATION_TEXT_SHA256
        ):
            raise QaContractError("BLOCK_EXPECTED_DIRECT_OWNER_SOURCE_IS_DELEGATION")
        owner_reviewed_at = parse_utc(owner_review["created_at_utc"])
        if owner_reviewed_at <= materialized_at or t1_checked_at <= owner_reviewed_at:
            raise QaContractError("BLOCK_EXPECTED_AUTHORITY_REVIEW_ORDER")
        consent = owner_review["structured_consent"]
        _equal("expected-review.consent.run", consent["run_id"], manifest["run_id"])
        _equal(
            "expected-review.consent.candidate",
            consent["candidate_sha"],
            manifest["candidate_sha"],
        )
        _equal(
            "expected-review.consent.spec",
            consent["spec_037_sha256"],
            manifest["spec_hashes"]["037"],
        )
        _equal(
            "expected-review.consent.commands",
            consent["approved_command_ids_sha256"],
            review["approved_command_ids_sha256"],
        )
        return

    delegation = review["owner_delegation"]
    delegated_at = parse_utc(delegation["created_at_utc"])
    decision = review["t1_technical_decision"]
    decision_at = parse_utc(decision["decided_at_utc"])
    if (
        delegated_at >= materialized_at
        or decision_at <= materialized_at
        or decision_at <= independent_reviewed_at
        or t1_checked_at <= decision_at
    ):
        raise QaContractError("BLOCK_EXPECTED_AUTHORITY_REVIEW_ORDER")
    _equal("expected-review.t1.identity", decision["t1_identity"], t1_identity)
    _equal("expected-review.t1.run", decision["run_id"], manifest["run_id"])
    _equal("expected-review.t1.candidate", decision["candidate_sha"], manifest["candidate_sha"])
    _equal(
        "expected-review.t1.spec",
        decision["spec_037_sha256"],
        manifest["spec_hashes"]["037"],
    )
    _equal(
        "expected-review.t1.commands",
        decision["approved_command_ids_sha256"],
        review["approved_command_ids_sha256"],
    )
    _equal(
        "expected-review.t1.independent-review",
        decision["independent_review_raw_sha256"],
        review["independent_review"]["raw_review_sha256"],
    )


def validate_expected_authority_review_receipt(
    run_dir: Path,
    manifest: dict[str, Any],
    commands: set[str],
    contract_dir: Path,
) -> None:
    relative_path = "authority/expected-authority-review.json"
    expected_review_path = resolve_inside(run_dir, relative_path, must_exist=False)
    if not expected_review_path.is_file():
        raise QaContractError("BLOCK_EXPECTED_AUTHORITY_REVIEW_MISSING")
    expected_review_path = resolve_inside(run_dir, relative_path)
    _verify_expected_authority_review(
        load_json(expected_review_path), manifest, commands, contract_dir
    )


def validate_preflight(repo_root: Path, contract_dir: Path, run_dir: Path) -> dict[str, Any]:
    authority_hashes = verify_expected_authority_hashes(contract_dir)
    manifest = load_json(run_dir / "run-manifest.json")
    validate_schema(manifest, contract_dir / "run-manifest.schema.json", label="manifest")
    _equal("manifest.authority-hashes", manifest["expected_authority_hashes"], authority_hashes)
    spec_paths = {
        "035A": repo_root / "agent-tasks" / "035-reminder-batching.md",
        "035B": repo_root / "agent-tasks" / "035-reminder-batching.md",
        "036": repo_root / "agent-tasks" / "036-dogfooding-ui-ux.md",
        "037": repo_root / "agent-tasks" / "037-comprehensive-qa-baseline.md",
    }
    _equal(
        "manifest.spec_hashes",
        manifest["spec_hashes"],
        {key: sha256_file(path) for key, path in spec_paths.items()},
        "BLOCK_SPEC_HASH_DRIFT",
    )
    core = {key: value for key, value in manifest.items() if key != "manifest_core_sha256"}
    _equal(
        "manifest.core",
        manifest["manifest_core_sha256"],
        sha256_json(core),
        "BLOCK_MANIFEST_CORE_DRIFT",
    )
    candidate_sha = git_output(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    candidate_tree = git_output(repo_root, "rev-parse", "HEAD^{tree}")
    _equal("candidate.sha", manifest["candidate_sha"], candidate_sha)
    _equal("candidate.tree", manifest["candidate_tree_sha"], candidate_tree)
    _equal(
        "candidate.worktree", Path(manifest["candidate_worktree"]).resolve(strict=True), repo_root
    )
    _equal(
        "candidate.clean-digest",
        manifest["git_status_porcelain_z_sha256"],
        ensure_clean_contract(repo_root, manifest["run_id"]),
    )
    source = _verify_strategy_source(repo_root, contract_dir)
    _verify_strategy_binding(manifest, source, contract_dir)
    commands = load_json(run_dir / "commands.json")
    command_ids = _verify_commands(commands, manifest, repo_root, contract_dir)
    _equal(
        "manifest.commands_sha", manifest["commands_sha256"], sha256_file(run_dir / "commands.json")
    )
    _verify_matrix(run_dir, contract_dir)
    provenance = load_json(run_dir / "candidate-provenance.json")
    _equal(
        "manifest.provenance_sha",
        manifest["candidate_provenance_sha256"],
        sha256_file(run_dir / "candidate-provenance.json"),
    )
    _verify_provenance(provenance, manifest, run_dir, repo_root, contract_dir)
    validate_expected_authority_review_receipt(run_dir, manifest, command_ids, contract_dir)
    return manifest


def validate_owner_sync(
    receipt: dict[str, Any], manifest: dict[str, Any], contract_dir: Path
) -> None:
    validate_schema(receipt, contract_dir / "authority-receipts.schema.json", label="owner-sync")
    _equal("owner-sync.type", receipt["authority_type"], "owner_neon_develop_sync_confirmation")
    binding = receipt["run_binding"]
    _equal("owner-sync.run", binding["run_id"], manifest["run_id"])
    _equal("owner-sync.candidate", binding["candidate_sha"], manifest["candidate_sha"])
    _equal("owner-sync.spec", binding["spec_037_sha256"], manifest["spec_hashes"]["037"])
    _equal("owner-sync.core", binding["manifest_core_sha256"], manifest["manifest_core_sha256"])
    consent = receipt["structured_consent"]
    _equal("owner-sync.consent.run", consent["run_id"], manifest["run_id"])
    _equal("owner-sync.consent.candidate", consent["candidate_sha"], manifest["candidate_sha"])
    _equal("owner-sync.consent.spec", consent["spec_037_sha256"], manifest["spec_hashes"]["037"])
    _equal("owner-sync.allowed", consent["allowed_command_ids"], ["tier2.prepare-qa-branch"])
    if parse_utc(receipt["neon_sync"]["sync_completed_at_utc"]) > utc_now():
        raise QaContractError("BLOCK_OWNER_SYNC_TIME")


def validate_activation(
    receipt: dict[str, Any], manifest: dict[str, Any], contract_dir: Path
) -> None:
    validate_schema(receipt, contract_dir / "authority-receipts.schema.json", label="activation")
    authority_type = receipt["authority_type"]
    if authority_type not in ACTIVATION_PROFILES:
        raise QaContractError("BLOCK_ACTIVATION_TYPE")
    profile = ACTIVATION_PROFILES[authority_type]
    binding = receipt["run_binding"]
    _equal("activation.run", binding["run_id"], manifest["run_id"])
    _equal("activation.candidate", binding["candidate_sha"], manifest["candidate_sha"])
    _equal("activation.spec", binding["spec_037_sha256"], manifest["spec_hashes"]["037"])
    _equal("activation.core", binding["manifest_core_sha256"], manifest["manifest_core_sha256"])
    consent = receipt["structured_consent"]
    _equal("activation.consent.run", consent["run_id"], binding["run_id"])
    _equal("activation.consent.candidate", consent["candidate_sha"], binding["candidate_sha"])
    _equal("activation.consent.spec", consent["spec_037_sha256"], binding["spec_037_sha256"])
    _equal("activation.consent.decision", consent["decision"], profile["decision"])
    _equal("activation.target.device", receipt["target"]["device_token"], profile["device_token"])
    _equal("activation.executor", receipt["executor"], manifest["executor"])
    approved_commands = set(receipt["allowed_command_ids"])
    _equal(
        "activation.commands.full-set",
        approved_commands,
        profile["commands"],
        "BLOCK_ACTIVATION_COMMANDS",
    )
    _equal(
        "activation.commands.structured",
        set(consent["allowed_command_ids"]),
        profile["commands"],
        "BLOCK_ACTIVATION_COMMANDS",
    )
    contract_bindings = load_json(contract_dir / "command-contract.v1.json")["command_bindings"]
    for command_id in profile["commands"]:
        _equal(
            f"activation.command-binding.{command_id}",
            contract_bindings[command_id]["activation"],
            authority_type,
            "BLOCK_ACTIVATION_COMMANDS",
        )
    issued = parse_utc(receipt["issued_at_utc"])
    expires = parse_utc(receipt["expires_at_utc"])
    now = utc_now()
    if not issued < now < expires or expires - issued > timedelta(hours=4):
        raise QaContractError("BLOCK_ACTIVATION_EXPIRED")
    if consent["allowed_command_ids"] != receipt["allowed_command_ids"]:
        raise QaContractError("BLOCK_ACTIVATION_COMMANDS")


def _verify_raw_files(run_dir: Path, acceptance: dict[str, Any]) -> None:
    for cell in acceptance["cells"]:
        if cell["status"] == "PASS":
            if cell["actual_exit"] not in cell["expected_exit"] or cell["oracle_result"] != "PASS":
                raise QaContractError("FAIL_ACCEPTANCE_FALSE_PASS", cell["acceptance_id"])
        for key in ("stdout", "stderr"):
            path = resolve_inside(run_dir, cell[f"{key}_path"])
            _equal(
                f"{cell['acceptance_id']}.{key}",
                sha256_file(path),
                cell[f"{key}_sha256"],
                "FAIL_RAW_DIGEST",
            )
        for item in cell["evidence"]:
            _equal(
                item["path"],
                sha256_file(resolve_inside(run_dir, item["path"])),
                item["sha256"],
                "FAIL_EVIDENCE_DIGEST",
            )


def _aggregate(acceptance: dict[str, Any]) -> str:
    cells = acceptance["cells"]
    if any(cell["status"] == "FAIL" and cell["failure_severity"] == "P0" for cell in cells):
        return "FAIL_P0"
    if any(cell["required"] and cell["status"] == "BLOCKED" for cell in cells):
        return "BLOCKED"
    if any(cell["required"] and cell["status"] == "FAIL" for cell in cells):
        return "FAIL"
    if any(cell["required"] and cell["status"] == "NOT_RUN" for cell in cells):
        return "PARTIAL_NOT_ACCEPTED"
    return "PASS_BASELINE"


def validate_command_results(
    run_dir: Path, contract_dir: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    commands = load_json(run_dir / "commands.json")
    validate_schema(commands, contract_dir / "commands.schema.json", label="commands")
    command_by_id = {item["command_id"]: item for item in commands["commands"]}
    results = load_json(run_dir / "command-results.json")
    if not isinstance(results, list):
        raise QaContractError("FAIL_COMMAND_RESULTS_SHAPE")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        required = {
            "command_id",
            "attempt",
            "cwd",
            "argv_sha256",
            "started_at_utc",
            "ended_at_utc",
            "status",
            "actual_exit",
            "stdout_path",
            "stdout_sha256",
            "stderr_path",
            "stderr_sha256",
            "oracle_results",
        }
        if set(result) != required:
            raise QaContractError("FAIL_COMMAND_RESULT_FIELDS", result.get("command_id", "?"))
        command_id = result["command_id"]
        if command_id not in command_by_id:
            raise QaContractError("FAIL_COMMAND_RESULT_EXTRA", command_id)
        grouped.setdefault(command_id, []).append(result)
    expected = set(command_by_id) - {"qa.final"}
    _equal("command-result.ids", set(grouped), expected, "FAIL_COMMAND_RESULT_BIJECTION")
    terminal: dict[str, dict[str, Any]] = {}
    for command_id, attempts in grouped.items():
        attempts.sort(key=lambda item: item["attempt"])
        if [item["attempt"] for item in attempts] != list(range(1, len(attempts) + 1)):
            raise QaContractError("FAIL_COMMAND_ATTEMPT_SEQUENCE", command_id)
        terminal[command_id] = attempts[-1]
        command = command_by_id[command_id]
        for result in attempts:
            _equal(f"{command_id}.cwd", result["cwd"], command["cwd"])
            _equal(f"{command_id}.argv", result["argv_sha256"], command["argv_sha256"])
            if result["status"] not in {"PASS", "BLOCKED", command["failure_status"]}:
                raise QaContractError("FAIL_COMMAND_RESULT_STATUS", command_id)
            started = parse_utc(result["started_at_utc"])
            ended = parse_utc(result["ended_at_utc"])
            if ended < started:
                raise QaContractError("FAIL_COMMAND_RESULT_TIME", command_id)
            oracle_ids = [item.get("oracle_id") for item in result["oracle_results"]]
            if len(oracle_ids) != len(set(oracle_ids)):
                raise QaContractError("FAIL_COMMAND_ORACLE_DUPLICATE", command_id)
            _equal(
                f"{command_id}.oracles",
                set(oracle_ids),
                set(command["oracle_ids"]),
                "FAIL_COMMAND_ORACLE_BINDING",
            )
            for stream in ("stdout", "stderr"):
                path = resolve_inside(run_dir, result[f"{stream}_path"])
                _equal(
                    f"{command_id}.{stream}",
                    sha256_file(path),
                    result[f"{stream}_sha256"],
                    "FAIL_COMMAND_RAW_DIGEST",
                )
            if result["status"] == "PASS":
                if result["actual_exit"] not in command["expected_exit_codes"]:
                    raise QaContractError("FAIL_COMMAND_FALSE_PASS", command_id)
                if any(item["result"] != "PASS" for item in result["oracle_results"]):
                    raise QaContractError("FAIL_COMMAND_FALSE_PASS", command_id)
    for command_id, result in terminal.items():
        if result["status"] == "BLOCKED":
            continue
        for dependency in commands["command_bindings"][command_id]["depends_on"]:
            dependency_result = terminal.get(dependency)
            if dependency_result is None or dependency_result["status"] != "PASS":
                raise QaContractError("FAIL_COMMAND_DEPENDENCY_ORDER", command_id)
            if parse_utc(dependency_result["ended_at_utc"]) > parse_utc(result["started_at_utc"]):
                raise QaContractError("FAIL_COMMAND_DEPENDENCY_ORDER", command_id)
        for dependency in commands["command_bindings"][command_id].get("depends_on_terminal", []):
            dependency_result = terminal.get(dependency)
            if dependency_result is None:
                raise QaContractError("FAIL_COMMAND_TERMINAL_DEPENDENCY_ORDER", command_id)
            if parse_utc(dependency_result["ended_at_utc"]) > parse_utc(result["started_at_utc"]):
                raise QaContractError("FAIL_COMMAND_TERMINAL_DEPENDENCY_ORDER", command_id)
    return command_by_id, terminal


def validate_acceptance_command_bindings(
    acceptance: dict[str, Any],
    command_by_id: dict[str, dict[str, Any]],
    terminal: dict[str, dict[str, Any]],
) -> None:
    """Bind every acceptance cell to contract metadata and the terminal attempt."""
    covered: set[str] = set()
    for cell in acceptance["cells"]:
        acceptance_id = cell["acceptance_id"]
        command_id = cell["command_id"]
        command = command_by_id.get(command_id)
        if command is None:
            raise QaContractError("FAIL_ACCEPTANCE_COMMAND_UNKNOWN", acceptance_id)
        result = terminal.get(command_id)
        if result is None:
            raise QaContractError("FAIL_ACCEPTANCE_TERMINAL_RESULT_MISSING", acceptance_id)
        covered.add(command_id)

        _equal(
            f"{acceptance_id}.required",
            cell["required"],
            command["required"],
            "FAIL_ACCEPTANCE_REQUIRED_BINDING",
        )
        _equal(
            f"{acceptance_id}.expected-exit",
            cell["expected_exit"],
            command["expected_exit_codes"],
            "FAIL_ACCEPTANCE_TERMINAL_METADATA",
        )
        _equal(
            f"{acceptance_id}.failure-status",
            cell["failure_status"],
            command["failure_status"],
            "FAIL_ACCEPTANCE_TERMINAL_METADATA",
        )
        _equal(
            f"{acceptance_id}.failure-severity",
            cell["failure_severity"],
            command["failure_severity"],
            "FAIL_ACCEPTANCE_TERMINAL_METADATA",
        )
        if cell["expected_oracle_id"] not in command["oracle_ids"]:
            raise QaContractError("FAIL_ACCEPTANCE_TERMINAL_ORACLE", acceptance_id)
        oracle_by_id = {
            oracle["oracle_id"]: oracle
            for oracle in result["oracle_results"]
            if isinstance(oracle, dict) and "oracle_id" in oracle
        }
        if len(oracle_by_id) != len(result["oracle_results"]):
            raise QaContractError("FAIL_ACCEPTANCE_TERMINAL_ORACLE", acceptance_id)
        oracle = oracle_by_id.get(cell["expected_oracle_id"])
        if oracle is None:
            raise QaContractError("FAIL_ACCEPTANCE_TERMINAL_ORACLE", acceptance_id)

        terminal_fields = {
            "actual_exit": result["actual_exit"],
            "actual_oracle_id": oracle["oracle_id"],
            "oracle_result": oracle["result"],
            "started_at_utc": result["started_at_utc"],
            "ended_at_utc": result["ended_at_utc"],
            "stdout_path": result["stdout_path"],
            "stdout_sha256": result["stdout_sha256"],
            "stderr_path": result["stderr_path"],
            "stderr_sha256": result["stderr_sha256"],
        }
        for field, expected in terminal_fields.items():
            _equal(
                f"{acceptance_id}.{field}",
                cell[field],
                expected,
                "FAIL_ACCEPTANCE_TERMINAL_BINDING",
            )

        if result["status"] == "PASS":
            allowed_cell_statuses = {"PASS"}
        elif result["status"] == "BLOCKED":
            allowed_cell_statuses = {"BLOCKED", "NOT_RUN"}
            if not cell["required"]:
                allowed_cell_statuses.add("SKIPPED_OPTIONAL")
        else:
            allowed_cell_statuses = {"FAIL"}
        if cell["status"] not in allowed_cell_statuses:
            raise QaContractError("FAIL_ACCEPTANCE_TERMINAL_STATUS", acceptance_id)

    required_commands = {
        command_id
        for command_id, command in command_by_id.items()
        if command_id != "qa.final" and command["required"]
    }
    executed_optional_commands = {
        command_id
        for command_id, result in terminal.items()
        if not command_by_id[command_id]["required"] and result["status"] != "BLOCKED"
    }
    missing = (required_commands | executed_optional_commands) - covered
    if missing:
        raise QaContractError("FAIL_ACCEPTANCE_COMMAND_COVERAGE", sorted(missing)[0])


def validate_redaction(run_dir: Path, contract_dir: Path) -> None:
    rules = load_json(contract_dir / "redaction-rules.v1.json")
    if rules.get("schema_version") != "037-redaction-rules/v1":
        raise QaContractError("FAIL_REDACTION_RULES_VERSION")
    for path in run_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir).as_posix()
        if path.suffix.lower() == ".png" or relative == "backup-v1.dump.enc":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise QaContractError("FAIL_REDACTION_UNDECLARED_BINARY", relative) from error
        for rule in rules["rules"]:
            if "path_pattern" in rule and re.search(rule["path_pattern"], relative):
                raise QaContractError("FAIL_REDACTION_PATH", rule["id"])
            pattern = rule.get("pattern")
            if not pattern:
                continue
            for match in re.finditer(pattern, text):
                if match.group(0) not in rule.get("allow", []):
                    raise QaContractError("FAIL_REDACTION_CONTENT", rule["id"])


def validate_screenshots(run_dir: Path, contract_dir: Path) -> None:
    checkpoints = load_json(contract_dir / "screenshot-checkpoints.v1.json")
    checkpoint_by_id = {item["checkpoint_id"]: item for item in checkpoints["checkpoints"]}
    records_path = run_dir / "screenshot-records.json"
    if not records_path.is_file():
        raise QaContractError("FAIL_SCREENSHOT_RECORDS_MISSING")
    records = load_json(records_path)
    if not isinstance(records, list):
        raise QaContractError("FAIL_SCREENSHOT_RECORDS_SHAPE")
    expected_ids = {item["checkpoint_id"] for item in checkpoints["checkpoints"]}
    actual_ids: set[str] = set()
    digests: dict[str, str] = {}
    md5_lines: list[str] = []
    sha_lines: list[str] = []
    allowlist = {
        frozenset(item)
        for item in checkpoints.get("duplicate_hash_allowlist", [])
        if isinstance(item, list)
    }
    for record in records:
        validate_schema(record, contract_dir / "screenshot-record.schema.json", label="screenshot")
        checkpoint_id = record["checkpoint_id"]
        if checkpoint_id in actual_ids:
            raise QaContractError("FAIL_SCREENSHOT_CHECKPOINT_DUPLICATE", checkpoint_id)
        actual_ids.add(checkpoint_id)
        checkpoint = checkpoint_by_id.get(checkpoint_id)
        if checkpoint is None:
            raise QaContractError("FAIL_SCREENSHOT_CHECKPOINT_UNKNOWN", checkpoint_id)
        for field in (
            "scenario_id",
            "acceptance_id",
            "viewport",
            "device_token",
            "visible_selector",
        ):
            _equal(
                f"screenshot.{checkpoint_id}.{field}",
                record[field],
                checkpoint[field],
                "FAIL_SCREENSHOT_BINDING",
            )
        image_path = resolve_inside(run_dir, record["image_path"])
        content = image_path.read_bytes()
        if (
            len(content) < 32
            or content[:8] != b"\x89PNG\r\n\x1a\n"
            or content[12:16] != b"IHDR"
            or b"IEND" not in content
        ):
            raise QaContractError("FAIL_SCREENSHOT_DECODE", checkpoint_id)
        pixel_width, pixel_height = struct.unpack(">II", content[16:24])
        _equal(
            "screenshot.pixel_width",
            record["pixel_width"],
            pixel_width,
            "FAIL_SCREENSHOT_DIMENSIONS",
        )
        _equal(
            "screenshot.pixel_height",
            record["pixel_height"],
            pixel_height,
            "FAIL_SCREENSHOT_DIMENSIONS",
        )
        crop = record["app_crop"]
        if crop["x"] + crop["width"] > pixel_width or crop["y"] + crop["height"] > pixel_height:
            raise QaContractError("FAIL_SCREENSHOT_CROP", checkpoint_id)
        md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        sha = hashlib.sha256(content).hexdigest()
        _equal("screenshot.md5", record["md5"], md5, "FAIL_SCREENSHOT_HASH")
        _equal("screenshot.sha256", record["sha256"], sha, "FAIL_SCREENSHOT_HASH")
        if sha in digests and frozenset({digests[sha], checkpoint_id}) not in allowlist:
            raise QaContractError("FAIL_SCREENSHOT_DUPLICATE_HASH", checkpoint_id)
        digests[sha] = checkpoint_id
        md5_lines.append(f"{md5}  {record['image_path']}")
        sha_lines.append(f"{sha}  {record['image_path']}")
    _equal("screenshot.checkpoints", actual_ids, expected_ids, "FAIL_SCREENSHOT_SET")
    expected_md5 = "\n".join(sorted(md5_lines)) + "\n"
    expected_sha = "\n".join(sorted(sha_lines)) + "\n"
    _equal("screenshots.md5", (run_dir / "screenshots.md5").read_text(), expected_md5)
    _equal("screenshots.sha256", (run_dir / "screenshots.sha256").read_text(), expected_sha)


def validate_final(run_dir: Path, manifest: dict[str, Any], contract_dir: Path) -> None:
    command_by_id, terminal = validate_command_results(run_dir, contract_dir)
    acceptance = load_json(run_dir / "acceptance.json")
    validate_schema(acceptance, contract_dir / "acceptance.schema.json", label="acceptance")
    _equal("acceptance.run", acceptance["run_id"], manifest["run_id"])
    _equal("acceptance.candidate", acceptance["candidate_sha"], manifest["candidate_sha"])
    ids = [cell["acceptance_id"] for cell in acceptance["cells"]]
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise QaContractError("FAIL_ACCEPTANCE_DUPLICATE", duplicates[0])
    matrix_ids = _verify_matrix(run_dir, contract_dir)
    if matrix_ids != set(ids):
        raise QaContractError("FAIL_ACCEPTANCE_MATRIX_COVERAGE")
    validate_acceptance_command_bindings(acceptance, command_by_id, terminal)
    _verify_raw_files(run_dir, acceptance)
    validate_screenshots(run_dir, contract_dir)
    validate_redaction(run_dir, contract_dir)
    _equal(
        "acceptance.final",
        acceptance["final_status"],
        _aggregate(acceptance),
        "FAIL_FINAL_AGGREGATION",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-dir", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--phase", choices=["preflight", "owner-sync", "production-device", "final"], required=True
    )
    parser.add_argument("--receipt")
    return parser


def main() -> None:
    args = _parser().parse_args()
    repo_root = find_repo_root()
    contract_dir = Path(args.contract_dir).resolve(strict=True)
    run_dir = Path(args.run_dir).resolve(strict=True)
    try:
        if args.phase == "preflight":
            validate_preflight(repo_root, contract_dir, run_dir)
        else:
            manifest = load_json(run_dir / "run-manifest.json")
            validate_schema(manifest, contract_dir / "run-manifest.schema.json", label="manifest")
            if args.phase == "owner-sync":
                if not args.receipt:
                    raise QaContractError("BLOCK_OWNER_SYNC_RECEIPT_MISSING")
                validate_owner_sync(load_json(Path(args.receipt)), manifest, contract_dir)
            elif args.phase == "production-device":
                if not args.receipt:
                    raise QaContractError("BLOCK_ACTIVATION_RECEIPT_MISSING")
                validate_activation(load_json(Path(args.receipt)), manifest, contract_dir)
            else:
                validate_preflight(repo_root, contract_dir, run_dir)
                validate_final(run_dir, manifest, contract_dir)
    except QaContractError as error:
        print(f"qa_validation={error.code}")
        if error.detail:
            print(f"detail={error.detail}")
        raise SystemExit(2) from error
    print(f"qa_validation=PASS phase={args.phase}")


if __name__ == "__main__":
    main()
