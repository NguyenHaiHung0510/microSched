"""STANDARD-only Mimi read tools against disposable PostgreSQL."""

import asyncio
import base64
import os
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.tools.registry import execute_read_tool
from app.agent.tools.task_reads import (
    TaskAggregate,
    TaskFilter,
    TaskInspectBatch,
    TaskQuery,
    aggregate_tasks,
    inspect_tasks,
    query_tasks,
)
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import Task

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def synthetic_cursor_key(monkeypatch):
    monkeypatch.setenv("MIMI_P0_DISABLE_DOTENV", "1")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_task_read_schema_rejects_invalid_bounds_before_database_access() -> None:
    ids = [uuid4() for _ in range(51)]
    for bad in ([], ids, [ids[0], ids[0]]):
        with pytest.raises(ValidationError):
            TaskInspectBatch(ids=bad)
    for limit in (0, 51):
        with pytest.raises(ValidationError):
            TaskQuery(limit=limit)
    with pytest.raises(ValidationError):
        TaskFilter(title_contains="x")
    with pytest.raises(ValidationError):
        TaskFilter(due_from=date(2026, 9, 23), due_through=date(2026, 9, 22))
    with pytest.raises(ValidationError):
        TaskQuery(projection=("id", "id"))


def test_task_reads_exclude_private_deleted_and_report_page_coverage(pg_dsn) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        prefix = f"mimi-read-{uuid4().hex}"
        owned_ids: list[UUID] = []
        try:
            async with maker() as db:
                rows = [Task(title=f"{prefix}-{i:02}", status="open") for i in range(51)]
                hidden = Task(title="enc:v1:synthetic-private", is_private=True)
                deleted_row = Task(title=f"{prefix}-deleted", deleted_at=datetime.now(UTC))
                db.add_all([*rows, hidden, deleted_row])
                await db.flush()
                owned_ids = [row.id for row in [*rows, hidden, deleted_row]]
                await db.commit()

            request = TaskQuery(filter=TaskFilter(title_contains=prefix), limit=50)
            async with maker() as db:
                first = await query_tasks(db, request)
                assert first["count"] == 50
                assert first["coverage"] == "partial"
                assert first["next_cursor"]
                assert all(row["title"].startswith(prefix) for row in first["rows"])
                second = await query_tasks(
                    db, request.model_copy(update={"cursor": first["next_cursor"]})
                )
                assert second["count"] == 1
                assert second["coverage"] == "complete"
                assert second["next_cursor"] is None
                assert len({row["id"] for row in first["rows"] + second["rows"]}) == 51
                assert "body_md" not in first["rows"][0]
                assert "body_md" not in first["omitted_fields"]
                narrow = await query_tasks(
                    db,
                    TaskQuery(
                        filter=TaskFilter(title_contains=f"{prefix}-00"),
                        projection=("title",),
                        limit=1,
                    ),
                )
                assert narrow["rows"][0]["id"] == str(rows[0].id)
                assert "id" not in narrow["omitted_fields"]

                groups = await aggregate_tasks(
                    db,
                    TaskAggregate(filter=TaskFilter(title_contains=prefix), group_by="status"),
                )
                assert groups["coverage"] == "complete"
                assert groups["groups"] == [{"value": "open", "count": 51}]

                inspected = await inspect_tasks(
                    db,
                    TaskInspectBatch(ids=(rows[0].id, hidden.id, deleted_row.id)),
                )
                assert [item["id"] for item in inspected["rows"]] == [str(rows[0].id)]
                assert inspected["missing_ids"] == [str(hidden.id), str(deleted_row.id)]

                with pytest.raises(ValueError, match="invalid_task_query_cursor"):
                    await query_tasks(db, request.model_copy(update={"cursor": "not-a-cursor"}))
                forged = first["next_cursor"].split(".", 1)[0]
                forged = f"{forged}.{'0' * 64}"
                with pytest.raises(ValueError, match="invalid_task_query_cursor"):
                    await query_tasks(db, request.model_copy(update={"cursor": forged}))
                with pytest.raises(ValueError, match="invalid_task_query_cursor"):
                    await query_tasks(
                        db,
                        request.model_copy(
                            update={
                                "filter": TaskFilter(title_contains=f"{prefix}-00"),
                                "cursor": first["next_cursor"],
                            }
                        ),
                    )
                with pytest.raises(ValueError, match="mimi_tool_not_read_only"):
                    await execute_read_tool(db, "task.create_candidate.v2", {})
        finally:
            if owned_ids:
                async with maker() as db:
                    await db.execute(delete(Task).where(Task.id.in_(owned_ids)))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_task_due_filter_uses_owner_calendar_day(pg_dsn) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        prefix = f"mimi-due-{uuid4().hex}"
        owned_ids: list[UUID] = []
        try:
            async with maker() as db:
                # The rolling-deploy compatibility trigger treats direct SQL
                # inserts as legacy writers unless this transaction opts in.
                await db.execute(text("SET LOCAL microsched.task_due_writer = 'v2'"))
                before_midnight = Task(
                    title=f"{prefix}-before",
                    due_precision="datetime",
                    due_at=datetime(2026, 9, 22, 16, 59, tzinfo=UTC),
                )
                after_midnight = Task(
                    title=f"{prefix}-after",
                    due_precision="datetime",
                    due_at=datetime(2026, 9, 22, 17, 0, tzinfo=UTC),
                )
                calendar_day = Task(
                    title=f"{prefix}-date", due_precision="date", due_on=date(2026, 9, 22)
                )
                db.add_all([before_midnight, after_midnight, calendar_day])
                await db.flush()
                owned_ids = [row.id for row in (before_midnight, after_midnight, calendar_day)]
                await db.commit()
            async with maker() as db:
                result = await query_tasks(
                    db,
                    TaskQuery(
                        filter=TaskFilter(
                            title_contains=prefix,
                            due_from=date(2026, 9, 22),
                            due_through=date(2026, 9, 22),
                        )
                    ),
                )
                assert {row["title"] for row in result["rows"]} == {
                    f"{prefix}-before",
                    f"{prefix}-date",
                }
        finally:
            if owned_ids:
                async with maker() as db:
                    await db.execute(delete(Task).where(Task.id.in_(owned_ids)))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
