"""Owner75 additive producer binding, atomicity and honest unknown contracts.

Opt-in violation hooks affect test context only; never the application runtime.
Each fixture owns fresh UUIDs on a disposable localhost database.
"""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401

from app.agent import crypto, evidence, service
from app.agent import message_provenance as provenance
from app.agent.models import (
    MimiConversation,
    MimiEvent,
    MimiMessage,
    MimiNotificationIntent,
    MimiProviderCall,
    MimiRun,
)
from app.core.database_urls import async_postgres_url

pytestmark = pytest.mark.pg


async def fixture_scenario(pg_dsn, action):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    actor = auth()
    cid = None
    try:
        async with maker() as db:
            view = await service.create_conversation(db, actor, service.ConversationCreate())
            cid, rid = view["id"], uuid7()
            db.add(
                MimiRun(
                    id=rid,
                    conversation_id=cid,
                    generation=1,
                    state="running",
                    deadline=datetime.now(UTC) + timedelta(minutes=15),
                )
            )
            await db.commit()
        await action(maker, actor, cid, rid)
    finally:
        if cid:
            async with maker() as db:
                await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                await db.commit()
        await engine.dispose()


async def append(db, cid, rid, code="provider_terminal", text="Cùng một nội dung.", call_id=None):
    conv = await db.get(MimiConversation, cid)
    return await service._add_assistant_message(
        db,
        conv,
        rid,
        crypto.unwrap_dek(conv.dek_wrapped),
        text,
        producer_code=code,
        provider_call_id=call_id,
    )


async def provenance_event(db, rid, message):
    digest = provenance.binding_hash(message.conversation_id, rid, message.id, message.sequence)
    return (
        await db.scalars(
            select(MimiEvent).where(
                MimiEvent.run_id == rid,
                MimiEvent.kind == provenance.KIND,
                MimiEvent.payload["binding_sha256"].astext == digest,
            )
        )
    ).one()


def test_same_prose_exact_model_call_and_server_producer(pg_dsn):
    async def action(maker, actor, cid, rid):
        async with maker() as db:
            call = MimiProviderCall(
                id=uuid7(),
                run_id=rid,
                attempt=1,
                state="succeeded",
                request_fingerprint="synthetic75",
                route={"purpose": "main"},
            )
            db.add(call)
            await db.flush()
            model = await append(db, cid, rid, "provider_text", call_id=call.id)
            server = await append(db, cid, rid)
            event = await provenance_event(db, rid, model)
            body = json.loads(
                crypto.open_content(
                    crypto.unwrap_dek((await db.get(MimiConversation, cid)).dek_wrapped),
                    event.payload["body_ciphertext"],
                    aad=crypto.event_content_aad(rid, event.sequence, provenance.KIND),
                )
            )
            assert body["message_id"] == str(model.id) and body["provider_call_id"] == str(call.id)
            assert set(event.payload) == {"schema_version", "binding_sha256", "body_ciphertext"}
            assert "Cùng một nội dung" not in json.dumps(event.payload, ensure_ascii=False)
            await db.commit()
        async with maker() as db:
            view = await service.conversation_view(db, actor, cid)
            by_id = {m["id"]: m for m in view["messages"]}
            assert by_id[model.id]["content"] == by_id[server.id]["content"]
            assert by_id[model.id]["provenance"]["origin"] == "model_answer"
            assert by_id[server.id]["provenance"]["origin"] == "server_notice"
            assert all("body_ciphertext" not in e["payload"] for e in view["events"])
            before = await db.scalar(
                select(func.count()).select_from(MimiMessage).where(MimiMessage.run_id == rid)
            )
            with pytest.raises(ValueError, match="cannot_borrow"):
                await append(db, cid, rid, call_id=call.id)
            with pytest.raises(ValueError, match="provider_binding_invalid"):
                await append(db, cid, rid, "provider_text", call_id=uuid7())
            call = await db.get(MimiProviderCall, call.id)
            call.route = {"purpose": "compaction"}
            with pytest.raises(ValueError, match="provider_binding_invalid"):
                await append(db, cid, rid, "provider_text", call_id=call.id)
            call.route = {"purpose": "main"}
            call.state = "unknown"
            read = await service.conversation_view(db, actor, cid)
            assert read["messages"][0]["provenance"]["origin"] == "unknown"
            assert before == await db.scalar(
                select(func.count()).select_from(MimiMessage).where(MimiMessage.run_id == rid)
            )
            await db.rollback()

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_historical_unknown_and_exact_binding_beyond_public_event_bound(pg_dsn):
    async def action(maker, actor, cid, rid):
        async with maker() as db:
            conv = await db.get(MimiConversation, cid)
            dek = crypto.unwrap_dek(conv.dek_wrapped)
            legacy = MimiMessage(
                id=uuid7(),
                conversation_id=cid,
                run_id=rid,
                sequence=1,
                role="assistant",
                content_ciphertext=crypto.seal_content(
                    dek, "Old route error", aad=crypto.message_aad(cid, 1, "assistant")
                ),
                content_bytes=15,
                content_sha256=hashlib.sha256(b"Old route error").hexdigest(),
            )
            db.add(legacy)
            conv.next_message_sequence = 2
            for sequence in range(1, 131):
                db.add(
                    MimiEvent(run_id=rid, sequence=sequence, kind="synthetic.padding", payload={})
                )
            await db.flush()
            current = await append(db, cid, rid, text="Old route error")
            await db.commit()
        async with maker() as db:
            view = await service.conversation_view(db, actor, cid)
            assert len(view["events"]) == 100 and all(
                e["kind"] != provenance.KIND for e in view["events"]
            )
            assert view["messages"][0]["provenance"] == provenance.unknown()
            assert (
                view["messages"][1]["id"] == current.id
                and view["messages"][1]["provenance"]["origin"] == "server_notice"
            )
            conv = await db.get(MimiConversation, cid)
            conv.is_private = True
            conv.sensitivity = "private"
            assert (
                await provenance.read_message_provenance(
                    db, conv, [current], crypto.unwrap_dek(conv.dek_wrapped)
                )
            )[current.id] == provenance.unknown()
            await db.rollback()

    asyncio.run(fixture_scenario(pg_dsn, action))


