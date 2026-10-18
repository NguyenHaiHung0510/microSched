"""P3 pair safety/frontier/measurement contracts, no database or egress."""

import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent.compaction import (
    CheckpointSource,
    make_semantic_checkpoint,
    validate_checkpoint,
)
from app.agent.observations import context_revision, prompt_observation
from app.agent.working_context import WorkingHistory, exact_pairs, projection_body, validate_body
from app.core.settings import Settings


def pairs(identity="read"):
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": identity,
                    "type": "function",
                    "function": {
                        "name": "task.query.v1",
                        "arguments": '{"filter":{"status":"open"},"projection":["title"]}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": identity,
            "content": (
                '{"count":0,"coverage":"complete","data_as_of":"2026-10-18T10:00:00Z","rows":[]}'
            ),
        },
    ]


def row(sequence, role="assistant"):
    text = "Chỉ đọc Task mẫu, chưa ghi thay đổi"
    return SimpleNamespace(
        id=uuid4(),
        sequence=sequence,
        role=role,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        content=text,
    )


def test_projection_keeps_exact_pairs_and_refs_without_canonical_prose_or_system_authority():
    user, assistant = row(1, "user"), row(2)
    raw = pairs()
    body = projection_body(
        user,
        assistant,
        raw + [{"role": "system", "content": "OLD LEASE"}],
        outcome="assistant_text",
        max_bytes=10000,
    )
    assert body["pairs"] == [raw]
    assert user.content not in json.dumps(body)
    assert "OLD LEASE" not in json.dumps(body)
    validate_body(body, user, assistant, max_bytes=10000)
    history = WorkingHistory(by_assistant={2: raw})
    decoded = [
        {"role": "user", "content": user.content},
        {"role": "assistant", "content": "Đã đọc"},
    ]
    wire = history.messages([user, assistant], decoded)
    assert wire == [decoded[0], *raw, decoded[1]]
    assert len([m for m in wire if m["role"] == "user"]) == 1


@pytest.mark.parametrize(
    "fault", ["orphan", "wrong_id", "duplicate", "reasoning", "tool", "oversize"]
)
def test_invalid_pair_fails_closed_as_one_segment(fault):
    raw = pairs()
    limit = 10000
    if fault == "orphan":
        raw = raw[:1]
    elif fault == "wrong_id":
        raw[1]["tool_call_id"] = "different"
    elif fault == "duplicate":
        raw += pairs()
    elif fault == "reasoning":
        raw[0]["reasoning"] = "hidden"
    elif fault == "tool":
        raw[0]["tool_calls"][0]["function"]["name"] = "shell"
    elif fault == "oversize":
        limit = 10
    with pytest.raises((ValueError, TypeError)):
        exact_pairs(raw, max_bytes=limit)


def test_compaction_binds_whole_working_unit_frontier_and_keeps_source_provenance():
    user, assistant = row(1, "user"), row(2)
    reference = {
        "event_id": str(uuid4()),
        "run_id": str(uuid4()),
        "sequence": 7,
        "message_sequence": 2,
        "sha256": "a" * 64,
        "storage_sha256": "b" * 64,
    }
    sources = [
        CheckpointSource(user.id, 1, "user", user.content_sha256, user.content),
        CheckpointSource(
            assistant.id,
            2,
            "assistant",
            assistant.content_sha256,
            assistant.content,
            {"ref": reference, "messages": pairs()},
        ),
    ]
    checkpoint = make_semantic_checkpoint(
        sources=sources,
        prior=None,
        policy_sha256="c" * 64,
        pending_preview={"id": "pending-ref"},
        pending_draft=None,
        current_user_source=None,
        candidate={
            "summary": "Đã đọc Task mẫu; dữ liệu lúc 18/10, chưa áp dụng; còn chờ quyết định.",
            "constraints": [],
            "supersessions": [],
            "resolutions": [],
        },
    )
    assert checkpoint["working_sources"] == [reference]
    assert checkpoint["working_frontier"]["message_sequence"] == 2
    assert checkpoint["pending_preview"] == {"id": "pending-ref"}
    checkpoint["working_frontier"]["message_sequence"] = 1
    with pytest.raises(ValueError, match="checkpoint_working_frontier_invalid"):
        validate_checkpoint(checkpoint, expected_sources=sources, prior=None)


