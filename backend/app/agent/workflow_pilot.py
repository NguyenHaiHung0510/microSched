"""Default-off local B16 bridge: actual public Tasks and atomic workflow receipts."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import asyncpg
from sqlalchemy.engine import make_url

from app.agent.workflow_probe.contracts import Preview, ProbeBlocked, Record
from app.agent.workflow_probe.engines import run_control, run_graph
from app.agent.workflow_probe.store import PgFrameStore, StoredFrame
from app.agent.workflow_probe.workflow import STOPPED, ConfirmationContent, Content, Workflow

PILOT_DATABASE = "microsched_p1ca_068_pilot073"
POLICY = "local-public-task-prefix-073-v1"
SOURCE_DDL = """
CREATE TABLE IF NOT EXISTS mimi_probe_068.task_source (
    run_id uuid NOT NULL REFERENCES mimi_probe_068.run(id) ON DELETE CASCADE,
    task_id uuid NOT NULL,
    fingerprint char(64) NOT NULL,
    PRIMARY KEY(run_id,task_id)
);
GRANT SELECT,INSERT,UPDATE,DELETE ON mimi_probe_068.task_source TO microsched_app;
CREATE TABLE IF NOT EXISTS mimi_probe_068.task_request (
    id uuid PRIMARY KEY,
    owner_ref varchar(64) NOT NULL,
    engine text NOT NULL,
    selection_hash char(64) NOT NULL
);
GRANT SELECT,INSERT ON mimi_probe_068.task_request TO microsched_app;
"""


def pilot_available(settings) -> bool:
    if settings.app_env != "local" or not settings.mimi_workflow_pilot_enabled:
        return False
    try:
        url = make_url(settings.database_url or "")
        return (
            url.host in {"localhost", "127.0.0.1"}
            and url.port is not None
            and url.database == PILOT_DATABASE
            and url.username == "microsched_app"
            and not url.query
        )
    except Exception:
        return False


def fingerprint(row) -> str:
    # JSONB includes updated_at and all Task fields; no narrow integer hash/version.
    return hashlib.sha256(row["source_json"].encode()).hexdigest()


async def selected_tasks(connection, ids: list[UUID], *, lock: bool = False, share: bool = False):
    if not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids):
        raise ProbeBlocked("selection_budget_exceeded")
    rows = await connection.fetch(
        "SELECT t.id,t.title,to_jsonb(t)::text AS source_json FROM microsched.task t "
        "WHERE t.id=ANY($1::uuid[]) AND NOT t.is_private AND t.deleted_at IS NULL "
        "ORDER BY t.id" + (" FOR UPDATE" if lock else (" FOR SHARE" if share else "")),
        ids,
    )
    if len(rows) != len(ids):
        raise ProbeBlocked("public_source_required")
    return rows


class TaskFrameStore(PgFrameStore):
    def __init__(self, database_url: str, provider=None):
        if make_url(database_url).database != PILOT_DATABASE:
            raise ProbeBlocked("exclusive_pilot_database_required")
        super().__init__(database_url)
        self.provider = provider

    @asynccontextmanager
    async def invocation(self, run_id: UUID):
        connection = await asyncpg.connect(self._dsn)
        key = int.from_bytes(hashlib.sha256(run_id.bytes).digest()[:8], signed=True)
        held = False
        try:
            held = await connection.fetchval("SELECT pg_try_advisory_lock($1)", key)
            if not held:
                raise ProbeBlocked("run_busy")
            yield
        finally:
            if held:
                await connection.execute("SELECT pg_advisory_unlock($1)", key)
            await connection.close()

    async def create_task_run(self, run_id: UUID, owner: str, engine: str, ids: list[UUID]):
        connection = await asyncpg.connect(self._dsn)
        try:
            rows = await selected_tasks(connection, ids)
            workflow = PilotWorkflow(self, run_id, owner, policy=POLICY)
            await workflow.create(
                "task", engine, tuple(Record(str(row["id"]), 1, row["title"]) for row in rows)
            )
            return workflow
        finally:
            await connection.close()

    async def initialize_domain_on(self, connection, run_id, owner, engine, records):
        if await connection.fetchval("SELECT count(*) FROM mimi_probe_068.task_request") >= 128:
            raise ProbeBlocked("pilot_identity_quota_exceeded")
        ids = [UUID(record.record_id) for record in records]
        rows = await selected_tasks(connection, ids, share=True)
        if {str(row["id"]): row["title"] for row in rows} != {
            record.record_id: record.title for record in records
        }:
            raise ProbeBlocked("source_requires_repreview")
        await connection.execute(
            "INSERT INTO mimi_probe_068.task_request VALUES($1,$2,$3,$4)",
            run_id,
            owner,
            engine,
            selection_hash(ids),
        )
        for row in rows:
            await connection.execute(
                "INSERT INTO mimi_probe_068.task_source VALUES($1,$2,$3)",
                run_id,
                row["id"],
                fingerprint(row),
            )

    async def existing_request(self, run_id, owner, engine, ids):
        connection = await asyncpg.connect(self._dsn)
        try:
            row = await connection.fetchrow(
                "SELECT * FROM mimi_probe_068.task_request WHERE id=$1", run_id
            )
            if row is None:
                return False
            if row["owner_ref"] != owner:
                raise ProbeBlocked("owned_run_not_found")
            if row["engine"] != engine or row["selection_hash"] != selection_hash(ids):
                raise ProbeBlocked("idempotency_scope_mismatch")
            if not await connection.fetchval(
                "SELECT 1 FROM mimi_probe_068.run WHERE id=$1", run_id
            ):
                raise ProbeBlocked("run_retired")
            return True
        finally:
            await connection.close()

    @asynccontextmanager
    async def public_context(self, frame, *, completed=False):
        connection = await asyncpg.connect(self._dsn)
        try:
            async with connection.transaction():
                bindings = await connection.fetch(
                    "SELECT task_id,fingerprint FROM mimi_probe_068.task_source WHERE run_id=$1",
                    frame.run_id,
                )
                if not bindings:
                    raise ProbeBlocked("source_requires_repreview")
                try:
                    rows = await selected_tasks(
                        connection, [r["task_id"] for r in bindings], share=True
                    )
                except ProbeBlocked:
                    raise ProbeBlocked("source_requires_repreview") from None
                if not completed and {r["id"]: fingerprint(r) for r in rows} != {
                    r["task_id"]: r["fingerprint"] for r in bindings
                }:
                    raise ProbeBlocked("source_requires_repreview")
                # Protect the public snapshot through egress/materialization; privacy updates wait.
                yield
        finally:
            await connection.close()

    async def apply_domain_on(self, connection, frame: StoredFrame, preview: Preview) -> None:
        ids = [UUID(source.record_id) for source in preview.sources]
        try:
            rows = await selected_tasks(connection, ids, lock=True)
        except ProbeBlocked:
            raise ProbeBlocked("source_requires_repreview") from None
        expected = await connection.fetch(
            "SELECT task_id,fingerprint FROM mimi_probe_068.task_source WHERE run_id=$1",
            frame.run_id,
        )
        if {row["id"]: fingerprint(row) for row in rows} != {
            row["task_id"]: row["fingerprint"] for row in expected
        }:
            raise ProbeBlocked("source_requires_repreview")
        if {str(row["id"]): row["title"] for row in rows} != {
            source.record_id: source.title for source in preview.sources
        }:
            raise ProbeBlocked("source_requires_repreview")
        if await connection.fetchval("SELECT clock_timestamp()") >= frame.expires_at:
            raise ProbeBlocked("run_expired")
        for task_id, title in preview.operations:
            await connection.execute(
                "UPDATE microsched.task SET title=$2 WHERE id=$1", UUID(task_id), title
            )

    async def owned_runs(self, owner: str):
        connection = await asyncpg.connect(self._dsn)
        try:
            rows = await connection.fetch(
                "SELECT id FROM mimi_probe_068.run WHERE owner_ref=$1 "
                "ORDER BY created_at DESC,id DESC LIMIT 24",
                owner,
            )
        finally:
            await connection.close()
        return [row["id"] for row in rows]

    async def choices(self):
        connection = await asyncpg.connect(self._dsn)
        try:
            rows = await connection.fetch(
                "SELECT id,title FROM microsched.task WHERE NOT is_private "
                "AND deleted_at IS NULL ORDER BY created_at DESC,id DESC LIMIT 100"
            )
            return [{"id": str(row["id"]), "title": row["title"]} for row in rows]
        finally:
            await connection.close()


async def status_view(workflow: Workflow):
    frame = await workflow.store.load(workflow.run_id, owner=workflow.owner)
    body = Content.model_validate(frame.content)
    phase, reason = frame.phase, body.stop_reason
    if phase not in STOPPED:
        if datetime.now(UTC) >= frame.expires_at:
            phase, reason = "expired", "expired"
        elif body.policy != workflow.policy or body.contract_hash != workflow.contract_hash:
            phase, reason = "repreview", "policy_requires_repreview"
    status = {
        "run_id": str(frame.run_id),
        "generation": frame.generation,
        "phase": phase,
        "schema_version": body.schema_version,
        "draft": body.draft,
        "preview": body.preview.model_dump() if body.preview else None,
        "preview_digest": body.preview.preview().digest if body.preview else None,
        "receipt": body.receipt,
        "stop_reason": reason,
        "provider_calls": len(body.provider_calls),
        "events": body.events,
    }
    try:
        async with workflow.store.public_context(frame, completed=frame.phase == "succeeded"):
            pass
    except ProbeBlocked:
        status.update(
            draft="", preview=None, preview_digest=None, stop_reason="source_requires_repreview"
        )
        if phase not in {"succeeded", "expired", "cancelled"}:
            status["phase"] = "repreview"
    return {
        **status,
        "engine": frame.engine,
        "provider_mode": "live" if "pilot_provider_live" in body.events else "deterministic",
    }


def selection_hash(ids):
    return hashlib.sha256(json.dumps(sorted(map(str, ids))).encode()).hexdigest()


class PilotWorkflow(Workflow):
    async def provider(self, frame, body, step):
        if not self.store.provider:
            try:
                async with self.store.public_context(frame):
                    return await super().provider(frame, body, step)
            except ProbeBlocked as error:
                if str(error) != "source_requires_repreview":
                    raise
                body.stop_reason = str(error)
                frame = await self.store.save(frame, phase="repreview", content=self.wire(body))
                return frame, body, None
        existing = next((call for call in body.provider_calls if call.step == step), None)
        if existing:
            if existing.status == "terminal":
                return frame, body, existing.result
            body.stop_reason = "provider_outcome_unknown"
            frame = await self.store.save(frame, phase="reconcile", content=self.wire(body))
            return frame, body, None
        from app.agent.workflow_probe.workflow import Call

        try:
            async with self.store.public_context(frame):
                call = Call(step=step, status="dispatched")
                body.provider_calls.append(call)
                if "pilot_provider_live" not in body.events:
                    body.events.append("pilot_provider_live")
                frame = await self.store.save(frame, phase=frame.phase, content=self.wire(body))
                result = await self.store.provider(step, body, frame)
        except ProbeBlocked:
            body.stop_reason = "source_requires_repreview"
            frame = await self.store.save(frame, phase="repreview", content=self.wire(body))
            return frame, body, None
        except Exception:
            body.stop_reason = "provider_outcome_unknown"
            frame = await self.store.save(frame, phase="reconcile", content=self.wire(body))
            return frame, body, None
        call.result, call.status = result, "terminal"
        frame = await self.store.save(frame, phase=frame.phase, content=self.wire(body))
        return frame, body, result

    async def _step(self, expected):
        if expected == "materialize":
            frame, body = await self.load()
            if frame.phase == expected:
                try:
                    async with self.store.public_context(frame):
                        return await super()._step(expected)
                except ProbeBlocked as error:
                    if str(error) != "source_requires_repreview":
                        raise
                    body.confirmation = None
                    body.stop_reason = str(error)
                    await self.store.save(frame, phase="repreview", content=self.wire(body))
                    return "repreview"
        if expected != "group" or not self.store.provider:
            return await super()._step(expected)
        frame, body = await self.load()
        if frame.phase != expected:
            return await super()._step(expected)
        frame, body, result = await self.provider(frame, body, expected)
        if result is None:
            return frame.phase
        try:
            groups = json.loads(result)
            if (
                not isinstance(groups, list)
                or not groups
                or any(not isinstance(group, list) or not group for group in groups)
            ):
                raise ValueError("invalid_partition")
            ids = [item for group in groups for item in group]
            if len(ids) != len(body.snapshot) or set(ids) != {s.id for s in body.snapshot}:
                raise ValueError("invalid_partition")
        except ValueError, TypeError:
            body.stop_reason = "provider_partition_invalid"
            await self.store.save(frame, phase="reconcile", content=self.wire(body))
            return "reconcile"
        body.groups = groups
        body.events.append("group")
        await self.store.save(frame, phase="draft", content=self.wire(body))
        return "draft"


async def advance(
    workflow: Workflow, *, generation: int, direction=None, digest=None, cancel=False, resume=False
):
    frame, body = await workflow.load()
    if frame.generation != generation:
        raise ProbeBlocked("input_generation_mismatch")
    if cancel:
        if frame.phase in {"succeeded", "expired", "cancelled"}:
            raise ProbeBlocked("input_phase_mismatch")
        body.stop_reason = (
            "owner_cancelled_provider_unknown"
            if any(call.status == "dispatched" for call in body.provider_calls)
            else "owner_cancelled"
        )
        body.confirmation = None
        await workflow.store.save(frame, phase="cancelled", content=workflow.wire(body))
        return await status_view(workflow)
    if frame.phase == "succeeded" and digest == (body.receipt or {}).get("digest"):
        return await status_view(workflow)
    if resume:
        if frame.phase not in {"query", "group", "draft", "materialize", "execute"}:
            raise ProbeBlocked("input_phase_mismatch")
    else:
        await workflow.accept(
            generation=generation,
            direction=direction,
            confirmation=ConfirmationContent(
                owner=workflow.owner, generation=generation, preview_digest=digest
            )
            if digest is not None
            else None,
        )
    await (run_graph(workflow) if frame.engine == "graph" else run_control(workflow))
    return await status_view(workflow)


async def create(store: TaskFrameStore, run_id: UUID, owner: str, engine: str, ids: list[UUID]):
    if await store.existing_request(run_id, owner, engine, ids):
        return await status_view(PilotWorkflow(store, run_id, owner, policy=POLICY))
    await store.cleanup(now=datetime.now(UTC))
    try:
        workflow = await store.create_task_run(run_id, owner, engine, ids)
    except asyncpg.UniqueViolationError:
        await store.existing_request(run_id, owner, engine, ids)
        return await status_view(PilotWorkflow(store, run_id, owner, policy=POLICY))
    await (run_graph(workflow) if engine == "graph" else run_control(workflow))
    return await status_view(workflow)
