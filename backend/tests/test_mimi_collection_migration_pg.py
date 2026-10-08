"""Disposable 0016->0017 populated upgrade, grants and loss-preventing fallback."""

import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from scripts.prepare_ci_database import prepare

pytestmark = pytest.mark.pg


def migrate(url, *args, expected=0):
    env = {
        **os.environ,
        "MIMI_P0_DISABLE_DOTENV": "1",
        "NEON_MIGRATOR_URL": url,
        "CI_MIGRATOR_URL": url,
    }
    run = subprocess.run(
        [sys.executable, "-m", "alembic", *args], env=env, capture_output=True, text=True
    )
    assert run.returncode == expected, run.stdout + run.stderr
    return run.stdout + run.stderr


def test_0017_populated_upgrade_catalog_grants_and_downgrade_refusal(pg_dsn):
    # Only this test's UUID-named database inside the caller's verified local PG.
    parsed = make_url(pg_dsn)
    assert parsed.host in {"127.0.0.1", "localhost", "::1"}
    name = "mimi086_migration_" + uuid4().hex[:12]
    admin = parsed.set(database="postgres").render_as_string(hide_password=False)
    bootstrap = parsed.set(database=name).render_as_string(hide_password=False)
    migrator = parsed.set(
        database=name, username="microsched_migrator", password="synthetic-migrator"
    ).render_as_string(hide_password=False)
    app = parsed.set(
        database=name, username="microsched_app", password="synthetic-app"
    ).render_as_string(hide_password=False)

    async def create():
        conn = await asyncpg.connect(admin)
        try:
            await conn.execute(f'CREATE DATABASE "{name}"')
        finally:
            await conn.close()
        await prepare(
            bootstrap_url=bootstrap,
            migrator_password="synthetic-migrator",
            app_password="synthetic-app",
        )

    asyncio.run(create())
    try:
        migrate(migrator, "upgrade", "0016")

        async def seed_baseline():
            conn = await asyncpg.connect(migrator)
            try:
                tid = await conn.fetchval(
                    "INSERT INTO microsched.task(title,body_md) "
                    "VALUES ('Synthetic baseline','Keep body') RETURNING id"
                )
                cid = await conn.fetchval(
                    "INSERT INTO microsched.task_item(task_id,content,position) "
                    "VALUES ($1,'Keep checklist',0) RETURNING id",
                    tid,
                )
                return tid, cid
            finally:
                await conn.close()

        tid, cid = asyncio.run(seed_baseline())
        migrate(migrator, "upgrade", "0017")

        async def audit():
            conn = await asyncpg.connect(migrator)
            try:
                assert (
                    await conn.fetchval("SELECT version_num FROM microsched.alembic_version")
                    == "0017"
                )
                row = await conn.fetchrow(
                    "SELECT title,body_md,collection_version FROM microsched.task WHERE id=$1", tid
                )
                assert dict(row) == {
                    "title": "Synthetic baseline",
                    "body_md": "Keep body",
                    "collection_version": 1,
                }
                assert await conn.fetchval(
                    "SELECT deleted_at IS NULL FROM microsched.task_item WHERE id=$1", cid
                )
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema='microsched' "
                        "AND table_name='mimi_evidence'"
                    )
                    == 1
                )
                for table in (
                    "mimi_device_preference",
                    "mimi_notification_intent",
                    "mimi_notification_delivery",
                ):
                    assert await conn.fetchval(
                        "SELECT has_table_privilege('microsched_app',$1,'SELECT,INSERT,UPDATE,"
                        "DELETE')",
                        f"microsched.{table}",
                    )
                    assert await conn.fetchval(
                        "SELECT tableowner='microsched_migrator' FROM pg_tables "
                        "WHERE schemaname='microsched' AND tablename=$1",
                        table,
                    )
                indexes = await conn.fetch(
                    "SELECT indexname FROM pg_indexes WHERE schemaname='microsched'"
                )
                assert {
                    "ix_task_item_active_position",
                    "ix_mimi_notification_intent_unread",
                    "ix_mimi_notification_delivery_pending",
                } <= {r["indexname"] for r in indexes}
                await conn.execute(
                    "UPDATE microsched.task_item SET content='changed' WHERE id=$1", cid
                )
                assert (
                    await conn.fetchval(
                        "SELECT collection_version FROM microsched.task WHERE id=$1", tid
                    )
                    > 1
                )
            finally:
                await conn.close()
            appconn = await asyncpg.connect(app)
            try:
                assert (
                    await appconn.fetchval("SELECT title FROM microsched.task WHERE id=$1", tid)
                    == "Synthetic baseline"
                )
                await appconn.execute(
                    "INSERT INTO microsched.mimi_device_preference(owner_id,subscription_id) "
                    "SELECT uuidv7(),id FROM microsched.push_subscription LIMIT 0"
                )
            finally:
                await appconn.close()

        asyncio.run(audit())

        async def tombstone():
            conn = await asyncpg.connect(migrator)
            try:
                await conn.execute(
                    "UPDATE microsched.task_item SET deleted_at=now() WHERE id=$1", cid
                )
            finally:
                await conn.close()

        asyncio.run(tombstone())
        output = migrate(migrator, "downgrade", "0016", expected=1)
        assert "refusing to drop Task/Mimi recovery" in output

        async def empty_recovery():
            conn = await asyncpg.connect(migrator)
            try:
                assert (
                    await conn.fetchval("SELECT version_num FROM microsched.alembic_version")
                    == "0017"
                )
                assert await conn.fetchval(
                    "SELECT deleted_at IS NOT NULL FROM microsched.task_item WHERE id=$1", cid
                )
                # Explicit synthetic test restoration, never live data cleanup.
                await conn.execute(
                    "UPDATE microsched.task_item SET deleted_at=NULL WHERE id=$1", cid
                )
            finally:
                await conn.close()

        asyncio.run(empty_recovery())
        migrate(migrator, "downgrade", "0016")
        migrate(migrator, "upgrade", "0017")
        asyncio.run(audit())
    finally:

        async def drop():
            conn = await asyncpg.connect(admin)
            try:
                # Exact test-owned DB; prevent computed target escaping its prefix.
                assert name.startswith("mimi086_migration_") and name.replace("_", "").isalnum()
                await conn.execute(f'DROP DATABASE "{name}"')
            finally:
                await conn.close()

        asyncio.run(drop())
