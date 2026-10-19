"""Synthetic native create shapes and whole-turn rejection before any effects."""

import json
from uuid import uuid4

import pytest

from app.agent.context import PreviewCandidate, ToolRequests
from app.agent.openrouter import RouteContractError, parse_agent_completion
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL


def single():
    return {
        "task": {
            "id": str(uuid4()),
            "title": "Synthetic single",
            "body_md": "Nội dung",
            "status": "open",
            "priority": "p2",
            "due_precision": "none",
            "due_on": None,
            "due_at": None,
            "is_private": False,
            "items": ["Bước 1"],
        }
    }


def collection(count):
    return {
        "selection_id": None,
        "entries": [
            {
                "action": "create",
                "fields": {
                    "title": f"Synthetic R1 {i}",
                    "body_md": f"Nội dung {i}",
                    "priority": "p2",
                    "due_precision": "date",
                    "due_on": "2026-11-02",
                    "due_at": None,
                },
                "children": [{"action": "append", "fields": {"content": f"Bước {i}"}}],
            }
            for i in range(count)
        ],
    }


def call(name, args):
    return {
        "id": f"synthetic-{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def payload(calls):
    return {
        "id": "synthetic-terminal",
        "model": "deepseek/deepseek-v4.1-flash-1017",
        "provider": "Synthetic",
        "usage": {"cost": 0.001},
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "Chưa ghi; chỉ đề xuất.",
                    "tool_calls": calls,
                },
            }
        ],
    }


@pytest.mark.parametrize("count", [1, 2, 4])
def test_native_collection_preserves_complete_create_set(count):
    result = parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, collection(count))]))
    assert isinstance(result.outcome, PreviewCandidate)
    entries = result.outcome.arguments["entries"]
    assert len(entries) == count
    assert [e["fields"]["title"] for e in entries] == [f"Synthetic R1 {i}" for i in range(count)]
    assert all(e["id"] is None and e["expected_collection_version"] is None for e in entries)
    assert all(e["children"][0]["fields"]["content"] == f"Bước {i}" for i, e in enumerate(entries))


def test_native_single_still_previews_and_read_fanout_remains_valid():
    result = parse_agent_completion(payload([call(CREATE_CANDIDATE_TOOL, single())]))
    assert result.outcome.arguments["title"] == "Synthetic single"
    reads = parse_agent_completion(payload([call("task.query.v1", {}) for _ in range(8)]))
    assert isinstance(reads.outcome, ToolRequests) and len(reads.outcome.requests) == 8


@pytest.mark.parametrize(
    "names",
    [
        [CREATE_CANDIDATE_TOOL, CREATE_CANDIDATE_TOOL],
        [CREATE_CANDIDATE_TOOL, "task.query.v1"],
        [COLLECTION_CANDIDATE_TOOL, "task.query.v1"],
        [COLLECTION_CANDIDATE_TOOL, CREATE_CANDIDATE_TOOL],
        [COLLECTION_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL],
    ],
)
def test_mixed_candidate_turn_never_yields_partial_candidate_or_reads(names):
    calls = [
        call(
            n,
            collection(2)
            if n == COLLECTION_CANDIDATE_TOOL
            else single()
            if n == CREATE_CANDIDATE_TOOL
            else {},
        )
        for n in names
    ]
    with pytest.raises(RouteContractError, match="^candidate_cannot_share_tool_turn$"):
        parse_agent_completion(payload(calls))


def test_unknown_sibling_is_fatal_even_when_candidate_arguments_are_malformed():
    bad = call(COLLECTION_CANDIDATE_TOOL, {})
    bad["function"]["arguments"] = "{invalid-json"
    with pytest.raises(RouteContractError, match="^provider_tool_not_allowed$"):
        parse_agent_completion(payload([bad, call("unleased.synthetic", {})]))


