"""Historical aggregates are opaque, not replayable current-eligibility evidence."""

import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup
from test_mimi_night_egress_pg import (
    BODY,
    CHILD,
    completion,
    configure,
    mutate,
    seed,
    send,
    summary,
    trigger_compaction,
)
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import service
from app.agent.context import AssistantText, ToolRequest, ToolRequests
from app.agent.models import MimiConversation
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.domain.models import Task

pytestmark = [pytest.mark.pg, pytest.mark.usefixtures("local_sync_contract")]


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("change", ["private", "delete", "empty"])
def test_aggregate_only_mixed_and_empty_history_withheld_truthfully(
    pg_dsn, monkeypatch, mixed, change
):
    configure(monkeypatch)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, tid, child = await seed(maker)
        stage, positive, safe = "read", [], []
        async with maker() as db:
            title = (await db.get(Task, tid)).title

        async def provider(messages, **kwargs):
            tools = [m for m in messages if m["role"] == "tool"]
            if stage == "read":
                if not tools:
                    requests = [
                        ToolRequest(
                            call_id="aggregate",
                            name="task.aggregate.v1",
                            arguments={
                                "group_by": "status",
                                "filter": {
                                    "title_contains": "never-" + uuid4().hex
                                    if change == "empty"
                                    else title
                                },
                            },
                        )
                    ]
                    if mixed:
                        requests.append(
                            ToolRequest(
                                call_id="content",
                                name="task.read_content.v1",
                                arguments={"id": str(tid)},
                            )
                        )
                    return completion(ToolRequests(requests=tuple(requests)))
                result = json.loads(
                    next(t["content"] for t in tools if t["tool_call_id"] == "aggregate")
                )
                assert sum(g["count"] for g in result["groups"]) == (0 if change == "empty" else 1)
                if mixed:
                    assert BODY in json.dumps(messages) and CHILD in json.dumps(messages)
                positive.append(result)
                return completion(AssistantText(text="Đã tổng hợp phạm vi được hỏi."))
            assert not tools
            if kwargs.get("summary_mode"):
                sources = json.loads(messages[-1]["content"])["sources"]
                assert not any(
                    s.get("working_history") and s["working_history"].get("messages")
                    for s in sources
                )
                safe.append("helper")
                return completion(summary())
            authority = next(
                json.loads(m["content"])
                for m in messages
                if m["role"] == "system" and "authority_envelope" in m["content"]
            )
            assert authority["context_manifest"]["working_history"]["coverage"] == "partial"
            assert BODY not in json.dumps(messages) and CHILD not in json.dumps(messages)
            safe.append("main")
            return completion(
                AssistantText(
                    text="Raw history thiếu lineage để kiểm lại; cần đọc mới nếu cần tổng hiện tại."
                )
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            await send(maker, actor, cid, "aggregate-first")
            assert positive
            if change != "empty":
                await mutate(maker, tid, child, change)
            stage = "history"
            async with maker() as db:
                await trigger_compaction(db, await db.get(MimiConversation, cid))
            await send(maker, actor, cid, "aggregate-history")
            assert "main" in safe and "helper" in safe
        finally:
            await cleanup(maker, cid, [tid])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
