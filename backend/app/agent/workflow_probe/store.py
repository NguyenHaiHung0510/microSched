"""Encrypted PostgreSQL frame with compare-and-swap for the local probe only.

No setup is performed on import or connection. The explicit schema preparation
command, graph cleanup and retention integration are separate probe work.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg
from sqlalchemy.engine import make_url

from app.agent.crypto import create_wrapped_dek, open_content, seal_content, unwrap_dek
from app.agent.workflow_probe.contracts import (
    Confirmation,
    Preview,
    ProbeBlocked,
    Record,
    authorize_confirmation,
    encode_frame,
)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
TERMINAL_PHASES = {"succeeded", "expired", "cancelled"}
PHASES = TERMINAL_PHASES | {
    "query",
    "group",
    "draft",
    "direction",
    "materialize",
    "confirmation",
    "execute",
    "reconcile",
    "repreview",
}


def local_probe_dsn(value: str, *, setup: bool = False) -> str:
    url = make_url(value)
    expected_role = "postgres" if setup else "microsched_app"
    if (
        url.host not in LOCAL_HOSTS
        or url.port is None
        or not (url.database or "").startswith("microsched_p1ca_068")
        or url.username != expected_role
        or url.query
    ):
        raise ProbeBlocked("local_probe_database_required")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def frame_aad(run_id: UUID, generation: int, revision: int) -> str:
    return f"mimi-probe-068:{run_id}:g{generation}:r{revision}:frame"


def record_aad(run_id: UUID, record_id: str, version: int) -> str:
    return f"mimi-probe-068:{run_id}:record:{record_id}:v{version}"


def checkpoint_thread(run_id: UUID, generation: int) -> str:
    return f"mimi-probe-068:{run_id}:g{generation}"


@dataclass(frozen=True)
class StoredFrame:
    run_id: UUID
    owner: str
    generation: int
    engine: str
    phase: str
    revision: int
    expires_at: datetime
    content: dict[str, object]


def _validate_content(content: dict[str, object], phase: str) -> str:
    if phase not in PHASES:
        raise ProbeBlocked("unsupported_phase")
    for key, cap in (("events", 32), ("provider_calls", 8)):
        values = content.get(key, [])
        if not isinstance(values, list) or len(values) > cap:
            raise ProbeBlocked(f"{key}_budget_exceeded")
    return encode_frame(content)


class PgFrameStore:
    """App role only, one connection per operation; credentials are never logged."""

    def __init__(self, database_url: str):
        self._dsn = local_probe_dsn(database_url)

    async def create(
        self,
        run_id: UUID,
        *,
        owner: str,
        generation: int,
        engine: str,
        content: dict[str, object],
        now: datetime,
        expires_at: datetime,
        records: tuple[Record, ...] = (),
    ) -> StoredFrame:
        if (
            not owner
            or type(generation) is not int
            or generation < 1
            or engine not in {"control", "graph"}
            or now.tzinfo is None
            or expires_at.tzinfo is None
            or not 0 < (expires_at - now).total_seconds() <= 86400
        ):
            raise ProbeBlocked("invalid_run_identity_or_expiry")
        encoded = _validate_content(content, "query")
        if (
            len(records) > 16
            or len({r.record_id for r in records}) != len(records)
            or any(
                not isinstance(r.record_id, str)
                or not r.record_id
                or type(r.version) is not int
                or r.version < 1
                or not isinstance(r.title, str)
                for r in records
            )
        ):
            raise ProbeBlocked("invalid_source_selection")
        encode_frame(
            {
                "records": [
                    {"id": r.record_id, "version": r.version, "title": r.title} for r in records
                ]
            }
        )
        wrapped = create_wrapped_dek()
        ciphertext = seal_content(
            unwrap_dek(wrapped), encoded, aad=frame_aad(run_id, generation, 0)
        )
        connection = await asyncpg.connect(self._dsn)
        try:
            async with connection.transaction():
                # Admission is serialized, so two new runs cannot both take slot eight.
                await connection.execute("SELECT pg_advisory_xact_lock(68068)")
                active = await connection.fetchval(
                    "SELECT count(*) FROM mimi_probe_068.run "
                    "WHERE engine=$1 AND phase NOT IN ('succeeded','expired','cancelled')",
                    engine,
                )
                if active >= 8:
                    raise ProbeBlocked("active_quota_exceeded")
                terminal = await connection.fetchval(
                    "SELECT count(*) FROM mimi_probe_068.run WHERE engine=$1 "
                    "AND phase IN ('succeeded','expired','cancelled')",
                    engine,
                )
                if terminal > 16:
                    raise ProbeBlocked("terminal_cleanup_required")
                await connection.execute(
                    "INSERT INTO mimi_probe_068.run "
                    "(id,owner_ref,generation,engine,phase,revision,expires_at,"
                    "wrapped_dek,content) "
                    "VALUES($1,$2,$3,$4,'query',0,$5,$6,$7)",
                    run_id,
                    owner,
                    generation,
                    engine,
                    expires_at,
                    wrapped,
                    ciphertext,
                )
                for record in records:
                    await connection.execute(
                        "INSERT INTO mimi_probe_068.record VALUES($1,$2,$3,$4)",
                        run_id,
                        record.record_id,
                        record.version,
                        seal_content(
                            unwrap_dek(wrapped),
                            record.title,
                            aad=record_aad(run_id, record.record_id, record.version),
                        ),
                    )
                await self.initialize_domain_on(connection, run_id, owner, engine, records)
        finally:
            await connection.close()
        return StoredFrame(run_id, owner, generation, engine, "query", 0, expires_at, content)

    async def load(self, run_id: UUID, *, owner: str) -> StoredFrame:
        connection = await asyncpg.connect(self._dsn)
        try:
            row = await connection.fetchrow(
                "SELECT * FROM mimi_probe_068.run WHERE id=$1 AND owner_ref=$2", run_id, owner
            )
        finally:
            await connection.close()
        if row is None:
            raise ProbeBlocked("owned_run_not_found")
        return self._decode(row)

    @staticmethod
    def _decode(row) -> StoredFrame:
        decoded = json.loads(
            open_content(
                unwrap_dek(row["wrapped_dek"]),
                row["content"],
                aad=frame_aad(row["id"], row["generation"], row["revision"]),
            )
        )
        if not isinstance(decoded, dict):
            raise ProbeBlocked("invalid_frame_shape")
        _validate_content(decoded, row["phase"])
        return StoredFrame(
            row["id"],
            row["owner_ref"],
            row["generation"],
            row["engine"],
            row["phase"],
            row["revision"],
            row["expires_at"],
            decoded,
        )

    async def save(
        self, previous: StoredFrame, *, phase: str, content: dict[str, object]
    ) -> StoredFrame:
        encoded = _validate_content(content, phase)
        connection = await asyncpg.connect(self._dsn)
        try:
            async with connection.transaction():
                result = await self._save_on(connection, previous, phase, content, encoded)
        finally:
            await connection.close()
        return result

    async def _save_on(
        self, connection, previous, phase, content, encoded=None, *, prune_terminal=True
    ):
        if phase in TERMINAL_PHASES:
            await connection.execute("SELECT pg_advisory_xact_lock(68068)")
        row = await connection.fetchrow(
            "SELECT wrapped_dek,phase,engine FROM mimi_probe_068.run "
            "WHERE id=$1 AND owner_ref=$2 AND generation=$3 AND revision=$4 FOR UPDATE",
            previous.run_id,
            previous.owner,
            previous.generation,
            previous.revision,
        )
        if row is None:
            raise ProbeBlocked("stale_frame_revision")
        if row["phase"] in TERMINAL_PHASES:
            raise ProbeBlocked("terminal_frame_frozen")
        revision = previous.revision + 1
        ciphertext = seal_content(
            unwrap_dek(row["wrapped_dek"]),
            encoded or _validate_content(content, phase),
            aad=frame_aad(previous.run_id, previous.generation, revision),
        )
        await connection.execute(
            "UPDATE mimi_probe_068.run SET phase=$2,revision=$3,content=$4,"
            "completed_at=CASE WHEN $2 IN ('succeeded','expired','cancelled') "
            "THEN clock_timestamp() ELSE NULL END WHERE id=$1",
            previous.run_id,
            phase,
            revision,
            ciphertext,
        )
        if phase in TERMINAL_PHASES and prune_terminal:
            await self._prune_terminal_on(
                connection, engines=(row["engine"],), keep_run=previous.run_id
            )
        return StoredFrame(
            previous.run_id,
            previous.owner,
            previous.generation,
            previous.engine,
            phase,
            revision,
            previous.expires_at,
            content,
        )

    async def records(self, frame: StoredFrame) -> tuple[Record, ...]:
        connection = await asyncpg.connect(self._dsn)
        try:
            wrapped = await connection.fetchval(
                "SELECT wrapped_dek FROM mimi_probe_068.run WHERE id=$1 AND owner_ref=$2",
                frame.run_id,
                frame.owner,
            )
            if wrapped is None:
                raise ProbeBlocked("owned_run_not_found")
            rows = await connection.fetch(
                "SELECT * FROM mimi_probe_068.record WHERE run_id=$1 ORDER BY id", frame.run_id
            )
            key = unwrap_dek(wrapped)
            return tuple(
                Record(
                    r["id"],
                    r["version"],
                    open_content(
                        key, r["title"], aad=record_aad(frame.run_id, r["id"], r["version"])
                    ),
                )
                for r in rows
            )
        finally:
            await connection.close()

    async def fake_dispatch(self, frame: StoredFrame, step: str) -> None:
        """Synthetic external-effect counter: a duplicate raises, never hides retries."""
        connection = await asyncpg.connect(self._dsn)
        try:
            await connection.execute(
                "INSERT INTO mimi_probe_068.dispatch VALUES($1,$2)", frame.run_id, step
            )
        finally:
            await connection.close()

    async def execute(
        self,
        previous: StoredFrame,
        preview: Preview,
        confirmation: Confirmation,
        *,
        policy: str,
        now: datetime,
        fault: Callable[[str], Awaitable[None]] | None = None,
    ) -> StoredFrame:
        """Lock sources, authorize exact scope, and commit mutations+receipt+frame atomically."""
        connection = await asyncpg.connect(self._dsn)
        try:
            async with connection.transaction():
                # Same lock order as admission/cleanup, before locking the run row.
                await connection.execute("SELECT pg_advisory_xact_lock(68068)")
                row = await connection.fetchrow(
                    "SELECT * FROM mimi_probe_068.run WHERE id=$1 AND owner_ref=$2 FOR UPDATE",
                    previous.run_id,
                    previous.owner,
                )
                if row is None:
                    raise ProbeBlocked("owned_run_not_found")
                current = self._decode(row)
                if current.phase == "succeeded":
                    digest = await connection.fetchval(
                        "SELECT digest FROM mimi_probe_068.receipt WHERE run_id=$1", current.run_id
                    )
                    if (
                        confirmation.owner != current.owner
                        or confirmation.generation != (current.generation)
                        or confirmation.preview_digest != digest
                    ):
                        raise ProbeBlocked("confirmation_mismatch")
                    return current
                if current.phase != "execute" or current.revision != previous.revision:
                    raise ProbeBlocked("execution_transition_invalid")
                if preview.authority_ref != current.content["authority_ref"]:
                    raise ProbeBlocked("preview_instance_mismatch")
                if current.content.get("preview") != preview.content() or (
                    preview.owner != current.owner or preview.generation != current.generation
                ):
                    raise ProbeBlocked("frozen_preview_mismatch")
                if current.content.get("confirmation") != {
                    "owner": confirmation.owner,
                    "generation": confirmation.generation,
                    "preview_digest": confirmation.preview_digest,
                }:
                    raise ProbeBlocked("persisted_confirmation_required")
                rows = await connection.fetch(
                    "SELECT id,version FROM mimi_probe_068.record WHERE run_id=$1 "
                    "ORDER BY id FOR UPDATE",
                    current.run_id,
                )
                operations = authorize_confirmation(
                    preview,
                    confirmation,
                    source_versions={r["id"]: r["version"] for r in rows},
                    policy=policy,
                    now=now,
                    expires_at=current.expires_at,
                )
                await self.apply_domain_on(connection, current, preview)
                key = unwrap_dek(row["wrapped_dek"])
                versions = {r["id"]: r["version"] for r in rows}
                for record_id, title in operations:
                    version = versions[record_id] + 1
                    await connection.execute(
                        "UPDATE mimi_probe_068.record SET version=$3,title=$4 "
                        "WHERE run_id=$1 AND id=$2",
                        current.run_id,
                        record_id,
                        version,
                        seal_content(
                            key, title, aad=record_aad(current.run_id, record_id, version)
                        ),
                    )
                receipt = {"digest": preview.digest, "changed": len(operations)}
                await connection.execute(
                    "INSERT INTO mimi_probe_068.receipt VALUES($1,$2,$3)",
                    current.run_id,
                    preview.digest,
                    seal_content(key, encode_frame(receipt), aad=f"probe-receipt:{current.run_id}"),
                )
                body = dict(current.content)
                body["receipt"] = receipt
                body["events"] = list(body.get("events", [])) + ["executed"]
                if body.get("active_started_at"):
                    body["active_seconds"] = min(
                        120.0,
                        body["active_seconds"]
                        + max(
                            0,
                            (
                                now - datetime.fromisoformat(body["active_started_at"])
                            ).total_seconds(),
                        ),
                    )
                    body["active_started_at"] = None
                result = await self._save_on(connection, current, "succeeded", body)
                if fault:
                    await fault("before_commit")
            if fault:
                await fault("after_commit")
            return result
        finally:
            await connection.close()

    async def apply_domain_on(self, connection, frame: StoredFrame, preview: Preview) -> None:
        """Optional domain integration, inside the same authorized receipt transaction."""

    async def initialize_domain_on(self, connection, run_id, owner, engine, records) -> None:
        """Optional source binding, atomic with initial frame admission."""

    async def cleanup(self, *, now: datetime) -> dict[str, int]:
        """Finite expiry/pruning, including exact graph threads in the same PG transaction."""
        connection = await asyncpg.connect(self._dsn)
        expired = pruned = 0
        try:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock(68068)")
                rows = await connection.fetch(
                    "SELECT * FROM mimi_probe_068.run WHERE expires_at<=$1 "
                    "AND phase NOT IN ('succeeded','expired','cancelled') LIMIT 16 FOR UPDATE",
                    now,
                )
                for row in rows:
                    frame = self._decode(row)
                    body = dict(frame.content)
                    body["stop_reason"] = "expired"
                    await self._save_on(connection, frame, "expired", body, prune_terminal=False)
                    expired += 1
                pruned = await self._prune_terminal_on(connection)
            return {"expired": expired, "pruned": pruned}
        finally:
            await connection.close()

    async def _prune_terminal_on(
        self, connection, *, engines=("control", "graph"), keep_run=None
    ) -> int:
        """Caller holds admission lock; terminal frame and pruning commit together."""
        tables = ["checkpoint_writes", "checkpoint_blobs", "checkpoints"]
        present = [
            await connection.fetchval("SELECT to_regclass($1)", f"public.{t}") for t in tables
        ]
        if any(present) and not all(present):
            raise ProbeBlocked("checkpoint_cleanup_schema_incomplete")
        pruned = 0
        for engine in engines:
            # Always retain the frame being completed, including timestamp ties.
            exclusion = "AND id<>$2 " if keep_run is not None else ""
            retained_others = 15 if keep_run is not None else 16
            args = (engine, keep_run) if keep_run is not None else (engine,)
            victims = await connection.fetch(
                "SELECT id,generation FROM mimi_probe_068.run WHERE engine=$1 "
                "AND phase IN ('succeeded','expired','cancelled') "
                + exclusion
                + f"ORDER BY completed_at DESC,id DESC OFFSET {retained_others} "
                "LIMIT 64 FOR UPDATE",
                *args,
            )
            for victim in victims:
                if all(present):
                    thread = checkpoint_thread(victim["id"], victim["generation"])
                    for table in tables:
                        await connection.execute(
                            f"DELETE FROM public.{table} WHERE thread_id=$1", thread
                        )
                await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=$1", victim["id"])
                pruned += 1
        return pruned