@pytest.mark.parametrize(
    "patch",
    [
        {"fields": {"title": "Synthetic", "due_precision": "date"}},
        {"fields": {"title": "Synthetic", "is_private": True}},
        {"id": str(uuid4())},
        {"expected_collection_version": 1},
        {"children": [{"action": "append", "content": "wrong nesting"}]},
    ],
)
def test_native_candidate_schema_errors_remain_rejected(patch):
    from app.agent.openrouter import CandidateContractError

    args = collection(2)
    args["entries"][1].update(patch)
    with pytest.raises(RouteContractError, match="^invalid_agent_terminal_payload$") as raised:
        parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, args)]))
    is_schedule_shape = patch == {"fields": {"title": "Synthetic", "due_precision": "date"}}
    assert isinstance(raised.value, CandidateContractError) == is_schedule_shape
    assert getattr(raised.value, "correction_ready", False) is False


@pytest.mark.parametrize("cost", [None, True, "NaN", "Infinity", -1, "invalid"])
def test_missing_or_invalid_cost_does_not_authorize_correction(cost):
    from app.agent.openrouter import CandidateContractError

    error = CandidateContractError("invalid_agent_terminal_payload", (COLLECTION_CANDIDATE_TOOL,))
    assert not error.correction_permitted(
        {"id": "known", "usage": {"cost": cost}}, [COLLECTION_CANDIDATE_TOOL]
    )


def test_no_correction_for_unleased_final_only_or_missing_provider_identity():
    from app.agent.openrouter import CandidateContractError

    error = CandidateContractError("candidate_cannot_share_tool_turn", (COLLECTION_CANDIDATE_TOOL,))
    receipt = {"id": "known", "usage": {"cost": 0.001}}
    assert not error.correction_permitted(receipt, [])
    assert not error.correction_permitted(receipt, [COLLECTION_CANDIDATE_TOOL], final_only=True)
    assert not error.correction_permitted({"usage": {"cost": 0}}, [COLLECTION_CANDIDATE_TOOL])
    assert error.correction_permitted(receipt, [COLLECTION_CANDIDATE_TOOL])


# Both progression implementations receive only service-accounted, wholly rejected turns.
from test_mimi_read_argument_feedback import run_runner  # noqa: E402,F401

# pytest injects the imported parametrized fixture into these test arguments.


@pytest.mark.parametrize("failure", ["mixed", "schema", "json"])
def test_bounded_correction_preserves_full_create_set_without_running_sibling(run_runner, failure):  # noqa: F811
    from unittest.mock import AsyncMock

    from app.agent.openrouter import CandidateContractError

    args = collection(4)
    bad_calls = [call(COLLECTION_CANDIDATE_TOOL, args), call("task.query.v1", {})]
    if failure == "schema":
        args["entries"][3]["fields"].pop("due_at")
        bad_calls = [call(COLLECTION_CANDIDATE_TOOL, args)]
    elif failure == "json":
        bad_calls[0]["function"]["arguments"] = "{sensitive-marker"
    turns = []
    execute = AsyncMock()

    async def invoke(messages, turn):
        turns.append(turn)
        if turn == 1:
            try:
                parse_agent_completion(payload(bad_calls))
            except CandidateContractError as error:
                error.correction_ready = True  # simulate successful durable service accounting
                raise
        assert "sensitive-marker" not in json.dumps(messages)
        feedback = json.loads(messages[-1]["content"])
        assert "whole proposal" in feedback["instruction"]
        return parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, collection(4))]))

    result = run_runner(invoke, execute)
    assert turns == [1, 2] and result.turns == 2 and result.tool_calls == 0
    assert len(result.outcome.arguments["entries"]) == 4
    execute.assert_not_awaited()


def test_correction_uses_existing_final_turn_without_extra_proposal_or_dispatch(run_runner):  # noqa: F811
    from unittest.mock import AsyncMock

    from app.agent.context import AssistantText
    from app.agent.loop import messages_final_only
    from app.agent.openrouter import AgentCompletion, CandidateContractError

    seen = []

    async def invoke(messages, turn):
        seen.append(turn)
        if messages_final_only(messages):
            return AgentCompletion(
                AssistantText(text="Chưa tạo preview; cần sửa đề xuất."),
                "synthetic-final",
                {"cost": 0},
                "Synthetic",
                None,
            )
        error = CandidateContractError(
            "invalid_agent_terminal_payload", (COLLECTION_CANDIDATE_TOOL,)
        )
        error.correction_ready = True
        raise error

    execute = AsyncMock()
    result = run_runner(invoke, execute, turns=3)
    assert seen == [1, 2, 3] and result.outcome.kind == "assistant_text"
    assert result.tool_calls == 0
    execute.assert_not_awaited()


