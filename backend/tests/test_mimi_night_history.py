"""Offline encrypted-history gates using actual eligibility SQL on in-memory SQLite.

Only the Task eligibility SELECT runs in SQLite; canonical event/receipt lookups
are doubles. This is not Postgres persistence, transactional or service evidence.
"""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import sqlite

from app.agent import crypto
from app.agent import working_context as working
from app.domain.models import Task


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


@pytest.mark.parametrize("gate", ["load", "checkpoint"])
@pytest.mark.parametrize(
    "deleted,private,raw",
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (False, False, True),
        (True, False, True),
        (False, True, True),
    ],
)
def test_scalar_receipt_and_raw_read_have_distinct_lifecycle_eligibility(
    deleted, private, raw, gate
):
    from app.core.settings import Settings

    async def scenario():
        identity, run_id, cid, receipt_id, change_id = (uuid4() for _ in range(5))
        dek = b"s" * 32
        settings = Settings(_env_file=None, mimi_working_projection_enabled=True)
        assistant = SimpleNamespace(
            id=uuid4(),
            run_id=run_id,
            conversation_id=cid,
            sequence=2,
            content_sha256="a" * 64,
            role="assistant",
        )
        user = SimpleNamespace(
            id=uuid4(), conversation_id=cid, sequence=1, content_sha256="b" * 64, role="user"
        )
        executed = datetime.now(UTC)
        terminal = {
            "receipt_id": str(receipt_id),
            "change_set_id": str(change_id),
            "state": "executed",
            "executed_at": executed.isoformat(),
            "task_ids": [str(identity)],
            "count": 1,
            "changes": [{"action": "create", "fields": ["title"]}],
        }
        pairs = []
        if raw:
            pairs = [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "read",
                            "type": "function",
                            "function": {
                                "name": "task.query.v1",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "read",
                    "content": json.dumps(
                        {
                            "rows": [{"id": str(identity), "title": "withheld-content-marker"}],
                        }
                    ),
                },
            ]
        body = working.projection_body(
            user if raw else None,
            assistant,
            pairs,
            outcome="assistant_text" if raw else "confirmed_execution",
            max_bytes=10000,
            terminal=None if raw else terminal,
        )
        event = SimpleNamespace(
            id=uuid4(),
            run_id=run_id,
            sequence=1,
            payload={
                "sha256": working.digest(body),
                "body_ciphertext": crypto.seal_content(
                    dek,
                    working.canonical(body),
                    aad=crypto.event_content_aad(run_id, 1, working.KIND),
                ),
            },
        )
        receipt = SimpleNamespace(
            change_set_id=change_id, executed_at=executed, result={"task_ids": [str(identity)]}
        )
        connection = sqlite3.connect(":memory:")
        connection.execute("ATTACH DATABASE ':memory:' AS microsched")
        connection.execute(
            "CREATE TABLE microsched.task (id TEXT, is_private BOOLEAN, deleted_at TEXT)"
        )
        connection.execute(
            "INSERT INTO microsched.task VALUES (?, ?, ?)",
            (identity.hex, private, executed.isoformat() if deleted else None),
        )

        class DB:
            async def execute(self, query):
                entity = query.column_descriptions[0]["entity"]
                if entity is Task:
                    # Exercise the exact production predicate, including UUID NOT IN
                    # and its empty-set behavior, rather than duplicate it in Python.
                    sql = str(
                        query.compile(
                            dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
                        )
                    )
                    return Result([UUID(row[0]) for row in connection.execute(sql)])
                if entity.__name__ == "MimiEvent":
                    return Result([event])
                return Result([receipt])

            async def get(self, model, key):
                return assistant if key == assistant.id else user if key == user.id else None

        try:
            db = DB()
            eligible = not private and (not deleted or not raw)
            if gate == "load":
                history = await working.load_history(
                    db, SimpleNamespace(id=cid), dek, [assistant], settings
                )
                assert (2 in history.refs) is eligible
                assert bool(history.outcomes) is (eligible and not raw)
                assert bool(history.by_assistant.get(2)) is (eligible and raw)
            reference = {
                "event_id": str(event.id),
                "sha256": working.digest(body),
                "storage_sha256": working.digest(event.payload),
            }
            if gate == "checkpoint":
                assert (
                    await working.working_refs_current(db, cid, [reference], dek, settings)
                    is eligible
                )
            if not eligible and gate == "load":
                assert "withheld-content-marker" not in json.dumps(history.by_assistant)
        finally:
            connection.close()

    asyncio.run(scenario())
