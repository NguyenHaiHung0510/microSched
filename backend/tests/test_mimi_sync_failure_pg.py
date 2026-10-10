"""Real-PG synchronous failure boundaries preserve durable provider truth, never replay."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid7

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import service
from app.agent.context import ToolRequest, ToolRequests
from app.agent.models import MimiChangeSet, MimiConversation, MimiEvent, MimiProviderCall, MimiRun
from app.agent.openrouter import AgentCompletion
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.db import get_engine, get_sessionmaker
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg
HEADERS = {"Origin": "http://test", "Sec-Fetch-Site": "same-origin", "X-Mimi-CSRF": "1"}


@pytest.fixture
def local_sync_contract(pg_dsn, monkeypatch):
    for name, value in {
        "MIMI_P0_DISABLE_DOTENV": "1",
        "APP_ENV": "local",
        "OAUTH_STATE_SECRET": "synthetic-sync-failure",
        "ENCRYPTION_MASTER_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "DATABASE_URL": async_postgres_url(pg_dsn),
        "MIMI_REAL_CHAT_ENABLED": "1",
        "MIMI_LIVE_PROVIDER_ENABLED": "1",
        "MIMI_CONTEXT_V1_ENABLED": "1",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODE": "exact",
        "MIMI_ROUTE_MODEL": "synthetic/model",
        "MIMI_ROUTE_PROVIDER": "Synthetic",
        "MIMI_ROUTE_QUANTIZATION": "fp16",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "1",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "1",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    crypto._cipher.cache_clear()
    yield
    engine = get_engine()
    if engine:
        asyncio.run(engine.dispose())
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


@pytest.mark.parametrize("failure", ["unexpected", "cancelled"])
def test_sync_unexpected_read_failure_is_durable(pg_dsn, monkeypatch, local_sync_contract, failure):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="sync-failure@example.test",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        task_id = conversation_id = None
        calls = 0
        app = create_app()

        async def actor():
            return auth

        async def request_session():
            async with maker() as db:
                try:
                    yield db
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise

        async def fake_provider(messages, **kwargs):
            nonlocal calls
            calls += 1
            return AgentCompletion(
                outcome=ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="synthetic-read",
                            name="task.read_content.v1",
                            arguments={"id": str(task_id)},
                        ),
                    )
                ),
                response_id="synthetic-sync-success",
                usage={"cost": 0},
                provider="Synthetic",
                model="synthetic/model",
            )

        async def failed_read(db, name, arguments):
            assert name == "task.read_content.v1"
            # Prove the parent provider transaction is already durable in a different session.
            async with maker() as witness:
                attempt = (
                    await witness.scalars(
                        select(MimiProviderCall)
                        .join(MimiRun, MimiProviderCall.run_id == MimiRun.id)
                        .where(MimiRun.conversation_id == conversation_id)
                    )
                ).one()
                assert attempt.state == "succeeded"
            if failure == "cancelled":
                raise asyncio.CancelledError()
            raise AttributeError("synthetic local source read failure")

        monkeypatch.setattr(service, "openrouter_complete", fake_provider)
        monkeypatch.setattr(service, "execute_read_tool", failed_read)
        app.dependency_overrides[require_session] = actor
        app.dependency_overrides[get_session] = request_session
        try:
            async with maker() as db:
                task = Task(title="Synthetic sync rollback source")
                db.add(task)
                await db.flush()
                task_id = task.id
                await db.commit()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                created = await client.post("/api/mimi/conversations", json={}, headers=HEADERS)
                assert created.status_code == 201
                conversation_id = UUID(created.json()["id"])
                payload = {"client_id": "source-failure", "content": "Đọc nguồn synthetic"}
                if failure == "cancelled":
                    try:
                        cancelled_response = await client.post(
                            f"/api/mimi/conversations/{conversation_id}/messages",
                            json=payload,
                            headers=HEADERS,
                        )
                        # Starlette's middleware may translate the cancelled
                        # endpoint into 500; durable cancellation is authoritative.
                        assert cancelled_response.status_code == 500
                    except asyncio.CancelledError:
                        pass
                else:
                    failed = await client.post(
                        f"/api/mimi/conversations/{conversation_id}/messages",
                        json=payload,
                        headers=HEADERS,
                    )
                    assert failed.status_code == 500
                async with maker() as db:
                    run = (
                        await db.scalars(
                            select(MimiRun).where(MimiRun.conversation_id == conversation_id)
                        )
                    ).one()
                    assert run.state == ("cancelled" if failure == "cancelled" else "halted")
                    assert run.error_code == (
                        "owner_cancelled" if failure == "cancelled" else "worker_failed"
                    )
                    assert run.completed_at is not None and run.provider_outcome == "succeeded"
                    call = (
                        await db.scalars(
                            select(MimiProviderCall).where(MimiProviderCall.run_id == run.id)
                        )
                    ).one()
                    assert call.state == "succeeded" and call.attempt == 1
                    result_before = dict(call.result)
                    assert call.usage == {"cost": 0}
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(MimiChangeSet)
                            .where(MimiChangeSet.run_id == run.id)
                        )
                        == 0
                    )
                    await service.finish_interrupted_run(
                        db, auth, run.id, cancelled=failure == "cancelled"
                    )
                    await db.commit()
                async with maker() as db:
                    events = (
                        await db.scalars(select(MimiEvent).where(MimiEvent.run_id == run.id))
                    ).all()
                    assert sum(e.kind == "run.terminal" for e in events) == 1
                    assert not any(
                        e.kind in {"selection.frozen", "tool.read_result"} for e in events
                    )
                    call = await db.get(MimiProviderCall, call.id)
                    assert call.result == result_before and call.state == "succeeded"
                    assert (await db.get(Task, task_id)).title == "Synthetic sync rollback source"
                # Repeating the same client ID can only read the retained run; no model replay.
                repeated = await client.post(
                    f"/api/mimi/conversations/{conversation_id}/messages",
                    json=payload,
                    headers=HEADERS,
                )
                assert repeated.status_code == 200
                assert calls == 1
        finally:
            async with maker() as db:
                if conversation_id:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation:
                        await db.delete(conversation)
                if task_id:
                    task = await db.get(Task, task_id)
                    if task:
                        await db.delete(task)
                await db.commit()
            app.dependency_overrides.clear()
            runtime_engine = get_engine()
            if runtime_engine is not None:
                await runtime_engine.dispose()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("state", ["completed", "waiting_confirmation"])
def test_sync_finalizer_retains_existing_terminal(pg_dsn, local_sync_contract, state):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="sync-terminal@example.test",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        cid = None
        try:
            async with maker() as db:
                view = await service.create_conversation(db, auth, service.ConversationCreate())
                cid = view["id"]
                row = MimiRun(
                    conversation_id=cid,
                    generation=1,
                    state=state,
                    provider_outcome="succeeded",
                    deadline=datetime.now(UTC) + timedelta(minutes=1),
                )
                db.add(row)
                await db.commit()
                rid = row.id
            async with maker() as db:
                await service.finish_interrupted_run(db, auth, rid, cancelled=False)
                # A pre-accept error's reserved ID has no durable run to finalize.
                await service.finish_interrupted_run(db, auth, uuid7(), cancelled=False)
                await db.commit()
            async with maker() as db:
                row = await db.get(MimiRun, rid)
                assert row.state == state and row.provider_outcome == "succeeded"
                assert row.completed_at is None
                assert (
                    await db.scalar(
                        select(func.count()).select_from(MimiEvent).where(MimiEvent.run_id == rid)
                    )
                    == 0
                )
        finally:
            if cid:
                async with maker() as db:
                    await db.delete(await db.get(MimiConversation, cid))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("call_state", "outcome"),
    [
        (None, None),
        ("intent", "failed"),
        ("failed", "failed"),
        ("succeeded", "succeeded"),
        ("dispatched", "unknown"),
        ("unknown", "unknown"),
    ],
)
def test_sync_finalizer_preserves_provider_truth(pg_dsn, local_sync_contract, call_state, outcome):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="sync-finalizer@example.test",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        cid = rid = uuid7()
        try:
            async with maker() as db:
                conv = await service.create_conversation(db, auth, service.ConversationCreate())
                cid = conv["id"]
                run = MimiRun(
                    id=rid,
                    conversation_id=cid,
                    generation=1,
                    state="running",
                    deadline=datetime.now(UTC) + timedelta(minutes=1),
                )
                db.add(run)
                await db.flush()
                call = None
                if call_state:
                    call = MimiProviderCall(
                        run_id=rid,
                        attempt=1,
                        state=call_state,
                        request_fingerprint="0" * 64,
                        route={"synthetic": True},
                        result={"response_id": "synthetic-known", "retained": True},
                        usage={"cost": 0},
                    )
                    db.add(call)
                await db.commit()
            async with maker() as db:
                await service.finish_interrupted_run(db, auth, rid, cancelled=False)
                await db.commit()
            async with maker() as db:
                run = await db.get(MimiRun, rid)
                assert run.state == ("outcome_unknown" if outcome == "unknown" else "halted")
                assert run.completed_at is not None
                assert run.provider_outcome == outcome
                if call:
                    current = await db.get(MimiProviderCall, call.id)
                    expected_state = "unknown" if call_state == "dispatched" else call_state
                    if call_state == "intent":
                        expected_state = "failed"
                    assert current.state == expected_state
                    if call_state in {"succeeded", "failed", "unknown"}:
                        assert current.result == call.result
                        assert current.usage == call.usage
                await service.finish_interrupted_run(db, auth, rid, cancelled=False)
                await db.commit()
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiEvent)
                        .where(MimiEvent.run_id == rid, MimiEvent.kind == "run.terminal")
                    )
                    == 1
                )
        finally:
            async with maker() as db:
                row = await db.get(MimiConversation, cid)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    ["succeeded", "failed", "unknown", "missing_id", "wrong_id", "wrong_owner", "legacy_halted"],
)
def test_sync_unknown_public_reconcile_preserves_call(
    pg_dsn, monkeypatch, local_sync_contract, mode
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="reconcile-sync@example.test",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        cid = None
        metadata_calls = 0
        app = create_app()

        async def actor():
            if mode == "wrong_owner":
                return AuthSession(user_email="other-reconcile@example.test")
            return auth

        async def request_session():
            async with maker() as db:
                try:
                    yield db
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise

        async def metadata(response_id):
            nonlocal metadata_calls
            metadata_calls += 1
            assert response_id == "synthetic-unknown-generation"
            return {
                "id": "other-generation" if mode == "wrong_id" else response_id,
                "cancelled": True if mode == "failed" else None if mode == "unknown" else False,
                "finish_reason": "stop",
            }

        async def forbidden_dispatch(*args, **kwargs):
            raise AssertionError("UNKNOWN_MUST_NOT_REDISPATCH")

        monkeypatch.setattr(service, "openrouter_get_generation", metadata)
        monkeypatch.setattr(service, "openrouter_complete", forbidden_dispatch)
        monkeypatch.setattr(service, "openrouter_complete_stream", forbidden_dispatch)
        app.dependency_overrides[require_session] = actor
        app.dependency_overrides[get_session] = request_session
        try:
            async with maker() as db:
                conv = await service.create_conversation(db, auth, service.ConversationCreate())
                cid = conv["id"]
                run = MimiRun(
                    conversation_id=cid,
                    generation=1,
                    state="running",
                    deadline=datetime.now(UTC) + timedelta(minutes=1),
                )
                db.add(run)
                await db.flush()
                call = MimiProviderCall(
                    run_id=run.id,
                    attempt=1,
                    state="dispatched",
                    request_fingerprint="0" * 64,
                    route={"synthetic": True},
                    result={
                        "response_id": None
                        if mode == "missing_id"
                        else "synthetic-unknown-generation"
                    },
                    usage={"cost": 0},
                )
                db.add(call)
                await db.commit()
                rid, call_id = run.id, call.id
            async with maker() as db:
                await service.finish_interrupted_run(db, auth, rid, cancelled=False)
                await db.commit()
            async with maker() as db:
                stopped = await db.get(MimiRun, rid)
                assert stopped.state == "outcome_unknown" and stopped.provider_outcome == "unknown"
                with pytest.raises(HTTPException) as held:
                    await service.prepare_run_resume(db, auth, rid)
                assert (
                    getattr(held.value, "detail", None)
                    == "mimi_run_outcome_unknown_reconciliation_required"
                )
                if mode == "legacy_halted":
                    # Compatibility with already durable pre-repair UNKNOWN; no migration/rewrite.
                    stopped.state = "halted"
                    await db.commit()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                result = await client.post(
                    f"/api/mimi/runs/{rid}/reconcile", json={}, headers=HEADERS
                )
            expected_status = (
                404 if mode == "wrong_owner" else 409 if mode in {"wrong_id", "missing_id"} else 200
            )
            assert result.status_code == expected_status, result.text
            assert metadata_calls == (0 if mode in {"wrong_owner", "missing_id"} else 1)
            async with maker() as db:
                current = await db.get(MimiRun, rid)
                saved = await db.get(MimiProviderCall, call_id)
                outcome = (
                    "succeeded"
                    if mode == "legacy_halted"
                    else mode
                    if mode in {"succeeded", "failed"}
                    else "unknown"
                )
                assert current.provider_outcome == saved.state == outcome
                assert current.state == ("outcome_unknown" if outcome == "unknown" else "halted")
                assert saved.result["response_id"] == (
                    None if mode == "missing_id" else "synthetic-unknown-generation"
                )
                assert saved.attempt == 1 and saved.usage == {"cost": 0}
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiProviderCall)
                        .where(MimiProviderCall.run_id == rid)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiChangeSet)
                        .where(MimiChangeSet.run_id == rid)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiEvent)
                        .where(MimiEvent.run_id == rid, MimiEvent.kind == "run.terminal")
                    )
                    == 1
                )
                if expected_status == 200:
                    assert result.json()["provider_outcome"] == outcome
                    assert saved.result["terminal"] == f"reconciled_generation_{outcome}"
        finally:
            if cid:
                async with maker() as db:
                    await db.delete(await db.get(MimiConversation, cid))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
