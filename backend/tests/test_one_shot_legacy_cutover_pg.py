"""The old cutover grant must not silently encompass new reminder data."""

import asyncio
import os

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database_urls import async_postgres_url
from scripts.cutover_v2 import CutoverError, attest_schema

pytestmark = pytest.mark.pg


def test_old_cutover_refuses_current_reminder_schema(pg_dsn):
    async def scenario():
        url = (
            make_url(pg_dsn)
            .set(username="microsched_migrator", password=os.environ["CI_MIGRATOR_PASSWORD"])
            .render_as_string(hide_password=False)
        )
        engine = create_async_engine(async_postgres_url(url))
        try:
            with pytest.raises(CutoverError, match="not at the pinned Alembic revision"):
                await attest_schema(engine)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
