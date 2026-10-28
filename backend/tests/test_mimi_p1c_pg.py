"""P1C context-loop behavior on disposable PostgreSQL with no model egress."""

import asyncio
import base64
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import service as mimi_service
from app.agent.context import AssistantText, Draft, PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiProviderCall, MimiRun
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
    monkeypatch.setenv("OAUTH_STATE_SECRET", "mimi-p1c-pg-test")
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
        token_hash="mimi-p1c-synthetic-session",
        user_email="owner@example.test",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
    )


@pytest.mark.parametrize("valid_schedule", [True, False])
def test_agent_preview_schedule_and_durable_success(pg_dsn, monkeypatch, valid_schedule):
    """Wire drift must not erase a paid terminal or bypass preview validation."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        cid = None
        calls = 0

        async def completion(messages, **kwargs):
            nonlocal calls
            calls += 1
            return AgentCompletion(
                outcome=PreviewCandidate(
                    tool=CREATE_CANDIDATE_TOOL,
                    arguments={
                        "title": "Đối chiếu optimistic version",
                        "due_precision": "datetime",
                        "due_on": "2026-10-03",
                        "due_at": "2026-10-03T19:00:00+07:00" if valid_schedule else "invalid-time",
                        "items": ["Đọc", "Cập nhật", "Kiểm tra conflict"],
                    },
                ),
                response_id="synthetic-paid-terminal",
                usage={},
                provider="Synthetic",
                model="synthetic/model",
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", completion)
        try:
            async with maker() as db:
                cid = (
                    await mimi_service.create_conversation(
                        db, auth, mimi_service.ConversationCreate(client_id="schedule-drift")
                    )
                )["id"]
                await db.commit()
            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    cid,
                    mimi_service.MessageCreate(
                        client_id="schedule-turn",
                        content="Lập preview cho tối mai",
                        expected_generation=1,
                    ),
                )
                await db.commit()
                run = result["runs"][-1]
                assert run["state"] == ("waiting_confirmation" if valid_schedule else "halted")
                assert run["provider_outcome"] == "succeeded"
                call = (
                    await db.execute(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == run["id"])
                    )
                ).scalar_one()
                assert call.state == "succeeded"
                assert call.result["terminal_ciphertext"]
                assert call.result["response_id"] == "synthetic-paid-terminal"
                assert calls == 1
                if valid_schedule:
                    assert len(result["change_sets"]) == 1
                    operation = result["change_sets"][0]["operation"]
                    assert operation["args"]["due_on"] is None
                    assert datetime.fromisoformat(operation["args"]["due_at"]) == datetime(
                        2026, 10, 3, 12, tzinfo=UTC
                    )
                else:
                    assert not result["change_sets"]
                    assert "provider_task_schema_invalid" in run["error_code"]
        finally:
            if cid:
                async with maker() as db:
                    conversation = await db.get(MimiConversation, cid)
                    if conversation:
                        await db.delete(conversation)
                        await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_pause_preserves_durable_terminal_and_resume_does_not_redispatch(pg_dsn, monkeypatch):
    """Model result completes once; successor consumes it with a fresh lease."""

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        paid_calls = 0

        async def completion(messages, **kwargs):
            nonlocal paid_calls
            paid_calls += 1
            async with maker() as control:
                run = (
                    await control.execute(
                        select(MimiRun).where(
                            MimiRun.conversation_id == conversation_id,
                            MimiRun.state == "running",
                        )
                    )
                ).scalar_one()
                await mimi_service.request_run_pause(control, auth, run.id)
                await control.commit()
            return AgentCompletion(
                outcome=AssistantText(text="Đã đọc yêu cầu, vẫn giữ mục tiêu học."),
                response_id="synthetic-pause-once",
                usage={},
                provider="Synthetic",
                model="synthetic/model",
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", completion)
        try:
            async with maker() as db:
                created = await mimi_service.create_conversation(
                    db, auth, mimi_service.ConversationCreate(client_id="p1c-pause-successor")
                )
                conversation_id = created["id"]
                await db.commit()
            async with maker() as db:
                paused = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="pause-turn", content="Lập kế hoạch học", expected_generation=1
                    ),
                )
                assert paused["runs"][-1]["state"] == "halted"
                assert paused["runs"][-1]["error_code"] == "owner_paused"
                assert paused["runs"][-1]["resumable"]
                assert not any(m["role"] == "assistant" for m in paused["messages"])
                parent_id = paused["runs"][-1]["id"]
                await db.commit()
            async with maker() as db:
                cid, successor, payload = await mimi_service.prepare_run_resume(db, auth, parent_id)
                await db.commit()
            async with maker() as db:
                resumed = await mimi_service.send_message(
                    db,
                    auth,
                    cid,
                    payload,
                    reserved_run_id=successor,
                    record_user_message=False,
                    parent_run_id=parent_id,
                )
                await db.commit()
                assert resumed["runs"][-1]["state"] == "completed"
                assert resumed["messages"][-1]["content"] == "Đã đọc yêu cầu, vẫn giữ mục tiêu học."
                assert paid_calls == 1
                assert resumed["change_sets"] == []
                row = await db.get(MimiRun, successor)
                assert row.execution_lease["run_id"] == str(successor)
                assert successor != parent_id
        finally:
            if conversation_id:
                async with maker() as db:
                    row = await db.get(MimiConversation, conversation_id)
                    if row:
                        await db.delete(row)
                        await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_readonly_answer_then_preview_has_no_write_before_confirmation(pg_dsn, monkeypatch):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        calls: list[list[dict]] = []

        async def fake_completion(
            messages,
            *,
            settings,
            session_id,
            force_task_tool,
            agent_contract,
            final_answer_only=False,
        ):
            assert agent_contract is True
            assert force_task_tool is False
            assert settings.mimi_route_model == "synthetic/model"
            calls.append(messages)
            outcome = (
                AssistantText(text="Chào bạn, mình có thể giúp xem Task.")
                if len(calls) == 1
                else PreviewCandidate(
                    tool=CREATE_CANDIDATE_TOOL,
                    arguments={"title": "Chuẩn bị demo P1C"},
                )
            )
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-{len(calls)}",
                usage={"prompt_tokens": 12, "completion_tokens": 8},
                provider="Synthetic",
                model="synthetic/model",
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                created = await mimi_service.create_conversation(
                    db, auth, mimi_service.ConversationCreate(client_id="p1c-pg-conversation")
                )
                conversation_id = created["id"]
                await db.commit()

            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-readonly-1", content="Chào Mimi", expected_generation=1
                    ),
                )
                assert result["runs"][-1]["state"] == "completed"
                assert result["change_sets"] == []
                assert result["messages"][-1]["content"].startswith("Chào bạn")
                await db.commit()

            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-preview-2",
                        content="Tạo task Chuẩn bị demo P1C",
                        expected_generation=2,
                    ),
                )
                assert result["runs"][-1]["state"] == "waiting_confirmation"
                assert len(result["change_sets"]) == 1
                assert result["change_sets"][0]["operation"]["args"]["title"] == "Chuẩn bị demo P1C"
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(Task)
                        .where(Task.title == "Chuẩn bị demo P1C")
                    )
                ).scalar_one() == 0
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(MimiProviderCall)
                        .where(MimiProviderCall.run_id == result["runs"][-1]["id"])
                    )
                ).scalar_one() == 1
                await db.commit()
            assert len(calls) == 2
            assert any(message["role"] == "system" for message in calls[0])
        finally:
            if conversation_id is not None:
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


def test_draft_direction_is_not_write_confirmation(pg_dsn, monkeypatch):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None

        async def fake_completion(
            messages,
            *,
            settings,
            session_id,
            force_task_tool,
            agent_contract,
            final_answer_only=False,
        ):
            assert agent_contract and not force_task_tool
            return AgentCompletion(
                outcome=Draft(text="Phương án: rà soát ba deadline rồi mới sắp xếp Task."),
                response_id="synthetic-draft",
                usage={},
                provider="Synthetic",
                model="synthetic/model",
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                created = await mimi_service.create_conversation(
                    db, auth, mimi_service.ConversationCreate(client_id="p1c-pg-draft")
                )
                conversation_id = created["id"]
                before_tasks = (
                    await db.execute(select(func.count()).select_from(Task))
                ).scalar_one()
                await db.commit()

            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-draft-1",
                        content="Phác thảo cách tránh xung đột deadline",
                        expected_generation=1,
                    ),
                )
                # New plans are prose and never create a direction gate.
                assert result["draft"] is None
                assert "Phương án" in result["messages"][-1]["content"]
                # Preserve legacy receipt binding separately: historical events
                # remain valid without reintroducing that gate for new plans.
                last_message = result["messages"][-1]
                await mimi_service._append_event(
                    db,
                    UUID(str(result["runs"][-1]["id"])),
                    "draft.ready",
                    {
                        "draft_id": str(uuid4()),
                        "revision": 1,
                        "content_sha256": hashlib.sha256(
                            last_message["content"].encode()
                        ).hexdigest(),
                        "message_sequence": last_message["sequence"],
                        "state": "pending",
                    },
                )
                legacy = await mimi_service.conversation_view(db, auth, conversation_id)
                draft = legacy["draft"]
                assert draft["direction_state"] == "pending"
                assert result["change_sets"] == []
                assert (
                    await db.execute(select(func.count()).select_from(Task))
                ).scalar_one() == before_tasks
                await db.commit()

            decision = mimi_service.DraftDirectionDecision(
                draft_id=UUID(draft["id"]),
                expected_revision=draft["revision"],
                expected_content_sha256=draft["content_sha256"],
                decision="approve",
            )
            async with maker() as db:
                assert (
                    await mimi_service.decide_draft_direction(db, auth, conversation_id, decision)
                )["state"] == "approved"
                await db.commit()
            async with maker() as db:
                assert (
                    await mimi_service.decide_draft_direction(db, auth, conversation_id, decision)
                )["state"] == "approved"
                view = await mimi_service.conversation_view(db, auth, conversation_id)
                assert view["draft"]["direction_state"] == "approved"
                assert view["change_sets"] == []
                assert (
                    await db.execute(select(func.count()).select_from(Task))
                ).scalar_one() == before_tasks
                with pytest.raises(HTTPException) as stale:
                    await mimi_service.decide_draft_direction(
                        db,
                        auth,
                        conversation_id,
                        decision.model_copy(update={"decision": "reject"}),
                    )
                assert stale.value.status_code == 409
        finally:
            if conversation_id is not None:
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


def test_iterative_read_updates_context_without_writing(pg_dsn, monkeypatch):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        requests: list[list[dict]] = []
        monkeypatch.setattr(mimi_service, "get_sessionmaker", lambda: maker)

        async def fake_completion(
            messages,
            *,
            settings,
            session_id,
            force_task_tool,
            agent_contract,
            final_answer_only=False,
        ):
            assert agent_contract and not force_task_tool
            requests.append(messages)
            if len(requests) == 1:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="synthetic-read-1",
                            name="task.aggregate.v1",
                            arguments={"filter": {}, "group_by": "status"},
                        ),
                    )
                )
            else:
                assert any(message.get("role") == "tool" for message in messages)
                outcome = AssistantText(text="Không có Task STANDARD trong phạm vi đã đọc.")
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-read-{len(requests)}",
                usage={"prompt_tokens": 12, "completion_tokens": 8},
                provider="Synthetic",
                model="synthetic/model",
            )

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                created = await mimi_service.create_conversation(
                    db, auth, mimi_service.ConversationCreate(client_id="p1c-pg-read-loop")
                )
                conversation_id = created["id"]
                await db.commit()
            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-read-loop-1",
                        content="Có bao nhiêu Task STANDARD theo trạng thái?",
                        expected_generation=1,
                    ),
                )
                assert result["runs"][-1]["state"] == "completed"
                assert result["change_sets"] == []
                assert result["messages"][-1]["content"].startswith("Không có Task")
                assert any(event["kind"] == "tool.read_result" for event in result["events"])
                await db.commit()
            assert len(requests) == 2
        finally:
            if conversation_id is not None:
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
