"""Bounded public Task-content retrieval and child-source freshness on local PG."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.tools.registry import execute_read_tool
from app.agent.tools.task_content import TaskContentRead, read_task_content
from app.core.database_urls import async_postgres_url
from app.domain.models import AuthSession, Task, TaskItem
from app.domain.tasks import TaskItemCreate, TaskItemUpdate, TaskStore

pytestmark = pytest.mark.pg


def test_checklist_mutations_advance_parent_source_version(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        task_id = None
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="content-qa@test.local",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        store = TaskStore()
        try:
            async with maker() as db:
                task = Task(title="Synthetic source freshness", body_md="Nội dung nguồn")
                db.add(task)
                await db.flush()
                task_id = task.id
                # A stable older version makes the change observable without sleeps.
                task.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
                await db.commit()
            async with maker() as db:
                before = (
                    (await db.execute(select(Task).where(Task.id == task_id)))
                    .scalar_one()
                    .updated_at
                )
                item = await store.add_item(db, auth, task_id, TaskItemCreate(content="Bước một"))
                await db.commit()
                await db.refresh(await db.get(Task, task_id))
                after_add = (await db.get(Task, task_id)).updated_at
                assert after_add > before, "child create must invalidate the parent source version"
                item_id = item.id
                parent = await db.get(Task, task_id)
                before_update = parent.updated_at
                await store.update_item(
                    db, auth, task_id, item_id, TaskItemUpdate(content="Bước đã sửa")
                )
                await db.commit()
                await db.refresh(parent)
                assert parent.updated_at > before_update
                before_delete = parent.updated_at
                assert await store.delete_item(db, auth, task_id, item_id)
                await db.commit()
                await db.refresh(parent)
                assert parent.updated_at > before_delete
        finally:
            if task_id:
                async with maker() as db:
                    await db.execute(delete(Task).where(Task.id == task_id))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_content_request_rejects_unbounded_or_unversioned_continuation():
    for args in (
        {"body_limit": 4001},
        {"items_limit": 21},
        {"body_offset": -1},
        {"items_offset": 1},
        {"body_offset": 1},
        {"expected_version": "2026-01-01"},
    ):
        with pytest.raises(ValidationError):
            TaskContentRead(id=uuid4(), **args)


def test_content_pages_exclude_private_deleted_and_detect_child_changes(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        ids = []
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="content-qa@test.local",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        try:
            async with maker() as db:
                public = Task(title="Nội dung tiếng Việt", body_md="ế" * 5002)
                hidden = Task(
                    title="enc:v1:private-fixture", body_md="enc:v1:private-body", is_private=True
                )
                deleted = Task(title="Deleted source", deleted_at=datetime.now(UTC))
                db.add_all([public, hidden, deleted])
                await db.flush()
                ids = [public.id, hidden.id, deleted.id]
                items = [
                    TaskItem(task_id=public.id, position=i, content=f"Bước {i}") for i in range(22)
                ]
                items[0].content = "x" * 700
                db.add_all([*items, TaskItem(task_id=hidden.id, content="enc:v1:private-child")])
                await db.commit()
                first_item_id = items[0].id
            async with maker() as db:
                for task_id in (hidden.id, deleted.id, uuid4()):
                    missing = await read_task_content(db, TaskContentRead(id=task_id))
                    assert missing["rows"] == []
                    assert "private" not in str(missing)
                page = await execute_read_tool(
                    db, "task.read_content.v1", {"id": str(public.id), "items_limit": 10}
                )
                row = page["rows"][0]
                assert len(row["body_md"]) == 4000
                assert row["body_total_chars"] == 5002
                assert row["body_range"] == [0, 4000]
                assert len(row["items"]) == 10
                assert row["items"][0]["content"] == "x" * 500
                assert row["items"][0]["content_truncated"] is True
                assert page["coverage"] == "partial"
                assert "items.content.after_500_chars" in page["omitted_fields"]
                assert page["next_body_offset"] == 4000
                assert page["next_items_offset"] == 10
                version = row["source_version"]
                next_page = await read_task_content(
                    db,
                    TaskContentRead(
                        id=public.id, body_offset=4000, items_offset=10, expected_version=version
                    ),
                )
                assert next_page["rows"][0]["body_md"] == "ế" * 1002
                assert len(next_page["rows"][0]["items"]) == 12
                assert next_page["next_body_offset"] is None
                assert next_page["next_items_offset"] is None
                assert next_page["coverage"] == "partial"  # prefix lies outside this page
                await db.rollback()
            async with maker() as db:
                await TaskStore().update_item(
                    db,
                    auth,
                    public.id,
                    first_item_id,
                    TaskItemUpdate(content="Ràng buộc nguồn mới"),
                )
                await db.commit()
            async with maker() as db:
                with pytest.raises(ValueError, match="task_content_source_changed"):
                    await read_task_content(
                        db, TaskContentRead(id=public.id, expected_version=version)
                    )
                current = await read_task_content(db, TaskContentRead(id=public.id))
                assert current["rows"][0]["items"][0]["content"] == "Ràng buộc nguồn mới"
                assert current["rows"][0]["source_version"] != version
        finally:
            if ids:
                async with maker() as db:
                    await db.execute(delete(Task).where(Task.id.in_(ids)))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_content_snapshot_lock_serializes_checklist_writer(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        task_id = None
        auth = AuthSession(
            token_hash=uuid4().hex,
            user_email="content-qa@test.local",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        try:
            async with maker() as seed:
                task = Task(title="Concurrent content source", body_md="Nguồn ban đầu")
                seed.add(task)
                await seed.flush()
                task_id = task.id
                await seed.commit()
            async with maker() as reader, maker() as writer:
                snapshot = await read_task_content(reader, TaskContentRead(id=task_id))
                await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
                with pytest.raises(DBAPIError, match="lock timeout"):
                    await TaskStore().add_item(
                        writer, auth, task_id, TaskItemCreate(content="New step")
                    )
                await writer.rollback()
                await reader.rollback()
                await TaskStore().add_item(
                    writer, auth, task_id, TaskItemCreate(content="New step")
                )
                await writer.commit()
                with pytest.raises(ValueError, match="task_content_source_changed"):
                    await read_task_content(
                        reader,
                        TaskContentRead(
                            id=task_id, expected_version=snapshot["rows"][0]["source_version"]
                        ),
                    )
        finally:
            if task_id:
                async with maker() as cleanup:
                    await cleanup.execute(delete(Task).where(Task.id == task_id))
                    await cleanup.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_body_continuation_crosses_former_offset_limit(pg_dsn):
    async def scenario():
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        task_id = None
        try:
            async with maker() as seed:
                task = Task(title="Synthetic large body boundary", body_md="x" * 1_004_020)
                seed.add(task)
                await seed.flush()
                task_id = task.id
                await seed.commit()
            async with maker() as reader:
                first = await read_task_content(reader, TaskContentRead(id=task_id, body_limit=1))
                version = first["rows"][0]["source_version"]
                for offset in (999_999, 1_000_000, 1_000_001):
                    page = await read_task_content(
                        reader,
                        TaskContentRead(id=task_id, body_offset=offset, expected_version=version),
                    )
                    assert len(page["rows"][0]["body_md"]) == 4000
                    next_offset = page["next_body_offset"]
                    assert next_offset == offset + 4000
                    continued = await read_task_content(
                        reader,
                        TaskContentRead(
                            id=task_id, body_offset=next_offset, expected_version=version
                        ),
                    )
                    assert continued["next_body_offset"] is None
                    assert continued["rows"][0]["body_range"][1] == 1_004_020
        finally:
            if task_id:
                async with maker() as cleanup:
                    await cleanup.execute(delete(Task).where(Task.id == task_id))
                    await cleanup.commit()
            await engine.dispose()

    asyncio.run(scenario())
