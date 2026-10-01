"""Explicit DDL for an already-empty dedicated synthetic pilot database only."""

import asyncio
import os
import selectors

import asyncpg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from app.agent.workflow_pilot import PILOT_DATABASE, SOURCE_DDL
from scripts.prepare_mimi_workflow_probe import prepare


async def main():
    admin = os.environ["MIMI_PILOT_SETUP_URL"]
    app = os.environ["MIMI_PILOT_APP_URL"]
    for value in (admin, app):
        url = make_url(value)
        if url.database != PILOT_DATABASE or url.host != "127.0.0.1" or url.query:
            raise RuntimeError("exclusive local pilot database required")
    await prepare(admin)
    connection = await asyncpg.connect(admin)
    try:
        await connection.execute(SOURCE_DDL)
    finally:
        await connection.close()
    async with AsyncPostgresSaver.from_conn_string(admin) as saver:
        await saver.setup()
    connection = await asyncpg.connect(admin)
    try:
        await connection.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO microsched_app"
        )
    finally:
        await connection.close()
    print("073 isolated local schema ready; no app-startup DDL")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
