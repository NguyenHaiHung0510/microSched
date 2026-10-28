"""Contract checks for the explicitly invoked synthetic-only replay harness."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.mimi_replay import (
    MAX_FIXTURE_BYTES,
    DecisionClass,
    DecisionResult,
    FixtureDecisionFacade,
    ReplayTimeout,
    canonical_policy_sha256,
    load_fixture,
    parse_fixture_bytes,
    run_replay,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mimi_feedback_replay" / "v1" / "heldout.json"
POLICY = Path(__file__).parents[1] / "app" / "agent" / "policy" / "mimi-standard-v1.md"


def test_frozen_authored_synthetic_cases_compare_fake_transport_and_baseline() -> None:
    policy_hash = canonical_policy_sha256(POLICY)
    fixture = load_fixture(FIXTURE, expected_policy_sha256=policy_hash)

    report = run_replay(fixture, FixtureDecisionFacade())

    assert len(report["cases"]) == 5
    assert all(row["baseline_fixture_matches"] for row in report["cases"])
    classes = {kind.value for kind in DecisionClass}
    assert all(row["fake_decision"] in classes for row in report["cases"])
    assert all(
        sum(row["fake_probabilities"].values()) == pytest.approx(1) for row in report["cases"]
    )
    assert report["quality_claim"].startswith("none;")
    assert report["transport"].startswith("fixture-only;")


def test_replay_rejects_tampered_case_bytes() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["synthetic_input"] += " tampered"

    with pytest.raises(ValueError, match="source_sha256"):
        parse_fixture_bytes(
            json.dumps(payload).encode("utf-8"),
            expected_policy_sha256=payload["policy_sha256"],
        )


def test_replay_rejects_oversized_raw_fixture_before_json_parse() -> None:
    with pytest.raises(ValueError, match="byte limit"):
        parse_fixture_bytes(
            b" " * (MAX_FIXTURE_BYTES + 1),
            expected_policy_sha256="0" * 64,
        )


def test_replay_rejects_unrecognized_authority_fields() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["tool_call"] = {"name": "task.create.v1"}
    canonical_cases = json.dumps(
        payload["cases"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload["source_sha256"] = hashlib.sha256(canonical_cases).hexdigest()

    with pytest.raises(ValidationError, match="tool_call"):
        parse_fixture_bytes(
            json.dumps(payload).encode("utf-8"),
            expected_policy_sha256=payload["policy_sha256"],
        )


def test_facade_timeout_becomes_typed_abstention() -> None:
    fixture = load_fixture(FIXTURE, expected_policy_sha256=canonical_policy_sha256(POLICY))

    class TimedOutFacade:
        def decide(self, _case):
            raise ReplayTimeout("synthetic facade timeout")

    report = run_replay(fixture, TimedOutFacade())

    assert all(row["facade_timed_out"] for row in report["cases"])
    assert all(row["fake_decision"] == DecisionClass.ABSTAIN.value for row in report["cases"])
    assert all(row["abstained"] for row in report["cases"])


def test_typed_probabilities_require_complete_distribution_and_explicit_abstention() -> None:
    with pytest.raises(ValidationError, match="sum to 1"):
        DecisionResult(
            classification=DecisionClass.ANSWER,
            probabilities={kind: 0.0 for kind in DecisionClass},
        )

    with pytest.raises(ValidationError, match="abstained must match"):
        DecisionResult(
            classification=DecisionClass.ABSTAIN,
            probabilities={
                kind: (1.0 if kind is DecisionClass.ABSTAIN else 0.0) for kind in DecisionClass
            },
        )


def test_replay_policy_digest_is_checkout_independent_and_still_detects_drift(tmp_path):
    canonical = POLICY.read_bytes().decode("utf-8").replace("\r\n", "\n").encode()
    lf_policy, crlf_policy = tmp_path / "lf.md", tmp_path / "crlf.md"
    lf_policy.write_bytes(canonical)
    crlf_policy.write_bytes(canonical.replace(b"\n", b"\r\n"))
    expected = canonical_policy_sha256(lf_policy)
    assert canonical_policy_sha256(crlf_policy) == expected
    load_fixture(FIXTURE, expected_policy_sha256=expected)
    crlf_policy.write_bytes(canonical + "Policy changed.\n".encode())
    with pytest.raises(ValueError, match="policy_sha256"):
        load_fixture(FIXTURE, expected_policy_sha256=canonical_policy_sha256(crlf_policy))


@pytest.mark.parametrize("payload", [b"\xef\xbb\xbfpolicy\n", b"policy\r", b"policy"])
def test_replay_rejects_invalid_policy_encoding(tmp_path, payload):
    path = tmp_path / "invalid.md"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="invalid_replay_policy_encoding"):
        canonical_policy_sha256(path)
