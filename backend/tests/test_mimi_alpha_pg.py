"""Persisted delayed observation and live run guard on disposable PostgreSQL."""

import asyncio
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto as mimi_crypto
from app.agent import runtime, service
from app.agent.context import AssistantText
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiProviderCall, MimiRun
from app.agent.observations import context_revision
from app.agent.openrouter import AgentCompletion
from app.agent.route_config import bind_configuration
from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def synthetic_crypto(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "phase1-disposable-only")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(b"s" * 32).decode())
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


async def _remove_own_conversations(maker, ids):
    # Exact generated IDs only, on pg_dsn's sanctioned disposable database.
    # Conversation FK cascade removes this test's runs/provider/events/history.
    owned_ids = [cid for cid in ids if cid is not None]
    async with maker() as db:
        for cid in owned_ids:
            row = await db.get(MimiConversation, cid)
            if row is not None:
                await db.delete(row)
        await db.commit()
        assert (
            await db.execute(
                select(func.count())
                .select_from(MimiConversation)
                .where(MimiConversation.id.in_(owned_ids))
            )
        ).scalar_one() == 0


def make_run(cid, *, state="building", generation=1):
    return MimiRun(
        id=uuid7(),
        conversation_id=cid,
        generation=generation,
        state=state,
        execution_lease={},
        source_versions={},
        deadline=datetime.now(UTC) + timedelta(minutes=5),
    )


