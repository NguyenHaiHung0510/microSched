"""Executable contract for the task store (008 Phase 0 → Phase 1 handshake).

This file is written RED on purpose. ``app.domain.tasks`` does not exist yet; Phase 0
(Agent-Opus) ships only the DB invariant, and Phase 1 (Codex) makes these pass. Each
test therefore imports the module lazily, inside the test body, and the whole module
is marked ``xfail(strict=True)``:

  * Phase 0 - the import raises, every test is an expected failure (xfailed), the CI
    gate stays green while the contract is provably unmet.
  * Phase 1 - once ``TaskStore`` and its DTOs exist and behave, the tests XPASS, which
    under ``strict=True`` is a RED. That red is the signal to **delete this xfail
    marker** (see below); after removal the tests are ordinary green checks.

Do not weaken these into an in-memory double: the at-rest ciphertext and privacy-gate
guarantees are only real against Postgres (spec §2.7), so the module is also ``pg``.

Contract the store must satisfy (spec §1.3, §2.1-§2.3, §2.6):

  store = TaskStore()                         # holds no session; each call takes one
  await store.create(db, auth, TaskCreate(title, body_md=None, is_private=False,
                                           priority=None, due_at=None, items=[str,...]))
  await store.list(db, auth, status="open", limit=100, offset=0) -> list[TaskRead]
  await store.get(db, auth, task_id)          -> TaskRead | None   (None => router 404)
  await store.update(db, auth, task_id, TaskUpdate(...optional...)) -> TaskRead | None
  await store.soft_delete(db, auth, task_id)  -> bool
  await store.list_items(db, auth, task_id)   -> list[TaskItemRead] | None
  await store.add_item(db, auth, task_id, TaskItemCreate(content, position=0))
  await store.update_item(db, auth, task_id, item_id, TaskItemUpdate(...)) -> ... | None

  * writes encrypt title/body_md/every item iff is_private, None-guarded (§2.2, #6);
  * reads decrypt; a locked session (private_until in the past/None) never sees a
    private task and never reaches its items (§2.3, §2.6, #2/#4);
  * task_item.task_id is immutable - update_item must refuse a reparent (§2.1, #7);
  * DELETE is soft (sets deleted_at); the row stays, filtered out on read (§2.6).

TaskRead exposes .id/.title/.body_md/.is_private/.items; each item read exposes
.id/.content. Adjust attribute names here and in tasks.py together if you must, but
keep the behaviours - 009-012 copy this shape.
"""

import asyncio
import base64
import contextlib
import os
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession

pytestmark = [
    pytest.mark.pg,
    pytest.mark.xfail(
        reason="Phase 1 (Codex): implement app/domain/tasks.py, then DELETE this marker",
        strict=True,
    ),
]

VIETNAMESE = "Hẹn gặp lúc 9 giờ — cà phê Đá, nhớ mang hồ sơ đã ký."
SECOND_ITEM = "Gọi điện xác nhận phòng họp số 3."


@pytest.fixture(autouse=True)
def fresh_key(monkeypatch):
    """Give crypto a throwaway key so the store can seal/open without a real .env."""
    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", key)
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _tasks():
    """Import the not-yet-existing store lazily so xfail captures the ImportError."""
    from app.domain import tasks

    return tasks


def _auth(*, unlocked: bool) -> AuthSession:
    """Build an in-memory session row; unlocked means private_until is in the future."""
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="contract-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@contextlib.asynccontextmanager
async def _session():
    """Yield a request-scoped AsyncSession bound to the migrator URL, then dispose."""
    engine = create_async_engine(async_postgres_url(os.environ["NEON_MIGRATOR_URL"]))
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            yield db
    finally:
        await engine.dispose()


async def _raw_val(dsn: str, sql: str, *args):
    """Read a single value on a fresh connection - i.e. what is committed at rest."""
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


async def _raw_row(dsn: str, sql: str, *args):
    """Read one row on a fresh connection."""
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetchrow(sql, *args)
    finally:
        await conn.close()


async def _cleanup(dsn: str, *task_ids) -> None:
    """Hard-delete tasks a test created (cascades to items); ephemeral CI DB anyway."""
    conn = await asyncpg.connect(dsn)
    try:
        for task_id in task_ids:
            if task_id is not None:
                await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
    finally:
        await conn.close()


