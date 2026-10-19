"""Native SDK -> service -> frozen create -> explicit atomic decision, disposable PG only."""

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import HTTPException
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup, local_contract  # noqa: F401
from test_mimi_owner296 import call, collection, single
from test_mimi_owner296_sdk import response

from app.agent import langgraph_runner, openai_sdk, service
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiExecutionReceipt,
    MimiProviderCall,
    MimiRun,
)
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task, TaskItem

pytestmark = pytest.mark.pg


@asynccontextmanager
async def runtime(pg_dsn, monkeypatch, *, streaming=False):
    # Test admission only, never a deployed local/production DB allowlist change.
    from sqlalchemy.engine import make_url

    parsed = make_url(pg_dsn)
    assert parsed.host in {"127.0.0.1", "localhost", "postgres", "db"}
    for name, value in {
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODE": "native",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_TRANSPORT": "openai_sdk",
        "MIMI_RUNNER": "langgraph",
        "MIMI_TEXT_RESPONSE_FORMAT": "natural",
        "DATABASE_URL": pg_dsn,
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        langgraph_runner,
        "_authorized_local_database",
        lambda p: (p.host, p.port, p.database) == (parsed.host, parsed.port, parsed.database),
    )
    get_settings.cache_clear()
    async with AsyncPostgresSaver.from_conn_string(pg_dsn) as saver:
        await saver.setup()
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
    state = SimpleNamespace(
        maker=maker,
        actor=auth(),
        cid=None,
        ids=[],
        queue=[],
        wires=[],
        reads=[],
        after_response=None,
        cost=0.001,
        streaming=streaming,
    )
    original_client = openai_sdk._client
    actual_read = service.execute_read_tool

    async def read(*args, **kwargs):
        state.reads.append(args[1])
        return await actual_read(*args, **kwargs)

    monkeypatch.setattr(service, "execute_read_tool", read)

    async def handler(request):
        wire = json.loads(request.content)
        state.wires.append(wire)
        native = copy.deepcopy(state.queue.pop(0))
        for item in native:
            if item["function"]["name"] == CREATE_CANDIDATE_TOOL:
                authority = next(
                    json.loads(m["content"])["authority_envelope"]
                    for m in wire["messages"]
                    if m["role"] == "system" and "authority_envelope" in m["content"]
                )
                args = json.loads(item["function"]["arguments"])
                args["task"]["id"] = authority["reserved_task_id"]
                item["function"]["arguments"] = json.dumps(args)
        if state.after_response:
            await state.after_response(state)
        return response(wire, native, sequence=len(state.wires), cost=state.cost)

    def client(settings, *, api_key, client):
        assert client is None
        return original_client(
            settings,
            api_key=api_key,
            client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )

    monkeypatch.setattr(openai_sdk, "_client", client)
    try:
        async with maker() as db:
            state.cid = (
                await service.create_conversation(db, state.actor, service.ConversationCreate())
            )["id"]
            await db.commit()
        yield state
    finally:
        if state.cid:
            await cleanup(maker, state.cid, list(set(state.ids)))
        await engine.dispose()


async def send(rt, *, revision=None):
    async with rt.maker() as db:
        current = await service.conversation_view(db, rt.actor, rt.cid)
        view = await service.send_message(
            db,
            rt.actor,
            rt.cid,
            service.MessageCreate(
                client_id=f"synthetic-r1-{uuid4()}",
                content="Tạo đầy đủ các Task synthetic đã yêu cầu",
                expected_generation=current["generation"],
                **(revision or {}),
            ),
            provider_stream=rt.streaming,
        )
        await db.commit()
        for change in view["change_sets"]:
            op = change["operation"]
            if op["tool"] == "task.collection.v1":
                rt.ids.extend(UUID(e["id"]) for e in op["args"]["entries"])
            else:
                rt.ids.append(UUID(str(op["args"]["id"])))
        return view


async def counts(rt):
    async with rt.maker() as db:
        tasks = await db.scalar(select(func.count()).select_from(Task))
        receipts = await db.scalar(select(func.count()).select_from(MimiExecutionReceipt))
        return tasks, receipts


async def decide(rt, change, decision, key):
    async with rt.maker() as db:
        result = await service.confirm_change_set(
            db,
            rt.actor,
            UUID(str(change["id"])),
            service.ConfirmationDecision(
                digest=change["digest"], nonce=change["nonce"], decision=decision
            ),
            key,
        )
        await db.commit()
        return result


