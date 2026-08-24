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
import base64
import hashlib
import inspect
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    UniqueConstraint,
    insert,
    text,
)
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel, select

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
# 026A is an expand migration: the cutover attestation must reject a target
# that has not yet received its compatible temporal triad and legacy writer
# triggers, even though source data is still legacy due_at-only.
EXPECTED_ALEMBIC_REVISION = "0010"
SOURCE_DB_NAME = "microschedule_v2"
SOURCE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", "db"})
TARGET_APP_ROLE = "microsched_app"
TARGET_MIGRATOR_ROLES = frozenset({"microsched_migrator", "neondb_owner"})
PINNED_SCHEMA_ROLES = frozenset(
    {"postgres", "microsched_migrator", "neondb_owner", TARGET_APP_ROLE}
)
OWNER_PUBLIC_KEY_ENV = "CUTOVER_OWNER_PUBLIC_KEY"
ARTIFACT_KEY_ENV = "CUTOVER_ARTIFACT_KEY"
RECOVERY_SOURCE_URL_ENV = "CUTOVER_RECOVERY_SOURCE_URL"
RESTORED_SOURCE_URL_ENV = "CUTOVER_RESTORED_SOURCE_URL"
FLY_STATE_COMMAND_ENV = "CUTOVER_FLY_STATE_COMMAND"
FLY_APP_ENV = "CUTOVER_FLY_APP"
AGE_IDENTITY_FILE_ENV = "CUTOVER_AGE_IDENTITY_FILE"
ARTIFACT_MAGIC = b"microsched-cutover-v1\0"
AGE_HEADER = b"age-encryption.org/v1\n"

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
        "due_precision",
        "due_on",
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


