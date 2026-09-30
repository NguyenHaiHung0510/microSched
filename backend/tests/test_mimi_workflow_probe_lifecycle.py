import asyncio
import os
import selectors
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import ValidationError

from app.agent.workflow_probe.contracts import Confirmation, ProbeBlocked, Record
from app.agent.workflow_probe.engines import run_control, run_graph, validate_refs
from app.agent.workflow_probe.store import PgFrameStore, checkpoint_thread, local_probe_dsn
from app.agent.workflow_probe.workflow import ConfirmationContent, Content, Workflow
from app.core import crypto


def test_schema_errors_do_not_disclose_private_frame_content():
    with pytest.raises(ValidationError) as error:
        Content.model_validate({"malformed": "PRIVATE_FRAME_MARKER"})
    assert "PRIVATE_FRAME_MARKER" not in str(error.value)


def test_graph_reference_guard_rejects_identity_version_and_content_channels():
    expected = {
        "run_id": "opaque",
        "generation": 1,
        "state_schema_version": 2,
        "policy_hash": "frozen-policy",
        "contract_hash": "frozen-handler-contract",
        "cursor": "query",
    }
    for changes in [
        {"run_id": "foreign"},
        {"generation": True},
        {"state_schema_version": 3},
        {"draft": "sensitive"},
    ]:
        with pytest.raises(ValueError):
            validate_refs(expected | changes, expected)


@pytest.fixture
def probe_database(monkeypatch):
    value = os.environ.get("MIMI_WORKFLOW_PROBE_APP_URL")
    if not value:
        pytest.skip("dedicated local 068 app URL required")
    local_probe_dsn(value)
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))
    return value


def run(coro):
    return asyncio.run(
        coro, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )


async def cleanup_owned(store, run_id):
    connection = await asyncpg.connect(store._dsn)
    try:
        async with connection.transaction():
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await connection.execute(
                    f"DELETE FROM public.{table} WHERE thread_id=$1", checkpoint_thread(run_id, 1)
                )
            await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=$1", run_id)
    finally:
        await connection.close()


async def counts(store, run_id):
    connection = await asyncpg.connect(store._dsn)
    try:
        return dict(
            await connection.fetchrow(
                "SELECT (SELECT count(*) FROM mimi_probe_068.dispatch WHERE run_id=$1) dispatches,"
                "(SELECT count(*) FROM mimi_probe_068.receipt WHERE run_id=$1) receipts",
                run_id,
            )
        )
    finally:
        await connection.close()


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
def test_terminal_cap_is_atomic_with_receipt_and_preserves_pending(probe_database, engine):
    async def scenario():
        store = PgFrameStore(probe_database)
        owner = f"synthetic-{uuid4()}"
        ids = [uuid4() for _ in range(18)]
        runner = {"control": run_control, "graph": run_graph}[engine]
        now = datetime.now(UTC)
        try:
            for run_id in ids[:16]:
                frame = await store.create(
                    run_id,
                    owner=owner,
                    generation=1,
                    engine=engine,
                    content={},
                    now=now,
                    expires_at=now + timedelta(hours=24),
                )
                await store.save(frame, phase="cancelled", content={})
            held = Workflow(store, ids[16], owner)
            await held.create("task", engine, (Record("a", 1, "Held synthetic"),))
            await runner(held)
            await held.accept(generation=1, direction="apply_prefix")
            pending = await runner(held)
            assert pending["phase"] == "confirmation"
            workflow = Workflow(store, ids[17], owner)
            await workflow.create("task", engine, (Record("a", 1, "New synthetic"),))
            await runner(workflow)
            await workflow.accept(generation=1, direction="apply_prefix")
            preview = await runner(workflow)
            await workflow.accept(
                generation=1,
                confirmation=ConfirmationContent(
                    owner=owner,
                    generation=1,
                    preview_digest=preview["preview_digest"],
                ),
            )

            async def fault(point):
                if point == "before_commit":
                    raise RuntimeError("synthetic_before_commit")

            workflow.fault = fault
            with pytest.raises(RuntimeError):
                await runner(workflow)
            connection = await asyncpg.connect(store._dsn)
            try:
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM mimi_probe_068.run WHERE id=ANY($1::uuid[])", ids[:16]
                    )
                    == 16
                )  # pruning rolls back with domain writes and receipt
                assert await counts(store, ids[17]) == {"dispatches": 2, "receipts": 0}

                async def after_commit(point):
                    if point == "after_commit":
                        raise RuntimeError("synthetic_after_commit")

                workflow.fault = after_commit
                with pytest.raises(RuntimeError):
                    await runner(workflow)
                # Inspect committed rows before any CLI or explicit cleanup.
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM mimi_probe_068.run WHERE engine=$1 "
                        "AND phase IN ('succeeded','expired','cancelled')",
                        engine,
                    )
                    == 16
                )
                assert await counts(store, ids[17]) == {"dispatches": 2, "receipts": 1}
                assert (await runner(Workflow(store, ids[17], owner)))["phase"] == "succeeded"
                held_again = await held.status()
                assert held_again["phase"] == "confirmation"
                assert held_again["preview_digest"] == pending["preview_digest"]
            finally:
                await connection.close()
        finally:
            for run_id in ids:
                await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
