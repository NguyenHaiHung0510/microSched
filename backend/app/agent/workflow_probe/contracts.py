"""Shared workflow leaf contracts for the control and graph experiments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

Domain = Literal["task", "note"]
MAX_SELECTION = 16
MAX_FRAME_BYTES = 64 * 1024


class ProbeBlocked(ValueError):
    """A lifecycle/authority contract failed; no execution is authorized."""


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def encode_frame(value: dict[str, object]) -> str:
    encoded = canonical_json(value)
    if len(encoded.encode("utf-8")) > MAX_FRAME_BYTES:
        raise ProbeBlocked("frame_budget_exceeded")
    return encoded


@dataclass(frozen=True)
class Record:
    record_id: str
    version: int
    title: str


@dataclass(frozen=True)
class Adapter:
    """Synthetic domain-specific leaf; no domain logic belongs in a runner."""

    domain: Domain
    title_prefix: str

    def materialize(self, records: tuple[Record, ...]) -> tuple[tuple[str, str], ...]:
        return tuple((record.record_id, self.title_prefix + record.title) for record in records)


TASK_ADAPTER = Adapter("task", "[planned] ")
NOTE_ADAPTER = Adapter("note", "[indexed] ")


@dataclass(frozen=True)
class Preview:
    authority_ref: str
    owner: str
    generation: int
    policy: str
    domain: Domain
    sources: tuple[Record, ...]
    operations: tuple[tuple[str, str], ...]

    def content(self) -> dict[str, object]:
        return {
            "authority_ref": self.authority_ref,
            "owner": self.owner,
            "generation": self.generation,
            "policy": self.policy,
            "domain": self.domain,
            "sources": [
                {"id": record.record_id, "version": record.version, "title": record.title}
                for record in self.sources
            ],
            "operations": [{"id": key, "title": title} for key, title in self.operations],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_frame(self.content()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Confirmation:
    owner: str
    generation: int
    preview_digest: str


def freeze_preview(
    adapter: Adapter,
    records: tuple[Record, ...],
    *,
    owner: str,
    generation: int,
    policy: str,
    authority_ref: str | None = None,
) -> Preview:
    """Server materialization freezes source versions and exact operations."""
    if not owner or not policy or type(generation) is not int or generation < 1:
        raise ProbeBlocked("invalid_identity")
    if adapter.domain not in {"task", "note"}:
        raise ProbeBlocked("unsupported_synthetic_domain")
    if not 1 <= len(records) <= MAX_SELECTION:
        raise ProbeBlocked("selection_budget_exceeded")
    if len({record.record_id for record in records}) != len(records):
        raise ProbeBlocked("duplicate_source")
    if any(
        not record.record_id or type(record.version) is not int or record.version < 1
        for record in records
    ):
        raise ProbeBlocked("invalid_source_version")
    preview = Preview(
        authority_ref or str(uuid4()),
        owner,
        generation,
        policy,
        adapter.domain,
        records,
        adapter.materialize(records),
    )
    encode_frame(preview.content())
    return preview


def authorize_confirmation(
    preview: Preview,
    confirmation: Confirmation,
    *,
    source_versions: dict[str, int],
    policy: str,
    now: datetime,
    expires_at: datetime,
) -> tuple[tuple[str, str], ...]:
    """Pure gate only; atomic consumption and mutation belong to the PG store."""
    if now.tzinfo is None or expires_at.tzinfo is None:
        raise ProbeBlocked("clock_must_be_aware")
    if now >= expires_at:
        raise ProbeBlocked("run_expired")
    if policy != preview.policy:
        raise ProbeBlocked("policy_requires_repreview")
    if (
        confirmation.owner != preview.owner
        or type(confirmation.generation) is not int
        or confirmation.generation != preview.generation
        or confirmation.preview_digest != preview.digest
    ):
        raise ProbeBlocked("confirmation_mismatch")
    if any(type(value) is not int for value in source_versions.values()) or source_versions != {
        record.record_id: record.version for record in preview.sources
    }:
        raise ProbeBlocked("source_requires_repreview")
    return preview.operations
