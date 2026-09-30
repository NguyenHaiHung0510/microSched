"""Encrypted PostgreSQL frame with compare-and-swap for the local probe only.

No setup is performed on import or connection. The explicit schema preparation
command, graph cleanup and retention integration are separate probe work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg
from sqlalchemy.engine import make_url

from app.agent.crypto import create_wrapped_dek, open_content, seal_content, unwrap_dek
from app.agent.workflow_probe.contracts import ProbeBlocked, encode_frame

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
        decoded = json.loads(
            open_content(
                unwrap_dek(row["wrapped_dek"]),
                row["content"],
                aad=frame_aad(run_id, row["generation"], row["revision"]),
            )
        )
        if not isinstance(decoded, dict):
            raise ProbeBlocked("invalid_frame_shape")
        _validate_content(decoded, row["phase"])
        return StoredFrame(
            run_id,
            owner,
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
                row = await connection.fetchrow(
                    "SELECT wrapped_dek FROM mimi_probe_068.run "
                    "WHERE id=$1 AND owner_ref=$2 AND generation=$3 AND revision=$4 FOR UPDATE",
                    previous.run_id,
                    previous.owner,
                    previous.generation,
                    previous.revision,
                )
                if row is None:
                    raise ProbeBlocked("stale_frame_revision")
                revision = previous.revision + 1
                ciphertext = seal_content(
                    unwrap_dek(row["wrapped_dek"]),
                    encoded,
                    aad=frame_aad(previous.run_id, previous.generation, revision),
                )
                await connection.execute(
                    "UPDATE mimi_probe_068.run SET phase=$2,revision=$3,content=$4 WHERE id=$1",
                    previous.run_id,
                    phase,
                    revision,
                    ciphertext,
                )
        finally:
            await connection.close()
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
