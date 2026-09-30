"""Crash-seam proof against a disposable, migrated Postgres only."""

import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto as mimi_crypto
from app.agent import service as mimi_service
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiEvent,
    MimiMessage,
    MimiProviderCall,
    MimiRun,
)
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-recovery-pg-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_succeeded_provider_call_lost_before_preview_fails_closed(pg_dsn, monkeypatch) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(mimi_service, "get_engine", lambda: engine)
        conversation_id = uuid7()
        run_id = uuid7()
        dek_wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(dek_wrapped)
        terminal = {
            "kind": "preview_candidate",
            "tool": "task.create.v1",
            "arguments": {"title": "Chuẩn bị demo"},
        }
        terminal_sha = mimi_service._canonical_digest(terminal)
        try:
            async with maker() as db:
                conversation = MimiConversation(
                    id=conversation_id,
                    owner_id=uuid7(),
                    sensitivity="standard",
                    dek_wrapped=dek_wrapped,
                )
                conversation.generation = 2
                conversation.next_message_sequence = 2
                db.add(conversation)
                await db.flush()
                run = MimiRun(
                    id=run_id,
                    conversation_id=conversation_id,
                    generation=1,
                    state="running",
                    execution_lease={},
                    source_versions={},
                    deadline=datetime.now(UTC) + timedelta(minutes=30),
                )
                db.add(run)
                await db.flush()
                user_text = "Tạo task Chuẩn bị demo"
                db.add(
                    MimiMessage(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        client_id="crash-user-1",
                        sequence=1,
                        role="user",
                        content_ciphertext=mimi_crypto.seal_content(
                            dek,
                            user_text,
                            aad=mimi_crypto.message_aad(conversation_id, 1, "user"),
                        ),
                        content_bytes=len(user_text.encode()),
                        content_sha256=hashlib.sha256(user_text.encode()).hexdigest(),
                    )
                )
                db.add(
                    MimiProviderCall(
                        run_id=run_id,
                        attempt=1,
                        state="succeeded",
                        request_fingerprint="0" * 64,
                        route={"run_guard_version": 1},
                        result={
                            "kind": terminal["kind"],
                            "result_sha256": terminal_sha,
                            "terminal_ciphertext": mimi_crypto.seal_content(
                                dek,
                                json.dumps(terminal, ensure_ascii=False),
                                aad=mimi_crypto.provider_terminal_aad(run_id, 1),
                            ),
                        },
                    )
                )
                await db.commit()

            # A still-running old worker holds this guard. Startup must leave
            # its run alone until the owning transaction disappears.
            async with engine.connect() as guard:
                async with guard.begin():
                    await guard.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": mimi_service.run_guard_key(run_id)},
                    )
                    async with maker() as db:
                        assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 0
                        still_running = (
                            await db.execute(select(MimiRun).where(MimiRun.id == run_id))
                        ).scalar_one()
                        assert still_running.state == "running"

            async with maker() as db:
                assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 1
                assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 0
                run = (await db.execute(select(MimiRun).where(MimiRun.id == run_id))).scalar_one()
                assert run.state == "halted"
                assert run.provider_outcome == "succeeded"
                assert run.error_code == "provider_result_not_delivered_after_restart"
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(MimiChangeSet)
                        .where(MimiChangeSet.run_id == run_id)
                    )
                ).scalar_one() == 0
                messages = (
                    (
                        await db.execute(
                            select(MimiMessage)
                            .where(MimiMessage.conversation_id == conversation_id)
                            .order_by(MimiMessage.sequence)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert [message.role for message in messages] == ["user", "assistant"]
                explanation = mimi_crypto.open_content(
                    dek,
                    messages[1].content_ciphertext,
                    aad=mimi_crypto.message_aad(conversation_id, 2, "assistant"),
                )
                assert "không tự gọi model lần nữa" in explanation
                assert "Chưa có thay đổi nào được ghi" in explanation
                call = (
                    await db.execute(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == run_id)
                    )
                ).scalar_one()
                assert call.state == "succeeded"
                assert call.result["result_sha256"] == terminal_sha
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
    ("call_state", "expected_run_state", "expected_outcome", "expected_error"),
    [
        ("intent", "retryable", "failed", "process_lost_before_dispatch"),
        ("dispatched", "outcome_unknown", "unknown", "process_lost_after_dispatch"),
    ],
)
def test_process_loss_respects_dispatch_boundary(
    pg_dsn, monkeypatch, call_state, expected_run_state, expected_outcome, expected_error
) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(mimi_service, "get_engine", lambda: engine)
        conversation_id = uuid7()
        run_id = uuid7()
        try:
            async with maker() as db:
                db.add(
                    MimiConversation(
                        id=conversation_id,
                        owner_id=uuid7(),
                        sensitivity="standard",
                        dek_wrapped=mimi_crypto.create_wrapped_dek(),
                    )
                )
                await db.flush()
                db.add(
                    MimiRun(
                        id=run_id,
                        conversation_id=conversation_id,
                        generation=1,
                        state="running",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=30),
                    )
                )
                await db.flush()
                db.add(
                    MimiProviderCall(
                        run_id=run_id,
                        attempt=1,
                        state=call_state,
                        request_fingerprint="0" * 64,
                        route={"run_guard_version": 1},
                        result={"response_id": "synthetic-response-id"},
                    )
                )
                await db.commit()

            async with maker() as db:
                assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 1
                assert await mimi_service.reconcile_orphaned_mimi_runs(db) == 0
                run = (await db.execute(select(MimiRun).where(MimiRun.id == run_id))).scalar_one()
                call = (
                    await db.execute(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == run_id)
                    )
                ).scalar_one()
                assert run.state == expected_run_state
                assert run.provider_outcome == expected_outcome
                assert run.error_code == expected_error
                assert call.state == ("fenced" if call_state == "intent" else "unknown")
                if call_state == "dispatched":
                    assert call.result["response_id"] == "synthetic-response-id"
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(MimiChangeSet)
                        .where(MimiChangeSet.run_id == run_id)
                    )
                ).scalar_one() == 0
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


def test_simultaneous_startup_reconciliation_is_once(pg_dsn, monkeypatch) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(mimi_service, "get_engine", lambda: engine)
        conversation_id = uuid7()
        run_id = uuid7()
        try:
            async with maker() as db:
                db.add(
                    MimiConversation(
                        id=conversation_id,
                        owner_id=uuid7(),
                        sensitivity="standard",
                        dek_wrapped=mimi_crypto.create_wrapped_dek(),
                    )
                )
                await db.flush()
                db.add(
                    MimiRun(
                        id=run_id,
                        conversation_id=conversation_id,
                        generation=1,
                        state="running",
                        execution_lease={},
                        source_versions={},
                        deadline=datetime.now(UTC) + timedelta(minutes=30),
                    )
                )
                await db.flush()
                db.add(
                    MimiProviderCall(
                        run_id=run_id,
                        attempt=1,
                        state="dispatched",
                        request_fingerprint="0" * 64,
                        route={"run_guard_version": 1},
                        result={"response_id": "synthetic-generation"},
                    )
                )
                await db.commit()

            async def recover() -> int:
                async with maker() as db:
                    return await mimi_service.reconcile_orphaned_mimi_runs(db)

            results = await asyncio.wait_for(asyncio.gather(recover(), recover()), timeout=5)
            assert sorted(results) == [0, 1]
            async with maker() as db:
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(MimiEvent)
                        .where(MimiEvent.run_id == run_id, MimiEvent.kind == "run.terminal")
                    )
                ).scalar_one() == 1
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
