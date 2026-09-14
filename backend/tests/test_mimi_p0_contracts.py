"""P0 contract tests: truthfulness, secret exclusion, and bounded authority."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agent.contracts import (
    CaptureStatus,
    CompletenessManifest,
    EvidenceBundle,
    EvidencePayload,
    ExecutionLease,
    FrozenChangeSet,
    Sensitivity,
)


def test_complete_manifest_cannot_hide_a_missing_part() -> None:
    with pytest.raises(ValidationError, match="complete capture"):
        CompletenessManifest(
            status=CaptureStatus.COMPLETE,
            expected_parts=("prompt", "response"),
            captured_parts=("prompt",),
            missing_parts=("response",),
        )


def test_partial_and_failed_capture_remain_explicit() -> None:
    partial = CompletenessManifest(
        status=CaptureStatus.INCOMPLETE,
        expected_parts=("prompt", "response", "tools"),
        captured_parts=("prompt", "tools"),
        missing_parts=("response",),
    )
    assert partial.status is CaptureStatus.INCOMPLETE
    assert partial.missing_parts == ("response",)

    failed = CompletenessManifest(
        status=CaptureStatus.FAILED,
        expected_parts=("prompt", "response"),
        captured_parts=("prompt",),
        missing_parts=("response",),
        failure_type="SyntheticStreamClosed",
    )
    assert failed.failure_type == "SyntheticStreamClosed"


def test_complete_bundle_cannot_claim_an_absent_payload_part() -> None:
    with pytest.raises(ValidationError, match="payload is absent"):
        EvidenceBundle(
            bundle_id=UUID("00000000-0000-7000-8000-000000000010"),
            client_id="truth-check",
            run_id=UUID("00000000-0000-7000-8000-000000000011"),
            turn_id=UUID("00000000-0000-7000-8000-000000000012"),
            call_id="call-truth-check",
            sensitivity=Sensitivity.STANDARD,
            environment_id="mimi-p0-local-055",
            fixture_version="mimi-p0.v1",
            source_versions={},
            completeness=CompletenessManifest(
                status=CaptureStatus.COMPLETE,
                expected_parts=("prompt", "response"),
                captured_parts=("prompt", "response"),
            ),
            payload=EvidencePayload(assembled_prompt="synthetic", response=None),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"request": {"headers": {"Authorization": "Bearer synthetic"}}},
        {"response": {"cookie": "synthetic=value"}},
        {"assembled_prompt": "Authorization: Bearer synthetic"},
        {"route": {"client_secret": "synthetic"}},
        {"request": {"input": [{"password": "synthetic"}]}},
        {"response": {"output": [{"reasoning_content": "hidden"}]}},
        {
            "tool_exchanges": [
                {
                    "call_id": "x",
                    "tool_name": "x",
                    "arguments": {"token": "synthetic"},
                    "outcome": "failed",
                }
            ]
        },
        {"config": {"nested": {"private_key": "synthetic"}}},
        {"usage": {"metadata": {"thinking": "hidden"}}},
        {"assembled_prompt": 'prefix {"Authorization": "Bearer synthetic"}'},
    ],
)
def test_evidence_rejects_auth_headers_cookies_and_secret_fields(payload: dict) -> None:
    with pytest.raises(ValidationError, match="forbidden"):
        EvidencePayload.model_validate(payload)


def test_execution_lease_is_bounded_and_server_issued() -> None:
    issued = datetime(2030, 1, 15, tzinfo=UTC)
    lease = ExecutionLease(
        lease_id=UUID("00000000-0000-7000-8000-000000000001"),
        owner_id=UUID("00000000-0000-7000-8000-000000000002"),
        run_id=UUID("00000000-0000-7000-8000-000000000003"),
        capabilities=("task.read", "task.propose_create"),
        issued_at=issued,
        deadline=issued + timedelta(minutes=15),
        max_turns=12,
        max_tool_calls=24,
        cost_cap_minor=0,
        sensitivity=Sensitivity.STANDARD,
    )
    assert lease.issuer == "microsched-server"
    assert lease.deadline > lease.issued_at

    with pytest.raises(ValidationError, match="deadline"):
        ExecutionLease.model_validate({**lease.model_dump(), "deadline": issued})


def test_evidence_rejects_unknown_top_level_provider_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidencePayload.model_validate({"thinking": "hidden"})


def test_visible_reasoning_summary_is_allowed() -> None:
    payload = EvidencePayload(response={"reasoning_summary": "Application-visible summary"})
    assert payload.response == {"reasoning_summary": "Application-visible summary"}


def test_change_set_digest_is_canonical_and_excludes_declared_digest() -> None:
    change_set = FrozenChangeSet(
        change_set_id=UUID("00000000-0000-7000-8000-000000000020"),
        run_id=UUID("00000000-0000-7000-8000-000000000021"),
        operations=(),
        expires_at=datetime(2030, 1, 15, tzinfo=UTC),
        nonce=UUID("00000000-0000-7000-8000-000000000022"),
        digest_sha256="0" * 64,
        idempotency_key="change-client-1",
    )
    digest = change_set.calculated_digest()
    assert len(digest) == 64
    assert change_set.model_copy(update={"digest_sha256": "f" * 64}).calculated_digest() == digest
