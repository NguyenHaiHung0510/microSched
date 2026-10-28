"""Full Task fields/checklists/lifecycle/reminder/undo and content obligations."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_mimi_task_collection_pg import auth, cleanup, seed

from app.agent import task_collection as c
from app.agent.selection import SelectionCandidate, bind_selection
from app.agent.tools.task_content import TaskContentRead, read_task_content
from app.agent.tools.task_reads import TaskFilter, TaskQuery, query_tasks
from app.core.database_urls import async_postgres_url
from app.domain.models import OneShotReminder, Task, TaskItem
from app.domain.one_shot import ReminderWrite, save_reminder

pytestmark = pytest.mark.pg


async def freeze(db, tid, *, action="edit", fields=None, children=(), reminder=None):
    task = await db.get(Task, tid)
    return await c.freeze_collection(
        db,
        c.CollectionCandidate(
            selection_id=uuid4(),
            entries=(
                c.TaskCommand(
                    id=tid,
                    action=action,
                    expected_collection_version=task.collection_version,
                    fields=fields or {},
                    children=children,
                    reminder=reminder or c.ReminderCommand(),
                ),
            ),
        ),
        covered_versions={tid: task.collection_version},
    )


def test_full_fields_checklist_identity_order_tombstone_and_parent_lifecycle(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            async with maker() as db:
                plan = await freeze(
                    db,
                    tid,
                    fields={
                        "title": "Tập luyện 🏃",
                        "body_md": "Đủ " * 3000,
                        "priority": "p3",
                        "pinned": True,
                        "due_precision": "date",
                        "due_on": "2026-10-15",
                        "due_at": None,
                    },
                    children=(
                        c.ChildCommand(action="append", fields={"content": "Bước một"}),
                        c.ChildCommand(
                            action="append", fields={"content": "Bước hai", "is_completed": True}
                        ),
                    ),
                )
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                items = (
                    await db.scalars(
                        select(TaskItem).where(TaskItem.task_id == tid).order_by(TaskItem.position)
                    )
                ).all()
                a, b = [i.id for i in items]
                assert items[1].is_completed and items[0].content == "Bước một"
            async with maker() as db:
                plan = await freeze(
                    db,
                    tid,
                    fields={"priority": None, "body_md": None, "status": "completed"},
                    children=(
                        c.ChildCommand(
                            action="patch",
                            id=a,
                            fields={"content": "Sửa đủ nội dung", "is_completed": True},
                        ),
                        c.ChildCommand(action="patch", id=b, fields={"is_completed": False}),
                        c.ChildCommand(action="reorder", ids=(b, a)),
                    ),
                )
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                task = await db.get(Task, tid)
                assert (
                    task.completed_at is not None and task.title == "Tập luyện 🏃" and task.pinned
                )
                assert (
                    task.priority is None and task.body_md is None and task.due_precision == "date"
                )
                assert (await db.get(TaskItem, a)).position == 1 and (
                    await db.get(TaskItem, b)
                ).position == 0
            async with maker() as db:
                plan = await freeze(
                    db,
                    tid,
                    fields={
                        "status": "open",
                        "due_precision": "none",
                        "due_on": None,
                        "due_at": None,
                    },
                    children=(c.ChildCommand(action="remove", id=b),),
                )
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                assert (await db.get(Task, tid)).completed_at is None
                assert (await db.get(TaskItem, b)).deleted_at is not None
            async with maker() as db:
                plan = await freeze(db, tid, action="soft_delete")
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                assert (await db.get(Task, tid)).deleted_at is not None
                assert (await db.get(TaskItem, a)).deleted_at is None
            async with maker() as db:
                plan = await freeze(db, tid, action="restore")
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                assert (await db.get(TaskItem, b)).deleted_at is not None
            async with maker() as db:
                plan = await freeze(db, tid, children=(c.ChildCommand(action="restore", id=b),))
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                assert (await db.get(TaskItem, b)).content == "Bước hai"
                with pytest.raises(HTTPException, match="exact_active_ids"):
                    await freeze(db, tid, children=(c.ChildCommand(action="reorder", ids=(a,)),))
                with pytest.raises(HTTPException, match="not_in_target"):
                    await freeze(
                        db,
                        tid,
                        children=(
                            c.ChildCommand(
                                action="patch", id=uuid4(), fields={"content": "invalid"}
                            ),
                        ),
                    )
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_long_body_and_item_continuation_union_clears_obligations_and_stale_stops(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            async with maker() as db:
                task = await db.get(Task, tid)
                task.body_md = "ế" * 12000
                db.add_all(
                    [
                        TaskItem(
                            task_id=tid, content="í" * 1200 if i == 0 else f"Bước {i}", position=i
                        )
                        for i in range(25)
                    ]
                )
                await db.commit()
            async with maker() as db:
                query = await query_tasks(
                    db, TaskQuery(filter=TaskFilter(title_contains="Synthetic collection"))
                )
                first = await read_task_content(db, TaskContentRead(id=tid))
                row = first["rows"][0]
                version = row["source_version"]
                child = uuid4()
                child = row["items"][0]["id"]
                receipts = [
                    {
                        "event_id": "query",
                        "tool": "task.query.v1",
                        "arguments": {"filter": {}, "cursor": None},
                        "result": query,
                    },
                    {
                        "event_id": "content1",
                        "tool": "task.read_content.v1",
                        "arguments": {},
                        "result": first,
                    },
                ]
                candidate = SelectionCandidate(
                    intent="Đọc đủ nội dung",
                    variants_considered=("synthetic",),
                    members=({"id": tid, "classification": "included", "reason": "Thực tế"},),
                )
                with pytest.raises(ValueError, match="unresolved_obligations"):
                    bind_selection(candidate, receipts)
                second = await read_task_content(
                    db,
                    TaskContentRead(
                        id=tid, body_offset=4000, items_offset=20, expected_version=version
                    ),
                )
                suffix1 = await read_task_content(
                    db,
                    TaskContentRead(
                        id=tid,
                        body_offset=8000,
                        item_content_offsets={child: 500},
                        expected_version=version,
                    ),
                )
                suffix2 = await read_task_content(
                    db,
                    TaskContentRead(
                        id=tid, item_content_offsets={child: 1000}, expected_version=version
                    ),
                )
                for i, result in enumerate((second, suffix1, suffix2)):
                    receipts.append(
                        {
                            "event_id": f"content{i + 2}",
                            "tool": "task.read_content.v1",
                            "arguments": {},
                            "result": result,
                        }
                    )
                bound = bind_selection(candidate, receipts)
                assert bound["semantic_complete"] and bound["content_obligations"] == []
                assert (
                    first["rows"][0]["body_md"]
                    + second["rows"][0]["body_md"]
                    + suffix1["rows"][0]["body_md"]
                    == "ế" * 12000
                )
                assert (
                    row["items"][0]["content"]
                    + suffix1["rows"][0]["items"][0]["content"]
                    + suffix2["rows"][0]["items"][0]["content"]
                    == "í" * 1200
                )
                await db.rollback()
            async with maker() as db:
                await db.execute(
                    text("UPDATE microsched.task_item SET content='concurrent' WHERE id=:id"),
                    {"id": child},
                )
                await db.commit()
            async with maker() as db:
                with pytest.raises(ValueError, match="source_changed"):
                    await read_task_content(db, TaskContentRead(id=tid, expected_version=version))
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("drift", ["sending", "revision", "absence"])
def test_reminder_drift_freezes_zero_write_and_sending_blocks_effects(pg_dsn, drift):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            future = datetime.now(UTC) + timedelta(days=3)
            async with maker() as db:
                task = await db.get(Task, tid)
                task.due_precision = "datetime"
                task.due_at = future
                await db.flush()
                await db.refresh(task)
                reminder = await save_reminder(
                    db, auth(), "task", tid, ReminderWrite(mode="relative", offset_minutes=-30)
                )
                rid = reminder.id
                await db.commit()
            async with maker() as db:
                plan = await freeze(
                    db,
                    tid,
                    fields={
                        "priority": "p1",
                        "due_precision": "datetime",
                        "due_on": None,
                        "due_at": (future + timedelta(days=1)).isoformat(),
                    },
                )
                await db.commit()
            async with maker() as db:
                r = await db.get(OneShotReminder, rid)
                if drift == "absence":
                    r.status = "cancelled"
                elif drift == "sending":
                    r.status = "sending"
                else:
                    r.revision += 1
                await db.commit()
            async with maker() as db:
                with pytest.raises(HTTPException, match="stale"):
                    await c.execute_collection(db, auth(), plan)
                assert (await db.get(Task, tid)).priority is None
                if drift == "sending":
                    with pytest.raises(HTTPException, match="send_requires_reconciliation"):
                        await freeze(db, tid, action="soft_delete")
                await db.rollback()
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_relative_missing_anchor_absolute_cancel_and_restore_no_rearm(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            future = datetime.now(UTC) + timedelta(days=3)
            async with maker() as db:
                task = await db.get(Task, tid)
                task.due_precision = "datetime"
                task.due_at = future
                await db.flush()
                await db.refresh(task)
                r = await save_reminder(
                    db, auth(), "task", tid, ReminderWrite(mode="relative", offset_minutes=-30)
                )
                rid = r.id
                await db.commit()
            async with maker() as db:
                plan = await freeze(
                    db, tid, fields={"due_precision": "none", "due_on": None, "due_at": None}
                )
                assert plan.entries[0].reminder_effect["action"] == "needs_reschedule"
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                assert (await db.get(OneShotReminder, rid)).status == "needs_reschedule"
            async with maker() as db:
                plan = await freeze(
                    db,
                    tid,
                    reminder=c.ReminderCommand(
                        action="configure",
                        configuration=ReminderWrite(mode="absolute", due_at=future),
                    ),
                )
                await c.execute_collection(db, auth(), plan)
                await db.commit()
            async with maker() as db:
                plan = await freeze(db, tid, action="soft_delete")
                assert plan.entries[0].reminder_effect["action"] == "cancel"
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                cancelled = (
                    await db.scalars(select(OneShotReminder).where(OneShotReminder.task_id == tid))
                ).all()
                assert all(r.status == "cancelled" for r in cancelled)
            async with maker() as db:
                plan = await freeze(db, tid, action="restore")
                await c.execute_collection(db, auth(), plan)
                await db.commit()
                assert all(
                    r.status == "cancelled"
                    for r in (
                        await db.scalars(
                            select(OneShotReminder).where(OneShotReminder.task_id == tid)
                        )
                    ).all()
                )
                with pytest.raises(ValueError, match="future"):
                    await freeze(
                        db,
                        tid,
                        reminder=c.ReminderCommand(
                            action="configure",
                            configuration=ReminderWrite(
                                mode="absolute", due_at=datetime.now(UTC) - timedelta(days=1)
                            ),
                        ),
                    )
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_undo_post_version_conflict_does_not_overwrite_later_edit(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            async with maker() as db:
                plan = await freeze(db, tid, fields={"priority": "p1"})
                recovery = await c.execute_collection(db, auth(), plan)
                await db.commit()
            async with maker() as db:
                task = await db.get(Task, tid)
                task.body_md = "Later unrelated content"
                await db.commit()
            async with maker() as db:
                with pytest.raises(HTTPException, match="post_version_stale"):
                    await c.freeze_undo(db, uuid4(), recovery)
                task = await db.get(Task, tid)
                assert task.priority == "p1" and task.body_md == "Later unrelated content"
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_raw_child_and_parent_writers_preserve_monotone_aggregate_version(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = await seed(maker, 1)
        tid = ids[0]
        try:
            async with maker() as db:
                child = TaskItem(task_id=tid, content="before")
                db.add(child)
                await db.commit()
                cid = child.id
                before = (await db.get(Task, tid)).collection_version
            first_locked = asyncio.Event()
            release = asyncio.Event()

            async def parent():
                async with maker() as db:
                    task = (
                        await db.scalars(select(Task).where(Task.id == tid).with_for_update())
                    ).one()
                    task.title = "parent changed"
                    await db.flush()
                    first_locked.set()
                    await release.wait()
                    await db.commit()

            async def raw_child():
                await first_locked.wait()
                async with maker() as db:
                    await db.execute(text("SET LOCAL lock_timeout='3s'"))
                    await db.execute(
                        text("UPDATE microsched.task_item SET content='raw changed' WHERE id=:id"),
                        {"id": cid},
                    )
                    await db.commit()

            p = asyncio.create_task(parent())
            await first_locked.wait()
            r = asyncio.create_task(raw_child())
            release.set()
            await asyncio.gather(p, r)
            async with maker() as db:
                task = await db.get(Task, tid)
                child = await db.get(TaskItem, cid)
                assert (
                    task.collection_version >= before + 2
                    and task.title == "parent changed"
                    and child.content == "raw changed"
                )
                current = task.collection_version
                await db.execute(
                    text("UPDATE microsched.task SET collection_version=1 WHERE id=:id"),
                    {"id": tid},
                )
                await db.commit()
                await db.refresh(task)
                assert task.collection_version == current + 1
        finally:
            await cleanup(maker, ids)
            await engine.dispose()

    asyncio.run(scenario())
