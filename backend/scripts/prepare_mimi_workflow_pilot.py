"""Explicit DDL for an already-empty dedicated synthetic pilot database only."""

import asyncio
import os
import selectors

import asyncpg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from app.agent.workflow_pilot import PILOT_DATABASE, SOURCE_DDL, selection_hash
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
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(68068)")
            rows = await connection.fetch(
                "SELECT r.id,r.owner_ref,r.engine,array_agg(s.task_id ORDER BY s.task_id) AS ids "
                "FROM mimi_probe_068.run r JOIN mimi_probe_068.task_source s ON s.run_id=r.id "
                "WHERE NOT EXISTS(SELECT 1 FROM mimi_probe_068.task_request q WHERE q.id=r.id) "
                "GROUP BY r.id,r.owner_ref,r.engine"
            )
            prior = await connection.fetchval("SELECT count(*) FROM mimi_probe_068.task_request")
            if prior + len(rows) > 128:
                raise RuntimeError("pilot_identity_backfill_quota_exceeded")
            for row in rows:
                await connection.execute(
                    "INSERT INTO mimi_probe_068.task_request VALUES($1,$2,$3,$4)",
                    row["id"],
                    row["owner_ref"],
                    row["engine"],
                    selection_hash(row["ids"]),
                )
            print(f"Retained legacy pilot request identities: {len(rows)}")
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
