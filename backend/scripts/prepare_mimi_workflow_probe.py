"""Explicit setup of the dedicated local 068 schema; never app startup DDL."""

import asyncio
import os

import asyncpg

from app.agent.workflow_probe.store import local_probe_dsn

DDL = """
CREATE SCHEMA IF NOT EXISTS mimi_probe_068;
CREATE TABLE IF NOT EXISTS mimi_probe_068.run (
    id uuid PRIMARY KEY,
    owner_ref varchar(64) NOT NULL,
    generation integer NOT NULL CHECK (generation > 0),
    engine text NOT NULL CHECK (engine IN ('control','graph')),
    phase text NOT NULL,
    revision integer NOT NULL CHECK (revision >= 0),
    expires_at timestamptz NOT NULL,
    wrapped_dek text NOT NULL CHECK (wrapped_dek LIKE 'enc:v1:%'),
    content text NOT NULL CHECK (content LIKE 'mimi:v1:%' AND octet_length(content) <= 90112)
);
GRANT USAGE ON SCHEMA mimi_probe_068 TO microsched_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON mimi_probe_068.run TO microsched_app;
"""


async def prepare(value: str) -> None:
    connection = await asyncpg.connect(local_probe_dsn(value, setup=True))
    try:
        async with connection.transaction():
            await connection.execute(DDL)
    finally:
        await connection.close()


if __name__ == "__main__":
    value = os.environ.get("MIMI_WORKFLOW_PROBE_SETUP_URL")
    if not value:
        raise SystemExit("MIMI_WORKFLOW_PROBE_SETUP_URL is required (local synthetic only)")
    asyncio.run(prepare(value))
    print("068 local schema ready; app role has DML only.")