@pytest.mark.parametrize(
    "mutation",
    [
        "message_id",
        "message_sequence",
        "run_id",
        "conversation_id",
        "producer_code",
        "producer_version",
        "origin",
        "provider_call_id",
        "aad",
    ],
)
def test_unverified_binding_never_classifies(pg_dsn, monkeypatch, mutation):
    if os.environ.get("OWNER75_TEST_VIOLATION") == "binding":

        def ignore_binding(event, message, conversation, dek):
            return json.loads(
                crypto.open_content(
                    dek,
                    event.payload["body_ciphertext"],
                    aad=crypto.event_content_aad(event.run_id, event.sequence, provenance.KIND),
                )
            )

        monkeypatch.setattr(provenance, "decode_binding", ignore_binding)

    async def action(maker, actor, cid, rid):
        async with maker() as db:
            message = await append(db, cid, rid)
            conv = await db.get(MimiConversation, cid)
            dek = crypto.unwrap_dek(conv.dek_wrapped)
            event = await provenance_event(db, rid, message)
            body = json.loads(
                crypto.open_content(
                    dek,
                    event.payload["body_ciphertext"],
                    aad=crypto.event_content_aad(rid, event.sequence, provenance.KIND),
                )
            )
            alterations = {
                "message_id": str(uuid7()),
                "message_sequence": True,
                "run_id": str(uuid7()),
                "conversation_id": str(uuid7()),
                "producer_code": "not_allowlisted",
                "producer_version": True,
                "origin": "model_answer",
                "provider_call_id": str(uuid7()),
            }
            if mutation != "aad":
                body[mutation] = alterations[mutation]
            event.payload = {
                **event.payload,
                "body_ciphertext": crypto.seal_content(
                    dek,
                    json.dumps(body),
                    aad="synthetic-wrong-aad"
                    if mutation == "aad"
                    else crypto.event_content_aad(rid, event.sequence, provenance.KIND),
                ),
            }
            await db.commit()
        async with maker() as db:
            view = await service.conversation_view(db, actor, cid)
            assert view["messages"][0]["provenance"] == provenance.unknown(), (
                "OWNER75_BINDING_GUARD_REQUIRED"
            )
            assert view["messages"][0]["content"] == "Cùng một nội dung."

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_duplicate_binding_cannot_hide_other_exact_message(pg_dsn):
    async def action(maker, actor, cid, rid):
        async with maker() as db:
            first = await append(db, cid, rid)
            event = await provenance_event(db, rid, first)
            for sequence in range(2, 133):
                db.add(
                    MimiEvent(
                        run_id=rid,
                        sequence=sequence,
                        kind=provenance.KIND,
                        payload=dict(event.payload),
                    )
                )
            await db.flush()
            second = await append(db, cid, rid)
            await db.commit()
        async with maker() as db:
            view = await service.conversation_view(db, actor, cid)
            assert view["messages"][0]["provenance"]["origin"] == "unknown"
            assert (
                view["messages"][1]["id"] == second.id
                and view["messages"][1]["provenance"]["origin"] == "server_notice"
            )

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_message_event_pair_rolls_back_even_when_outer_handler_commits(pg_dsn, monkeypatch):
    async def broken_event(*args, **kwargs):
        raise ValueError("synthetic-event-write-failed")

    monkeypatch.setattr(service, "_append_event", broken_event)
    if os.environ.get("OWNER75_TEST_VIOLATION") == "atomic":

        async def missing_savepoint(db, conversation, run_id, dek, content, **kwargs):
            db.add(
                MimiMessage(
                    id=uuid7(),
                    conversation_id=conversation.id,
                    run_id=run_id,
                    sequence=conversation.next_message_sequence,
                    role="assistant",
                    content_bytes=len(content.encode()),
                    content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                    content_ciphertext=crypto.seal_content(
                        dek,
                        content,
                        aad=crypto.message_aad(
                            conversation.id, conversation.next_message_sequence, "assistant"
                        ),
                    ),
                )
            )
            conversation.next_message_sequence += 1
            await db.flush()
            raise ValueError("synthetic-event-write-failed")

        monkeypatch.setattr(provenance, "append_message", missing_savepoint)

    async def action(maker, actor, cid, rid):
        async with maker() as db:
            with pytest.raises(ValueError, match="synthetic-event-write-failed"):
                await append(db, cid, rid)
            await db.commit()  # imitates an enclosing handler recording its terminal
        async with maker() as db:
            count = await db.scalar(
                select(func.count()).select_from(MimiMessage).where(MimiMessage.run_id == rid)
            )
            assert count == 0, "OWNER75_ATOMIC_PAIR_REQUIRED"
            assert (await db.get(MimiConversation, cid)).next_message_sequence == 1
            assert (
                await db.scalar(
                    select(func.count()).select_from(MimiEvent).where(MimiEvent.run_id == rid)
                )
                == 0
            )

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_owner_bound_api_cannot_expose_foreign_message_provenance(pg_dsn, monkeypatch):
    original = service._conversation

    async def action(maker, actor, cid, rid):
        async with maker() as db:
            await append(db, cid, rid)
            await db.commit()
        if os.environ.get("OWNER75_TEST_VIOLATION") == "owner":

            async def bypass_owner(db, _foreign, conversation_id, **kwargs):
                return await original(db, actor, conversation_id, **kwargs)

            monkeypatch.setattr(service, "_conversation", bypass_owner)
        foreign = auth()
        foreign.user_email = "foreign@example.test"
        async with maker() as db:
            blocked = False
            try:
                await service.conversation_view(db, foreign, cid)
            except HTTPException as exc:
                blocked = exc.status_code == 404
            assert blocked, "OWNER75_OWNER_BOUND_READ_REQUIRED"

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_provenance_does_not_trigger_notification_and_retains_causal_feedback(pg_dsn):
    async def action(maker, actor, cid, rid):
        async with maker() as db:
            first = await append(db, cid, rid, "local_deterministic_result")
            (await db.get(MimiRun, rid)).state = "completed"
            await service._append_event(db, rid, "run.terminal", {"state": "completed"})
            before = await db.scalar(
                select(func.count())
                .select_from(MimiNotificationIntent)
                .where(MimiNotificationIntent.run_id == rid)
            )
            assert before == 1
            await append(db, cid, rid, "process_loss_recovery")
            assert before == await db.scalar(
                select(func.count())
                .select_from(MimiNotificationIntent)
                .where(MimiNotificationIntent.run_id == rid)
            )
            conv = await db.get(MimiConversation, cid)
            bundle = await evidence.capture_feedback(db, conv, "turn", str(first.id), [])
            read = await evidence.read_evidence(db, conv, bundle.id)
            assert bundle.capture_status == "complete"
            assert read["metadata"]["target_id"] == str(first.id)
            assert any(e["kind"] == provenance.KIND for e in read["content"]["event_refs"])
            assert "body_ciphertext" not in json.dumps(read["content"]["event_refs"])
            await db.rollback()

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_actual_transport_and_restart_sources(pg_dsn, monkeypatch):
    from app.agent.context import AssistantText
    from app.agent.openrouter import AgentCompletion
    from app.core.settings import get_settings

    for name, value in {
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_STANDARD_API_KEY": "synthetic-not-sent",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash",
        "MIMI_ROUTE_PROVIDER": "deepinfra",
        "MIMI_ROUTE_QUANTIZATION": "fp8",
        "MIMI_ROUTE_REASONING_EFFORT": "low",
        "MIMI_ROUTE_MODE": "exact",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    calls = []

    async def completion(*args, **kwargs):
        calls.append(1)
        return AgentCompletion(
            outcome=AssistantText(text="Cùng một nội dung."),
            response_id="synthetic75-transport",
            usage={},
            provider="Synthetic",
            model="deepseek/deepseek-v4.1-flash",
        )

    monkeypatch.setattr(service, "openrouter_complete", completion)

    async def action(maker, actor, cid, rid):
        async with maker() as db:
            # Remove only the fixture's unused run before the real send path.
            await db.execute(delete(MimiRun).where(MimiRun.id == rid))
            await db.commit()
        async with maker() as db:
            view = await service.send_message(
                db,
                actor,
                cid,
                service.MessageCreate(
                    client_id="synthetic75-turn", content="Chào Mimi", expected_generation=1
                ),
            )
            await db.commit()
            model = view["messages"][-1]
            assert model["provenance"]["origin"] == "model_answer"
            assert model["provenance"]["producer_code"] == "provider_text" and len(calls) == 1
            call = (
                await db.scalars(
                    select(MimiProviderCall).where(MimiProviderCall.run_id == model["run_id"])
                )
            ).one()
            event = await provenance_event(
                db, model["run_id"], await db.get(MimiMessage, model["id"])
            )
            conv = await db.get(MimiConversation, cid)
            body = provenance.decode_binding(
                event,
                await db.get(MimiMessage, model["id"]),
                conv,
                crypto.unwrap_dek(conv.dek_wrapped),
            )
            assert body["provider_call_id"] == call.id
            restart = MimiRun(
                id=uuid7(),
                conversation_id=cid,
                generation=conv.generation,
                state="running",
                deadline=datetime.now(UTC) + timedelta(minutes=15),
            )
            db.add(restart)
            await db.flush()
            db.add(
                MimiProviderCall(
                    id=uuid7(),
                    run_id=restart.id,
                    attempt=1,
                    state="succeeded",
                    request_fingerprint="synthetic75-restart",
                    route={"run_guard_version": 1},
                )
            )
            conv.generation += 1
            await db.commit()
        monkeypatch.setattr(service, "get_engine", lambda: maker.kw["bind"])
        async with maker() as db:
            assert await service.reconcile_orphaned_mimi_runs(db) == 1
            await db.commit()
        async with maker() as db:
            result = await service.conversation_view(db, actor, cid)
            assert result["messages"][-1]["provenance"]["producer_code"] == "process_loss_recovery"
            assert result["messages"][-1]["provenance"]["origin"] == "server_notice"
            assert len(calls) == 1  # startup recovery never dispatches a provider

    asyncio.run(fixture_scenario(pg_dsn, action))


def test_actual_collection_confirm_and_undo_sources(pg_dsn):
    from test_mimi_collection_service_pg import cleanup, prepare

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, change_id, decision = await prepare(maker)
        try:
            async with maker() as db:
                view = await service.conversation_view(db, actor, cid)
                assert view["messages"][-1]["provenance"]["producer_code"] == "preview_prepared"
                result = await service.confirm_change_set(
                    db, actor, change_id, decision, "synthetic75-confirm"
                )
                await db.commit()
            async with maker() as db:
                receipt = (
                    await db.scalars(
                        select(service.MimiExecutionReceipt).where(
                            service.MimiExecutionReceipt.change_set_id == change_id
                        )
                    )
                ).one()
                assert result["result"]["count"] == 2
                view = await service.conversation_view(db, actor, cid)
                assert view["messages"][-1]["provenance"]["producer_code"] == "collection_committed"
                inverse = await service.prepare_receipt_undo(db, actor, receipt.id)
                await db.commit()
                assert inverse["messages"][-1]["provenance"]["producer_code"] == "undo_prepared"
                assert inverse["messages"][-1]["provenance"]["origin"] == "server_notice"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiProviderCall)
                        .where(MimiProviderCall.run_id == rid)
                    )
                    == 0
                )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
