"""P1C draft and preview decision bindings on disposable PostgreSQL."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import service as mimi_service
from app.agent.context import Draft, PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiRun
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
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test" * 16)
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
        token_hash=f"mimi-p1c-decisions-{uuid4().hex}",
        user_email="owner@example.test",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
    )


async def _create_conversation(db, auth: AuthSession, client_id: str) -> UUID:
    result = await mimi_service.create_conversation(
        db, auth, mimi_service.ConversationCreate(client_id=client_id)
    )
    conversation_id = result["id"]
    return conversation_id if isinstance(conversation_id, UUID) else UUID(conversation_id)


def _preview(title: str) -> PreviewCandidate:
    return PreviewCandidate(tool=CREATE_CANDIDATE_TOOL, arguments={"title": title})


def _completion(outcome, response_id: str) -> AgentCompletion:
    return AgentCompletion(
        outcome=outcome,
        response_id=response_id,
        usage={"prompt_tokens": 12, "completion_tokens": 8},
        provider="Synthetic",
        model="synthetic/model",
    )


def test_first_time_draft_reject_binds_immutable_revision_without_task_write(pg_dsn, monkeypatch):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        before_tasks = 0

        async def fake_completion(
            messages, *, settings, session_id, force_task_tool, agent_contract
        ):
            assert agent_contract and not force_task_tool
            return _completion(Draft(text="Rà soát deadline trước khi sắp xếp."), "draft-1")

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                before_tasks = (
                    await db.execute(select(func.count()).select_from(Task))
                ).scalar_one()
                conversation_id = await _create_conversation(db, auth, "p1c-decision-draft")
                await db.commit()

            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-draft-reject-1",
                        content="Phác thảo cách sắp xếp deadline",
                        expected_generation=1,
                    ),
                )
                draft = result["draft"]
                assert draft["direction_state"] == "pending"
                assert result["change_sets"] == []
                await db.commit()

            decision = mimi_service.DraftDirectionDecision(
                draft_id=UUID(draft["id"]),
                expected_revision=draft["revision"],
                expected_content_sha256=draft["content_sha256"],
                decision="reject",
            )
            async with maker() as db:
                with pytest.raises(HTTPException) as stale_binding:
                    await mimi_service.decide_draft_direction(
                        db,
                        auth,
                        conversation_id,
                        decision.model_copy(update={"expected_content_sha256": "0" * 64}),
                    )
                assert stale_binding.value.status_code == 409
                await db.rollback()

            async with maker() as db:
                rejected = await mimi_service.decide_draft_direction(
                    db, auth, conversation_id, decision
                )
                assert rejected["state"] == "rejected"
                await db.commit()

            async with maker() as db:
                view = await mimi_service.conversation_view(db, auth, conversation_id)
                assert view["draft"]["direction_state"] == "rejected"
                assert view["change_sets"] == []
                with pytest.raises(HTTPException) as immutable:
                    await mimi_service.decide_draft_direction(
                        db,
                        auth,
                        conversation_id,
                        decision.model_copy(update={"decision": "approve"}),
                    )
                assert immutable.value.status_code == 409
                assert (
                    await db.execute(select(func.count()).select_from(Task))
                ).scalar_one() == before_tasks
        finally:
            if conversation_id is not None:
                async with maker() as db:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation is not None:
                        await db.delete(conversation)
                        await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_preview_revision_requires_exact_pending_digest_and_supersedes_old_preview(
    pg_dsn, monkeypatch
):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        calls = 0
        title_prefix = f"p1c-preview-revision-{uuid4().hex}"

        async def fake_completion(
            messages, *, settings, session_id, force_task_tool, agent_contract
        ):
            nonlocal calls
            calls += 1
            assert agent_contract
            assert force_task_tool is (calls > 1)
            return _completion(_preview(f"{title_prefix}-candidate-{calls}"), f"revision-{calls}")

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                conversation_id = await _create_conversation(db, auth, "p1c-decision-revision")
                await db.commit()

            async with maker() as db:
                first = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-preview-revision-1",
                        content="Tạo Task synthetic đầu tiên",
                        expected_generation=1,
                    ),
                )
                old = first["change_sets"][0]
                assert old["state"] == "pending"
                assert len(old["digest"]) == 64
                await db.commit()

            async with maker() as db:
                with pytest.raises(HTTPException) as stale_cas:
                    await mimi_service.send_message(
                        db,
                        auth,
                        conversation_id,
                        mimi_service.MessageCreate(
                            client_id="p1c-preview-revision-stale",
                            content="Sửa preview đầu tiên",
                            expected_generation=2,
                            intent="revise_pending_preview",
                            expected_change_set_id=old["id"],
                            expected_change_set_digest="0" * 64,
                        ),
                    )
                assert stale_cas.value.status_code == 409
                await db.rollback()
            assert calls == 1

            async with maker() as db:
                revised = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-preview-revision-2",
                        content="Sửa preview đầu tiên thành candidate thứ hai",
                        expected_generation=2,
                        intent="revise_pending_preview",
                        expected_change_set_id=old["id"],
                        expected_change_set_digest=old["digest"],
                    ),
                )
                assert revised["runs"][-1]["state"] == "waiting_confirmation"
                assert len(revised["change_sets"]) == 2
                old_after = next(item for item in revised["change_sets"] if item["id"] == old["id"])
                new = next(item for item in revised["change_sets"] if item["id"] != old["id"])
                assert old_after["state"] == "stale"
                assert new["state"] == "pending"
                assert new["digest"] != old["digest"]
                assert new["operation"]["args"]["title"] == f"{title_prefix}-candidate-2"
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(Task)
                        .where(Task.title.like(f"{title_prefix}%"))
                    )
                ).scalar_one() == 0
                await db.commit()
            assert calls == 2
        finally:
            if conversation_id is not None:
                async with maker() as db:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation is not None:
                        await db.delete(conversation)
                        await db.commit()
                    await db.execute(delete(Task).where(Task.title.like(f"{title_prefix}%")))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_mismatched_confirmation_and_stale_source_fail_before_task_write(pg_dsn, monkeypatch):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        title_prefix = f"p1c-decision-source-{uuid4().hex}"
        source_id = None

        async def fake_completion(
            messages, *, settings, session_id, force_task_tool, agent_contract
        ):
            assert agent_contract and not force_task_tool
            return _completion(_preview(f"{title_prefix}-created"), "source-preview")

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                await db.execute(text("SET LOCAL microsched.task_due_writer = 'v2'"))
                source = Task(title=f"{title_prefix}-source")
                db.add(source)
                await db.flush()
                source_id = source.id
                conversation_id = await _create_conversation(db, auth, "p1c-decision-source")
                await db.commit()

            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-source-preview-1",
                        content=f"Tạo Task {title_prefix}-created",
                        expected_generation=1,
                    ),
                )
                change_set = result["change_sets"][0]
                run = (
                    await db.execute(select(MimiRun).where(MimiRun.id == change_set["run_id"]))
                ).scalar_one()
                assert f"task:{source_id}" in run.source_versions
                await db.commit()

            async with maker() as db:
                with pytest.raises(HTTPException) as binding_mismatch:
                    await mimi_service.confirm_change_set(
                        db,
                        auth,
                        change_set["id"],
                        mimi_service.ConfirmationDecision(
                            digest="0" * 64,
                            nonce=change_set["nonce"],
                            decision="confirm",
                        ),
                        "p1c-confirm-mismatched",
                    )
                assert binding_mismatch.value.status_code == 409
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(Task)
                        .where(Task.title.like(f"{title_prefix}%"))
                    )
                ).scalar_one() == 1
                await db.rollback()

            async with maker() as db:
                source = await db.get(Task, source_id)
                source.title = f"{title_prefix}-source-edited"
                source.updated_at = datetime.now(UTC) + timedelta(seconds=1)
                await db.commit()

            async with maker() as db:
                stale_source = None
                try:
                    await mimi_service.confirm_change_set(
                        db,
                        auth,
                        change_set["id"],
                        mimi_service.ConfirmationDecision(
                            digest=change_set["digest"],
                            nonce=change_set["nonce"],
                            decision="confirm",
                        ),
                        "p1c-confirm-stale-source",
                    )
                except HTTPException as error:
                    stale_source = error
                owned_task_count = (
                    await db.execute(
                        select(func.count())
                        .select_from(Task)
                        .where(Task.title.like(f"{title_prefix}%"))
                    )
                ).scalar_one()
                assert stale_source is not None, (
                    "stale source was accepted; confirmation result wrote/left "
                    f"{owned_task_count - 1} new synthetic Task(s) in the transaction"
                )
                assert stale_source.status_code == 409
                assert owned_task_count == 1
                await db.rollback()

            async with maker() as db:
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(Task)
                        .where(Task.title.like(f"{title_prefix}%"))
                    )
                ).scalar_one() == 1
        finally:
            async with maker() as db:
                if conversation_id is not None:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation is not None:
                        await db.delete(conversation)
                await db.execute(delete(Task).where(Task.title.like(f"{title_prefix}%")))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_iterative_query_source_outside_prefetch_is_bound_and_stale_confirmation_rejected(
    pg_dsn, monkeypatch
):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        auth = _auth()
        conversation_id = None
        owned_ids: list[UUID] = []
        prefix = f"p1c-iterative-source-{uuid4().hex}"
        target_title = f"{prefix}-target"
        created_title = f"{prefix}-preview-created"
        target_version = datetime.now(UTC) - timedelta(days=30)
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
                    ToolRequests(
                        requests=(
                            ToolRequest(
                                call_id="iterative-source-read-1",
                                name="task.query.v1",
                                arguments={
                                    "filter": {
                                        "status": None,
                                        "priority": None,
                                        "due_from": None,
                                        "due_through": None,
                                        "title_contains": target_title,
                                    },
                                    "projection": ["id", "title", "status"],
                                    "sort": "updated_desc",
                                    "limit": 10,
                                    "cursor": None,
                                },
                            ),
                        )
                    ),
                    "iterative-source-read",
                )
            assert any(
                "KẾT QUẢ CÔNG CỤ ĐỌC" in str(message.get("content", "")) for message in messages
            )
            return _completion(_preview(created_title), "iterative-source-preview")

        monkeypatch.setattr(mimi_service, "openrouter_complete", fake_completion)
        try:
            async with maker() as db:
                await db.execute(text("SET LOCAL microsched.task_due_writer = 'v2'"))
                future_base = datetime.now(UTC) + timedelta(days=10)
                fillers = [
                    Task(
                        title=f"{prefix}-filler-{index:02}",
                        updated_at=future_base + timedelta(seconds=index),
                    )
                    for index in range(11)
                ]
                target = Task(title=target_title, updated_at=target_version)
                db.add_all([*fillers, target])
                await db.flush()
                owned_ids = [row.id for row in [*fillers, target]]
                target_id = target.id
                initial_prefetch = await mimi_service.list_standard_tasks(db, auth, limit=10)
                assert all(row["id"] != target_id for row in initial_prefetch)
                conversation_id = await _create_conversation(
                    db, auth, "p1c-iterative-source-binding"
                )
                await db.commit()

            async with maker() as db:
                result = await mimi_service.send_message(
                    db,
                    auth,
                    conversation_id,
                    mimi_service.MessageCreate(
                        client_id="p1c-iterative-source-preview-1",
                        content=f"Tạo Task theo dữ kiện {target_title}",
                        expected_generation=1,
                    ),
                )
                assert result["runs"][-1]["state"] == "waiting_confirmation"
                assert len(result["change_sets"]) == 1
                change_set = result["change_sets"][0]
                run = (
                    await db.execute(select(MimiRun).where(MimiRun.id == result["runs"][-1]["id"]))
                ).scalar_one()
                assert run.source_versions[f"task:{target_id}"] == target_version.isoformat()
                assert any(event["kind"] == "tool.read_result" for event in result["events"])
                await db.commit()
            assert calls == 2

            async with maker() as db:
                target = await db.get(Task, target_id)
                target.title = f"{prefix}-target-edited"
                target.updated_at = datetime.now(UTC) + timedelta(seconds=1)
                await db.commit()

            async with maker() as db:
                with pytest.raises(HTTPException) as stale:
                    await mimi_service.confirm_change_set(
                        db,
                        auth,
                        change_set["id"],
                        mimi_service.ConfirmationDecision(
                            digest=change_set["digest"],
                            nonce=change_set["nonce"],
                            decision="confirm",
                        ),
                        "p1c-confirm-iterative-source-stale",
                    )
                assert stale.value.status_code == 409
                assert stale.value.detail == "change_set_source_stale"

            async with maker() as db:
                assert (
                    await db.execute(
                        select(func.count()).select_from(Task).where(Task.title.like(f"{prefix}%"))
                    )
                ).scalar_one() == 12
        finally:
            async with maker() as db:
                if conversation_id is not None:
                    conversation = await db.get(MimiConversation, conversation_id)
                    if conversation is not None:
                        await db.delete(conversation)
                if owned_ids:
                    await db.execute(delete(Task).where(Task.id.in_(owned_ids)))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
