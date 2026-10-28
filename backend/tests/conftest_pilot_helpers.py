"""Exact generated fixture identity cleanup via exclusive local bootstrap role."""

import os

import asyncpg
from sqlalchemy.engine import make_url

from app.agent.workflow_pilot import PILOT_DATABASE


async def remove_fixture_identities(ids):
    value = os.environ.get("MIMI_PILOT_SETUP_URL")
    if not value:
        return  # Admission remains bounded; missing fixture cleanup is never app privilege.
    parsed = make_url(value)
    if (
        parsed.host != "127.0.0.1"
        or parsed.database != PILOT_DATABASE
        or parsed.username != "postgres"
        or parsed.query
    ):
        raise RuntimeError("exclusive synthetic bootstrap required")
    connection = await asyncpg.connect(value)
    try:
        await connection.execute(
            "DELETE FROM mimi_probe_068.task_request WHERE id=ANY($1::uuid[]) "
            "AND NOT EXISTS (SELECT 1 FROM mimi_probe_068.run WHERE run.id=task_request.id)",
            ids,
        )
    finally:
        await connection.close()
