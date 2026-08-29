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
        async def rows(query: str, *args: object) -> tuple[tuple[object, ...], ...]:
            return tuple(tuple(row) for row in await conn.fetch(query, *args))

        return {
            "revision": await conn.fetchval("SELECT version_num FROM microsched.alembic_version"),
            "relations": await rows(
                """
                WITH target_tables AS (
                    SELECT c.oid
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'microsched'
                      AND c.relname IN (
                        'tracker', 'reminder_dispatch',
                        'tracker_reminder_batch', 'tracker_reminder_batch_item'
                      )
                      AND c.relkind IN ('r', 'p')
                ),
                target_sequences AS (
                    SELECT DISTINCT sequence.oid
                    FROM pg_class AS sequence
                    JOIN pg_namespace AS n ON n.oid = sequence.relnamespace
                    JOIN pg_depend AS dependency
                      ON dependency.classid = 'pg_class'::regclass
                     AND dependency.objid = sequence.oid
                     AND dependency.refclassid = 'pg_class'::regclass
                    WHERE n.nspname = 'microsched'
                      AND sequence.relkind = 'S'
                      AND dependency.refobjid IN (SELECT oid FROM target_tables)
                      AND dependency.deptype IN ('a', 'i')
                ),
                target_relations AS (
                    SELECT oid FROM target_tables
                    UNION
                    SELECT oid FROM target_sequences
                )
                SELECT n.nspname, c.relname, c.relkind::text, c.relpersistence::text
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE c.oid IN (SELECT oid FROM target_relations)
                ORDER BY n.nspname, c.relname
                """
            ),
            "sequence_properties": await rows(
                """
                WITH target_tables AS (
                    SELECT c.oid
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'microsched'
                      AND c.relname IN (
                        'tracker', 'reminder_dispatch',
                        'tracker_reminder_batch', 'tracker_reminder_batch_item'
                      )
                      AND c.relkind IN ('r', 'p')
                )
                SELECT n.nspname, c.relname, format_type(s.seqtypid, NULL),
                       s.seqstart, s.seqincrement, s.seqmax, s.seqmin,
                       s.seqcache, s.seqcycle
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_sequence AS s ON s.seqrelid = c.oid
                JOIN pg_depend AS dependency
                  ON dependency.classid = 'pg_class'::regclass
                 AND dependency.objid = c.oid
                 AND dependency.refclassid = 'pg_class'::regclass
                WHERE n.nspname = 'microsched'
                  AND c.relkind = 'S'
                  AND dependency.refobjid IN (SELECT oid FROM target_tables)
                  AND dependency.deptype IN ('a', 'i')
                ORDER BY n.nspname, c.relname
                """
            ),
            "columns": await rows(
                """
                SELECT n.nspname, c.relname, a.attnum, a.attname,
                       format_type(a.atttypid, a.atttypmod), a.attnotnull,
                       pg_get_expr(d.adbin, d.adrelid),
                       a.attidentity::text, a.attgenerated::text
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_attribute AS a ON a.attrelid = c.oid
                LEFT JOIN pg_attrdef AS d
                  ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE n.nspname = 'microsched'
                  AND c.relname IN (
                    'tracker', 'reminder_dispatch',
                    'tracker_reminder_batch', 'tracker_reminder_batch_item'
                  )
                  AND c.relkind IN ('r', 'p')
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY n.nspname, c.relname, a.attnum
                """
            ),
            "constraints": await rows(
                """
                SELECT n.nspname, c.relname, constraint_row.conname,
                       constraint_row.contype::text, constraint_row.convalidated,
                       constraint_row.condeferrable, constraint_row.condeferred,
                       pg_get_constraintdef(constraint_row.oid, true)
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS c ON c.oid = constraint_row.conrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'microsched'
                  AND c.relname IN (
                    'tracker', 'reminder_dispatch',
                    'tracker_reminder_batch', 'tracker_reminder_batch_item'
                  )
                ORDER BY n.nspname, c.relname, constraint_row.conname
                """
            ),
            "indexes": await rows(
                """
                SELECT n.nspname, table_row.relname, index_row.relname,
                       index_catalog.indisunique, index_catalog.indisprimary,
                       index_catalog.indisvalid, index_catalog.indisready,
                       index_catalog.indislive,
                       pg_get_indexdef(index_row.oid)
                FROM pg_index AS index_catalog
                JOIN pg_class AS table_row ON table_row.oid = index_catalog.indrelid
                JOIN pg_class AS index_row ON index_row.oid = index_catalog.indexrelid
                JOIN pg_namespace AS n ON n.oid = table_row.relnamespace
                WHERE n.nspname = 'microsched'
                  AND table_row.relname IN (
                    'tracker', 'reminder_dispatch',
                    'tracker_reminder_batch', 'tracker_reminder_batch_item'
                  )
                ORDER BY n.nspname, table_row.relname, index_row.relname
                """
            ),
            "triggers": await rows(
                """
                SELECT n.nspname, c.relname, trigger_row.tgname,
                       trigger_row.tgenabled::text,
                       pg_get_triggerdef(trigger_row.oid, true)
                FROM pg_trigger AS trigger_row
                JOIN pg_class AS c ON c.oid = trigger_row.tgrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'microsched'
                  AND c.relname IN (
                    'tracker', 'reminder_dispatch',
                    'tracker_reminder_batch', 'tracker_reminder_batch_item'
                  )
                  AND NOT trigger_row.tgisinternal
                ORDER BY n.nspname, c.relname, trigger_row.tgname
                """
            ),
            "owners": await rows(
                """
                WITH target_tables AS (
                    SELECT c.oid
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'microsched'
                      AND c.relname IN (
                        'tracker', 'reminder_dispatch',
                        'tracker_reminder_batch', 'tracker_reminder_batch_item'
                      )
                      AND c.relkind IN ('r', 'p')
                ),
                target_relations AS (
                    SELECT oid FROM target_tables
                    UNION
                    SELECT DISTINCT sequence.oid
                    FROM pg_class AS sequence
                    JOIN pg_namespace AS n ON n.oid = sequence.relnamespace
                    JOIN pg_depend AS dependency
                      ON dependency.classid = 'pg_class'::regclass
                     AND dependency.objid = sequence.oid
                     AND dependency.refclassid = 'pg_class'::regclass
                    WHERE n.nspname = 'microsched'
                      AND sequence.relkind = 'S'
                      AND dependency.refobjid IN (SELECT oid FROM target_tables)
                      AND dependency.deptype IN ('a', 'i')
                )
                SELECT n.nspname, c.relname, c.relkind::text,
                       pg_get_userbyid(c.relowner)
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE c.oid IN (SELECT oid FROM target_relations)
                ORDER BY n.nspname, c.relname
                """
            ),
            "relation_acls": await rows(
                """
                WITH target_tables AS (
                    SELECT c.oid
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'microsched'
                      AND c.relname IN (
                        'tracker', 'reminder_dispatch',
                        'tracker_reminder_batch', 'tracker_reminder_batch_item'
                      )
                      AND c.relkind IN ('r', 'p')
                ),
                target_relations AS (
                    SELECT oid FROM target_tables
                    UNION
                    SELECT DISTINCT sequence.oid
                    FROM pg_class AS sequence
                    JOIN pg_namespace AS n ON n.oid = sequence.relnamespace
                    JOIN pg_depend AS dependency
                      ON dependency.classid = 'pg_class'::regclass
                     AND dependency.objid = sequence.oid
                     AND dependency.refclassid = 'pg_class'::regclass
                    WHERE n.nspname = 'microsched'
                      AND sequence.relkind = 'S'
                      AND dependency.refobjid IN (SELECT oid FROM target_tables)
                      AND dependency.deptype IN ('a', 'i')
                )
                SELECT n.nspname, c.relname, c.relkind::text, c.relacl::text
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE c.oid IN (SELECT oid FROM target_relations)
                ORDER BY n.nspname, c.relname
                """
            ),
            "table_grants": await rows(
                """
                WITH target_tables AS (
                    SELECT c.oid
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'microsched'
                      AND c.relname IN (
                        'tracker', 'reminder_dispatch',
                        'tracker_reminder_batch', 'tracker_reminder_batch_item'
                      )
                      AND c.relkind IN ('r', 'p')
                ),
                target_relations AS (
                    SELECT oid FROM target_tables
                    UNION
                    SELECT DISTINCT sequence.oid
                    FROM pg_class AS sequence
                    JOIN pg_namespace AS n ON n.oid = sequence.relnamespace
                    JOIN pg_depend AS dependency
                      ON dependency.classid = 'pg_class'::regclass
                     AND dependency.objid = sequence.oid
                     AND dependency.refclassid = 'pg_class'::regclass
                    WHERE n.nspname = 'microsched'
                      AND sequence.relkind = 'S'
                      AND dependency.refobjid IN (SELECT oid FROM target_tables)
                      AND dependency.deptype IN ('a', 'i')
                )
                SELECT n.nspname, c.relname,
                       pg_get_userbyid(grant_row.grantor),
                       CASE WHEN grant_row.grantee = 0 THEN 'PUBLIC'
                            ELSE pg_get_userbyid(grant_row.grantee) END,
                       grant_row.privilege_type, grant_row.is_grantable
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                CROSS JOIN LATERAL aclexplode(
                    COALESCE(
                        c.relacl,
                        acldefault(
                            (CASE WHEN c.relkind = 'S' THEN 'S' ELSE 'r' END)::"char",
                            c.relowner
                        )
                    )
                ) AS grant_row
                WHERE c.oid IN (SELECT oid FROM target_relations)
                ORDER BY n.nspname, c.relname, 4, 5, 3
                """
            ),
            "column_acls": await rows(
                """
                SELECT n.nspname, c.relname, a.attnum, a.attname, a.attacl::text
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_attribute AS a ON a.attrelid = c.oid
                WHERE n.nspname = 'microsched'
                  AND c.relname IN (
                    'tracker', 'reminder_dispatch',
                    'tracker_reminder_batch', 'tracker_reminder_batch_item'
                  )
                  AND c.relkind IN ('r', 'p')
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY n.nspname, c.relname, a.attnum
                """
            ),
            "column_grants": await rows(
                """
                SELECT n.nspname, c.relname, a.attnum, a.attname,
                       pg_get_userbyid(grant_row.grantor),
                       CASE WHEN grant_row.grantee = 0 THEN 'PUBLIC'
                            ELSE pg_get_userbyid(grant_row.grantee) END,
                       grant_row.privilege_type, grant_row.is_grantable
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_attribute AS a ON a.attrelid = c.oid
                CROSS JOIN LATERAL aclexplode(a.attacl) AS grant_row
                WHERE n.nspname = 'microsched'
                  AND c.relname IN (
                    'tracker', 'reminder_dispatch',
                    'tracker_reminder_batch', 'tracker_reminder_batch_item'
                  )
                  AND c.relkind IN ('r', 'p')
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY n.nspname, c.relname, a.attnum, 6, 7, 5
                """
            ),
            "default_acls": await rows(
                """
                WITH target_owners AS (
                    SELECT DISTINCT c.relowner
                    FROM pg_class AS c
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'microsched'
                      AND c.relname IN (
                        'tracker', 'reminder_dispatch',
                        'tracker_reminder_batch', 'tracker_reminder_batch_item'
                      )
                      AND c.relkind IN ('r', 'p')
                )
                SELECT pg_get_userbyid(default_row.defaclrole),
                       COALESCE(n.nspname, ''), default_row.defaclobjtype::text,
                       default_row.defaclacl::text,
                       pg_get_userbyid(grant_row.grantor),
                       CASE WHEN grant_row.grantee = 0 THEN 'PUBLIC'
                            ELSE pg_get_userbyid(grant_row.grantee) END,
                       grant_row.privilege_type, grant_row.is_grantable
                FROM pg_default_acl AS default_row
                LEFT JOIN pg_namespace AS n ON n.oid = default_row.defaclnamespace
                LEFT JOIN LATERAL aclexplode(default_row.defaclacl) AS grant_row ON true
                WHERE default_row.defaclrole IN (SELECT relowner FROM target_owners)
                  AND (default_row.defaclnamespace = 0 OR n.nspname = 'microsched')
                  AND default_row.defaclobjtype IN ('r', 'S')
                ORDER BY 1, 2, 3, 6, 7, 5
                """
            ),
            "dispatch_rows": await rows(
                """
                SELECT id, subject_type, subject_id, dispatched_on, status,
                       attempt_count, last_attempt_at, confirmed_entry_id,
                       confirmed_at, created_at, updated_at
                FROM microsched.reminder_dispatch
                WHERE id = $1
                ORDER BY id
                """,
                dispatch_id,
            ),
            "batch_rows": await rows(
                """
                SELECT id, occurrence_on, reminder_time, generation, status,
                       attempt_count, last_attempt_at, created_at, updated_at
                FROM microsched.tracker_reminder_batch
                ORDER BY id
                """
            ),
            "batch_item_rows": await rows(
                """
                SELECT id, batch_id, dispatch_id, reminder_mode,
                       reminder_interval_days, reminder_action, input_mode,
                       state, created_at, updated_at
                FROM microsched.tracker_reminder_batch_item
                ORDER BY id
                """
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

    try:
        before = asyncio.run(seed_and_snapshot())
        assert tuple(row[1] for row in before["relations"] if row[2] in {"r", "p"}) == (
            "reminder_dispatch",
            "tracker",
            "tracker_reminder_batch",
            "tracker_reminder_batch_item",
        )
        assert tuple(before) == (
            "revision",
            "relations",
            "sequence_properties",
            "columns",
            "constraints",
            "indexes",
            "triggers",
            "owners",
            "relation_acls",
            "table_grants",
            "column_acls",
            "column_grants",
            "default_acls",
            "dispatch_rows",
            "batch_rows",
            "batch_item_rows",
        )
        with pytest.raises(DBAPIError) as exc_info:
            command.downgrade(_config(), "0011")
        assert getattr(exc_info.value.orig, "sqlstate", None) == "23514"
        driver_error = exc_info.value.orig.__cause__
        assert driver_error is not None
        assert str(driver_error) == (
            "cannot downgrade 0012: batching or terminal data would be lost"
        )
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
