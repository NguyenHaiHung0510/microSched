import asyncio
import os
import selectors
from uuid import uuid4

import asyncpg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.agent.workflow_probe.contracts import Record
from app.agent.workflow_probe.engines import run_control, run_graph, validate_refs
from app.agent.workflow_probe.store import PgFrameStore, checkpoint_thread, local_probe_dsn
from app.agent.workflow_probe.workflow import ConfirmationContent, Workflow
from app.core import crypto


def test_graph_reference_guard_rejects_identity_version_and_content_channels():
    expected = {
        "run_id": "opaque",
        "generation": 1,
        "state_schema_version": 2,
        "policy_hash": "frozen-policy",
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
            with pytest.raises(RuntimeError, match="synthetic_crash"):
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