def deterministic_uuid7(seed: str, cutoff_at: datetime) -> UUID:
    """Stable UUIDv7-shaped ID for the one generated manual calendar source."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    milliseconds = int(cutoff_at.timestamp() * 1000) & ((1 << 48) - 1)
    random_a = int.from_bytes(digest[:2], "big") & 0x0FFF
    random_b = int.from_bytes(digest[2:10], "big") & ((1 << 62) - 1)
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


def expected_final_inventory(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {component: manifest["source_expected"][component] for component in MAPPED_COMPONENTS}
    result.update({component: empty_inventory(component) for component in PURGE_ONLY_COMPONENTS})
    result.update(
        {
            component: manifest["phase_b_target_snapshot"][component]
            for component in APP_READABLE_PRESERVE
        }
    )
    return result


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


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _key_from_env() -> bytes:
    raw = os.environ.get(ARTIFACT_KEY_ENV)
    if not raw:
        raise CutoverError(f"{ARTIFACT_KEY_ENV} is required for encrypted artifacts")
    try:
        value = base64.b64decode(raw, validate=True)
    except ValueError, base64.binascii.Error:
        try:
            value = bytes.fromhex(raw)
        except ValueError:
            raise CutoverError(f"{ARTIFACT_KEY_ENV} must be base64 or hex") from None
    if len(value) != 32:
        raise CutoverError(f"{ARTIFACT_KEY_ENV} must decode to 32 bytes")
    return value


def _public_key_from_env() -> Ed25519PublicKey:
    raw = os.environ.get(OWNER_PUBLIC_KEY_ENV)
    if not raw:
        raise CutoverError(f"{OWNER_PUBLIC_KEY_ENV} is required for signature verification")
    try:
        key_bytes = base64.b64decode(raw, validate=True)
    except ValueError, base64.binascii.Error:
        try:
            key_bytes = bytes.fromhex(raw)
        except ValueError:
            raise CutoverError(f"{OWNER_PUBLIC_KEY_ENV} must be base64 or hex") from None
    if len(key_bytes) != 32:
        raise CutoverError(f"{OWNER_PUBLIC_KEY_ENV} must decode to 32 bytes")
    try:
        return Ed25519PublicKey.from_public_bytes(key_bytes)
    except ValueError:
        raise CutoverError(f"{OWNER_PUBLIC_KEY_ENV} is not an Ed25519 public key") from None


def encrypt_artifact(payload: Mapping[str, Any]) -> bytes:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key_from_env()).encrypt(nonce, canonical_json(payload), ARTIFACT_MAGIC)
    return ARTIFACT_MAGIC + base64.b64encode(nonce + ciphertext)


def decrypt_artifact(path: Path) -> dict[str, Any]:
    try:
        blob = path.read_bytes()
        if not blob.startswith(ARTIFACT_MAGIC):
            raise ManifestError("artifact is not encrypted")
        raw = base64.b64decode(blob[len(ARTIFACT_MAGIC) :], validate=True)
        plaintext = AESGCM(_key_from_env()).decrypt(raw[:12], raw[12:], ARTIFACT_MAGIC)
        payload = json.loads(plaintext.decode("utf-8"))
    except Exception:
        raise ManifestError("cannot decrypt artifact") from None
    if not isinstance(payload, dict):
        raise ManifestError("encrypted artifact is not an object")
    return payload


def approval_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manifest_digest": manifest.get("manifest_digest"),
        "run_id": manifest.get("run_id"),
        "script_sha": manifest.get("script_sha"),
        "script_file_sha256": manifest.get("script_file_sha256"),
        "target_host": manifest.get("target_host"),
        "target_identity": manifest.get("target_identity"),
        "source_cutoff_at": manifest.get("source_cutoff_at"),
        "approval_expires_at": manifest.get("approval_expires_at"),
        "source_expected": manifest.get("source_expected"),
        "phase_b_target_snapshot_digest": manifest.get("phase_b_target_snapshot_digest"),
    }


def verify_signature(signature: Any, payload: Mapping[str, Any]) -> None:
    if not isinstance(signature, str):
        raise ManifestError("signature must be base64 text")
    try:
        value = base64.b64decode(signature, validate=True)
    except ValueError, base64.binascii.Error:
        raise ManifestError("signature is not valid base64") from None
    try:
        _public_key_from_env().verify(value, canonical_json(payload))
    except Exception:
        raise ManifestError("cryptographic signature verification failed") from None


def actual_code_identity() -> dict[str, str]:
    path = Path(__file__).resolve()
    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=path.parents[2], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except OSError, subprocess.CalledProcessError:
        raise CutoverError("cannot resolve immutable git SHA for cutover script") from None
    if len(git_sha) != 40 or any(char not in "0123456789abcdef" for char in git_sha.lower()):
        raise CutoverError("git SHA for cutover script is invalid")
    return {"git_sha": git_sha, "file_sha256": file_sha256}


def failure_receipt_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "signature"}


def build_source_url() -> str:
    expected_database = os.environ.get("CUTOVER_SOURCE_DATABASE", SOURCE_DB_NAME)
    value = os.environ.get("CUTOVER_SOURCE_URL")
    if value:
        url = make_url(value)
        if (url.host or "").lower() not in SOURCE_HOSTS or url.database != expected_database:
            raise CutoverError("CUTOVER_SOURCE_URL must target the approved local source database")
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
        database=expected_database,
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


def restored_source_engine(value: str) -> AsyncEngine:
    """Open a dump restore with the same server-side read-only guard as source."""
    return create_async_engine(
        async_postgres_url(value),
        pool_pre_ping=True,
        connect_args={"server_settings": {"default_transaction_read_only": "on"}},
    )


def fly_state_verifier_from_env() -> Callable[[], Awaitable[Mapping[str, Any]]]:
    """Build the read-only native ``fly status --json`` probe.

    The native Apps v2 response is an object containing ``Machines``.  The
    machine event stream is part of the Machines API response.  The parser
    scopes start/restart evidence to the signed failure cutoff and machine ID;
    older history is allowed while post-failure changes are rejected.  A wrapper may still
    be selected explicitly for a workstation, but the default is the official
    ``fly`` executable and its native JSON shape is never replaced by a pair of
    operator-supplied booleans.
    """
    command = os.environ.get(FLY_STATE_COMMAND_ENV, "fly")
    app = os.environ.get(FLY_APP_ENV)
    if not app:
        raise CutoverError(f"{FLY_APP_ENV} is required for recovery")
    try:
        command_parts = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        raise CutoverError(f"{FLY_STATE_COMMAND_ENV} is invalid") from None
    if not command_parts:
        raise CutoverError(f"{FLY_STATE_COMMAND_ENV} is empty")

    async def verify() -> Mapping[str, Any]:
        try:
            output = await asyncio.to_thread(
                subprocess.check_output,
                [*command_parts, "status", "--app", app, "--json"],
                stderr=subprocess.DEVNULL,
                timeout=10,
                text=True,
            )
            value = json.loads(output)
        except OSError, subprocess.SubprocessError, json.JSONDecodeError:
            raise CutoverError("current Fly stopped-state query failed") from None
        return value

    return verify


def parse_fly_status(
    payload: Mapping[str, Any],
    *,
    failure_time: datetime | None = None,
    expected_machine_id: str | None = None,
) -> dict[str, Any]:
    """Normalize and fail closed on the native Apps v2 ``fly status --json``.

    Fly's documented status response uses a top-level ``Machines`` array and
    lower-case machine fields.  ``Events`` is retained in the response by the
    Machines API and carries ``type`` plus an optional ``request`` with
    ``restart_count``.  We do not infer continuity from a static ``stopped``
    string: exactly one machine, creation/start history, and explicit absence
    of restart evidence after the signed failure cutoff are required.
    """
    if not isinstance(payload, Mapping):
        raise CutoverError("current Fly stopped-state query returned invalid JSON")
    machines = payload.get("Machines")
    if not isinstance(machines, list) or len(machines) != 1:
        raise CutoverError("current Fly state does not contain exactly one machine")
    machine = machines[0]
    if not isinstance(machine, Mapping):
        raise CutoverError("current Fly machine record is invalid")
    machine_id = machine.get("id")
    state = machine.get("state")
    if not isinstance(machine_id, str) or not machine_id.strip():
        raise CutoverError("current Fly machine ID is missing")
    if expected_machine_id is not None and machine_id != expected_machine_id:
        raise CutoverError("current Fly machine identity changed after failure")
    if state != "stopped":
        raise CutoverError("current Fly machine is not stopped")
    events = machine.get("events")
    if not isinstance(events, list) or not events:
        raise CutoverError("current Fly machine restart evidence is missing")
    event_types: list[str] = []
    restart_counts: list[int] = []
    known_event_types = {
        "create",
        "created",
        "destroy",
        "exit",
        "launch",
        "restart",
        "start",
        "stop",
        "suspend",
    }
    for event in events:
        if not isinstance(event, Mapping) or not isinstance(event.get("type"), str):
            raise CutoverError("current Fly machine event evidence is invalid")
        event_type = event["type"].lower()
        if event_type not in known_event_types:
            raise CutoverError("current Fly machine event type is unknown")
        event_types.append(event_type)
        event_timestamp = event.get("timestamp")
        event_time = None
        if event_timestamp is not None:
            if isinstance(event_timestamp, bool) or not isinstance(event_timestamp, (int, float)):
                raise CutoverError("current Fly machine event timestamp is invalid")
            try:
                event_time = datetime.fromtimestamp(float(event_timestamp) / 1000, tz=UTC)
            except OverflowError, OSError, ValueError:
                raise CutoverError("current Fly machine event timestamp is invalid") from None
        if failure_time is not None and event_time is None:
            raise CutoverError("current Fly machine event timestamp is missing")
        if (
            failure_time is not None
            and event_time is not None
            and event_time > failure_time
            and event_type in {"restart", "start"}
        ):
            raise CutoverError("current Fly machine restarted after the signed failure cutoff")
        request = event.get("request")
        if request is not None:
            if not isinstance(request, Mapping):
                raise CutoverError("current Fly machine restart evidence is invalid")
            restart_count = request.get("restart_count")
            if restart_count is not None:
                if isinstance(restart_count, bool) or not isinstance(restart_count, int):
                    raise CutoverError("current Fly machine restart count is invalid")
                restart_counts.append(restart_count)
                if restart_count != 0 and (
                    failure_time is None or event_time is None or event_time > failure_time
                ):
                    raise CutoverError("current Fly machine has restart evidence")
            for exit_key in ("exit_event", "MonitorEvent"):
                exit_event = request.get(exit_key)
                if (
                    isinstance(exit_event, Mapping)
                    and exit_event.get("restarting") is True
                    and (failure_time is None or event_time is None or event_time > failure_time)
                ):
                    raise CutoverError("current Fly machine has restart evidence")
        if event.get("status") == "restarted" and (
            failure_time is None or event_time is None or event_time > failure_time
        ):
            raise CutoverError("current Fly machine has restart evidence")
    if not any(event_type in {"launch", "created", "create"} for event_type in event_types):
        raise CutoverError("current Fly machine lacks creation history")
    if not any(event_type == "start" for event_type in event_types):
        raise CutoverError("current Fly machine lacks start history")
    return {
        "fly_state": "stopped",
        "machine_id": machine_id,
        "machine_state": state,
        "sole_machine_stopped": True,
        "never_restarted": True,
        "restart_evidence": {
            "event_count": len(events),
            "launch_count": sum(
                event_type in {"launch", "created", "create"} for event_type in event_types
            ),
            "start_count": event_types.count("start"),
            "restart_counts": restart_counts,
        },
    }


async def assert_current_fly_stopped(
    verifier: Callable[[], Awaitable[Mapping[str, Any]]] | Callable[[], Mapping[str, Any]],
    *,
    failure_time: datetime | None = None,
    expected_machine_id: str | None = None,
) -> Mapping[str, Any]:
    try:
        result = verifier()
        state = await result if inspect.isawaitable(result) else result
    except CutoverError:
        raise
    except Exception:
        raise CutoverError("current Fly stopped-state query failed") from None
    return parse_fly_status(
        state,
        failure_time=failure_time,
        expected_machine_id=expected_machine_id,
    )


def assert_target_coordinates() -> None:
    target = make_url(os.environ["CUTOVER_TARGET_URL"])
    migrator = make_url(os.environ["CUTOVER_MIGRATOR_URL"])
    if (target.host or "").lower() != (
        migrator.host or ""
    ).lower() or target.database != migrator.database:
        raise CutoverError("target and migrator URLs do not address the same host/database")


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
        identity = await read_connection_identity(connection, "public")
    expected_database = os.environ.get("CUTOVER_SOURCE_DATABASE", SOURCE_DB_NAME)
    if identity["database"] != expected_database:
        raise CutoverError("source database identity is not the approved local database")


async def read_connection_identity(connection: Any, schema: str) -> dict[str, Any]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT current_database() AS database, current_user AS current_user, "
                    "inet_server_addr()::text AS server_addr, inet_server_port() AS server_port, "
                    "current_setting('cluster_name', true) AS cluster_name"
                )
            )
        )
        .mappings()
        .one()
    )
    columns = (
        (
            await connection.execute(
                text(
                    "SELECT table_name,column_name,data_type,is_nullable,ordinal_position,"
                    "column_default,udt_name,numeric_precision,numeric_scale,"
                    "datetime_precision "
                    "FROM information_schema.columns WHERE table_schema=:schema "
                    "ORDER BY table_name,ordinal_position"
                ),
                {"schema": schema},
            )
        )
        .mappings()
        .all()
    )
    constraints = (
        (
            await connection.execute(
                text(
                    "SELECT n.nspname AS table_schema, c.relname AS table_name, "
                    "con.conname AS constraint_name, con.contype AS constraint_type, "
                    "pg_get_constraintdef(con.oid, true) AS definition "
                    "FROM pg_catalog.pg_constraint con "
                    "JOIN pg_catalog.pg_class c ON c.oid=con.conrelid "
                    "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema ORDER BY c.relname,con.conname"
                ),
                {"schema": schema},
            )
        )
        .mappings()
        .all()
    )
    triggers = (
        (
            await connection.execute(
                text(
                    "SELECT n.nspname AS table_schema, c.relname AS table_name, "
                    "t.tgname AS trigger_name, t.tgenabled, pg_get_triggerdef(t.oid, true) "
                    "AS definition FROM pg_catalog.pg_trigger t "
                    "JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema AND NOT t.tgisinternal "
                    "ORDER BY c.relname,t.tgname"
                ),
                {"schema": schema},
            )
        )
        .mappings()
        .all()
    )
    routines = (
        (
            await connection.execute(
                text(
                    "SELECT n.nspname AS routine_schema, p.proname AS routine_name, "
                    "pg_get_functiondef(p.oid) AS definition FROM pg_catalog.pg_proc p "
                    "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname=:schema AND p.prokind = 'f' ORDER BY p.proname"
                ),
                {"schema": schema},
            )
        )
        .mappings()
        .all()
    )
    ddl = {
        "columns": [_catalog_row(item) for item in columns],
        "constraints": [_catalog_row(item) for item in constraints],
        "triggers": [_catalog_row(item) for item in triggers],
        "routines": [_catalog_row(item) for item in routines],
    }
    return {
        "database": row["database"],
        "current_user": row["current_user"],
        "server_addr": row["server_addr"],
        "server_port": row["server_port"],
        "cluster_name": row["cluster_name"],
        "ddl": ddl,
        "ddl_sha256": hashlib.sha256(canonical_json(ddl)).hexdigest(),
    }


def _catalog_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.decode("utf-8") if isinstance(value, bytes) else value
        for key, value in row.items()
    }


def _normalize_catalog_sql(value: Any) -> str:
    """Normalize PostgreSQL's harmless display differences, not semantics."""
    result = " ".join(str(value or "").lower().split())
    # pg_get_constraintdef prefixes catalog definitions with their object
    # kind (for example ``PRIMARY KEY (id)`` or ``CHECK ((...))``).  Remove
    # that display-only prefix before peeling redundant outer parentheses;
    # doing it in the opposite order leaves every catalog PK/UNIQUE wrapped
    # and leaves CHECK expressions with one extra pair.
    for prefix in ("check ", "primary key ", "unique ", "foreign key "):
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    while result.startswith("(") and result.endswith(")"):
        depth = 0
        balanced = True
        for index, char in enumerate(result):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(result) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        result = result[1:-1].strip()
    # PostgreSQL's deparser uses equivalent operator/type spellings for
    # migrated CHECK expressions.  These replacements are display-only: the
    # exact constraint name/type and the column nullability contract remain
    # separately pinned below.
    result = re.sub(r'"([a-z_][a-z0-9_]*)"', r"\1", result)
    result = re.sub(r"\s*~~\s*", " like ", result)
    result = re.sub(r"\s*::(?:text|boolean|jsonb|numeric)\b", "", result)
    result = re.sub(r"=\s*any\s*\(\s*array\[(.*?)\]\s*\)", r"in(\1)", result)
    # The deparser drops redundant grouping around a conjunction under OR.
    # Keep grouping when the first term itself contains OR, where it changes
    # precedence; only canonicalize the unambiguous display variant.
    result = re.sub(
        r"\bor\s*\(\(([^()]*)\)\s+and\s*\(([^()]*)\)\)",
        r"or(\1) and(\2)",
        result,
    )
    result = re.sub(
        r"\bor\s*\((?![^()]*\bor\b)([^()]+?)\s+and\s*\(([^()]*)\)\)",
        r"or \1 and(\2)",
        result,
    )
    # PostgreSQL also removes grouping around a single IN term after OR and
    # around the two AND terms in this exact unit-match CHECK.  Both sides
    # contain no OR, so AND precedence makes these removals AST-equivalent.
    result = re.sub(
        r"\bor\s*\(([^()]*\bin\s*\([^()]*\))\)",
        r"or \1",
        result,
    )
    result = re.sub(
        r"^\(([^()]*)\)\s+or\s*\(([^()]*)\)$",
        r"\1 or \2",
        result,
    )
    result = re.sub(r"\$\$", "$function$", result)
    result = re.sub(r"\s*\(\s*", "(", result)
    result = re.sub(r"\s*\)", ")", result)
    return re.sub(r"\s*,\s*", ",", result)


