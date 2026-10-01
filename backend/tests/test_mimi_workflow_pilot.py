import asyncio
import os
import selectors
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import ValidationError

from app.agent.workflow_pilot import (
    PILOT_DATABASE,
    POLICY,
    PilotWorkflow,
    TaskFrameStore,
    advance,
    create,
    pilot_available,
)
from app.agent.workflow_probe.contracts import ProbeBlocked
from app.agent.workflow_probe.store import checkpoint_thread
from app.agent.workflow_probe.workflow import Workflow
from app.core import crypto
from app.web.routers.mimi_workflow_pilot import AdvanceRun, CreateRun


def test_default_off_remote_and_other_database_fail_closed():
    base = dict(
        app_env="local",
        mimi_workflow_pilot_enabled=True,
        database_url=f"postgresql://microsched_app@127.0.0.1:55466/{PILOT_DATABASE}",
    )
    assert pilot_available(SimpleNamespace(**base))
    for changes in (
        {"app_env": "production"},
        {"mimi_workflow_pilot_enabled": False},
        {"database_url": "postgresql://microsched_app@remote.example:5432/other"},
        {"database_url": "postgresql://microsched_app@127.0.0.1:55466/other"},
    ):
        assert not pilot_available(SimpleNamespace(**(base | changes)))


def test_request_no_forged_operations_or_combined_actions():
    for payload in (
        {"generation": True, "cancel": True},
        {"generation": 1, "cancel": True, "resume": True},
        {"generation": 1},
        {"generation": 1, "direction": "apply_prefix", "operations": []},
    ):
        with pytest.raises(ValidationError):
            AdvanceRun.model_validate(payload)
    task = uuid4()
    with pytest.raises(ValidationError):
        CreateRun(run_id=uuid4(), task_ids=[task, task])


def run(coroutine):
    return asyncio.run(
        coroutine, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
@pytest.mark.parametrize("violation", ["none", "stale", "private", "deleted", "rollback"])
def test_actual_tasks_freshness_atomicity_and_receipt_replay(monkeypatch, engine, violation):
    url = os.environ.get("MIMI_PILOT_APP_URL")
    if not url:
        pytest.skip("dedicated synthetic pilot database required")
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))

    async def scenario():
        store = TaskFrameStore(url)
        connection = await asyncpg.connect(store._dsn)
        task_id, run_id, owner = uuid4(), uuid4(), f"synthetic-{uuid4()}"
        original = "QA_073 synthetic chuẩn bị tài liệu"
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,$2)", task_id, original
            )
            state = await create(store, run_id, owner, engine, [task_id])
            assert state["phase"] == "direction"
            assert (
                await connection.fetchval("SELECT title FROM microsched.task WHERE id=$1", task_id)
                == original
            )
            with pytest.raises(ProbeBlocked, match="owned_run_not_found"):
                await Workflow(store, run_id, "foreign-owner", policy=POLICY).status()
            workflow = Workflow(store, run_id, owner, policy=POLICY)
            state = await advance(workflow, generation=1, direction="apply_prefix")
            assert state["phase"] == "confirmation"
            digest = state["preview_digest"]
            with pytest.raises(ProbeBlocked, match="confirmation_mismatch"):
                await advance(workflow, generation=1, digest="0" * 64)
            assert (
                await connection.fetchval("SELECT title FROM microsched.task WHERE id=$1", task_id)
                == original
            )
            if violation == "stale":
                await connection.execute(
                    "UPDATE microsched.task SET pinned=true WHERE id=$1", task_id
                )
            elif violation == "private":
                await connection.execute(
                    "UPDATE microsched.task SET is_private=true,title='enc:v1:synthetic' "
                    "WHERE id=$1",
                    task_id,
                )
            elif violation == "deleted":
                await connection.execute(
                    "UPDATE microsched.task SET deleted_at=clock_timestamp() WHERE id=$1", task_id
                )

            async def fault(point):
                if point == "before_commit":
                    raise RuntimeError("synthetic rollback fault")

            if violation == "rollback":
                workflow = Workflow(store, run_id, owner, policy=POLICY, fault=fault)
                with pytest.raises(RuntimeError, match="probe_stage_failed"):
                    await advance(workflow, generation=1, digest=digest)
                assert (
                    await connection.fetchval(
                        "SELECT title FROM microsched.task WHERE id=$1", task_id
                    )
                    == original
                )
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM mimi_probe_068.receipt WHERE run_id=$1", run_id
                    )
                    == 0
                )
                # PG execute cursor survives failed commit; owner resumes explicitly.
                workflow = Workflow(store, run_id, owner, policy=POLICY)
                state = await advance(workflow, generation=1, resume=True)
            else:
                state = await advance(workflow, generation=1, digest=digest)
            if violation in {"stale", "private", "deleted"}:
                assert state["phase"] == "repreview"
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM mimi_probe_068.receipt WHERE run_id=$1", run_id
                    )
                    == 0
                )
                title = await connection.fetchval(
                    "SELECT title FROM microsched.task WHERE id=$1", task_id
                )
                assert not title.startswith("[planned] ")
            else:
                assert state["phase"] == "succeeded"
                assert (
                    await connection.fetchval(
                        "SELECT title FROM microsched.task WHERE id=$1", task_id
                    )
                    == "[planned] " + original
                )
                assert (await advance(workflow, generation=1, digest=digest))["receipt"] == state[
                    "receipt"
                ]
                assert (await create(store, run_id, owner, engine, [task_id]))["receipt"] == state[
                    "receipt"
                ]
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM mimi_probe_068.receipt WHERE run_id=$1", run_id
                    )
                    == 1
                )
        finally:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await connection.execute(
                    f"DELETE FROM public.{table} WHERE thread_id=$1", checkpoint_thread(run_id, 1)
                )
            await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=$1", run_id)
            await connection.execute("DELETE FROM microsched.task WHERE id=$1", task_id)
            await connection.close()

    run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize("engine", ["control", "graph"])
