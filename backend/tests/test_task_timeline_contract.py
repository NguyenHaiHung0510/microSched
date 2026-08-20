"""Pure and throwaway-Postgres contract checks for the Task timeline seam."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task
from app.domain.tasks import (
    InvalidTaskCursor,
    TaskCreate,
    TaskStore,
    TaskUpdate,
    _cursor_decode,
    _cursor_encode,
)


def test_task_due_write_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone"):
        TaskCreate(title="naive", due_at=datetime(2026, 8, 16, 12, 0))
    with pytest.raises(ValueError, match="timezone"):
        TaskUpdate(due_at=datetime(2026, 8, 16, 12, 0))


def test_cursor_is_opaque_signed_and_scope_bound(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "timeline-test-secret")
    get_settings.cache_clear()
    token = _cursor_encode(
        {
            "v": 1,
            "status": "open",
            "from": "2026-08-13T00:00:00+00:00",
            "to": "2026-08-20T00:00:00+00:00",
            "bucket": "dated",
            "private": False,
            "direction": "forward",
            "expires": datetime.now(UTC).timestamp() + 60,
            "last": {"id": "0190a0b0-c0d0-7e00-8000-000000000020"},
        }
    )
    assert "." in token
    payload = _cursor_decode(
        token,
        status="open",
        from_instant=datetime.fromisoformat("2026-08-13T00:00:00+00:00"),
        to_instant=datetime.fromisoformat("2026-08-20T00:00:00+00:00"),
        bucket="dated",
        can_see_private=False,
    )
    assert payload["last"]["id"].endswith("0020")
    with pytest.raises(InvalidTaskCursor):
        _cursor_decode(
            token,
            status="completed",
            from_instant=datetime.fromisoformat("2026-08-13T00:00:00+00:00"),
            to_instant=datetime.fromisoformat("2026-08-20T00:00:00+00:00"),
            bucket="dated",
            can_see_private=False,
        )
    get_settings.cache_clear()


@pytest.mark.pg
def test_cursor_reaches_all_rows_beyond_191_on_throwaway_postgres(pg_dsn):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = TaskStore()
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash="timeline-contract-test",
            user_email="owner@example.com",
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
            private_until=None,
        )
        created: list[UUID] = []
        try:
            async with maker() as db:
                for index in range(205):
                    task = await store.create(
                        db,
                        auth,
                        TaskCreate(
                            title=f"Synthetic timeline {index}",
                            due_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
                        ),
                    )
                    created.append(task.id)
                for index in range(60):
                    overdue = await store.create(
                        db,
                        auth,
                        TaskCreate(
                            title=f"Completed overdue {index}",
                            due_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
                        ),
                    )
                    await store.update(
                        db,
                        auth,
                        overdue.id,
                        TaskUpdate(status="completed"),
                    )
                    created.append(overdue.id)
                open_overdue = await store.create(
                    db,
                    auth,
                    TaskCreate(
                        title="Open overdue remains reachable",
                        due_at=datetime(2026, 8, 1, 13, 0, tzinfo=UTC),
                    ),
                )
                created.append(open_overdue.id)
                undated_open: list[UUID] = []
                for index in range(60):
                    undated = await store.create(
                        db,
                        auth,
                        TaskCreate(title=f"Open undated picker {index}"),
                    )
                    undated_open.append(undated.id)
                    created.append(undated.id)
                await db.commit()

            collected: list[UUID] = []
            cursor = None
            async with maker() as db:
                while True:
                    page = await store.list_cursor(
                        db,
                        auth,
                        status="open",
                        from_instant=datetime(2026, 8, 16, tzinfo=UTC),
                        to_instant=datetime(2026, 8, 17, tzinfo=UTC),
                        bucket="dated",
                        limit=50,
                        cursor=cursor,
                    )
                    collected.extend(task.id for task in page.items)
                    if page.next_cursor is None:
                        break
                    cursor = page.next_cursor
            assert len(collected) == 205
            assert len(set(collected)) == 205
            assert set(collected) == set(created[:205])
            async with maker() as db:
                overdue_page = await store.list_cursor(
                    db,
                    auth,
                    status="all",
                    from_instant=datetime(2026, 8, 13, tzinfo=UTC),
                    to_instant=datetime(2026, 8, 20, tzinfo=UTC),
                    bucket="overdue",
                    limit=50,
                    now=datetime(2026, 8, 20, tzinfo=UTC),
                )
            assert [task.status for task in overdue_page.items] == ["open"]
            assert overdue_page.items[0].title == "Open overdue remains reachable"
            picker_ids: list[UUID] = []
            picker_cursor = None
            async with maker() as db:
                while True:
                    page = await store.list_cursor(
                        db,
                        auth,
                        status="open",
                        bucket="open_picker",
                        limit=50,
                        cursor=picker_cursor,
                    )
                    picker_ids.extend(task.id for task in page.items)
                    if page.next_cursor is None:
                        break
                    picker_cursor = page.next_cursor
            assert len(picker_ids) == 266
            assert len(set(picker_ids)) == 266
            assert set(undated_open).issubset(picker_ids)
        finally:
            async with maker() as db:
                await db.execute(delete(Task).where(Task.id.in_(created)))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
