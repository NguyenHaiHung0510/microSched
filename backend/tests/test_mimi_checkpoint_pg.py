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
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiProviderCall, MimiRun
from app.agent.openrouter import AgentCompletion, RouteContractError
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
    "failure_mode",
    [None, "invalid_summary", "frontier_conflict", "capacity_short", "actual_capacity"],
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
            assert kwargs["settings"].mimi_route_context_tokens == 32000
            assert kwargs["settings"].mimi_route_max_output_tokens == 2048
            source_payload = json.loads(messages[-1]["content"])
            first_source = next((s for s in source_payload["sources"] if s["sequence"] == 1), None)
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
                            "constraints": [
                                {
                                    "text": "Chỉ học buổi tối",
                                    "kind": "decision",
                                    "source_sequence": 1,
                                    "source_sha256": first_source["sha256"] if first_source else "",
                                    "quote": "Chỉ học buổi tối",
                                }
                            ]
                            if first_source
                            else [],
                            "supersessions": [],
                            "resolutions": [],
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

                def capacity_probe(history, checkpoint, *_metadata):
                    # Simulate complete-request overhead reducing history space;
                    # raw history is below the old 60% trigger in this variant.
                    if len(history) >= 8:
                        raise ValueError("context_overflow_preflight")

                from app.agent.context_builder import assemble_context
                from app.agent.contracts import ExecutionLease, Sensitivity
                from app.agent.openrouter import build_request, serialized_input_bytes

                lease = ExecutionLease(
                    lease_id=uuid7(),
                    owner_id=uuid7(),
                    run_id=rid,
                    capabilities=("task.query.v1",),
                    issued_at=datetime.now(UTC),
                    deadline=datetime.now(UTC) + timedelta(minutes=5),
                    max_turns=4,
                    max_tool_calls=6,
                    cost_cap_minor=0,
                    sensitivity=Sensitivity.STANDARD,
                )
                test_settings = settings.model_copy(
                    update={"mimi_standard_api_key": "synthetic-no-key"}
                )
                exact_inputs = []

                def actual_probe(history, checkpoint, checkpoint_id, frontier, span):
                    _ctx, wire = assemble_context(
                        lease=lease,
                        reserved_task_id=uuid7(),
                        conversation_id=cid,
                        generation=1,
                        request_id="capacity-full-wire",
                        transcript_suffix=history,
                        current_user_turn="Giữ buổi tối, trình phương án trước khi ghi.",
                        task_context=[],
                        pending_preview_content=[{"title": "Pending synthetic"}],
                        pending_preview=None,
                        pending_draft=None,
                        checkpoint=checkpoint,
                        checkpoint_id=checkpoint_id,
                        checkpoint_frontier=frontier,
                        transcript_range=span,
                        settings=test_settings,
                        remaining_turns=4,
                        remaining_tool_calls=6,
                    )
                    build_request(wire, test_settings, agent_contract=True)
                    exact_inputs.append(serialized_input_bytes(wire, agent_contract=True))

                suffix, span, checkpoint, event_id = await mimi_service._prepare_context_history(
                    db,
                    row,
                    dek,
                    rid,
                    19,
                    None,
                    None,
                    settings=settings,
                    context_probe=(
                        actual_probe
                        if failure_mode == "actual_capacity"
                        else capacity_probe
                        if failure_mode == "capacity_short"
                        else None
                    ),
                )
                await db.commit()
                assert checkpoint["summary_kind"] == "semantic_model"
                assert "buổi tối" in checkpoint["summary"]
                if span is not None:
                    assert checkpoint["frontier"] < span[0]
                else:
                    assert failure_mode == "actual_capacity" and checkpoint["frontier"] == 18
                assert 1 <= dispatched <= 4
                if failure_mode == "actual_capacity":
                    assert exact_inputs and exact_inputs[-1] + 8192 <= 32000
                assert suffix or failure_mode == "actual_capacity"
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                _, _, restored, _ = await mimi_service._prepare_context_history(
                    db, row, dek, rid, 19, None, None, settings=settings
                )
                assert restored["summary"] == checkpoint["summary"]
                assert 1 <= dispatched <= 4
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_mode", ["small_cap", "reservation"])
def test_compaction_preflight_or_reservation_failure_halts_without_dispatch_or_history_loss(
    pg_dsn, monkeypatch, failure_mode
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        cid, rid = uuid7(), uuid7()
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        calls = 0

        async def unexpected_dispatch(*args, **kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("preflight failure must halt before dispatch")

        monkeypatch.setattr(mimi_service, "openrouter_complete", unexpected_dispatch)
        if failure_mode == "reservation":
            from app.agent import local_budget

            def fail_reservation(*args, **kwargs):
                raise RouteContractError("synthetic_reservation_refused")

            monkeypatch.setattr(local_budget, "reserve", fail_reservation)
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
                    role = "user" if seq % 2 else "assistant"
                    content = f"synthetic-preserved-{seq}-" + "x" * 1800
                    db.add(
                        MimiMessage(
                            conversation_id=cid,
                            run_id=rid,
                            sequence=seq,
                            role=role,
                            content_ciphertext=mimi_crypto.seal_content(
                                dek,
                                content,
                                aad=mimi_crypto.message_aad(cid, seq, role),
                            ),
                            content_bytes=len(content.encode()),
                            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                        )
                    )
                await db.commit()

            async with maker() as db:
                conversation = await db.get(MimiConversation, cid)
                settings = bind_configuration(
                    get_settings(),
                    {"profile_id": "luna", "effort": "medium", "input_tokens": 32000},
                )
                if failure_mode == "small_cap":
                    settings = settings.model_copy(update={"mimi_route_context_tokens": 2048})
                with pytest.raises(HTTPException) as stopped:
                    await mimi_service._prepare_context_history(
                        db, conversation, dek, rid, 19, None, None, settings=settings
                    )
                assert stopped.value.status_code == 409
                run = await db.get(MimiRun, rid)
                assert run.state == "budget_exceeded"
                assert run.completed_at is not None
                assert conversation.context_frontier_sequence == 0
                rows = (
                    (
                        await db.execute(
                            select(MimiMessage).where(MimiMessage.conversation_id == cid)
                        )
                    )
                    .scalars()
                    .all()
                )
                provider_calls = (
                    (
                        await db.execute(
                            select(MimiProviderCall).where(MimiProviderCall.run_id == rid)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(rows) == 18
                assert provider_calls == []
                assert calls == 0
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_compaction_stops_after_four_helper_calls_and_keeps_all_raw_sources(pg_dsn, monkeypatch):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        cid, rid = uuid7(), uuid7()
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        calls = 0

        async def summary(*args, **kwargs):
            nonlocal calls
            calls += 1
            return AgentCompletion(
                outcome=AssistantText(
                    text=json.dumps(
                        {
                            "summary": "bounded synthetic summary",
                            "constraints": [],
                            "supersessions": [],
                            "resolutions": [],
                        }
                    )
                ),
                response_id=f"summary-{calls}",
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
                    next_message_sequence=61,
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
                for seq in range(1, 61):
                    role = "user" if seq % 2 else "assistant"
                    content = f"synthetic-chunk-{seq}-" + "x" * 50
                    db.add(
                        MimiMessage(
                            conversation_id=cid,
                            run_id=rid,
                            sequence=seq,
                            role=role,
                            content_ciphertext=mimi_crypto.seal_content(
                                dek,
                                content,
                                aad=mimi_crypto.message_aad(cid, seq, role),
                            ),
                            content_bytes=len(content.encode()),
                            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                        )
                    )
                await db.commit()

            async with maker() as db:
                conversation = await db.get(MimiConversation, cid)
                settings = bind_configuration(
                    get_settings(),
                    {"profile_id": "luna", "effort": "medium", "input_tokens": 32000},
                )

                def always_overflow(_history, _checkpoint, *_metadata):
                    raise ValueError("context_overflow_preflight")

                with pytest.raises(HTTPException) as stopped:
                    await mimi_service._prepare_context_history(
                        db,
                        conversation,
                        dek,
                        rid,
                        61,
                        None,
                        None,
                        settings=settings,
                        context_probe=always_overflow,
                    )
                assert stopped.value.detail == "mimi_compaction_helper_call_limit"
                assert calls == 4
                run = await db.get(MimiRun, rid)
                assert run.state == "budget_exceeded"
                assert conversation.context_frontier_sequence > 0
                rows = (
                    (
                        await db.execute(
                            select(MimiMessage).where(MimiMessage.conversation_id == cid)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(rows) == 60
                assert all(row.content_ciphertext.startswith("mimi:v1:") for row in rows)
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
