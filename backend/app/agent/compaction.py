"""Validated, extractive Mimi checkpoints over encrypted canonical messages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MAX_CHECKPOINT_CHARS = 8_000
MAX_EXCERPT_CHARS = 180
MAX_CONSTRAINTS = 80


def _constraint_id(
    text: str, sequence: int | None, source_hash: str | None, kind: str | None = None
) -> str:
    return _digest({"text": text, "sequence": sequence, "sha256": source_hash, "kind": kind})


def active_constraint_context(checkpoint: dict[str, Any] | None) -> str | dict[str, Any] | None:
    """Render only validated active semantic records with their source citations."""
    if not checkpoint or checkpoint.get("summary_kind") != "semantic_model":
        return checkpoint["summary"] if checkpoint else None
    if "constraint_ledger" not in checkpoint:
        # Read legacy semantic v1 checkpoints without discarding their active
        # strings; new v2 compaction migrates these to immutable legacy entries.
        legacy = [
            {"kind": kind, "text": text, "source": {"legacy_frontier": checkpoint["frontier"]}}
            for kind, key in (("decision", "decisions"), ("unresolved", "unresolved"))
            for text in checkpoint.get(key, [])
        ]
        return (
            checkpoint["summary"]
            + "\nLEGACY_ACTIVE_CONSTRAINTS="
            + json.dumps(legacy, ensure_ascii=False, separators=(",", ":"))
        )
    ledger = checkpoint["constraint_ledger"]
    active = [entry for entry in ledger if entry["status"] == "active"]
    sources: list[dict[str, Any]] = []
    rows = []
    for item in active:
        # The encrypted canonical ledger and user inspector keep original
        # quotes. Main-model context needs the complete constraint meaning
        # plus immutable provenance, not a second copy of every source quote.
        source = {key: value for key, value in item["source"].items() if key != "quote"}
        if source not in sources:
            sources.append(source)
        # The answering model cannot mutate the checkpoint ledger. Full IDs
        # remain in canonical storage and the compaction helper, where they
        # are needed for validated supersession/resolution transitions.
        rows.append([item["text"], item["kind"], sources.index(source)])
    return {
        "schema": "mimi.active-context.v2",
        "summary": checkpoint["summary"],
        "sources": sources,
        "columns": ["text", "kind", "source_ref"],
        "rows": rows,
        "source_quotes": "omitted_from_wire; retained_in_canonical_checkpoint",
    }


def make_semantic_checkpoint(
    *,
    sources: list[CheckpointSource],
    prior: dict[str, Any] | None,
    policy_sha256: str,
    pending_preview: dict[str, Any] | None,
    pending_draft: dict[str, Any] | None,
    candidate: dict[str, Any],
    current_user_source: CheckpointSource | None = None,
) -> dict[str, Any]:
    """Validate attribution/shape; semantic faithfulness remains a QA obligation."""
    if set(candidate) != {"summary", "constraints", "supersessions", "resolutions"}:
        raise ValueError("checkpoint_semantic_candidate_shape_invalid")
    if (
        not isinstance(candidate["summary"], str)
        or not candidate["summary"].strip()
        or not any(character.isalnum() for character in candidate["summary"])
        or len(candidate["summary"]) > 6000
    ):
        raise ValueError("checkpoint_semantic_summary_invalid")
    for key in ("constraints", "supersessions", "resolutions"):
        if not isinstance(candidate[key], list) or len(candidate[key]) > 40:
            raise ValueError("checkpoint_semantic_lists_invalid")
    checkpoint = make_checkpoint(
        sources=sources,
        prior=prior,
        policy_sha256=policy_sha256,
        pending_preview=pending_preview,
        pending_draft=pending_draft,
    )
    ledger = [dict(item) for item in (prior.get("constraint_ledger", []) if prior else [])]
    # Migrate historical v1 strings as active immutable records. They remain
    # visible until a current user source explicitly supersedes/resolves them.
    if prior and "constraint_ledger" not in prior:
        for kind in ("decision", "unresolved"):
            for text in prior.get("decisions" if kind == "decision" else "unresolved", []):
                ledger.append(
                    {
                        "id": _constraint_id(text, None, None, kind),
                        "text": text,
                        "kind": kind,
                        "status": "active",
                        "source": {"legacy_checkpoint_sha256": _digest(prior)},
                        "resolution": None,
                    }
                )
    source_by_sequence = {
        source.sequence: source
        for source in [*sources, *([current_user_source] if current_user_source else [])]
    }

    def cited_user_source(item: dict[str, Any]) -> tuple[CheckpointSource, str]:
        if not {"source_sequence", "source_sha256", "quote"} <= set(item):
            raise ValueError("checkpoint_semantic_source_shape_invalid")
        sequence, source_hash, quote = (
            item.get("source_sequence"),
            item.get("source_sha256"),
            item.get("quote"),
        )
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or not isinstance(source_hash, str)
        ):
            raise ValueError("checkpoint_semantic_source_quote_invalid")
        source = source_by_sequence.get(sequence)
        if (
            source is None
            or source.role != "user"
            or source.content_sha256 != source_hash
            or not isinstance(quote, str)
            or not quote
            or quote not in source.content
        ):
            raise ValueError("checkpoint_semantic_source_quote_invalid")
        if hashlib.sha256(source.content.encode("utf-8")).hexdigest() != source.content_sha256:
            raise ValueError("checkpoint_semantic_source_hash_invalid")
        return source, quote

    new_entries = []
    for item in candidate["constraints"]:
        if not isinstance(item, dict) or set(item) != {
            "text",
            "kind",
            "source_sequence",
            "source_sha256",
            "quote",
        }:
            raise ValueError("checkpoint_semantic_constraint_invalid")
        text, kind = item["text"], item["kind"]
        source, quote = cited_user_source(item)
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 1000
            or kind not in {"decision", "unresolved"}
        ):
            raise ValueError("checkpoint_semantic_constraint_invalid")
        new_entries.append(
            {
                "id": _constraint_id(text, source.sequence, source.content_sha256, kind),
                "text": text,
                "kind": kind,
                "status": "active",
                "source": {
                    "sequence": source.sequence,
                    "sha256": source.content_sha256,
                    "quote": quote,
                },
                "resolution": None,
            }
        )

    ledger_by_id = {entry["id"]: entry for entry in ledger}
    for item in candidate["supersessions"]:
        if not isinstance(item, dict) or set(item) != {
            "prior_id",
            "source_sequence",
            "source_sha256",
            "quote",
            "replacement_text",
        }:
            raise ValueError("checkpoint_semantic_supersession_invalid")
        old = ledger_by_id.get(item["prior_id"])
        source, quote = cited_user_source(item)
        replacement = item["replacement_text"]
        replacement_entry = next(
            (entry for entry in new_entries if entry["text"] == replacement), None
        )
        if (
            old is None
            or old["status"] != "active"
            or old["kind"] != "decision"
            or not isinstance(replacement, str)
            or source.sequence <= (prior["frontier"] if prior else 0)
            or replacement_entry is None
            or replacement_entry["source"]["sequence"] != source.sequence
            or replacement_entry["source"]["sha256"] != source.content_sha256
        ):
            raise ValueError("checkpoint_semantic_supersession_invalid")
        old["status"] = "superseded"
        old["resolution"] = {
            "kind": "superseded",
            "by": replacement_entry["id"],
            "source": {
                "sequence": source.sequence,
                "sha256": source.content_sha256,
                "quote": quote,
            },
        }
    for item in candidate["resolutions"]:
        if not isinstance(item, dict) or set(item) != {
            "prior_id",
            "source_sequence",
            "source_sha256",
            "quote",
        }:
            raise ValueError("checkpoint_semantic_resolution_invalid")
        old = ledger_by_id.get(item["prior_id"])
        source, quote = cited_user_source(item)
        if (
            old is None
            or old["status"] != "active"
            or old["kind"] != "unresolved"
            or source.sequence <= (prior["frontier"] if prior else 0)
        ):
            raise ValueError("checkpoint_semantic_resolution_invalid")
        old["status"] = "resolved"
        old["resolution"] = {
            "kind": "resolved",
            "source": {
                "sequence": source.sequence,
                "sha256": source.content_sha256,
                "quote": quote,
            },
        }
    existing_ids = {entry["id"] for entry in ledger}
    for entry in new_entries:
        if entry["id"] not in existing_ids:
            ledger.append(entry)
            existing_ids.add(entry["id"])
    if len(ledger) > MAX_CONSTRAINTS:
        raise ValueError("checkpoint_semantic_ledger_limit")
    checkpoint.update(
        {
            "summary": candidate["summary"],
            "decisions": [],
            "unresolved": [],
            "constraint_ledger": ledger,
        }
    )
    checkpoint["summary_kind"] = "semantic_model"
    checkpoint["omitted_earlier_chars"] = 0
    checkpoint["schema_version"] = "mimi.checkpoint.v2"
    validate_checkpoint(checkpoint, expected_sources=sources, prior=prior)
    return checkpoint


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
    semantic = checkpoint.get("summary_kind") == "semantic_model"
    if semantic:
        required.add("constraint_ledger")
    expected_version = "mimi.checkpoint.v2" if semantic else "mimi.checkpoint.v1"
    if set(checkpoint) != required or checkpoint["schema_version"] != expected_version:
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
    if checkpoint["summary_kind"] not in {"extractive_excerpt", "semantic_model"}:
        raise ValueError("checkpoint_summary_kind_invalid")
    if not isinstance(checkpoint["summary"], str) or not checkpoint["summary"]:
        raise ValueError("checkpoint_summary_empty")
    expected_summary, omitted_chars = _expected_summary(expected_sources, prior)
    if (
        checkpoint["summary_kind"] == "extractive_excerpt"
        and checkpoint["summary"] != expected_summary
    ):
        raise ValueError("checkpoint_summary_invalid")
    if (
        checkpoint["summary_kind"] == "extractive_excerpt"
        and checkpoint["omitted_earlier_chars"]
        != (prior.get("omitted_earlier_chars", 0) if prior else 0) + omitted_chars
    ):
        raise ValueError("checkpoint_omitted_count_invalid")
    if len(checkpoint["summary"]) > MAX_CHECKPOINT_CHARS:
        raise ValueError("checkpoint_summary_too_large")
    if not isinstance(checkpoint["decisions"], list) or not isinstance(
        checkpoint["unresolved"], list
    ):
        raise ValueError("checkpoint_decision_shape_invalid")
    if semantic:
        ledger = checkpoint["constraint_ledger"]
        if not isinstance(ledger, list) or len(ledger) > MAX_CONSTRAINTS:
            raise ValueError("checkpoint_semantic_ledger_limit")
        ids = [item.get("id") for item in ledger if isinstance(item, dict)]
        if len(ids) != len(ledger) or len(set(ids)) != len(ids):
            raise ValueError("checkpoint_semantic_duplicate_id")
        if (
            prior
            and "constraint_ledger" in prior
            and ledger[: len(prior["constraint_ledger"])] != prior["constraint_ledger"]
        ):
            # An explicitly resolved record may change state, so compare its
            # immutable identity/source fields and permit only that transition.
            old_map = {item["id"]: item for item in ledger}
            for previous in prior["constraint_ledger"]:
                current = old_map.get(previous["id"])
                if current is None or any(
                    current.get(key) != previous.get(key)
                    for key in ("id", "text", "kind", "source")
                ):
                    raise ValueError("checkpoint_semantic_history_invalid")
                if previous["status"] != "active" and current != previous:
                    raise ValueError("checkpoint_semantic_history_invalid")
    if (
        not semantic
        and prior is not None
        and (
            checkpoint["decisions"][: len(prior["decisions"])] != prior["decisions"]
            or checkpoint["unresolved"][: len(prior["unresolved"])] != prior["unresolved"]
        )
    ):
        raise ValueError("checkpoint_prior_decisions_missing")
