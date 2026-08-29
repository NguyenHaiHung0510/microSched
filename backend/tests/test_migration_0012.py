"""Disposable-Postgres receipts for tracker reminder batch migration 0012."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy.exc import DBAPIError

from alembic import command

pytestmark = pytest.mark.pg


def _config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def test_0012_catalog_constraints_triggers_owner_and_grants(pg_dsn: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            tables = await conn.fetch(
                """
                SELECT tablename, tableowner FROM pg_tables
                WHERE schemaname = 'microsched'
                  AND tablename IN ('tracker_reminder_batch', 'tracker_reminder_batch_item')
                ORDER BY tablename
                """
            )
            assert [(row["tablename"], row["tableowner"]) for row in tables] == [
                ("tracker_reminder_batch", "microsched_migrator"),
                ("tracker_reminder_batch_item", "microsched_migrator"),
            ]
            constraints = {
                row["conname"]
                for row in await conn.fetch(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE connamespace = 'microsched'::regnamespace
                      AND conrelid IN (
                        'microsched.tracker'::regclass,
                        'microsched.reminder_dispatch'::regclass,
                        'microsched.tracker_reminder_batch'::regclass,
                        'microsched.tracker_reminder_batch_item'::regclass
                      )
                    """
                )
            }
            assert {
                "ck_tracker_reminder_time_whole_second",
                "ck_tracker_reminder_batch_time_whole_second",
                "ck_tracker_reminder_batch_attempt_count",
                "uq_tracker_reminder_batch_occurrence_time_generation",
                "uq_tracker_reminder_batch_item_dispatch_id",
                "fk_tracker_reminder_batch_item_batch_id",
                "fk_tracker_reminder_batch_item_dispatch_id",
            } <= constraints
            triggers = await conn.fetchval(
                """
                SELECT count(*) FROM pg_trigger
                WHERE NOT tgisinternal AND tgname = 'set_updated_at'
                  AND tgrelid IN (
                    'microsched.tracker_reminder_batch'::regclass,
                    'microsched.tracker_reminder_batch_item'::regclass
                  )
                """
            )
            assert triggers == 2
            app_grants = await conn.fetchval(
                """
                SELECT count(*) FROM information_schema.role_table_grants
                WHERE grantee = 'microsched_app' AND table_schema = 'microsched'
                  AND table_name IN ('tracker_reminder_batch', 'tracker_reminder_batch_item')
                  AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
                """
            )
            assert app_grants == 8
            public_grants = await conn.fetchval(
                """
                SELECT count(*) FROM information_schema.role_table_grants
                WHERE grantee = 'PUBLIC' AND table_schema = 'microsched'
                  AND table_name IN ('tracker_reminder_batch', 'tracker_reminder_batch_item')
                """
            )
            assert public_grants == 0
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_0012_direct_sql_fractional_seconds_fail(pg_dsn: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    """
                    INSERT INTO microsched.tracker
                        (name, kind, input_mode, reminder_time, reminder_mode,
                         reminder_interval_days, reminder_action)
                    VALUES ('enc:v1:fixture', 'general', 'event', TIME '08:00:00.1',
                            'fixed', 1, 'open_tracker')
                    """
                )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    """
                    INSERT INTO microsched.tracker_reminder_batch
                        (occurrence_on, reminder_time)
                    VALUES (CURRENT_DATE, TIME '08:00:00.1')
                    """
                )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_0012_application_role_has_crud_but_not_ddl() -> None:
    """The CI application URL proves the role split, not only catalog ACL text."""

    async def scenario() -> None:
        conn = await asyncpg.connect(os.environ["CI_APP_DATABASE_URL"])
        try:
            transaction = conn.transaction()
            await transaction.start()
            batch_id = await conn.fetchval(
                """
                INSERT INTO microsched.tracker_reminder_batch
                    (occurrence_on, reminder_time)
                VALUES (DATE '2099-12-31', TIME '23:59:59') RETURNING id
                """
            )
            await conn.execute(
                "UPDATE microsched.tracker_reminder_batch SET status='cancelled' WHERE id=$1",
                batch_id,
            )
            assert (
                await conn.fetchval(
                    "SELECT status FROM microsched.tracker_reminder_batch WHERE id=$1", batch_id
                )
                == "cancelled"
            )
            await conn.execute(
                "DELETE FROM microsched.tracker_reminder_batch WHERE id=$1", batch_id
            )
            await transaction.rollback()

            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("CREATE TABLE microsched.app_role_must_not_ddl (id integer)")
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_0012_downgrade_nonempty_fails_before_ddl(pg_dsn: str) -> None:
    async def seed() -> object:
        conn = await asyncpg.connect(pg_dsn)
        try:
            return await conn.fetchval(
                """
                INSERT INTO microsched.tracker_reminder_batch
                    (occurrence_on, reminder_time)
                VALUES (CURRENT_DATE, TIME '08:00:00') RETURNING id
                """
            )
        finally:
            await conn.close()

    async def cleanup(batch_id: object) -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute(
                "DELETE FROM microsched.tracker_reminder_batch WHERE id = $1", batch_id
            )
        finally:
            await conn.close()

    batch_id = asyncio.run(seed())
    try:
        with pytest.raises(DBAPIError, match="batching or terminal data would be lost"):
            command.downgrade(_config(), "0011")

        async def assert_unchanged() -> None:
            conn = await asyncpg.connect(pg_dsn)
            try:
                assert await conn.fetchval(
                    "SELECT to_regclass('microsched.tracker_reminder_batch')"
                )
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM microsched.tracker_reminder_batch WHERE id = $1",
                        batch_id,
                    )
                    == 1
                )
            finally:
                await conn.close()

        asyncio.run(assert_unchanged())
    finally:
        asyncio.run(cleanup(batch_id))
        command.upgrade(_config(), "head")


