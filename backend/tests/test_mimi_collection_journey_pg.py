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


def test_old_answer_feedback_exports_exact_causal_parts_after_newer_run(pg_dsn, monkeypatch):
    import os
    from datetime import UTC, datetime, timedelta
    from uuid import uuid7

    from fastapi import HTTPException
    from test_mimi_collection_service_pg import prepare

    from app.agent import crypto, evidence
    from app.agent.models import (
        MimiChangeSet,
        MimiEvidence,
        MimiExecutionReceipt,
        MimiMessage,
        MimiProviderCall,
        MimiRun,
    )

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, change_id, decision = await prepare(maker)
        expected_contexts, expected_reads, expected_calls = [], [], []
        try:
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conv.dek_wrapped)
                run = await db.get(MimiRun, rid)
                run.source_versions = {
                    f"task:{t.id}": str(t.collection_version)
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                }
                expected_versions = dict(run.source_versions)
                expected_lease = dict(run.execution_lease)
                change = await db.get(MimiChangeSet, change_id)
                operation = json.loads(
                    crypto.open_content(
                        dek, change.operation_ciphertext, aad=crypto.change_set_aad(cid, change_id)
                    )
                )
                for attempt in (1, 2):
                    body = {
                        "manifest": {"policy_id": "mimi-standard-v3", "run_id": str(rid)},
                        "messages": [{"role": "user", "content": f"original request {attempt}"}],
                        "attempt": attempt,
                    }
                    call = MimiProviderCall(
                        run_id=rid,
                        attempt=attempt,
                        state="succeeded",
                        request_fingerprint=evidence.digest(body),
                        route={"model": "deepseek/deepseek-v4.1-flash", "provider": "Synthetic"},
                        usage={"input_tokens": attempt, "output_tokens": 2},
                    )
                    db.add(call)
                    await db.flush()
                    expected_calls.append(
                        {
                            "id": str(call.id),
                            "attempt": attempt,
                            "state": "succeeded",
                            "route": dict(call.route),
                            "usage": dict(call.usage),
                            "request_fingerprint": call.request_fingerprint,
                        }
                    )
                    sequence = await service._append_event(db, rid, "provider.request_context", {})
                    event = (
                        await db.scalars(
                            select(MimiEvent).where(
                                MimiEvent.run_id == rid, MimiEvent.sequence == sequence
                            )
                        )
                    ).one()
                    event.payload = {
                        "body_ciphertext": crypto.seal_content(
                            dek,
                            json.dumps(body),
                            aad=crypto.event_content_aad(rid, sequence, event.kind),
                        )
                    }
                    expected_contexts.append(
                        {"event_id": str(event.id), "kind": event.kind, "body": body}
                    )
                for kind, body in (
                    (
                        "tool.read_result",
                        {
                            "tool": "task.query.v1",
                            "arguments": {"limit": 50},
                            "rows": [{"id": str(i)} for i in ids],
                        },
                    ),
                    (
                        "selection.frozen",
                        {
                            "selection_id": operation["args"]["selection_id"],
                            "members": [{"id": str(i)} for i in ids],
                        },
                    ),
                ):
                    sequence = await service._append_event(db, rid, kind, {})
                    event = (
                        await db.scalars(
                            select(MimiEvent).where(
                                MimiEvent.run_id == rid, MimiEvent.sequence == sequence
                            )
                        )
                    ).one()
                    event.payload = {
                        "body_ciphertext": crypto.seal_content(
                            dek, json.dumps(body), aad=crypto.event_content_aad(rid, sequence, kind)
                        )
                    }
                    expected_reads.append({"event_id": str(event.id), "kind": kind, "body": body})
                await service.confirm_change_set(
                    db, actor, change_id, decision, f"last-causal-{cid}"
                )
                await db.commit()
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conv.dek_wrapped)
                messages = (
                    await db.scalars(
                        select(MimiMessage)
                        .where(MimiMessage.run_id == rid)
                        .order_by(MimiMessage.sequence)
                    )
                ).all()
                old_answer = next(m for m in reversed(messages) if m.role == "assistant")
                expected_messages = [
                    {
                        "id": str(m.id),
                        "role": m.role,
                        "sequence": m.sequence,
                        "content": crypto.open_content(
                            dek,
                            m.content_ciphertext,
                            aad=crypto.message_aad(cid, m.sequence, m.role),
                        ),
                    }
                    for m in messages
                ]
                receipts = (
                    await db.scalars(
                        select(MimiExecutionReceipt).where(
                            MimiExecutionReceipt.change_set_id == change_id
                        )
                    )
                ).all()
                expected_receipts = [
                    {
                        "id": str(r.id),
                        "operation_id": str(r.operation_id),
                        "digest": r.digest_sha256,
                        "result": r.result,
                        "executed_at": r.executed_at.isoformat(),
                    }
                    for r in receipts
                ]
                events = (
                    await db.scalars(
                        select(MimiEvent)
                        .where(MimiEvent.run_id == rid)
                        .order_by(MimiEvent.sequence)
                    )
                ).all()
                expected_events = [
                    {
                        "id": str(e.id),
                        "sequence": e.sequence,
                        "kind": e.kind,
                        "payload_sha256": evidence.digest(e.payload),
                    }
                    for e in events
                ]
                later = MimiRun(
                    id=uuid7(),
                    conversation_id=cid,
                    generation=conv.generation,
                    state="completed",
                    source_versions={"later-only": "excluded"},
                    execution_lease={"later-only": True},
                    deadline=datetime.now(UTC) + timedelta(minutes=5),
                )
                conv.generation += 1
                db.add(later)
                await db.flush()
                await service._add_assistant_message(
                    db,
                    conv,
                    later.id,
                    dek,
                    "LATER_RUN_MUST_BE_EXCLUDED",
                    producer_code="preview_prepared",
                )
                db.add(
                    MimiProviderCall(
                        run_id=later.id,
                        attempt=1,
                        state="succeeded",
                        request_fingerprint="later-only",
                        route={"later-only": True},
                        usage={},
                    )
                )
                await service._append_event(
                    db, later.id, "synthetic.later", {"marker": "later-only"}
                )
                await db.commit()
                later_id, old_id = later.id, old_answer.id
            if os.environ.get("MIMI086_LAST_NEGATIVE") == "causal":

                async def misbound(*args):
                    return later_id

                monkeypatch.setattr(evidence, "target_run", misbound)
            payload = service.FeedbackCreate(
                client_id=f"last-old-answer-{cid}",
                target_type="turn",
                target_id=str(old_id),
                comment="Synthetic exact old causal set",
            )
            async with maker() as db:
                saved = await service.save_feedback(db, actor, cid, payload)
                bid = UUID(saved["evidence_bundle_ids"][0])
                bundle = await evidence.read_evidence(db, await db.get(MimiConversation, cid), bid)
                assert (await db.get(MimiEvidence, bid)).run_id == rid, (
                    "causal target run guard was bypassed"
                )
                assert bundle["capture_status"] == "complete"
                content = bundle["content"]
                assert content["messages"] == expected_messages
                assert content["calls"] == expected_calls
                assert content["source_versions"] == expected_versions and expected_versions
                assert content["execution_lease"] == expected_lease
                assert content["request_contexts"] == expected_contexts
                assert content["reads_and_selection"] == expected_reads
                assert content["operations"] == [operation]
                assert content["receipts"] == expected_receipts and expected_receipts
                assert content["event_refs"] == expected_events
                assert "LATER_RUN_MUST_BE_EXCLUDED" not in json.dumps(content)
                assert "later-only" not in json.dumps(content)
                assert bundle["metadata"]["target_id"] == str(old_id)
                assert bundle["metadata"]["hidden_reasoning"] == "EXCLUDED"
                assert bundle["metadata"]["provider_raw_response"] == "NOT_CAPTURED"
                await db.commit()
            async with maker() as db:
                replay = await service.save_feedback(db, actor, cid, payload)
                assert (
                    replay["id"] == saved["id"]
                    and replay["evidence_bundle_ids"] == saved["evidence_bundle_ids"]
                )
                with pytest.raises(HTTPException, match="not found"):
                    await service.save_feedback(
                        db,
                        actor.model_copy(update={"user_email": "foreign-last@example.test"}),
                        cid,
                        payload,
                    )
                conv = await db.get(MimiConversation, cid)
                with pytest.raises(HTTPException, match="causal_binding"):
                    await evidence.capture_feedback(db, conv, "run", str(later_id), [bid])
                await db.rollback()
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
