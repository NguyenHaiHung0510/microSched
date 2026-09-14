"""Frozen P0 contracts for Mimi evidence, feedback, and execution authority."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Sensitivity(StrEnum):
    STANDARD = "standard"
    PRIVATE = "private"


class CaptureStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class FeedbackState(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    TRIAGED = "triaged"
    LINKED_TO_FIX = "linked_to_fix"
    LINKED_TO_CASE = "linked_to_case"
    VERIFIED = "verified"
    DISMISSED = "dismissed"


class ExecutionLease(BaseModel):
    """Server-issued authority snapshot; never accepts a model-created bypass."""

    schema_version: Literal["mimi.execution-lease.v1"] = "mimi.execution-lease.v1"
    lease_id: UUID
    owner_id: UUID
    run_id: UUID
    issuer: Literal["microsched-server"] = "microsched-server"
    capabilities: tuple[str, ...]
    issued_at: datetime
    deadline: datetime
    max_turns: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    cost_cap_minor: int = Field(ge=0)
    revoked_at: datetime | None = None
    sensitivity: Sensitivity
    source_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bounds(self) -> ExecutionLease:
        if self.deadline <= self.issued_at:
            raise ValueError("deadline must be after issued_at")
        return self


class ChangeOperation(BaseModel):
    operation_id: UUID
    tool: str = Field(min_length=1, max_length=200)
    args: dict[str, Any]
    expected_entity_version: str | None = None
    reversible: bool


class FrozenChangeSet(BaseModel):
    """Preview payload bound to one digest/nonce and current entity versions."""

    schema_version: Literal["mimi.change-set.v1"] = "mimi.change-set.v1"
    change_set_id: UUID
    run_id: UUID
    operations: tuple[ChangeOperation, ...]
    expires_at: datetime
    nonce: UUID
    digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=160)

    def calculated_digest(self) -> str:
        """Canonical digest of the immutable proposal content bound by digest_sha256."""

        body = self.model_dump(mode="json", exclude={"digest_sha256"})
        canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ToolExchange(BaseModel):
    call_id: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any]
    result: Any | None = None
    outcome: Literal["succeeded", "failed", "unknown"]


class EvidencePayload(BaseModel):
    """Application-visible provider data only; hidden reasoning is not a field."""

    model_config = ConfigDict(extra="forbid")

    assembled_prompt: str | None = None
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    tool_exchanges: tuple[ToolExchange, ...] = ()
    route: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_secret_material(self) -> EvidencePayload:
        _reject_evidence_material(self.model_dump(mode="python"))
        return self


class CompletenessManifest(BaseModel):
    status: CaptureStatus
    expected_parts: tuple[str, ...]
    captured_parts: tuple[str, ...]
    missing_parts: tuple[str, ...] = ()
    failure_type: str | None = None

    @model_validator(mode="after")
    def validate_truthfulness(self) -> CompletenessManifest:
        expected = set(self.expected_parts)
        captured = set(self.captured_parts)
        missing = set(self.missing_parts)
        if captured - expected or missing - expected:
            raise ValueError("captured/missing parts must be declared in expected_parts")
        if captured & missing:
            raise ValueError("a part cannot be both captured and missing")
        if self.status == CaptureStatus.COMPLETE and (missing or captured != expected):
            raise ValueError("complete capture must contain every expected part")
        if self.status != CaptureStatus.COMPLETE and not missing:
            raise ValueError("incomplete/failed capture must identify missing parts")
        if self.status == CaptureStatus.FAILED and not self.failure_type:
            raise ValueError("failed capture must include failure_type")
        return self


class EvidenceBundle(BaseModel):
    schema_version: Literal["mimi.evidence-bundle.v1"] = "mimi.evidence-bundle.v1"
    bundle_id: UUID
    client_id: str = Field(min_length=1, max_length=160)
    run_id: UUID
    turn_id: UUID
    call_id: str = Field(min_length=1, max_length=200)
    sensitivity: Sensitivity
    environment_id: str = Field(min_length=1, max_length=120)
    fixture_version: str = Field(min_length=1, max_length=120)
    source_versions: dict[str, str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completeness: CompletenessManifest
    payload: EvidencePayload

    @model_validator(mode="after")
    def bind_manifest_to_payload(self) -> EvidenceBundle:
        captured = set(self.completeness.captured_parts)
        missing = set(self.completeness.missing_parts)
        values = {
            "prompt": self.payload.assembled_prompt,
            "request": self.payload.request,
            "response": self.payload.response,
            "tools": self.payload.tool_exchanges,
            "route": self.payload.route,
            "config": self.payload.config,
            "usage": self.payload.usage,
        }
        for part, value in values.items():
            if part in captured and part != "tools" and value is None:
                raise ValueError(f"manifest captures {part!r} but payload is absent")
            if part in missing and value not in (None, (), [], {}):
                raise ValueError(f"manifest marks {part!r} missing but payload is present")
        return self

    def content_digest(self) -> str:
        """Digest logical client content, excluding server identity and receipt time."""

        body = self.model_dump(mode="json", exclude={"bundle_id", "created_at"})
        canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FeedbackRecord(BaseModel):
    schema_version: Literal["mimi.feedback.v1"] = "mimi.feedback.v1"
    feedback_id: UUID
    client_id: str = Field(min_length=1, max_length=160)
    target_type: Literal["turn", "run", "call", "operation", "receipt"]
    target_id: str = Field(min_length=1, max_length=200)
    comment: str = Field(min_length=1, max_length=10_000)
    expected: str | None = Field(default=None, max_length=10_000)
    evidence_bundle_ids: tuple[UUID, ...]
    sensitivity: Sensitivity
    state: FeedbackState = FeedbackState.NEW
    unresolved: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None

    @field_validator("comment", "expected")
    @classmethod
    def reject_feedback_headers(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_secret_material(value)
        return value

    @model_validator(mode="after")
    def validate_acknowledgement(self) -> FeedbackRecord:
        if self.state == FeedbackState.ACKNOWLEDGED and self.acknowledged_at is None:
            raise ValueError("acknowledged feedback requires acknowledged_at")
        if self.state in {FeedbackState.VERIFIED, FeedbackState.DISMISSED} and self.unresolved:
            raise ValueError("terminal feedback cannot remain unresolved")
        return self

    def content_digest(self) -> str:
        body = self.model_dump(
            mode="json",
            exclude={"feedback_id", "created_at", "acknowledged_at", "state", "unresolved"},
        )
        canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_FORBIDDEN_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "api-key",
    "api_key",
    "x-api-key",
    "access-token",
    "access_token",
    "refresh-token",
    "refresh_token",
    "client-secret",
    "client_secret",
    "password",
    "passwd",
    "token",
    "session-token",
    "session_token",
    "secret",
    "secret-key",
    "secret_key",
    "private-key",
    "private_key",
}
_HIDDEN_REASONING_KEYS = {
    "chain-of-thought",
    "chain_of_thought",
    "hidden-reasoning",
    "hidden_reasoning",
    "reasoning-content",
    "reasoning_content",
    "thinking",
    "thoughts",
}
_FORBIDDEN_TEXT = re.compile(
    r"(?i)[\"']?(?:authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|api-key)[\"']?\s*[:=]"
)


def _reject_secret_material(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError(f"secret-bearing field is forbidden at {path}.{key}")
            _reject_secret_material(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_material(child, f"{path}[{index}]")
    elif isinstance(value, str) and _FORBIDDEN_TEXT.search(value):
        raise ValueError(f"serialized auth header/cookie is forbidden at {path}")


def _reject_evidence_material(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _HIDDEN_REASONING_KEYS:
                raise ValueError(f"provider-internal hidden reasoning is forbidden at {path}.{key}")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError(f"secret-bearing field is forbidden at {path}.{key}")
            _reject_evidence_material(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_evidence_material(child, f"{path}[{index}]")
    elif isinstance(value, str) and _FORBIDDEN_TEXT.search(value):
        raise ValueError(f"serialized auth header/cookie is forbidden at {path}")
