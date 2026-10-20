"""0018 populated upgrade, retained-data refusal and empty rollback on throwaway PG."""

import asyncio
from datetime import date, datetime, timedelta, timezone

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from test_mimi_collection_fallback_pg import isolated_0017  # noqa: F401
from test_mimi_collection_migration_pg import migrate

pytestmark = pytest.mark.pg


def test_0018_preserves_sources_and_refuses_nonempty_downgrade(request):
    url = request.getfixturevalue("isolated_0017")
    app_url = (
        make_url(url)
        .set(username="microsched_app", password="synthetic-app")
        .render_as_string(hide_password=False)
    )

    async def seed():
        conn = await asyncpg.connect(url)
        try:
            tid = await conn.fetchval(
                "INSERT INTO microsched.task(title,body_md) "
                "VALUES ('Synthetic088 baseline','Retain full body') RETURNING id"
            )
            aid = await conn.fetchval(
                "INSERT INTO microsched.day_annotation(label,starts_on,ends_on) "
                "VALUES ('Synthetic088 retained day',$1,$1) RETURNING id",
                date(2026, 10, 25),
            )
            return tid, aid
        finally:
            await conn.close()

    tid, aid = asyncio.run(seed())
    migrate(url, "upgrade", "0018")

    async def audit_and_remind():
        # Actual app role reads the expanded model columns and writes the new FK.
        conn = await asyncpg.connect(app_url)
        try:
            assert (
                await conn.fetchval("SELECT body_md FROM microsched.task WHERE id=$1", tid)
                == "Retain full body"
            )
            assert (
                await conn.fetchval("SELECT label FROM microsched.day_annotation WHERE id=$1", aid)
                == "Synthetic088 retained day"
            )
            return await conn.fetchval(
                "INSERT INTO microsched.one_shot_reminder(annotation_id,mode,due_at) "
                "VALUES ($1,'absolute',$2) RETURNING id",
                aid,
                datetime.now(timezone.utc) + timedelta(days=1),
            )
        finally:
            await conn.close()

    rid = asyncio.run(audit_and_remind())
    refusal = migrate(url, "downgrade", "0017", expected=1)
    assert "cannot downgrade 0018 with day-annotation reminder data" in refusal

    async def retained_then_remove_owned():
        conn = await asyncpg.connect(url)
        try:
            assert (
                await conn.fetchval("SELECT version_num FROM microsched.alembic_version") == "0018"
            )
            assert (
                await conn.fetchval(
                    "SELECT annotation_id FROM microsched.one_shot_reminder WHERE id=$1", rid
                )
                == aid
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM pg_trigger WHERE tgrelid="
                    "'microsched.day_annotation'::regclass AND tgname='sync_one_shot_annotation'"
                )
                == 1
            )
            await conn.execute("DELETE FROM microsched.one_shot_reminder WHERE id=$1", rid)
        finally:
            await conn.close()

    asyncio.run(retained_then_remove_owned())
    migrate(url, "downgrade", "0017")
    migrate(url, "upgrade", "0018")