@pytest.mark.parametrize("domain", ["task", "note"])
def test_two_domains_pause_resume_and_atomic_receipt(probe_database, engine, domain):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id = uuid4()
        owner = f"synthetic-{uuid4()}"
        workflow = Workflow(store, run_id, owner)
        runner = {"control": run_control, "graph": run_graph}[engine]
        records = (Record("a", 1, "Synthetic alpha"), Record("b", 2, "Synthetic beta"))
        try:
            await workflow.create(domain, engine, records)
            first = await runner(workflow)
            assert first["phase"] == "direction"
            assert await store.records(await store.load(run_id, owner=owner)) == records
            # New workflow object proves all private data is reloaded, not invocation memory.
            resumed = Workflow(store, run_id, owner)
            await resumed.accept(generation=1, direction="apply_prefix")
            preview = await runner(resumed)
            assert preview["phase"] == "confirmation"
            assert await counts(store, run_id) == {"dispatches": 2, "receipts": 0}
            await resumed.accept(
                generation=1,
                confirmation=ConfirmationContent(
                    owner=owner,
                    generation=1,
                    preview_digest=preview["preview_digest"],
                ),
            )
            final = await runner(Workflow(store, run_id, owner))
            assert final["phase"] == "succeeded"
            assert final["receipt"]["changed"] == 2
            assert await counts(store, run_id) == {"dispatches": 2, "receipts": 1}
            changed = await store.records(await store.load(run_id, owner=owner))
            assert [r.version for r in changed] == [2, 3]
            assert (await runner(Workflow(store, run_id, owner)))["receipt"] == final["receipt"]
            assert await counts(store, run_id) == {"dispatches": 2, "receipts": 1}
            if engine == "graph":
                connection = await asyncpg.connect(store._dsn)
                try:
                    blobs = await connection.fetch(
                        "SELECT blob FROM public.checkpoint_blobs WHERE thread_id=$1",
                        checkpoint_thread(run_id, 1),
                    )
                    assert blobs
                    for blob in blobs:
                        assert b"Synthetic alpha" not in bytes(blob["blob"] or b"")
                        assert str(preview["draft"]).encode() not in bytes(blob["blob"] or b"")
                finally:
                    await connection.close()
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
@pytest.mark.parametrize("point", ["after_dispatch", "after_terminal"])
def test_provider_fence_and_saved_terminal_replay(probe_database, engine, point):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id, owner = uuid4(), f"synthetic-{uuid4()}"
        runner = {"control": run_control, "graph": run_graph}[engine]

        async def fault(current):
            if current == point:
                raise RuntimeError("synthetic_crash")

        try:
            workflow = Workflow(store, run_id, owner, fault=fault)
            await workflow.create("task", engine, (Record("a", 1, "Synthetic"),))
            with pytest.raises(RuntimeError, match="probe_stage_failed"):
                await runner(workflow)
            result = await runner(Workflow(store, run_id, owner))
            expected = "reconcile" if point == "after_dispatch" else "direction"
            assert result["phase"] == expected
            assert (await counts(store, run_id))["dispatches"] == (
                1 if point == "after_dispatch" else 2
            )
            assert (await counts(store, run_id))["receipts"] == 0
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
def test_compatible_upgrade_and_changed_policy_stop(probe_database, engine):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id, owner = uuid4(), f"synthetic-{uuid4()}"
        runner = {"control": run_control, "graph": run_graph}[engine]
        try:
            old = Workflow(store, run_id, owner, version=1)
            await old.create("note", engine, (Record("a", 1, "Synthetic"),))
            assert (await runner(old))["schema_version"] == 1
            current = Workflow(store, run_id, owner, version=2)
            assert (await current.status())["schema_version"] == 2
            await current.accept(generation=1, direction="apply_prefix")
            paused = await runner(current)
            assert paused["phase"] == "confirmation"
            incompatible = Workflow(store, run_id, owner, policy="probe-v2")
            stopped = await runner(incompatible)
            assert stopped["phase"] == "repreview"
            assert (await counts(store, run_id))["dispatches"] == 2
            assert (await counts(store, run_id))["receipts"] == 0
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
def test_graph_error_writes_do_not_contain_private_exception(probe_database):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id, owner = uuid4(), f"synthetic-{uuid4()}"

        async def fault(point):
            if point == "after_dispatch":
                raise RuntimeError("PRIVATE_RUNTIME_MARKER")

        try:
            workflow = Workflow(store, run_id, owner, fault=fault)
            await workflow.create("task", "graph", (Record("a", 1, "Synthetic"),))
            with pytest.raises(RuntimeError):
                await run_graph(workflow)
            connection = await asyncpg.connect(store._dsn)
            try:
                rows = await connection.fetch(
                    "SELECT blob FROM public.checkpoint_writes WHERE thread_id=$1",
                    checkpoint_thread(run_id, 1),
                )
                assert rows
                assert all(b"PRIVATE_RUNTIME_MARKER" not in bytes(r["blob"] or b"") for r in rows)
            finally:
                await connection.close()
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_atomic_execute_crash_is_rollback_or_one_receipt(probe_database, engine, point):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id, owner = uuid4(), f"synthetic-{uuid4()}"
        runner = {"control": run_control, "graph": run_graph}[engine]
        original = (Record("a", 1, "Synthetic"),)

        async def fault(current):
            if current == point:
                raise RuntimeError("synthetic_crash")

        try:
            workflow = Workflow(store, run_id, owner)
            await workflow.create("task", engine, original)
            await runner(workflow)
            await workflow.accept(generation=1, direction="apply_prefix")
            preview = await runner(workflow)
            await workflow.accept(
                generation=1,
                confirmation=ConfirmationContent(
                    owner=owner,
                    generation=1,
                    preview_digest=preview["preview_digest"],
                ),
            )
            with pytest.raises(RuntimeError, match="probe_stage_failed"):
                await runner(Workflow(store, run_id, owner, fault=fault))
            persisted = await store.load(run_id, owner=owner)
            before = point == "before_commit"
            assert (await counts(store, run_id))["receipts"] == (0 if before else 1)
            assert (await store.records(persisted))[0].version == (1 if before else 2)
            result = await runner(Workflow(store, run_id, owner))
            assert result["phase"] == "succeeded"
            assert await counts(store, run_id) == {"dispatches": 2, "receipts": 1}
            assert (await store.records(await store.load(run_id, owner=owner)))[0].version == 2
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
def test_stale_snapshot_and_expired_confirmation_never_mutate(probe_database, engine):
    async def scenario():
        store = PgFrameStore(probe_database)
        runner = {"control": run_control, "graph": run_graph}[engine]
        for cause in ("source", "expiry", "contract"):
            run_id, owner = uuid4(), f"synthetic-{uuid4()}"
            workflow = Workflow(store, run_id, owner)
            try:
                await workflow.create("task", engine, (Record("a", 1, "Synthetic"),))
                await runner(workflow)
                await workflow.accept(generation=1, direction="apply_prefix")
                preview = await runner(workflow)
                await workflow.accept(
                    generation=1,
                    confirmation=ConfirmationContent(
                        owner=owner,
                        generation=1,
                        preview_digest=preview["preview_digest"],
                    ),
                )
                if cause == "source":
                    connection = await asyncpg.connect(store._dsn)
                    try:
                        # Version-only drift must stop before title decryption.
                        await connection.execute(
                            "UPDATE mimi_probe_068.record SET version=2 WHERE run_id=$1", run_id
                        )
                    finally:
                        await connection.close()
                    result = await runner(Workflow(store, run_id, owner))
                    assert result["phase"] == "repreview"
                elif cause == "contract":
                    frame = await store.load(run_id, owner=owner)
                    body = dict(frame.content)
                    body["contract_hash"] = "unknown-handler-contract"
                    await store.save(frame, phase=frame.phase, content=body)
                    result = await runner(Workflow(store, run_id, owner))
                    assert result["phase"] == "repreview"
                else:

                    def clock():
                        return datetime.now(UTC) + timedelta(hours=25)

                    result = await runner(Workflow(store, run_id, owner, now=clock))
                    assert result["phase"] == "expired"
                assert (await counts(store, run_id))["receipts"] == 0
                assert (await counts(store, run_id))["dispatches"] == 2
            finally:
                await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
