"""Synthetic, privacy-safe contracts for the 012 cutover transform."""

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.cutover_v2 import (
    CutoverError,
    ManifestError,
    SourceSnapshot,
    SourceValidationError,
    build_manifest,
    canonical_value,
    digest_rows,
    empty_inventory,
    manifest_digest,
    new_uuid7,
    read_final_manifest,
    transform_source,
    validate_source,
    verify_source_dump,
    write_manifest,
)

NOW = datetime(2026, 8, 20, 12, 34, 56, 1, tzinfo=UTC)


def source_rows(*, calendar_uid: str = "manual_123") -> dict[str, list[dict]]:
    task_id, note_id, priority_id = uuid4(), uuid4(), uuid4()
    event_id = uuid4()
    return {
        "tasks": [
            {
                "id": task_id,
                "title": "synthetic title",
                "note": "synthetic body",
                "status": "completed",
                "priority_id": priority_id,
                "due_at": NOW,
                "completed_at": NOW,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "task_items": [
            {
                "id": uuid4(),
                "task_id": task_id,
                "content": "synthetic item",
                "is_completed": True,
                "position": 0,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "notes": [
            {
                "id": note_id,
                "title": "synthetic note",
                "body": "synthetic note body",
                "pinned": True,
                "priority_id": None,
                "archived_at": None,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "note_items": [
            {
                "id": uuid4(),
                "note_id": note_id,
                "content": "synthetic note item",
                "is_done": True,
                "position": 0,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "priorities": [{"id": priority_id, "name": "Quan trọng hơn TN"}],
        "calendar_events": [
            {
                "id": event_id,
                "source_id": uuid4(),
                "title": "synthetic event",
                "location": None,
                "starts_at": NOW,
                "ends_at": NOW + timedelta(hours=1),
                "description": "synthetic description",
                "user_cancelled": False,
                "status": "scheduled",
                "external_uid": calendar_uid,
                "created_at": NOW,
                "updated_at": NOW,
                "display_name": "v1_sqlite_schedule",
            }
        ],
    }


def test_canonical_value_uses_length_prefixed_utf8_and_null() -> None:
    assert canonical_value(None) == "<NULL>"
    assert canonical_value("đỏ") == "5:đỏ"


def test_canonical_time_boundaries_are_fixed() -> None:
    assert canonical_value(time(0, 0, 0)) == "15:00:00:00.000000"
    assert canonical_value(time(23, 59, 59, 999999)) == "15:23:59:59.999999"


def test_canonical_rejects_timezone_bearing_time() -> None:
    with pytest.raises(CutoverError, match="timezone-bearing"):
        canonical_value(time(12, tzinfo=UTC))


def test_full_digest_changes_when_one_field_changes() -> None:
    row = {"id": uuid4(), "title": "safe", "created_at": NOW}
    changed = {**row, "title": "changed"}
    assert digest_rows("task", [row], ("id", "title", "created_at")) != digest_rows(
        "task", [changed], ("id", "title", "created_at")
    )


def test_transform_maps_constants_and_uuid7_manual_source() -> None:
    transformed = transform_source(SourceSnapshot(source_rows(), NOW))
    assert transformed["task"][0]["priority"] == "p1"
    assert transformed["note"][0]["pinned"] is True
    assert transformed["note_item"][0]["is_completed"] is True
    assert "is_done" not in transformed["note_item"][0]
    assert transformed["calendar_source"][0]["id"].version == 7


def test_ics_reimport_bucket_is_not_mapped() -> None:
    transformed = transform_source(SourceSnapshot(source_rows(calendar_uid="v1-schedule-9"), NOW))
    assert transformed["calendar_source"] == []
    assert transformed["calendar_event"] == []


def test_archived_source_is_fail_closed() -> None:
    rows = source_rows()
    rows["tasks"][0]["status"] = "archived"
    with pytest.raises(SourceValidationError, match="archived"):
        validate_source(rows)


def test_unknown_referenced_priority_is_fail_closed() -> None:
    rows = source_rows()
    rows["priorities"][0]["name"] = "owner-only priority"
    with pytest.raises(SourceValidationError, match="unknown referenced priority"):
        validate_source(rows)


def test_missing_child_parent_is_fail_closed() -> None:
    rows = source_rows()
    rows["task_items"][0]["task_id"] = uuid4()
    with pytest.raises(SourceValidationError, match="parent"):
        validate_source(rows)


def test_unclassified_calendar_uid_is_fail_closed() -> None:
    rows = source_rows(calendar_uid="future-pattern")
    with pytest.raises(SourceValidationError, match="unclassified"):
        validate_source(rows)


def test_manifest_digest_and_unsigned_gate() -> None:
    transformed = transform_source(SourceSnapshot(source_rows(), NOW))
    target_snapshot = {
        component: empty_inventory(component)
        for component in (
            "task",
            "task_item",
            "note",
            "note_item",
            "calendar_source",
            "calendar_event",
            "day_annotation",
            "tracker_group",
            "tracker",
            "entry",
            "subscription",
            "reminder_dispatch",
            "message",
            "audit_log",
            "app_setting",
            "session",
            "push_subscription",
        )
    }
    manifest = build_manifest(
        snapshot=SourceSnapshot(source_rows(), NOW),
        transformed=transformed,
        target_snapshot=target_snapshot,
        source_identity={"database": "microschedule_v2", "host": "local"},
        schema_attestation={"catalog_digest": "synthetic"},
        target_host_name="throwaway",
        script_sha="synthetic-sha",
    )
    path = Path("cutover-test-manifest.tmp.json")
    try:
        write_manifest(path, manifest)
        assert manifest_digest(
            {**manifest, "manifest_digest": manifest_digest(manifest)}
        ) == manifest_digest(manifest)
        with pytest.raises(ManifestError, match="owner approval"):
            read_final_manifest(
                path, expected_script_sha="synthetic-sha", expected_host="throwaway"
            )
        approved = json.loads(path.read_text(encoding="utf-8"))
        approved["owner_approval"] = {
            "manifest_digest": approved["manifest_digest"],
            "run_id": approved["run_id"],
            "script_sha": "synthetic-sha",
            "target_host": "throwaway",
            "phase_b_target_snapshot_digest": approved["phase_b_target_snapshot_digest"],
            "signature": "synthetic-owner-signature",
        }
        path.write_text(json.dumps(approved), encoding="utf-8")
        assert (
            read_final_manifest(
                path, expected_script_sha="synthetic-sha", expected_host="throwaway"
            )["manifest_digest"]
            == approved["manifest_digest"]
        )
    finally:
        path.unlink(missing_ok=True)


def test_empty_inventory_is_stable() -> None:
    first = empty_inventory("message")
    second = empty_inventory("message")
    assert first == second
    assert first["count"] == 0


def test_source_dump_hash_seam() -> None:
    dump = Path(__file__)
    digest = verify_source_dump(dump)
    assert verify_source_dump(dump, digest) == digest
    with pytest.raises(CutoverError, match="SHA-256"):
        verify_source_dump(dump, "0" * 64)


def test_new_uuid7_is_uuid7() -> None:
    assert new_uuid7().version == 7
