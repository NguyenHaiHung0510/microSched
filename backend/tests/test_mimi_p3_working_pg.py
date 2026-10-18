"""Finalized P3 continuity on its own disposable DB; model/checkpointer doubles only."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import langgraph_runner, service
from app.agent.context import AssistantText, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent, MimiMessage, MimiProviderCall
from app.agent.openrouter import AgentCompletion
from app.agent.working_context import KIND
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.mark.parametrize("runner", ["current", "langgraph"])
@pytest.mark.usefixtures("local_sync_contract")
def test_two_normal_finalized_turns_keep_ordered_pairs_then_rollback_or_privacy_gap(
    pg_dsn, monkeypatch, runner
):
    monkeypatch.setenv("MIMI_RUNNER", runner)
    if runner == "langgraph":
        real_graph = langgraph_runner.run_langgraph

        async def graph(*args, **kwargs):
            return await real_graph(*args, **kwargs, checkpointer_for_test=InMemorySaver())

        monkeypatch.setattr(service, "_run_langgraph_agent", graph)
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        cid, ids = None, []
        actor = auth()
        calls = []
        read_count = 0
        prefix = "synthetic-p3-" + uuid4().hex
        original_read = service.execute_read_tool

        async def read(*args, **kwargs):
            nonlocal read_count
            read_count += 1
            return await original_read(*args, **kwargs)

        monkeypatch.setattr(service, "execute_read_tool", read)

        async def provider(messages, **kwargs):
            calls.append(json.loads(json.dumps(messages)))
            stage = len(calls)
            if stage == 1:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="first-exact-id",
                            name="task.query.v1",
                            arguments={
                                "filter": {"title_contains": prefix},
                                "projection": ["id", "title", "status"],
                            },
                        ),
                    )
                )
            else:
                tools = [m for m in messages if m["role"] == "tool"]
                if stage in (2, 3, 4, 5):
                    assert (
                        len(tools) == (1 if stage in (2, 3) else 2)
                        and tools[0]["tool_call_id"] == "first-exact-id"
                    )
                    assert json.loads(tools[0]["content"])["rows"][0]["title"] == prefix
                    position = messages.index(tools[0])
                    assert messages[position - 1]["tool_calls"][0]["id"] == "first-exact-id"
                else:
                    assert not tools  # rollback/eligibility do not reconstruct an old read.
                if stage == 3:
                    assert sum(m.get("content") == "Đọc Task mẫu" for m in messages) == 1
                    assert (
                        sum(m.get("content") == "Đã đọc Task mẫu, chưa ghi." for m in messages) == 1
                    )
                if stage == 3:
                    return AgentCompletion(
                        outcome=ToolRequests(
                            requests=(
                                ToolRequest(
                                    call_id="second-exact-id",
                                    name="task.query.v1",
                                    arguments={
                                        "filter": {"title_contains": prefix},
                                        "projection": ["title"],
                                    },
                                ),
                            )
                        ),
                        response_id="synthetic-second-read",
                        usage={"cost": 0},
                        model=kwargs["settings"].mimi_route_model,
                        provider="Synthetic",
                    )
                if stage in (4, 5):
                    assert [t["tool_call_id"] for t in tools] == [
                        "first-exact-id",
                        "second-exact-id",
                    ]
                outcome = AssistantText(
                    text="Đã đọc Task mẫu, chưa ghi."
                    if stage == 2
                    else f"Tiếp tục phạm vi cũ {stage}; chỉ là lịch sử."
                )
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-p3-{stage}",
                usage={"prompt_tokens": 1000 + stage, "completion_tokens": 20, "cost": 0},
                model=kwargs["settings"].mimi_route_model,
                provider="Synthetic",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                task = Task(title=prefix)
                db.add(task)
                await db.flush()
                ids = [task.id]
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                await db.commit()
            for turn, content in enumerate(
                ["Đọc Task mẫu", "Tiếp tục từ phạm vi vừa đọc", "Giữ lại phạm vi lịch sử"], 1
            ):
                async with maker() as db:
                    view = await service.send_message(
                        db,
                        actor,
                        cid,
                        service.MessageCreate(
                            client_id=f"p3-{turn}", content=content, expected_generation=turn
                        ),
                    )
                    assert view["runs"][-1]["state"] == "completed", (
                        view["runs"][-1]["error_code"],
                        len(calls),
                    )
                    await db.commit()
            assert read_count == 2 and len(calls) == 5
            async with maker() as db:
                events = (
                    (
                        await db.execute(
                            select(MimiEvent).where(
                                MimiEvent.kind == KIND,
                                MimiEvent.run_id.in_(
                                    [
                                        UUID(r["id"]) if isinstance(r["id"], str) else r["id"]
                                        for r in view["runs"]
                                    ]
                                ),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(events) == 3
                assert sum(e.payload["pair_count"] for e in events) == 2
                assert prefix not in json.dumps([e.payload for e in events])
                assert all(
                    "body_ciphertext" not in event["payload"]
                    for event in view["events"]
                    if event["kind"] == KIND
                )
                calls_db = (
                    (
                        await db.execute(
                            select(MimiProviderCall).where(
                                MimiProviderCall.run_id == events[-1].run_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert all(
                    c.route.get("input_projection", {}).get("request_fingerprint")
                    == c.request_fingerprint
                    for c in calls_db
                )
                count_messages = (
                    (
                        await db.execute(
                            select(MimiMessage).where(MimiMessage.conversation_id == cid)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(count_messages) == 6
                # Changing STANDARD eligibility removes exact old pairs without requerying content.
                task = await db.get(Task, ids[0])
                task.is_private = True
                task.title = "enc:v1:synthetic"
                task.body_md = None
                await db.commit()
            async with maker() as db:
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="p3-private", content="Tiếp tục", expected_generation=4
                    ),
                )
                assert view["runs"][-1]["state"] == "completed", (
                    view["runs"][-1]["error_code"],
                    len(calls),
                )
                manifests = [e for e in view["events"] if e["kind"] == "context.manifest"]
                assert manifests[-1]["payload"]["working_history"]["coverage"] == "partial"
                await db.commit()
            monkeypatch.setenv("MIMI_WORKING_PROJECTION_ENABLED", "0")
            get_settings.cache_clear()
            async with maker() as db:
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="p3-rollback",
                        content="Rollback đọc lịch sử canonical",
                        expected_generation=5,
                    ),
                )
                assert view["runs"][-1]["state"] == "completed", (
                    view["runs"][-1]["error_code"],
                    len(calls),
                )
                await db.commit()
            assert read_count == 2
        finally:
            if cid:
                await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.usefixtures("local_sync_contract")
@pytest.mark.parametrize("failure", [None, "invalid", "working_cas", "frontier_cas"])
def test_compaction_uses_exact_finalized_working_frontier_and_keeps_safe_suffix(
    pg_dsn,
    monkeypatch,
    failure,
):
    from fastapi import HTTPException

    from app.agent import crypto
    from app.agent.models import MimiRun

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        cid = None
        actor = auth()
        dispatches = []

        async def provider(messages, **kwargs):
            dispatches.append(messages)
            if kwargs.get("summary_mode"):
                payload = json.loads(messages[-1]["content"])
                working = [s["working_history"] for s in payload["sources"] if s["working_history"]]
                assert any(
                    w["messages"] and w["messages"][0]["tool_calls"][0]["id"] == "compact-exact"
                    for w in working
                )
                if failure:
                    async with maker() as concurrent:
                        if failure == "frontier_cas":
                            conv = await concurrent.get(MimiConversation, cid)
                            conv.generation += 1
                        elif failure == "working_cas":
                            event = (
                                (
                                    await concurrent.execute(
                                        select(MimiEvent)
                                        .join(MimiRun, MimiEvent.run_id == MimiRun.id)
                                        .where(
                                            MimiRun.conversation_id == cid, MimiEvent.kind == KIND
                                        )
                                    )
                                )
                                .scalars()
                                .first()
                            )
                            event.payload = {**event.payload, "sha256": "0" * 64}
                        await concurrent.commit()
                return AgentCompletion(
                    outcome=AssistantText(
                        text=json.dumps(
                            {
                                "summary": "..."
                                if failure == "invalid"
                                else (
                                    "Đã đọc phạm vi open lúc 18/10; không có Task khớp, chưa ghi; "
                                    "vẫn giữ yêu cầu chỉ đọc."
                                ),
                                "constraints": [],
                                "supersessions": [],
                                "resolutions": [],
                            },
                            ensure_ascii=False,
                        )
                    ),
                    response_id="synthetic-compact",
                    usage={"cost": 0},
                    model=kwargs["settings"].mimi_route_model,
                    provider="Synthetic",
                )
            if len(dispatches) == 1:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="compact-exact",
                            name="task.query.v1",
                            arguments={"filter": {"title_contains": "p3-no-matches-" + str(cid)}},
                        ),
                    )
                )
            else:
                outcome = AssistantText(text="Đã đọc phạm vi open. Không có Task khớp, chưa ghi.")
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-compact-{len(dispatches)}",
                usage={"cost": 0},
                model=kwargs["settings"].mimi_route_model,
                provider="Synthetic",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, actor, service.ConversationCreate()))[
                    "id"
                ]
                await db.commit()
            async with maker() as db:
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="p3-compact-first",
                        content="Chỉ đọc phạm vi open",
                        expected_generation=1,
                    ),
                )
                assert view["runs"][-1]["state"] == "completed"
                await db.commit()
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                run = MimiRun(
                    conversation_id=cid,
                    generation=3,
                    state="building",
                    execution_lease={},
                    source_versions={},
                    deadline=service.datetime.now(service.UTC) + service.timedelta(minutes=5),
                )
                db.add(run)
                await db.flush()
                # Keep a newer canonical suffix outside the compacted working unit.
                for i in range(12):
                    await service._add_assistant_message(
                        db,
                        conv,
                        run.id,
                        crypto.unwrap_dek(conv.dek_wrapped),
                        f"Suffix progress {i}",
                        producer_code="local_deterministic_result",
                    )
                await db.commit()
                settings = service.bind_configuration(
                    get_settings(),
                    {"profile_id": "deepseek", "effort": "high", "input_tokens": 272000},
                )
                await observed_trigger(db, conv, run.id, settings)
                history = service.WorkingHistory()
                if failure:
                    with pytest.raises(HTTPException) as rejected:
                        await service._prepare_context_history(
                            db,
                            conv,
                            crypto.unwrap_dek(conv.dek_wrapped),
                            run.id,
                            conv.next_message_sequence,
                            None,
                            None,
                            settings=settings,
                            working_history=history,
                        )
                    assert rejected.value.status_code == 409
                    await db.refresh(conv)
                    assert conv.context_frontier_sequence == 0
                    assert (
                        not (
                            await db.execute(
                                select(MimiEvent).where(
                                    MimiEvent.run_id == run.id,
                                    MimiEvent.kind == "context.checkpoint.activated",
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                else:
                    suffix, span, checkpoint, _ = await service._prepare_context_history(
                        db,
                        conv,
                        crypto.unwrap_dek(conv.dek_wrapped),
                        run.id,
                        conv.next_message_sequence,
                        None,
                        None,
                        settings=settings,
                        working_history=history,
                    )
                    assert checkpoint["working_frontier"]["message_sequence"] == 12
                    assert len(checkpoint["working_sources"]) == 1
                    assert span == (13, 14)
                    assert [m["content"] for m in suffix] == [
                        "Suffix progress 10",
                        "Suffix progress 11",
                    ]
                    assert all(m["role"] != "tool" for m in suffix)
                    await db.commit()
        finally:
            if cid:
                await cleanup(maker, cid, [])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.usefixtures("local_sync_contract")
def test_confirmed_receipt_survives_next_normal_run_and_compaction_without_effect_replay(
    pg_dsn,
    monkeypatch,
):
    from test_mimi_collection_service_pg import prepare

    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    get_settings.cache_clear()
    from sqlalchemy import func

    from app.agent import crypto
    from app.agent.models import MimiExecutionReceipt, MimiRun
    from app.agent.working_context import WorkingHistory

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, rid, ids, change_id, decision = await prepare(maker)
        calls = []

        async def provider(messages, **kwargs):
            calls.append(messages)
            if kwargs.get("summary_mode"):
                payload = json.loads(messages[-1]["content"])
                outcomes = [
                    s["working_history"]["finalized_outcome"]
                    for s in payload["sources"]
                    if s["working_history"] and s["working_history"]["finalized_outcome"]
                ]
                assert len(outcomes) == 1 and outcomes[0]["state"] == "executed"
                assert outcomes[0]["count"] == 2
                text = json.dumps(
                    {
                        "summary": (
                            "Owner đã Confirm; receipt xác nhận 2 Task đã đổi priority; "
                            "không còn pending preview. Chỉ là kết quả lịch sử."
                        ),
                        "constraints": [],
                        "supersessions": [],
                        "resolutions": [],
                    },
                    ensure_ascii=False,
                )
            else:
                terminal = [
                    json.loads(m["content"].split("\n", 1)[1])
                    for m in messages
                    if m.get("content", "")
                    and m["content"].startswith("SERVER-PROVIDED HISTORICAL OUTCOME")
                ]
                assert len(terminal) == 1
                assert terminal[0]["receipt_id"] == str(receipt_id)
                assert terminal[0]["state"] == "executed" and terminal[0]["count"] == 2
                assert terminal[0]["changes"] == [{"action": "edit", "fields": ["priority"]}] * 2
                assert "nonce" not in json.dumps(terminal) and "execution_lease" not in json.dumps(
                    terminal
                )
                assert (
                    sum(
                        m.get("content", "").startswith("Đã áp dụng thay đổi cho 2 Task")
                        for m in messages
                    )
                    == 1
                )
                text = (
                    "Bạn đã xác nhận, receipt ghi nhận 2 Task đã đổi ưu tiên; "
                    "chưa có hành động mới."
                )
            return AgentCompletion(
                outcome=AssistantText(text=text),
                response_id=f"synthetic-after-confirm-{len(calls)}",
                usage={"cost": 0},
                model=kwargs["settings"].mimi_route_model,
                provider="Synthetic",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                result = await service.confirm_change_set(
                    db, actor, change_id, decision, "synthetic-p3-confirm"
                )
                receipt_id = result["id"]
                await db.commit()
                before = [(await db.get(Task, t)).model_dump() for t in ids]
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="p3-after-confirm",
                        content="Tóm tắt việc đã xác nhận; chỉ đọc",
                        expected_generation=conv.generation,
                    ),
                )
                assert view["runs"][-1]["state"] == "completed"
                assert len(view["receipts"]) == 1 and not [
                    c for c in view["change_sets"] if c["state"] == "pending"
                ]
                await db.commit()
            async with maker() as db:
                assert [(await db.get(Task, t)).model_dump() for t in ids] == before
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == change_id)
                    )
                    == 1
                )
                conv = await db.get(MimiConversation, cid)
                run = MimiRun(
                    conversation_id=cid,
                    generation=conv.generation,
                    state="building",
                    execution_lease={},
                    source_versions={},
                    deadline=service.datetime.now(service.UTC) + service.timedelta(minutes=5),
                )
                db.add(run)
                await db.flush()
                settings = service.bind_configuration(
                    get_settings(),
                    {"profile_id": "deepseek", "effort": "high", "input_tokens": 272000},
                )
                await observed_trigger(db, conv, run.id, settings)
                history = WorkingHistory()
                _, _, checkpoint, _ = await service._prepare_context_history(
                    db,
                    conv,
                    crypto.unwrap_dek(conv.dek_wrapped),
                    run.id,
                    conv.next_message_sequence,
                    None,
                    None,
                    settings=settings,
                    working_history=history,
                )
                assert "receipt" in checkpoint["summary"] and "Confirm" in checkpoint["summary"]
                await db.commit()
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


async def observed_trigger(db, conversation, current_id, settings):
    from app.agent.models import MimiRun
    from app.agent.observations import context_revision

    previous = (
        await db.execute(
            select(MimiRun)
            .where(MimiRun.conversation_id == conversation.id, MimiRun.id != current_id)
            .order_by(MimiRun.generation.desc())
            .limit(1)
        )
    ).scalar_one()
    existing = (
        (await db.execute(select(MimiProviderCall).where(MimiProviderCall.run_id == previous.id)))
        .scalars()
        .all()
    )
    db.add(
        MimiProviderCall(
            run_id=previous.id,
            attempt=max((c.attempt for c in existing), default=0) + 1,
            state="succeeded",
            request_fingerprint="c" * 64,
            usage={"prompt_tokens": settings.mimi_compaction_trigger_tokens + 1},
            result={},
            route={
                "kind": "openrouter",
                "purpose": "main",
                "mode": "native",
                "model": settings.mimi_route_model,
                "actual_model": settings.mimi_route_model,
                "actual_provider": "Synthetic",
                "context_revision": context_revision(
                    settings, conversation.route_config_version, None
                ),
                "input_projection": {
                    "version": 1,
                    "request_fingerprint": "c" * 64,
                    "projection_fingerprint": "d" * 64,
                    "checkpoint_id": None,
                    "message_frontier": 0,
                    "model": settings.mimi_route_model,
                },
            },
        )
    )
    await db.commit()


@pytest.mark.usefixtures("local_sync_contract")
@pytest.mark.parametrize("fault", ["oversize", "interrupted"])
def test_unavailable_projection_keeps_canonical_answer_and_never_replays_effects(
    pg_dsn, monkeypatch, fault
):
    from app.agent import working_context
    from app.agent.context import Blocked

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        cid = None
        calls = []
        reads = []
        original = service.execute_read_tool

        async def read(*args, **kwargs):
            reads.append(1)
            return await original(*args, **kwargs)

        monkeypatch.setattr(service, "execute_read_tool", read)

        async def provider(messages, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="partial-read",
                            name="task.query.v1",
                            arguments={
                                "filter": {"title_contains": "synthetic-p3-missing-" + str(cid)}
                            },
                        ),
                    )
                )
            elif len(calls) == 2:
                if fault == "oversize":

                    def refused(*args, **kwargs):
                        raise ValueError("working_projection_oversize")

                    monkeypatch.setattr(working_context, "projection_body", refused)
                    outcome = AssistantText(
                        text="Đã đọc phần có sẵn; câu trả lời canonical vẫn đúng."
                    )
                else:
                    outcome = Blocked(reason="Dừng với lịch sử chưa hoàn tất, không ghi thay đổi.")
            else:
                assert not [m for m in messages if m["role"] == "tool"]
                assert any(
                    "canonical vẫn đúng" in (m.get("content") or "")
                    or "lịch sử chưa hoàn tất" in (m.get("content") or "")
                    for m in messages
                )
                outcome = AssistantText(text="Lịch sử công cụ thiếu; chưa có thao tác mới.")
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-gap-{len(calls)}",
                usage={"cost": 0},
                model=kwargs["settings"].mimi_route_model,
                provider="Synthetic",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                cid = (await service.create_conversation(db, auth(), service.ConversationCreate()))[
                    "id"
                ]
                await db.commit()
            for turn in (1, 2):
                async with maker() as db:
                    view = await service.send_message(
                        db,
                        auth(),
                        cid,
                        service.MessageCreate(
                            client_id=f"gap-{turn}",
                            content="Tiếp tục phần có sẵn",
                            expected_generation=turn,
                        ),
                    )
                    if turn == 1:
                        assert not [e for e in view["events"] if e["kind"] == KIND]
                        assert view["runs"][-1]["state"] == (
                            "completed" if fault == "oversize" else "halted"
                        )
                    else:
                        manifest = [
                            e["payload"] for e in view["events"] if e["kind"] == "context.manifest"
                        ][-1]
                        assert manifest["working_history"]["coverage"] == "partial"
                        assert view["runs"][-1]["state"] == "completed"
                    assert not view["change_sets"] and not view["receipts"]
                    await db.commit()
            assert len(reads) == 1 and len(calls) == 3
        finally:
            if cid:
                await cleanup(maker, cid, [])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.usefixtures("local_sync_contract")
def test_historical_selection_is_visible_but_cannot_authorize_new_preview(pg_dsn, monkeypatch):
    from app.agent.context import PreviewCandidate

    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        cid = None
        ids = []
        calls = []
        frozen = None

        async def provider(messages, **kwargs):
            nonlocal frozen
            calls.append(messages)
            if len(calls) == 1:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="fresh-read",
                            name="task.inspect_batch.v1",
                            arguments={"ids": [str(ids[0])], "projection": ["title", "priority"]},
                        ),
                    )
                )
            elif len(calls) == 2:
                outcome = ToolRequests(
                    requests=(
                        ToolRequest(
                            call_id="old-selection",
                            name="task.freeze_selection.v1",
                            arguments={
                                "intent": "Task được chỉ tên",
                                "variants_considered": ["exact ID"],
                                "explicitly_named_subset": True,
                                "members": [
                                    {
                                        "id": str(ids[0]),
                                        "classification": "included",
                                        "reason": "Phạm vi synthetic",
                                    }
                                ],
                            },
                        ),
                    )
                )
            elif len(calls) == 3:
                frozen = json.loads(messages[-1]["content"])["selection"]
                outcome = AssistantText(
                    text="Đã đọc và chốt phạm vi lịch sử; chưa tạo preview hay ghi."
                )
            else:
                assert len([m for m in messages if m["role"] == "tool"]) == 2
                outcome = PreviewCandidate(
                    tool="task.collection_candidate.v1",
                    arguments={
                        "selection_id": frozen["selection_id"],
                        "entries": [
                            {
                                "action": "edit",
                                "id": str(ids[0]),
                                "expected_collection_version": frozen["members"][0][
                                    "collection_version"
                                ],
                                "fields": {"priority": "p1"},
                            }
                        ],
                    },
                )
            return AgentCompletion(
                outcome=outcome,
                response_id=f"synthetic-stale-{len(calls)}",
                usage={"cost": 0},
                model=kwargs["settings"].mimi_route_model,
                provider="Synthetic",
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                task = Task(title="Synthetic historical authority")
                db.add(task)
                await db.flush()
                ids = [task.id]
                cid = (await service.create_conversation(db, auth(), service.ConversationCreate()))[
                    "id"
                ]
                await db.commit()
                await db.refresh(task)
                before = task.model_dump()
            for turn in (1, 2):
                async with maker() as db:
                    view = await service.send_message(
                        db,
                        auth(),
                        cid,
                        service.MessageCreate(
                            client_id=f"stale-{turn}",
                            content="Giữ phạm vi cũ",
                            expected_generation=turn,
                        ),
                    )
                    await db.commit()
            assert view["runs"][-1]["state"] == "halted"
            assert (
                view["runs"][-1]["error_code"]
                == "provider_contract_provider_revision_requires_current_run_selection"
            )
            assert not view["change_sets"] and not view["receipts"]
            async with maker() as db:
                assert (await db.get(Task, ids[0])).model_dump() == before
        finally:
            if cid:
                await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