def test_private_task_is_ciphertext_at_rest_and_plaintext_through_the_store(pg_dsn):
    """Case 1: create private -> every prose column is enc:v1:%, reads come back clear."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(
                    db,
                    _auth(unlocked=True),
                    tasks.TaskCreate(
                        title=VIETNAMESE,
                        body_md="Nội dung riêng tư.",
                        is_private=True,
                        items=[VIETNAMESE, SECOND_ITEM],
                    ),
                )
                await db.commit()
                task_id = created.id

                assert created.title == VIETNAMESE
                assert created.body_md == "Nội dung riêng tư."
                assert [item.content for item in created.items] == [VIETNAMESE, SECOND_ITEM]

            row = await _raw_row(
                pg_dsn, "SELECT title, body_md FROM microsched.task WHERE id = $1", task_id
            )
            assert row["title"].startswith("enc:v1:")
            assert row["body_md"].startswith("enc:v1:")
            plaintext_items = await _raw_val(
                pg_dsn,
                "SELECT count(*) FROM microsched.task_item "
                "WHERE task_id = $1 AND content NOT LIKE 'enc:v1:%'",
                task_id,
            )
            assert plaintext_items == 0
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())


def test_toggle_private_round_trips_three_times_without_corruption(pg_dsn):
    """Case 2: public<->private x3 keeps content exact and never violates the trigger."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        auth = _auth(unlocked=True)
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(
                    db,
                    auth,
                    tasks.TaskCreate(
                        title=VIETNAMESE,
                        body_md="thân bài",
                        is_private=False,
                        items=[VIETNAMESE, SECOND_ITEM],
                    ),
                )
                await db.commit()
                task_id = created.id

                for _ in range(3):
                    await store.update(db, auth, task_id, tasks.TaskUpdate(is_private=True))
                    await db.commit()
                    # While private, nothing plaintext may remain under the task.
                    leaked = await _raw_val(
                        pg_dsn,
                        "SELECT count(*) FROM microsched.task_item "
                        "WHERE task_id = $1 AND content NOT LIKE 'enc:v1:%'",
                        task_id,
                    )
                    title = await _raw_val(
                        pg_dsn, "SELECT title FROM microsched.task WHERE id = $1", task_id
                    )
                    assert leaked == 0
                    assert title.startswith("enc:v1:")

                    private_view = await store.get(db, auth, task_id)
                    assert private_view.title == VIETNAMESE
                    assert [item.content for item in private_view.items] == [
                        VIETNAMESE,
                        SECOND_ITEM,
                    ]

                    await store.update(db, auth, task_id, tasks.TaskUpdate(is_private=False))
                    await db.commit()
                    public_view = await store.get(db, auth, task_id)
                    assert public_view.title == VIETNAMESE
                    assert [item.content for item in public_view.items] == [
                        VIETNAMESE,
                        SECOND_ITEM,
                    ]
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())


def test_locked_session_cannot_see_or_open_a_private_task(pg_dsn):
    """Case 3: private_until in the past hides list/get; unlocking reveals + decrypts."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(
                    db,
                    _auth(unlocked=True),
                    tasks.TaskCreate(title=VIETNAMESE, is_private=True, items=[]),
                )
                await db.commit()
                task_id = created.id

                locked = _auth(unlocked=False)
                listed = await store.list(db, locked)
                assert all(task.id != task_id for task in listed)
                assert await store.get(db, locked, task_id) is None

                unlocked = _auth(unlocked=True)
                opened = await store.get(db, unlocked, task_id)
                assert opened is not None
                assert opened.title == VIETNAMESE
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())


def test_locked_session_cannot_reach_items_of_a_private_task(pg_dsn):
    """Case 4 (#2): items are gated through the parent - locked view gets None, no leak."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(
                    db,
                    _auth(unlocked=True),
                    tasks.TaskCreate(
                        title=VIETNAMESE, is_private=True, items=[VIETNAMESE, SECOND_ITEM]
                    ),
                )
                await db.commit()
                task_id = created.id

                locked = _auth(unlocked=False)
                assert await store.list_items(db, locked, task_id) is None
                assert await store.get(db, locked, task_id) is None
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())


def test_soft_deleted_task_hides_itself_and_its_items(pg_dsn):
    """Case 5 (#4): deleting the parent removes it and its items from every read path."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        auth = _auth(unlocked=True)
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(
                    db,
                    auth,
                    tasks.TaskCreate(title="Điện nước", items=[SECOND_ITEM]),
                )
                await db.commit()
                task_id = created.id

                assert await store.soft_delete(db, auth, task_id) is True
                await db.commit()

                assert await store.get(db, auth, task_id) is None
                assert all(task.id != task_id for task in await store.list(db, auth))
                assert await store.list_items(db, auth, task_id) is None
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())


def test_private_task_with_null_body_does_not_crash_on_encrypt(pg_dsn):
    """Case 6 (#6): body_md=None must not reach crypto.encrypt; it reads back as None."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        auth = _auth(unlocked=True)
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(
                    db,
                    auth,
                    tasks.TaskCreate(title=VIETNAMESE, body_md=None, is_private=True, items=[]),
                )
                await db.commit()
                task_id = created.id
                assert created.body_md is None

                reopened = await store.get(db, auth, task_id)
                assert reopened.body_md is None

            stored_body = await _raw_val(
                pg_dsn, "SELECT body_md FROM microsched.task WHERE id = $1", task_id
            )
            assert stored_body is None
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())


def test_update_item_refuses_to_reparent(pg_dsn):
    """Case 7 (#7): changing an item's task_id is refused (would strand ciphertext)."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        auth = _auth(unlocked=True)
        first_id = None
        second_id = None
        try:
            async with _session() as db:
                first = await store.create(
                    db, auth, tasks.TaskCreate(title="Task A", items=[SECOND_ITEM])
                )
                second = await store.create(db, auth, tasks.TaskCreate(title="Task B", items=[]))
                await db.commit()
                first_id = first.id
                second_id = second.id
                item_id = first.items[0].id

                with pytest.raises(ValueError):
                    await store.update_item(
                        db,
                        auth,
                        first_id,
                        item_id,
                        tasks.TaskItemUpdate(task_id=second_id),
                    )
        finally:
            await _cleanup(pg_dsn, first_id, second_id)

    asyncio.run(scenario())


def test_soft_delete_leaves_the_row_with_a_timestamp(pg_dsn):
    """Case 8: DELETE is soft - the row survives in the table with deleted_at set."""

    async def scenario():
        tasks = _tasks()
        store = tasks.TaskStore()
        auth = _auth(unlocked=True)
        task_id = None
        try:
            async with _session() as db:
                created = await store.create(db, auth, tasks.TaskCreate(title="giữ lại hàng"))
                await db.commit()
                task_id = created.id

                await store.soft_delete(db, auth, task_id)
                await db.commit()

            deleted_at = await _raw_val(
                pg_dsn, "SELECT deleted_at FROM microsched.task WHERE id = $1", task_id
            )
            assert deleted_at is not None
        finally:
            await _cleanup(pg_dsn, task_id)

    asyncio.run(scenario())
