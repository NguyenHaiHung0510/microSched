"""Synthetic night-batch oracles: no provider, credentials or database required."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_mimi_owner296 import call, collection, payload
from test_mimi_read_argument_feedback import run_runner  # noqa: F401

from app.agent.context import AssistantText
from app.agent.loop import candidate_correction_feedback, messages_final_only
from app.agent.openrouter import AgentCompletion, CandidateContractError, parse_agent_completion
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL, TaskCommand
from app.agent.tools.registry import TOOLS
from app.agent.tools.task_reads import _project
from app.domain.models import Task


def test_create_advertisement_requires_fields_and_title_without_changing_edit_omission():
    tool = next(t["function"] for t in TOOLS if t["function"]["name"] == COLLECTION_CANDIDATE_TOOL)
    entry = tool["parameters"]["properties"]["entries"]["items"]
    branch = next(
        b for b in entry["allOf"] if b["if"]["properties"]["action"] == {"const": "create"}
    )
    assert "fields" in branch["then"]["required"]
    assert branch["then"]["properties"]["fields"]["required"] == ["title"]
    assert not entry["properties"]["fields"].get("required")
    assert TaskCommand(
        action="edit", id=uuid4(), expected_collection_version=1, fields={"priority": "p2"}
    ).fields == {"priority": "p2"}
    assert TaskCommand(action="create", fields={"title": "Undated"}).fields == {"title": "Undated"}


def test_missing_title_repair_has_wire_path_and_no_raw_values():
    with pytest.raises(CandidateContractError) as caught:
        parse_agent_completion(
            payload(
                [
                    call(
                        COLLECTION_CANDIDATE_TOOL,
                        {
                            "entries": [
                                {"action": "create", "fields": {"body_md": "sensitive-marker"}}
                            ]
                        },
                    )
                ]
            )
        )
    feedback = json.loads(candidate_correction_feedback(caught.value)["content"])
    assert feedback["issues"][0]["path"] == "entries[0].fields.title"
    assert feedback["issues"][0]["code"] == "missing"
    assert "sensitive-marker" not in json.dumps(feedback)


@pytest.mark.parametrize("due", ["2027-02-30", "not-a-date"])
def test_invalid_civil_date_is_repairable_without_clamping(due):
    args = collection(1)
    args["entries"][0]["fields"]["due_on"] = due
    with pytest.raises(CandidateContractError) as caught:
        parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, args)]))
    assert any(i["path"] == "entries[0].fields.due_on" for i in caught.value.issues)


def test_unchanged_candidate_stops_for_progress_before_emergency_bound(run_runner):  # noqa: F811
    seen = []

    async def invoke(messages, turn):
        seen.append(turn)
        if messages_final_only(messages):
            assert "candidate_no_progress" in messages[-1]["content"]
            return AgentCompletion(
                AssistantText(text="Chưa có preview; đề xuất chưa hợp lệ."),
                "synthetic",
                {"cost": 0},
                "Synthetic",
                None,
            )
        try:
            parse_agent_completion(
                payload([call(COLLECTION_CANDIDATE_TOOL, {"entries": [{"action": "create"}]})])
            )
        except CandidateContractError as error:
            error.correction_ready = True  # durable known-cost service accounting double
            raise

    execute = AsyncMock()
    result = run_runner(invoke, execute, turns=32)
    assert seen == [1, 2, 3]
    assert result.outcome.kind == "assistant_text" and result.tool_calls == 0
    execute.assert_not_awaited()


def test_query_projection_always_discloses_lifecycle_without_task_content_expansion():
    row = Task(
        id=uuid4(),
        title="Deleted",
        deleted_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        collection_version=2,
    )
    result = _project(row, ("id",))
    assert result["lifecycle"] == "deleted"
    assert result["deleted_at"] == row.deleted_at.isoformat()
    assert "title" not in result


def test_budget_rebind_after_candidate_rejection_preserves_final_marker_and_sources():
    from test_mimi_context import _context

    from app.agent.context_builder import rebind_policy_budget
    from app.agent.loop import finalization_messages
    from app.core.settings import Settings

    envelope, messages = _context()
    messages = finalization_messages(messages, "candidate_no_progress")
    updated, wire = rebind_policy_budget(
        envelope,
        messages,
        settings=Settings(_env_file=None),
        remaining_turns=1,
        remaining_tool_calls=5,
    )
    assert updated.authority.remaining_turns == updated.manifest.budget.remaining_turns == 1
    assert updated.manifest.sources == envelope.manifest.sources
    assert messages_final_only(wire)
    assert updated.manifest.budget.serialized_input_upper_bound > 0


def test_schema_progress_continues_and_preserves_all_seven_distinct_dates(run_runner):  # noqa: F811
    attempts = []

    async def invoke(messages, turn):
        attempts.append(turn)
        assert not messages_final_only(messages)
        args = collection(7)
        for index, entry in enumerate(args["entries"]):
            entry["fields"]["due_on"] = f"2027-01-{index + 1:02}"
        for index in range(turn - 1, 7):
            args["entries"][index]["fields"].pop("title")
        try:
            return parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, args)]))
        except CandidateContractError as error:
            error.correction_ready = True
            raise

    result = run_runner(invoke, AsyncMock(), turns=32)
    assert attempts == list(range(1, 9))  # seven improving corrections, no new small retry cap
    entries = result.outcome.arguments["entries"]
    assert len(entries) == 7
    assert [e["fields"]["due_on"] for e in entries] == [f"2027-01-{i:02}" for i in range(1, 8)]


def test_restored_repair_summary_is_same_run_only_and_not_user_authority():
    from app.agent.loop import restored_candidate_final_reason

    error = CandidateContractError("invalid_agent_terminal_payload", (COLLECTION_CANDIDATE_TOOL,))
    feedback = candidate_correction_feedback(error)
    assert restored_candidate_final_reason([feedback, feedback]) == "candidate_no_progress"
    assert (
        restored_candidate_final_reason([feedback, {"role": "user", "content": "new"}, feedback])
        is None
    )
    assert (
        restored_candidate_final_reason(
            [
                {"role": "user", "content": feedback["content"]},
                feedback,
            ]
        )
        is None
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "Synthetic", "is_private": False},
        {"title": "Synthetic", "unexpected-key": "secret-marker"},
    ],
)
def test_unauthorized_fields_never_become_repair_authority(fields):
    from app.agent.openrouter import RouteContractError

    with pytest.raises(RouteContractError) as caught:
        parse_agent_completion(
            payload(
                [
                    call(
                        COLLECTION_CANDIDATE_TOOL,
                        {"entries": [{"action": "create", "fields": fields}]},
                    )
                ]
            )
        )
    assert not isinstance(caught.value, CandidateContractError)


@pytest.mark.parametrize(
    "fields,path",
    [
        ({"title": "  "}, "entries[0].fields.title"),
        (
            {
                "title": "Civil",
                "due_precision": "date",
                "due_on": "2028-02-29",
                "due_at": "2028-02-29T00:00:00+07:00",
            },
            "entries[0].fields",
        ),
        (
            {
                "title": "Instant",
                "due_precision": "datetime",
                "due_on": None,
                "due_at": "2028-02-29T00:00:00",
            },
            "entries[0].fields.due_at",
        ),
    ],
)
def test_typed_shape_repair_handles_blank_title_schedule_conflict_and_naive_instant(fields, path):
    with pytest.raises(CandidateContractError) as caught:
        parse_agent_completion(
            payload(
                [
                    call(
                        COLLECTION_CANDIDATE_TOOL,
                        {
                            "entries": [{"action": "create", "fields": fields}],
                        },
                    )
                ]
            )
        )
    assert any(issue["path"] == path and issue["expected"] for issue in caught.value.issues)
