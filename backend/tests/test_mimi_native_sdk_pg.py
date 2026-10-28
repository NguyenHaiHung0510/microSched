"""Actual service/context->fake transport->selection->collection->confirm journey."""

import asyncio
import json
from pathlib import Path
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


@pytest.mark.parametrize("streaming", [False, True])
def test_actual_sdk_langgraph_pg_collection_confirm_and_idempotency(pg_dsn, monkeypatch, streaming):
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("MIMI_CONTEXT_V1_ENABLED", "1")
    monkeypatch.setenv("MIMI_STANDARD_API_KEY", "synthetic-never-sent")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    monkeypatch.setenv("MIMI_ROUTE_PROVIDER", "deepinfra")
    monkeypatch.setenv("MIMI_ROUTE_QUANTIZATION", "fp8")
    monkeypatch.setenv("MIMI_ROUTE_MAX_INPUT_PRICE", "0.2")
    monkeypatch.setenv("MIMI_ROUTE_MAX_OUTPUT_PRICE", "0.6")
    monkeypatch.setenv("MIMI_ROUTE_MODE", "native")
    import os

    from sqlalchemy.engine import make_url

    app_url = os.environ["MIMI_LANGGRAPH_APP_DATABASE_URL"]
    parsed = make_url(app_url)
    assert (parsed.host, parsed.port, parsed.database, parsed.username) == (
        "127.0.0.1",
        21887,
        "mimi086_qa",
        "microsched_app",
    )
    monkeypatch.setenv("MIMI_RUNNER", "langgraph")
    monkeypatch.setenv("MIMI_TRANSPORT", "openai_sdk")
    monkeypatch.setenv("MIMI_TEXT_RESPONSE_FORMAT", "natural")
    monkeypatch.setenv("DATABASE_URL", app_url)
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
            assert kwargs["settings"].mimi_route_model == "deepseek/deepseek-v4.1-flash-1017"
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
                model="deepseek/deepseek-v4.1-flash-1017",
            )

        import httpx2

        from app.agent import openai_sdk

        original_client = openai_sdk._client
        wires = []
        failures = []
        original_graph = service._run_langgraph_agent

        async def diagnose_graph(*args, **kwargs):
            try:
                return await original_graph(*args, **kwargs)
            except Exception as error:
                failures.append(type(error).__name__)
                cause = error.__cause__ or error.__context__
                while cause is not None and len(failures) < 10:
                    failures.append(type(cause).__name__)
                    if isinstance(cause, AttributeError):
                        import traceback

                        failures.append(str(cause)[:150])
                        failures.extend(
                            f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                            for frame in traceback.extract_tb(cause.__traceback__)[-4:]
                        )
                    if isinstance(cause, (ValueError, AssertionError)):
                        failures.append(str(cause)[:200])
                    cause = cause.__cause__ or cause.__context__
                if isinstance(error, (ValueError, AssertionError)):
                    failures.append(str(error)[:200])
                raise

        monkeypatch.setattr(service, "_run_langgraph_agent", diagnose_graph)

        async def handler(request):
            wire = json.loads(request.content)
            wires.append(wire)
            assert not {"only", "order", "sort"} & wire["provider"].keys()
            assert wire["provider"]["allow_fallbacks"] is True
            assert "max_tokens" not in wire and "max_completion_tokens" not in wire
            assert wire["provider"]["zdr"] and wire["provider"]["data_collection"] == "deny"
            assert wire["store"] is False
            assert wire["session_id"] == service._provider_session_id(cid)
            result = await fake(wire["messages"], settings=get_settings())
            outcome = result.outcome
            requests = (
                [(r.name, r.arguments) for r in outcome.requests]
                if isinstance(outcome, ToolRequests)
                else [(outcome.tool, outcome.arguments)]
            )
            native = [
                {
                    "index": i,
                    "id": f"native-{len(wires)}-{i}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
                for i, (name, args) in enumerate(requests)
            ]
            if not wire["stream"]:
                return httpx2.Response(
                    200,
                    json={
                        "id": result.response_id,
                        "object": "chat.completion",
                        "created": 1,
                        "model": wire["model"],
                        "provider": "DeepInfra",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": native,
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 800,
                            "completion_tokens": 100,
                            "total_tokens": 900,
                            "cost": 0,
                            "prompt_tokens_details": {"cached_tokens": 0},
                        },
                    },
                )
            chunks = [
                {
                    "id": result.response_id,
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": wire["model"],
                    "provider": "DeepInfra",
                    "choices": [
                        {"index": 0, "delta": {"tool_calls": native}, "finish_reason": "tool_calls"}
                    ],
                },
                {
                    "id": result.response_id,
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": wire["model"],
                    "provider": "DeepInfra",
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 800,
                        "completion_tokens": 100,
                        "total_tokens": 900,
                        "cost": 0,
                        "prompt_tokens_details": {"cached_tokens": 0},
                    },
                },
            ]
            body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
            return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})

        def sdk_client(settings, *, api_key, client):
            assert client is None
            return original_client(
                settings,
                api_key=api_key,
                client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
            )

        monkeypatch.setattr(openai_sdk, "_client", sdk_client)

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
                    provider_stream=streaming,
                )
                await db.commit()
                print("NATIVE_DIAGNOSTIC", failures)
                assert view["runs"][-1]["state"] == "waiting_confirmation" and len(calls) == 3, {
                    "state": view["runs"][-1]["state"],
                    "error": view["runs"][-1].get("error_code"),
                    "wires": len(wires),
                    "calls": len(calls),
                    "failures": failures,
                }
                assert len(wires) == 3 and all(
                    w["messages"][:2] == wires[0]["messages"][:2] for w in wires
                )
                replay = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="journey086",
                        content="Đổi độ ưu tiên các Task Synthetic journey thành p1",
                        expected_generation=1,
                    ),
                )
                assert len(wires) == 3 and replay["runs"][-1]["id"] == view["runs"][-1]["id"]
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
                second = await service.confirm_change_set(
                    db,
                    actor,
                    UUID(str(change["id"])),
                    service.ConfirmationDecision(
                        digest=change["digest"], nonce=change["nonce"], decision="confirm"
                    ),
                    "journey-confirm086",
                )
                assert second["id"] == result["id"]
                assert all(
                    t.priority == "p1"
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                )
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

    from app.core.qa_event_loop import selector_loop_factory

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
