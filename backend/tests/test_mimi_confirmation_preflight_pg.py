"""Fresh GET can race; POST frontier still refuses atomically and retains frozen bytes."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_collection_service_pg import cleanup, local_contract, prepare  # noqa: F401

from app.agent import service
from app.agent.models import MimiChangeSet, MimiConversation, MimiExecutionReceipt
from app.core.database_urls import async_postgres_url
from app.domain.models import Task

pytestmark = pytest.mark.pg


def test_preflight_get_is_readonly_and_racing_post_still_rejects_frontier(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        actor, cid, rid, ids, ch, decision = await prepare(maker)
        try:
            async with maker() as db:
                row = await db.get(MimiChangeSet, ch)
                original = (
                    row.state,
                    row.operation_ciphertext,
                    row.digest_sha256,
                    row.nonce,
                    row.expires_at,
                )
                for _ in range(2):
                    view = await service.conversation_view(db, actor, cid)
                    shown = next(c for c in view["change_sets"] if c["id"] == ch)
                    assert shown["confirmation_preflight"] == {"status": "eligible", "reason": None}
                    assert (
                        row.state,
                        row.operation_ciphertext,
                        row.digest_sha256,
                        row.nonce,
                        row.expires_at,
                    ) == original
            async with maker() as db:
                (await db.get(MimiConversation, cid)).generation += 1
                await db.commit()
            async with maker() as db:
                with pytest.raises(HTTPException) as refused:
                    await service.confirm_change_set(
                        db, actor, ch, decision, "item2-race-" + str(cid)
                    )
                assert (
                    refused.value.status_code == 409
                    and refused.value.detail == "change_set_frontier_stale"
                )
                await db.rollback()
            async with maker() as db:
                row = await db.get(MimiChangeSet, ch)
                assert row.state == "stale"
                assert (
                    row.operation_ciphertext,
                    row.digest_sha256,
                    row.nonce,
                    row.expires_at,
                ) == original[1:]
                view = await service.conversation_view(db, actor, cid)
                assert next(c for c in view["change_sets"] if c["id"] == ch)[
                    "confirmation_preflight"
                ] == {"status": "blocked", "reason": "change_set_stale"}
                assert all(
                    t.priority is None and t.collection_version == 1
                    for t in await db.scalars(select(Task).where(Task.id.in_(ids)))
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(MimiExecutionReceipt)
                        .where(MimiExecutionReceipt.change_set_id == ch)
                    )
                    == 0
                )
        finally:
            await cleanup(maker, cid, ids)
            await engine.dispose()

    asyncio.run(scenario())
