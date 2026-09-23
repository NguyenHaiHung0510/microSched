"""Validated, extractive Mimi checkpoints over encrypted canonical messages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MAX_CHECKPOINT_CHARS = 8_000
MAX_EXCERPT_CHARS = 180


@dataclass(frozen=True)
class CheckpointSource:
    id: UUID
    sequence: int
    role: str
    content_sha256: str
    content: str


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _expected_summary(
    sources: list[CheckpointSource], prior: dict[str, Any] | None
) -> tuple[str, int]:
    excerpts = [
        f"{item.role} #{item.sequence}: {item.content[:MAX_EXCERPT_CHARS]}" for item in sources
    ]
    prior_summary = prior["summary"] if prior is not None else ""
    full_summary = "\n".join(([prior_summary] if prior_summary else []) + excerpts)
    return full_summary[-MAX_CHECKPOINT_CHARS:], max(0, len(full_summary) - MAX_CHECKPOINT_CHARS)


def make_checkpoint(
    *,
    sources: list[CheckpointSource],
    prior: dict[str, Any] | None,
    policy_sha256: str,
    pending_preview: dict[str, Any] | None,
    pending_draft: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compress only the declared frontier; no invented semantic decisions."""

    if not sources:
        raise ValueError("checkpoint_source_empty")
    frontier = sources[-1].sequence
    if any(left.sequence >= right.sequence for left, right in zip(sources, sources[1:])):
        raise ValueError("checkpoint_source_order_invalid")
    if prior is not None and prior["frontier"] >= sources[0].sequence:
        raise ValueError("checkpoint_frontier_overlap")
    refs = [
        {"id": str(item.id), "sequence": item.sequence, "sha256": item.content_sha256}
        for item in sources
    ]
    summary, omitted_chars = _expected_summary(sources, prior)
    checkpoint = {
        "schema_version": "mimi.checkpoint.v1",
        "frontier": frontier,
        "policy_sha256": policy_sha256,
        "source_refs": refs,
        "prior_checkpoint_sha256": _digest(prior) if prior is not None else None,
        "summary": summary,
        "summary_kind": "extractive_excerpt",
        "omitted_earlier_chars": (prior.get("omitted_earlier_chars", 0) if prior else 0)
        + omitted_chars,
        "decisions": list(prior["decisions"]) if prior else [],
        "unresolved": list(prior["unresolved"]) if prior else [],
        "pending_preview": pending_preview,
        "pending_draft": pending_draft,
    }
    validate_checkpoint(checkpoint, expected_sources=sources, prior=prior)
    return checkpoint


def validate_checkpoint(
    checkpoint: dict[str, Any],
    *,
    expected_sources: list[CheckpointSource],
    prior: dict[str, Any] | None,
) -> None:
    """Reject an incomplete or falsely attributed replacement before activation."""

    required = {
        "schema_version",
        "frontier",
        "policy_sha256",
        "source_refs",
        "prior_checkpoint_sha256",
        "summary",
        "summary_kind",
        "omitted_earlier_chars",
        "decisions",
        "unresolved",
        "pending_preview",
        "pending_draft",
    }
    if set(checkpoint) != required or checkpoint["schema_version"] != "mimi.checkpoint.v1":
        raise ValueError("checkpoint_schema_invalid")
    if not expected_sources or checkpoint["frontier"] != expected_sources[-1].sequence:
        raise ValueError("checkpoint_frontier_invalid")
    expected_refs = [
        {"id": str(item.id), "sequence": item.sequence, "sha256": item.content_sha256}
        for item in expected_sources
    ]
    if checkpoint["source_refs"] != expected_refs:
        raise ValueError("checkpoint_sources_invalid")
    if any(
        hashlib.sha256(item.content.encode("utf-8")).hexdigest() != item.content_sha256
        for item in expected_sources
    ):
        raise ValueError("checkpoint_source_hash_invalid")
    if checkpoint["prior_checkpoint_sha256"] != (_digest(prior) if prior else None):
        raise ValueError("checkpoint_prior_invalid")
    if checkpoint["summary_kind"] != "extractive_excerpt":
        raise ValueError("checkpoint_summary_kind_invalid")
    if not isinstance(checkpoint["summary"], str) or not checkpoint["summary"]:
        raise ValueError("checkpoint_summary_empty")
    expected_summary, omitted_chars = _expected_summary(expected_sources, prior)
    if checkpoint["summary"] != expected_summary:
        raise ValueError("checkpoint_summary_invalid")
    if (
        checkpoint["omitted_earlier_chars"]
        != (prior.get("omitted_earlier_chars", 0) if prior else 0) + omitted_chars
    ):
        raise ValueError("checkpoint_omitted_count_invalid")
    if len(checkpoint["summary"]) > MAX_CHECKPOINT_CHARS:
        raise ValueError("checkpoint_summary_too_large")
    if not isinstance(checkpoint["decisions"], list) or not isinstance(
        checkpoint["unresolved"], list
    ):
        raise ValueError("checkpoint_decision_shape_invalid")
    if prior is not None and (
        checkpoint["decisions"][: len(prior["decisions"])] != prior["decisions"]
        or checkpoint["unresolved"][: len(prior["unresolved"])] != prior["unresolved"]
    ):
        raise ValueError("checkpoint_prior_decisions_missing")
