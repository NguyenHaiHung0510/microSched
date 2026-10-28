"""Real-PG Task collection CAS, atomicity and recovery oracles; synthetic only."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import task_collection as collection
from app.core.database_urls import async_postgres_url
from app.domain.models import AuthSession, OneShotReminder, Task, TaskItem
from app.domain.one_shot import ReminderWrite, save_reminder
from app.domain.tasks import TaskItemCreate, TaskStore

pytestmark = pytest.mark.pg


def auth():
    return AuthSession(
        user_email="owner@example.test",
        token_hash="synthetic086",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def seed(maker, count):
    async with maker() as db:
        tasks = [
            Task(title=f"Synthetic collection{i}", body_md="Giữ nội dung", due_precision="none")
            for i in range(count)
        ]
        db.add_all(tasks)
        await db.flush()
        ids = [t.id for t in tasks]
        await db.commit()
    return ids


async def cleanup(maker, ids):
    async with maker() as db:
        await db.execute(delete(Task).where(Task.id.in_(ids)))
        await db.commit()


async def candidate(maker, ids, **overrides):
    async with maker() as db:
        rows = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
        versions = {r.id: r.collection_version for r in rows}
        entries = [
            collection.TaskCommand(
                id=tid,
                expected_collection_version=versions[tid],
                action="edit",
                fields={"priority": "p1"},
                **overrides,
            )
            for tid in ids
        ]
        proposal = collection.CollectionCandidate(selection_id=uuid4(), entries=tuple(entries))
        plan = await collection.freeze_collection(db, proposal, covered_versions=versions)
        await db.commit()
    return plan


@pytest.mark.parametrize("count", [50, 100, 200])
def test_bulk_exact_targets_and_rollback(pg_dsn, count):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, count)
        try:
            plan = await candidate(maker, ids)
            async with maker() as db:
                assert all(
                    r.priority is None
                    for r in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                ), "preview cannot mutate"
                recovery = await collection.execute_collection(db, auth(), plan)
                assert len(recovery["after"]) == count
                await db.rollback()
            async with maker() as db:
                assert all(
                    r.priority is None
                    for r in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                ), "outer rollback must undo whole batch"
                recovery = await collection.execute_collection(db, auth(), plan)
                await db.commit()
            async with maker() as db:
                rows = (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                assert len(rows) == count and all(
                    r.priority == "p1" and r.body_md == "Giữ nội dung" for r in rows
                )
                assert {r.id for r in rows} == set(ids)
                with pytest.raises(HTTPException, match="task_collection_source_stale"):
                    await collection.execute_collection(db, auth(), plan)
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_one_stale_member_gives_zero_writes(pg_dsn, monkeypatch):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 200)
        try:
            plan = await candidate(maker, ids)
            async with maker() as db:
                row = await db.get(Task, ids[1])
                row.title = "Concurrent unrelated edit"
                await db.commit()
            if os.environ.get("MIMI086_NEGATIVE_BYPASS_CAS") == "1":

                async def bypass(db, plan):
                    return await collection.locked_state(db, [e.id for e in plan.entries])

                monkeypatch.setattr(collection, "validate_prepared", bypass)
            async with maker() as db:
                with pytest.raises(HTTPException, match="task_collection_source_stale"):
                    await collection.execute_collection(db, auth(), plan)
                assert all(
                    r.priority is None
                    for r in (await db.scalars(select(Task).where(Task.id.in_(ids)))).all()
                ), "one stale means zero domain writes"
                await db.rollback()
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_checklist_recovery_and_raw_writer_version(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            async with maker() as db:
                task = await db.get(Task, tid)
                v = task.collection_version
                child = await TaskStore().add_item(
                    db, auth(), tid, TaskItemCreate(content="Recover me")
                )
                cid = child.id
                await db.commit()
                await db.refresh(task)
                assert task.collection_version > v
                v = task.collection_version
                await db.execute(
                    text("UPDATE microsched.task_item SET content='Raw change' WHERE id=:id"),
                    {"id": cid},
                )
                await db.commit()
                await db.refresh(task)
                assert task.collection_version > v, "raw child writes invalidate aggregate CAS"
            plan = await candidate(
                maker, ids, children=(collection.ChildCommand(action="remove", id=cid),)
            )
            async with maker() as db:
                await collection.execute_collection(db, auth(), plan)
                await db.commit()
                assert (await db.get(TaskItem, cid)).deleted_at is not None
                assert await TaskStore().list_items(db, auth(), tid) == []
                assert (await db.get(Task, tid)).body_md == "Giữ nội dung"
            plan = await candidate(
                maker, ids, children=(collection.ChildCommand(action="restore", id=cid),)
            )
            async with maker() as db:
                await collection.execute_collection(db, auth(), plan)
                await db.commit()
                items = await TaskStore().list_items(db, auth(), tid)
                assert len(items) == 1 and items[0].id == cid and items[0].content == "Raw change"
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["absolute", "relative"])
def test_reminder_effect_preview_and_atomic_source_trigger(pg_dsn, mode):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            future = datetime.now(UTC) + timedelta(days=4)
            async with maker() as db:
                task = await db.get(Task, tid)
                task.due_precision = "datetime"
                task.due_at = future
                await db.flush()
                await db.refresh(task)
                config = ReminderWrite(
                    mode=mode,
                    **(
                        {"due_at": future - timedelta(minutes=60)}
                        if mode == "absolute"
                        else {"offset_minutes": -60}
                    ),
                )
                reminder = await save_reminder(db, auth(), "task", tid, config)
                rid = reminder.id
                original_due = reminder.due_at
                await db.commit()
            async with maker() as db:
                task = await db.get(Task, tid)
                cmd = collection.TaskCommand(
                    action="edit",
                    id=tid,
                    expected_collection_version=task.collection_version,
                    fields={
                        "due_precision": "datetime",
                        "due_on": None,
                        "due_at": (future + timedelta(days=1)).isoformat(),
                    },
                )
                plan = await collection.freeze_collection(
                    db,
                    collection.CollectionCandidate(selection_id=uuid4(), entries=(cmd,)),
                    covered_versions={tid: task.collection_version},
                )
                assert plan.entries[0].reminder_effect["action"] == (
                    "reschedule" if mode == "relative" else "keep"
                )
                await db.commit()
            async with maker() as db:
                await collection.execute_collection(db, auth(), plan)
                await db.commit()
                r = await db.get(OneShotReminder, rid)
                assert r.due_at == (
                    original_due + timedelta(days=1) if mode == "relative" else original_due
                )
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())
