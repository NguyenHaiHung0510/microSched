"""Task099 isolated PostgreSQL binding, append, retained coverage and encryption."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, local_contract  # noqa: F401

from app.agent import crypto, service
from app.agent import response_timing as timing
from app.agent.models import (
    MimiConversation,
    MimiEvent,
    MimiFeedback,
    MimiMessage,
    MimiProviderCall,
    MimiRun,
)
from app.core.database_urls import async_postgres_url

pytestmark = pytest.mark.pg


def test_durable_concurrent_replay_all_retained_and_feedback_8000(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid = auth(), None
        try:
            async with maker() as db:
                created = await service.create_conversation(db, actor, service.ConversationCreate())
                cid = created["id"]
                conversation = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conversation.dek_wrapped)
                targets = []
                for generation in range(1, 4):
                    run = MimiRun(
                        id=uuid7(),
                        conversation_id=cid,
                        generation=generation,
                        state="completed",
                        provider_outcome="succeeded",
                        deadline=datetime.now(UTC) + timedelta(minutes=15),
                    )
                    db.add(run)
                    await db.flush()
                    sequence = conversation.next_message_sequence
                    user = MimiMessage(
                        conversation_id=cid,
                        run_id=run.id,
                        client_id=f"submit099-{generation}",
                        sequence=sequence,
                        role="user",
                        content_bytes=4,
                        content_sha256=hashlib.sha256(b"test").hexdigest(),
                        content_ciphertext=crypto.seal_content(
                            dek, "test", aad=crypto.message_aad(cid, sequence, "user")
                        ),
                    )
                    db.add(user)
                    conversation.next_message_sequence += 1
                    call = MimiProviderCall(
                        id=uuid7(),
                        run_id=run.id,
                        attempt=1,
                        state="succeeded",
                        request_fingerprint="fixture099",
                        route={"kind": "openrouter", "purpose": "main"},
                        result={"response_id": f"synthetic099-{generation}"},
                        usage={"cost": 0.01},
                    )
                    db.add(call)
                    await db.flush()
                    answer = await service._add_assistant_message(
                        db,
                        conversation,
                        run.id,
                        dek,
                        "Câu trả lời tổng hợp.",
                        producer_code="provider_text",
                        provider_call_id=call.id,
                    )
                    targets.append((run.id, answer.id, user.client_id))
                await db.commit()

            def body(index, milliseconds):
                rid, mid, source = targets[index]
                return timing.ResponseTimingCreate(
                    client_id=f"receipt099-{index}",
                    run_id=rid,
                    target_id=mid,
                    source_id=source,
                    phase="send",
                    observation="visible_paint",
                    elapsed_ms=milliseconds,
                )

            async def submit(payload):
                async with maker() as db:
                    result = await timing.save_response_timing(db, actor, cid, payload)
                    await db.commit()
                    return result

            first, duplicate = await asyncio.gather(submit(body(0, 2000)), submit(body(0, 2000)))
            assert first == duplicate
            async with maker() as db:
                # Later events exceed the public window without hiding the old receipt.
                for number in range(service.MAX_EVENTS + 1):
                    await service._append_event(
                        db, targets[0][0], "synthetic099.filler", {"i": number}
                    )
                await db.commit()
            await submit(body(1, 8000))
            async with maker() as db:
                for patch in [
                    dict(elapsed_ms=3000),
                    dict(client_id="new-key"),
                    dict(source_id="foreign-source"),
                    dict(target_id=targets[1][1]),
                ]:
                    with pytest.raises(HTTPException) as error:
                        await timing.save_response_timing(
                            db, actor, cid, body(0, 2000).model_copy(update=patch)
                        )
                    assert error.value.status_code in {404, 409}
                    await db.rollback()
                other_actor = auth()
                other_actor.user_email = "other-owner@example.test"
                with pytest.raises(HTTPException) as error:
                    await timing.save_response_timing(db, other_actor, cid, body(0, 2000))
                assert error.value.status_code == 404
                await db.rollback()
                view = await service.conversation_view(db, actor, cid)
                summary = view["response_timings"]
                assert (summary["min_ms"], summary["avg_ms"], summary["max_ms"]) == (
                    2000,
                    5000,
                    8000,
                )
                assert (summary["observed"], summary["eligible"], summary["missing"]) == (2, 3, 1)
                assert view["metrics"]["usd"]["known"] == "0.03"
                events = (
                    await db.scalars(select(MimiEvent).where(MimiEvent.run_id == targets[0][0]))
                ).all()
                assert len({event.sequence for event in events}) == len(events)
                assert sum(event.kind == timing.KIND for event in events) == 1

                detail = "🌸" * 7999 + "ệ"
                feedback = service.FeedbackCreate(
                    client_id="feedback099",
                    target_type="turn",
                    target_id=str(targets[0][1]),
                    comment="Phản hồi chưa tốt.\n" + detail,
                    expected=detail,
                )
                saved = await service.save_feedback(db, actor, cid, feedback)
                await db.commit()
                assert await service.save_feedback(db, actor, cid, feedback) == saved
                row = await db.get(MimiFeedback, saved["id"])
                conversation = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conversation.dek_wrapped)
                assert detail not in row.comment_ciphertext
                assert (
                    crypto.open_content(
                        dek, row.comment_ciphertext, aad=crypto.feedback_aad(cid, row.id, "comment")
                    )
                    == feedback.comment
                )
                assert (
                    crypto.open_content(
                        dek,
                        row.expected_ciphertext,
                        aad=crypto.feedback_aad(cid, row.id, "expected"),
                    )
                    == detail
                )
                await db.rollback()
        finally:
            if cid:
                async with maker() as db:
                    await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
