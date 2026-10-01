"""Persisted Mimi checkpoint rehydration on disposable PostgreSQL."""

import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto as mimi_crypto
from app.agent import service as mimi_service
from app.agent.context import AssistantText
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiRun
from app.agent.openrouter import AgentCompletion
from app.agent.route_config import bind_configuration
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def local_crypto(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-checkpoint-pg-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_checkpoint_rehydrates_across_sessions_and_rejects_tamper(pg_dsn) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        conversation_id = uuid7()
        run_id = uuid7()
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        try:
            async with maker() as db:
                conversation = MimiConversation(
                    id=conversation_id,
                    owner_id=uuid7(),
                    sensitivity="standard",
                    dek_wrapped=wrapped,
                    next_message_sequence=15,
                )
                db.add(conversation)
                await db.flush()
                db.add(
                    MimiRun(
                        id=run_id,
                        conversation_id=conversation_id,
                        generation=1,
                        state="building",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=30),
                    )
                )
                await db.flush()
                for sequence in range(1, 15):
                    role = "user" if sequence % 2 else "assistant"
                    content = f"synthetic-message-{sequence}"
                    db.add(
                        MimiMessage(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            client_id=f"checkpoint-{sequence}",
                            sequence=sequence,
                            role=role,
                            content_ciphertext=mimi_crypto.seal_content(
                                dek,
                                content,
                                aad=mimi_crypto.message_aad(conversation_id, sequence, role),
                            ),
                            content_bytes=len(content.encode()),
                            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                        )
                    )
                await db.flush()
                (
                    suffix,
                    span,
                    checkpoint,
                    checkpoint_id,
                ) = await mimi_service._prepare_context_history(
                    db,
                    conversation,
                    dek,
                    run_id,
                    15,
                    pending_preview={"id": "synthetic-preview"},
                    pending_draft={"id": "synthetic-draft"},
                )
                assert checkpoint is not None
                assert checkpoint["frontier"] == 2
                assert checkpoint["pending_preview"] == {"id": "synthetic-preview"}
                assert checkpoint["pending_draft"] == {"id": "synthetic-draft"}
                assert span == (3, 14)
                assert len(suffix) == 12
                event = (
                    await db.execute(select(MimiEvent).where(MimiEvent.id == checkpoint_id))
                ).scalar_one()
                assert "synthetic-message-1" not in json.dumps(event.payload)
                assert str(event.payload["content_ciphertext"]).startswith("mimi:v1:")
                await db.commit()

            # A new session has no Python checkpoint state; only encrypted DB
            # content, frontier and canonical message hashes may rehydrate it.
            async with maker() as db:
                conversation = (
                    await db.execute(
                        select(MimiConversation).where(MimiConversation.id == conversation_id)
                    )
                ).scalar_one()
                suffix, span, restored, restored_id = await mimi_service._prepare_context_history(
                    db, conversation, dek, run_id, 15, None, None
                )
                assert restored_id == checkpoint_id
                assert restored == checkpoint
                assert span == (3, 14)
                assert suffix[0]["content"] == "synthetic-message-3"
                assert suffix[-1]["content"] == "synthetic-message-14"

                event = (
                    await db.execute(select(MimiEvent).where(MimiEvent.id == checkpoint_id))
                ).scalar_one()
                event.payload = {**event.payload, "content_sha256": "0" * 64}
                await db.commit()

            async with maker() as db:
                conversation = (
                    await db.execute(
                        select(MimiConversation).where(MimiConversation.id == conversation_id)
                    )
                ).scalar_one()
                with pytest.raises(HTTPException) as blocked:
                    await mimi_service._prepare_context_history(
                        db, conversation, dek, run_id, 15, None, None
                    )
                assert blocked.value.status_code == 409
                assert blocked.value.detail == "mimi_active_checkpoint_invalid"
        finally:
            async with maker() as db:
                conversation = (
                    await db.execute(
                        select(MimiConversation).where(MimiConversation.id == conversation_id)
                    )
                ).scalar_one_or_none()
                if conversation is not None:
                    await db.delete(conversation)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure_mode", [None, "invalid_summary", "frontier_conflict", "capacity_short"]
)
def test_semantic_compaction_retains_late_constraint_and_rejects_invalid_activation(
    pg_dsn, monkeypatch, failure_mode
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        cid, rid = uuid7(), uuid7()
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        dispatched = 0

        async def summary(messages, **kwargs):
            nonlocal dispatched
            dispatched += 1
            assert kwargs["settings"].mimi_route_context_tokens == 100000
            assert kwargs["settings"].mimi_route_max_output_tokens == 2048
            assert "Chỉ học buổi tối" in messages[-1]["content"]
            if failure_mode == "frontier_conflict":
                async with maker() as concurrent:
                    changed = await concurrent.get(MimiConversation, cid)
                    changed.generation += 1
                    await concurrent.commit()
            return AgentCompletion(
                outcome=AssistantText(
                    text=json.dumps(
                        {
                            "summary": "Chỉ học buổi tối, không đổi ngày thi (nguồn#1).",
                            "decisions": ["Nguồn#1: chỉ học buổi tối"],
                            "unresolved": ["Chưa chốt lịch"],
                            **(
                                {"untrusted_extra": True}
                                if failure_mode == "invalid_summary"
                                else {}
                            ),
                        },
                        ensure_ascii=False,
                    )
                ),
                response_id="synthetic-summary",
                usage={},
                provider="Synthetic",
                model="openai/gpt-6-luna",
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", summary)
        try:
            async with maker() as db:
                conversation = MimiConversation(
                    id=cid,
                    owner_id=uuid7(),
                    sensitivity="standard",
                    dek_wrapped=wrapped,
                    next_message_sequence=19,
                )
                db.add(conversation)
                await db.flush()
                db.add(
                    MimiRun(
                        id=rid,
                        conversation_id=cid,
                        generation=1,
                        state="building",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=5),
                    )
                )
                await db.flush()
                for seq in range(1, 19):
                    content = (
                        "Đoạn giải thích dài " * (5 if failure_mode == "capacity_short" else 70)
                    ) + ("Chỉ học buổi tối, không đổi ngày thi." if seq == 1 else "Giữ mục tiêu.")
                    role = "user" if seq % 2 else "assistant"
                    db.add(
                        MimiMessage(
                            conversation_id=cid,
                            run_id=rid,
                            sequence=seq,
                            role=role,
                            content_ciphertext=mimi_crypto.seal_content(
                                dek, content, aad=mimi_crypto.message_aad(cid, seq, role)
                            ),
                            content_bytes=len(content.encode()),
                            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                        )
                    )
                await db.commit()
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                settings = bind_configuration(
                    get_settings(),
                    {"profile_id": "luna", "effort": "medium", "input_tokens": 32000},
                )
                if failure_mode in {"invalid_summary", "frontier_conflict"}:
                    with pytest.raises(HTTPException) as failed:
                        await mimi_service._prepare_context_history(
                            db, row, dek, rid, 19, None, None, settings=settings
                        )
                    assert failed.value.status_code == 409
                    await db.refresh(row)
                    assert row.context_frontier_sequence == 0
                    run = await db.get(MimiRun, rid)
                    assert run.state == "halted"
                    assert run.completed_at is not None
                    raw_messages = (
                        (
                            await db.execute(
                                select(MimiMessage).where(MimiMessage.conversation_id == cid)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert len(raw_messages) == 18
                    return

                def capacity_probe(history, checkpoint):
                    # Simulate complete-request overhead reducing history space;
                    # raw history is below the old 60% trigger in this variant.
                    if len(history) >= 8:
                        raise ValueError("context_overflow_preflight")

                suffix, span, checkpoint, event_id = await mimi_service._prepare_context_history(
                    db,
                    row,
                    dek,
                    rid,
                    19,
                    None,
                    None,
                    settings=settings,
                    context_probe=capacity_probe if failure_mode == "capacity_short" else None,
                )
                await db.commit()
                assert checkpoint["summary_kind"] == "semantic_model"
                assert "buổi tối" in checkpoint["summary"]
                assert checkpoint["frontier"] < span[0]
                assert dispatched == 1
                assert suffix
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                _, _, restored, _ = await mimi_service._prepare_context_history(
                    db, row, dek, rid, 19, None, None, settings=settings
                )
                assert restored["summary"] == checkpoint["summary"]
                assert dispatched == 1
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