@pytest.mark.parametrize("ready", [False, True])
def test_unaccounted_or_final_only_rejection_cannot_continue(run_runner, ready):  # noqa: F811
    from unittest.mock import AsyncMock

    from app.agent.openrouter import CandidateContractError

    invoke = AsyncMock()
    error = CandidateContractError("invalid_agent_terminal_payload", (COLLECTION_CANDIDATE_TOOL,))
    error.correction_ready = ready
    invoke.side_effect = error
    with pytest.raises(CandidateContractError):
        run_runner(invoke, AsyncMock(), turns=1 if ready else 3)
    assert invoke.await_count == 1


def assert_collection_wire_schema(wire):
    tool = next(
        t["function"] for t in wire["tools"] if t["function"]["name"] == COLLECTION_CANDIDATE_TOOL
    )
    fields = tool["parameters"]["properties"]["entries"]["items"]["properties"]["fields"]
    assert fields["additionalProperties"] is False
    assert set(fields["properties"]) == {
        "title",
        "body_md",
        "status",
        "priority",
        "due_precision",
        "due_on",
        "due_at",
        "pinned",
    }
    assert not fields.get("required")  # Existing-target edits can preserve omitted fields.
    assert fields["properties"]["due_precision"]["enum"] == ["none", "date", "datetime"]
    assert fields["properties"]["pinned"]["type"] == "boolean"
    assert "is_private" in tool["description"] and "even false" in tool["description"]
    single_tool = next(
        t["function"] for t in wire["tools"] if t["function"]["name"] == CREATE_CANDIDATE_TOOL
    )
    assert single_tool["parameters"]["properties"]["task"]["properties"]["is_private"] == {
        "const": False
    }


def test_native_collection_wire_schema_lists_only_authorized_collection_fields():
    from test_mimi_openai_sdk import _settings

    from app.agent.openrouter import build_request

    wire = build_request(
        [{"role": "user", "content": "Synthetic two-create"}],
        _settings(mimi_route_mode="native"),
        agent_contract=True,
    )
    assert_collection_wire_schema(wire)


@pytest.mark.parametrize("privacy", [False, True, None, 0, "false"])
def test_observed_collection_privacy_field_stays_fatal_without_normalization(privacy):
    from app.agent.openrouter import CandidateContractError

    args = collection(2)
    args["entries"][1]["fields"]["is_private"] = privacy
    original = json.dumps(args, sort_keys=True)
    with pytest.raises(RouteContractError, match="^invalid_agent_terminal_payload$") as raised:
        parse_agent_completion(payload([call(COLLECTION_CANDIDATE_TOOL, args)]))
    assert not isinstance(raised.value, CandidateContractError)
    issues = raised.value.__cause__.errors(include_input=False)
    assert any(
        str(issue.get("ctx", {}).get("error")) == "task_collection_field_not_authorized"
        for issue in issues
    )
    assert json.dumps(args, sort_keys=True) == original


def test_collection_guidance_pin_keeps_only_known_checkpoint_predecessors():
    from app.agent.policy import checkpoint_policy_compatible, load_standard_policy

    current = load_standard_policy(collection_enabled=True)
    previous = "c44ab32f8d41643f219a85cd8dda5371fbdf254410c89f92c281e8a44ea3561e"
    assert current.sha256 != previous and "Omit is_private entirely, even false" in current.text
    assert checkpoint_policy_compatible(previous, collection_enabled=True)
    assert checkpoint_policy_compatible(current.sha256, collection_enabled=True)
    assert not checkpoint_policy_compatible(previous, collection_enabled=False)
    assert not checkpoint_policy_compatible("0" * 64, collection_enabled=True)
