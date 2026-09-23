"""Encrypted local P0 evidence store with a lifecycle separate from fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.agent.contracts import EvidenceBundle, FeedbackRecord, FeedbackState
from app.core import crypto

_STORE_LOCKS_GUARD = threading.Lock()
_STORE_LOCKS: dict[Path, threading.RLock] = {}


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
    MAX_BUNDLE_BYTES = 1_048_576
    MAX_FEEDBACK_BYTES = 65_536
    MAX_BINDING_BYTES = 8_192

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.bundles = self.root / "bundles"
        self.feedback = self.root / "feedback"
        self.clients = self.root / "clients"
        self.pending = self.root / "pending"
        with _STORE_LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(self.root, threading.RLock())
        for directory in (self.bundles, self.feedback, self.clients, self.pending):
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
        self._recover_pending()

    def save_bundle(self, bundle: EvidenceBundle) -> SaveReceipt:
        with self._lock:
            existing = self._client_lookup("bundle", bundle.client_id)
            digest = bundle.content_digest()
            if existing:
                if existing["digest"] != digest:
                    raise IdempotencyConflict("bundle client_id already binds different content")
                return SaveReceipt(server_id=UUID(existing["server_id"]), created=False)

            payload = bundle.model_dump(mode="json")
            pending = self._write_pending(
                "bundle", bundle.client_id, bundle.bundle_id, digest, payload
            )
            try:
                self._write_encrypted(
                    self.bundles / f"{bundle.bundle_id}.enc",
                    payload,
                    max_plaintext_bytes=self.MAX_BUNDLE_BYTES,
                )
                self._write_client_binding("bundle", bundle.client_id, bundle.bundle_id, digest)
            except Exception:
                (self.bundles / f"{bundle.bundle_id}.enc").unlink(missing_ok=True)
                pending.unlink(missing_ok=True)
                raise
            pending.unlink()
            return SaveReceipt(server_id=bundle.bundle_id, created=True)

    def load_bundle(self, bundle_id: UUID) -> EvidenceBundle:
        return EvidenceBundle.model_validate(
            self._read_encrypted(self.bundles / f"{bundle_id}.enc")
        )

    def save_feedback(self, record: FeedbackRecord) -> SaveReceipt:
        with self._lock:
            existing = self._client_lookup("feedback", record.client_id)
            digest = record.content_digest()
            if existing:
                if existing["digest"] != digest:
                    raise IdempotencyConflict("feedback client_id already binds different content")
                return SaveReceipt(server_id=UUID(existing["server_id"]), created=False)

            payload = record.model_dump(mode="json")
            pending = self._write_pending(
                "feedback", record.client_id, record.feedback_id, digest, payload
            )
            try:
                self._write_encrypted(
                    self.feedback / f"{record.feedback_id}.enc",
                    payload,
                    max_plaintext_bytes=self.MAX_FEEDBACK_BYTES,
                )
                self._write_client_binding("feedback", record.client_id, record.feedback_id, digest)
            except Exception:
                (self.feedback / f"{record.feedback_id}.enc").unlink(missing_ok=True)
                pending.unlink(missing_ok=True)
                raise
            pending.unlink()
            return SaveReceipt(server_id=record.feedback_id, created=True)

    def load_feedback(self, feedback_id: UUID) -> FeedbackRecord:
        return FeedbackRecord.model_validate(
            self._read_encrypted(self.feedback / f"{feedback_id}.enc")
        )

    def acknowledge_feedback(
        self, feedback_id: UUID, *, acknowledged_at: datetime | None = None
    ) -> FeedbackRecord:
        with self._lock:
            record = self.load_feedback(feedback_id)
            updated = record.model_copy(
                update={
                    "state": FeedbackState.ACKNOWLEDGED,
                    "acknowledged_at": acknowledged_at or datetime.now(UTC),
                    "unresolved": True,
                }
            )
            updated = FeedbackRecord.model_validate(updated.model_dump(mode="python"))
            self._write_encrypted(
                self.feedback / f"{feedback_id}.enc",
                updated.model_dump(mode="json"),
                max_plaintext_bytes=self.MAX_FEEDBACK_BYTES,
            )
            return updated

    def _write_client_binding(
        self, kind: str, client_id: str, server_id: UUID, digest: str
    ) -> None:
        self._write_encrypted(
            self.clients / f"{kind}-{_safe_name(client_id)}.enc",
            {"kind": kind, "client_id": client_id, "server_id": str(server_id), "digest": digest},
            max_plaintext_bytes=self.MAX_BINDING_BYTES,
        )

    def _client_lookup(self, kind: str, client_id: str) -> dict[str, str] | None:
        path = self.clients / f"{kind}-{_safe_name(client_id)}.enc"
        return self._read_encrypted(path) if path.exists() else None

    def _write_pending(
        self, kind: str, client_id: str, server_id: UUID, digest: str, payload: object
    ) -> Path:
        path = self.pending / f"{kind}-{_safe_name(client_id)}.enc"
        cap = self.MAX_BUNDLE_BYTES if kind == "bundle" else self.MAX_FEEDBACK_BYTES
        self._write_encrypted(
            path,
            {
                "kind": kind,
                "client_id": client_id,
                "server_id": str(server_id),
                "digest": digest,
                "payload": payload,
            },
            max_plaintext_bytes=cap + self.MAX_BINDING_BYTES,
        )
        return path

    def _recover_pending(self) -> None:
        """Finish a two-file save interrupted after its encrypted intent became durable."""

        with self._lock:
            for path in self.pending.glob("*.enc"):
                intent = self._read_encrypted(path)
                kind = intent["kind"]
                server_id = UUID(intent["server_id"])
                if kind == "bundle":
                    destination = self.bundles / f"{server_id}.enc"
                    cap = self.MAX_BUNDLE_BYTES
                elif kind == "feedback":
                    destination = self.feedback / f"{server_id}.enc"
                    cap = self.MAX_FEEDBACK_BYTES
                else:
                    raise ValueError(f"unknown pending review-store kind: {kind!r}")
                self._write_encrypted(destination, intent["payload"], max_plaintext_bytes=cap)
                self._write_client_binding(kind, intent["client_id"], server_id, intent["digest"])
                path.unlink()

    @staticmethod
    def _write_encrypted(path: Path, value: object, *, max_plaintext_bytes: int) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > max_plaintext_bytes:
            raise ValueError(f"encrypted record exceeds {max_plaintext_bytes} byte P0 cap")
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
