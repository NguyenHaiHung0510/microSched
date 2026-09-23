"""P1C source provenance must stay consistent across provider turns."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import service as mimi_service
from app.agent.context import PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent, MimiRun
from app.agent.openrouter import AgentCompletion
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def local_live_contract(monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-source-consistency-pg-test")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    )
    monkeypatch.setenv("MIMI_REAL_CHAT_ENABLED", "1")
    monkeypatch.setenv("MIMI_LIVE_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("MIMI_CONTEXT_V1_ENABLED", "1")
    monkeypatch.setenv("MIMI_STANDARD_API_KEY", "synthetic-not-sent")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "synthetic/model")
    monkeypatch.setenv("MIMI_ROUTE_PROVIDER", "Synthetic")
    monkeypatch.setenv("MIMI_ROUTE_QUANTIZATION", "fp16")
    monkeypatch.setenv("MIMI_ROUTE_MAX_INPUT_PRICE", "1")
    monkeypatch.setenv("MIMI_ROUTE_MAX_OUTPUT_PRICE", "1")
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash=f"mimi-source-consistency-{uuid4().hex}",
        user_email="owner@example.test",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
    )


def _completion(outcome, response_id: str) -> AgentCompletion:
    return AgentCompletion(
        outcome=outcome,
        response_id=response_id,
        usage={"prompt_tokens": 12, "completion_tokens": 8},
        provider="Synthetic",
        model="synthetic/model",
    )


def _read_request(call_id: str, name: str, arguments: dict) -> ToolRequests:
    return ToolRequests(requests=(ToolRequest(call_id=call_id, name=name, arguments=arguments),))


def _candidate(title: str) -> PreviewCandidate:
    return PreviewCandidate(tool=CREATE_CANDIDATE_TOOL, arguments={"title": title})


async def _create_conversation(db, auth: AuthSession, client_id: str) -> UUID:
    result = await mimi_service.create_conversation(
        db, auth, mimi_service.ConversationCreate(client_id=client_id)
    )
    value = result["id"]
    return value if isinstance(value, UUID) else UUID(value)


async def _run_message(maker, auth, conversation_id, client_id: str, content: str):
    async with maker() as db:
        result = await mimi_service.send_message(
            db,
            auth,
            conversation_id,
            mimi_service.MessageCreate(client_id=client_id, content=content, expected_generation=1),
        )
        await db.commit()
        return result


def test_aggregate_read_then_candidate_is_blocked_without_preview_or_task_write(
    pg_dsn, monkeypatch
):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        prefix = f"p1c-aggregate-provenance-{uuid4().hex}"
        calls = 0
        monkeypatch.setattr(mimi_service, "get_sessionmaker", lambda: maker)

        async def fake_completion(
            messages, *, settings, session_id, force_task_tool, agent_contract
        ):
            nonlocal calls
            calls += 1
            assert agent_contract and not force_task_tool
            if calls == 1:
                return _completion(
                    _read_request(
                        "aggregate-read", "task.aggregate.v1", {"filter": {}, "group_by": "status"}
                    ),
                    "aggregate-read",
                )
            return _completion(_candidate(f"{prefix}-candidate"), "aggregate-preview-attempt")

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                await db.execute(text("SET LOCAL microsched.task_due_writer = 'v2'"))
                db.add(Task(title=f"{prefix}-source"))
                conversation_id = await _create_conversation(db, auth, "p1c-aggregate-source")
                await db.commit()

            result = await _run_message(
                maker,
                auth,
                conversation_id,
                "p1c-aggregate-source-run",
                "Count my Tasks then create one",
            )
            run_view = result["runs"][-1]
            assert run_view["state"] == "halted"
            assert len(result["change_sets"]) == 0
            assert calls == 2

            async with maker() as db:
                run = await db.get(MimiRun, run_view["id"])
                assert run is not None
                terminal_events = (
                    (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.run_id == run.id, MimiEvent.kind == "agent.terminal"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert terminal_events and terminal_events[-1].payload.get("kind") == "blocked"
                count = (
                    await db.execute(
                        select(func.count()).select_from(Task).where(Task.title.like(f"{prefix}%"))
                    )
                ).scalar_one()
                assert count == 1
        finally:
            async with maker() as db:
                if conversation_id is not None:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation is not None:
                        await db.delete(conversation)
                await db.execute(delete(Task).where(Task.title.like(f"{prefix}%")))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_same_task_version_change_between_reads_halts_before_candidate(pg_dsn, monkeypatch):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        prefix = f"p1c-version-drift-{uuid4().hex}"
        candidate_title = f"{prefix}-candidate"
        source_id = None
        calls = 0
        read_calls = 0
        original_execute_read = mimi_service.execute_read_tool
        monkeypatch.setattr(mimi_service, "get_sessionmaker", lambda: maker)

        async def fake_completion(
            messages, *, settings, session_id, force_task_tool, agent_contract
        ):
            nonlocal calls
            calls += 1
            assert agent_contract and not force_task_tool
            if calls == 1:
                return _completion(
                    _read_request(
                        "source-read-a",
                        "task.query.v1",
                        {
                            "filter": {
                                "status": None,
                                "priority": None,
                                "due_from": None,
                                "due_through": None,
                                "title_contains": prefix,
                            },
                            "projection": ["id", "title", "status"],
                            "sort": "updated_desc",
                            "limit": 10,
                            "cursor": None,
                        },
                    ),
                    "source-read-a",
                )
            if calls == 2:
                return _completion(
                    _read_request(
                        "source-read-b",
                        "task.inspect_batch.v1",
                        {"ids": [str(source_id)], "projection": ["id", "title", "status"]},
                    ),
                    "source-read-b",
                )
            return _completion(_candidate(candidate_title), "candidate-after-version-drift")

        async def mutate_after_first_read(db, name, arguments):
            nonlocal read_calls
            result = await original_execute_read(db, name, arguments)
            read_calls += 1
            if read_calls == 1:
                async with maker() as writer:
                    source = await writer.get(Task, source_id)
                    source.title = f"{prefix}-changed"
                    source.updated_at = datetime.now(UTC) + timedelta(seconds=2)
                    await writer.commit()
            return result

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        monkeypatch.setattr(mimi_service, "execute_read_tool", mutate_after_first_read)
        try:
            async with maker() as db:
                await db.execute(text("SET LOCAL microsched.task_due_writer = 'v2'"))
                source = Task(title=f"{prefix}-source")
                db.add(source)
                await db.flush()
                source_id = source.id
                conversation_id = await _create_conversation(db, auth, "p1c-version-drift")
                await db.commit()

            result = await _run_message(
                maker,
                auth,
                conversation_id,
                "p1c-version-drift-run",
                "Read this Task twice then propose a new one",
            )
            run_view = result["runs"][-1]
            assert run_view["state"] == "halted"
            assert len(result["change_sets"]) == 0
            assert calls == 2, "provider was invoked after the repeated Task changed version"
            assert read_calls == 2

            async with maker() as db:
                run = await db.get(MimiRun, run_view["id"])
                assert (
                    run is not None
                    and run.error_code == "provider_contract_task_source_version_changed_during_run"
                )
                assert f"task:{source_id}" in run.source_versions
                count = (
                    await db.execute(
                        select(func.count()).select_from(Task).where(Task.title.like(f"{prefix}%"))
                    )
                ).scalar_one()
                assert count == 1
                terminal_events = (
                    (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.run_id == run.id, MimiEvent.kind == "run.terminal"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert terminal_events and terminal_events[-1].payload.get("state") == "halted"
        finally:
            async with maker() as db:
                if conversation_id is not None:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation is not None:
                        await db.delete(conversation)
                await db.execute(delete(Task).where(Task.title.like(f"{prefix}%")))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
