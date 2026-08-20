"""One-shot, fail-closed cutover tooling for the legacy Postgres store.

The module deliberately keeps the migration protocol boring and explicit.  It
does not contain credentials, does not print row content, and never silently
skips a source or target table.  The production ceremony (source dump,
owner-signed manifest and the actual command) remains an owner operation; the
same functions are used by the synthetic/throwaway-Postgres rehearsal.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import insert, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import select

from app.core.database_urls import async_postgres_url
from app.domain.models import (
    CalendarEvent,
    CalendarSource,
    Note,
    NoteItem,
    Task,
    TaskItem,
)

TRANSFORM_VERSION = "012-cutover-v2-2026-08-20"
SOURCE_DB_NAME = "microschedule_v2"
SOURCE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", "db"})
TARGET_APP_ROLE = "microsched_app"
TARGET_MIGRATOR_ROLES = frozenset({"microsched_migrator", "neondb_owner"})

PRIORITY_MAP: dict[str, str] = {
    "Quan trọng hơn TN": "p1",
    "Nguy hiểm": "p1",
    "Bỏ là nhót": "p2",
    "Phải làm": "p2",
    "Nên làm": "p3",
    "Optional": "p3",
}

APP_READABLE_PRESERVE = ("app_setting", "session", "push_subscription")
MAPPED_COMPONENTS = (
    "task",
    "task_item",
    "note",
    "note_item",
    "calendar_source",
    "calendar_event",
)
PURGE_ONLY_COMPONENTS = (
    "day_annotation",
    "tracker_group",
    "tracker",
    "entry",
    "subscription",
    "reminder_dispatch",
    "message",
    "audit_log",
)
DOMAIN_COMPONENTS = MAPPED_COMPONENTS + PURGE_ONLY_COMPONENTS
ALL_EXPECTED_TARGET_TABLES = frozenset(APP_READABLE_PRESERVE + DOMAIN_COMPONENTS)

TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "task": (
        "id",
        "title",
        "body_md",
        "status",
        "priority",
        "due_at",
        "completed_at",
        "is_private",
        "pinned",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "task_item": (
        "id",
        "task_id",
        "content",
        "is_completed",
        "position",
        "created_at",
        "updated_at",
    ),
    "note": (
        "id",
        "title",
        "body_md",
        "embedding",
        "pinned",
        "priority",
        "is_private",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "note_item": (
        "id",
        "note_id",
        "content",
        "is_completed",
        "position",
        "created_at",
        "updated_at",
    ),
    "calendar_source": ("id", "name", "kind", "color", "is_visible", "created_at", "updated_at"),
    "calendar_event": (
        "id",
        "source_id",
        "title",
        "location",
        "starts_at",
        "ends_at",
        "description_md",
        "all_day",
        "is_hidden",
        "created_at",
        "updated_at",
    ),
    "app_setting": ("id", "key", "value", "created_at", "updated_at"),
    "session": (
        "id",
        "token_hash",
        "user_email",
        "last_seen_at",
        "expires_at",
        "private_until",
        "created_at",
        "updated_at",
    ),
    "push_subscription": (
        "id",
        "endpoint",
        "p256dh",
        "auth",
        "user_agent",
        "last_seen_at",
        "created_at",
        "updated_at",
    ),
    "day_annotation": (
        "id",
        "starts_on",
        "ends_on",
        "label",
        "note_md",
        "color",
        "is_private",
        "created_at",
        "updated_at",
    ),
    "tracker_group": ("id", "name", "kind", "color", "position", "created_at", "updated_at"),
    "tracker": (
        "id",
        "name",
        "kind",
        "direction",
        "input_mode",
        "group_id",
        "unit",
        "color",
        "reminder_time",
        "reminder_text",
        "is_private",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "entry": (
        "id",
        "tracker_id",
        "subscription_id",
        "quantity",
        "amount",
        "list_amount",
        "occurred_at",
        "note_md",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "subscription": (
        "id",
        "name",
        "tracker_id",
        "amount",
        "list_amount",
        "period_count",
        "period_unit",
        "started_on",
        "expires_on",
        "auto_renew",
        "canceled_at",
        "note_md",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "reminder_dispatch": (
        "id",
        "subject_type",
        "subject_id",
        "dispatched_on",
        "status",
        "attempt_count",
        "last_attempt_at",
        "confirmed_entry_id",
        "confirmed_at",
        "created_at",
        "updated_at",
    ),
    "message": ("id", "role", "content", "is_private", "trace_id", "created_at", "updated_at"),
    "audit_log": (
        "id",
        "trace_id",
        "turn_id",
        "action",
        "tool",
        "entity_type",
        "entity_id",
        "payload",
        "created_at",
        "updated_at",
    ),
}

SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "tasks": (
        "id",
        "title",
        "note",
        "status",
        "priority_id",
        "due_at",
        "completed_at",
        "created_at",
        "updated_at",
    ),
    "task_items": (
        "id",
        "task_id",
        "content",
        "is_completed",
        "position",
        "created_at",
        "updated_at",
    ),
    "notes": (
        "id",
        "title",
        "body",
        "pinned",
        "priority_id",
        "archived_at",
        "created_at",
        "updated_at",
    ),
    "note_items": ("id", "note_id", "content", "is_done", "position", "created_at", "updated_at"),
    "priorities": ("id", "name"),
    "calendar_events": (
        "id",
        "source_id",
        "title",
        "location",
        "starts_at",
        "ends_at",
        "description",
        "user_cancelled",
        "status",
        "external_uid",
        "created_at",
        "updated_at",
        "display_name",
    ),
}

MODEL_TABLES = {
    "task": Task.__table__,
    "task_item": TaskItem.__table__,
    "note": Note.__table__,
    "note_item": NoteItem.__table__,
    "calendar_source": CalendarSource.__table__,
    "calendar_event": CalendarEvent.__table__,
}


class CutoverError(RuntimeError):
    """A safe, user-actionable abort which must not include row plaintext."""


class SourceValidationError(CutoverError):
    pass


class ManifestError(CutoverError):
    pass


def _safe_id(value: Any) -> str:
    return str(value) if isinstance(value, UUID) else str(value)


def new_uuid7() -> UUID:
    """Generate the one target-owned ID without depending on a provider function."""
    uuid7 = getattr(__import__("uuid"), "uuid7", None)
    if uuid7 is not None:
        return uuid7()
    # RFC 9562 layout: 48-bit Unix milliseconds, version 7, and RFC variant.
    import secrets
    import time as time_module

    milliseconds = int(time_module.time() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (milliseconds << 80) | (7 << 76) | (random_a << 64) | (2 << 62) | random_b
    return UUID(int=value)


def canonical_value(value: Any) -> str:
    """Encode one value under the fixed, non-ambiguous canonical contract."""
    if value is None:
        return "<NULL>"
    if isinstance(value, UUID):
        value = str(value).lower()
    elif isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CutoverError("naive timestamp in canonical row")
        value = value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    elif isinstance(value, date) and not isinstance(value, datetime):
        value = value.isoformat()
    elif isinstance(value, time):
        if value.tzinfo is not None:
            raise CutoverError("timezone-bearing time in canonical row")
        value = value.strftime("%H:%M:%S.%f")
    elif isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, Decimal):
        value = format(value, "f")
    elif isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CutoverError("non-finite float in canonical row")
        value = format(value, ".17g")
    elif not isinstance(value, str):
        value = str(value)
    encoded = str(value).encode("utf-8")
    return f"{len(encoded)}:{value}"


def canonical_row(fields: Sequence[str], row: Mapping[str, Any]) -> bytes:
    return b"|".join(canonical_value(row.get(field)).encode("utf-8") for field in fields)


def digest_rows(component: str, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> str:
    ordered = sorted(rows, key=lambda row: canonical_value(row.get("id")))
    payload = b"\0".join(canonical_row(fields, row) for row in ordered)
    return hashlib.sha256(
        TRANSFORM_VERSION.encode() + b"\0" + component.encode() + b"\0" + payload
    ).hexdigest()


def digest_ids(component: str, rows: Iterable[Mapping[str, Any]]) -> str:
    ordered = sorted(canonical_value(row.get("id")) for row in rows)
    payload = b"\0".join(item.encode("utf-8") for item in ordered)
    return hashlib.sha256(
        TRANSFORM_VERSION.encode() + b"\0ids\0" + component.encode() + b"\0" + payload
    ).hexdigest()


def inventory(
    component: str,
    rows: Iterable[Mapping[str, Any]],
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    rows = list(rows)
    fields = fields or TARGET_FIELDS[component]
    return {
        "count": len(rows),
        "sorted_id_digest": digest_ids(component, rows),
        "full_row_digest": digest_rows(component, rows, fields),
    }


def empty_inventory(component: str) -> dict[str, Any]:
    return inventory(component, [])


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_digest", "signature", "owner_approval"}
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_source_url() -> str:
    value = os.environ.get("CUTOVER_SOURCE_URL")
    if value:
        url = make_url(value)
        if (url.host or "").lower() not in SOURCE_HOSTS or url.database != SOURCE_DB_NAME:
            raise CutoverError("CUTOVER_SOURCE_URL must target local microschedule_v2")
        return async_postgres_url(value)
    password = os.environ.get("PGPW")
    if not password:
        raise CutoverError("PGPW is required for the local source")
    return URL.create(
        "postgresql+asyncpg",
        username="postgres",
        password=password,
        host="localhost",
        port=5432,
        database=SOURCE_DB_NAME,
    ).render_as_string(hide_password=False)


def target_url() -> str:
    value = os.environ.get("CUTOVER_TARGET_URL")
    if not value:
        raise CutoverError("CUTOVER_TARGET_URL is required")
    return async_postgres_url(value)


def target_host(value: str) -> str:
    return (make_url(value).host or "").lower().rstrip(".")


def assert_confirmed_host(value: str, confirmation: str) -> None:
    actual = target_host(value)
    expected = confirmation.lower().rstrip(".")
    if not actual or actual != expected:
        raise CutoverError("target host confirmation does not match CUTOVER_TARGET_URL")


def source_engine() -> AsyncEngine:
    return create_async_engine(
        build_source_url(),
        pool_pre_ping=True,
        connect_args={"server_settings": {"default_transaction_read_only": "on"}},
    )


def target_engine() -> AsyncEngine:
    return create_async_engine(target_url(), pool_pre_ping=True)


def migrator_engine() -> AsyncEngine:
    value = os.environ.get("CUTOVER_MIGRATOR_URL")
    if not value:
        raise CutoverError("CUTOVER_MIGRATOR_URL is required for schema attestation")
    return create_async_engine(async_postgres_url(value), pool_pre_ping=True)


async def assert_source_read_only(engine: AsyncEngine) -> None:
    """RED/GREEN seam: a real UPDATE must be rejected by Postgres 25006."""
    async with engine.connect() as connection:
        try:
            await connection.execute(text("UPDATE public.tasks SET title = title WHERE false"))
        except Exception as exc:  # asyncpg exposes sqlstate on the wrapped exception
            sqlstate = getattr(exc, "sqlstate", None) or getattr(
                getattr(exc, "orig", None), "sqlstate", None
            )
            if sqlstate != "25006":
                raise CutoverError(
                    "source write guard returned an unexpected database error"
                ) from None
        else:
            raise CutoverError("source write guard did not reject UPDATE (SQLSTATE 25006)")


async def assert_source_identity(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        database = (await connection.execute(text("SELECT current_database()"))).scalar_one()
    if database != SOURCE_DB_NAME:
        raise CutoverError("source database identity is not microschedule_v2")


async def assert_app_role(connection: Any) -> None:
    role = (await connection.execute(text("SELECT current_user"))).scalar_one()
    if role != TARGET_APP_ROLE:
        raise CutoverError("target DML connection is not microsched_app")


async def attest_schema(
    engine: AsyncEngine, *, expected_digest: str | None = None
) -> dict[str, Any]:
    """Bounded, read-only schema attestation; never used for target DML."""
    async with engine.connect() as connection:
        role = (await connection.execute(text("SELECT current_user"))).scalar_one()
        if role not in TARGET_MIGRATOR_ROLES:
            raise CutoverError("schema attestation requires microsched_migrator or neondb_owner")
        revision = (
            (await connection.execute(text("SELECT version_num FROM microsched.alembic_version")))
            .scalars()
            .all()
        )
        columns = (
            (
                await connection.execute(
                    text(
                        "SELECT table_name, column_name, data_type, is_nullable "
                        "FROM information_schema.columns WHERE table_schema='microsched' "
                        "ORDER BY table_name, ordinal_position"
                    )
                )
            )
            .mappings()
            .all()
        )
        table_names = set(
            (
                await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='microsched' ORDER BY table_name"
                    )
                )
            )
            .scalars()
            .all()
        )
    unknown = table_names - (set(ALL_EXPECTED_TARGET_TABLES) | {"alembic_version"})
    missing = set(ALL_EXPECTED_TARGET_TABLES) - table_names
    if unknown:
        raise CutoverError("unclassified microsched target table: " + ",".join(sorted(unknown)))
    if missing:
        raise CutoverError(
            "required microsched target table is missing: " + ",".join(sorted(missing))
        )
    payload = {
        "revision": list(revision),
        "tables": sorted(table_names),
        "columns": [dict(row) for row in columns],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    result = {
        "role": role,
        "revision": list(revision),
        "catalog_digest": hashlib.sha256(encoded).hexdigest(),
    }
    if expected_digest and result["catalog_digest"] != expected_digest:
        raise ManifestError("schema/catalog digest drift")
    return result


async def _fetch_source_rows(connection: Any, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in (await connection.execute(text(query))).mappings().all()]


@dataclass(frozen=True)
class SourceSnapshot:
    rows: dict[str, list[dict[str, Any]]]
    cutoff_at: datetime

    @property
    def source_inventory(self) -> dict[str, dict[str, Any]]:
        return {
            name: inventory(name, rows, SOURCE_FIELDS[name])
            for name, rows in self.rows.items()
            if name in SOURCE_FIELDS
        }


async def load_source_snapshot(engine: AsyncEngine) -> SourceSnapshot:
    async with engine.connect() as connection:
        source_rows = {
            "tasks": await _fetch_source_rows(
                connection,
                "SELECT id,title,note,status,priority_id,due_at,completed_at,created_at,"
                "updated_at FROM public.tasks ORDER BY id",
            ),
            "task_items": await _fetch_source_rows(
                connection,
                "SELECT id,task_id,content,is_completed,position,created_at,updated_at "
                "FROM public.task_items ORDER BY id",
            ),
            "notes": await _fetch_source_rows(
                connection,
                "SELECT id,title,body,pinned,priority_id,archived_at,created_at,updated_at "
                "FROM public.notes ORDER BY id",
            ),
            "note_items": await _fetch_source_rows(
                connection,
                "SELECT id,note_id,content,is_done,position,created_at,updated_at "
                "FROM public.note_items ORDER BY id",
            ),
            "priorities": await _fetch_source_rows(
                connection, "SELECT id,name FROM public.priorities ORDER BY id"
            ),
            "calendar_events": await _fetch_source_rows(
                connection,
                "SELECT ce.id,ce.source_id,ce.title,ce.location,ce.starts_at,ce.ends_at,"
                "ce.description,ce.user_cancelled,ce.status,ce.external_uid,ce.created_at,"
                "ce.updated_at,cs.display_name FROM public.calendar_events ce "
                "LEFT JOIN public.calendar_sources cs ON cs.id=ce.source_id ORDER BY ce.id",
            ),
        }
        cutoff = datetime.now(UTC)
    validate_source(source_rows)
    return SourceSnapshot(source_rows, cutoff)


async def verify_restored_source(
    engine: AsyncEngine, expected_inventory: Mapping[str, Mapping[str, Any]]
) -> SourceSnapshot:
    """Verify a fresh throwaway restore before it can feed recovery/Phase A.

    Decryption and ``pg_restore`` belong to the owner workstation ceremony.  This
    seam receives only the resulting throwaway connection and compares the full
    source inventory; it never opens the live source URL.
    """
    await assert_source_identity(engine)
    await assert_source_read_only(engine)
    snapshot = await load_source_snapshot(engine)
    if snapshot.source_inventory != dict(expected_inventory):
        raise CutoverError("restored source inventory does not match the signed source section")
    return snapshot


def _require_offset(value: Any, label: str) -> None:
    if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
        raise SourceValidationError(f"source timestamp is naive in {label}")


def validate_source(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    missing_tables = set(SOURCE_FIELDS) - set(rows)
    if missing_tables:
        raise SourceValidationError(
            "source inventory is missing table: " + ",".join(sorted(missing_tables))
        )
    tasks = list(rows.get("tasks", []))
    notes = list(rows.get("notes", []))
    task_ids = {row["id"] for row in tasks}
    note_ids = {row["id"] for row in notes}
    archived_tasks = [row for row in tasks if row.get("status") not in {"open", "completed"}]
    if archived_tasks:
        raise SourceValidationError(
            "source has archived or unknown task status; "
            f"count={len(archived_tasks)} id_digest={digest_ids('tasks', archived_tasks)}"
        )
    archived_notes = [row for row in notes if row.get("archived_at") is not None]
    if archived_notes:
        raise SourceValidationError(
            "source has archived notes; "
            f"count={len(archived_notes)} id_digest={digest_ids('notes', archived_notes)}"
        )
    for table in ("tasks", "task_items", "notes", "note_items", "calendar_events"):
        for row in rows.get(table, []):
            for key, value in row.items():
                if key.endswith("_at") or key in {
                    "created_at",
                    "updated_at",
                    "starts_at",
                    "ends_at",
                }:
                    _require_offset(value, f"{table}.{key}")
    if any(row.get("position", 0) < 0 for row in rows.get("task_items", [])):
        raise SourceValidationError("negative task item position")
    if any(row.get("position", 0) < 0 for row in rows.get("note_items", [])):
        raise SourceValidationError("negative note item position")
    if any(row.get("task_id") not in task_ids for row in rows.get("task_items", [])):
        raise SourceValidationError("task item parent is missing")
    if any(row.get("note_id") not in note_ids for row in rows.get("note_items", [])):
        raise SourceValidationError("note item parent is missing")
    priority_rows = {row["id"]: row for row in rows.get("priorities", [])}
    referenced = {row["priority_id"] for row in tasks + notes if row.get("priority_id") is not None}
    missing = referenced - set(priority_rows)
    if missing:
        raise SourceValidationError("referenced source priority is missing")
    names: dict[str, int] = {}
    for priority_id in referenced:
        name = priority_rows[priority_id].get("name")
        names[name] = names.get(name, 0) + 1
        if name not in PRIORITY_MAP:
            raise SourceValidationError(f"unknown referenced priority name: {name}")
    if any(count != 1 for count in names.values()):
        raise SourceValidationError("duplicate referenced source priority name")
    for event in rows.get("calendar_events", []):
        if event.get("display_name") != "v1_sqlite_schedule":
            raise SourceValidationError("calendar event has unknown source taxonomy")
        uid = event.get("external_uid")
        if uid is None or not (
            str(uid).startswith("manual_") or str(uid).startswith("v1-schedule-")
        ):
            raise SourceValidationError("calendar event has unclassified external_uid")
        if event.get("ends_at") <= event.get("starts_at"):
            raise SourceValidationError("calendar event has invalid duration")


def transform_source(
    snapshot: SourceSnapshot, *, manual_source_id: UUID | None = None
) -> dict[str, list[dict[str, Any]]]:
    rows = snapshot.rows
    priorities = {row["id"]: row["name"] for row in rows["priorities"]}
    task_rows = []
    for row in rows["tasks"]:
        priority = (
            None if row["priority_id"] is None else PRIORITY_MAP[priorities[row["priority_id"]]]
        )
        task_rows.append(
            {
                "id": row["id"],
                "title": row["title"],
                "body_md": row["note"],
                "status": row["status"],
                "priority": priority,
                "due_at": row["due_at"],
                "completed_at": row["completed_at"],
                "is_private": False,
                "pinned": False,
                "deleted_at": None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    task_ids = {row["id"] for row in task_rows}
    result = {
        "task": task_rows,
        "task_item": [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "content": row["content"],
                "is_completed": bool(row["is_completed"]),
                "position": row["position"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows["task_items"]
            if row["task_id"] in task_ids
        ],
        "note": [],
        "note_item": [],
        "calendar_source": [],
        "calendar_event": [],
    }
    for row in rows["notes"]:
        result["note"].append(
            {
                "id": row["id"],
                "title": row["title"],
                "body_md": row["body"],
                "embedding": None,
                "pinned": bool(row["pinned"]),
                "priority": None
                if row["priority_id"] is None
                else PRIORITY_MAP[priorities[row["priority_id"]]],
                "is_private": False,
                "deleted_at": None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    note_ids = {row["id"] for row in result["note"]}
    result["note_item"] = [
        {
            "id": row["id"],
            "note_id": row["note_id"],
            "content": row["content"],
            "is_completed": bool(row["is_done"]),
            "position": row["position"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows["note_items"]
        if row["note_id"] in note_ids
    ]
    manual = [
        row for row in rows["calendar_events"] if str(row["external_uid"]).startswith("manual_")
    ]
    if manual:
        source_id = manual_source_id or new_uuid7()
        if source_id.version != 7:
            raise SourceValidationError("manual calendar source ID is not UUIDv7")
        result["calendar_source"] = [
            {
                "id": source_id,
                "name": "Buổi thủ công (app cũ)",
                "kind": "manual",
                "color": None,
                "is_visible": True,
                "created_at": snapshot.cutoff_at,
                "updated_at": snapshot.cutoff_at,
            }
        ]
        result["calendar_event"] = [
            {
                "id": row["id"],
                "source_id": source_id,
                "title": row["title"],
                "location": row["location"],
                "starts_at": row["starts_at"],
                "ends_at": row["ends_at"],
                "description_md": row["description"],
                "all_day": False,
                "is_hidden": bool(row["user_cancelled"]) or row["status"] == "cancelled",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in manual
        ]
    return result


def build_manifest(
    *,
    snapshot: SourceSnapshot,
    transformed: Mapping[str, Sequence[Mapping[str, Any]]],
    target_snapshot: Mapping[str, Mapping[str, Any]],
    source_identity: Mapping[str, Any],
    schema_attestation: Mapping[str, Any],
    target_host_name: str,
    script_sha: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    source_expected = {name: inventory(name, values) for name, values in transformed.items()}
    expected_ids = {
        name: [str(row["id"]) for row in values] for name, values in transformed.items()
    }
    empty = {name: empty_inventory(name) for name in PURGE_ONLY_COMPONENTS}
    return {
        "manifest_version": 1,
        "transform_version": TRANSFORM_VERSION,
        "run_id": run_id or str(uuid4()),
        "script_sha": script_sha,
        "target_host": target_host_name,
        "source_cutoff_at": snapshot.cutoff_at.astimezone(UTC).isoformat(),
        "source_identity": dict(source_identity),
        "source_expected": source_expected,
        "source_inventory": snapshot.source_inventory,
        "expected_ids": expected_ids,
        "phase_b_target_snapshot": dict(target_snapshot),
        "phase_b_target_snapshot_digest": manifest_digest({"snapshot": target_snapshot}),
        "schema_attestation": dict(schema_attestation),
        "purge_only_empty": empty,
    }


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    digest = manifest_digest(payload)
    payload["manifest_digest"] = digest
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return digest


def read_final_manifest(
    path: Path, *, expected_script_sha: str, expected_host: str
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        raise ManifestError("cannot read manifest") from None
    if payload.get("manifest_digest") != manifest_digest(payload):
        raise ManifestError("manifest digest mismatch")
    if payload.get("script_sha") != expected_script_sha:
        raise ManifestError("manifest script SHA mismatch")
    if payload.get("target_host") != expected_host:
        raise ManifestError("manifest target host mismatch")
    approval = payload.get("owner_approval")
    if not isinstance(approval, dict):
        raise ManifestError("manifest has no owner approval")
    required = {
        "manifest_digest": payload["manifest_digest"],
        "run_id": payload.get("run_id"),
        "script_sha": expected_script_sha,
        "target_host": expected_host,
        "phase_b_target_snapshot_digest": payload.get("phase_b_target_snapshot_digest"),
    }
    if any(approval.get(key) != value for key, value in required.items()):
        raise ManifestError("owner approval is not bound to this exact manifest")
    if not approval.get("signature"):
        raise ManifestError("owner approval signature is missing")
    return payload


def verify_source_dump(dump_path: Path, expected_sha256: str | None = None) -> str:
    """Verify only a supplied encrypted/full dump; never opens a live source."""
    if not dump_path.is_file() or dump_path.stat().st_size == 0:
        raise CutoverError("source dump is missing or empty")
    digest = hashlib.sha256(dump_path.read_bytes()).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise CutoverError("source dump SHA-256 mismatch")
    return digest


def read_failure_receipt(
    path: Path,
    *,
    manifest: Mapping[str, Any],
    expected_script_sha: str,
    expected_host: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate the narrow, expiring authorization required by ``--recover``."""
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        raise ManifestError("cannot read failure receipt") from None
    required = {
        "run_id": manifest.get("run_id"),
        "manifest_digest": manifest.get("manifest_digest"),
        "script_sha": expected_script_sha,
        "target_host": expected_host,
        "fly_never_restarted": True,
    }
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ManifestError("failure receipt is not bound to this run")
    if receipt.get("failed_command") not in {"commit", "verify"}:
        raise ManifestError("failure receipt has an invalid failed command")
    if not receipt.get("failure_stage") or not receipt.get("signature"):
        raise ManifestError("failure receipt is unsigned or missing failure stage")
    inventory_map = receipt.get("failed_run_domain_inventory")
    if set(inventory_map or {}) != set(DOMAIN_COMPONENTS):
        raise ManifestError("failure receipt does not contain the complete domain inventory")
    try:
        expiry = datetime.fromisoformat(receipt.get("expires_at"))
    except TypeError, ValueError:
        raise ManifestError("failure receipt expiry is invalid") from None
    if expiry.tzinfo is None or expiry <= (now or datetime.now(UTC)):
        raise ManifestError("failure receipt has expired")
    return receipt


