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
from app.agent.observations import context_revision
from app.agent.openrouter import AgentCompletion, RouteContractError
from app.agent.route_config import bind_configuration
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession

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
        auth = AuthSession(
            token_hash="synthetic-checkpoint-reader",
            user_email="checkpoint@example.invalid",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        other = auth.model_copy(update={"user_email": "other-checkpoint@example.invalid"})
        conversation_id = uuid7()
        run_id = uuid7()
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        try:
            async with maker() as db:
                conversation = MimiConversation(
                    id=conversation_id,
                    owner_id=mimi_service._owner_id(auth),
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
                view = await mimi_service.conversation_checkpoint_view(db, auth, conversation_id)
                assert view["checkpoint"]["summary"] == restored["summary"]
                assert view["checkpoint"]["source_refs"] == restored["source_refs"]
                assert "pending_preview" not in view["checkpoint"]
                assert "pending_draft" not in view["checkpoint"]
                assert "policy_sha256" not in view["checkpoint"]
                assert datetime.fromisoformat(view["activated_at"]) == event.created_at
                assert view["checkpoint_id"] == str(checkpoint_id)
                assert view["frontier"] == 2
                assert view["checkpoint_sha256"] == mimi_service._canonical_digest(restored)
                assert not db.new and not db.dirty and not db.deleted
                with pytest.raises(HTTPException) as isolated:
                    await mimi_service.conversation_checkpoint_view(db, other, conversation_id)
                assert isolated.value.status_code == 404
                source = await db.get(MimiMessage, restored["source_refs"][0]["id"])
                original_hash = source.content_sha256
                source.content_sha256 = "f" * 64
                await db.flush()
                with pytest.raises(HTTPException) as drift:
                    await mimi_service.conversation_checkpoint_view(db, auth, conversation_id)
                assert drift.value.detail == "mimi_active_checkpoint_source_drift"
                source.content_sha256 = original_hash
                await db.flush()
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
                with pytest.raises(HTTPException) as viewer_blocked:
                    await mimi_service.conversation_checkpoint_view(db, auth, conversation_id)
                assert viewer_blocked.value.status_code == 409
                event = await db.get(MimiEvent, checkpoint_id)
                blob = bytearray(
                    base64.urlsafe_b64decode(
                        event.payload["content_ciphertext"][
                            len(mimi_crypto.MIMI_CIPHERTEXT_PREFIX) :
                        ]
                    )
                )
                blob[-1] ^= 1
                event.payload = {
                    **event.payload,
                    "content_sha256": mimi_service._canonical_digest(checkpoint),
                    "content_ciphertext": mimi_crypto.MIMI_CIPHERTEXT_PREFIX
                    + base64.urlsafe_b64encode(blob).decode(),
                }
                await db.commit()
                with pytest.raises(HTTPException) as cipher_tamper:
                    await mimi_service.conversation_checkpoint_view(db, auth, conversation_id)
                assert cipher_tamper.value.status_code == 409
                assert cipher_tamper.value.detail == "mimi_active_checkpoint_invalid"
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


async def _seed_observed_trigger(db, conversation, run_id, settings):
    """A main provider-double receipt drives delayed compaction, never raw bytes."""
    current = await db.get(MimiRun, run_id)
    current.generation = 2
    await db.flush()
    previous = MimiRun(
        id=uuid7(),
        conversation_id=conversation.id,
        generation=1,
        state="completed",
        execution_lease={},
        source_versions={},
        deadline=datetime.now(UTC) + timedelta(minutes=5),
    )
    db.add(previous)
    await db.flush()
    db.add(
        MimiProviderCall(
            run_id=previous.id,
            attempt=1,
            state="succeeded",
            request_fingerprint="c" * 64,
            usage={"prompt_tokens": 100_001},
            result={"response_id": str(uuid7())},
            route={
                "kind": "openrouter",
                "purpose": "main",
                "context_revision": context_revision(
                    settings, conversation.route_config_version, None
                ),
                "model": settings.mimi_route_model,
                "actual_model": settings.mimi_route_model,
                "actual_provider": settings.mimi_route_provider,
                "providers": [settings.mimi_route_provider],
            },
        )
    )
    await db.commit()


@pytest.mark.parametrize(
    "failure_mode",
    [
        None,
        "invalid_summary",
        "empty_semantic_summary",
        "invalid_quote",
        "frontier_conflict",
        "capacity_short",
        "actual_capacity",
    ],
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
            assert kwargs["settings"].mimi_route_context_tokens == 1_050_000
            assert kwargs["settings"].mimi_route_max_output_tokens == 8192
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
                            "summary": "..."
                            if failure_mode == "empty_semantic_summary"
                            else "Chỉ học buổi tối, không đổi ngày thi (nguồn#1).",
                            "constraints": [
                                {
                                    "text": "Chỉ học buổi tối",
                                    "kind": "decision",
                                    "source_sequence": 1,
                                    "source_sha256": first_source["sha256"] if first_source else "",
                                    "quote": "fabricated synthetic quote"
                                    if failure_mode == "invalid_quote"
                                    else "Chỉ học buổi tối",
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
                await _seed_observed_trigger(db, row, rid, settings)
                if failure_mode in {
                    "invalid_summary",
                    "empty_semantic_summary",
                    "invalid_quote",
                    "frontier_conflict",
                }:
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
                    if failure_mode in {"invalid_quote", "empty_semantic_summary"}:
                        call = (
                            await db.execute(
                                select(MimiProviderCall).where(MimiProviderCall.run_id == rid)
                            )
                        ).scalar_one()
                        assert call.result["diagnostic"] == {
                            "category": "summary_validation_failed",
                            "reason": "checkpoint_semantic_source_quote_invalid"
                            if failure_mode == "invalid_quote"
                            else "checkpoint_semantic_summary_invalid",
                        }
                        assert "fabricated synthetic quote" not in json.dumps(call.result)
                        assert dispatched == 1
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
                    assert exact_inputs and exact_inputs[-1] <= settings.mimi_max_payload_bytes
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
                await _seed_observed_trigger(db, conversation, rid, settings)
                if failure_mode == "small_cap":
                    # Endpoint output bound remains a real guard, independent of bytes.
                    settings = settings.model_copy(update={"mimi_route_context_tokens": 2048})
                    # Keep binding on the same model/epoch for this resource refusal.
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


@pytest.mark.parametrize("crash_boundary", ["intent", "dispatched"])
def test_real_compaction_receipt_survives_process_loss_without_redispatch(
    pg_dsn, monkeypatch, crash_boundary
):
    from app.agent.compaction import CheckpointSource

    class SimulatedProcessLoss(BaseException):
        pass

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(mimi_service, "get_engine", lambda: engine)
        cid, rid = uuid7(), uuid7()
        dispatches = 0

        async def crash_dispatch(*args, **kwargs):
            nonlocal dispatches
            dispatches += 1
            raise SimulatedProcessLoss()

        monkeypatch.setattr(mimi_service, "openrouter_complete", crash_dispatch)
        monkeypatch.setattr(
            "app.agent.local_budget.reserve", lambda *args, **kwargs: "synthetic-hold"
        )
        source_text = "Chỉ học buổi tối."
        source = CheckpointSource(
            id=uuid7(),
            sequence=1,
            role="user",
            content_sha256=hashlib.sha256(source_text.encode()).hexdigest(),
            content=source_text,
        )
        try:
            async with maker() as db:
                db.add(
                    MimiConversation(
                        id=cid,
                        owner_id=uuid7(),
                        sensitivity="standard",
                        dek_wrapped=mimi_crypto.create_wrapped_dek(),
                    )
                )
                await db.flush()
                db.add(
                    MimiRun(
                        id=rid,
                        conversation_id=cid,
                        generation=1,
                        state="accepted",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=5),
                    )
                )
                await db.commit()
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                actual_commit = db.commit

                async def commit_at_crash_seam():
                    await actual_commit()
                    if crash_boundary == "intent":
                        raise SimulatedProcessLoss()

                monkeypatch.setattr(db, "commit", commit_at_crash_seam)
                settings = bind_configuration(
                    get_settings(),
                    {"profile_id": "deepseek", "effort": "high", "input_tokens": 32000},
                )
                with pytest.raises(SimulatedProcessLoss):
                    await mimi_service._semantic_checkpoint(
                        db, row, rid, [source], None, None, None, settings
                    )
            assert dispatches == (0 if crash_boundary == "intent" else 1)
            async with maker() as db:
                assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 1
                assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 0
                run = await db.get(MimiRun, rid)
                call = (
                    await db.execute(select(MimiProviderCall).where(MimiProviderCall.run_id == rid))
                ).scalar_one()
                assert call.route["purpose"] == "compaction"
                assert call.route["run_guard_version"] == 1
                assert call.state == ("fenced" if crash_boundary == "intent" else "unknown")
                assert run.state == (
                    "retryable" if crash_boundary == "intent" else "outcome_unknown"
                )
                assert run.error_code == (
                    "process_lost_before_dispatch"
                    if crash_boundary == "intent"
                    else "process_lost_after_dispatch"
                )
                assert run.completed_at is not None
                conversation = await db.get(MimiConversation, cid)
                assert conversation.context_frontier_sequence == 0
                events = (
                    (await db.execute(select(MimiEvent).where(MimiEvent.run_id == rid)))
                    .scalars()
                    .all()
                )
                assert sum(e.kind == "run.terminal" for e in events) == 1
                assert not any(e.kind == "context.checkpoint.activated" for e in events)
            assert dispatches == (0 if crash_boundary == "intent" else 1)
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row is not None:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_truncated_helper_accounts_observed_terminal_without_activating_history(
    pg_dsn, monkeypatch
):
    from app.agent.compaction import CheckpointSource
    from app.agent.openrouter import parse_compaction_completion

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        cid, rid = uuid7(), uuid7()
        accounted = []
        observed_caps = []

        async def truncated(*args, **kwargs):
            observed_caps.append(kwargs["settings"].mimi_route_max_output_tokens)
            return parse_compaction_completion(
                {
                    "id": "synthetic-truncated-helper",
                    "model": "synthetic-model",
                    "provider": "synthetic-provider",
                    "usage": {"cost": 0.00012},
                    "choices": [
                        {"finish_reason": "length", "message": {"content": '{"summary":"cut'}}
                    ],
                }
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", truncated)
        monkeypatch.setattr("app.agent.local_budget.reserve", lambda *a, **k: "synthetic-hold")
        monkeypatch.setattr("app.agent.local_budget.account", lambda *a: accounted.append(a))
        source_text = "Chỉ học buổi tối."
        source = CheckpointSource(
            id=uuid7(),
            sequence=1,
            role="user",
            content_sha256=hashlib.sha256(source_text.encode()).hexdigest(),
            content=source_text,
        )
        try:
            async with maker() as db:
                row = MimiConversation(
                    id=cid,
                    owner_id=uuid7(),
                    sensitivity="standard",
                    dek_wrapped=mimi_crypto.create_wrapped_dek(),
                )
                db.add(row)
                await db.flush()
                db.add(
                    MimiRun(
                        id=rid,
                        conversation_id=cid,
                        generation=1,
                        state="accepted",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=5),
                    )
                )
                await db.commit()
                settings = bind_configuration(
                    get_settings(),
                    {"profile_id": "deepseek", "effort": "high", "input_tokens": 32000},
                )
                with pytest.raises(HTTPException) as caught:
                    await mimi_service._semantic_checkpoint(
                        db, row, rid, [source], None, None, None, settings
                    )
                assert caught.value.detail == "compaction_candidate_invalid_history_preserved"
                assert observed_caps == [8192]
                assert len(accounted) == 1
                assert accounted[0][2:] == ({"cost": 0.00012}, "synthetic-truncated-helper")
                await db.refresh(row)
                assert row.context_frontier_sequence == 0
                call = (
                    await db.execute(select(MimiProviderCall).where(MimiProviderCall.run_id == rid))
                ).scalar_one()
                assert call.state == "failed"
                assert call.result == {
                    "response_id": "synthetic-truncated-helper",
                    "diagnostic": {
                        "category": "output_truncated",
                        "reason": "compaction_summary_output_truncated",
                    },
                }
                assert call.usage == {"cost": 0.00012}
                run = await db.get(MimiRun, rid)
                assert run.state == "halted" and run.provider_outcome == "succeeded"
                assert run.completed_at is not None
                events = (
                    (await db.execute(select(MimiEvent).where(MimiEvent.run_id == rid)))
                    .scalars()
                    .all()
                )
                assert sum(e.kind == "run.terminal" for e in events) == 1
                assert not any(e.kind == "context.checkpoint.activated" for e in events)
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_checkpoint_reader_http_auth_no_checkpoint_and_private_unavailable(pg_dsn):
    import httpx
    from fastapi import FastAPI

    from app.web.routers import mimi as router_module

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = AuthSession(
            token_hash="synthetic-reader-http",
            user_email="checkpoint-http@example.invalid",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        cid = uuid7()
        app = FastAPI()
        app.include_router(router_module.router, prefix="/api")

        async def database():
            async with maker() as db:
                yield db

        app.dependency_overrides[router_module.get_session] = database
        try:
            async with maker() as db:
                db.add(
                    MimiConversation(
                        id=cid,
                        owner_id=mimi_service._owner_id(auth),
                        sensitivity="standard",
                        dek_wrapped=mimi_crypto.create_wrapped_dek(),
                    )
                )
                await db.commit()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://synthetic.local"
            ) as client:
                response = await client.get(f"/api/mimi/conversations/{cid}/context")
                assert response.status_code == 401
                app.dependency_overrides[router_module.require_session] = lambda: auth
                response = await client.get(f"/api/mimi/conversations/{cid}/context")
                assert response.status_code == 200
                assert response.json()["checkpoint"] is None
                assert response.json()["activated_at"] is None
                assert response.json()["frontier"] == 0
                app.dependency_overrides[router_module.require_session] = lambda: auth.model_copy(
                    update={"user_email": "other-reader@example.invalid"}
                )
                response = await client.get(f"/api/mimi/conversations/{cid}/context")
                assert response.status_code == 404
                app.dependency_overrides[router_module.require_session] = lambda: auth
                async with maker() as db:
                    row = await db.get(MimiConversation, cid)
                    row.sensitivity = "private"
                    row.is_private = True
                    await db.commit()
                response = await client.get(f"/api/mimi/conversations/{cid}/context")
                assert response.status_code == 404
        finally:
            from sqlalchemy import delete

            async with maker() as db:
                await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