@pytest.mark.parametrize("mode", ["valid", "unknown", "bad_partition"])
def test_provider_terminal_replay_fences_and_run_lock(monkeypatch, engine, mode):
    url = os.environ.get("MIMI_PILOT_APP_URL")
    if not url:
        pytest.skip("exclusive synthetic pilot database required")
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))

    async def scenario():
        import json

        task_id, run_id, owner = uuid4(), uuid4(), f"synthetic-{uuid4()}"
        calls = []

        async def provider(step, body, frame):
            calls.append(step)
            if mode == "unknown":
                raise TimeoutError("synthetic ambiguous dispatch")
            if step == "group":
                return json.dumps([[str(task_id)]] if mode == "valid" else [["foreign-id"]])
            return "Nhóm đã chọn có một việc. Đề xuất gắn prefix; chưa thay đổi dữ liệu."

        store = TaskFrameStore(url, provider=provider)
        connection = await asyncpg.connect(store._dsn)
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title) VALUES($1,$2)",
                task_id,
                "QA_073 synthetic provider",
            )
            async with store.invocation(run_id):
                with pytest.raises(ProbeBlocked, match="run_busy"):
                    async with store.invocation(run_id):
                        raise AssertionError("parallel invocation must be refused")
            state = await create(store, run_id, owner, engine, [task_id])
            assert state["provider_mode"] == "live"
            if mode != "valid":
                assert state["phase"] == "reconcile"
                assert calls == ["group"]
                assert (await create(store, run_id, owner, engine, [task_id]))[
                    "phase"
                ] == "reconcile"
                assert calls == ["group"]
            else:
                assert state["phase"] == "direction"
                assert calls == ["group", "draft"]
                workflow = PilotWorkflow(store, run_id, owner, policy=POLICY)
                await advance(workflow, generation=1, direction="apply_prefix")
                digest = (await workflow.status())["preview_digest"]
                state = await advance(workflow, generation=1, digest=digest)
                assert state["phase"] == "succeeded"
                assert calls == ["group", "draft"]
        finally:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await connection.execute(
                    f"DELETE FROM public.{table} WHERE thread_id=$1", checkpoint_thread(run_id, 1)
                )
            await connection.execute("DELETE FROM mimi_probe_068.run WHERE id=$1", run_id)
            await connection.execute("DELETE FROM microsched.task WHERE id=$1", task_id)
            await connection.close()

    run(scenario())


@pytest.mark.pg
def test_private_deleted_selection_and_choices(monkeypatch):
    url = os.environ.get("MIMI_PILOT_APP_URL")
    if not url:
        pytest.skip("dedicated synthetic pilot database required")
    monkeypatch.setattr(crypto, "_cipher", lambda: AESGCM(b"s" * 32))

    async def scenario():
        store = TaskFrameStore(url)
        connection = await asyncpg.connect(store._dsn)
        ids = [uuid4(), uuid4()]
        try:
            await connection.execute(
                "INSERT INTO microsched.task(id,title,is_private) "
                "VALUES($1,'enc:v1:synthetic',true)",
                ids[0],
            )
            await connection.execute(
                "INSERT INTO microsched.task(id,title,deleted_at) "
                "VALUES($1,'QA_073 deleted',clock_timestamp())",
                ids[1],
            )
            choices = {item["id"] for item in await store.choices()}
            assert not choices.intersection(map(str, ids))
            for task in ids:
                with pytest.raises(ProbeBlocked, match="public_source_required"):
                    await create(store, uuid4(), "synthetic-selection", "control", [task])
        finally:
            await connection.execute("DELETE FROM microsched.task WHERE id=ANY($1::uuid[])", ids)
            await connection.close()

    run(scenario())
