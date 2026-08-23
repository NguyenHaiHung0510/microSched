"""Synthetic, privacy-safe contracts for the 012 cutover transform."""

import asyncio
import base64
import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.cutover_v2 import (
    APP_READABLE_PRESERVE,
    ARTIFACT_KEY_ENV,
    ARTIFACT_MAGIC,
    DOMAIN_COMPONENTS,
    FLY_APP_ENV,
    OWNER_PUBLIC_KEY_ENV,
    TARGET_FIELDS,
    CutoverError,
    ManifestError,
    SourceSnapshot,
    SourceValidationError,
    _normalize_catalog_sql,
    actual_code_identity,
    approval_payload,
    assert_current_fly_stopped,
    async_main,
    build_failure_receipt,
    build_manifest,
    calendar_bucket_inventory,
    canonical_value,
    digest_rows,
    empty_inventory,
    failure_receipt_payload,
    finalize_failure_receipt,
    finalize_manifest,
    fly_state_verifier_from_env,
    manifest_digest,
    new_uuid7,
    parse_fly_status,
    parser,
    read_failure_receipt,
    read_final_manifest,
    transform_source,
    validate_source,
    verify_source_dump,
    write_failure_receipt,
    write_manifest,
)

NOW = datetime(2026, 8, 20, 12, 34, 56, 1, tzinfo=UTC)


def freeze_cutover_clock(monkeypatch: pytest.MonkeyPatch, current_time: datetime) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return current_time.replace(tzinfo=None)
            return current_time.astimezone(tz)

    monkeypatch.setattr("scripts.cutover_v2.datetime", FrozenDateTime)


NATIVE_FLY_STOPPED = {
    "PlatformVersion": "machines",
    "Machines": [
        {
            "id": "machine-synthetic",
            "state": "stopped",
            "events": [
                {
                    "type": "start",
                    "status": "started",
                    "source": "flyd",
                    "timestamp": 1724150000000,
                },
                {
                    "type": "launch",
                    "status": "created",
                    "source": "user",
                    "timestamp": 1724140000000,
                },
            ],
        }
    ],
}


@pytest.mark.parametrize(
    ("catalog_definition", "expected"),
    [
        ("PRIMARY KEY (id)", "id"),
        (
            "UNIQUE (subject_type, subject_id, dispatched_on)",
            "subject_type,subject_id,dispatched_on",
        ),
        (
            "FOREIGN KEY (source_id) REFERENCES microsched.calendar_source(id) ON DELETE CASCADE",
            "(source_id) references microsched.calendar_source(id) on delete cascade",
        ),
        (
            "CHECK ((entity_type IS NULL) = (entity_id IS NULL))",
            "(entity_type is null) =(entity_id is null)",
        ),
        (
            "CHECK (kind = ANY (ARRAY['ics', 'excel', 'manual']))",
            "kind in('ics','excel','manual')",
        ),
        ('CHECK ("position" >= 0)', "position >= 0"),
        (
            "CHECK (quantity IS NULL OR quantity > 0::numeric)",
            "quantity is null or quantity > 0",
        ),
        (
            "CHECK (NOT is_private OR (title LIKE 'enc:v1:%' AND "
            "(body_md IS NULL OR body_md LIKE 'enc:v1:%')))",
            "not is_private or title like 'enc:v1:%' and"
            "(body_md is null or body_md like 'enc:v1:%')",
        ),
        (
            "CHECK (priority IS NULL OR (priority IN ('p1', 'p2', 'p3')))",
            "priority is null or priority in('p1','p2','p3')",
        ),
        (
            "CHECK ((input_mode = 'quantity' AND unit IS NOT NULL) OR "
            "(input_mode <> 'quantity' AND unit IS NULL))",
            "input_mode = 'quantity' and unit is not null or "
            "input_mode <> 'quantity' and unit is null",
        ),
    ],
)
def test_catalog_constraint_normalization_matches_pg_get_constraintdef(
    catalog_definition: str, expected: str
):
    assert _normalize_catalog_sql(catalog_definition) == expected


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


