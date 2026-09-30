"""Explicit offline replay contract for synthetic Mimi fixtures; never imported by runtime."""

from __future__ import annotations

import hashlib
import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DecisionClass(StrEnum):
    ANSWER = "answer"
    READ_ONLY = "read_only"
    CLARIFY = "clarify"
    DRAFT = "draft"
    PREVIEW = "preview"
    BLOCKED = "blocked"
    ABSTAIN = "abstain"


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: DecisionClass
    probabilities: dict[DecisionClass, float]
    abstained: bool = False

    @field_validator("probabilities")
    @classmethod
    def probabilities_are_valid(
        cls, value: dict[DecisionClass, float]
    ) -> dict[DecisionClass, float]:
        if set(value) != set(DecisionClass):
            raise ValueError("probabilities must include every decision class exactly once")
        if any(not 0 <= probability <= 1 for probability in value.values()):
            raise ValueError("probabilities must be between 0 and 1")
        if abs(sum(value.values()) - 1) > 1e-6:
            raise ValueError("probabilities must sum to 1")
        return value

    @model_validator(mode="after")
    def abstention_matches_classification(self) -> DecisionResult:
        if self.abstained != (self.classification == DecisionClass.ABSTAIN):
            raise ValueError("abstained must match the typed abstain classification")
        return self


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^heldout-[a-z0-9-]{1,40}$")
    synthetic_input: str = Field(min_length=1, max_length=500)
    expected_classification: DecisionClass
    baseline: DecisionResult
    fake_decision: DecisionResult

    @field_validator("synthetic_input")
    @classmethod
    def no_transcript_export(cls, value: str) -> str:
        forbidden = ("-----BEGIN ", "Bearer ", "sk-", "api_key", "oauth", "real email")
        if any(marker.casefold() in value.casefold() for marker in forbidden):
            raise ValueError("fixture input contains a forbidden transcript/credential marker")
        return value


class ReplayFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["mimi.synthetic-replay.v1"]
    synthetic_only: Literal[True]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[ReplayCase] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_case_ids(self) -> ReplayFixture:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique")
        return self


class DecisionFacade(Protocol):
    """Local transport contract only. Implementations must not call a model/provider."""

    def decide(self, case: ReplayCase) -> DecisionResult: ...


class FixtureDecisionFacade:
    """Deterministic stand-in whose decisions are authored in explicit fixtures."""

    def decide(self, case: ReplayCase) -> DecisionResult:
        return case.fake_decision


def deterministic_baseline(text: str) -> DecisionClass:
    """Tiny transparent baseline used only to compare the frozen synthetic examples."""

    normalized = text.casefold()
    if "ngày nào" in normalized or "thiếu ngày" in normalized:
        return DecisionClass.CLARIFY
    if "tạo task" in normalized or "tạo một task" in normalized:
        return DecisionClass.PREVIEW
    if "quy trình" in normalized or "danh sách" in normalized:
        return DecisionClass.READ_ONLY
    return DecisionClass.ANSWER


def load_fixture(path: Path, *, expected_policy_sha256: str) -> ReplayFixture:
    """Validate raw fixture bytes and all provenance before a manual offline replay."""

    return parse_fixture_bytes(path.read_bytes(), expected_policy_sha256=expected_policy_sha256)


def parse_fixture_bytes(raw: bytes, *, expected_policy_sha256: str) -> ReplayFixture:
    """Validate an in-memory raw fixture payload, including its content hash."""

    parsed = ReplayFixture.model_validate_json(raw)
    raw_cases = json.loads(raw)["cases"]
    canonical_cases = json.dumps(
        raw_cases,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_source_hash = hashlib.sha256(canonical_cases).hexdigest()
    if parsed.source_sha256 != actual_source_hash:
        raise ValueError("fixture source_sha256 does not match raw fixture bytes")
    if parsed.policy_sha256 != expected_policy_sha256:
        raise ValueError("fixture policy_sha256 does not match the supplied policy receipt")
    return parsed


def run_replay(fixture: ReplayFixture, facade: DecisionFacade) -> dict[str, object]:
    rows = []
    for case in fixture.cases:
        decision = facade.decide(case)
        baseline_class = deterministic_baseline(case.synthetic_input)
        rows.append(
            {
                "case_id": case.case_id,
                "expected": case.expected_classification.value,
                "baseline": baseline_class.value,
                "frozen_baseline": case.baseline.classification.value,
                "fake_decision": decision.classification.value,
                "fake_probabilities": {
                    kind.value: probability for kind, probability in decision.probabilities.items()
                },
                "baseline_fixture_matches": baseline_class == case.baseline.classification,
                "baseline_matches_expected": baseline_class == case.expected_classification,
                "abstained": decision.abstained,
            }
        )
    return {
        "schema_version": fixture.schema_version,
        "source_sha256": fixture.source_sha256,
        "policy_sha256": fixture.policy_sha256,
        "transport": "fixture-only; no provider/model call",
        "quality_claim": "none; contract and deterministic fixture comparison only",
        "cases": rows,
    }


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "--fixture":
        raise SystemExit("usage: python -m app.agent.mimi_replay --fixture PATH")
    fixture_path = Path(sys.argv[2])
    policy_path = Path(__file__).with_name("policy") / "mimi-standard-v1.md"
    policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    fixture = load_fixture(fixture_path, expected_policy_sha256=policy_sha256)
    print(json.dumps(run_replay(fixture, FixtureDecisionFacade()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
