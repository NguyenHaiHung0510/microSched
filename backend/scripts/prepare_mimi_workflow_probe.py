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
ALTER TABLE mimi_probe_068.run ADD COLUMN IF NOT EXISTS created_at timestamptz
    NOT NULL DEFAULT clock_timestamp();
ALTER TABLE mimi_probe_068.run ADD COLUMN IF NOT EXISTS completed_at timestamptz;
CREATE TABLE IF NOT EXISTS mimi_probe_068.record (
    run_id uuid NOT NULL REFERENCES mimi_probe_068.run(id) ON DELETE CASCADE,
    id text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    title text NOT NULL CHECK (title LIKE 'mimi:v1:%'),
    PRIMARY KEY(run_id,id)
);
CREATE TABLE IF NOT EXISTS mimi_probe_068.dispatch (
    run_id uuid NOT NULL REFERENCES mimi_probe_068.run(id) ON DELETE CASCADE,
    step text NOT NULL,
    PRIMARY KEY(run_id,step)
);
CREATE TABLE IF NOT EXISTS mimi_probe_068.receipt (
    run_id uuid PRIMARY KEY REFERENCES mimi_probe_068.run(id) ON DELETE CASCADE,
    digest text NOT NULL,
    content text NOT NULL CHECK (content LIKE 'mimi:v1:%')
);
GRANT USAGE ON SCHEMA mimi_probe_068 TO microsched_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA mimi_probe_068 TO microsched_app;
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