def test_native_fly_status_requires_one_stopped_machine_without_restart() -> None:
    state = parse_fly_status(NATIVE_FLY_STOPPED)
    assert state["sole_machine_stopped"] is True
    assert state["never_restarted"] is True
    assert state["machine_id"] == "machine-synthetic"
    for changed in (
        {**NATIVE_FLY_STOPPED, "Machines": []},
        {
            **NATIVE_FLY_STOPPED,
            "Machines": [{**NATIVE_FLY_STOPPED["Machines"][0], "state": "started"}],
        },
        {
            **NATIVE_FLY_STOPPED,
            "Machines": [
                {
                    **NATIVE_FLY_STOPPED["Machines"][0],
                    "events": [
                        {"type": "restart", "status": "restarted"},
                        *NATIVE_FLY_STOPPED["Machines"][0]["events"],
                    ],
                }
            ],
        },
    ):
        with pytest.raises(CutoverError):
            parse_fly_status(changed)
    old_history = {
        **NATIVE_FLY_STOPPED,
        "Machines": [
            {
                **NATIVE_FLY_STOPPED["Machines"][0],
                "events": [
                    {"type": "start", "status": "started", "timestamp": 1724150000000},
                    {"type": "stop", "status": "stopped", "timestamp": 1724160000000},
                    {"type": "start", "status": "started", "timestamp": 1724170000000},
                    {"type": "launch", "status": "created", "timestamp": 1724140000000},
                ],
            }
        ],
    }
    assert parse_fly_status(old_history, failure_time=NOW)["never_restarted"] is True
    post_failure_start = {
        **old_history,
        "Machines": [
            {
                **old_history["Machines"][0],
                "events": [
                    *old_history["Machines"][0]["events"],
                    {"type": "start", "status": "started", "timestamp": 1790000000000},
                ],
            }
        ],
    }
    with pytest.raises(CutoverError, match="after the signed failure cutoff"):
        parse_fly_status(post_failure_start, failure_time=NOW)
    with pytest.raises(CutoverError, match="event type is unknown"):
        parse_fly_status(
            {
                **NATIVE_FLY_STOPPED,
                "Machines": [
                    {
                        **NATIVE_FLY_STOPPED["Machines"][0],
                        "events": [
                            {"type": "mystery", "timestamp": 1724140000000},
                        ],
                    }
                ],
            },
            failure_time=NOW,
        )
    with pytest.raises(CutoverError, match="machine identity changed"):
        parse_fly_status(NATIVE_FLY_STOPPED, expected_machine_id="other-machine")


def test_native_fly_command_adapter_returns_raw_once(monkeypatch) -> None:
    monkeypatch.setenv(FLY_APP_ENV, "synthetic-app")
    monkeypatch.delenv("CUTOVER_FLY_STATE_COMMAND", raising=False)

    def fake_check_output(*args, **kwargs):
        assert args[0][-4:] == ["status", "--app", "synthetic-app", "--json"]
        return json.dumps(NATIVE_FLY_STOPPED)

    monkeypatch.setattr("scripts.cutover_v2.subprocess.check_output", fake_check_output)
    verifier = fly_state_verifier_from_env()
    raw = asyncio.run(verifier())
    assert "Machines" in raw
    normalized = asyncio.run(assert_current_fly_stopped(verifier))
    assert normalized["machine_id"] == "machine-synthetic"


def test_full_digest_changes_when_one_field_changes() -> None:
    row = {"id": uuid4(), "title": "safe", "created_at": NOW}
    changed = {**row, "title": "changed"}
    assert digest_rows("task", [row], ("id", "title", "created_at")) != digest_rows(
        "task", [changed], ("id", "title", "created_at")
    )


@pytest.mark.parametrize("component", (*DOMAIN_COMPONENTS, *APP_READABLE_PRESERVE))
def test_domain_and_preserve_full_row_digest_covers_every_ordered_field(component: str) -> None:
    row = {field: f"{component}-{field}" for field in TARGET_FIELDS[component]}
    baseline = digest_rows(component, [row], TARGET_FIELDS[component])
    for field in TARGET_FIELDS[component]:
        changed = {**row, field: f"changed-{field}"}
        assert digest_rows(component, [changed], TARGET_FIELDS[component]) != baseline


