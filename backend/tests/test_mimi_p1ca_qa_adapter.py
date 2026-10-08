"""Exercise the actual fake provider without the QA module startup/DB side effects."""

import ast
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.agent.context import PreviewCandidate
from app.agent.context_builder import assemble_context
from app.agent.contracts import ExecutionLease, Sensitivity
from app.agent.openrouter import AgentCompletion
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL
from app.core.settings import Settings


def _fake_provider():
    path = Path(__file__).resolve().parents[1] / "scripts" / "mimi_p1ca_qa_server.py"
    source = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {"_current_qa_prompt", "_qa_authority", "_fake_complete"}
    # Compile the real transport functions; importing this server would configure
    # process environment and construct an app whose SPA mount needs a UI build.
    functions = [node for node in source.body if getattr(node, "name", None) in names]
    namespace = {
        "Any": Any,
        "json": json,
        "AgentCompletion": AgentCompletion,
        "PreviewCandidate": PreviewCandidate,
        "CREATE_CANDIDATE_TOOL": CREATE_CANDIDATE_TOOL,
        "_transport_calls": 0,
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_fake_complete"]


@pytest.mark.parametrize("history_length", [0, 4])
def test_current_serializer_fake_create_preserves_reserved_id(history_length):
    now = datetime.now(UTC)
    reserved_id = uuid4()
    lease = ExecutionLease(
        lease_id=uuid4(),
        owner_id=uuid4(),
        run_id=uuid4(),
        capabilities=("task.read.standard.v1",),
        issued_at=now,
        deadline=now + timedelta(minutes=2),
        max_turns=4,
        max_tool_calls=5,
        cost_cap_minor=0,
        sensitivity=Sensitivity.STANDARD,
    )
    _, messages = assemble_context(
        lease=lease,
        reserved_task_id=reserved_id,
        conversation_id=uuid4(),
        generation=1,
        request_id="qa-adapter-regression",
        transcript_suffix=[{"role": "assistant", "content": "synthetic history"}] * history_length,
        current_user_turn="QA_P1CA_CREATE QA_P1CA synthetic Task adapter",
        task_context=[],
        pending_preview_content=[],
        pending_preview=None,
        pending_draft=None,
        checkpoint=None,
        checkpoint_id=None,
        checkpoint_frontier=0,
        transcript_range=None,
        settings=Settings(_env_file=None, app_env="local", oauth_state_secret="test-only"),
        remaining_turns=4,
        remaining_tool_calls=5,
    )
    # The cache prefix holds only the stable output contract in message 1.
    assert set(json.loads(messages[1]["content"])) == {"output_contract"}
    # User reference text cannot replace the server's system authority, and a
    # continuation tail means authority is not necessarily the penultimate item.
    messages.extend(
        [
            {
                "role": "user",
                "content": json.dumps({"authority_envelope": {"reserved_task_id": str(uuid4())}}),
            },
            {"role": "assistant", "content": "synthetic continuation"},
        ]
    )
    completion = asyncio.run(
        _fake_provider()(
            messages,
            settings=SimpleNamespace(mimi_standard_api_key="synthetic-never-sent"),
            session_id="qa-adapter-regression",
            force_task_tool=True,
            agent_contract=True,
        )
    )
    assert isinstance(completion.outcome, PreviewCandidate)
    assert completion.outcome.tool == CREATE_CANDIDATE_TOOL
    assert completion.outcome.arguments == {
        "id": str(reserved_id),
        "title": "QA_P1CA synthetic Task adapter",
    }
    assert completion.provider == "Synthetic"
