"""Create-content request wiring and materialization; no model compliance claim."""

import copy
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_mimi_context import _context
from test_mimi_openrouter import _settings
from test_mimi_owner296 import call, payload

from app.agent.context import PreviewCandidate
from app.agent.context_builder import serialize_openrouter_messages
from app.agent.openrouter import build_request, parse_agent_completion
from app.agent.policy import checkpoint_policy_compatible, load_standard_policy
from app.agent.task_collection import (
    COLLECTION_CANDIDATE_TOOL,
    CollectionCandidate,
    TaskCommand,
    proposed_children,
    proposed_fields,
)


@pytest.mark.parametrize("revision", [False, True])
def test_create_content_guidance_reaches_actual_request_without_removing_optional_fields(revision):
    settings = _settings(mimi_collection_enabled=True, mimi_revision_collection=revision)
    envelope, _ = _context(settings=settings)
    envelope = envelope.model_copy(update={"current_user_turn": "Tạo Task mẫu vào ngày mai."})
    request = build_request(
        serialize_openrouter_messages(envelope),
        settings,
        agent_contract=True,
        force_task_tool=revision,
    )
    policy = load_standard_policy(collection_enabled=True)
    assert request["messages"][0] == {"role": "system", "content": policy.text}
    assert envelope.manifest.policy_sha256 == policy.sha256
    system = request["messages"][0]["content"]
    assert "For title/date-only creates, omit body_md and children" in system
    assert "explicitly requested for generation" in system
    assert "copied from an eligible STANDARD source" in system
    assert "preserve existing content unless the user requests a change" in system
    assert "Keep body_md and checklist content for every Task" not in system
    tool = next(
        t["function"]
        for t in request["tools"]
        if t["function"]["name"] == COLLECTION_CANDIDATE_TOOL
    )
    assert "For title/date-only creates omit body_md and children" in tool["description"]
    fields = tool["parameters"]["properties"]["entries"]["items"]["properties"]["fields"]
    assert "body_md" in fields["properties"] and not fields.get("required")
    assert checkpoint_policy_compatible(
        "56ba4c60d10f95b0c3553a0cb464e907c58fbb1858f107ad647c01f355779924",
        collection_enabled=True,
    )


@pytest.mark.parametrize("body", [{}, {"body_md": None}, {"body_md": ""}])
def test_seven_title_date_only_entries_materialize_without_optional_content(body):
    entries = [
        {
            "action": "create",
            "fields": {
                "title": f"Synthetic minimal {day}",
                "due_precision": "date",
                "due_on": f"2030-04-{day:02d}",
                "due_at": None,
                **body,
            },
        }
        for day in range(1, 8)
    ]
    terminal = parse_agent_completion(
        payload([call(COLLECTION_CANDIDATE_TOOL, {"entries": entries})])
    ).outcome
    assert isinstance(terminal, PreviewCandidate)
    candidate = CollectionCandidate.model_validate(terminal.arguments)
    assert candidate.selection_id is None and len(candidate.entries) == 7
    for day, command in enumerate(candidate.entries, 1):
        fields = proposed_fields(command, None)
        assert fields["title"] == f"Synthetic minimal {day}"
        assert fields["due_precision"] == "date" and fields["due_on"] == f"2030-04-{day:02d}"
        assert fields["due_at"] is None and fields["body_md"] == body.get("body_md")
        assert fields["priority"] is None and fields["pinned"] is False
        assert fields["status"] == "open" and command.reminder.action == "keep"
        assert proposed_children(command, None, datetime.now(UTC)) == []


def test_rich_create_and_followup_edit_preserve_requested_content_verbatim():
    body = "## Kế hoạch được yêu cầu\n\nGiữ **nội dung** và `mã`.\n"
    checklist = ["Đọc nội dung nguồn", "Thực hành theo kế hoạch"]
    supplied = {
        "action": "create",
        "fields": {"title": "Synthetic rich plan", "body_md": body, "priority": "p2"},
        "children": [{"action": "append", "fields": {"content": text}} for text in checklist],
    }
    original = json.dumps(supplied, ensure_ascii=False, sort_keys=True)
    terminal = parse_agent_completion(
        payload([call(COLLECTION_CANDIDATE_TOOL, {"entries": [supplied]})])
    ).outcome
    command = CollectionCandidate.model_validate(terminal.arguments).entries[0]
    before = {
        "fields": proposed_fields(command, None),
        "children": proposed_children(command, None, datetime.now(UTC)),
    }
    assert before["fields"]["body_md"] == body
    assert [child["content"] for child in before["children"]] == checklist
    frozen = copy.deepcopy(before)
    edit = TaskCommand(
        action="edit", id=uuid4(), expected_collection_version=1, fields={"title": "Renamed plan"}
    )
    assert proposed_fields(edit, before) == {**before["fields"], "title": "Renamed plan"}
    assert proposed_children(edit, before, datetime.now(UTC)) == before["children"]
    assert before == frozen and json.dumps(supplied, ensure_ascii=False, sort_keys=True) == original