@pytest.mark.parametrize("count,streaming", [(0, False), (2, False), (4, True)])
def test_native_create_complete_preview_zero_effects_then_one_atomic_confirm(
    pg_dsn, monkeypatch, count, streaming
):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch, streaming=streaming) as rt:
            before = await counts(rt)
            rt.queue = [
                [call(CREATE_CANDIDATE_TOOL, single())]
                if count == 0
                else [call(COLLECTION_CANDIDATE_TOOL, collection(count))]
            ]
            view = await send(rt)
            assert view["runs"][-1]["state"] == "waiting_confirmation", view["runs"][-1]
            assert await counts(rt) == before and len(rt.wires) == 1
            change = view["change_sets"][-1]
            if count:
                entries = change["operation"]["args"]["entries"]
                rt.ids = [UUID(e["id"]) for e in entries]
                assert len(entries) == count
                assert [e["after"]["fields"]["title"] for e in entries] == [
                    f"Synthetic R1 {i}" for i in range(count)
                ]
                assert all(
                    e["after"]["fields"]["body_md"] == f"Nội dung {i}"
                    and e["after"]["fields"]["due_on"] == "2026-11-02"
                    and e["after"]["children"][0]["content"] == f"Bước {i}"
                    for i, e in enumerate(entries)
                )
            result = await decide(rt, change, "confirm", "synthetic-r1-once")
            if not count:
                rt.ids = [UUID(str(result["result"]["task_id"]))]
            assert await counts(rt) == (before[0] + (count or 1), before[1] + 1)
            again = await decide(rt, change, "confirm", "synthetic-r1-once")
            assert again["id"] == result["id"] and len(rt.wires) == 1
            async with rt.maker() as db:
                reloaded = await service.conversation_view(db, rt.actor, rt.cid)
                assert len(reloaded["receipts"]) == 1
                if count:
                    children = (
                        await db.scalars(select(TaskItem).where(TaskItem.task_id.in_(rt.ids)))
                    ).all()
                    assert len(children) == count
            assert await counts(rt) == (before[0] + (count or 1), before[1] + 1)

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.parametrize("failure,count,streaming", [("mixed", 2, False), ("schema", 4, True)])
def test_native_rejected_turn_corrects_complete_set_with_separate_accounted_attempt(
    pg_dsn, monkeypatch, failure, count, streaming
):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch, streaming=streaming) as rt:
            before = await counts(rt)
            bad = collection(count)
            calls = [call(COLLECTION_CANDIDATE_TOOL, bad), call("task.query.v1", {})]
            if failure == "schema":
                bad["entries"][-1]["fields"].pop("due_at")
                calls = [call(COLLECTION_CANDIDATE_TOOL, bad)]
            rt.queue = [calls, [call(COLLECTION_CANDIDATE_TOOL, collection(count))]]
            view = await send(rt)
            assert view["runs"][-1]["state"] == "waiting_confirmation", view["runs"][-1]
            assert await counts(rt) == before and len(rt.wires) == 2 and rt.reads == []
            change = view["change_sets"][-1]
            assert len(change["operation"]["args"]["entries"]) == count
            async with rt.maker() as db:
                calls = (
                    await db.scalars(
                        select(MimiProviderCall)
                        .where(MimiProviderCall.run_id == UUID(str(view["runs"][-1]["id"])))
                        .order_by(MimiProviderCall.attempt)
                    )
                ).all()
                assert [c.state for c in calls] == ["failed", "succeeded"]
                assert calls[0].result["candidate_correction"] is True
                assert all(c.usage["cost"] == 0.001 for c in calls)
                assert sum(c.usage["cost"] for c in calls) == 0.002
            result = await decide(rt, change, "confirm", "synthetic-r1-correction")
            assert result["result"]["count"] == count and len(rt.wires) == 2
            assert await counts(rt) == (before[0] + count, before[1] + 1)

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


def test_reject_and_fault_after_first_new_row_leave_no_domain_or_receipt_effects(
    pg_dsn, monkeypatch
):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch) as rt:
            before = await counts(rt)
            rt.queue = [[call(COLLECTION_CANDIDATE_TOOL, collection(2))]]
            change = (await send(rt))["change_sets"][-1]
            await decide(rt, change, "reject", "synthetic-r1-reject")
            assert await counts(rt) == before and len(rt.wires) == 1
            rt.queue = [[call(COLLECTION_CANDIDATE_TOOL, collection(4))]]
            change = (await send(rt))["change_sets"][-1]

            async def fail(db, actor, plan):
                first = plan.entries[0]
                db.add(Task(id=first.id, title=first.after["fields"]["title"]))
                await db.flush()
                raise ValueError("synthetic_fault_after_first_new_row")

            monkeypatch.setattr(service, "execute_collection", fail)
            with pytest.raises((HTTPException, ValueError)):
                await decide(rt, change, "confirm", "synthetic-r1-fault")
            assert await counts(rt) == before and len(rt.wires) == 2
            async with rt.maker() as db:
                assert (await db.get(MimiChangeSet, UUID(str(change["id"])))).state == "pending"

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


