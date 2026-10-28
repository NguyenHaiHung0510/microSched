"""Assigned disposable-PG journeys; provider doubles only, never live calls."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup
from test_mimi_p3_working_pg import observed_trigger
from test_mimi_sync_failure_pg import local_sync_contract  # noqa: F401

from app.agent import crypto, service
from app.agent.context import AssistantText, PreviewCandidate
from app.agent.models import MimiConversation, MimiMessage, MimiRun
from app.agent.openrouter import AgentCompletion
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.agent.working_context import WorkingHistory, load_history, working_refs_current
from app.core.database_urls import async_postgres_url
from app.core.qa_event_loop import selector_loop_factory
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.mark.usefixtures("local_sync_contract")
def test_two_create_undo_cycles_keep_four_receipts_through_reload_compaction_and_privacy(
    pg_dsn,
    monkeypatch,
):
    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, ids, cid = auth(), [], None
        stage, helper_calls, main_calls = "create", [], []
        expected_receipts = []

        async def provider(messages, **kwargs):
            if kwargs.get("summary_mode"):
                helper_calls.append(messages)
                request = json.loads(messages[-1]["content"])
                outcomes = [
                    s["working_history"]["finalized_outcome"]
                    for s in request["sources"]
                    if s.get("working_history") and s["working_history"]["finalized_outcome"]
                ]
                assert {o["receipt_id"] for o in outcomes} == set(expected_receipts)
                text = json.dumps(
                    {
                        "summary": "Hai lần tạo, hai lần hoàn tác; bốn receipt lịch sử.",
                        "constraints": [],
                        "supersessions": [],
                        "resolutions": [],
                    }
                )
                outcome = AssistantText(text=text)
            elif stage == "create":
                outcome = PreviewCandidate(
                    tool=COLLECTION_CANDIDATE_TOOL,
                    arguments={
                        "selection_id": None,
                        "entries": [
                            {
                                "action": "create",
                                "fields": {
                                    "title": f"Synthetic civil {i}",
                                    "body_md": "deleted-read-marker",
                                    "due_precision": "date",
                                    "due_on": f"2027-01-{i:02}",
                                    "due_at": None,
                                },
                            }
                            for i in range(1, 8)
                        ],
                    },
                )
            else:
                main_calls.append(messages)
                authority = next(
                    json.loads(m["content"])
                    for m in messages
                    if m["role"] == "system" and "authority_envelope" in m["content"]
                )
                scalar = authority["pending_state"]["preview_lifecycle"]["historical_outcomes"]
                assert [o["receipt_id"] for o in scalar] == expected_receipts
                outcomes = [
                    json.loads(m["content"].split("\n", 1)[1])
                    for m in messages
                    if (m.get("content") or "").startswith("SERVER-PROVIDED HISTORICAL OUTCOME")
                ]
                if stage == "history":
                    assert [o["receipt_id"] for o in outcomes] == expected_receipts
                    assert [o["changes"][0]["action"] for o in outcomes] == [
                        "create",
                        "soft_delete",
                        "create",
                        "soft_delete",
                    ]
                    assert all(o["count"] == 7 for o in outcomes)
                assert "deleted-read-marker" not in json.dumps(messages)
                outcome = AssistantText(
                    text="Đã tạo rồi hoàn tác hai lần; hiện không có Task active."
                )
            return AgentCompletion(outcome, "synthetic-night", {"cost": 0}, "Synthetic", None)

        monkeypatch.setattr(service, "openrouter_complete", provider)

        async def send(content, client_id):
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                result = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id=client_id,
                        content=content,
                        expected_generation=conv.generation,
                    ),
                )
                await db.commit()
                return result

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
                expected_receipts.append(str(receipt["id"]))
                return receipt

        try:
            async with maker() as db:
                view = await service.create_conversation(db, actor, service.ConversationCreate())
                cid = view["id"]
                await db.commit()
            for cycle in range(2):
                view = await send("Tạo bảy việc theo bảy ngày đã chỉ định.", f"create-{cycle}")
                change = next(c for c in view["change_sets"] if c["state"] == "pending")
                receipt = await confirm(change, f"night-create-{cycle}")
                created = [UUID(i) for i in receipt["result"]["task_ids"]]
                ids.extend(created)
                async with maker() as db:
                    tasks = [(await db.get(Task, identity)) for identity in created]
                    assert [t.due_on.isoformat() for t in tasks] == [
                        f"2027-01-{i:02}" for i in range(1, 8)
                    ]
                    inverse = await service.prepare_receipt_undo(
                        db, actor, UUID(str(receipt["id"]))
                    )
                    await db.commit()
                undo = next(c for c in inverse["change_sets"] if c["state"] == "pending")
                await confirm(undo, f"night-undo-{cycle}")
            stage = "history"
            view = await send("Tóm tắt những lần đã áp dụng và hoàn tác.", "history")
            assert len(view["receipts"]) == 4
            async with maker() as db:
                tasks = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                assert len(tasks) == 14 and all(t.deleted_at is not None for t in tasks)
                before = [t.model_dump() for t in tasks]
                conv = await db.get(MimiConversation, cid)
                dek = crypto.unwrap_dek(conv.dek_wrapped)
                rows = (
                    await db.scalars(
                        select(MimiMessage)
                        .where(MimiMessage.conversation_id == cid)
                        .order_by(MimiMessage.sequence)
                    )
                ).all()
                settings = get_settings()
                history = await load_history(db, conv, dek, rows, settings)
                refs = [r for seq, r in history.refs.items() if seq in history.outcomes]
                assert len(history.outcomes) == len(refs) == 4
                assert await working_refs_current(db, cid, refs, dek, settings)
                run = MimiRun(
                    conversation_id=cid,
                    generation=conv.generation,
                    state="building",
                    execution_lease={},
                    source_versions={},
                    deadline=datetime.now(UTC) + timedelta(minutes=5),
                )
                conv.generation += 1  # reserve the synthetic helper driver's generation
                db.add(run)
                await db.flush()
                await observed_trigger(db, conv, run.id, settings)
                _, _, checkpoint, _ = await service._prepare_context_history(
                    db,
                    conv,
                    dek,
                    run.id,
                    conv.next_message_sequence,
                    None,
                    None,
                    settings=settings,
                    working_history=WorkingHistory(),
                )
                assert helper_calls and checkpoint["working_sources"]
                assert await working_refs_current(
                    db, cid, checkpoint["working_sources"], dek, settings
                )
                run.state = "completed"  # synthetic compaction driver is no longer active
                run.completed_at = datetime.now(UTC)
                await db.commit()
                stage = "compacted"
            view = await send("Tóm tắt lại lịch sử, không thực hiện gì.", "after-compaction")
            assert len(view["receipts"]) == 4 and len(main_calls) == 2
            async with maker() as db:
                tasks = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                assert [t.model_dump() for t in tasks] == before
                # Current privacy still withholds both scalar refs involving this Task.
                tasks[0].is_private = True
                tasks[0].title = "enc:v1:synthetic"
                tasks[0].body_md = None
                await db.flush()
                assert not await working_refs_current(db, cid, refs, dek, settings)
                await db.rollback()
                assert await working_refs_current(db, cid, refs, dek, settings)
                tampered = [{**refs[0], "sha256": "0" * 64}]
                assert not await working_refs_current(db, cid, tampered, dek, settings)
        finally:
            if cid:
                await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)


@pytest.mark.parametrize("bound_revision", [True, False])
@pytest.mark.usefixtures("local_sync_contract")
def test_preview_lifecycle_no_hidden_candidate_or_predecessor_resurrection(
    pg_dsn,
    monkeypatch,
    bound_revision,
):
    from test_mimi_collection_service_pg import prepare

    from app.agent.models import MimiChangeSet

    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_ROUTE_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    get_settings.cache_clear()

    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "get_sessionmaker", lambda: maker)
        actor, cid, _, ids, old_id, decision = await prepare(maker, 7)
        calls = []

        async def provider(messages, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                outcome = PreviewCandidate(
                    tool=COLLECTION_CANDIDATE_TOOL,
                    arguments={
                        "entries": [
                            {"action": "create", "fields": {"title": f"Synthetic B{i}"}}
                            for i in range(2)
                        ],
                    },
                )
            else:
                authority = next(
                    json.loads(m["content"])
                    for m in messages
                    if m["role"] == "system" and "authority_envelope" in m["content"]
                )
                pending = authority["pending_state"]
                assert pending["preview"] is None
                lifecycle = {p["id"]: p for p in pending["preview_lifecycle"]["previews"]}
                old = lifecycle[str(old_id)]
                if bound_revision:
                    assert old["state"] == "stale"
                    assert old["reason"] == "superseded_by_validated_preview"
                    assert lifecycle[str(rejected_id)]["state"] == "rejected"
                    assert old["successor_id"] is None
                else:
                    assert old["state"] == "rejected" and len(lifecycle) == 1
                outcome = AssistantText(text="Không còn preview chờ xác nhận; chưa ghi Task.")
            return AgentCompletion(outcome, "synthetic-preview", {"cost": 0}, "Synthetic", None)

        monkeypatch.setattr(service, "openrouter_complete", provider)
        try:
            async with maker() as db:
                before = [(await db.get(Task, identity)).model_dump() for identity in ids]
                old = await db.get(MimiChangeSet, old_id)
                binding = (old.digest_sha256, old.nonce, old.expires_at, old.operation_ciphertext)
                conv = await db.get(MimiConversation, cid)
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="replace-preview",
                        content="Chuẩn bị phương án mới để xem lại.",
                        expected_generation=conv.generation,
                        **(
                            {
                                "intent": "revise_pending_preview",
                                "expected_change_set_id": old_id,
                                "expected_change_set_digest": decision.digest,
                            }
                            if bound_revision
                            else {}
                        ),
                    ),
                )
                await db.commit()
                pending = [c for c in view["change_sets"] if c["state"] == "pending"]
                assert len(pending) == 1
                rejected = pending[0]
                rejected_id = UUID(str(rejected["id"]))
                if not bound_revision:
                    assert rejected_id == old_id and len(view["change_sets"]) == 1
                    await db.refresh(old)
                    assert (
                        old.digest_sha256,
                        old.nonce,
                        old.expires_at,
                        old.operation_ciphertext,
                    ) == binding
                    assert view["runs"][-1]["error_code"] == "pending_preview_requires_decision"
                else:
                    assert rejected_id != old_id and len(view["change_sets"]) == 2
            async with maker() as db:
                await service.confirm_change_set(
                    db,
                    actor,
                    rejected_id,
                    service.ConfirmationDecision(
                        digest=rejected["digest"], nonce=rejected["nonce"], decision="reject"
                    ),
                    "reject-replacement",
                )
                await db.commit()
            assert len(calls) == 1  # reject/reload does not dispatch a model
            async with maker() as db:
                conv = await db.get(MimiConversation, cid)
                view = await service.send_message(
                    db,
                    actor,
                    cid,
                    service.MessageCreate(
                        client_id="after-rejection",
                        content="Trạng thái các phương án hiện tại?",
                        expected_generation=conv.generation,
                    ),
                )
                await db.commit()
                assert not [c for c in view["change_sets"] if c["state"] == "pending"]
                assert view["receipts"] == []
                assert [(await db.get(Task, identity)).model_dump() for identity in ids] == before
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario(), loop_factory=selector_loop_factory)
