"""Pure and throwaway-Postgres contract checks for the Task timeline seam."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession, Task
from app.domain.tasks import (
    VIETNAM_TZ,
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


_TEST_DB_URL = "postgresql://user:pass@localhost:5432/microsched"


def _isolate_local_env(monkeypatch):
    """Pin APP_ENV/DATABASE_URL so Settings() never falls back to backend/.env."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", _TEST_DB_URL)
    monkeypatch.delenv("ALLOW_PROD_DB_IN_LOCAL", raising=False)
    monkeypatch.delenv("NEON_DEVELOP_BRANCH_KEY", raising=False)
    monkeypatch.delenv("NEON_OWNER_URL", raising=False)
    monkeypatch.delenv("NEON_MIGRATOR_URL", raising=False)


def test_cursor_is_opaque_signed_and_scope_bound(monkeypatch):
    _isolate_local_env(monkeypatch)
    monkeypatch.setenv("OAUTH_STATE_SECRET", "timeline-test-secret")
    get_settings.cache_clear()
    token = _cursor_encode(
        {
            "v": 2,
            "status": "open",
            "from": "2026-08-13T00:00:00Z",
            "to": "2026-08-20T00:00:00Z",
            "bucket": "dated",
            "private": False,
            "direction": "forward",
            "expires": datetime.now(UTC).timestamp() + 60,
            "last": {
                "group_rank": 1,
                "group_day": "2026-08-16",
                "pinned": False,
                "schedule_day": "2026-08-16",
                "precision_rank": 1,
                "due_at": None,
                "created_at": "2026-08-12T08:00:00Z",
                "id": "0190a0b0-c0d0-7e00-8000-000000000020",
            },
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


def test_cursor_v1_and_due_at_only_positions_are_rejected(monkeypatch):
    _isolate_local_env(monkeypatch)
    monkeypatch.setenv("OAUTH_STATE_SECRET", "timeline-test-secret")
    get_settings.cache_clear()
    scope = {
        "status": "open",
        "from": "2026-08-13T00:00:00Z",
        "to": "2026-08-20T00:00:00Z",
        "bucket": "dated",
        "private": False,
        "direction": "forward",
        "expires": datetime.now(UTC).timestamp() + 60,
    }
    for version, last in (
        (1, {"id": "0190a0b0-c0d0-7e00-8000-000000000020"}),
        (
            2,
            {
                "pinned": False,
                "due_at": "2026-08-16T12:00:00Z",
                "created_at": "2026-08-12T08:00:00Z",
                "id": "0190a0b0-c0d0-7e00-8000-000000000020",
            },
        ),
    ):
        token = _cursor_encode({"v": version, **scope, "last": last})
        with pytest.raises(InvalidTaskCursor):
            _cursor_decode(
                token,
                status="open",
                from_instant=datetime.fromisoformat("2026-08-13T00:00:00+00:00"),
                to_instant=datetime.fromisoformat("2026-08-20T00:00:00+00:00"),
                bucket="dated",
                can_see_private=False,
            )
    get_settings.cache_clear()


def test_cursor_rejects_mismatched_group_precision_and_null_shapes(monkeypatch):
    _isolate_local_env(monkeypatch)
    monkeypatch.setenv("OAUTH_STATE_SECRET", "timeline-test-secret")
    get_settings.cache_clear()
    scope = {
        "v": 2,
        "status": "open",
        "from": "2026-08-13T00:00:00Z",
        "to": "2026-08-20T00:00:00Z",
        "bucket": "dated",
        "private": False,
        "direction": "forward",
        "expires": datetime.now(UTC).timestamp() + 60,
    }
    valid = {
        "group_rank": 1,
        "group_day": "2026-08-16",
        "pinned": False,
        "schedule_day": "2026-08-16",
        "precision_rank": 1,
        "due_at": None,
        "created_at": "2026-08-12T08:00:00Z",
        "id": "0190a0b0-c0d0-7e00-8000-000000000020",
    }
    invalid_positions = [
        {**valid, "group_rank": 0},
        {**valid, "group_day": "2026-08-15"},
        {**valid, "precision_rank": 0},
        {**valid, "precision_rank": 2},
        {**valid, "due_at": "2026-08-16T12:00:00+00:00"},
        {
            **valid,
            "precision_rank": 0,
            "due_at": "2026-08-15T12:00:00Z",
        },
        {key: value for key, value in valid.items() if key != "schedule_day"},
    ]
    for last in invalid_positions:
        token = _cursor_encode({**scope, "last": last})
        with pytest.raises(InvalidTaskCursor):
            _cursor_decode(
                token,
                status="open",
                from_instant=datetime(2026, 8, 13, tzinfo=UTC),
                to_instant=datetime(2026, 8, 20, tzinfo=UTC),
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
                    schedule = (
                        {
                            "due_precision": "date",
                            "due_on": date(2026, 8, 16),
                        }
                        if index % 3 == 0
                        else {
                            "due_precision": "datetime",
                            "due_at": datetime(
                                2026,
                                8,
                                15 if index % 3 == 1 else 16,
                                17 if index % 3 == 1 else 12,
                                0,
                                tzinfo=UTC,
                            ),
                        }
                    )
                    task = await store.create(
                        db,
                        auth,
                        TaskCreate(
                            title=f"Synthetic timeline {index}",
                            **schedule,
                        ),
                    )
                    if index % 17 == 0:
                        pinned = await store.update(db, auth, task.id, TaskUpdate(pinned=True))
                        assert pinned is not None
                    created.append(task.id)
                private_hidden = Task(
                    title="enc:v1:dGVzdA==",
                    is_private=True,
                    due_precision="date",
                    due_on=date(2026, 8, 16),
                )
                db.add(private_hidden)
                await db.flush()
                created.append(private_hidden.id)
                deleted_hidden = await store.create(
                    db,
                    auth,
                    TaskCreate(
                        title="Deleted timeline row",
                        due_precision="date",
                        due_on=date(2026, 8, 16),
                    ),
                )
                assert await store.soft_delete(db, auth, deleted_hidden.id)
                created.append(deleted_hidden.id)
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
                        from_instant=datetime(2026, 8, 15, 17, tzinfo=UTC),
                        to_instant=datetime(2026, 8, 16, 17, tzinfo=UTC),
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
            assert private_hidden.id not in collected
            assert deleted_hidden.id not in collected
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


@pytest.mark.pg
def test_typed_bucket_order_and_cursor_boundaries_match_the_normalized_key(pg_dsn):
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "task_schedule_order.json"
        ).read_text(encoding="utf-8")
    )

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = TaskStore()
        now = datetime(2026, 8, 24, 12, tzinfo=UTC)
        auth = AuthSession(
            token_hash="typed-timeline-contract",
            user_email="owner@example.test",
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
        )
        created: list[UUID] = []

        async def add(db, **kwargs):
            item = await store.create(db, auth, TaskCreate(**kwargs))
            created.append(item.id)
            return item

        try:
            async with maker() as db:
                for row in fixture["rows"]:
                    due_on = date.fromisoformat(row["due_on"]) if row["due_on"] else None
                    due_at = (
                        datetime.fromisoformat(row["due_at"].replace("Z", "+00:00"))
                        if row["due_at"]
                        else None
                    )
                    item = await add(
                        db,
                        id=UUID(row["id"]),
                        title=row["title"],
                        due_precision=row["due_precision"],
                        due_on=due_on,
                        due_at=due_at,
                    )
                    if row["pinned"]:
                        changed = await store.update(db, auth, item.id, TaskUpdate(pinned=True))
                        assert changed is not None
                completed = await add(
                    db,
                    title="completed-hidden",
                    status="completed",
                    due_precision="date",
                    due_on=date(2026, 8, 20),
                )
                deleted = await add(
                    db,
                    title="deleted-hidden",
                    due_precision="date",
                    due_on=date(2026, 8, 20),
                )
                assert await store.soft_delete(db, auth, deleted.id)
                await db.commit()

            from_instant = datetime(2026, 8, 19, 17, tzinfo=UTC)
            to_instant = datetime(2026, 8, 22, 17, tzinfo=UTC)

            async def collect(bucket: str, limit: int):
                result = []
                cursor = None
                async with maker() as db:
                    while True:
                        page = await store.list_cursor(
                            db,
                            auth,
                            status="open",
                            from_instant=from_instant if bucket != "open_picker" else None,
                            to_instant=to_instant if bucket != "open_picker" else None,
                            bucket=bucket,
                            limit=limit,
                            cursor=cursor,
                            now=now,
                        )
                        result.extend(page.items)
                        if page.next_cursor is None:
                            break
                        cursor = page.next_cursor
                return result

            for bucket, expected in fixture["buckets"].items():
                one_page = await collect(bucket, 100)
                assert [item.title for item in one_page] == expected
                assert completed.id not in {item.id for item in one_page}
                assert deleted.id not in {item.id for item in one_page}
                for limit in (1, 2):
                    paged = await collect(bucket, limit)
                    assert [item.title for item in paged] == expected
                    assert len({item.id for item in paged}) == len(expected)

        finally:
            async with maker() as db:
                await db.execute(delete(Task).where(Task.id.in_(created)))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_date_only_today_crosses_overdue_at_vietnam_midnight(pg_dsn):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = TaskStore()
        local_day = date(2026, 8, 24)
        auth = AuthSession(
            token_hash="date-overdue-contract",
            user_email="owner@example.test",
            last_seen_at=datetime(2026, 8, 24, tzinfo=UTC),
            expires_at=datetime(2026, 8, 26, tzinfo=UTC),
        )
        task_id = None
        try:
            async with maker() as db:
                created = await store.create(
                    db,
                    auth,
                    TaskCreate(
                        title="today-civil",
                        due_precision="date",
                        due_on=local_day,
                    ),
                )
                task_id = created.id
                await db.commit()

            range_start = datetime(2026, 8, 25, tzinfo=VIETNAM_TZ)
            before_midnight = datetime(2026, 8, 24, 23, 59, 59, tzinfo=VIETNAM_TZ)
            at_midnight = datetime(2026, 8, 25, tzinfo=VIETNAM_TZ)
            async with maker() as db:
                before = await store.list_cursor(
                    db,
                    auth,
                    bucket="overdue",
                    from_instant=range_start,
                    limit=10,
                    now=before_midnight,
                )
                after = await store.list_cursor(
                    db,
                    auth,
                    bucket="overdue",
                    from_instant=range_start,
                    limit=10,
                    now=at_midnight,
                )
            assert task_id not in {item.id for item in before.items}
            assert task_id in {item.id for item in after.items}
        finally:
            if task_id is not None:
                async with maker() as db:
                    await db.execute(delete(Task).where(Task.id == task_id))
                    await db.commit()
            await engine.dispose()

    asyncio.run(scenario())