def _expected_column_contract() -> dict[tuple[str, str], dict[str, Any]]:
    """Build the pinned head column contract from the checked-in SQLModel metadata."""
    dialect = postgresql_dialect()
    result: dict[tuple[str, str], dict[str, Any]] = {}
    type_map = {
        "UUID": ("uuid", "uuid"),
        "TEXT": ("text", "text"),
        "BOOLEAN": ("boolean", "bool"),
        "INTEGER": ("integer", "int4"),
        "DATE": ("date", "date"),
        "TIME WITHOUT TIME ZONE": ("time without time zone", "time"),
        "TIMESTAMP WITH TIME ZONE": ("timestamp with time zone", "timestamptz"),
        "JSONB": ("jsonb", "jsonb"),
        "VECTOR": ("USER-DEFINED", "vector"),
        "NUMERIC": ("numeric", "numeric"),
    }
    for table in SQLModel.metadata.tables.values():
        if table.schema != "microsched":
            continue
        for column in table.columns:
            compiled_type = str(column.type.compile(dialect=dialect)).upper()
            if compiled_type.startswith("NUMERIC"):
                compiled_type = "NUMERIC"
            data_type, udt_name = type_map.get(
                compiled_type,
                (compiled_type.lower(), compiled_type.lower()),
            )
            default = None
            if column.server_default is not None:
                default = str(column.server_default.arg)
            numeric_precision = getattr(column.type, "precision", None)
            numeric_scale = getattr(column.type, "scale", None)
            if compiled_type == "INTEGER":
                numeric_precision, numeric_scale = 32, 0
            result[(table.name, column.name)] = {
                "data_type": data_type,
                "udt_name": udt_name,
                "is_nullable": "YES" if column.nullable else "NO",
                "column_default": default,
                "numeric_precision": numeric_precision,
                "numeric_scale": numeric_scale,
                "datetime_precision": 6
                if compiled_type in {"TIMESTAMP WITH TIME ZONE", "TIME WITHOUT TIME ZONE"}
                else 0
                if compiled_type == "DATE"
                else None,
            }
    result[("alembic_version", "version_num")] = {
        "data_type": "character varying",
        "udt_name": "varchar",
        "is_nullable": "NO",
        "column_default": None,
        "numeric_precision": None,
        "numeric_scale": None,
        "datetime_precision": None,
    }
    return result


def _expected_constraint_contract() -> set[tuple[str, str, str, str]]:
    """Return exact head constraint names/types/definitions, including Alembic PK."""
    result: set[tuple[str, str, str, str]] = {
        (
            "alembic_version",
            "alembic_version_pkc",
            "p",
            _normalize_catalog_sql("(version_num)"),
        ),
    }
    for table in SQLModel.metadata.tables.values():
        if table.schema != "microsched":
            continue
        for constraint in table.constraints:
            name = constraint.name
            if not name:
                raise CutoverError(f"expected schema constraint has no name: {table.name}")
            if isinstance(constraint, PrimaryKeyConstraint):
                kind = "p"
                definition = "(" + ", ".join(column.name for column in constraint.columns) + ")"
            elif isinstance(constraint, UniqueConstraint):
                kind = "u"
                definition = "(" + ", ".join(column.name for column in constraint.columns) + ")"
            elif isinstance(constraint, ForeignKeyConstraint):
                kind = "f"
                columns = ", ".join(element.parent.name for element in constraint.elements)
                target = constraint.elements[0].target_fullname.rsplit(".", 1)[0]
                targets = ", ".join(
                    element.target_fullname.rsplit(".", 1)[-1] for element in constraint.elements
                )
                definition = f"({columns}) references {target} ({targets})"
                ondelete = constraint.elements[0].ondelete
                if ondelete:
                    definition += f" on delete {ondelete}"
            elif isinstance(constraint, CheckConstraint):
                kind = "c"
                definition = str(constraint.sqltext)
            else:
                raise CutoverError(f"unsupported expected schema constraint: {table.name}")
            result.add((table.name, str(name), kind, _normalize_catalog_sql(definition)))
    return result


def _expected_trigger_contract() -> set[tuple[str, str, str, str]]:
    result = {
        (
            table,
            "set_updated_at",
            "O",
            _normalize_catalog_sql(
                f"CREATE TRIGGER set_updated_at BEFORE UPDATE ON microsched.{table} "
                "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
            ),
        )
        for table in ALL_EXPECTED_TARGET_TABLES
    }
    result.update(
        {
            (
                "task_item",
                "trg_task_item_privacy",
                "O",
                _normalize_catalog_sql(
                    "CREATE TRIGGER trg_task_item_privacy BEFORE INSERT OR UPDATE "
                    "ON microsched.task_item FOR EACH ROW EXECUTE FUNCTION "
                    "microsched.enforce_task_item_privacy()"
                ),
            ),
            (
                "task",
                "trg_task_children_privacy",
                "O",
                _normalize_catalog_sql(
                    "CREATE TRIGGER trg_task_children_privacy BEFORE UPDATE OF is_private "
                    "ON microsched.task FOR EACH ROW EXECUTE FUNCTION "
                    "microsched.enforce_task_children_privacy()"
                ),
            ),
            (
                "task",
                "trg_task_due_legacy_insert_v1",
                "O",
                _normalize_catalog_sql(
                    "CREATE TRIGGER trg_task_due_legacy_insert_v1 BEFORE INSERT "
                    "ON microsched.task FOR EACH ROW EXECUTE FUNCTION "
                    "microsched.fn_task_due_legacy_insert_v1()"
                ),
            ),
            (
                "task",
                "trg_task_due_legacy_update_v1",
                "O",
                _normalize_catalog_sql(
                    "CREATE TRIGGER trg_task_due_legacy_update_v1 BEFORE UPDATE OF due_at "
                    "ON microsched.task FOR EACH ROW EXECUTE FUNCTION "
                    "microsched.fn_task_due_legacy_update_v1()"
                ),
            ),
        }
    )
    return result


def _expected_routine_contract() -> set[tuple[str, str]]:
    return {
        (
            "enforce_task_children_privacy",
            _normalize_catalog_sql(
                "CREATE OR REPLACE FUNCTION microsched.enforce_task_children_privacy() "
                "RETURNS trigger LANGUAGE plpgsql AS $function$ "
                "BEGIN "
                "IF NEW.is_private AND NOT OLD.is_private THEN "
                "IF EXISTS ( "
                "SELECT 1 FROM microsched.task_item "
                "WHERE task_id = NEW.id AND content NOT LIKE 'enc:v1:%' "
                ") THEN "
                "RAISE EXCEPTION "
                "'cannot make task private while it has plaintext task_item children'; "
                "END IF; "
                "END IF; "
                "RETURN NEW; "
                "END; $function$"
            ),
        ),
        (
            "enforce_task_item_privacy",
            _normalize_catalog_sql(
                "CREATE OR REPLACE FUNCTION microsched.enforce_task_item_privacy() "
                "RETURNS trigger LANGUAGE plpgsql AS $function$ "
                "BEGIN "
                "IF EXISTS ( "
                "SELECT 1 FROM microsched.task "
                "WHERE id = NEW.task_id AND is_private "
                ") THEN "
                "IF NEW.content NOT LIKE 'enc:v1:%' THEN "
                "RAISE EXCEPTION "
                "'task_item.content must be ciphertext when parent task is private'; "
                "END IF; "
                "END IF; "
                "RETURN NEW; "
                "END; $function$"
            ),
        ),
        (
            "fn_task_due_legacy_insert_v1",
            _normalize_catalog_sql(
                "CREATE OR REPLACE FUNCTION microsched.fn_task_due_legacy_insert_v1() "
                "RETURNS trigger LANGUAGE plpgsql AS $function$ "
                "BEGIN "
                "IF current_setting('microsched.task_due_writer', true) = 'v2' THEN "
                "RETURN NEW; "
                "END IF; "
                "IF NEW.due_at IS NULL THEN "
                "NEW.due_precision := 'none'; "
                "ELSE "
                "NEW.due_precision := 'datetime'; "
                "END IF; "
                "NEW.due_on := NULL; "
                "RETURN NEW; "
                "END; $function$"
            ),
        ),
        (
            "fn_task_due_legacy_update_v1",
            _normalize_catalog_sql(
                "CREATE OR REPLACE FUNCTION microsched.fn_task_due_legacy_update_v1() "
                "RETURNS trigger LANGUAGE plpgsql AS $function$ "
                "BEGIN "
                "IF current_setting('microsched.task_due_writer', true) = 'v2' THEN "
                "RETURN NEW; "
                "END IF; "
                "IF NEW.due_at IS NULL THEN "
                "NEW.due_precision := 'none'; "
                "ELSE "
                "NEW.due_precision := 'datetime'; "
                "END IF; "
                "NEW.due_on := NULL; "
                "RETURN NEW; "
                "END; $function$"
            ),
        ),
        (
            "set_updated_at",
            _normalize_catalog_sql(
                "CREATE OR REPLACE FUNCTION microsched.set_updated_at() "
                "RETURNS trigger LANGUAGE plpgsql AS $function$ "
                "BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $function$"
            ),
        ),
    }


def _expected_functional_unique_index_contract() -> set[tuple[str, str, str]]:
    return {
        (
            "calendar_source",
            "uq_calendar_source_name_lower",
            _normalize_catalog_sql(
                "CREATE UNIQUE INDEX uq_calendar_source_name_lower ON "
                "microsched.calendar_source USING btree (lower(name))"
            ),
        ),
        (
            "tracker_group",
            "uq_tracker_group_name_lower",
            _normalize_catalog_sql(
                "CREATE UNIQUE INDEX uq_tracker_group_name_lower ON "
                "microsched.tracker_group USING btree (lower(name))"
            ),
        ),
    }


