"""Synthetic PG source/egress controls and helper-I/O barriers; no paid transport."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup
from test_mimi_p3_working_pg import observed_trigger as _observed_trigger
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import service
from app.agent.context import AssistantText, PreviewCandidate, ToolRequest, ToolRequests
from app.agent.models import MimiConversation, MimiEvent, MimiProviderCall, MimiRun
from app.agent.openrouter import AgentCompletion
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task, TaskItem

pytestmark = [pytest.mark.pg, pytest.mark.usefixtures("local_sync_contract")]
BODY, CHILD, REASON = (
    "egress-body-marker",
    "egress-checklist-marker",
    "egress-selection-reason-marker",
)


def configure(monkeypatch):
    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    get_settings.cache_clear()


async def trigger_compaction(db, conv):
    from app.agent.route_config import bind_configuration, default_configuration

    base = get_settings()
    settings = bind_configuration(base, conv.route_config or default_configuration(base))
    await _observed_trigger(db, conv, uuid4(), settings)


def completion(outcome):
    return AgentCompletion(outcome, "synthetic-egress", {"cost": 0}, "Synthetic", None)


async def seed(maker):
    actor = auth()
    async with maker() as db:
        task = Task(title=f"Synthetic {uuid4().hex}", body_md=BODY)
        db.add(task)
        await db.flush()
        item = TaskItem(task_id=task.id, content=CHILD, position=0)
        db.add(item)
        cid = (await service.create_conversation(db, actor, service.ConversationCreate()))["id"]
        await db.commit()
    return actor, cid, task.id, item.id


async def mutate(maker, tid, child_id, change):
    async with maker() as db:
        task = await db.get(Task, tid)
        if change == "private":
            (await db.get(TaskItem, child_id)).content = "enc:v1:synthetic"
            await db.flush()
            task.title, task.body_md, task.is_private = "enc:v1:synthetic", None, True
        else:
            task.deleted_at = datetime.now(UTC)
        await db.commit()


async def send(maker, actor, cid, client):
    async with maker() as db:
        conv = await db.get(MimiConversation, cid)
        result = await service.send_message(
            db,
            actor,
            cid,
            service.MessageCreate(
                client_id=client,
                content="Xem thông tin đã chọn, giữ nguyên dữ liệu.",
                expected_generation=conv.generation,
            ),
        )
        await db.commit()
        return result


def read(tid, identity="content"):
    return ToolRequests(
        requests=(
            ToolRequest(
                call_id=identity,
                name="task.read_content.v1",
                arguments={"id": str(tid)},
            ),
        )
    )


def summary():
    return AssistantText(
        text=json.dumps(
            {
                "summary": "Đã đọc nguồn trong phạm vi; chưa áp dụng thay đổi.",
                "constraints": [],
                "supersessions": [],
                "resolutions": [],
            }
        )
    )


@pytest.mark.parametrize("change", ["private", "delete"])
def test_pending_and_selection_raw_content_redacted_in_main_and_helper(pg_dsn, monkeypatch, change):
    configure(monkeypatch)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, tid, child = await seed(maker)
        stage, positive, safe = "prepare", [], []

        async def provider(messages, **kwargs):
            wire = json.dumps(messages)
            if stage == "prepare":
                tools = [m for m in messages if m["role"] == "tool"]
                if not tools:
                    outcome = read(tid)
                elif len(tools) == 1:
                    assert BODY in wire and CHILD in wire
                    positive.append(True)
                    outcome = ToolRequests(
                        requests=(
                            ToolRequest(
                                call_id="selection",
                                name="task.freeze_selection.v1",
                                arguments={
                                    "intent": "Synthetic exact target",
                                    "variants_considered": ["Synthetic"],
                                    "explicitly_named_subset": True,
                                    "members": [
                                        {
                                            "id": str(tid),
                                            "classification": "included",
                                            "reason": REASON,
                                        }
                                    ],
                                },
                            ),
                        )
                    )
                else:
                    selection = json.loads(tools[-1]["content"])["selection"]
                    outcome = PreviewCandidate(
                        tool=COLLECTION_CANDIDATE_TOOL,
                        arguments={
                            "selection_id": selection["selection_id"],
                            "entries": [
                                {
                                    "action": "edit",
                                    "id": str(tid),
                                    "expected_collection_version": selection["members"][0][
                                        "collection_version"
                                    ],
                                    "fields": {"priority": "p1"},
                                }
                            ],
                        },
                    )
            else:
                assert all(marker not in wire for marker in (BODY, CHILD, REASON))
                safe.append("helper" if kwargs.get("summary_mode") else "main")
                if not kwargs.get("summary_mode"):
                    authority = next(
                        json.loads(m["content"])
                        for m in messages
                        if m["role"] == "system" and "authority_envelope" in m["content"]
                    )
                    assert authority["pending_state"]["preview_content_available"] is False
                outcome = (
                    summary()
                    if kwargs.get("summary_mode")
                    else AssistantText(text="Nguồn cũ đã bị giữ lại; preview chưa được áp dụng.")
                )
            return completion(outcome)

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            initial = await send(maker, actor, cid, "prepare")
            pending = next(c for c in initial["change_sets"] if c["state"] == "pending")
            assert positive
            await mutate(maker, tid, child, change)
            stage = "check"
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                await trigger_compaction(db, conv)
            result = await send(maker, actor, cid, "after-source-change")
            assert "main" in safe and "helper" in safe
            retained = next(c for c in result["change_sets"] if str(c["id"]) == str(pending["id"]))
            assert (retained["digest"], retained["nonce"]) == (pending["digest"], pending["nonce"])
            assert result["receipts"] == []
        finally:
            await cleanup(maker, cid, [tid])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.parametrize("change", ["private", "delete"])
def test_helper_return_rechecks_source_after_mid_io_flip(pg_dsn, monkeypatch, change):
    configure(monkeypatch)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, tid, child = await seed(maker)
        ready, release = asyncio.Event(), asyncio.Event()
        stage, main_after_barrier = "read", []

        async def provider(messages, **kwargs):
            if stage == "read":
                if messages[-1].get("role") != "tool":
                    return completion(read(tid))
                assert BODY in json.dumps(messages) and CHILD in json.dumps(messages)
                return completion(AssistantText(text="Đã đọc nội dung hợp lệ."))
            if kwargs.get("summary_mode"):
                # Positive control: helper's input was eligible BEFORE the flip.
                assert BODY in json.dumps(messages) and CHILD in json.dumps(messages)
                ready.set()
                await release.wait()
                return completion(
                    AssistantText(
                        text=json.dumps(
                            {
                                "summary": BODY + CHILD,
                                "constraints": [],
                                "supersessions": [],
                                "resolutions": [],
                            }
                        )
                    )
                )
            main_after_barrier.append(messages)
            return completion(AssistantText(text="Unexpected main dispatch"))

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            await send(maker, actor, cid, "permitted-read")
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                old_frontier = conv.context_frontier_sequence
                await trigger_compaction(db, conv)
            stage = "barrier"
            pending = asyncio.create_task(send(maker, actor, cid, "helper-barrier"))
            try:
                await asyncio.wait_for(ready.wait(), 10)
                await mutate(maker, tid, child, change)
            finally:
                release.set()
            with pytest.raises(HTTPException) as refused:
                await pending
            assert refused.value.status_code == 409
            assert refused.value.detail == "compaction_working_sources_changed_history_preserved"
            assert not main_after_barrier
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                assert conv.context_frontier_sequence == old_frontier
                latest = (
                    await db.scalars(
                        select(MimiRun)
                        .where(MimiRun.conversation_id == cid)
                        .order_by(MimiRun.generation.desc())
                    )
                ).first()
                assert latest.state == "halted"
                calls = (
                    await db.scalars(
                        select(MimiProviderCall).where(MimiProviderCall.run_id == latest.id)
                    )
                ).all()
                assert (
                    len(calls) == 1
                    and calls[0].state == "succeeded"
                    and calls[0].usage["cost"] == 0
                )
                activated = (
                    await db.scalars(
                        select(MimiEvent).where(
                            MimiEvent.run_id == latest.id,
                            MimiEvent.kind == "context.checkpoint.activated",
                        )
                    )
                ).all()
                assert not activated
        finally:
            await cleanup(maker, cid, [tid])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


def test_explicit_deleted_read_restore_and_compensating_undo_remain_usable(pg_dsn, monkeypatch):
    configure(monkeypatch)

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, tid, child = await seed(maker)
        stage, positive = "restore", []
        await mutate(maker, tid, child, "delete")

        async def provider(messages, **kwargs):
            tools = [m for m in messages if m["role"] == "tool"]
            if stage == "check":
                assert BODY in json.dumps(messages) and CHILD in json.dumps(messages)
                authority = next(
                    json.loads(m["content"])
                    for m in messages
                    if m["role"] == "system" and "authority_envelope" in m["content"]
                )
                assert authority["pending_state"]["preview_content_available"] is True
                positive.append("restore-preview")
                return completion(
                    AssistantText(text="Phương án khôi phục có thể xem; chưa Confirm.")
                )
            if not tools:
                return completion(
                    ToolRequests(
                        requests=(
                            ToolRequest(
                                call_id="deleted-content",
                                name="task.read_content.v1",
                                arguments={"id": str(tid), "include_deleted": True},
                            ),
                        )
                    )
                )
            assert BODY in json.dumps(messages) and CHILD in json.dumps(messages)
            positive.append("deleted-read")
            if len(tools) == 1:
                return completion(
                    ToolRequests(
                        requests=(
                            ToolRequest(
                                call_id="restore-selection",
                                name="task.freeze_selection.v1",
                                arguments={
                                    "intent": "Restore exact synthetic Task",
                                    "variants_considered": ["Synthetic"],
                                    "explicitly_named_subset": True,
                                    "members": [
                                        {
                                            "id": str(tid),
                                            "classification": "included",
                                            "reason": "Explicit restore",
                                        }
                                    ],
                                },
                            ),
                        )
                    )
                )
            selection = json.loads(tools[-1]["content"])["selection"]
            assert selection["members"][0]["deleted_read_authorized"] is True
            return completion(
                PreviewCandidate(
                    tool=COLLECTION_CANDIDATE_TOOL,
                    arguments={
                        "selection_id": selection["selection_id"],
                        "entries": [
                            {
                                "id": str(tid),
                                "action": "restore",
                                "expected_collection_version": selection["members"][0][
                                    "collection_version"
                                ],
                            }
                        ],
                    },
                )
            )

        monkeypatch.setattr(service, "openrouter_complete", provider)

        async def confirm(change, key):
            async with maker() as db:
                receipt = await service.confirm_change_set(
                    db,
                    actor,
                    UUID(str(change["id"])),
                    service.ConfirmationDecision(
                        digest=change["digest"], nonce=change["nonce"], decision="confirm"
                    ),
                    key,
                )
                await db.commit()
                return receipt

        try:
            view = await send(maker, actor, cid, "explicit-restore")
            restore = next(c for c in view["change_sets"] if c["state"] == "pending")
            receipt = await confirm(restore, "restore-once")
            async with maker() as db:
                task = await db.get(Task, tid)
                assert task.deleted_at is None and task.body_md == BODY
                assert (await db.get(TaskItem, child)).content == CHILD
                inverse = await service.prepare_receipt_undo(db, actor, UUID(str(receipt["id"])))
                await db.commit()
            inverse_change = next(c for c in inverse["change_sets"] if c["state"] == "pending")
            undo_receipt = await confirm(inverse_change, "undo-restoration")
            async with maker() as db:
                assert (await db.get(Task, tid)).deleted_at is not None
                next_inverse = await service.prepare_receipt_undo(
                    db, actor, UUID(str(undo_receipt["id"]))
                )
                await db.commit()
                assert any(c["state"] == "pending" for c in next_inverse["change_sets"])
            stage = "check"
            view = await send(maker, actor, cid, "inspect-restore-preview")
            assert len(view["receipts"]) == 2 and "restore-preview" in positive
        finally:
            await cleanup(maker, cid, [tid])
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
