"""Throwaway-Postgres receipts for the 026A expand/compatibility phase."""

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.core.database_urls import async_postgres_url
from app.domain.models import AuthSession, Task
from app.domain.tasks import TaskCreate, TaskStore, TaskUpdate

pytestmark = pytest.mark.pg


async def _delete_tasks(conn: asyncpg.Connection, ids: list) -> None:
    if ids:
        await conn.execute("DELETE FROM microsched.task WHERE id = ANY($1::uuid[])", ids)


def test_expand_upgrade_backfills_every_legacy_row_without_reclassifying_2359(pg_dsn):
    async def seed_legacy_rows() -> list:
        conn = await asyncpg.connect(pg_dsn)
        try:
            assert await conn.fetchval("SELECT count(*) FROM microsched.task") == 0
            undated = await conn.fetchval(
                "INSERT INTO microsched.task (title, due_at) VALUES ('legacy-none', NULL) "
                "RETURNING id"
            )
            exact_2359 = datetime(2026, 8, 24, 16, 59, tzinfo=UTC)
            timed = await conn.fetchval(
                """
                INSERT INTO microsched.task
                    (title, due_at, is_private, completed_at, deleted_at)
                VALUES ('enc:v1:dGVzdA==', $1, true, $2, $2)
                RETURNING id
                """,
                exact_2359,
                datetime(2026, 8, 25, 1, 0, tzinfo=UTC),
            )
            return [undated, timed]
        finally:
            await conn.close()

    async def assert_backfill(ids: list) -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            rows = await conn.fetch(
                """
                SELECT id, due_precision, due_on, due_at, is_private,
                       completed_at IS NOT NULL AS completed,
                       deleted_at IS NOT NULL AS deleted
                FROM microsched.task
                WHERE id = ANY($1::uuid[])
                ORDER BY due_at NULLS FIRST
                """,
                ids,
            )
            assert len(rows) == 2
            assert tuple(rows[0][key] for key in ("due_precision", "due_on", "due_at")) == (
                "none",
                None,
                None,
            )
            assert tuple(rows[1][key] for key in ("due_precision", "due_on")) == (
                "datetime",
                None,
            )
            assert rows[1]["due_at"] == datetime(2026, 8, 24, 16, 59, tzinfo=UTC)
            assert rows[1]["is_private"] is True
            assert rows[1]["completed"] is True
            assert rows[1]["deleted"] is True
        finally:
            await _delete_tasks(conn, ids)
            await conn.close()

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    ids: list = []
    try:
        command.downgrade(config, "0009")
        ids = asyncio.run(seed_legacy_rows())
        command.upgrade(config, "head")
        asyncio.run(assert_backfill(ids))
        ids = []
    finally:
        command.upgrade(config, "head")
        if ids:

            async def cleanup() -> None:
                conn = await asyncpg.connect(pg_dsn)
                try:
                    await _delete_tasks(conn, ids)
                finally:
                    await conn.close()

            asyncio.run(cleanup())


