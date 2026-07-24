"""DB-level proof of the task_item privacy invariant (008 Phase 0, migration 0003).

These tests talk to a real Postgres on purpose (spec §2.7): the invariant is a pair
of triggers plus a row lock, none of which an in-memory double can exercise. Every
value here is raw SQL through asyncpg so the test asserts what the *database* does,
independent of any store code (``app.domain.tasks`` does not exist yet - that is
Phase 1). ``enc:v1:`` literals stand in for real ciphertext because the triggers key
purely off the prefix, exactly like the column CHECKs.

The suite is written to fail loudly if the triggers are removed: dropping either one
turns the matching "rejected" case green-to-red, which is how we know the test is
testing the trigger and not itself. See the PR body for that red/green transcript.
"""

import asyncio
import contextlib
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.pg

# A private task's title must already satisfy task's private_ciphertext CHECK, so a
# task can only ever be flipped to private once its prose is ciphertext. The store
# guarantees that ordering (encrypt first, then set is_private); here we just pin the
# title to a valid ciphertext literal so the parent CHECK is never what fails.
CIPHER_TITLE = "enc:v1:cGxhY2Vob2xkZXI="
CIPHER_ITEM = "enc:v1:aXRlbS1jaXBoZXJ0ZXh0"
PLAINTEXT = "buy milk"

ITEM_REJECT = "ciphertext when parent task is private"
TOGGLE_REJECT = "plaintext task_item children"


async def _create_task(conn: asyncpg.Connection, *, title: str, is_private: bool):
    """Insert one task and return its generated id."""
    return await conn.fetchval(
        "INSERT INTO microsched.task (title, is_private) VALUES ($1, $2) RETURNING id",
        title,
        is_private,
    )


async def _plaintext_item_count(conn: asyncpg.Connection, task_id) -> int:
    """Count children of a task whose content is NOT ciphertext."""
    return await conn.fetchval(
        "SELECT count(*) FROM microsched.task_item "
        "WHERE task_id = $1 AND content NOT LIKE 'enc:v1:%'",
        task_id,
    )


async def _delete_task(conn: asyncpg.Connection, task_id) -> None:
    """Remove a task (task_item rows cascade) so tests leave no residue."""
    if task_id is not None:
        await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)


# --- Single-connection trigger behaviour (cases 1-5) ---------------------------------


def test_plaintext_item_under_private_task_is_rejected(pg_dsn):
    """Case 1: a bare item may not be written beneath an already-private task."""

    async def scenario():
        conn = await asyncpg.connect(pg_dsn)
        task_id = None
        try:
            task_id = await _create_task(conn, title=CIPHER_TITLE, is_private=True)
            with pytest.raises(asyncpg.exceptions.RaiseError, match=ITEM_REJECT):
                await conn.execute(
                    "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                    task_id,
                    PLAINTEXT,
                )
            assert await _plaintext_item_count(conn, task_id) == 0
        finally:
            await _delete_task(conn, task_id)
            await conn.close()

    asyncio.run(scenario())


def test_ciphertext_item_under_private_task_is_accepted(pg_dsn):
    """Case 2: a ciphertext item under a private task passes the trigger."""

    async def scenario():
        conn = await asyncpg.connect(pg_dsn)
        task_id = None
        try:
            task_id = await _create_task(conn, title=CIPHER_TITLE, is_private=True)
            await conn.execute(
                "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                task_id,
                CIPHER_ITEM,
            )
            total = await conn.fetchval(
                "SELECT count(*) FROM microsched.task_item WHERE task_id = $1", task_id
            )
            assert total == 1
        finally:
            await _delete_task(conn, task_id)
            await conn.close()

    asyncio.run(scenario())


def test_plaintext_item_under_public_task_is_accepted(pg_dsn):
    """Case 3: a public task carries plaintext items freely."""

    async def scenario():
        conn = await asyncpg.connect(pg_dsn)
        task_id = None
        try:
            task_id = await _create_task(conn, title="public title", is_private=False)
            await conn.execute(
                "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                task_id,
                PLAINTEXT,
            )
            assert await _plaintext_item_count(conn, task_id) == 1
        finally:
            await _delete_task(conn, task_id)
            await conn.close()

    asyncio.run(scenario())


