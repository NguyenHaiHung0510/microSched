"""Real-PG collection confirmation adversaries and concurrent receipt namespace."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import auth, cleanup, local_contract, prepare  # noqa: F401

from app.agent import service
from app.agent.models import (
    MimiChangeSet,
    MimiConversation,
    MimiExecutionReceipt,
    MimiNotificationIntent,
    MimiRun,
)
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.mark.parametrize(
    "boundary", ["nonce", "digest", "expiry", "frontier", "owner", "lease", "privacy", "disabled"]
)
def test_confirmation_binding_adversaries_write_zero(pg_dsn, monkeypatch, boundary):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        try:
            if boundary == "owner":
                actor = auth().model_copy(update={"user_email": "other@example.test"})
            elif boundary == "nonce":
                decision = decision.model_copy(update={"nonce": uuid4()})
            elif boundary == "digest":
                decision = decision.model_copy(update={"digest": "f" * 64})
            elif boundary == "disabled":
                monkeypatch.setenv("MIMI_COLLECTION_ENABLED", "0")
                get_settings.cache_clear()
            else:
                async with maker() as db:
                    if boundary == "expiry":
                        (await db.get(MimiChangeSet, ch)).expires_at = datetime.now(
                            UTC
                        ) - timedelta(seconds=1)
                    elif boundary == "frontier":
                        (await db.get(MimiConversation, cid)).generation += 1
                    elif boundary == "lease":
                        (await db.get(MimiRun, rid)).execution_lease = {"capabilities": []}
                    elif boundary == "privacy":
                        conv = await db.get(MimiConversation, cid)
                        conv.sensitivity = "private"
                        conv.is_private = True
                    await db.commit()
            async with maker() as db:
                with pytest.raises(HTTPException):
                    await service.confirm_change_set(
                        db, actor, ch, decision, f"negative-{boundary}"
                    )
                await db.rollback()
            async with maker() as db:
                assert all(
                    t.priority is None
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == ch)
                    )
                    == 0
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
                    == 0
                )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("count", [50, 100, 200])
def test_one_collection_preview_confirmation_receipt_exact_complete_set(pg_dsn, count):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker, count)
        try:
            async with maker() as db:
                before = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                assert len(before) == count and all(t.priority is None for t in before)
                first = await service.confirm_change_set(
                    db, actor, ch, decision, f"bulk-service-{count}"
                )
                await db.commit()
                assert first["result"]["count"] == count and first["result"]["task_ids"] == [
                    str(i) for i in ids
                ]
            async with maker() as db:
                replay = await service.confirm_change_set(
                    db, actor, ch, decision, f"bulk-service-{count}"
                )
                assert replay == first
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == ch)
                    )
                    == 1
                )
                assert all(
                    t.priority == "p1" and t.body_md == "Không mất nội dung"
                    for t in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                )
                with pytest.raises(HTTPException):
                    await service.confirm_change_set(
                        db,
                        actor,
                        ch,
                        decision.model_copy(update={"digest": "e" * 64}),
                        f"bulk-service-{count}",
                    )
                with pytest.raises(HTTPException):
                    await service.confirm_change_set(
                        db,
                        auth().model_copy(update={"user_email": "foreign@example.test"}),
                        ch,
                        decision,
                        f"bulk-service-{count}",
                    )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_confirm_same_key_returns_exact_one_receipt(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        try:

            async def confirm():
                async with maker() as db:
                    result = await service.confirm_change_set(
                        db, actor, ch, decision, "concurrent-confirm086"
                    )
                    await db.commit()
                    return result

            results = await asyncio.gather(confirm(), confirm())
            assert results[0] == results[1]
            async with maker() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == ch)
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
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