def test_measurement_lineage_survives_new_output_but_not_compaction_or_request_tamper():
    settings = Settings(_env_file=None, app_env="local", oauth_state_secret="synthetic")
    revision = context_revision(settings, 1, None)
    call = SimpleNamespace(
        id=uuid4(),
        state="succeeded",
        request_fingerprint="a" * 64,
        usage={"prompt_tokens": 272001},
        route={
            "kind": "openrouter",
            "purpose": "main",
            "mode": "native",
            "context_revision": revision,
            "model": "model",
            "actual_model": "model",
            "actual_provider": "provider",
            "input_projection": {
                "version": 1,
                "request_fingerprint": "a" * 64,
                "projection_fingerprint": "b" * 64,
                "checkpoint_id": None,
                "message_frontier": 0,
                "model": "model",
            },
        },
    )
    observation = prompt_observation(call, revision, require_projection=True)
    assert observation["eligible"] and observation["should_compact"]
    # New output/user changes next-unsent projection; old reading still informs compact lineage.
    assert prompt_observation(call, revision, require_projection=True)["should_compact"]
    assert not prompt_observation(call, revision, checkpoint_id=uuid4(), require_projection=True)[
        "eligible"
    ]
    call.request_fingerprint = "tampered"
    assert not prompt_observation(call, revision, require_projection=True)["eligible"]


def test_wire_measurement_matches_actual_transport_options_and_retains_last_native_on_failure():
    from test_mimi_context import _context

    from app.agent.context_builder import input_projection_observation
    from app.agent.observations import conversation_metrics
    from app.agent.openrouter import build_request
    from app.agent.working_context import digest

    settings = Settings(
        _env_file=None,
        app_env="local",
        oauth_state_secret="synthetic",
        mimi_standard_api_key="synthetic-never-sent",
        mimi_route_mode="native",
        mimi_route_model="synthetic/model",
        mimi_route_max_input_price=1,
        mimi_route_max_output_price=1,
        mimi_route_forced_tool_choice="function",
    )
    envelope, messages = _context(settings=settings)
    binding = input_projection_observation(
        envelope,
        messages,
        settings=settings,
        session_id="synthetic-session",
        stream=True,
        force_task_tool=True,
    )
    wire = build_request(
        messages,
        settings,
        agent_contract=True,
        session_id="synthetic-session",
        stream=True,
        force_task_tool=True,
    )
    assert binding["request_fingerprint"] == digest(wire)
    revision = context_revision(settings, 1, None)
    call = SimpleNamespace(
        id=uuid4(),
        state="failed",
        request_fingerprint=digest(wire),
        usage={"prompt_tokens": 272001},
        route={
            "kind": "openrouter",
            "purpose": "main",
            "mode": "native",
            "model": settings.mimi_route_model,
            "actual_model": settings.mimi_route_model,
            "actual_provider": "Synthetic",
            "context_revision": revision,
            "input_projection": binding,
        },
    )
    assert prompt_observation(call, revision, require_projection=True)["should_compact"]
    call.result = {}
    metrics = conversation_metrics([call], [], [], as_of="now", scope_start="start")
    assert metrics["last_measured_input"]["tokens"] == 272001
    assert metrics["last_measured_input"]["request_fingerprint"] == digest(wire)
    assert metrics["context_policy"]["compaction_trigger_tokens"] == 272000
    call.route["dispatch_not_started"] = True
    assert not prompt_observation(call, revision, require_projection=True)["eligible"]


def test_historical_read_is_not_current_run_progress_or_collision_replayed():
    from app.agent.loop import ReadProgress

    old = pairs()
    history = WorkingHistory(
        by_assistant={2: old, 4: pairs()}, refs={2: {"ref": "first"}, 4: {"ref": "second"}}
    )
    rows = [row(1, "user"), row(2), row(3, "user"), row(4)]
    wire = history.messages(rows, [{"role": r.role, "content": str(r.sequence)} for r in rows])
    assert sum(m.get("role") == "tool" for m in wire) == 1
    assert "historical_tool_call_id_collision" in history.gaps
    assert 4 not in history.refs and history.source(4) is None
    progress = ReadProgress([*old, {"role": "user", "content": "Current turn"}])
    args = json.loads(old[0]["tool_calls"][0]["function"]["arguments"])
    result = json.loads(old[1]["content"])
    assert not progress.observe("task.query.v1", args, result)
    assert progress.observe("task.query.v1", args, result)