def test_toggle_to_private_with_plaintext_child_is_rejected(pg_dsn):
    """Case 4: a task cannot go private while a plaintext child still exists."""

    async def scenario():
        conn = await asyncpg.connect(pg_dsn)
        task_id = None
        try:
            # Ciphertext title so the parent CHECK is never the blocker; the plaintext
            # child is what the second trigger must catch.
            task_id = await _create_task(conn, title=CIPHER_TITLE, is_private=False)
            await conn.execute(
                "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                task_id,
                PLAINTEXT,
            )
            with pytest.raises(asyncpg.exceptions.RaiseError, match=TOGGLE_REJECT):
                await conn.execute(
                    "UPDATE microsched.task SET is_private = true WHERE id = $1", task_id
                )
            still_public = await conn.fetchval(
                "SELECT is_private FROM microsched.task WHERE id = $1", task_id
            )
            assert still_public is False
        finally:
            await _delete_task(conn, task_id)
            await conn.close()

    asyncio.run(scenario())


def test_toggle_to_private_with_only_ciphertext_children_is_accepted(pg_dsn):
    """Case 5: with every child already ciphertext, the flip to private succeeds."""

    async def scenario():
        conn = await asyncpg.connect(pg_dsn)
        task_id = None
        try:
            task_id = await _create_task(conn, title=CIPHER_TITLE, is_private=False)
            await conn.execute(
                "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                task_id,
                CIPHER_ITEM,
            )
            await conn.execute(
                "UPDATE microsched.task SET is_private = true WHERE id = $1", task_id
            )
            now_private = await conn.fetchval(
                "SELECT is_private FROM microsched.task WHERE id = $1", task_id
            )
            assert now_private is True
        finally:
            await _delete_task(conn, task_id)
            await conn.close()

    asyncio.run(scenario())


# --- Concurrency: why the trigger alone is not enough (case 6) -----------------------


