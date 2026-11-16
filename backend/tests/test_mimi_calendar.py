"""Offline Calendar tool schema, gate, and provenance checks."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid7

import pytest
from pydantic import ValidationError

from app.agent.context_builder import assemble_context, rebind_after_read
from app.agent.contracts import ExecutionLease, Sensitivity
from app.agent.openrouter import build_request, serialized_input_bytes
from app.agent.service import _manifest_receipt
from app.agent.tools.calendar_reads import CALENDAR_READ_TOOL, CALENDAR_READ_TOOLS
from app.agent.tools.registry import execute_read_tool, validate_read_arguments
from app.agent.working_context import projection_body, validate_body
from app.core.settings import Settings
from app.domain.calendar_read import CalendarReadRequest, CalendarReadResult


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"date": "2040-09-01", "dates": ["2040-09-01"]},
        {"dates": []},
        {"dates": ["2040-09-01"] * 2},
        {"dates": ["2040-09-01"] * 32},
        {"date": "2040-09-01T00:00:00Z"},
        {"date": 2230070400},
        {"date": "2040-02-30"},
        {"date": "9999-12-31"},
        {"through_date": "2040-09-01"},
        {"from_date": "2040-09-02", "through_date": "2040-09-01"},
        {"from_date": "2040-09-01", "through_date": "2040-10-02"},
        {"date": "2040-09-01", "kinds": []},
        {"date": "2040-09-01", "kinds": ["event", "event"]},
        {"date": "2040-09-01", "include_hidden_sources": True},
        {"date": "2040-09-01", "allow_private": True},
    ],
)
def test_read_arguments_reject_ambiguous_or_out_of_bounds_scope(invalid):
    with pytest.raises(ValidationError):
        validate_read_arguments(CALENDAR_READ_TOOL, invalid)


def test_date_selection_normalizes_disjoint_days_and_accepts_31_inclusive_days():
    assert CalendarReadRequest(dates=["2040-09-01", "2040-08-30"]).days() == (
        date(2040, 8, 30),
        date(2040, 9, 1),
    )
    full = CalendarReadRequest(from_date="2040-09-01", through_date="2040-10-01")
    assert len(full.days()) == 31 and full.days()[-1] == date(2040, 10, 1)


def test_calendar_dispatch_is_disabled_before_any_database_access():
    args = {"date": "2040-09-01"}
    settings = Settings(_env_file=None)

    class NoDatabase:
        async def execute(self, *_args):
            pytest.fail("Calendar read touched the database with its flag disabled")

    with pytest.raises(ValueError, match="mimi_calendar_read_disabled"):
        asyncio.run(execute_read_tool(NoDatabase(), CALENDAR_READ_TOOL, args, settings=settings))


def test_openrouter_offer_is_opt_in_and_context_records_calendar_not_task():
    disabled = Settings(
        _env_file=None,
        app_env="local",
        mimi_route_mode="native",
        mimi_standard_api_key="synthetic-unused-transport",
        mimi_route_model="synthetic/calendar-test",
        mimi_route_max_input_price="0.2",
        mimi_route_max_output_price="0.6",
    )
    enabled = disabled.model_copy(update={"mimi_calendar_read_enabled": True})
    off = build_request([], settings=disabled, agent_contract=True)
    on = build_request([], settings=enabled, agent_contract=True)

    def names(payload):
        return {t["function"]["name"] for t in payload["tools"]}

    assert not (names(off) & CALENDAR_READ_TOOLS)
    assert names(on) - names(off) == CALENDAR_READ_TOOLS
    assert {k: v for k, v in off.items() if k != "tools"} == {
        k: v for k, v in on.items() if k != "tools"
    }

    now = datetime.now(UTC)
    args = {"date": "2040-09-01"}
    lease = ExecutionLease(
        lease_id=uuid7(),
        owner_id=uuid7(),
        run_id=uuid7(),
        capabilities=(CALENDAR_READ_TOOL,),
        issued_at=now,
        deadline=now + timedelta(minutes=1),
        max_turns=3,
        max_tool_calls=3,
        cost_cap_minor=0,
        sensitivity=Sensitivity.STANDARD,
    )
    envelope, messages = assemble_context(
        lease=lease,
        reserved_task_id=uuid7(),
        conversation_id=uuid7(),
        generation=1,
        request_id="calendar-test",
        transcript_suffix=[],
        current_user_turn="Lịch ngày 1/9?",
        task_context=[],
        pending_preview_content=[],
        pending_preview=None,
        pending_draft=None,
        checkpoint=None,
        checkpoint_id=None,
        checkpoint_frontier=0,
        transcript_range=None,
        settings=enabled,
        remaining_turns=3,
        remaining_tool_calls=3,
    )
    assert envelope.authority.allowed_tools == (CALENDAR_READ_TOOL,)
    assert "including after Resume" in envelope.policy_text
    result = CalendarReadResult(
        requested_dates=(date(2040, 9, 1),),
        kinds=("task", "event", "annotation"),
        rows=(),
        count=0,
        coverage="complete",
        has_more=False,
        continued=False,
        next_cursor=None,
        data_as_of=now,
    ).model_dump(mode="json")
    pair = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "calendar-call",
                    "type": "function",
                    "function": {"name": CALENDAR_READ_TOOL, "arguments": json.dumps(args)},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "calendar-call", "content": json.dumps(result)},
    ]
    updated, wire = rebind_after_read(
        envelope,
        [*messages, *pair],
        tool_name=CALENDAR_READ_TOOL,
        call_id="calendar-call",
        arguments=args,
        result=result,
        remaining_turns=2,
        remaining_tool_calls=2,
    )
    assert updated.manifest.sources[-1].source_type == "microsched.calendar.standard"
    assert _manifest_receipt(updated)["sources"][-1]["source_type"] == (
        "microsched.calendar.standard"
    )
    assert updated.manifest.sources[-1].coverage == "complete"
    assert updated.manifest.sources[-1].count == 0
    assert serialized_input_bytes(wire, agent_contract=True, calendar_enabled=True) <= (
        updated.manifest.budget.serialized_input_upper_bound
    )
    user = SimpleNamespace(id=uuid7(), sequence=1, content_sha256="1" * 64)
    assistant = SimpleNamespace(id=uuid7(), sequence=2, content_sha256="2" * 64)
    finalized = projection_body(user, assistant, pair, outcome="assistant_text", max_bytes=100_000)
    assert finalized["pairs"] == []
    validate_body(finalized, user, assistant, max_bytes=100_000)
