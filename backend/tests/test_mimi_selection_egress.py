"""Opaque historical selection text never inherits selected-member eligibility."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import sqlite

from app.agent.selection import SelectionCandidate, bind_selection, selection_for_egress
from app.agent.working_context import read_requirements

MARKER = "synthetic-unclassified-B-title"


def subset():
    a, b, event, run = (str(uuid4()) for _ in range(4))
    observed = datetime.now(UTC).isoformat()
    rows = [
        {
            "id": identity,
            "title": "A" if identity == a else MARKER,
            "collection_version": 1,
            "source_version": observed,
            "deleted_at": None,
        }
        for identity in (a, b)
    ]
    receipt = {
        "event_id": event,
        "run_id": run,
        "tool": "task.query.v1",
        "arguments": {},
        "result": {"rows": rows, "data_as_of": observed, "coverage": "complete"},
    }
    snapshot = bind_selection(
        SelectionCandidate(
            intent="Choose A using " + MARKER,
            variants_considered=(MARKER,),
            explicitly_named_subset=True,
            members=({"id": a, "classification": "included", "reason": MARKER},),
        ),
        [receipt],
    )
    assert snapshot["missing_classifications"] == [b]
    return a, b, {"event_id": event, "run_id": run, "snapshot": snapshot}


@pytest.mark.parametrize("b_state", ["active", "private", "deleted"])
def test_historical_subset_omits_opaque_free_text_but_retains_scalar_binding(b_state):
    a, b, selection = subset()
    original = json.dumps(selection, sort_keys=True)
    connection = sqlite3.connect(":memory:")
    connection.execute("ATTACH DATABASE ':memory:' AS microsched")
    connection.execute(
        "CREATE TABLE microsched.task (id TEXT, is_private BOOLEAN, deleted_at TEXT)"
    )
    connection.executemany(
        "INSERT INTO microsched.task VALUES (?, ?, ?)",
        [
            (UUID(a).hex, False, None),
            (UUID(b).hex, b_state == "private", "deleted" if b_state == "deleted" else None),
        ],
    )

    class DB:
        async def execute(self, query):
            sql = str(
                query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            )
            values = [UUID(row[0]) for row in connection.execute(sql)]

            class Result:
                def scalars(self):
                    return self

                def all(self):
                    return values

            return Result()

    try:
        safe = asyncio.run(selection_for_egress(DB(), selection))
        assert MARKER not in json.dumps(safe)
        assert safe["selection_id"] == selection["snapshot"]["selection_id"]
        assert safe["members"][0]["id"] == a
        assert safe["coverage"] == "unavailable"
        assert json.dumps(selection, sort_keys=True) == original  # canonical body untouched
    finally:
        connection.close()


def test_current_selection_remains_usable_but_opaque_raw_history_is_withheld():
    a, _, selection = subset()
    pair = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "select",
                    "type": "function",
                    "function": {"name": "task.freeze_selection.v1", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "select",
            "content": json.dumps({"selection": selection["snapshot"]}),
        },
    ]
    assert read_requirements([pair], historical=False) == ({a}, {a})
    with pytest.raises(ValueError, match="opaque_selection"):
        read_requirements([pair])