def test_expand_catalog_and_legacy_writer_trigger_matrix(pg_dsn):
    async def scenario() -> None:
        conn = await asyncpg.connect(pg_dsn)
        task_ids = []
        try:
            columns = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'microsched'
                  AND table_name = 'task'
                  AND column_name IN ('due_precision', 'due_on', 'due_at')
                ORDER BY column_name
                """
            )
            assert [tuple(row.values()) for row in columns] == [
                ("due_at", "timestamp with time zone", "YES"),
                ("due_on", "date", "YES"),
                ("due_precision", "text", "YES"),
            ]
            index = await conn.fetchval(
                """
                SELECT indexdef FROM pg_indexes
                WHERE schemaname = 'microsched' AND indexname = 'ix_task_due_on'
                """
            )
            assert index == "CREATE INDEX ix_task_due_on ON microsched.task USING btree (due_on)"
            triggers = await conn.fetch(
                """
                SELECT t.tgname, pg_get_triggerdef(t.oid) AS definition
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'microsched'
                  AND t.tgname IN (
                    'trg_task_due_legacy_insert_v1',
                    'trg_task_due_legacy_update_v1'
                  )
                ORDER BY t.tgname
                """
            )
            assert [row["tgname"] for row in triggers] == [
                "trg_task_due_legacy_insert_v1",
                "trg_task_due_legacy_update_v1",
            ]
            assert "BEFORE INSERT" in triggers[0]["definition"]
            assert "BEFORE UPDATE OF due_at" in triggers[1]["definition"]

            undated = await conn.fetchrow(
                "INSERT INTO microsched.task (title, due_at) VALUES ('legacy-none', NULL) "
                "RETURNING id, due_precision, due_on, due_at"
            )
            task_ids.append(undated["id"])
            assert (undated["due_precision"], undated["due_on"], undated["due_at"]) == (
                "none",
                None,
                None,
            )
            instant = datetime(2026, 8, 24, 2, 30, tzinfo=UTC)
            timed = await conn.fetchrow(
                "INSERT INTO microsched.task (title, due_at) VALUES ('legacy-time', $1) "
                "RETURNING id, due_precision, due_on, due_at",
                instant,
            )
            task_ids.append(timed["id"])
            assert (timed["due_precision"], timed["due_on"], timed["due_at"]) == (
                "datetime",
                None,
                instant,
            )

            transaction = conn.transaction()
            await transaction.start()
            try:
                await conn.execute("SELECT set_config('microsched.task_due_writer', 'v2', true)")
                civil = await conn.fetchrow(
                    """
                    INSERT INTO microsched.task (title, due_precision, due_on, due_at)
                    VALUES ('v2-date', 'date', $1, NULL)
                    RETURNING id, due_precision, due_on, due_at
                    """,
                    date(2026, 8, 24),
                )
                task_ids.append(civil["id"])
                assert (civil["due_precision"], civil["due_on"], civil["due_at"]) == (
                    "date",
                    date(2026, 8, 24),
                    None,
                )

                await conn.execute(
                    "UPDATE microsched.task SET title = 'v2-date-renamed' WHERE id = $1",
                    civil["id"],
                )
                preserved = await conn.fetchrow(
                    "SELECT due_precision, due_on, due_at FROM microsched.task WHERE id = $1",
                    civil["id"],
                )
                assert tuple(preserved.values()) == ("date", date(2026, 8, 24), None)
                await transaction.commit()
            except Exception:
                await transaction.rollback()
                raise

            # Ending the transaction clears the LOCAL V2 marker even if the pool
            # later hands the exact same physical connection to an old binary.
            legacy_reuse = await conn.fetchrow(
                "UPDATE microsched.task SET due_at = NULL WHERE id = $1 "
                "RETURNING due_precision, due_on, due_at",
                civil["id"],
            )
            assert tuple(legacy_reuse.values()) == ("none", None, None)
        finally:
            await _delete_tasks(conn, task_ids)
            await conn.close()

    asyncio.run(scenario())


def test_store_dual_writes_and_non_temporal_patch_preserves_full_schedule(pg_dsn):
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = TaskStore()
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash="temporal-precision-pg",
            user_email="owner@example.test",
            last_seen_at=now,
            expires_at=now,
        )
        created_ids = []
        try:
            conn = await asyncpg.connect(pg_dsn)
            try:
                transaction = conn.transaction()
                await transaction.start()
                await conn.execute("SELECT set_config('microsched.task_due_writer', 'v2', true)")
                legacy_patch_id = await conn.fetchval(
                    "INSERT INTO microsched.task (title, due_precision, due_on, due_at) "
                    "VALUES ('legacy-null-patch', NULL, NULL, $1) RETURNING id",
                    datetime(2026, 8, 23, 2, 30, tzinfo=UTC),
                )
                legacy_restore_id = await conn.fetchval(
                    "INSERT INTO microsched.task "
                    "(title, due_precision, due_on, due_at, deleted_at) "
                    "VALUES ('legacy-null-restore', NULL, NULL, NULL, $1) RETURNING id",
                    now,
                )
                legacy_delete_id = await conn.fetchval(
                    "INSERT INTO microsched.task (title, due_precision, due_on, due_at) "
                    "VALUES ('legacy-null-delete', NULL, NULL, NULL) RETURNING id"
                )
                await transaction.commit()
                created_ids.extend((legacy_patch_id, legacy_restore_id, legacy_delete_id))
            finally:
                await conn.close()

            async with maker() as db:
                civil = await store.create(
                    db,
                    auth,
                    TaskCreate(
                        title="civil",
                        due_precision="date",
                        due_on=date(2026, 8, 24),
                    ),
                )
                created_ids.append(civil.id)
                await db.commit()
            async with maker() as db:
                renamed = await store.update(db, auth, civil.id, TaskUpdate(title="renamed"))
                assert renamed is not None
                assert (renamed.due_precision, renamed.due_on, renamed.due_at) == (
                    "date",
                    date(2026, 8, 24),
                    None,
                )
                await db.commit()
            async with maker() as db:
                changed = await store.update(
                    db,
                    auth,
                    civil.id,
                    TaskUpdate(
                        due_precision="datetime",
                        due_at=datetime(2026, 8, 24, 2, 30, tzinfo=UTC),
                    ),
                )
                assert changed is not None
                assert (changed.due_precision, changed.due_on, changed.due_at) == (
                    "datetime",
                    None,
                    datetime(2026, 8, 24, 2, 30, tzinfo=UTC),
                )
                await db.commit()
            async with maker() as db:
                legacy_patched = await store.update(
                    db,
                    auth,
                    legacy_patch_id,
                    TaskUpdate(title="legacy-canonical"),
                )
                assert legacy_patched is not None
                assert (
                    legacy_patched.due_precision,
                    legacy_patched.due_on,
                    legacy_patched.due_at,
                ) == ("datetime", None, datetime(2026, 8, 23, 2, 30, tzinfo=UTC))
                restored = await store.restore(db, auth, legacy_restore_id)
                assert restored is not None
                assert await store.soft_delete(db, auth, legacy_delete_id)
                await db.commit()

            conn = await asyncpg.connect(pg_dsn)
            try:
                physical = await conn.fetch(
                    "SELECT id, due_precision, due_on, due_at, deleted_at "
                    "FROM microsched.task WHERE id = ANY($1::uuid[]) ORDER BY id",
                    [legacy_patch_id, legacy_restore_id, legacy_delete_id],
                )
                by_id = {row["id"]: row for row in physical}
                assert by_id[legacy_patch_id]["due_precision"] == "datetime"
                assert by_id[legacy_restore_id]["due_precision"] == "none"
                assert by_id[legacy_delete_id]["due_precision"] == "none"
                assert all(row["due_on"] is None for row in physical)
                assert by_id[legacy_restore_id]["deleted_at"] is None
                assert by_id[legacy_delete_id]["deleted_at"] is not None
            finally:
                await conn.close()
        finally:
            async with maker() as db:
                await db.execute(delete(Task).where(Task.id.in_(created_ids)))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


def test_expand_downgrade_refuses_to_discard_date_only_task(pg_dsn):
    async def insert_date() -> object:
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute("SELECT set_config('microsched.task_due_writer', 'v2', false)")
            return await conn.fetchval(
                """
                INSERT INTO microsched.task (title, due_precision, due_on, due_at)
                VALUES ('downgrade-guard', 'date', DATE '2026-08-24', NULL)
                RETURNING id
                """
            )
        finally:
            await conn.close()

    task_id = asyncio.run(insert_date())
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with pytest.raises(IntegrityError, match="date-only task scheduling would be lost"):
            command.downgrade(config, "0009")

        async def assert_intact() -> None:
            conn = await asyncpg.connect(pg_dsn)
            try:
                assert await conn.fetchval(
                    "SELECT due_on = DATE '2026-08-24' FROM microsched.task WHERE id = $1",
                    task_id,
                )
                assert (
                    await conn.fetchval("SELECT version_num FROM microsched.alembic_version")
                    == "0012"
                )
            finally:
                await conn.close()

        asyncio.run(assert_intact())
    finally:

        async def cleanup() -> None:
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute("DELETE FROM microsched.task WHERE id = $1", task_id)
            finally:
                await conn.close()

        asyncio.run(cleanup())
        command.upgrade(config, "head")
