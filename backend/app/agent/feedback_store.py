"""Encrypted local P0 evidence store with a lifecycle separate from fixtures."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.agent.contracts import EvidenceBundle, FeedbackRecord, FeedbackState
from app.core import crypto


class IdempotencyConflict(ValueError):
    """The same stable client ID was reused for different logical content."""


@dataclass(frozen=True)
class SaveReceipt:
    server_id: UUID
    created: bool
    acknowledged: bool = True


class EncryptedReviewStore:
    """Small synthetic-only store; no runtime route registers it during P0."""

    SCHEMA_VERSION = "mimi.local-review-store.v1"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.bundles = self.root / "bundles"
        self.feedback = self.root / "feedback"
        self.clients = self.root / "clients"
        for directory in (self.bundles, self.feedback, self.clients):
            directory.mkdir(parents=True, exist_ok=True)
        marker = self.root / "STORE-MARKER.json"
        if not marker.exists():
            _atomic_write_text(
                marker,
                json.dumps(
                    {
                        "schema_version": self.SCHEMA_VERSION,
                        "lifecycle": "durable-review-evidence",
                        "ordinary_fixture_reset": "must-not-delete",
                    },
                    sort_keys=True,
                ),
            )

    def save_bundle(self, bundle: EvidenceBundle) -> SaveReceipt:
        existing = self._client_lookup("bundle", bundle.client_id)
        digest = bundle.content_digest()
        if existing:
            if existing["digest"] != digest:
                raise IdempotencyConflict("bundle client_id already binds different content")
            return SaveReceipt(server_id=UUID(existing["server_id"]), created=False)

        self._write_encrypted(
            self.bundles / f"{bundle.bundle_id}.enc", bundle.model_dump(mode="json")
        )
        self._write_client_binding("bundle", bundle.client_id, bundle.bundle_id, digest)
        return SaveReceipt(server_id=bundle.bundle_id, created=True)

    def load_bundle(self, bundle_id: UUID) -> EvidenceBundle:
        return EvidenceBundle.model_validate(
            self._read_encrypted(self.bundles / f"{bundle_id}.enc")
        )

    def save_feedback(self, record: FeedbackRecord) -> SaveReceipt:
        existing = self._client_lookup("feedback", record.client_id)
        digest = record.content_digest()
        if existing:
            if existing["digest"] != digest:
                raise IdempotencyConflict("feedback client_id already binds different content")
            return SaveReceipt(server_id=UUID(existing["server_id"]), created=False)

        self._write_encrypted(
            self.feedback / f"{record.feedback_id}.enc", record.model_dump(mode="json")
        )
        self._write_client_binding("feedback", record.client_id, record.feedback_id, digest)
        return SaveReceipt(server_id=record.feedback_id, created=True)

    def load_feedback(self, feedback_id: UUID) -> FeedbackRecord:
        return FeedbackRecord.model_validate(
            self._read_encrypted(self.feedback / f"{feedback_id}.enc")
        )

    def acknowledge_feedback(
        self, feedback_id: UUID, *, acknowledged_at: datetime | None = None
    ) -> FeedbackRecord:
        record = self.load_feedback(feedback_id)
        updated = record.model_copy(
            update={
                "state": FeedbackState.ACKNOWLEDGED,
                "acknowledged_at": acknowledged_at or datetime.now(UTC),
                "unresolved": True,
            }
        )
        updated = FeedbackRecord.model_validate(updated.model_dump(mode="python"))
        self._write_encrypted(self.feedback / f"{feedback_id}.enc", updated.model_dump(mode="json"))
        return updated

    def _write_client_binding(
        self, kind: str, client_id: str, server_id: UUID, digest: str
    ) -> None:
        self._write_encrypted(
            self.clients / f"{kind}-{_safe_name(client_id)}.enc",
            {"kind": kind, "client_id": client_id, "server_id": str(server_id), "digest": digest},
        )

    def _client_lookup(self, kind: str, client_id: str) -> dict[str, str] | None:
        path = self.clients / f"{kind}-{_safe_name(client_id)}.enc"
        return self._read_encrypted(path) if path.exists() else None

    @staticmethod
    def _write_encrypted(path: Path, value: object) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        _atomic_write_text(path, crypto.encrypt(serialized))

    @staticmethod
    def _read_encrypted(path: Path) -> dict:
        return json.loads(crypto.decrypt(path.read_text(encoding="utf-8")))


def _safe_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
