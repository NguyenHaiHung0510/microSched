"""Synthetic DB journey: invalid selection batch -> corrected reads -> frozen preview."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_contracts import ADMITTED_MODEL
from test_mimi_collection_service_pg import auth, cleanup
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import langgraph_runner, service
from app.agent.context import PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiEvent, MimiProviderCall, MimiRun
from app.agent.openrouter import AgentCompletion, build_request
from app.agent.selection import SELECTION_TOOL
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("runner", ["current", "langgraph"])
@pytest.mark.usefixtures("local_sync_contract")
def test_missing_members_corrected_next_turn_materializes_preview_without_domain_write(
    pg_dsn, monkeypatch, runner
):
    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_RUNNER", runner)
    monkeypatch.setenv("MIMI_ROUTE_MODEL", ADMITTED_MODEL)
    if runner == "langgraph":
        real_graph = langgraph_runner.run_langgraph

        async def graph(*args, **kwargs):
            return await real_graph(*args, **kwargs, checkpointer_for_test=InMemorySaver())

        monkeypatch.setattr(langgraph_runner, "run_langgraph", graph)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor = auth()
        cid, ids = None, []
        prefix = f"synthetic-argument-repair-{uuid4().hex}"
        calls = []
        selection_args = {"intent": "Synthetic priority edit", "variants_considered": [prefix]}
        read_names, selections = [], []
        actual_read = service.execute_read_tool
        actual_selection = service.persist_selection

        async def read(db, name, arguments):
            read_names.append(name)
            return await actual_read(db, name, arguments)

        async def freeze(*args, **kwargs):
            selections.append(True)
            return await actual_selection(*args, **kwargs)

        async def model(messages, **kwargs):
            calls.append(build_request(messages, kwargs["settings"], agent_contract=True))
            turn = len(calls)
            if turn == 1:
                requests = (
                    ToolRequest(
                        call_id="query",
                        name="task.query.v1",
                        arguments={
                            "filter": {"title_contains": prefix},
                            "limit": 50,
                        },
                    ),
                )
            elif turn == 2:
                rows = json.loads(messages[-1]["content"])["rows"]
                assert {r["id"] for r in rows} == {str(tid) for tid in ids}
                requests = (
                    ToolRequest(
                        call_id="unexecuted-inspect",
                        name="task.inspect_batch.v1",
                        arguments={"ids": [str(tid) for tid in ids]},
                    ),
                    ToolRequest(
                        call_id="missing-members", name=SELECTION_TOOL, arguments=selection_args
                    ),
                )
            elif turn == 3:
                assert read_names == ["task.query.v1"] and not selections
                assert json.loads(messages[-1]["content"])["error"]["code"] == (
                    "invalid_read_arguments"
                )
                requests = (
                    ToolRequest(
                        call_id="unexecuted-inspect",
                        name="task.inspect_batch.v1",
                        arguments={"ids": [str(tid) for tid in ids]},
                    ),
                    ToolRequest(
                        call_id="correct-members",
                        name=SELECTION_TOOL,
                        arguments=selection_args
                        | {
                            "members": [
                                {
                                    "id": str(tid),
                                    "classification": "included",
                                    "reason": "Matches synthetic request",
                                }
                                for tid in ids
                            ]
                        },
                    ),
                )
            else:
                assert turn == 4 and len(selections) == 1
                selection = json.loads(messages[-1]["content"])["selection"]
                assert selection["semantic_complete"]
                return AgentCompletion(
                    outcome=PreviewCandidate(
                        tool=COLLECTION_CANDIDATE_TOOL,
                        arguments={
                            "selection_id": selection["selection_id"],
                            "entries": [
                                {
                                    "action": "edit",
                                    "id": r["id"],
                                    "expected_collection_version": r["collection_version"],
                                    "fields": {"priority": "p1"},
                                }
                                for r in selection["members"]
                            ],
                        },
                    ),
                    response_id="synthetic-preview",
                    usage={"cost": 0},
                    provider="Synthetic",
                    model="synthetic/model",
                )
            return AgentCompletion(
                outcome=ToolRequests(requests=requests),
                response_id=f"synthetic-{turn}",
                usage={"cost": 0},
                provider="Synthetic",
                model="synthetic/model",
            )

        monkeypatch.setattr(service, "openrouter_complete", model)
        monkeypatch.setattr(service, "execute_read_tool", read)
        monkeypatch.setattr(service, "persist_selection", freeze)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                tasks = [Task(title=f"{prefix}-{i}") for i in range(2)]
                db.add_all(tasks)
                await db.flush()
                for task in tasks:
                    await db.refresh(task)
                ids = [t.id for t in tasks]
                before = [t.model_dump() for t in tasks]
                await db.commit()
            async with maker() as db:
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="synthetic-argument-repair",
                        content=f"Đổi ưu tiên {prefix} thành p1",
                    ),
                )
                await db.commit()
                assert view["runs"][-1]["state"] == "waiting_confirmation", view["runs"][-1]
                assert len(view["change_sets"]) == 1 and len(calls) == 4
                run_id = UUID(str(view["runs"][-1]["id"]))
                provider_calls = (
                    await db.scalars(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == run_id)
                    )
                ).all()
                assert len(provider_calls) == 4
                assert {c.attempt for c in provider_calls} == {1, 2, 3, 4}
                assert all(c.state == "succeeded" for c in provider_calls)
                events = (
                    await db.scalars(select(MimiEvent).where(MimiEvent.run_id == run_id))
                ).all()
                assert sum(e.kind == "selection.frozen" for e in events) == 1
                assert sum(e.kind == "tool.read_result" for e in events) == 3
                assert read_names == ["task.query.v1", "task.inspect_batch.v1"]
                assert [(await db.get(Task, tid)).model_dump() for tid in ids] == before
                assert set((await db.get(MimiRun, run_id)).source_versions) == {
                    f"task:{tid}" for tid in ids
                }
        finally:
            if cid:
                await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
