"""Actual service/context->fake transport->selection->collection->confirm journey."""

import asyncio
import json
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup, local_contract  # noqa: F401

from app.agent import service
from app.agent.context import PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent
from app.agent.openrouter import AgentCompletion
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


def test_current_serializer_fake_collection_journey_and_causal_request_capture(pg_dsn, monkeypatch):
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("MIMI_CONTEXT_V1_ENABLED", "1")
    monkeypatch.setenv("MIMI_STANDARD_API_KEY", "synthetic-never-sent")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setenv("MIMI_ROUTE_PROVIDER", "deepinfra")
    monkeypatch.setenv("MIMI_ROUTE_QUANTIZATION", "fp8")
    monkeypatch.setenv("MIMI_ROUTE_MAX_INPUT_PRICE", "0.2")
    monkeypatch.setenv("MIMI_ROUTE_MAX_OUTPUT_PRICE", "0.6")
    monkeypatch.setenv("MIMI_ROUTE_MODE", "exact")
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor = auth()
        cid = None
        ids = []
        calls = []
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)

        async def fake(messages, **kwargs):
            calls.append(messages)
            authority = json.loads(
                next(
                    m["content"]
                    for m in reversed(messages)
                    if m["role"] == "system" and "authority_envelope" in m["content"]
                )
            )
            assert authority["authority_envelope"]["allowed_tools"]
            assert kwargs["settings"].mimi_route_model == "deepseek/deepseek-v4.1-flash"
            turn = len(calls)
            if turn == 1:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="qa-query",
                            name="task.query.v1",
                            arguments={
                                "filter": {"title_contains": "Synthetic journey"},
                                "projection": ["id", "title"],
                                "limit": 50,
                            },
                        ),
                    )
                )
            elif turn == 2:
                rows = json.loads(messages[-1]["content"])["rows"]
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="qa-selection",
                            name="task.freeze_selection.v1",
                            arguments={
                                "intent": "Đổi ưu tiên",
                                "variants_considered": ["Synthetic journey"],
                                "members": [
                                    {
                                        "id": r["id"],
                                        "classification": "included",
                                        "reason": "Đúng Task tổng hợp",
                                    }
                                    for r in rows
                                ],
                            },
                        ),
                    )
                )
            else:
                selection = json.loads(messages[-1]["content"])["selection"]
                outcome = PreviewCandidate(
                    tool="task.collection_candidate.v1",
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
                )
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-journey-{turn}",
                usage={},
                provider="Synthetic",
                model="deepseek/deepseek-v4.1-flash",
            )

        monkeypatch.setattr(service, "openrouter_complete", fake)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                conv = await db.get(MimiConversation, cid)
                conv.route_config = {
                    "profile_id": "deepseek",
                    "effort": "high",
                    "input_tokens": 100000,
                    "routing_mode": "exact",
                }
                tasks = [Task(title=f"Synthetic journey{i}") for i in range(2)]
                db.add_all(tasks)
                await db.flush()
                ids = [t.id for t in tasks]
                await db.commit()
            async with maker() as db:
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="journey086",
                        content="Đổi độ ưu tiên các Task Synthetic journey thành p1",
                        expected_generation=1,
                    ),
                )
                await db.commit()
                assert view["runs"][-1]["state"] == "waiting_confirmation" and len(calls) == 3
                assert all(
                    t.priority is None
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                )
                change = view["change_sets"][-1]
                rid = UUID(str(view["runs"][-1]["id"]))
                snapshots = (
                    await db.scalars(
                        select(MimiEvent).where(
                            MimiEvent.run_id == rid, MimiEvent.kind == "provider.request_context"
                        )
                    )
                ).all()
                assert len(snapshots) == 3
                assert all("Synthetic journey" not in json.dumps(e.payload) for e in snapshots)
                assert "selection" in json.dumps(calls[-1], ensure_ascii=False)
            async with maker() as db:
                result = await service.confirm_change_set(
                    db,
                    actor,
                    UUID(str(change["id"])),
                    service.ConfirmationDecision(
                        digest=change["digest"], nonce=change["nonce"], decision="confirm"
                    ),
                    "journey-confirm086",
                )
                await db.commit()
                assert result["result"]["count"] == 2 and len(calls) == 3
                feedback = await service.save_feedback(
                    db,
                    actor,
                    cid,
                    service.FeedbackCreate(
                        client_id="journey-feedback086",
                        target_type="run",
                        target_id=str(rid),
                        comment="Đúng selection",
                    ),
                )
                from app.agent.evidence import read_evidence

                bundle = await read_evidence(
                    db,
                    await db.get(MimiConversation, cid),
                    UUID(feedback["evidence_bundle_ids"][0]),
                )
                assert len(bundle["content"]["request_contexts"]) == 3
                assert (
                    bundle["content"]["request_contexts"][0]["body"]["manifest"]["policy_id"]
                    == "mimi-standard-v3"
                )
                await db.commit()
        finally:
            if cid:
                await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