async def read_runtime_coordinates(connection: Any) -> dict[str, Any]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT current_database() AS database, current_user AS current_user, "
                    "inet_server_addr()::text AS server_addr, inet_server_port() AS server_port, "
                    "current_setting('cluster_name', true) AS cluster_name"
                )
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


def assert_identity_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    # Server IPs are connection-pool/provider visibility details, not the
    # target's immutable host/branch identity.  Host is checked from the signed
    # manifest URL; database/port/cluster and DDL remain bounded attestation data.
    keys = ("database", "server_port", "cluster_name", "ddl_sha256")
    if any(actual.get(key) != expected.get(key) for key in keys):
        raise CutoverError("database identity or DDL fingerprint drift")


def assert_runtime_coordinates_match(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    keys = ("database", "server_port", "cluster_name")
    if any(actual.get(key) != expected.get(key) for key in keys):
        raise CutoverError("target runtime database coordinates drift")


def assert_manifest_target_host(manifest: Mapping[str, Any]) -> None:
    expected_host = str(manifest.get("target_host", "")).lower().rstrip(".")
    if not expected_host or target_host(target_url()) != expected_host:
        raise CutoverError("target runtime host/branch does not match the signed manifest")


def assert_restored_source_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if actual.get("ddl_sha256") != expected.get("ddl_sha256"):
        raise CutoverError("restored source DDL fingerprint drift")


def assert_restored_source_is_distinct(
    actual: Mapping[str, Any], live_source: Mapping[str, Any]
) -> None:
    keys = ("database", "server_addr", "server_port", "cluster_name")
    if all(actual.get(key) == live_source.get(key) for key in keys):
        raise CutoverError("restored source must be distinct from the live source")


async def assert_app_role(connection: Any) -> None:
    role = (await connection.execute(text("SELECT current_user"))).scalar_one()
    if role != TARGET_APP_ROLE:
        raise CutoverError("target DML connection is not microsched_app")


async def assert_app_cannot_read_alembic(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await assert_app_role(connection)
        try:
            await connection.execute(text("SELECT version_num FROM microsched.alembic_version"))
        except Exception:
            await connection.rollback()
            return
    raise CutoverError("microsched_app unexpectedly has alembic_version access")


async def attest_schema(
    engine: AsyncEngine, *, expected_digest: str | None = None
) -> dict[str, Any]:
    """Bounded, read-only schema attestation; never used for target DML."""
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            role = (await connection.execute(text("SELECT current_user"))).scalar_one()
            if role not in TARGET_MIGRATOR_ROLES:
                raise CutoverError(
                    "schema attestation requires microsched_migrator or neondb_owner"
                )
            revision = (
                (
                    await connection.execute(
                        text("SELECT version_num FROM microsched.alembic_version")
                    )
                )
                .scalars()
                .all()
            )
            if list(revision) != [EXPECTED_ALEMBIC_REVISION]:
                raise CutoverError("schema attestation is not at the pinned Alembic revision")
            identity = await read_connection_identity(connection, "microsched")
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
            grants = (
                (
                    await connection.execute(
                        text(
                            "SELECT c.relname AS table_name, r.rolname AS grantee, "
                            "CASE WHEN acl.grantee=0 THEN 'PUBLIC' ELSE r.rolname END AS grantee, "
                            "acl.privilege_type "
                            "FROM pg_catalog.pg_class c "
                            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                            "JOIN LATERAL aclexplode(COALESCE(c.relacl, "
                            "acldefault('r', c.relowner))) acl ON true "
                            "LEFT JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee "
                            "WHERE n.nspname='microsched' "
                            "ORDER BY c.relname,r.rolname,acl.privilege_type"
                        )
                    )
                )
                .mappings()
                .all()
            )
            schema_grants = (
                (
                    await connection.execute(
                        text(
                            "SELECT CASE WHEN acl.grantee=0 THEN 'PUBLIC' "
                            "ELSE r.rolname END AS grantee, acl.privilege_type "
                            "FROM pg_catalog.pg_namespace n "
                            "JOIN LATERAL aclexplode(COALESCE(n.nspacl, "
                            "acldefault('n', n.nspowner))) acl ON true "
                            "LEFT JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee "
                            "WHERE n.nspname='microsched' "
                            "ORDER BY grantee,acl.privilege_type"
                        )
                    )
                )
                .mappings()
                .all()
            )
            owners = (
                (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT pg_get_userbyid(c.relowner) AS role "
                            "FROM pg_catalog.pg_class c "
                            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE n.nspname='microsched'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            functional_unique_indexes = (
                (
                    await connection.execute(
                        text(
                            "SELECT tbl.relname AS table_name, idx.relname AS index_name, "
                            "ix.indisvalid, pg_get_indexdef(ix.indexrelid, 0, true) AS definition "
                            "FROM pg_catalog.pg_index ix "
                            "JOIN pg_catalog.pg_class idx ON idx.oid=ix.indexrelid "
                            "JOIN pg_catalog.pg_class tbl ON tbl.oid=ix.indrelid "
                            "JOIN pg_catalog.pg_namespace n ON n.oid=tbl.relnamespace "
                            "LEFT JOIN pg_catalog.pg_constraint con ON con.conindid=ix.indexrelid "
                            "WHERE n.nspname='microsched' AND ix.indisunique "
                            "AND con.oid IS NULL ORDER BY tbl.relname,idx.relname"
                        )
                    )
                )
                .mappings()
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
    actual_columns = {
        (row["table_name"], row["column_name"]): {
            key: row.get(key)
            for key in (
                "data_type",
                "udt_name",
                "is_nullable",
                "column_default",
                "numeric_precision",
                "numeric_scale",
                "datetime_precision",
            )
        }
        for row in identity["ddl"]["columns"]
    }
    expected_columns = _expected_column_contract()
    if set(actual_columns) != set(expected_columns):
        raise CutoverError("target catalog column set drift")
    for key, expected in expected_columns.items():
        actual = actual_columns[key]
        for field in ("data_type", "udt_name", "is_nullable"):
            if actual[field] != expected[field]:
                raise CutoverError(f"target catalog column {field} drift: {key[0]}.{key[1]}")
        if _normalize_catalog_sql(actual["column_default"]) != _normalize_catalog_sql(
            expected["column_default"]
        ):
            raise CutoverError(f"target catalog column default drift: {key[0]}.{key[1]}")
        for field in ("numeric_precision", "numeric_scale", "datetime_precision"):
            if actual[field] != expected[field]:
                raise CutoverError(f"target catalog column {field} drift: {key[0]}.{key[1]}")
    actual_constraints = {
        (
            row["table_name"],
            row["constraint_name"],
            row["constraint_type"],
            _normalize_catalog_sql(row["definition"]),
        )
        for row in identity["ddl"]["constraints"]
        # PostgreSQL 18 exposes NOT NULL as generated contype='n' entries.
        # Nullability is already pinned exactly in _expected_column_contract;
        # retaining these provider-generated names would make the contract
        # depend on a server-version display detail rather than schema DDL.
        if row["constraint_type"] != "n"
    }
    if actual_constraints != _expected_constraint_contract():
        expected_constraints = _expected_constraint_contract()
        missing_constraints = expected_constraints - actual_constraints
        extra_constraints = actual_constraints - expected_constraints
        raise CutoverError(
            "target catalog constraint contract drift: "
            f"missing={sorted(missing_constraints)!r} extra={sorted(extra_constraints)!r}"
        )
    actual_triggers = {
        (
            row["table_name"],
            row["trigger_name"],
            row["tgenabled"],
            _normalize_catalog_sql(row["definition"]),
        )
        for row in identity["ddl"]["triggers"]
    }
    if actual_triggers != _expected_trigger_contract():
        raise CutoverError("target catalog trigger contract drift")
    actual_routines = {
        (
            row["routine_name"],
            _normalize_catalog_sql(row["definition"]),
        )
        for row in identity["ddl"].get("routines", [])
    }
    if actual_routines != _expected_routine_contract():
        expected_routines = _expected_routine_contract()
        missing_routines = expected_routines - actual_routines
        extra_routines = actual_routines - expected_routines
        raise CutoverError(
            "target catalog routine contract drift: "
            f"missing={sorted(missing_routines)!r} extra={sorted(extra_routines)!r}"
        )
    actual_functional_unique_indexes = {
        (
            row["table_name"],
            row["index_name"],
            _normalize_catalog_sql(row["definition"]),
        )
        for row in functional_unique_indexes
        if row["indisvalid"] is True
    }
    if len(actual_functional_unique_indexes) != len(functional_unique_indexes) or (
        actual_functional_unique_indexes != _expected_functional_unique_index_contract()
    ):
        raise CutoverError("target catalog functional unique-index contract drift")
    grant_rows = [dict(row) for row in grants]
    if any(row["grantee"] == "PUBLIC" for row in grant_rows) or any(
        row["grantee"] == "PUBLIC" for row in schema_grants
    ):
        raise CutoverError("target catalog PUBLIC grants are forbidden")
    if not set(owners) <= PINNED_SCHEMA_ROLES:
        raise CutoverError("target catalog owner is outside the pinned role allowlist")
    allowed_grantees = set(PINNED_SCHEMA_ROLES)
    if any(
        row["grantee"] not in allowed_grantees
        for row in (*grant_rows, *[dict(row) for row in schema_grants])
    ):
        raise CutoverError("target catalog grant grantee is outside the pinned role allowlist")
    expected_migrator_grants = {
        (table_name, "SELECT") for table_name in (*ALL_EXPECTED_TARGET_TABLES, "alembic_version")
    }
    for migrator_role in TARGET_MIGRATOR_ROLES - set(owners):
        actual_migrator_grants = {
            (row["table_name"], row["privilege_type"])
            for row in grant_rows
            if row["grantee"] == migrator_role
        }
        if actual_migrator_grants and actual_migrator_grants != expected_migrator_grants:
            raise CutoverError(f"target migrator grant contract drift: {migrator_role}")
    app_grants = {
        (row["table_name"], row["privilege_type"])
        for row in grant_rows
        if row["grantee"] == TARGET_APP_ROLE
    }
    for table_name in ALL_EXPECTED_TARGET_TABLES:
        expected = {
            (table_name, privilege) for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
        }
        if {
            (table, privilege) for table, privilege in app_grants if table == table_name
        } != expected:
            raise CutoverError(f"target app grant contract drift: {table_name}")
    if any(
        row["table_name"] == "alembic_version" and row["grantee"] == TARGET_APP_ROLE
        for row in grant_rows
    ):
        raise CutoverError("target app must not have alembic_version grants")
    payload = {
        "revision": list(revision),
        "tables": sorted(table_names),
        "columns": identity["ddl"]["columns"],
        "constraints": identity["ddl"]["constraints"],
        "triggers": identity["ddl"]["triggers"],
        "grants": [dict(row) for row in grants],
        "schema_grants": [dict(row) for row in schema_grants],
        "functional_unique_indexes": [dict(row) for row in functional_unique_indexes],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    result = {
        "role": role,
        "revision": list(revision),
        "catalog_digest": hashlib.sha256(encoded).hexdigest(),
        "target_identity": identity,
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
        async with connection.begin():
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            cutoff = datetime.now(UTC)
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
                    "ce.updated_at,cs.display_name,"
                    "CASE "
                    "WHEN ce.external_uid LIKE 'manual\\_%' ESCAPE '\\' THEN 'manual' "
                    "WHEN ce.external_uid LIKE 'v1-schedule-%' THEN 'ics_reimport' "
                    "ELSE 'unclassified' END AS cutover_bucket "
                    "FROM public.calendar_events ce "
                    "LEFT JOIN public.calendar_sources cs ON cs.id=ce.source_id ORDER BY ce.id",
                ),
            }
    validate_source(source_rows)
    return SourceSnapshot(source_rows, cutoff)


async def verify_restored_source(
    engine: AsyncEngine,
    expected_inventory: Mapping[str, Mapping[str, Any]],
    expected_identity: Mapping[str, Any] | None = None,
) -> SourceSnapshot:
    """Verify a fresh throwaway restore before it can feed recovery/Phase A.

    Decryption and ``pg_restore`` belong to the owner workstation ceremony.  This
    seam receives only the resulting throwaway connection and compares the full
    source inventory; it never opens the live source URL.
    """
    await assert_source_read_only(engine)
    if expected_identity:
        async with engine.connect() as connection:
            actual_identity = await read_connection_identity(connection, "public")
        assert_restored_source_is_distinct(actual_identity, expected_identity)
        assert_restored_source_matches(actual_identity, expected_identity)
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
        expected_bucket = _calendar_bucket_from_uid(uid)
        if event.get("cutover_bucket", expected_bucket) != expected_bucket:
            raise SourceValidationError("calendar SQL taxonomy disagrees with source UID")
        if expected_bucket == "unclassified":
            raise SourceValidationError("calendar event has unclassified external_uid")
        if event.get("ends_at") <= event.get("starts_at"):
            raise SourceValidationError("calendar event has invalid duration")


def calendar_bucket_counts(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    return {bucket: value["count"] for bucket, value in calendar_bucket_inventory(rows).items()}


def _calendar_bucket_from_uid(value: Any) -> str:
    if isinstance(value, str) and value.startswith("manual_"):
        return "manual"
    if isinstance(value, str) and value.startswith("v1-schedule-"):
        return "ics_reimport"
    return "unclassified"


def calendar_bucket_inventory(
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[Mapping[str, Any]]] = {
        "manual": [],
        "ics_reimport": [],
        "unclassified": [],
    }
    for row in rows.get("calendar_events", []):
        bucket = row.get("cutover_bucket")
        if bucket not in buckets:
            bucket = _calendar_bucket_from_uid(row.get("external_uid"))
        buckets[bucket].append(row)
    return {
        bucket: {
            "count": len(bucket_rows),
            "sorted_id_digest": digest_ids(f"calendar_events:{bucket}", bucket_rows),
        }
        for bucket, bucket_rows in buckets.items()
    }


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
        due_at = row["due_at"]
        task_rows.append(
            {
                "id": row["id"],
                "title": row["title"],
                "body_md": row["note"],
                "status": row["status"],
                "priority": priority,
                "due_precision": "none" if due_at is None else "datetime",
                "due_on": None,
                "due_at": due_at,
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
        source_id = manual_source_id or deterministic_uuid7(
            snapshot.cutoff_at.isoformat(), snapshot.cutoff_at
        )
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
    script_sha: str | None = None,
    script_file_sha256: str | None = None,
    target_identity: Mapping[str, Any] | None = None,
    source_dump_sha256: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    source_expected = {name: inventory(name, values) for name, values in transformed.items()}
    expected_ids = {
        name: [str(row["id"]) for row in values] for name, values in transformed.items()
    }
    empty = {name: empty_inventory(name) for name in PURGE_ONLY_COMPONENTS}
    code = actual_code_identity()
    if script_sha and script_sha != code["git_sha"]:
        raise ManifestError("manifest must bind the actual immutable git SHA")
    if script_file_sha256 and script_file_sha256 != code["file_sha256"]:
        raise ManifestError("manifest must bind the actual script file digest")
    return {
        "manifest_version": 1,
        "transform_version": TRANSFORM_VERSION,
        "run_id": run_id or str(uuid4()),
        "script_sha": code["git_sha"],
        "script_file_sha256": code["file_sha256"],
        "target_host": target_host_name,
        "target_identity": dict(target_identity or {}),
        "source_cutoff_at": snapshot.cutoff_at.astimezone(UTC).isoformat(),
        "approval_expires_at": (
            snapshot.cutoff_at.astimezone(UTC) + timedelta(hours=24)
        ).isoformat(),
        "source_identity": dict(source_identity),
        "source_expected": source_expected,
        "source_inventory": snapshot.source_inventory,
        "source_dump_sha256": source_dump_sha256,
        "calendar_buckets": calendar_bucket_inventory(snapshot.rows),
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
    path.write_bytes(encrypt_artifact(payload))
    return digest


def finalize_manifest(path: Path, signature: str) -> None:
    """Attach an owner Ed25519 signature without changing the signed digest."""
    payload = decrypt_artifact(path)
    if payload.get("manifest_digest") != manifest_digest(payload):
        raise ManifestError("cannot finalize a changed manifest")
    verify_signature(signature, approval_payload(payload))
    payload["owner_approval"] = {
        "algorithm": "Ed25519",
        **approval_payload(payload),
        "signature": signature,
    }
    path.write_bytes(encrypt_artifact(payload))


def read_final_manifest(
    path: Path, *, expected_script_sha: str | None, expected_host: str
) -> dict[str, Any]:
    payload = decrypt_artifact(path)
    if payload.get("manifest_digest") != manifest_digest(payload):
        raise ManifestError("manifest digest mismatch")
    identity = actual_code_identity()
    if payload.get("script_sha") != identity["git_sha"]:
        raise ManifestError("manifest script SHA mismatch")
    if payload.get("script_file_sha256") != identity["file_sha256"]:
        raise ManifestError("manifest script file digest mismatch")
    if expected_script_sha and expected_script_sha != identity["git_sha"]:
        raise ManifestError("operator supplied SHA is not the actual immutable git SHA")
    if payload.get("target_host") != expected_host:
        raise ManifestError("manifest target host mismatch")
    source_dump_sha = payload.get("source_dump_sha256")
    if (
        not isinstance(source_dump_sha, str)
        or len(source_dump_sha) != 64
        or any(char not in "0123456789abcdef" for char in source_dump_sha.lower())
    ):
        raise ManifestError("manifest is not bound to a verified encrypted source dump")
    required_sections = (
        "source_identity",
        "source_inventory",
        "source_expected",
        "expected_ids",
        "calendar_buckets",
        "approval_expires_at",
        "target_identity",
        "phase_b_target_snapshot",
        "phase_b_target_snapshot_digest",
        "schema_attestation",
    )
    if any(payload.get(section) is None for section in required_sections):
        raise ManifestError("manifest is missing a required signed section")
    approval = payload.get("owner_approval")
    if not isinstance(approval, dict):
        raise ManifestError("manifest has no owner approval")
    required = {
        "manifest_digest": payload["manifest_digest"],
        "run_id": payload.get("run_id"),
        "script_sha": identity["git_sha"],
        "script_file_sha256": identity["file_sha256"],
        "target_host": expected_host,
        "approval_expires_at": payload.get("approval_expires_at"),
        "phase_b_target_snapshot_digest": payload.get("phase_b_target_snapshot_digest"),
    }
    if any(approval.get(key) != value for key, value in required.items()):
        raise ManifestError("owner approval is not bound to this exact manifest")
    try:
        approval_expiry = datetime.fromisoformat(payload["approval_expires_at"])
    except KeyError, TypeError, ValueError:
        raise ManifestError("manifest approval expiry is invalid") from None
    if approval_expiry.tzinfo is None or approval_expiry <= datetime.now(UTC):
        raise ManifestError("manifest owner approval has expired")
    if approval.get("algorithm") != "Ed25519":
        raise ManifestError("owner approval algorithm is not Ed25519")
    if not approval.get("signature"):
        raise ManifestError("owner approval signature is missing")
    verify_signature(approval["signature"], approval_payload(payload))
    return payload


def verify_source_dump(
    dump_path: Path,
    expected_sha256: str | None = None,
    *,
    require_authenticated_restore: bool = False,
) -> str:
    """Verify only a supplied encrypted/full dump; never opens a live source."""
    if not dump_path.is_file() or dump_path.stat().st_size == 0:
        raise CutoverError("source dump is missing or empty")
    if dump_path.suffix.lower() != ".age":
        raise CutoverError("source dump must be an age-encrypted artifact")
    blob = dump_path.read_bytes()
    if not blob.startswith(AGE_HEADER):
        raise CutoverError("source dump is not an age envelope")
    if require_authenticated_restore:
        identity_path = os.environ.get(AGE_IDENTITY_FILE_ENV)
        if not identity_path:
            raise CutoverError(f"{AGE_IDENTITY_FILE_ENV} is required for age verification")
        age_binary = os.environ.get("CUTOVER_AGE_BINARY", "age")
        restore_binary = os.environ.get("CUTOVER_PG_RESTORE_BINARY", "pg_restore")
        age_process = restore_process = None
        try:
            age_process = subprocess.Popen(
                [age_binary, "--decrypt", "--identity", identity_path, str(dump_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            restore_process = subprocess.Popen(
                [restore_binary, "--list"],
                stdin=age_process.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if age_process.stdout is not None:
                age_process.stdout.close()
            restore_process.wait(timeout=30)
            age_process.wait(timeout=30)
            if restore_process.returncode != 0 or age_process.returncode != 0:
                raise CutoverError("encrypted source dump age/pg_restore verification failed")
        except OSError, subprocess.SubprocessError:
            raise CutoverError("encrypted source dump age/pg_restore verification failed") from None
        finally:
            for process in (restore_process, age_process):
                if process is not None and process.poll() is None:
                    process.kill()
    digest = hashlib.sha256(blob).hexdigest()
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
    code = actual_code_identity()
    if expected_script_sha != code["git_sha"] or manifest.get("script_sha") != code["git_sha"]:
        raise ManifestError("failure receipt script SHA is not the actual immutable SHA")
    receipt = decrypt_artifact(path)
    required = {
        "run_id": manifest.get("run_id"),
        "manifest_digest": manifest.get("manifest_digest"),
        "script_sha": manifest.get("script_sha"),
        "script_file_sha256": manifest.get("script_file_sha256"),
        "target_host": expected_host,
        "fly_never_restarted": True,
        "source_dump_sha256": manifest.get("source_dump_sha256"),
    }
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ManifestError("failure receipt is not bound to this run")
    if receipt.get("algorithm") != "Ed25519":
        raise ManifestError("failure receipt algorithm is not Ed25519")
    if receipt.get("failed_command") not in {"commit", "verify"}:
        raise ManifestError("failure receipt has an invalid failed command")
    outcome = receipt.get("failure_outcome")
    expected_outcome = (
        "unknown_after_submit"
        if receipt.get("failed_command") == "commit"
        else "post_commit_verify_failed"
    )
    if outcome != expected_outcome:
        raise ManifestError("failure receipt is not an authorized recoverable outcome")
    if (
        not receipt.get("failure_class")
        or not receipt.get("failure_stage")
        or not receipt.get("failure_time")
        or not receipt.get("source_dump_sha256")
        or not receipt.get("signature")
    ):
        raise ManifestError("failure receipt is unsigned or missing failure stage")
    if receipt.get("fly_state") != "stopped":
        raise ManifestError("failure receipt does not attest Fly stopped")
    target_state = receipt.get("target_state")
    if (
        not isinstance(target_state, dict)
        or target_state.get("sole_machine_stopped") is not True
        or target_state.get("never_restarted") is not True
        or not isinstance(target_state.get("machine_id"), str)
        or not isinstance(target_state.get("restart_evidence"), dict)
    ):
        raise ManifestError("failure receipt lacks native Fly stopped/restart evidence")
    verify_signature(receipt["signature"], failure_receipt_payload(receipt))
    inventory_map = receipt.get("failed_run_domain_inventory")
    if set(inventory_map or {}) != set(DOMAIN_COMPONENTS):
        raise ManifestError("failure receipt does not contain the complete domain inventory")
    for component in DOMAIN_COMPONENTS:
        proof = inventory_map[component]
        if (
            not isinstance(proof, dict)
            or not isinstance(proof.get("count"), int)
            or not isinstance(proof.get("sorted_id_digest"), str)
            or len(proof["sorted_id_digest"]) != 64
            or not isinstance(proof.get("full_row_digest"), str)
            or len(proof["full_row_digest"]) != 64
        ):
            raise ManifestError("failure receipt has an invalid domain inventory proof")
    try:
        expiry = datetime.fromisoformat(receipt.get("expires_at"))
    except TypeError, ValueError:
        raise ManifestError("failure receipt expiry is invalid") from None
    try:
        failure_time = datetime.fromisoformat(receipt.get("failure_time"))
    except TypeError, ValueError:
        raise ManifestError("failure receipt failure time is invalid") from None
    current_time = now or datetime.now(UTC)
    if (
        expiry.tzinfo is None
        or failure_time.tzinfo is None
        or failure_time > current_time
        or expiry <= current_time
        or expiry <= failure_time
    ):
        raise ManifestError("failure receipt has expired")
    return receipt


def write_failure_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    payload = dict(receipt)
    payload["algorithm"] = "Ed25519"
    path.write_bytes(encrypt_artifact(payload))


def assert_artifact_output_is_distinct(output: Path, *inputs: Path | None) -> None:
    """Reject an output path that would overwrite any ceremony input artifact."""
    try:
        output_path = output.expanduser().resolve(strict=False)
        input_paths = {
            path.expanduser().resolve(strict=False) for path in inputs if path is not None
        }
    except OSError:
        raise CutoverError("failure receipt output path cannot be resolved") from None
    if output_path in input_paths:
        raise CutoverError("failure receipt output must differ from every input artifact")


def build_failure_receipt(
    manifest: Mapping[str, Any],
    *,
    target_inventory: Mapping[str, Mapping[str, Any]],
    target_state: Mapping[str, Any],
    failed_command: str,
    failure_class: str,
    failure_stage: str,
    failure_time: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    """Create an encrypted, unsigned draft from a just-observed failed run.

    This is intentionally a draft ceremony: only the owner signer can attach
    the Ed25519 signature with ``--finalize-failure-receipt``.  The inventory is
    copied from the app-role read-only connection and never printed.
    """
    if failed_command not in {"commit", "verify"}:
        raise ManifestError("failure receipt command must be commit or verify")
    if not failure_class or not failure_stage:
        raise ManifestError("failure receipt class and stage are required")
    if failure_time.tzinfo is None or expires_at.tzinfo is None or expires_at <= failure_time:
        raise ManifestError("failure receipt expiry must follow failure time")
    if (
        target_state.get("fly_state") != "stopped"
        or target_state.get("never_restarted") is not True
        or not isinstance(target_state.get("machine_id"), str)
        or not isinstance(target_state.get("restart_evidence"), Mapping)
    ):
        raise ManifestError("failure receipt requires current native Fly stopped evidence")
    if set(target_inventory) != set(DOMAIN_COMPONENTS + APP_READABLE_PRESERVE):
        raise ManifestError("failure receipt requires the complete target inventory")
    return {
        "algorithm": "Ed25519",
        "run_id": manifest["run_id"],
        "manifest_digest": manifest["manifest_digest"],
        "script_sha": manifest["script_sha"],
        "script_file_sha256": manifest["script_file_sha256"],
        "target_host": manifest["target_host"],
        "source_dump_sha256": manifest["source_dump_sha256"],
        "failed_command": failed_command,
        "failure_outcome": (
            "unknown_after_submit" if failed_command == "commit" else "post_commit_verify_failed"
        ),
        "failure_class": failure_class,
        "failure_stage": failure_stage,
        "failure_time": failure_time.astimezone(UTC).isoformat(),
        "expires_at": expires_at.astimezone(UTC).isoformat(),
        "fly_state": "stopped",
        "target_state": dict(target_state),
        "fly_never_restarted": True,
        "failed_run_domain_inventory": {
            component: dict(target_inventory[component]) for component in DOMAIN_COMPONENTS
        },
    }


def finalize_failure_receipt(path: Path, signature: str) -> None:
    payload = decrypt_artifact(path)
    payload["algorithm"] = "Ed25519"
    verify_signature(signature, failure_receipt_payload(payload))
    payload["signature"] = signature
    path.write_bytes(encrypt_artifact(payload))


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


async def collect_target_inventory_as_app(
    engine: AsyncEngine,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await assert_app_role(session)
            identity = await read_runtime_coordinates(session)
            return identity, await collect_target_inventory(session)


async def run_commit(
    manifest: Mapping[str, Any],
    engine: AsyncEngine,
    transformed: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    assert_manifest_target_host(manifest)
    for component in MAPPED_COMPONENTS:
        transformed_rows = list(transformed.get(component, []))
        if inventory(component, transformed_rows) != manifest["source_expected"][component]:
            raise ManifestError(f"transformed source drift: {component}")
        actual_ids = sorted(str(row["id"]) for row in transformed_rows)
        if actual_ids != sorted(manifest["expected_ids"][component]):
            raise ManifestError(f"transformed source ID set drift: {component}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            await assert_app_role(session)
            target_identity = await read_runtime_coordinates(session)
            assert_runtime_coordinates_match(target_identity, manifest["target_identity"])
            current = await collect_target_inventory(session)
            if current == expected_final_inventory(manifest):
                return
            if current != manifest["phase_b_target_snapshot"]:
                raise ManifestError("target Phase-B snapshot drift before DELETE")
            await purge_import_assert(session, manifest, transformed)
            final = await collect_target_inventory(session)
            if final != expected_final_inventory(manifest):
                raise ManifestError("post-purge final inventory drift")


async def purge_import_assert(
    session: AsyncSession,
    manifest: Mapping[str, Any],
    transformed: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
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
    for component in MAPPED_COMPONENTS:
        for row in transformed.get(component, []):
            await session.execute(insert(MODEL_TABLES[component]).values(**dict(row)))
    final = await collect_target_inventory(session)
    phase_b_expected = dict(manifest["phase_b_target_snapshot"])
    for component in MAPPED_COMPONENTS:
        if final[component] != manifest["source_expected"][component]:
            raise ManifestError(f"mapped component proof failed: {component}")
    for component in PURGE_ONLY_COMPONENTS:
        if final[component] != empty_inventory(component):
            raise ManifestError(f"purge-only component is not empty: {component}")
    for component in APP_READABLE_PRESERVE:
        if final[component] != phase_b_expected[component]:
            raise ManifestError(f"preserve component changed: {component}")


async def run_recover(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    engine: AsyncEngine,
    transformed: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    fly_state_verifier: Callable[[], Awaitable[Mapping[str, Any]]]
    | Callable[[], Mapping[str, Any]]
    | None = None,
) -> None:
    assert_manifest_target_host(manifest)
    if fly_state_verifier is None:
        raise CutoverError("current Fly stopped-state verifier is required for recovery")
    try:
        failure_time = datetime.fromisoformat(str(receipt["failure_time"]))
    except KeyError, TypeError, ValueError:
        raise ManifestError("recovery receipt failure time is invalid") from None
    if failure_time.tzinfo is None:
        raise ManifestError("recovery receipt failure time must include UTC offset")
    receipt_target_state = receipt.get("target_state")
    if not isinstance(receipt_target_state, Mapping) or not isinstance(
        receipt_target_state.get("machine_id"), str
    ):
        raise ManifestError("recovery receipt lacks the signed Fly machine identity")
    for component in MAPPED_COMPONENTS:
        transformed_rows = list(transformed.get(component, []))
        if inventory(component, transformed_rows) != manifest["source_expected"][component]:
            raise ManifestError(f"recovery source drift: {component}")
        if sorted(str(row["id"]) for row in transformed_rows) != sorted(
            manifest["expected_ids"][component]
        ):
            raise ManifestError(f"recovery source ID set drift: {component}")
    # The owner-assisted stop is checked before opening the destructive target
    # transaction.  A post-commit audit below records the explicitly accepted
    # residual race if an operator restarts the Machine between these checks.
    await assert_current_fly_stopped(
        fly_state_verifier,
        failure_time=failure_time,
        expected_machine_id=receipt_target_state["machine_id"],
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            await assert_app_role(session)
            target_identity = await read_runtime_coordinates(session)
            assert_runtime_coordinates_match(target_identity, manifest["target_identity"])
            current = await collect_target_inventory(session)
            failure_inventory = receipt["failed_run_domain_inventory"]
            for component in DOMAIN_COMPONENTS:
                if current[component] != failure_inventory[component]:
                    raise ManifestError("target moved beyond authorized failed-run state")
            for component in APP_READABLE_PRESERVE:
                if current[component] != manifest["phase_b_target_snapshot"][component]:
                    raise ManifestError("preserve data changed before recovery")
            await purge_import_assert(session, manifest, transformed)
            final = await collect_target_inventory(session)
            if final != expected_final_inventory(manifest):
                raise ManifestError("post-purge final inventory drift")
    # This is intentionally an audit after commit, not a claim that the
    # external Fly state is fenced through the database COMMIT.
    await assert_current_fly_stopped(
        fly_state_verifier,
        failure_time=failure_time,
        expected_machine_id=receipt_target_state["machine_id"],
    )


async def run_verify(manifest: Mapping[str, Any], engine: AsyncEngine) -> dict[str, Any]:
    assert_manifest_target_host(manifest)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await assert_app_role(session)
            target_identity = await read_runtime_coordinates(session)
            assert_runtime_coordinates_match(target_identity, manifest["target_identity"])
            current = await collect_target_inventory(session)
    for component in MAPPED_COMPONENTS:
        if current[component] != manifest["source_expected"][component]:
            raise ManifestError(f"verify found mapped drift: {component}")
    # Check descendants before their synthetic FK support rows so a residual
    # fixture proves the named component's guard rather than its parent.
    for component in reversed(PURGE_ONLY_COMPONENTS):
        if current[component] != empty_inventory(component):
            raise ManifestError(f"verify found residual purge-only row: {component}")
    for component in APP_READABLE_PRESERVE:
        if current[component] != manifest["phase_b_target_snapshot"][component]:
            raise ManifestError(f"verify found preserve drift: {component}")
    return current


async def attest_manifest_schema(manifest: Mapping[str, Any]) -> None:
    engine = migrator_engine()
    try:
        await attest_schema(
            engine,
            expected_digest=manifest["schema_attestation"]["catalog_digest"],
        )
    finally:
        await engine.dispose()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cutover_v2")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--commit", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--recover", action="store_true")
    p.add_argument("--finalize-manifest", action="store_true")
    p.add_argument("--finalize-failure-receipt", action="store_true")
    p.add_argument(
        "--write-failure-receipt",
        type=Path,
        help="Write an encrypted unsigned receipt from the current failed-run state",
    )
    p.add_argument(
        "--signature-file",
        type=Path,
        help="UTF-8 Ed25519 signature produced by the owner signer; never a private key",
    )
    p.add_argument("--manifest", type=Path)
    p.add_argument("--write-manifest", type=Path)
    p.add_argument("--confirm-target-host")
    p.add_argument("--expected-script-sha", default=os.environ.get("CUTOVER_SCRIPT_SHA"))
    p.add_argument("--source-dump", type=Path)
    p.add_argument("--source-dump-sha256")
    p.add_argument("--failure-receipt", type=Path)
    p.add_argument("--failed-command", choices=("commit", "verify"))
    p.add_argument("--failure-class")
    p.add_argument("--failure-stage")
    p.add_argument("--failure-time")
    p.add_argument("--expires-at")
    return p


def read_signature_file(path: Path) -> str:
    try:
        signature = path.read_text(encoding="utf-8").strip()
    except OSError, UnicodeError:
        raise CutoverError("signature file cannot be read as UTF-8") from None
    if not signature or "\x00" in signature:
        raise CutoverError("signature file is empty or invalid")
    return signature


async def async_main(args: argparse.Namespace) -> int:
    if args.write_failure_receipt:
        assert_artifact_output_is_distinct(
            args.write_failure_receipt,
            args.manifest,
            args.source_dump,
            args.failure_receipt,
            args.signature_file,
        )
        if (
            args.finalize_manifest
            or args.finalize_failure_receipt
            or args.dry_run
            or args.commit
            or args.verify
            or args.recover
        ):
            raise CutoverError("failure receipt draft cannot be combined with another mode")
        if (
            not args.manifest
            or not args.confirm_target_host
            or not args.expected_script_sha
            or not args.failed_command
            or not args.failure_class
            or not args.failure_stage
            or not args.failure_time
            or not args.expires_at
        ):
            raise CutoverError(
                "failure receipt draft requires manifest, SHA, host, failed "
                "command/class/stage/time and expiry"
            )
        target = target_url()
        assert_confirmed_host(target, args.confirm_target_host)
        assert_target_coordinates()
        manifest = read_final_manifest(
            args.manifest,
            expected_script_sha=args.expected_script_sha,
            expected_host=args.confirm_target_host.lower(),
        )
        try:
            failure_time = datetime.fromisoformat(args.failure_time)
            expires_at = datetime.fromisoformat(args.expires_at)
        except ValueError:
            raise CutoverError("failure receipt time and expiry must be RFC3339") from None
        now = datetime.now(UTC)
        if (
            failure_time.tzinfo is None
            or expires_at.tzinfo is None
            or failure_time > now
            or expires_at <= now
            or expires_at <= failure_time
        ):
            raise CutoverError("failure receipt time/expiry window is invalid")
        target_engine_obj = target_engine()
        try:
            target_identity, target_inventory = await collect_target_inventory_as_app(
                target_engine_obj
            )
        finally:
            await target_engine_obj.dispose()
        assert_runtime_coordinates_match(target_identity, manifest["target_identity"])
        target_state = await assert_current_fly_stopped(
            fly_state_verifier_from_env(), failure_time=failure_time
        )
        receipt = build_failure_receipt(
            manifest,
            target_inventory=target_inventory,
            target_state=target_state,
            failed_command=args.failed_command,
            failure_class=args.failure_class,
            failure_stage=args.failure_stage,
            failure_time=failure_time,
            expires_at=expires_at,
        )
        write_failure_receipt(args.write_failure_receipt, receipt)
        print(f"failure_receipt=draft path={args.write_failure_receipt}")
        return 0
    if args.finalize_manifest or args.finalize_failure_receipt:
        if args.finalize_manifest and args.finalize_failure_receipt:
            raise CutoverError("manifest and failure receipt finalization are mutually exclusive")
        if args.dry_run or args.commit or args.verify or args.recover:
            raise CutoverError("finalization cannot be combined with a cutover mode")
        if not args.signature_file:
            raise CutoverError("finalization requires --signature-file")
        signature = read_signature_file(args.signature_file)
        if args.finalize_manifest:
            if not args.manifest:
                raise CutoverError("manifest finalization requires --manifest")
            finalize_manifest(args.manifest, signature)
            print("manifest=finalized")
            return 0
        if not args.failure_receipt:
            raise CutoverError("failure receipt finalization requires --failure-receipt")
        finalize_failure_receipt(args.failure_receipt, signature)
        print("failure_receipt=finalized")
        return 0
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
    code = actual_code_identity()
    manifest = None
    final_manifest_target_before: dict[str, dict[str, Any]] | None = None
    if mode == "dry-run" and args.manifest:
        if not args.confirm_target_host or not args.expected_script_sha:
            raise CutoverError(
                "dry-run with a finalized manifest requires actual script SHA and host confirmation"
            )
        if args.write_manifest:
            raise CutoverError("dry-run cannot read and write manifests in one invocation")
        assert_confirmed_host(target, args.confirm_target_host)
        assert_target_coordinates()
        manifest = read_final_manifest(
            args.manifest,
            expected_script_sha=args.expected_script_sha,
            expected_host=args.confirm_target_host.lower(),
        )
        if args.source_dump is None or args.source_dump_sha256 is None:
            raise CutoverError("final-manifest dry-run requires encrypted source dump and SHA-256")
        dump_digest = verify_source_dump(
            args.source_dump,
            args.source_dump_sha256,
            require_authenticated_restore=True,
        )
        if dump_digest != manifest["source_dump_sha256"]:
            raise ManifestError("source dump does not match signed manifest")
        attestation_engine = migrator_engine()
        try:
            attestation = await attest_schema(
                attestation_engine,
                expected_digest=manifest["schema_attestation"]["catalog_digest"],
            )
        finally:
            await attestation_engine.dispose()
        assert_identity_matches(attestation["target_identity"], manifest["target_identity"])
        target_probe = target_engine()
        try:
            await assert_app_cannot_read_alembic(target_probe)
            _, final_manifest_target_before = await collect_target_inventory_as_app(target_probe)
        finally:
            await target_probe.dispose()
    if mode != "dry-run":
        if not args.confirm_target_host or not args.expected_script_sha or not args.manifest:
            raise CutoverError(
                "non-dry mode requires manifest, actual script SHA and host confirmation"
            )
        if args.expected_script_sha != code["git_sha"]:
            raise CutoverError("expected script SHA must equal the actual immutable git SHA")
        assert_confirmed_host(target, args.confirm_target_host)
        assert_target_coordinates()
        manifest = read_final_manifest(
            args.manifest,
            expected_script_sha=args.expected_script_sha,
            expected_host=args.confirm_target_host.lower(),
        )
        if args.source_dump is None or args.source_dump_sha256 is None:
            raise CutoverError("non-dry mode requires encrypted source dump and SHA-256")
        dump_digest = verify_source_dump(
            args.source_dump,
            args.source_dump_sha256,
            require_authenticated_restore=True,
        )
        if dump_digest != manifest["source_dump_sha256"]:
            raise ManifestError("source dump does not match signed manifest")
        attestation_engine = migrator_engine()
        try:
            attestation = await attest_schema(
                attestation_engine,
                expected_digest=manifest["schema_attestation"]["catalog_digest"],
            )
        finally:
            await attestation_engine.dispose()
        assert_identity_matches(attestation["target_identity"], manifest["target_identity"])
        target_probe = target_engine()
        try:
            await assert_app_cannot_read_alembic(target_probe)
        finally:
            await target_probe.dispose()
        if mode == "verify":
            target_engine_obj = target_engine()
            try:
                await run_verify(manifest, target_engine_obj)
            finally:
                await target_engine_obj.dispose()
            await attest_manifest_schema(manifest)
            print("verify=ok")
            return 0
        if mode == "recover":
            if not args.failure_receipt:
                raise CutoverError("recover requires a separately signed failure receipt")
            receipt = read_failure_receipt(
                args.failure_receipt,
                manifest=manifest,
                expected_script_sha=args.expected_script_sha,
                expected_host=args.confirm_target_host.lower(),
            )
            if receipt["source_dump_sha256"] != dump_digest:
                raise ManifestError("failure receipt source dump hash mismatch")
            recovery_value = os.environ.get(RECOVERY_SOURCE_URL_ENV)
            if not recovery_value:
                raise CutoverError(f"{RECOVERY_SOURCE_URL_ENV} is required for recovery")
            recovery_engine = restored_source_engine(recovery_value)
            try:
                restored = await verify_restored_source(
                    recovery_engine,
                    manifest["source_inventory"],
                    manifest["source_identity"],
                )
            finally:
                await recovery_engine.dispose()
            source_id = (
                UUID(manifest["expected_ids"]["calendar_source"][0])
                if manifest["expected_ids"].get("calendar_source")
                else None
            )
            transformed = transform_source(restored, manual_source_id=source_id)
            target_engine_obj = target_engine()
            try:
                await run_recover(
                    manifest,
                    receipt,
                    target_engine_obj,
                    transformed,
                    fly_state_verifier=fly_state_verifier_from_env(),
                )
            finally:
                await target_engine_obj.dispose()
            await attest_manifest_schema(manifest)
            print("recover=ok")
            return 0
        source = source_engine()
        try:
            await assert_source_identity(source)
            await assert_source_read_only(source)
            async with source.connect() as connection:
                source_identity = await read_connection_identity(connection, "public")
            if source_identity != manifest["source_identity"]:
                raise ManifestError("source identity or DDL fingerprint drift after freeze")
            snapshot = await load_source_snapshot(source)
            if snapshot.source_inventory != manifest["source_inventory"]:
                raise ManifestError("source inventory drift after freeze")
            source_id = (
                UUID(manifest["expected_ids"]["calendar_source"][0])
                if manifest["expected_ids"].get("calendar_source")
                else None
            )
            transformed = transform_source(snapshot, manual_source_id=source_id)
        finally:
            await source.dispose()
        target_engine_obj = target_engine()
        try:
            await run_commit(manifest, target_engine_obj, transformed)
        finally:
            await target_engine_obj.dispose()
        await attest_manifest_schema(manifest)
        print("commit=ok")
        return 0
    if args.write_manifest and (args.source_dump is None or args.source_dump_sha256 is None):
        raise CutoverError("manifest draft requires encrypted source dump and SHA-256")
    dump_digest = (
        verify_source_dump(
            args.source_dump,
            args.source_dump_sha256,
            require_authenticated_restore=True,
        )
        if args.source_dump and args.source_dump_sha256
        else None
    )
    assert_target_coordinates()
    source = source_engine()
    try:
        await assert_source_identity(source)
        await assert_source_read_only(source)
        async with source.connect() as connection:
            source_identity = await read_connection_identity(connection, "public")
        if manifest and source_identity != manifest["source_identity"]:
            raise ManifestError("source identity or DDL fingerprint drift after freeze")
        snapshot = await load_source_snapshot(source)
        source_id = (
            UUID(manifest["expected_ids"]["calendar_source"][0])
            if manifest and manifest["expected_ids"].get("calendar_source")
            else None
        )
        transformed = transform_source(snapshot, manual_source_id=source_id)
        if manifest:
            if snapshot.source_inventory != manifest["source_inventory"]:
                raise ManifestError("source inventory drift after freeze")
            if calendar_bucket_inventory(snapshot.rows) != manifest["calendar_buckets"]:
                raise ManifestError("calendar bucket receipt drift after freeze")
            for component in MAPPED_COMPONENTS:
                if (
                    inventory(component, transformed[component])
                    != manifest["source_expected"][component]
                ):
                    raise ManifestError(f"transformed source drift: {component}")
                if sorted(str(row["id"]) for row in transformed[component]) != sorted(
                    manifest["expected_ids"][component]
                ):
                    raise ManifestError(f"transformed source ID set drift: {component}")
        print(f"SOURCE {SOURCE_DB_NAME} @ local (read-only)")
        print(f"TARGET {target_host(target)}")
        buckets = calendar_bucket_counts(snapshot.rows)
        print(
            "calendar_buckets "
            f"manual={buckets['manual']} ics_reimport={buckets['ics_reimport']} "
            f"unclassified={buckets['unclassified']}"
        )
        for bucket, proof in calendar_bucket_inventory(snapshot.rows).items():
            print(
                f"calendar_bucket {bucket} count={proof['count']} "
                f"id_digest={proof['sorted_id_digest']}"
            )
        for component in transformed:
            full_digest = digest_rows(component, transformed[component], TARGET_FIELDS[component])
            print(
                f"{component} count={len(transformed[component])} "
                f"id_digest={digest_ids(component, transformed[component])} "
                f"full_digest={full_digest}"
            )
        if not args.write_manifest:
            if manifest:
                target_engine_obj = target_engine()
                try:
                    target_identity, target_snapshot = await collect_target_inventory_as_app(
                        target_engine_obj
                    )
                finally:
                    await target_engine_obj.dispose()
                assert_runtime_coordinates_match(target_identity, manifest["target_identity"])
                if final_manifest_target_before is None:
                    raise ManifestError("final-manifest dry-run lacks an initial target snapshot")
                if target_snapshot != final_manifest_target_before:
                    raise ManifestError("target Phase-B snapshot changed during dry-run")
                if target_snapshot != manifest["phase_b_target_snapshot"]:
                    raise ManifestError("target Phase-B snapshot drift during dry-run")
            return 0
        target_engine_obj = target_engine()
        try:
            await assert_app_cannot_read_alembic(target_engine_obj)
            target_identity, target_snapshot = await collect_target_inventory_as_app(
                target_engine_obj
            )
        finally:
            await target_engine_obj.dispose()
        attestation_engine = migrator_engine()
        try:
            attestation = await attest_schema(attestation_engine)
        finally:
            await attestation_engine.dispose()
        assert_runtime_coordinates_match(target_identity, attestation["target_identity"])
        restored_value = os.environ.get(RESTORED_SOURCE_URL_ENV)
        if not restored_value:
            raise CutoverError(
                f"{RESTORED_SOURCE_URL_ENV} is required to verify the full source dump restore"
            )
        restored_engine = restored_source_engine(restored_value)
        try:
            await verify_restored_source(
                restored_engine, snapshot.source_inventory, source_identity
            )
        finally:
            await restored_engine.dispose()
        manifest = build_manifest(
            snapshot=snapshot,
            transformed=transformed,
            target_snapshot=target_snapshot,
            source_identity=source_identity,
            schema_attestation=attestation,
            target_host_name=target_host(target),
            target_identity=attestation["target_identity"],
            source_dump_sha256=dump_digest,
        )
        digest = write_manifest(args.write_manifest, manifest)
        print(f"draft_manifest digest={digest} path={args.write_manifest}")
        return 0
    finally:
        await source.dispose()


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
