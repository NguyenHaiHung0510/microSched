"""Exercise Calendar text and Resume through the real service, with zero provider I/O."""

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401

from app.agent import config_policy, crypto, service
from app.agent.compaction import CheckpointSource, make_checkpoint
from app.agent.context import AssistantText, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiProviderCall, MimiRun
from app.agent.openrouter import AgentCompletion
from app.agent.policy import load_standard_policy
from app.agent.tools.calendar_reads import CALENDAR_READ_TOOL, execute_calendar_tool
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AppSetting, DayAnnotation

pytestmark = pytest.mark.pg


def test_calendar_resume_rereads_after_a_previously_empty_complete_page(pg_dsn, monkeypatch):
    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    for key, value in {
        "MIMI_CALENDAR_READ_ENABLED": "1",
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_NOTIFICATIONS_ENABLED": "0",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODE": "native",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash-1017",
        "MIMI_ROUTE_REASONING_EFFORT": "none",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
        "MIMI_TRANSPORT": "httpx",
        "MIMI_RUNNER": "current",
    }.items():
        monkeypatch.setenv(key, value)
    policy_key = f"mimi.calendar.test.{uuid7()}"
    monkeypatch.setattr(config_policy, "POLICY_KEY", policy_key)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor = auth()
        cid = None
        marker_id = uuid7()
        parent_id = uuid7()
        calls = []
        day = date(2091, 3, 4)
        args = {"date": str(day), "kinds": ["annotation"]}
        label = "Synthetic annotation added before Resume"
        old_answer = "Synthetic stale answer: the day is empty."
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)

        async def fake(messages, **kwargs):
            authority = json.loads(
                next(
                    m["content"]
                    for m in reversed(messages)
                    if m["role"] == "system" and "authority_envelope" in m["content"]
                )
            )["authority_envelope"]
            assert CALENDAR_READ_TOOL in authority["allowed_tools"]
            assert old_answer not in json.dumps(messages)
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                assert not any(m["role"] == "tool" for m in messages)
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="calendar-fresh", name=CALENDAR_READ_TOOL, arguments=args
                        ),
                    )
                )
            else:
                result = json.loads(messages[-1]["content"])
                assert result["coverage"] == "complete"
                assert [r["id"] for r in result["rows"]] == [str(marker_id)]
                assert result["rows"][0]["label"] == label
                outcome = AssistantText(text=f"Lịch có ghi chú: {label}")
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-calendar-{len(calls)}",
                usage={},
                provider="Synthetic",
                model=kwargs["settings"].mimi_route_model,
            )

        monkeypatch.setattr(service, "openrouter_complete", fake)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                conv = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conv.dek_wrapped)
                now = datetime.now(UTC)
                db.add(
                    MimiRun(
                        id=parent_id,
                        conversation_id=cid,
                        generation=conv.generation,
                        state="halted",
                        error_code="owner_paused",
                        provider_outcome="succeeded",
                        deadline=now + timedelta(minutes=1),
                        completed_at=now,
                    )
                )
                await db.flush()
                user_text = "Lịch ngày 2091-03-04 có ghi chú gì?"
                db.add(
                    MimiMessage(
                        conversation_id=cid,
                        run_id=parent_id,
                        role="user",
                        sequence=1,
                        content_ciphertext=crypto.seal_content(
                            dek,
                            user_text,
                            aad=crypto.message_aad(cid, 1, "user"),
                        ),
                        content_sha256=hashlib.sha256(user_text.encode()).hexdigest(),
                        content_bytes=len(user_text.encode()),
                    )
                )
                conv.generation += 1
                db.add(
                    MimiMessage(
                        conversation_id=cid,
                        run_id=parent_id,
                        role="assistant",
                        sequence=2,
                        content_ciphertext=crypto.seal_content(
                            dek, old_answer, aad=crypto.message_aad(cid, 2, "assistant")
                        ),
                        content_sha256=hashlib.sha256(old_answer.encode()).hexdigest(),
                        content_bytes=len(old_answer.encode()),
                    )
                )
                conv.next_message_sequence = 3
                old_result = await execute_calendar_tool(
                    db, CALENDAR_READ_TOOL, args, settings=get_settings()
                )
                assert old_result["coverage"] == "complete" and old_result["rows"] == []
                db.add(
                    MimiEvent(
                        run_id=parent_id,
                        sequence=1,
                        kind="tool.read_result",
                        payload={
                            "tool": CALENDAR_READ_TOOL,
                            "arguments_sha256": service._canonical_digest(args),
                            "result_sha256": service._canonical_digest(old_result),
                            "body_ciphertext": crypto.seal_content(
                                dek,
                                json.dumps({"arguments": args, "result": old_result}),
                                aad=crypto.event_content_aad(parent_id, 1, "tool.read_result"),
                            ),
                        },
                    )
                )
                await db.flush()
                history_rows = list(
                    await db.scalars(
                        select(MimiMessage)
                        .where(MimiMessage.conversation_id == cid)
                        .order_by(MimiMessage.sequence)
                    )
                )
                checkpoint = make_checkpoint(
                    sources=[
                        CheckpointSource(
                            id=row.id,
                            sequence=row.sequence,
                            role=row.role,
                            content_sha256=row.content_sha256,
                            content=service._message_read(row, dek)["content"],
                            calendar_derived=row.role == "assistant",
                        )
                        for row in history_rows
                    ],
                    prior=None,
                    policy_sha256=load_standard_policy().sha256,
                    pending_preview=None,
                    pending_draft=None,
                )
                db.add(
                    MimiEvent(
                        run_id=parent_id,
                        sequence=2,
                        kind="context.checkpoint.activated",
                        payload={
                            "frontier": 2,
                            "content_sha256": service._canonical_digest(checkpoint),
                            "content_ciphertext": crypto.seal_content(
                                dek,
                                json.dumps(checkpoint),
                                aad=crypto.event_content_aad(
                                    parent_id, 2, "context.checkpoint.activated"
                                ),
                            ),
                        },
                    )
                )
                conv.context_frontier_sequence = 2
                terminal = AssistantText(text=old_answer).model_dump(mode="json")
                db.add(
                    MimiProviderCall(
                        run_id=parent_id,
                        attempt=1,
                        state="succeeded",
                        request_fingerprint=hashlib.sha256(b"calendar-old-terminal").hexdigest(),
                        route={},
                        usage={},
                        result={
                            "result_sha256": service._canonical_digest(terminal),
                            "terminal_ciphertext": crypto.seal_content(
                                dek,
                                json.dumps(terminal),
                                aad=crypto.provider_terminal_aad(parent_id, 1),
                            ),
                        },
                    )
                )
                db.add(DayAnnotation(id=marker_id, starts_on=day, ends_on=day, label=label))
                await db.commit()

            async with maker() as db:
                _, successor_id, request = await service.prepare_run_resume(db, actor, parent_id)
                await db.commit()
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    request,
                    parent_run_id=parent_id,
                    reserved_run_id=successor_id,
                    record_user_message=False,
                )
                assert calls == [1, 2]
                assert view["runs"][-1]["state"] == "completed"
                assert view["change_sets"] == []
                assert any(m["content"] == old_answer for m in view["messages"])
                successor = await db.get(MimiRun, successor_id)
                assert successor.source_versions == {}  # Calendar never binds Task write CAS.
                conv = await db.get(MimiConversation, cid)
                loaded, _ = await service._load_active_checkpoint(
                    db, conv, crypto.unwrap_dek(conv.dek_wrapped)
                )
                assert loaded == checkpoint and conv.context_frontier_sequence == 2
                events = list(
                    await db.scalars(select(MimiEvent).where(MimiEvent.run_id == successor_id))
                )
                restored = next(
                    e.payload for e in events if e.kind == "continuation.evidence_restored"
                )
                assert restored["calendar_refresh_required"] is True
                assert restored["read_receipts"] == 0
                assert any(
                    source["source_type"] == "microsched.calendar.standard"
                    for event in events
                    if event.kind == "context.manifest"
                    for source in event.payload["sources"]
                )
                await db.commit()
        finally:
            try:
                async with maker() as db:
                    if cid is not None:
                        await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                    await db.execute(delete(DayAnnotation).where(DayAnnotation.id == marker_id))
                    await db.execute(delete(AppSetting).where(AppSetting.key == policy_key))
                    await db.commit()
            finally:
                await engine.dispose()

    asyncio.run(scenario())
