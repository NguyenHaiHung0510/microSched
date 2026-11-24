"""Read/restore instruction wiring and existing typed boundaries, no live inference."""

from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid7

import pytest
from fastapi import HTTPException
from test_mimi_context import _context
from test_mimi_openrouter import _settings
from test_mimi_owner296 import call, payload

from app.agent.context import AssistantText, PreviewCandidate, ToolRequests
from app.agent.context_builder import serialize_openrouter_messages
from app.agent.openrouter import RouteContractError, build_request, parse_agent_completion
from app.agent.policy import checkpoint_policy_compatible
from app.agent.selection import SelectionCandidate, bind_selection, covered_versions
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL, CollectionCandidate
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL
from app.agent.tools.task_reads import TaskQuery, _project
from app.domain.models import Task


def request_for(text):
    settings = _settings(mimi_collection_enabled=True)
    envelope, _ = _context(settings=settings)
    envelope = envelope.model_copy(update={"current_user_turn": text})
    return build_request(serialize_openrouter_messages(envelope), settings, agent_contract=True)


def test_list_request_wires_read_answer_guidance_without_forcing_a_candidate():
    request = request_for("Cho xem danh sách Task hiện có.")
    assert request["tool_choice"] == "auto"
    assert (
        "A request only to list, show, search or count Tasks must not produce a mutation proposal"
        in (request["messages"][0]["content"])
    )
    tools = {t["function"]["name"]: t["function"] for t in request["tools"]}
    assert "For list/read-only requests, read and answer" in tools["task.query.v1"]["description"]
    for name in (CREATE_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL):
        assert (
            "Do not call for list/read-only requests without a requested change"
            in (tools[name]["description"])
        )
    args = TaskQuery().model_dump(mode="json")
    read = parse_agent_completion(payload([call("task.query.v1", args)])).outcome
    assert isinstance(read, ToolRequests) and read.requests[0].arguments == args
    answer = payload([])
    answer["choices"][0]["message"]["content"] = "Đã đọc phạm vi hợp lệ; chưa thay đổi dữ liệu."
    assert isinstance(parse_agent_completion(answer).outcome, AssistantText)


def test_restore_workflow_reaches_request_with_existing_exact_identity_schema():
    request = request_for("Khôi phục Task vừa xóa.")
    system = request["messages"][0]["content"]
    assert "To restore a deleted Task, use an explicit filter.lifecycle=deleted read" in system
    assert "freeze a current-run selection" in system
    assert "action=restore with the exact selected id and expected_collection_version" in system
    tool = next(
        t["function"]
        for t in request["tools"]
        if t["function"]["name"] == COLLECTION_CANDIDATE_TOOL
    )
    assert (
        "Restore requires an explicit deleted read and a current-run selection"
        in (tool["description"])
    )
    entry = tool["parameters"]["properties"]["entries"]["items"]
    assert "restore" in entry["properties"]["action"]["enum"]
    branch = next(
        b for b in entry["allOf"] if b["if"]["properties"].get("action") == {"const": "create"}
    )
    assert set(branch["else"]["required"]) == {"id", "expected_collection_version"}
    assert checkpoint_policy_compatible(
        "1e89e2f470bc39ea9c66c0237979f194f3c9b03f5217eee974fd231f52f94a11",
        collection_enabled=True,
    )


def restore_fixture():
    now = datetime.now(UTC)
    task = Task(
        id=uuid7(),
        title="Synthetic archived Task",
        deleted_at=now,
        updated_at=now,
        collection_version=17,
    )
    query = TaskQuery.model_validate(
        {
            "filter": {"lifecycle": "deleted", "title_contains": task.title},
            "projection": ["id", "title"],
        }
    )
    receipt = {
        "event_id": str(uuid7()),
        "tool": "task.query.v1",
        "arguments": query.model_dump(mode="json"),
        "result": {
            "rows": [_project(task, query.projection)],
            "coverage": "complete",
            "count": 1,
            "next_cursor": None,
            "data_as_of": now.isoformat(),
        },
    }
    selection = bind_selection(
        SelectionCandidate(
            intent="Restore the named deleted Task",
            variants_considered=(task.title,),
            explicitly_named_subset=True,
            members=({"id": task.id, "classification": "included", "reason": "Requested target"},),
        ),
        [receipt],
    )
    args = {
        "selection_id": selection["selection_id"],
        "entries": [{"action": "restore", "id": str(task.id), "expected_collection_version": 17}],
    }
    return selection, args


def test_minimal_restore_from_explicit_deleted_read_keeps_identity_and_omission():
    selection, args = restore_fixture()
    assert selection["members"][0]["deleted_read_authorized"] is True
    outcome = parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, args)])).outcome
    assert isinstance(outcome, PreviewCandidate)
    candidate = CollectionCandidate.model_validate(outcome.arguments)
    command = candidate.entries[0]
    assert candidate.selection_id == UUID(selection["selection_id"])
    assert covered_versions(selection, [command.id]) == {
        command.id: command.expected_collection_version
    }
    assert command.action == "restore" and command.fields == {} and command.children == ()
    assert command.reminder.action == "keep"


@pytest.mark.parametrize(
    "fault", ["id", "version", "zero_version", "selection", "privacy", "lifecycle"]
)
def test_restore_does_not_relax_required_identity_or_authorized_fields(fault):
    _, args = restore_fixture()
    entry = args["entries"][0]
    if fault == "selection":
        args["selection_id"] = None
    elif fault == "id":
        del entry["id"]
    elif fault in {"version", "zero_version"}:
        entry["expected_collection_version"] = None if fault == "version" else 0
    else:
        entry["fields"] = {"is_private": False} if fault == "privacy" else {"deleted_at": None}
    with pytest.raises(RouteContractError):
        parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, args)]))


def test_restore_cannot_substitute_another_target_for_the_selected_task():
    selection, _ = restore_fixture()
    with pytest.raises(HTTPException) as caught:
        covered_versions(selection, [uuid4()])
    assert caught.value.status_code == 409
    assert caught.value.detail == "collection_must_match_exact_frozen_selection"
