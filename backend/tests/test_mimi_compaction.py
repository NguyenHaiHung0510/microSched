"""Deterministic tests for source-bound, frontier-aware Mimi checkpoints."""

import hashlib
from uuid import uuid4

import pytest

from app.agent.compaction import CheckpointSource, make_checkpoint, validate_checkpoint


def _source(sequence: int, content: str) -> CheckpointSource:
    return CheckpointSource(
        id=uuid4(),
        sequence=sequence,
        role="user" if sequence % 2 else "assistant",
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        content=content,
    )


def _checkpoint(sources, prior=None):
    return make_checkpoint(
        sources=sources,
        prior=prior,
        policy_sha256="a" * 64,
        pending_preview={"id": "preview-1"},
        pending_draft=None,
    )


def test_checkpoint_binds_source_hashes_frontier_and_pending_state() -> None:
    sources = [_source(4, "what is due?"), _source(5, "two tasks are due")]
    checkpoint = _checkpoint(sources)
    assert checkpoint["frontier"] == 5
    assert checkpoint["source_refs"] == [
        {"id": str(source.id), "sequence": source.sequence, "sha256": source.content_sha256}
        for source in sources
    ]
    assert checkpoint["summary_kind"] == "extractive_excerpt"
    assert checkpoint["pending_preview"] == {"id": "preview-1"}
    validate_checkpoint(checkpoint, expected_sources=sources, prior=None)


def test_checkpoint_rejects_frontier_overlap_and_source_hash_mismatch() -> None:
    prior = {"frontier": 5, "summary": "older", "decisions": [], "unresolved": []}
    with pytest.raises(ValueError, match="checkpoint_frontier_overlap"):
        _checkpoint([_source(5, "overlap")], prior=prior)

    sources = [_source(7, "original source")]
    checkpoint = _checkpoint(sources)
    changed_hash = CheckpointSource(
        id=sources[0].id,
        sequence=sources[0].sequence,
        role=sources[0].role,
        content_sha256="b" * 64,
        content=sources[0].content,
    )
    with pytest.raises(ValueError, match="checkpoint_sources_invalid"):
        validate_checkpoint(checkpoint, expected_sources=[changed_hash], prior=None)

    hash_mismatch = CheckpointSource(
        id=uuid4(),
        sequence=8,
        role="user",
        content_sha256="c" * 64,
        content="content whose hash does not match",
    )
    with pytest.raises(ValueError, match="checkpoint_source_hash_invalid"):
        _checkpoint([hash_mismatch])


def test_checkpoint_rejects_tampering_and_preserves_prior_provenance() -> None:
    first_sources = [_source(1, "first user message")]
    prior = _checkpoint(first_sources)
    next_sources = [_source(2, "assistant reply")]
    checkpoint = _checkpoint(next_sources, prior=prior)
    assert checkpoint["prior_checkpoint_sha256"]
    assert checkpoint["summary"].startswith(prior["summary"])

    tampered = {**checkpoint, "summary": "rewritten summary"}
    with pytest.raises(ValueError, match="checkpoint_summary"):
        validate_checkpoint(tampered, expected_sources=next_sources, prior=prior)

    wrong_prior = {**prior, "summary": "changed prior"}
    with pytest.raises(ValueError, match="checkpoint_prior_invalid"):
        validate_checkpoint(checkpoint, expected_sources=next_sources, prior=wrong_prior)

    missing_prior_decision = {**prior, "decisions": ["approved direction"]}
    checkpoint_without_prior_decision = _checkpoint(next_sources, prior=prior)
    checkpoint_without_prior_decision["decisions"] = []
    checkpoint_without_prior_decision["prior_checkpoint_sha256"] = hashlib.sha256(
        __import__("json")
        .dumps(missing_prior_decision, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="checkpoint_prior_decisions_missing"):
        validate_checkpoint(
            checkpoint_without_prior_decision,
            expected_sources=next_sources,
            prior=missing_prior_decision,
        )