async def collect_target_inventory(
    session: AsyncSession, components: Sequence[str] = DOMAIN_COMPONENTS + APP_READABLE_PRESERVE
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for component in components:
        table = MODEL_TABLES.get(component)
        if table is None:
            rows = (
                (
                    await session.execute(
                        text(
                            f"SELECT {', '.join(TARGET_FIELDS[component])} "
                            f'FROM microsched."{component}"'
                        )
                    )
                )
                .mappings()
                .all()
            )
        else:
            rows = (await session.execute(select(table))).mappings().all()
        row_dicts = [dict(row) for row in rows]
        if component == "note" and any(row.get("embedding") is not None for row in row_dicts):
            raise ManifestError("pre-existing note.embedding must be NULL")
        result[component] = inventory(component, row_dicts)
    return result


async def run_commit(
    manifest: Mapping[str, Any],
    engine: AsyncEngine,
    transformed: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await assert_app_role(session)
        async with session.begin():
            current = await collect_target_inventory(session)
            if current != manifest["phase_b_target_snapshot"]:
                raise ManifestError("target Phase-B snapshot drift before DELETE")
            for component in (
                "reminder_dispatch",
                "entry",
                "subscription",
                "tracker",
                "tracker_group",
                "calendar_event",
                "calendar_source",
                "task_item",
                "task",
                "note_item",
                "note",
                "day_annotation",
                "message",
                "audit_log",
            ):
                table_name = f'microsched."{component}"'
                await session.execute(text(f"DELETE FROM {table_name}"))
            for component in (
                "task",
                "task_item",
                "note",
                "note_item",
                "calendar_source",
                "calendar_event",
            ):
                for row in transformed.get(component, []):
                    await session.execute(insert(MODEL_TABLES[component]).values(**dict(row)))
            final = await collect_target_inventory(session)
            expected = dict(manifest["phase_b_target_snapshot"])
            for component in DOMAIN_COMPONENTS:
                if (
                    final[component] != inventory(component, transformed.get(component, []))
                    and component not in PURGE_ONLY_COMPONENTS
                ):
                    raise ManifestError(f"mapped component proof failed: {component}")
            for component in PURGE_ONLY_COMPONENTS:
                if final[component] != empty_inventory(component):
                    raise ManifestError(f"purge-only component is not empty: {component}")
            for component in APP_READABLE_PRESERVE:
                if final[component] != expected[component]:
                    raise ManifestError(f"preserve component changed: {component}")


async def run_verify(manifest: Mapping[str, Any], engine: AsyncEngine) -> dict[str, Any]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await assert_app_role(session)
        current = await collect_target_inventory(session)
    for component in PURGE_ONLY_COMPONENTS:
        if current[component] != empty_inventory(component):
            raise ManifestError(f"verify found residual purge-only row: {component}")
    for component in APP_READABLE_PRESERVE:
        if current[component] != manifest["phase_b_target_snapshot"][component]:
            raise ManifestError(f"verify found preserve drift: {component}")
    return current


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cutover_v2")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--commit", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--recover", action="store_true")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--write-manifest", type=Path)
    p.add_argument("--confirm-target-host")
    p.add_argument("--expected-script-sha", default=os.environ.get("CUTOVER_SCRIPT_SHA"))
    p.add_argument("--source-dump", type=Path)
    p.add_argument("--source-dump-sha256")
    p.add_argument("--failure-receipt", type=Path)
    return p


async def async_main(args: argparse.Namespace) -> int:
    mode = (
        "commit"
        if args.commit
        else "verify"
        if args.verify
        else "recover"
        if args.recover
        else "dry-run"
    )
    target = target_url()
    if mode != "dry-run":
        if not args.confirm_target_host or not args.expected_script_sha or not args.manifest:
            raise CutoverError(
                "non-dry mode requires manifest, expected script SHA and target host confirmation"
            )
        assert_confirmed_host(target, args.confirm_target_host)
        manifest = read_final_manifest(
            args.manifest,
            expected_script_sha=args.expected_script_sha,
            expected_host=args.confirm_target_host.lower(),
        )
        attestation_engine = migrator_engine()
        try:
            await attest_schema(
                attestation_engine,
                expected_digest=manifest["schema_attestation"]["catalog_digest"],
            )
        finally:
            await attestation_engine.dispose()
        if mode == "recover":
            if not args.failure_receipt:
                raise CutoverError("recover requires a separately signed failure receipt")
            read_failure_receipt(
                args.failure_receipt,
                manifest=manifest,
                expected_script_sha=args.expected_script_sha,
                expected_host=args.confirm_target_host.lower(),
            )
            if not args.source_dump:
                raise CutoverError("recover requires a fresh encrypted source restore")
            verify_source_dump(args.source_dump, args.source_dump_sha256)
            raise CutoverError(
                "recovery authorization passed; restore the encrypted dump into the named "
                "throwaway source and provide its verified snapshot before recovery DML"
            )
    if mode == "verify":
        tgt = target_engine()
        try:
            await run_verify(manifest, tgt)
        finally:
            await tgt.dispose()
        attestation_engine = migrator_engine()
        try:
            await attest_schema(
                attestation_engine,
                expected_digest=manifest["schema_attestation"]["catalog_digest"],
            )
        finally:
            await attestation_engine.dispose()
        print("verify=ok")
        return 0
    if args.source_dump:
        digest = verify_source_dump(args.source_dump, args.source_dump_sha256)
        print(f"source_dump sha256={digest}")
    src = source_engine()
    try:
        await assert_source_identity(src)
        await assert_source_read_only(src)
        snapshot = await load_source_snapshot(src)
        if mode != "dry-run" and snapshot.source_inventory != manifest.get("source_inventory"):
            raise ManifestError("source inventory drift after freeze")
        manual_source_id = None
        if mode != "dry-run" and manifest.get("expected_ids", {}).get("calendar_source"):
            manual_source_id = UUID(manifest["expected_ids"]["calendar_source"][0])
        transformed = transform_source(snapshot, manual_source_id=manual_source_id)
        if mode == "dry-run":
            print(f"SOURCE {SOURCE_DB_NAME} @ local (read-only)")
            print(f"TARGET {target_host(target)}")
            for component in transformed:
                full_digest = digest_rows(
                    component, transformed[component], TARGET_FIELDS[component]
                )
                print(
                    f"{component} count={len(transformed[component])} "
                    f"id_digest={digest_ids(component, transformed[component])} "
                    f"full_digest={full_digest}"
                )
            if args.write_manifest:
                target_engine_obj = target_engine()
                try:
                    async with target_engine_obj.connect() as conn:
                        await assert_app_role(conn)
                        maker = async_sessionmaker(target_engine_obj, expire_on_commit=False)
                        async with maker() as db:
                            target_snapshot = await collect_target_inventory(db)
                    attestation_engine = migrator_engine()
                    try:
                        attestation = await attest_schema(attestation_engine)
                    finally:
                        await attestation_engine.dispose()
                    manifest = build_manifest(
                        snapshot=snapshot,
                        transformed=transformed,
                        target_snapshot=target_snapshot,
                        source_identity={"database": SOURCE_DB_NAME, "host": "local"},
                        schema_attestation=attestation,
                        target_host_name=target_host(target),
                        script_sha=args.expected_script_sha or "UNPINNED",
                    )
                    digest = write_manifest(args.write_manifest, manifest)
                    print(f"draft_manifest digest={digest} path={args.write_manifest}")
                finally:
                    await target_engine_obj.dispose()
            return 0
    finally:
        await src.dispose()
    tgt = target_engine()
    try:
        if mode == "commit":
            await run_commit(manifest, tgt, transformed)
        elif mode == "verify":
            await run_verify(manifest, tgt)
    finally:
        await tgt.dispose()
    if mode in {"commit", "verify"}:
        attestation_engine = migrator_engine()
        try:
            await attest_schema(
                attestation_engine,
                expected_digest=manifest["schema_attestation"]["catalog_digest"],
            )
        finally:
            await attestation_engine.dispose()
    print(f"{mode}=ok")
    return 0


def main() -> int:
    args = parser().parse_args()
    try:
        return asyncio.run(async_main(args))
    except CutoverError as exc:
        print(f"cutover_v2 aborted: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # never leak a row repr/traceback to a public log
        print(f"cutover_v2 aborted: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
