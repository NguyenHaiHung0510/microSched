"""Synthetic real-DB collection transaction/receipt/undo/evidence contracts."""

import asyncio
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid7

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import crypto, service
from app.agent import task_collection as collection
from app.agent.contracts import ChangeOperation, FrozenChangeSet
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiEvidence,
    MimiExecutionReceipt,
    MimiNotificationIntent,
    MimiRefreshMarker,
    MimiRun,
)
from app.core import crypto as master_crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def local_contract(monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "synthetic086-state")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("MIMI_REAL_CHAT_ENABLED", "1")
    monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "1")
    monkeypatch.setenv("MIMI_NOTIFICATIONS_ENABLED", "1")
    get_settings.cache_clear()
    master_crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    master_crypto._cipher.cache_clear()


def auth():
    return AuthSession(
        user_email="owner@example.test",
        token_hash="synthetic086",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


async def prepare(maker, count=2):
    actor = auth()
    async with maker() as db:
        view = await service.create_conversation(db, actor, service.ConversationCreate())
        cid = view["id"]
        conv = await db.get(MimiConversation, cid)
        tasks = [
            Task(title=f"Synthetic receipt{i}", body_md="Không mất nội dung") for i in range(count)
        ]
        db.add_all(tasks)
        await db.flush()
        ids = [t.id for t in tasks]
        versions = {t.id: t.collection_version for t in tasks}
        plan = await collection.freeze_collection(
            db,
            collection.CollectionCandidate(
                selection_id=uuid7(),
                entries=tuple(
                    collection.TaskCommand(
                        action="edit",
                        id=t.id,
                        expected_collection_version=t.collection_version,
                        fields={"priority": "p1"},
                    )
                    for t in tasks
                ),
            ),
            covered_versions=versions,
        )
        rid = uuid7()
        now = datetime.now(UTC)
        run = MimiRun(
            id=rid,
            conversation_id=cid,
            generation=conv.generation,
            state="waiting_confirmation",
            deadline=now + timedelta(minutes=15),
            execution_lease={"capabilities": [collection.COLLECTION_TOOL]},
            source_versions={},
        )
        conv.generation += 1
        db.add(run)
        await db.flush()
        change_id, nonce = uuid7(), uuid7()
        operation = ChangeOperation(
            operation_id=uuid7(),
            tool=collection.COLLECTION_TOOL,
            args=plan.model_dump(mode="json"),
            reversible=True,
        )
        frozen = FrozenChangeSet(
            change_set_id=change_id,
            run_id=rid,
            operations=(operation,),
            expires_at=run.deadline,
            nonce=nonce,
            digest_sha256="0" * 64,
            idempotency_key=f"preview:{change_id}",
        )
        dek = crypto.unwrap_dek(conv.dek_wrapped)
        change = MimiChangeSet(
            id=change_id,
            run_id=rid,
            state="pending",
            nonce=nonce,
            expires_at=run.deadline,
            digest_sha256=frozen.calculated_digest(),
            policy_version="synthetic086",
            operation_ciphertext=crypto.seal_content(
                dek,
                collection.canonical(operation.model_dump(mode="json")),
                aad=crypto.change_set_aad(cid, change_id),
            ),
        )
        db.add(change)
        await service._add_assistant_message(
            db,
            conv,
            rid,
            dek,
            "Chuẩn bị đổi độ ưu tiên. Chưa áp dụng.",
            producer_code="preview_prepared",
        )
        await service._append_event(db, rid, "change_set.ready", {"change_set_id": str(change_id)})
        await db.commit()
        decision = service.ConfirmationDecision(
            digest=change.digest_sha256, nonce=nonce, decision="confirm"
        )
    return actor, cid, rid, ids, change_id, decision


async def cleanup(maker, cid, ids):
    async with maker() as db:
        await db.execute(delete(MimiConversation).where(MimiConversation.id == cid))
        await db.execute(delete(Task).where(Task.id.in_(ids)))
        await db.commit()


def test_fault_after_domain_write_cannot_commit_partial_state(pg_dsn, monkeypatch):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, change_id, decision = await prepare(maker)

        async def injected_failure(db, _actor, _plan):
            row = await db.get(Task, ids[0])
            row.priority = "p1"
            await db.flush()
            raise ValueError("synthetic_fault_after_first_domain_write")

        monkeypatch.setattr(service, "execute_collection", injected_failure)
        try:
            async with maker() as db:
                with pytest.raises((HTTPException, ValueError)):
                    await service.confirm_change_set(
                        db, actor, change_id, decision, "synthetic-fault"
                    )
                await db.rollback()
            async with maker() as db:
                rows = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                assert all(t.priority is None for t in rows), (
                    "fault after first write committed a partial collection"
                )
                assert (await db.get(MimiChangeSet, change_id)).state == "pending"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == change_id)
                    )
                    == 0
                )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_confirm_receipt_idempotency_unknown_recovery_and_versioned_undo(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, change_id, decision = await prepare(maker)
        try:
            async with maker() as db:
                result = await service.confirm_change_set(
                    db, actor, change_id, decision, "synthetic086-once"
                )
                await db.commit()  # response deliberately discarded: recovery reuses receipt
            async with maker() as db:
                replay = await service.confirm_change_set(
                    db, actor, change_id, decision, "synthetic086-once"
                )
                assert replay == result
                receipt = (
                    await db.scalars(
                        select(MimiExecutionReceipt).where(
                            MimiExecutionReceipt.change_set_id == change_id
                        )
                    )
                ).one()
                assert receipt.result["count"] == 2 and set(receipt.result["task_ids"]) == {
                    str(t) for t in ids
                }
                assert "Không mất nội dung" not in json.dumps(receipt.result, ensure_ascii=False)
                assert receipt.result_ciphertext.startswith("mimi:v1:")
                receipt_id = receipt.id
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiRefreshMarker)
                        .where(MimiRefreshMarker.receipt_id == receipt_id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiNotificationIntent)
                        .where(
                            MimiNotificationIntent.run_id == rid,
                            MimiNotificationIntent.kind == "completed",
                        )
                    )
                    == 1
                )
                await db.commit()
            async with maker() as db:
                inverse = await service.prepare_receipt_undo(db, actor, receipt_id)
                await db.commit()
                change = inverse["change_sets"][-1]
                undo_id = UUID(str(change["id"]))
                undo_decision = service.ConfirmationDecision(
                    digest=change["digest"], nonce=change["nonce"], decision="confirm"
                )
            async with maker() as db:
                undo = await service.confirm_change_set(
                    db, actor, undo_id, undo_decision, "synthetic086-undo"
                )
                await db.commit()
                assert undo["result"]["count"] == 2
                assert all(
                    t.priority is None and t.body_md == "Không mất nội dung"
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_feedback_causal_bundle_owner_scope_and_replay(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, change_id, decision = await prepare(maker)
        try:
            payload = service.FeedbackCreate(
                client_id="synthetic086-feedback",
                target_type="run",
                target_id=str(rid),
                comment="Thay đổi đúng phương án.",
                expected="Hai Task đã đổi ưu tiên.",
            )
            async with maker() as db:
                await service.confirm_change_set(
                    db, actor, change_id, decision, "synthetic086-feedback-confirm"
                )
                first = await service.save_feedback(db, actor, cid, payload)
                await db.commit()
            async with maker() as db:
                replay = await service.save_feedback(db, actor, cid, payload)
                assert (
                    replay["id"] == first["id"]
                    and replay["evidence_bundle_ids"] == first["evidence_bundle_ids"]
                )
                conv = await db.get(MimiConversation, cid)
                from app.agent.evidence import capture_feedback, read_evidence

                evidence = await read_evidence(db, conv, UUID(first["evidence_bundle_ids"][0]))
                assert evidence["content"]["receipts"][0]["result"]["count"] == 2
                assert evidence["content"]["messages"]
                row = await db.get(MimiEvidence, UUID(first["evidence_bundle_ids"][0]))
                assert "Thay đổi đúng" not in json.dumps(row.metadata_json, ensure_ascii=False)
                foreign = MimiConversation(
                    owner_id=uuid4(),
                    sensitivity="standard",
                    dek_wrapped=crypto.create_wrapped_dek(),
                )
                db.add(foreign)
                await db.flush()
                with pytest.raises(HTTPException, match="Feedback target not found"):
                    await capture_feedback(db, foreign, "run", str(rid), [])
                await db.rollback()
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