@pytest.mark.parametrize("invalid_helper", [False, True])
def test_observed_main_triggers_next_turn_once_and_preserves_canonical_authority(
    pg_dsn, monkeypatch, invalid_helper
):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        wrapped = mimi_crypto.create_wrapped_dek()
        dek = mimi_crypto.unwrap_dek(wrapped)
        conversation = MimiConversation(
            id=uuid7(),
            owner_id=uuid7(),
            sensitivity="standard",
            dek_wrapped=wrapped,
            next_message_sequence=4,
        )
        previous, current = (
            make_run(conversation.id, state="completed"),
            make_run(conversation.id, generation=2),
        )
        settings = bind_configuration(
            get_settings(), {"profile_id": "deepseek", "effort": "high", "input_tokens": 100_000}
        )
        calls = 0

        async def summary(messages, **kwargs):
            nonlocal calls
            calls += 1
            assert kwargs["settings"].mimi_route_context_tokens == 1_048_576
            sources = json.loads(messages[-1]["content"])["sources"]
            candidate = {
                "summary": "Giữ lịch học 20 giờ và yêu cầu mới trong nguồn chính.",
                "constraints": [],
                "supersessions": [],
                "resolutions": [],
            }
            if invalid_helper:
                candidate["summary"] = ""
            else:
                source = sources[0]
                candidate["constraints"] = [
                    {
                        "text": "Học lúc20giờ",
                        "kind": "decision",
                        "source_sequence": source["sequence"],
                        "source_sha256": source["sha256"],
                        "quote": "Học lúc 20 giờ",
                    }
                ]
            return AgentCompletion(
                outcome=AssistantText(text=json.dumps(candidate, ensure_ascii=False)),
                response_id=f"synthetic-helper-{calls}",
                usage={"prompt_tokens": 190_000, "cost": 0.05},
                provider="DeepInfra",
                model=settings.mimi_route_model,
            )

        monkeypatch.setattr(service, "openrouter_complete", summary)
        frozen = {
            "id": str(uuid7()),
            "digest": "a" * 64,
            "expiry": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "source_versions": {},
        }
        try:
            async with maker() as db:
                db.add(conversation)
                await db.flush()
                db.add_all([previous, current])
                await db.flush()
                for sequence, role, content in (
                    (1, "user", "Học lúc 20 giờ"),
                    (2, "assistant", "Mình ghi nhận yêu cầu."),
                    (3, "user", "Thêm suffix mới, chưa Confirm."),
                ):
                    raw = content.encode()
                    db.add(
                        MimiMessage(
                            conversation_id=conversation.id,
                            run_id=previous.id,
                            sequence=sequence,
                            role=role,
                            content_bytes=len(raw),
                            content_sha256=hashlib.sha256(raw).hexdigest(),
                            content_ciphertext=mimi_crypto.seal_content(
                                dek,
                                content,
                                aad=mimi_crypto.message_aad(conversation.id, sequence, role),
                            ),
                        )
                    )
                main = MimiProviderCall(
                    run_id=previous.id,
                    attempt=1,
                    state="succeeded",
                    request_fingerprint="a" * 64,
                    usage={"prompt_tokens": 100_001, "cost": 0.3},
                    result={"response_id": "synthetic-main"},
                    route={
                        "kind": "openrouter",
                        "purpose": "main",
                        "context_revision": context_revision(settings, 1, None),
                        "model": settings.mimi_route_model,
                        "actual_model": settings.mimi_route_model,
                        "providers": ["deepinfra"],
                        "actual_provider": "DeepInfra",
                    },
                )
                db.add(main)
                await db.commit()
                if invalid_helper:
                    with pytest.raises(
                        HTTPException, match="compaction_candidate_invalid_history_preserved"
                    ):
                        await service._prepare_context_history(
                            db, conversation, dek, current.id, 3, frozen, None, settings=settings
                        )
                    assert conversation.context_frontier_sequence == 0
                else:
                    _, _, checkpoint, checkpoint_id = await service._prepare_context_history(
                        db, conversation, dek, current.id, 3, frozen, None, settings=settings
                    )
                    await db.commit()
                    assert checkpoint["pending_preview"] == frozen
                    assert checkpoint["constraint_ledger"][0]["source"]["quote"] == "Học lúc 20 giờ"
                    assert checkpoint_id and conversation.context_frontier_sequence == 2
                # Receipt is consumed durably even if the helper failed. A helper's
                # larger usage and a new suffix must not redispatch another helper.
                next_run = make_run(conversation.id, generation=3)
                db.add(next_run)
                await db.commit()
                if invalid_helper:
                    with pytest.raises(HTTPException, match="mimi_compaction_required_unactivated"):
                        await service._prepare_context_history(
                            db, conversation, dek, next_run.id, 4, frozen, None, settings=settings
                        )
                else:
                    await service._prepare_context_history(
                        db, conversation, dek, next_run.id, 4, frozen, None, settings=settings
                    )
                await db.commit()
                assert calls == 1
                events = (
                    (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.run_id == next_run.id,
                                MimiEvent.kind == "context.usage.observed",
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert events[0].payload["reason"] == (
                    "compaction_required_unactivated"
                    if invalid_helper
                    else "stale_context_revision"
                )
                assert (
                    await db.execute(
                        select(func.count())
                        .select_from(MimiMessage)
                        .where(MimiMessage.conversation_id == conversation.id)
                    )
                ).scalar_one() == 3
                decisions = (
                    (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.run_id == current.id,
                                MimiEvent.kind == "context.compaction.decided",
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(decisions) == 1 and decisions[0].payload["source_call_id"] == str(
                    main.id
                )
        finally:
            await _remove_own_conversations(maker, [conversation.id])
            await engine.dispose()

    asyncio.run(scenario())


def test_service_commit_does_not_release_dispatch_guard_or_admit_orphan(pg_dsn, monkeypatch):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn), pool_size=5, max_overflow=10)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(runtime, "get_engine", lambda: engine)
        monkeypatch.setattr(service, "get_engine", lambda: engine)
        settings = get_settings().model_copy(
            update={
                "mimi_context_v1_enabled": True,
                "mimi_live_provider_enabled": True,
                "mimi_max_active_runs": 2,
            }
        )
        monkeypatch.setattr(runtime, "get_settings", lambda: settings)
        cid = uuid7()
        run = make_run(cid, state="running")
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
                db.add(run)
                await db.flush()
                db.add(
                    MimiProviderCall(
                        run_id=run.id,
                        attempt=1,
                        state="dispatched",
                        request_fingerprint="b" * 64,
                        route={"kind": "openrouter", "run_guard_version": 1},
                    )
                )
                await db.commit()
                async with runtime.hold_run_guard_if_enabled(run.id):
                    await db.execute(text("SELECT 1"))
                    await db.commit()  # service session returns its connection
                    async with engine.connect() as contender:
                        assert not (
                            await contender.execute(
                                text("SELECT pg_try_advisory_xact_lock(:key)"),
                                {"key": runtime.run_guard_key(run.id)},
                            )
                        ).scalar_one()
                    async with maker() as reconciler:
                        await service.reconcile_orphaned_mimi_runs(reconciler)
                        await reconciler.commit()
                    await db.refresh(run)
                    assert run.state == "running" and run.provider_outcome is None
                    # With two Mimi slots occupied, a third fails immediately;
                    # ordinary Task traffic still obtains the shared connection.
                    async with runtime.hold_run_guard_if_enabled(uuid7()):
                        with pytest.raises(HTTPException, match="mimi_busy_try_later"):
                            runtime.admit_run(uuid7())
                        async with maker() as ordinary:
                            assert (
                                await ordinary.execute(text("SELECT count(*) FROM microsched.task"))
                            ).scalar_one() >= 0
                            from app.domain.models import AuthSession
                            from app.domain.tasks import TaskCreate, TaskStore

                            auth = AuthSession(
                                token_hash="ordinary-busy-test",
                                user_email="ordinary@example.invalid",
                                expires_at=datetime.now(UTC) + timedelta(hours=1),
                            )
                            created = await TaskStore().create(
                                ordinary,
                                auth,
                                TaskCreate(title="Phase1 ordinary Task while Mimi busy"),
                            )
                            await ordinary.commit()
                            assert created.title == "Phase1 ordinary Task while Mimi busy"
                async with maker() as reconciler:
                    await service.reconcile_orphaned_mimi_runs(reconciler)
                    await reconciler.commit()
                await db.refresh(run)
                assert run.state == "outcome_unknown" and run.provider_outcome == "unknown"
        finally:
            await _remove_own_conversations(maker, [cid])
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("helper_outcome", ["invalid", "unknown"])
def test_failed_helper_cannot_silently_continue_main_in_same_epoch(
    pg_dsn, monkeypatch, helper_outcome
):
    from uuid import UUID

    from app.domain.models import AuthSession

    for name, value in {
        "MIMI_REAL_CHAT_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash",
        "MIMI_ROUTE_PROVIDER": "deepinfra",
        "MIMI_ROUTE_QUANTIZATION": "fp8",
        "MIMI_ROUTE_REASONING_EFFORT": "high",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        main_calls, helper_calls = 0, 0

        async def provider(messages, **kwargs):
            nonlocal main_calls, helper_calls
            if kwargs.get("summary_mode"):
                helper_calls += 1
                if helper_outcome == "unknown":
                    from app.agent.openrouter import ProviderDispatchError

                    raise ProviderDispatchError("unknown", None)
                return AgentCompletion(
                    outcome=AssistantText(
                        text=json.dumps(
                            {
                                "summary": "",
                                "constraints": [],
                                "supersessions": [],
                                "resolutions": [],
                            }
                        )
                    ),
                    response_id="synthetic-invalid-helper",
                    usage={"cost": 0.02},
                    model="deepseek/deepseek-v4.1-flash",
                    provider="DeepInfra",
                )
            main_calls += 1
            return AgentCompletion(
                outcome=AssistantText(text="Mình đã hiểu yêu cầu."),
                response_id="synthetic-first-main",
                usage={"prompt_tokens": 100_001, "cost": 0.03},
                model="deepseek/deepseek-v4.1-flash",
                provider="DeepInfra",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        auth = AuthSession(
            token_hash="phase1-synthetic",
            user_email="phase1@example.invalid",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        cid = None
        try:
            async with maker() as db:
                created = await service.create_conversation(db, auth, service.ConversationCreate())
                cid = UUID(str(created["id"]))
                await db.commit()
                first = await service.send_message(
                    db,
                    auth,
                    cid,
                    service.MessageCreate(client_id="alpha-first", content="Chào Mimi"),
                )
                assert first["runs"][-1]["state"] == "completed"
                with pytest.raises(
                    HTTPException,
                    match=(
                        "compaction_provider_outcome_requires_review"
                        if helper_outcome == "unknown"
                        else "compaction_candidate_invalid_history_preserved"
                    ),
                ):
                    await service.send_message(
                        db,
                        auth,
                        cid,
                        service.MessageCreate(
                            client_id="alpha-failed-helper", content="Tiếp tục kế hoạch"
                        ),
                    )
                with pytest.raises(HTTPException, match="mimi_compaction_required_unactivated"):
                    await service.send_message(
                        db,
                        auth,
                        cid,
                        service.MessageCreate(
                            client_id="alpha-blocked-next", content="Tiếp tục lượt sau"
                        ),
                    )
                assert main_calls == 1 and helper_calls == 1
                view = await service.conversation_view(db, auth, cid)
                assert view["runs"][-1]["error_code"] == "mimi_compaction_required_unactivated"
                assert not view["receipts"] and not view["change_sets"]
                assert view["runs"][-1]["state"] == "budget_exceeded"
                # Clear product recovery path: new conversation has a new epoch.
                next_conversation = await service.create_conversation(
                    db, auth, service.ConversationCreate()
                )
                assert next_conversation["id"] != created["id"]
        finally:
            await _remove_own_conversations(maker, [cid])
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("runner", ["current", "langgraph"])
@pytest.mark.parametrize("execution_limits", [(32, 64), (12, 24)])
def test_bounded_read_completes_then_auto_compacts_next_conversation_turn(
    pg_dsn, monkeypatch, runner, execution_limits
):
    from uuid import UUID

    from app.agent.context import ToolRequest, ToolRequests
    from app.domain.models import AuthSession

    for name, value in {
        "APP_ENV": "production",
        "DATABASE_URL": async_postgres_url(pg_dsn),
        "MIMI_PUBLIC_ORIGIN": "https://alpha.example.invalid",
        "MIMI_RUNNER": runner,
        "MIMI_RUN_MAX_TURNS": str(execution_limits[0]),
        "MIMI_RUN_MAX_TOOL_CALLS": str(execution_limits[1]),
        "MIMI_REAL_CHAT_ENABLED": "true",
        "MIMI_LIVE_PROVIDER_ENABLED": "true",
        "MIMI_CONTEXT_V1_ENABLED": "true",
        "MIMI_STANDARD_API_KEY": "synthetic-never-sent",
        "MIMI_ROUTE_MODEL": "deepseek/deepseek-v4.1-flash",
        "MIMI_ROUTE_PROVIDER": "deepinfra",
        "MIMI_ROUTE_QUANTIZATION": "fp8",
        "MIMI_ROUTE_REASONING_EFFORT": "high",
        "MIMI_ROUTE_MAX_INPUT_PRICE": "0.2",
        "MIMI_ROUTE_MAX_OUTPUT_PRICE": "0.6",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        main_calls, helper_calls = 0, 0

        async def provider(messages, **kwargs):
            nonlocal main_calls, helper_calls
            if kwargs.get("summary_mode"):
                helper_calls += 1
                outcome = AssistantText(
                    text=json.dumps(
                        {
                            "summary": "Đã đọc Task STANDARD theo yêu cầu.",
                            "constraints": [],
                            "supersessions": [],
                            "resolutions": [],
                        }
                    )
                )
                return AgentCompletion(
                    outcome=outcome,
                    response_id="synthetic-safe-turn-helper",
                    usage={"prompt_tokens": 140_000, "cost": 0.02},
                    model="deepseek/deepseek-v4.1-flash",
                    provider="DeepInfra",
                )
            main_calls += 1
            if main_calls <= 4:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id=f"alpha-read-{main_calls}",
                            name="task.aggregate.v1",
                            arguments={
                                "filter": {"title_contains": f"synthetic-step-{main_calls}"},
                                "group_by": "status",
                            },
                        ),
                    )
                )
            else:
                outcome = AssistantText(text="Đã hoàn tất lượt đọc Task STANDARD.")
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-main-{main_calls}",
                usage={
                    "prompt_tokens": 100_001 + main_calls if main_calls <= 5 else 30,
                    "cost": 0.03,
                },
                model="deepseek/deepseek-v4.1-flash",
                provider="DeepInfra",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        auth = AuthSession(
            token_hash="phase1-safe-turn",
            user_email="safe-turn@example.invalid",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        cid = None
        try:
            async with maker() as db:
                conversation = await service.create_conversation(
                    db, auth, service.ConversationCreate()
                )
                cid = UUID(str(conversation["id"]))
                await db.commit()
                view = await service.send_message(
                    db,
                    auth,
                    cid,
                    service.MessageCreate(client_id="alpha-loop", content="Đọc Task đang mở"),
                )
                await db.commit()  # Match the router/request transaction boundary.
                assert main_calls == 5 and helper_calls == 0
                initial_run = await db.get(MimiRun, UUID(str(view["runs"][-1]["id"])))
                assert (
                    initial_run.execution_lease["max_turns"],
                    initial_run.execution_lease["max_tool_calls"],
                ) == execution_limits
                assert view["runs"][-1]["state"] == "completed"
                assert view["runs"][-1]["error_code"] is None
                latest_main = view["provider_calls"][-1]
                assert (
                    latest_main["state"] == "succeeded"
                    and latest_main["usage"]["prompt_tokens"] > 100_000
                )
                assert not view["receipts"] and not view["change_sets"]
                continued = await service.send_message(
                    db,
                    auth,
                    cid,
                    service.MessageCreate(
                        client_id="alpha-next", content="Giữ các yêu cầu và tiếp tục"
                    ),
                )
                await db.commit()
                assert main_calls == 6 and helper_calls == 1
                assert continued["runs"][-1]["state"] == "completed"
                current_run = str(continued["runs"][-1]["id"])
                compact = [
                    event
                    for event in continued["events"]
                    if event["kind"] == "context.compaction.decided"
                    and str(event["run_id"]) == current_run
                ]
                assert len(compact) == 1 and compact[0]["payload"]["source_call_id"] == str(
                    latest_main["id"]
                )
                assert any(
                    event["kind"] == "context.checkpoint.activated"
                    and str(event["run_id"]) == current_run
                    for event in continued["events"]
                )
                assert continued["provider_calls"][-2]["purpose"] == "compaction"
                assert continued["provider_calls"][-1]["purpose"] == "main"
            # The completed snapshot must also survive a new request/session.
            async with maker() as persisted:
                durable = await persisted.get(MimiRun, UUID(current_run))
                assert durable.state == "completed" and durable.completed_at is not None
        finally:
            await _remove_own_conversations(maker, [cid])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop)
