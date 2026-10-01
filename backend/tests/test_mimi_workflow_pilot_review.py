import asyncio
import os
import selectors
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.agent.workflow_pilot import (
    POLICY,
    PilotWorkflow,
    TaskFrameStore,
    advance,
    create,
    status_view,
)
from app.agent.workflow_probe.contracts import ProbeBlocked
from app.agent.workflow_probe.engines import run_control, run_graph
from app.agent.workflow_probe.store import checkpoint_thread
from app.core import crypto


def test_direct_store_rejects_old_qa_namespace_before_connect():
    with pytest.raises(ProbeBlocked, match="exclusive_pilot_database_required"):
        TaskFrameStore("postgresql://microsched_app@127.0.0.1:55466/microsched_p1ca_068")


@pytest.fixture
def store(monkeypatch):
    value = os.environ.get("MIMI_PILOT_APP_URL")
    if not value:
        pytest.skip("exclusive synthetic pilot database required")
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))
    return TaskFrameStore(value)


def run(coroutine):
    return asyncio.run(
        coroutine, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )


async def cleanup(connection, ids, tasks):
    for run_id in ids:
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            await connection.execute(
                f"DELETE FROM public.{table} WHERE thread_id=$1", checkpoint_thread(run_id, 1)
            )
    await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=ANY($1::uuid[])", ids)
    await connection.execute("DELETE FROM microsched.task WHERE id=ANY($1::uuid[])", tasks)


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
@pytest.mark.parametrize("point", ["group", "materialize", "status"])
def test_reclassified_source_blocks_egress_preview_and_read(store, engine, point):
    async def scenario():
        import json

        connection = await asyncpg.connect(store._dsn)
        task, identity, owner = uuid4(), uuid4(), "synthetic-review-" + str(uuid4())
        calls = []

        async def provider(step, body, frame):
            calls.append(step)
            return (
                json.dumps([[str(task)]]) if step == "group" else "Dữ liệu synthetic chỉ là nháp."
            )

        async def fault(marker):
            if point == "group" and marker == "after_query":
                raise RuntimeError("synthetic pause after query")

        store.provider = provider
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,$2)",
                task,
                "QA_073 public becomes private",
            )
            workflow = await store.create_task_run(identity, owner, engine, [task])
            runner = run_graph if engine == "graph" else run_control
            if point == "group":
                workflow.fault = fault
                with pytest.raises(RuntimeError):
                    await runner(workflow)
                workflow.fault = None
            else:
                await runner(workflow)
                if point == "status":
                    await advance(workflow, generation=1, direction="apply_prefix")
            before = len(calls)
            await connection.execute(
                "UPDATE microsched.task SET is_private=true,title='enc:v1:synthetic' WHERE id=$1",
                task,
            )
            if point == "group":
                await runner(workflow)
            elif point == "materialize":
                await advance(workflow, generation=1, direction="apply_prefix")
            state = await status_view(workflow)
            assert state["phase"] == "repreview"
            assert state["draft"] == "" and state["preview"] is None
            assert len(calls) == before
        finally:
            await cleanup(connection, [identity], [task])
            await connection.close()

    run(scenario())


@pytest.mark.pg
def test_reads_are_pure_replay_survives_reclassification_and_pruning(store):
    async def scenario():
        connection = await asyncpg.connect(store._dsn)
        task, identity, owner = uuid4(), uuid4(), "synthetic-review-" + str(uuid4())
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,'QA_073 read')", task
            )
            await create(store, identity, owner, "control", [task])
            workflow = PilotWorkflow(store, identity, owner, policy=POLICY)
            await connection.execute(
                "UPDATE mimi_probe_068.run SET expires_at=clock_timestamp()-interval '1 minute' "
                "WHERE id=$1",
                identity,
            )
            before = dict(
                await connection.fetchrow(
                    "SELECT phase,revision,content FROM mimi_probe_068.run WHERE id=$1", identity
                )
            )
            assert (await status_view(workflow))["phase"] == "expired"
            assert (
                dict(
                    await connection.fetchrow(
                        "SELECT phase,revision,content FROM mimi_probe_068.run WHERE id=$1",
                        identity,
                    )
                )
                == before
            )
            await connection.execute(
                "UPDATE microsched.task SET deleted_at=clock_timestamp() WHERE id=$1", task
            )
            assert (await create(store, identity, owner, "control", [task]))["draft"] == ""
            await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=$1", identity)
            with pytest.raises(ProbeBlocked, match="run_retired"):
                await create(store, identity, owner, "control", [task])
        finally:
            await cleanup(connection, [identity], [task])
            await connection.close()

    run(scenario())


