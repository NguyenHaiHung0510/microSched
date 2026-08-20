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
EXPECTED_ALEMBIC_REVISION = "0009"
SOURCE_DB_NAME = "microschedule_v2"
SOURCE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", "db"})
TARGET_APP_ROLE = "microsched_app"
TARGET_MIGRATOR_ROLES = frozenset({"microsched_migrator", "neondb_owner"})
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
    """Build a read-only Fly status probe; tests inject a synthetic equivalent."""
    command = os.environ.get(FLY_STATE_COMMAND_ENV)
    app = os.environ.get(FLY_APP_ENV)
    if not command or not app:
        raise CutoverError(f"{FLY_STATE_COMMAND_ENV} and {FLY_APP_ENV} are required for recovery")
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
        if not isinstance(value, dict):
            raise CutoverError("current Fly stopped-state query returned invalid JSON")
        return value

    return verify


async def assert_current_fly_stopped(
    verifier: Callable[[], Awaitable[Mapping[str, Any]]] | Callable[[], Mapping[str, Any]],
) -> Mapping[str, Any]:
    try:
        result = verifier()
        state = await result if inspect.isawaitable(result) else result
    except CutoverError:
        raise
    except Exception:
        raise CutoverError("current Fly stopped-state query failed") from None
    if (
        not isinstance(state, Mapping)
        or state.get("sole_machine_stopped") is not True
        or state.get("never_restarted") is not True
    ):
        raise CutoverError("current Fly state is not sole-machine stopped and never-restarted")
    return state


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
                    "column_default,udt_name "
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
    ddl = {
        "columns": [_catalog_row(item) for item in columns],
        "constraints": [_catalog_row(item) for item in constraints],
        "triggers": [_catalog_row(item) for item in triggers],
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
    keys = ("database", "server_addr", "server_port", "cluster_name", "ddl_sha256")
    if any(actual.get(key) != expected.get(key) for key in keys):
        raise CutoverError("database identity or DDL fingerprint drift")


def assert_runtime_coordinates_match(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    keys = ("database", "server_addr", "server_port", "cluster_name")
    if any(actual.get(key) != expected.get(key) for key in keys):
        raise CutoverError("target runtime database coordinates drift")


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
                            "acl.privilege_type "
                            "FROM pg_catalog.pg_class c "
                            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                            "JOIN LATERAL aclexplode(COALESCE(c.relacl, "
                            "acldefault('r', c.relowner))) acl ON true "
                            "JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee "
                            "WHERE n.nspname='microsched' "
                            "ORDER BY c.relname,r.rolname,acl.privilege_type"
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
    columns_by_table: dict[str, set[str]] = {}
    for column in identity["ddl"]["columns"]:
        columns_by_table.setdefault(column["table_name"], set()).add(column["column_name"])
    expected_columns = {component: set(fields) for component, fields in TARGET_FIELDS.items()}
    expected_columns["alembic_version"] = {"version_num"}
    for table_name, expected in expected_columns.items():
        if columns_by_table.get(table_name) != expected:
            raise CutoverError(f"target catalog columns drift: {table_name}")
    constraint_rows = identity["ddl"]["constraints"]
    primary_key_tables = {
        row["table_name"] for row in constraint_rows if row["constraint_type"] == "p"
    }
    if not set(ALL_EXPECTED_TARGET_TABLES) <= primary_key_tables:
        raise CutoverError("target catalog primary-key contract drift")
    trigger_rows = identity["ddl"]["triggers"]
    trigger_tables = {
        row["table_name"] for row in trigger_rows if row["trigger_name"] == "set_updated_at"
    }
    if trigger_tables != set(ALL_EXPECTED_TARGET_TABLES):
        raise CutoverError("target catalog updated-at trigger contract drift")
    grant_rows = [dict(row) for row in grants]
    app_grants = {
        (row["table_name"], row["privilege_type"])
        for row in grant_rows
        if row["grantee"] == TARGET_APP_ROLE
    }
    for table_name in ALL_EXPECTED_TARGET_TABLES:
        if not all(
            (table_name, privilege) in app_grants
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
        ):
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
    if not isinstance(target_state, dict) or target_state.get("sole_machine_stopped") is not True:
        raise ManifestError("failure receipt lacks sole-machine stopped current state")
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
    if fly_state_verifier is None:
        raise CutoverError("current Fly stopped-state verifier is required for recovery")
    for component in MAPPED_COMPONENTS:
        transformed_rows = list(transformed.get(component, []))
        if inventory(component, transformed_rows) != manifest["source_expected"][component]:
            raise ManifestError(f"recovery source drift: {component}")
        if sorted(str(row["id"]) for row in transformed_rows) != sorted(
            manifest["expected_ids"][component]
        ):
            raise ManifestError(f"recovery source ID set drift: {component}")
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
            await assert_current_fly_stopped(fly_state_verifier)
            await purge_import_assert(session, manifest, transformed)


async def run_verify(manifest: Mapping[str, Any], engine: AsyncEngine) -> dict[str, Any]:
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
    for component in PURGE_ONLY_COMPONENTS:
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