def test_calendar_buckets_keep_manual_and_imported_receipts_separate() -> None:
    rows = source_rows(calendar_uid="manual_123")
    imported = {**rows["calendar_events"][0], "id": uuid4(), "external_uid": "v1-schedule-9"}
    rows["calendar_events"].append(imported)
    buckets = calendar_bucket_inventory(rows)
    assert buckets["manual"]["count"] == 1
    assert buckets["ics_reimport"]["count"] == 1
    assert buckets["unclassified"]["count"] == 0
    assert buckets["manual"]["sorted_id_digest"] != buckets["ics_reimport"]["sorted_id_digest"]


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


def test_manifest_digest_unsigned_and_expiry_gates(monkeypatch) -> None:
    freeze_cutover_clock(monkeypatch, NOW)
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
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(ARTIFACT_KEY_ENV, base64.b64encode(b"a" * 32).decode())
    monkeypatch.setenv(
        OWNER_PUBLIC_KEY_ENV,
        base64.b64encode(key.public_key().public_bytes_raw()).decode(),
    )
    code = actual_code_identity()
    manifest = build_manifest(
        snapshot=SourceSnapshot(source_rows(), NOW),
        transformed=transformed,
        target_snapshot=target_snapshot,
        source_identity={"database": "microschedule_v2", "host": "local"},
        schema_attestation={"catalog_digest": "synthetic"},
        target_host_name="throwaway",
        script_sha=code["git_sha"],
        source_dump_sha256="a" * 64,
    )
    path = Path("cutover-test-manifest.tmp.json")
    try:
        write_manifest(path, manifest)
        encrypted = path.read_bytes()
        assert encrypted.startswith(ARTIFACT_MAGIC)
        assert b"synthetic title" not in encrypted
        assert b"run-synthetic" not in encrypted
        assert manifest_digest(
            {**manifest, "manifest_digest": manifest_digest(manifest)}
        ) == manifest_digest(manifest)
        with pytest.raises(ManifestError, match="owner approval"):
            read_final_manifest(
                path, expected_script_sha=code["git_sha"], expected_host="throwaway"
            )
        from scripts.cutover_v2 import decrypt_artifact

        unsigned = decrypt_artifact(path)
        signature = base64.b64encode(
            key.sign(
                json.dumps(
                    approval_payload(unsigned),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
        ).decode()
        finalize_manifest(path, signature)
        assert (
            read_final_manifest(
                path, expected_script_sha=code["git_sha"], expected_host="throwaway"
            )["manifest_digest"]
            == unsigned["manifest_digest"]
        )
        freeze_cutover_clock(monkeypatch, NOW + timedelta(hours=24))
        with pytest.raises(ManifestError, match="owner approval has expired"):
            read_final_manifest(
                path, expected_script_sha=code["git_sha"], expected_host="throwaway"
            )
    finally:
        path.unlink(missing_ok=True)


def test_finalized_manifest_dry_run_rechecks_target_and_authenticated_dump(
    monkeypatch, capsys
) -> None:
    import scripts.cutover_v2 as cutover_v2

    freeze_cutover_clock(monkeypatch, NOW)
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(ARTIFACT_KEY_ENV, base64.b64encode(b"f" * 32).decode())
    monkeypatch.setenv(
        OWNER_PUBLIC_KEY_ENV,
        base64.b64encode(key.public_key().public_bytes_raw()).decode(),
    )
    monkeypatch.setenv(
        "CUTOVER_TARGET_URL", "postgresql+asyncpg://microsched_app@throwaway.example/microsched"
    )
    monkeypatch.setenv(
        "CUTOVER_MIGRATOR_URL",
        "postgresql+asyncpg://microsched_migrator@throwaway.example/microsched",
    )
    code = actual_code_identity()
    snapshot = SourceSnapshot(source_rows(), NOW)
    transformed = transform_source(snapshot)
    target_snapshot = {
        component: empty_inventory(component)
        for component in (*DOMAIN_COMPONENTS, *APP_READABLE_PRESERVE)
    }
    identity = {
        "database": "microsched",
        "server_port": 5432,
        "cluster_name": "synthetic-cluster",
        "ddl_sha256": "d" * 64,
    }
    manifest = build_manifest(
        snapshot=snapshot,
        transformed=transformed,
        target_snapshot=target_snapshot,
        source_identity={"database": "microschedule_v2", "ddl_sha256": "s" * 64},
        schema_attestation={"catalog_digest": "catalog", "target_identity": identity},
        target_host_name="throwaway.example",
        target_identity=identity,
        source_dump_sha256="e" * 64,
        script_sha=code["git_sha"],
        script_file_sha256=code["file_sha256"],
    )
    manifest_path = Path("cutover-final-dry-run.tmp.age")
    dump_path = Path("cutover-final-dry-run.dump.age")
    write_manifest(manifest_path, manifest)
    unsigned = cutover_v2.decrypt_artifact(manifest_path)
    signature = base64.b64encode(
        key.sign(
            json.dumps(
                approval_payload(unsigned),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
    ).decode()
    finalize_manifest(manifest_path, signature)
    dump_path.write_bytes(b"age-encryption.org/v1\nsynthetic")

    class FakeEngine:
        class _Connection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

        def connect(self):
            return self._Connection()

        async def dispose(self):
            return None

    calls = {"dump": [], "inventory": 0}

    def fake_verify_dump(path, expected, *, require_authenticated_restore):
        calls["dump"].append((path, expected, require_authenticated_restore))
        assert require_authenticated_restore is True
        return "e" * 64

    async def fake_attest_schema(engine, *, expected_digest=None):
        assert expected_digest == "catalog"
        return {"catalog_digest": "catalog", "target_identity": identity}

    async def fake_collect(engine):
        calls["inventory"] += 1
        return identity, target_snapshot

    async def fake_source_identity(*args):
        return {"database": "microschedule_v2", "ddl_sha256": "s" * 64}

    async def fake_snapshot(engine):
        return snapshot

    async def fake_noop(engine):
        return None

    monkeypatch.setattr(cutover_v2, "verify_source_dump", fake_verify_dump)
    monkeypatch.setattr(cutover_v2, "migrator_engine", lambda: FakeEngine())
    monkeypatch.setattr(cutover_v2, "target_engine", lambda: FakeEngine())
    monkeypatch.setattr(cutover_v2, "source_engine", lambda: FakeEngine())
    monkeypatch.setattr(cutover_v2, "attest_schema", fake_attest_schema)
    monkeypatch.setattr(cutover_v2, "assert_app_cannot_read_alembic", fake_noop)
    monkeypatch.setattr(cutover_v2, "collect_target_inventory_as_app", fake_collect)
    monkeypatch.setattr(cutover_v2, "assert_source_identity", fake_noop)
    monkeypatch.setattr(cutover_v2, "assert_source_read_only", fake_noop)
    monkeypatch.setattr(cutover_v2, "read_connection_identity", fake_source_identity)
    monkeypatch.setattr(cutover_v2, "load_source_snapshot", fake_snapshot)
    monkeypatch.setattr(cutover_v2, "assert_target_coordinates", lambda: None)
    try:
        result = asyncio.run(
            async_main(
                parser().parse_args(
                    [
                        "--dry-run",
                        "--manifest",
                        str(manifest_path),
                        "--confirm-target-host",
                        "throwaway.example",
                        "--expected-script-sha",
                        code["git_sha"],
                        "--source-dump",
                        str(dump_path),
                        "--source-dump-sha256",
                        "e" * 64,
                    ]
                )
            )
        )
        assert result == 0
        assert len(calls["dump"]) == 2
        assert calls["inventory"] == 2
        assert "calendar_bucket manual" in capsys.readouterr().out
    finally:
        manifest_path.unlink(missing_ok=True)
        dump_path.unlink(missing_ok=True)


def test_empty_inventory_is_stable() -> None:
    first = empty_inventory("message")
    second = empty_inventory("message")
    assert first == second
    assert first["count"] == 0


def test_source_dump_hash_seam() -> None:
    dump = Path("synthetic-source.dump.age")
    dump.write_bytes(b"age-encryption.org/v1\nsynthetic encrypted payload")
    try:
        digest = verify_source_dump(dump)
        assert verify_source_dump(dump, digest) == digest
        with pytest.raises(CutoverError, match="SHA-256"):
            verify_source_dump(dump, "0" * 64)
        dump.write_bytes(b"plaintext pg_dump renamed to age")
        with pytest.raises(CutoverError, match="age envelope"):
            verify_source_dump(dump)
    finally:
        dump.unlink(missing_ok=True)


def test_failure_receipt_output_cannot_overwrite_input_before_probe() -> None:
    same_path = Path("cutover-same-artifact.tmp.age").resolve()
    original_bytes = b"encrypted input artifact bytes"
    same_path.write_bytes(original_bytes)
    args = parser().parse_args(
        [
            "--write-failure-receipt",
            str(same_path),
            "--manifest",
            str(same_path),
        ]
    )
    try:
        with pytest.raises(CutoverError, match="output must differ"):
            asyncio.run(async_main(args))
        assert same_path.read_bytes() == original_bytes
    finally:
        same_path.unlink(missing_ok=True)


def test_failure_receipt_signature_and_expiry_are_enforced() -> None:
    monkeypatch = pytest.MonkeyPatch()
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(ARTIFACT_KEY_ENV, base64.b64encode(b"b" * 32).decode())
    monkeypatch.setenv(
        OWNER_PUBLIC_KEY_ENV,
        base64.b64encode(key.public_key().public_bytes_raw()).decode(),
    )
    code = actual_code_identity()
    manifest = {
        "manifest_digest": "c" * 64,
        "run_id": "run-synthetic",
        "target_host": "throwaway",
        "script_sha": code["git_sha"],
        "script_file_sha256": code["file_sha256"],
        "source_dump_sha256": "d" * 64,
    }
    draft = build_failure_receipt(
        manifest,
        target_inventory={
            component: empty_inventory(component)
            for component in (*DOMAIN_COMPONENTS, *APP_READABLE_PRESERVE)
        },
        target_state=parse_fly_status(NATIVE_FLY_STOPPED),
        failed_command="commit",
        failure_class="unknown-after-submit",
        failure_stage="post-submit",
        failure_time=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    assert draft["failure_outcome"] == "unknown_after_submit"
    receipt = {
        "algorithm": "Ed25519",
        "run_id": manifest["run_id"],
        "manifest_digest": manifest["manifest_digest"],
        "script_sha": code["git_sha"],
        "script_file_sha256": code["file_sha256"],
        "target_host": "throwaway",
        "source_dump_sha256": manifest["source_dump_sha256"],
        "failed_command": "commit",
        "failure_outcome": "unknown_after_submit",
        "failure_class": "unknown-after-submit",
        "failure_stage": "post-submit",
        "failure_time": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "fly_state": "stopped",
        "target_state": parse_fly_status(NATIVE_FLY_STOPPED),
        "fly_never_restarted": True,
        "failed_run_domain_inventory": {
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
            )
        },
    }
    path = Path("cutover-failure-receipt.tmp.age")
    try:
        write_failure_receipt(path, receipt)
        signature = base64.b64encode(
            key.sign(
                json.dumps(
                    failure_receipt_payload(receipt),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
        ).decode()
        finalize_failure_receipt(path, signature)
        assert (
            read_failure_receipt(
                path,
                manifest=manifest,
                expected_script_sha=code["git_sha"],
                expected_host="throwaway",
                now=NOW,
            )["failure_class"]
            == "unknown-after-submit"
        )
        stale = {**receipt, "expires_at": (NOW - timedelta(seconds=1)).isoformat()}
        stale["signature"] = base64.b64encode(
            key.sign(
                json.dumps(
                    failure_receipt_payload(stale),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
        ).decode()
        write_failure_receipt(path, stale)
        with pytest.raises(ManifestError, match="expired"):
            read_failure_receipt(
                path,
                manifest=manifest,
                expected_script_sha=code["git_sha"],
                expected_host="throwaway",
                now=NOW,
            )
    finally:
        path.unlink(missing_ok=True)
        monkeypatch.undo()


def test_new_uuid7_is_uuid7() -> None:
    assert new_uuid7().version == 7
