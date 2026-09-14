"""Encrypted local feedback/evidence durability and idempotency tests."""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.agent.contracts import (
    CaptureStatus,
    CompletenessManifest,
    EvidenceBundle,
    EvidencePayload,
    FeedbackRecord,
    FeedbackState,
    Sensitivity,
    ToolExchange,
)
from app.agent.feedback_store import EncryptedReviewStore, IdempotencyConflict
from app.core import crypto
from app.core.settings import get_settings


@pytest.fixture
def fresh_key(monkeypatch):
    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", key)
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _bundle(*, client_id: str = "bundle-client-001", prompt: str = "Lập kế hoạch tuần"):
    expected = ("prompt", "request", "response", "tools", "route", "config", "usage")
    return EvidenceBundle(
        bundle_id=uuid4(),
        client_id=client_id,
        run_id=UUID("00000000-0000-7000-8000-000000000101"),
        turn_id=UUID("00000000-0000-7000-8000-000000000102"),
        call_id="call-synthetic-001",
        sensitivity=Sensitivity.PRIVATE,
        environment_id="mimi-p0-local-055",
        fixture_version="mimi-p0.v1",
        source_versions={"task": "task-v3", "fixture": "sha256:synthetic"},
        created_at=datetime(2030, 1, 15, tzinfo=UTC),
        completeness=CompletenessManifest(
            status=CaptureStatus.COMPLETE,
            expected_parts=expected,
            captured_parts=expected,
        ),
        payload=EvidencePayload(
            assembled_prompt=prompt,
            request={"model": "fake-provider", "input": [{"role": "user", "content": prompt}]},
            response={"output": [{"type": "text", "text": "Bản nháp synthetic"}]},
            tool_exchanges=(
                ToolExchange(
                    call_id="tool-call-001",
                    tool_name="task.read",
                    arguments={"task_id": "task-j02-overlap"},
                    result={"title": "Ca thực tập synthetic"},
                    outcome="succeeded",
                ),
            ),
            route={"provider": "fake", "model": "scripted-v1"},
            config={"temperature": 0},
            usage={"input_tokens": 42, "output_tokens": 12},
        ),
    )


def _feedback(bundle_id: UUID, *, client_id: str = "feedback-client-001", comment="Sai giờ"):
    return FeedbackRecord(
        feedback_id=uuid4(),
        client_id=client_id,
        target_type="turn",
        target_id="turn-synthetic-001",
        comment=comment,
        expected="Giữ ca thực tập và cảnh báo overlap",
        evidence_bundle_ids=(bundle_id,),
        sensitivity=Sensitivity.PRIVATE,
    )


def test_full_payload_roundtrip_is_encrypted_at_rest(fresh_key, tmp_path: Path) -> None:
    store = EncryptedReviewStore(tmp_path / "review")
    bundle = _bundle()
    receipt = store.save_bundle(bundle)

    assert receipt.created is True
    assert store.load_bundle(bundle.bundle_id) == bundle
    raw_files = "\n".join(path.read_text(encoding="utf-8") for path in store.root.rglob("*.enc"))
    assert "Lập kế hoạch tuần" not in raw_files
    assert "Ca thực tập synthetic" not in raw_files
    assert "enc:v1:" in raw_files


def test_retry_deduplicates_and_conflicting_reuse_is_rejected(fresh_key, tmp_path: Path) -> None:
    store = EncryptedReviewStore(tmp_path / "review")
    first = _bundle()
    first_receipt = store.save_bundle(first)
    retry = _bundle()
    retry_receipt = store.save_bundle(retry)
    assert retry_receipt.created is False
    assert retry_receipt.server_id == first_receipt.server_id

    with pytest.raises(IdempotencyConflict, match="different content"):
        store.save_bundle(_bundle(prompt="Nội dung khác"))


def test_acknowledged_unresolved_feedback_survives_restart_and_fixture_reset(
    fresh_key, tmp_path: Path
) -> None:
    domain_root = tmp_path / "disposable-fixtures"
    review_root = tmp_path / "durable-review"
    domain_root.mkdir()
    (domain_root / "seed-state.json").write_text("synthetic", encoding="utf-8")

    first_store = EncryptedReviewStore(review_root)
    bundle = _bundle()
    first_store.save_bundle(bundle)
    feedback = _feedback(bundle.bundle_id)
    first_store.save_feedback(feedback)
    acknowledged = first_store.acknowledge_feedback(
        feedback.feedback_id, acknowledged_at=datetime(2030, 1, 16, tzinfo=UTC)
    )
    assert acknowledged.state is FeedbackState.ACKNOWLEDGED
    assert acknowledged.unresolved is True

    (domain_root / "seed-state.json").unlink()
    (domain_root / "seed-state.json").write_text("reseeded", encoding="utf-8")

    restarted = EncryptedReviewStore(review_root)
    loaded = restarted.load_feedback(feedback.feedback_id)
    assert loaded.state is FeedbackState.ACKNOWLEDGED
    assert loaded.unresolved is True
    assert restarted.load_bundle(bundle.bundle_id).payload == bundle.payload


def test_feedback_retry_is_deduplicated(fresh_key, tmp_path: Path) -> None:
    store = EncryptedReviewStore(tmp_path / "review")
    bundle = _bundle()
    store.save_bundle(bundle)
    first = _feedback(bundle.bundle_id)
    created = store.save_feedback(first)
    retried = store.save_feedback(_feedback(bundle.bundle_id))
    assert created.created is True
    assert retried.created is False
    assert retried.server_id == created.server_id

    with pytest.raises(IdempotencyConflict, match="different content"):
        store.save_feedback(_feedback(bundle.bundle_id, comment="Khác nội dung"))


def test_two_store_instances_serialize_same_client_retry(fresh_key, tmp_path: Path) -> None:
    root = tmp_path / "review"
    first_store = EncryptedReviewStore(root)
    second_store = EncryptedReviewStore(root)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(
            pool.map(lambda store: store.save_bundle(_bundle()), (first_store, second_store))
        )

    assert sorted(receipt.created for receipt in receipts) == [False, True]
    assert receipts[0].server_id == receipts[1].server_id


def test_pending_intent_recovers_interrupted_bundle_binding(fresh_key, tmp_path: Path) -> None:
    root = tmp_path / "review"
    store = EncryptedReviewStore(root)
    bundle = _bundle()
    digest = bundle.content_digest()
    pending = store._write_pending(
        "bundle", bundle.client_id, bundle.bundle_id, digest, bundle.model_dump(mode="json")
    )
    store._write_encrypted(
        store.bundles / f"{bundle.bundle_id}.enc",
        bundle.model_dump(mode="json"),
        max_plaintext_bytes=store.MAX_BUNDLE_BYTES,
    )

    restarted = EncryptedReviewStore(root)

    assert not pending.exists()
    retry = restarted.save_bundle(_bundle())
    assert retry.created is False
    assert retry.server_id == bundle.bundle_id


def test_bundle_size_cap_applies_before_encrypted_write(fresh_key, tmp_path: Path) -> None:
    store = EncryptedReviewStore(tmp_path / "review")
    store.MAX_BUNDLE_BYTES = 512
    bundle = _bundle(prompt="x" * 2_000)

    with pytest.raises(ValueError, match="byte P0 cap"):
        store.save_bundle(bundle)
    assert list(store.bundles.glob("*.enc")) == []
    assert list(store.clients.glob("bundle-*.enc")) == []