async def _wait_until_blocked(monitor: asyncpg.Connection, pid: int, timeout: float = 10.0):
    """Return once backend ``pid`` is parked on a lock, so the race is deterministic."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        blocked = await monitor.fetchval(
            "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = $1", pid
        )
        if blocked:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("expected the second session to block on the parent-row lock")


def test_concurrent_toggle_and_insert_breaks_without_lock_and_holds_with_lock(pg_dsn):
    """Case 6: the trigger is a last net; the parent-row lock is the primary one.

    Two READ COMMITTED transactions do not see each other's uncommitted work, so a
    session flipping a task to private and a session inserting a plaintext child can
    each pass their own trigger check and still leave a plaintext item under a private
    task. The write path closes that window with ``SELECT ... FOR UPDATE`` on the
    parent (spec §2.5); this test reproduces the break without it and the hold with it.
    """

    async def without_lock_reproduces_the_break():
        setup = await asyncpg.connect(pg_dsn)
        a = await asyncpg.connect(pg_dsn)
        b = await asyncpg.connect(pg_dsn)
        task_id = None
        try:
            task_id = await _create_task(setup, title=CIPHER_TITLE, is_private=False)

            # A flips to private (no plaintext children yet) but does not commit.
            ta = a.transaction()
            await ta.start()
            await a.execute("UPDATE microsched.task SET is_private = true WHERE id = $1", task_id)

            # B, on its own snapshot, still sees a public task and inserts plaintext.
            # Its FK insert takes only FOR KEY SHARE on the parent, which does not
            # conflict with A's FOR NO KEY UPDATE, so nothing makes B wait.
            tb = b.transaction()
            await tb.start()
            await b.execute(
                "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                task_id,
                "leaked plaintext",
            )

            await ta.commit()
            await tb.commit()

            is_private = await setup.fetchval(
                "SELECT is_private FROM microsched.task WHERE id = $1", task_id
            )
            leaked = await _plaintext_item_count(setup, task_id)
            # The invariant is violated: this is the gap the row lock has to close.
            assert is_private is True
            assert leaked == 1
        finally:
            await _delete_task(setup, task_id)
            await a.close()
            await b.close()
            await setup.close()

    async def with_lock_holds_the_invariant():
        setup = await asyncpg.connect(pg_dsn)
        a = await asyncpg.connect(pg_dsn)
        b = await asyncpg.connect(pg_dsn)
        monitor = await asyncpg.connect(pg_dsn)
        task_id = None
        b_task = None
        try:
            task_id = await _create_task(setup, title=CIPHER_TITLE, is_private=False)
            b_pid = await b.fetchval("SELECT pg_backend_pid()")

            # A opens the write path with FOR UPDATE, then flips to private.
            await a.execute("BEGIN")
            await a.fetchrow("SELECT id FROM microsched.task WHERE id = $1 FOR UPDATE", task_id)
            await a.execute("UPDATE microsched.task SET is_private = true WHERE id = $1", task_id)

            # B's write path also opens with FOR UPDATE, which now conflicts with A and
            # blocks until A commits - so by the time B inserts, the flip is visible.
            await b.execute("BEGIN")

            async def b_locks_then_inserts():
                await b.fetchrow("SELECT id FROM microsched.task WHERE id = $1 FOR UPDATE", task_id)
                await b.execute(
                    "INSERT INTO microsched.task_item (task_id, content) VALUES ($1, $2)",
                    task_id,
                    "would-be plaintext",
                )

            b_task = asyncio.create_task(b_locks_then_inserts())
            await _wait_until_blocked(monitor, b_pid)
            await a.execute("COMMIT")

            # wait_for so a regressed (dropped) trigger fails loud instead of hanging the
            # suite: if B's insert is wrongly allowed, this returns and raises-check fails.
            with pytest.raises(asyncpg.exceptions.RaiseError, match=ITEM_REJECT):
                await asyncio.wait_for(b_task, timeout=10.0)

            assert await _plaintext_item_count(setup, task_id) == 0
        finally:
            # Order matters: cancel B and close its connection (releasing any FOR UPDATE
            # lock) BEFORE setup deletes the row. A failed raises-check above skips a
            # normal rollback, so deleting first would block on B's lock forever.
            if b_task is not None:
                b_task.cancel()
                with contextlib.suppress(BaseException):
                    await b_task
            await a.close()
            await b.close()
            await monitor.close()
            await _delete_task(setup, task_id)
            await setup.close()

    async def scenario():
        await without_lock_reproduces_the_break()
        await with_lock_holds_the_invariant()

    asyncio.run(scenario())


# --- Migration reversibility (case 7) -----------------------------------------------


async def _trigger_names(dsn: str) -> set[str]:
    """Return which of our two triggers currently exist in the schema."""
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT t.tgname
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'microsched'
              AND t.tgname IN ('trg_task_item_privacy', 'trg_task_children_privacy')
            """
        )
        return {row["tgname"] for row in rows}
    finally:
        await conn.close()


def test_migration_0003_round_trip_drops_and_recreates_triggers(pg_dsn):
    """Case 7: 0003 downgrade removes both triggers; upgrade puts them back.

    Driven through NEON_MIGRATOR_URL (the same env var pg_dsn required), so the whole
    round-trip runs against the ephemeral CI service, never a real database. The
    finally clause always returns the schema to head, whatever the assertions do.
    """
    from alembic.config import Config

    from alembic import command

    both = {"trg_task_item_privacy", "trg_task_children_privacy"}
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.downgrade(config, "0002")
        assert asyncio.run(_trigger_names(pg_dsn)) == set()
        command.upgrade(config, "head")
        assert asyncio.run(_trigger_names(pg_dsn)) == both
    finally:
        command.upgrade(config, "head")
