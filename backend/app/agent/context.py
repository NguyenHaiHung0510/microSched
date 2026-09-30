"""Provider-neutral, typed authority and provenance for one Mimi model turn."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceManifest(StrictModel):
    source_id: str
    source_type: str
    query: dict[str, Any]
    projection: tuple[str, ...]
    version: str | None
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    count: int = Field(ge=0)
    coverage: Literal["complete", "partial", "unavailable"]
    omitted_fields: tuple[str, ...] = ()
    next_cursor: str | None = None
    data_as_of: datetime | None = None


class ContextBudget(StrictModel):
    context_limit: int = Field(ge=1)
    output_reserve: int = Field(ge=1)
    serialized_input_upper_bound: int = Field(ge=0)
    remaining_turns: int = Field(ge=0)
    remaining_tool_calls: int = Field(ge=0)
    deadline: datetime

    @model_validator(mode="after")
    def reject_overflow(self) -> ContextBudget:
        if self.serialized_input_upper_bound + self.output_reserve > self.context_limit:
            raise ValueError("context_overflow_preflight")
        return self


class RouteManifest(StrictModel):
    requested_model: str | None
    requested_effort: str | None
    route_policy_id: str


class CacheManifest(StrictModel):
    eligible_layers: tuple[str, ...]
    requested_mode: str
    cache_key_components: tuple[str, ...]


class PendingDraft(StrictModel):
    id: UUID
    revision: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    direction_state: Literal["pending", "approved", "rejected"]


class PendingPreview(StrictModel):
    id: UUID
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_versions: dict[str, str]
    expiry: datetime


class ContextManifest(StrictModel):
    request_id: str
    conversation_id: UUID
    generation: int = Field(ge=1)
    run_id: UUID
    policy_id: str
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sensitivity: Literal["standard"]
    write_mode: Literal["normal"]
    timezone: str
    checkpoint_id: UUID | None
    checkpoint_frontier: int = Field(ge=0)
    transcript_range: tuple[int, int] | None
    sources: tuple[SourceManifest, ...]
    pending_draft: PendingDraft | None
    pending_preview: PendingPreview | None
    budget: ContextBudget
    route: RouteManifest
    cache: CacheManifest

    def sha256(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class AuthorityEnvelope(StrictModel):
    lease_id: UUID
    reserved_task_id: UUID
    current_time: datetime
    deadline: datetime
    sensitivity: Literal["standard"]
    write_mode: Literal["normal"]
    allowed_tools: tuple[str, ...]
    disallowed_capabilities: tuple[str, ...]
    timezone: str
    remaining_turns: int = Field(ge=0)
    remaining_tool_calls: int = Field(ge=0)


class ContextEnvelope(StrictModel):
    """One assembled turn; plaintext is ephemeral and never a JSONB receipt."""

    policy_text: str
    authority: AuthorityEnvelope
    manifest: ContextManifest
    checkpoint: str | None
    transcript_suffix: tuple[dict[str, str], ...]
    pending_state: dict[str, Any]
    domain_evidence: tuple[dict[str, Any], ...]
    current_user_turn: str
    output_contract: dict[str, Any]

    @model_validator(mode="after")
    def bind_authority_to_manifest(self) -> ContextEnvelope:
        if (
            self.authority.sensitivity != self.manifest.sensitivity
            or self.authority.write_mode != self.manifest.write_mode
            or self.authority.deadline != self.manifest.budget.deadline
            or self.authority.timezone != self.manifest.timezone
        ):
            raise ValueError("context_authority_manifest_mismatch")
        return self


class ToolRequest(StrictModel):
    call_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any]


class ToolRequests(StrictModel):
    kind: Literal["tool_requests"] = "tool_requests"
    requests: tuple[ToolRequest, ...] = Field(min_length=1, max_length=3)


class AssistantText(StrictModel):
    kind: Literal["assistant_text"] = "assistant_text"
    text: str = Field(min_length=1)


class Clarification(StrictModel):
    kind: Literal["clarification"] = "clarification"
    question: str = Field(min_length=1)


class Draft(StrictModel):
    kind: Literal["draft"] = "draft"
    text: str = Field(min_length=1)


class PreviewCandidate(StrictModel):
    kind: Literal["preview_candidate"] = "preview_candidate"
    tool: str
    arguments: dict[str, Any]


class Blocked(StrictModel):
    kind: Literal["blocked"] = "blocked"
    reason: str = Field(min_length=1)


TerminalOutcome = Annotated[
    ToolRequests | AssistantText | Clarification | Draft | PreviewCandidate | Blocked,
    Field(discriminator="kind"),
]
TERMINAL_ADAPTER = TypeAdapter(TerminalOutcome)
OUTPUT_SCHEMA_SHA256 = hashlib.sha256(
    json.dumps(
        TERMINAL_ADAPTER.json_schema(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
).hexdigest()

AGENT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "mimi_terminal_v1",
        "strict": True,
        "schema": TERMINAL_ADAPTER.json_schema(),
    },
}