def test_client_replaced_operations_cannot_execute_even_with_matching_digest(probe_database):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id, owner = uuid4(), f"synthetic-{uuid4()}"
        workflow = Workflow(store, run_id, owner)
        try:
            await workflow.create("task", "control", (Record("a", 1, "Synthetic"),))
            await run_control(workflow)
            await workflow.accept(generation=1, direction="apply_prefix")
            await run_control(workflow)
            frame, body = await workflow.load()
            preview = body.preview.preview()
            forged = replace(preview, operations=(("a", "UNAUTHORIZED"),))
            frame = await store.save(frame, phase="execute", content=frame.content)
            with pytest.raises(ProbeBlocked, match="frozen_preview_mismatch"):
                await store.execute(
                    frame,
                    forged,
                    Confirmation(owner, 1, forged.digest),
                    policy="probe-v1",
                    now=datetime.now(UTC),
                )
            assert (await store.records(await store.load(run_id, owner=owner)))[
                0
            ].title == "Synthetic"
            assert (await counts(store, run_id))["receipts"] == 0
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())


@pytest.mark.pg
def test_phase_cursor_alone_does_not_grant_confirmation_authority(probe_database):
    async def scenario():
        store = PgFrameStore(probe_database)
        run_id, owner = uuid4(), f"synthetic-{uuid4()}"
        workflow = Workflow(store, run_id, owner)
        try:
            await workflow.create("task", "control", (Record("a", 1, "Synthetic"),))
            await run_control(workflow)
            await workflow.accept(generation=1, direction="apply_prefix")
            await run_control(workflow)
            frame, body = await workflow.load()
            preview = body.preview.preview()
            assert body.confirmation is None
            frame = await store.save(frame, phase="execute", content=frame.content)
            with pytest.raises(ProbeBlocked, match="persisted_confirmation_required"):
                await store.execute(
                    frame,
                    preview,
                    Confirmation(owner, 1, preview.digest),
                    policy="probe-v1",
                    now=datetime.now(UTC),
                )
            assert (await counts(store, run_id))["receipts"] == 0
        finally:
            await cleanup_owned(store, run_id)

    run(scenario())