@pytest.mark.parametrize("terminal_status", ["cancelled", "exhausted"])
def test_0012_downgrade_terminal_dispatch_fails_before_ddl(
    pg_dsn: str, terminal_status: str
) -> None:
    """A lone widened terminal dispatch blocks downgrade with zero catalog drift."""

    dispatch_id = uuid4()

    async def seed_and_snapshot() -> dict[str, object]:
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute(
                """
                INSERT INTO microsched.reminder_dispatch
                    (id, subject_type, subject_id, dispatched_on, status,
                     attempt_count, created_at)
                VALUES ($1, 'tracker', $2, DATE '2026-09-07', $3, 0, NOW())
                """,
                dispatch_id,
                uuid4(),
                terminal_status,
            )
            return await catalog_snapshot(conn)
        finally:
            await conn.close()

    async def catalog_snapshot(conn: asyncpg.Connection) -> dict[str, object]:
        return {
            "revision": await conn.fetchval("SELECT version_num FROM microsched.alembic_version"),
            "batch_table": str(
                await conn.fetchval("SELECT to_regclass('microsched.tracker_reminder_batch')")
            ),
            "item_table": str(
                await conn.fetchval("SELECT to_regclass('microsched.tracker_reminder_batch_item')")
            ),
            "tracker_whole_second": await conn.fetchval(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'microsched.tracker'::regclass
                  AND conname = 'ck_tracker_reminder_time_whole_second'
                """
            ),
            "dispatch_status_check": await conn.fetchval(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'microsched.reminder_dispatch'::regclass
                  AND conname = 'ck_reminder_dispatch_status'
                """
            ),
            "dispatch_row": tuple(
                await conn.fetchrow(
                    """
                    SELECT id, status, attempt_count
                    FROM microsched.reminder_dispatch
                    WHERE id = $1
                    """,
                    dispatch_id,
                )
            ),
        }

    async def read_snapshot() -> dict[str, object]:
        conn = await asyncpg.connect(pg_dsn)
        try:
            return await catalog_snapshot(conn)
        finally:
            await conn.close()

    async def cleanup() -> None:
        conn = await asyncpg.connect(pg_dsn)
        try:
            await conn.execute(
                "DELETE FROM microsched.reminder_dispatch WHERE id = $1", dispatch_id
            )
        finally:
            await conn.close()

    before = asyncio.run(seed_and_snapshot())
    try:
        with pytest.raises(DBAPIError) as exc_info:
            command.downgrade(_config(), "0011")
        assert getattr(exc_info.value.orig, "sqlstate", None) == "23514"
        assert "batching or terminal data would be lost" in str(exc_info.value)
        assert asyncio.run(read_snapshot()) == before
    finally:
        asyncio.run(cleanup())
        command.upgrade(_config(), "head")


def test_0012_empty_downgrade_catalog_then_upgrade(pg_dsn: str) -> None:
    config = _config()
    try:
        command.downgrade(config, "0011")

        async def assert_0011() -> None:
            conn = await asyncpg.connect(pg_dsn)
            try:
                assert (
                    await conn.fetchval("SELECT to_regclass('microsched.tracker_reminder_batch')")
                    is None
                )
                assert (
                    await conn.fetchval(
                        """
                    SELECT count(*) FROM pg_constraint
                    WHERE connamespace = 'microsched'::regnamespace
                      AND conname = 'ck_tracker_reminder_time_whole_second'
                    """
                    )
                    == 0
                )
                dispatch_check = await conn.fetchval(
                    """
                    SELECT pg_get_constraintdef(oid) FROM pg_constraint
                    WHERE conrelid = 'microsched.reminder_dispatch'::regclass
                      AND conname = 'ck_reminder_dispatch_status'
                    """
                )
                assert "cancelled" not in dispatch_check
                assert "exhausted" not in dispatch_check
            finally:
                await conn.close()

        asyncio.run(assert_0011())
    finally:
        command.upgrade(config, "head")