@pytest.mark.pg
def test_create_replay_bypasses_new_admission_at_full_quota(store):
    async def scenario():
        connection = await asyncpg.connect(store._dsn)
        task, owner, identities = (
            uuid4(),
            "synthetic-review-" + str(uuid4()),
            [uuid4() for _ in range(8)],
        )
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,'QA_073 quota')", task
            )
            available = 8 - await connection.fetchval(
                "SELECT count(*) FROM mimi_probe_068.run WHERE engine='control' "
                "AND phase NOT IN ('succeeded','expired','cancelled')"
            )
            assert available > 0, "no fixture admission slot available"
            for identity in identities[:available]:
                await store.create_task_run(identity, owner, "control", [task])
            assert (await create(store, identities[0], owner, "control", [task]))[
                "phase"
            ] == "query"
            with pytest.raises(ProbeBlocked, match="active_quota_exceeded"):
                await store.create_task_run(uuid4(), owner, "control", [task])
        finally:
            await cleanup(connection, identities, [task])
            await connection.close()

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
def test_multi_task_rollback_and_cancel_processing(store, engine):
    async def scenario():
        connection = await asyncpg.connect(store._dsn)
        tasks, identity, owner = [uuid4(), uuid4()], uuid4(), "synthetic-review-" + str(uuid4())
        try:
            for task in tasks:
                await connection.execute(
                    "INSERT INTO microsched.task(id,title) VALUES($1,'QA_073 atomic')", task
                )
            await create(store, identity, owner, engine, tasks)
            workflow = PilotWorkflow(store, identity, owner, policy=POLICY)
            state = await advance(workflow, generation=1, direction="apply_prefix")

            async def fault(marker):
                if marker == "before_commit":
                    raise RuntimeError("synthetic two-task rollback")

            workflow.fault = fault
            with pytest.raises(RuntimeError):
                await advance(workflow, generation=1, digest=state["preview_digest"])
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM microsched.task WHERE id=ANY($1::uuid[]) "
                    "AND title='QA_073 atomic'",
                    tasks,
                )
                == 2
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM mimi_probe_068.receipt WHERE run_id=$1", identity
                )
                == 0
            )
            workflow.fault = None
            assert (await advance(workflow, generation=1, cancel=True))["phase"] == "cancelled"
        finally:
            await cleanup(connection, [identity], tasks)
            await connection.close()

    run(scenario())


@pytest.mark.pg
def test_task_lock_wait_past_expiry_refuses_execution(store):
    async def scenario():
        connection = await asyncpg.connect(store._dsn)
        blocker = await asyncpg.connect(store._dsn)
        task, identity, owner = uuid4(), uuid4(), "synthetic-review-" + str(uuid4())
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,'QA_073 expiry')", task
            )
            await create(store, identity, owner, "control", [task])
            workflow = PilotWorkflow(store, identity, owner, policy=POLICY)
            state = await advance(workflow, generation=1, direction="apply_prefix")
            await connection.execute(
                "UPDATE mimi_probe_068.run SET expires_at=$2 WHERE id=$1",
                identity,
                datetime.now(UTC) + timedelta(seconds=1),
            )
            await blocker.execute("BEGIN")
            await blocker.execute("SELECT id FROM microsched.task WHERE id=$1 FOR UPDATE", task)
            pending = asyncio.create_task(
                advance(workflow, generation=1, digest=state["preview_digest"])
            )
            await asyncio.sleep(1.4)
            await blocker.execute("ROLLBACK")
            state = await pending
            assert state["phase"] == "expired"
            assert (
                await connection.fetchval("SELECT title FROM microsched.task WHERE id=$1", task)
                == "QA_073 expiry"
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM mimi_probe_068.receipt WHERE run_id=$1", identity
                )
                == 0
            )
        finally:
            await blocker.close()
            await cleanup(connection, [identity], [task])
            await connection.close()

    run(scenario())