def test_missing_cost_never_dispatches_correction_and_old_pending_survives(pg_dsn, monkeypatch):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch) as rt:
            before = await counts(rt)
            rt.queue = [[call(COLLECTION_CANDIDATE_TOOL, collection(2))]]
            original = (await send(rt))["change_sets"][-1]
            rt.cost = None
            rt.queue = [[call(COLLECTION_CANDIDATE_TOOL, collection(4)), call("task.query.v1", {})]]
            view = await send(
                rt,
                revision={
                    "intent": "revise_pending_preview",
                    "expected_change_set_id": original["id"],
                    "expected_change_set_digest": original["digest"],
                },
            )
            assert len(rt.wires) == 2 and await counts(rt) == before
            pending = [c for c in view["change_sets"] if c["state"] == "pending"]
            assert len(pending) == 1
            assert (
                pending[0]["id"],
                pending[0]["digest"],
                pending[0]["nonce"],
                pending[0]["operation"],
            ) == (original["id"], original["digest"], original["nonce"], original["operation"])

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.parametrize("boundary", ["stop", "frontier"])
def test_stop_after_bad_terminal_never_dispatches_a_correction(pg_dsn, monkeypatch, boundary):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch) as rt:
            before = await counts(rt)
            rt.queue = [
                [call(COLLECTION_CANDIDATE_TOOL, collection(2)), call("task.query.v1", {})],
                [call(COLLECTION_CANDIDATE_TOOL, collection(2))],
            ]

            async def stop(state):
                if len(state.wires) != 1:
                    return
                async with state.maker() as db:
                    run = (
                        await db.scalars(
                            select(MimiRun).where(MimiRun.conversation_id == state.cid)
                        )
                    ).one()
                    if boundary == "stop":
                        await service.finish_interrupted_run(
                            db, state.actor, run.id, cancelled=True
                        )
                    else:
                        conversation = await db.get(MimiConversation, state.cid)
                        conversation.generation += 1
                    await db.commit()

            rt.after_response = stop
            view = await send(rt)
            assert len(rt.wires) == 1
            assert view["runs"][-1]["state"] == ("cancelled" if boundary == "stop" else "halted")
            if boundary == "frontier":
                assert view["runs"][-1]["error_code"] == "response_frontier_changed"
            assert await counts(rt) == before and not view["change_sets"]

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


def test_corrected_collection_replaces_old_preview_only_after_complete_valid_candidate(
    pg_dsn, monkeypatch
):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch) as rt:
            before = await counts(rt)
            rt.queue = [[call(COLLECTION_CANDIDATE_TOOL, collection(2))]]
            original = (await send(rt))["change_sets"][-1]
            rt.queue = [
                [call(COLLECTION_CANDIDATE_TOOL, collection(4)), call("task.query.v1", {})],
                [call(COLLECTION_CANDIDATE_TOOL, collection(4))],
            ]

            async def observe(state):
                async with state.maker() as db:
                    old = await db.get(MimiChangeSet, UUID(str(original["id"])))
                    assert old.state == "pending" and old.digest_sha256 == original["digest"]
                assert await counts(state) == before

            rt.after_response = observe
            view = await send(
                rt,
                revision={
                    "intent": "revise_pending_preview",
                    "expected_change_set_id": original["id"],
                    "expected_change_set_digest": original["digest"],
                },
            )
            pending = [c for c in view["change_sets"] if c["state"] == "pending"]
            assert len(pending) == 1 and pending[0]["id"] != original["id"]
            assert len(pending[0]["operation"]["args"]["entries"]) == 4
            assert len(rt.wires) == 3 and rt.reads == []
            result = await decide(rt, pending[0], "confirm", "synthetic-r1-revised")
            assert result["result"]["count"] == 4 and len(rt.wires) == 3
            assert await counts(rt) == (before[0] + 4, before[1] + 1)

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


def test_unauthorized_candidate_field_does_not_dispatch_correction(pg_dsn, monkeypatch):
    async def scenario():
        async with runtime(pg_dsn, monkeypatch) as rt:
            before = await counts(rt)
            args = collection(2)
            args["entries"][0]["fields"]["is_private"] = True
            rt.queue = [
                [call(COLLECTION_CANDIDATE_TOOL, args)],
                [call(COLLECTION_CANDIDATE_TOOL, collection(2))],
            ]
            view = await send(rt)
            assert len(rt.wires) == 1 and not view["change_sets"]
            assert view["runs"][-1]["state"] == "halted"
            assert await counts(rt) == before

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
