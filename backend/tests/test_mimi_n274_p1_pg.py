"""N-274 synthetic recovery through real receipts/preview/Confirm; no inference egress."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_contracts import ADMITTED_MODEL
from test_mimi_collection_service_pg import auth, cleanup
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import evidence, langgraph_runner, service
from app.agent.context import PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent
from app.agent.openrouter import AgentCompletion
from app.agent.selection import SELECTION_TOOL
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("runner", ["current", "langgraph"])
@pytest.mark.usefixtures("local_sync_contract")
def test_duplicate_and_typed_selection_corrections_reach_exact_title_preview_and_confirm(
    pg_dsn, monkeypatch, runner
):
    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_RUNNER", runner)
    monkeypatch.setenv("MIMI_ROUTE_MODEL", ADMITTED_MODEL)
    if runner == "langgraph":
        real = langgraph_runner.run_langgraph

        async def graph(*args, **kwargs):
            return await real(*args, **kwargs, checkpointer_for_test=InMemorySaver())

        monkeypatch.setattr(langgraph_runner, "run_langgraph", graph)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor = auth()
        cid, ids, before = None, [], {}
        prefix = f"synthetic-n274-{uuid4().hex}"
        query = {"filter": {"title_contains": prefix}, "limit": 1}
        turns = []
        selection_args = {
            "intent": "Rename the exact synthetic title set",
            "variants_considered": [prefix],
        }

        def result(messages, call_id):
            return next(
                json.loads(m["content"])
                for m in reversed(messages)
                if m.get("role") == "tool" and m.get("tool_call_id") == call_id
            )

        def request(name, arguments, call_id):
            return ToolRequest(name=name, arguments=arguments, call_id=call_id)

        async def model(messages, **kwargs):
            turn = len(turns) + 1
            turns.append(turn)
            if turn == 1:
                reads = [request("task.query.v1", query, "first")]
            elif turn == 2:
                first = result(messages, "first")
                assert len(first["rows"]) == 1 and first["next_cursor"]
                selection_args["members"] = [
                    {"id": str(tid), "classification": "included", "reason": "Golden target"}
                    for tid in ids
                ]
                reads = [
                    request("task.query.v1", query, "duplicate"),
                    request(SELECTION_TOOL, selection_args, "missing"),
                ]
            elif turn == 3:
                missing = result(messages, "missing")
                assert missing["error"]["code"] == (
                    "selection_member_has_no_actual_versioned_receipt"
                )
                assert len(missing["obligations"]["missing_receipt_ids"]) == 1
                assert missing["coverage"] == "unavailable" and "selection" not in missing
                reads = [
                    request("task.inspect_batch.v1", {"ids": [str(t) for t in ids]}, "ids"),
                    request(SELECTION_TOOL, selection_args, "coverage"),
                ]
            elif turn == 4:
                gap = result(messages, "coverage")
                assert gap["error"]["code"] == "selection_all_scope_has_unresolved_obligations"
                assert not gap["obligations"]["query_complete"]
                assert gap["obligations"]["queries"][0]["open_cursors"]
                reads = [
                    request(
                        "task.query.v1",
                        query | {"cursor": result(messages, "duplicate")["next_cursor"]},
                        "last-page",
                    ),
                    request(SELECTION_TOOL, selection_args, "fixed"),
                ]
            else:
                assert turn == 5
                frozen = result(messages, "fixed")["selection"]
                assert frozen["semantic_complete"]
                return AgentCompletion(
                    outcome=PreviewCandidate(
                        tool=COLLECTION_CANDIDATE_TOOL,
                        arguments={
                            "selection_id": frozen["selection_id"],
                            "entries": [
                                {
                                    "action": "edit",
                                    "id": member["id"],
                                    "expected_collection_version": member["collection_version"],
                                    "fields": {"title": f"{prefix}-normalized"},
                                }
                                for member in frozen["members"]
                            ],
                        },
                    ),
                    response_id=f"synthetic-n274-{turn}",
                    usage={},
                    provider="Synthetic",
                    model=ADMITTED_MODEL,
                )
            return AgentCompletion(
                outcome=ToolRequests(requests=tuple(reads)),
                response_id=f"synthetic-n274-{turn}",
                usage={},
                provider="Synthetic",
                model=ADMITTED_MODEL,
            )

        monkeypatch.setattr(service, "openrouter_complete", model)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                tasks = [
                    Task(title=f"{prefix}-{i}", body_md="Keep this content", priority="p2")
                    for i in range(2)
                ]
                db.add_all(tasks)
                await db.flush()
                for task in tasks:
                    await db.refresh(task)
                ids = [t.id for t in tasks]
                before = {t.id: t.model_dump() for t in tasks}
                await db.commit()
            async with maker() as db:
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="n274-recovery", content=f"Đổi tên đúng hai Task {prefix}."
                    ),
                )
                await db.commit()
                assert view["runs"][-1]["state"] == "waiting_confirmation", view["runs"][-1]
                assert turns == [1, 2, 3, 4, 5]
                for tid in ids:
                    assert (await db.get(Task, tid)).model_dump() == before[tid]
                change = view["change_sets"][-1]
                rid = UUID(str(view["runs"][-1]["id"]))
                events = (await db.scalars(select(MimiEvent).where(MimiEvent.run_id == rid))).all()
                assert sum(e.kind == "selection.frozen" for e in events) == 1
                assert sum(e.kind == "tool.read_result" for e in events) == 7
            async with maker() as db:
                with pytest.raises(HTTPException):
                    await service.confirm_change_set(
                        db,
                        actor,
                        UUID(str(change["id"])),
                        service.ConfirmationDecision(
                            digest="0" * 64, nonce=change["nonce"], decision="confirm"
                        ),
                        "wrong-digest",
                    )
                await db.rollback()
                for tid in ids:
                    assert (await db.get(Task, tid)).title == before[tid]["title"]
                decision = service.ConfirmationDecision(
                    digest=change["digest"], nonce=change["nonce"], decision="confirm"
                )
                receipt = await service.confirm_change_set(
                    db, actor, UUID(str(change["id"])), decision, "n274-confirm"
                )
                await db.commit()
                replay = await service.confirm_change_set(
                    db, actor, UUID(str(change["id"])), decision, "n274-confirm"
                )
                assert replay == receipt and receipt["result"]["count"] == 2
                for tid in ids:
                    task = await db.get(Task, tid)
                    assert task.title == f"{prefix}-normalized"
                    for field, value in before[tid].items():
                        if field not in {"title", "updated_at", "collection_version"}:
                            assert getattr(task, field) == value
                feedback = await service.save_feedback(
                    db,
                    actor,
                    cid,
                    service.FeedbackCreate(
                        client_id="n274-positive-detail",
                        target_type="run",
                        target_id=str(rid),
                        comment="Phản hồi tích cực: Đúng tập đích.",
                    ),
                )
                bundle = await evidence.read_evidence(
                    db,
                    await db.get(MimiConversation, cid),
                    UUID(feedback["evidence_bundle_ids"][0]),
                )
                assert len(bundle["content"]["request_contexts"]) == 5
                assert len(bundle["content"]["reads_and_selection"]) == 8
                await db.commit()
        finally:
            if cid:
                await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.usefixtures("local_sync_contract")
@pytest.mark.parametrize("terminal", ["system", "provider"])
def test_system_halt_source_survives_message_and_causal_feedback(pg_dsn, monkeypatch, terminal):
    from app.agent.context import Blocked
    from app.agent.loop import LoopLimits, run_read_loop

    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", ADMITTED_MODEL)
    monkeypatch.setenv("MIMI_RUNNER", "current")
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid = auth(), None
        calls = []

        async def model(messages, **kwargs):
            calls.append(True)
            outcome = (
                Blocked(reason="Provider declined this synthetic request")
                if terminal == "provider"
                else ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id=f"read-{len(calls)}",
                            name="task.query.v1",
                            arguments={"filter": {"title_contains": "n274-none"}},
                        ),
                    )
                )
            )
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-{len(calls)}",
                usage={},
                provider="Synthetic",
                model=ADMITTED_MODEL,
            )

        # Tight test-only lease exercises the real runner and service terminal path.
        async def bounded(messages, *, limits, **kwargs):
            return await run_read_loop(
                messages,
                limits=LoopLimits(4, 3, limits.max_serialized_bytes, limits.deadline),
                **kwargs,
            )

        monkeypatch.setattr(service, "openrouter_complete", model)
        monkeypatch.setattr(service, "run_read_loop", bounded)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                await db.commit()
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="n274-source", content="Đọc tập synthetic này."
                    ),
                )
                await db.commit()
                message = view["messages"][-1]
                expected = "agent_loop_stop" if terminal == "system" else "provider_text"
                assert message["provenance"]["producer_code"] == expected
                assert message["provenance"]["origin"] == (
                    "server_notice" if terminal == "system" else "model_answer"
                )
                assert view["runs"][-1]["error_code"] == (
                    "no_progress" if terminal == "system" else "provider_blocked"
                )
                feedback = await service.save_feedback(
                    db,
                    actor,
                    cid,
                    service.FeedbackCreate(
                        client_id="n274-source-feedback",
                        target_type="turn",
                        target_id=str(message["id"]),
                        comment="Synthetic state feedback",
                    ),
                )
                bundle = await evidence.read_evidence(
                    db,
                    await db.get(MimiConversation, cid),
                    UUID(feedback["evidence_bundle_ids"][0]),
                )
                captured = next(
                    m for m in bundle["content"]["messages"] if m["id"] == str(message["id"])
                )
                assert captured["provenance"]["producer_code"] == expected
                assert bundle["metadata"]["target_id"] == str(message["id"])
                await db.commit()
        finally:
            if cid:
                await cleanup(maker, cid, [])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
