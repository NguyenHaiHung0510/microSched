"""Focused deterministic contract matrix for P1C parsing and bounded reads."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.agent.context import (
    TERMINAL_ADAPTER,
    AssistantText,
    Blocked,
    Clarification,
    Draft,
    PreviewCandidate,
    ToolRequest,
    ToolRequests,
)
from app.agent.context_builder import assemble_context, rebind_after_read
from app.agent.contracts import ExecutionLease, Sensitivity
from app.agent.loop import LoopLimits, run_read_loop
from app.agent.openrouter import AgentCompletion, ProviderDispatchError
from app.core.settings import Settings


def _completion(outcome):
    return AgentCompletion(
        outcome=outcome,
        response_id="p1c-contract-matrix",
        usage={},
        provider=None,
        model=None,
    )


def _context():
    now = datetime.now(UTC)
    lease = ExecutionLease(
        lease_id=uuid4(),
        owner_id=uuid4(),
        run_id=uuid4(),
        capabilities=("task.read.standard.v1",),
        issued_at=now,
        deadline=now + timedelta(minutes=2),
        max_turns=8,
        max_tool_calls=6,
        cost_cap_minor=0,
        sensitivity=Sensitivity.STANDARD,
    )
    return assemble_context(
        lease=lease,
        reserved_task_id=uuid4(),
        conversation_id=uuid4(),
        generation=1,
        request_id="p1c-contract-matrix",
        transcript_suffix=[],
        current_user_turn="Đọc tiếp các trang Task",
        task_context=[],
        pending_preview_content=[],
        pending_preview=None,
        pending_draft=None,
        checkpoint=None,
        checkpoint_id=None,
        checkpoint_frontier=0,
        transcript_range=None,
        settings=Settings(app_env="local", oauth_state_secret="test-only"),
        remaining_turns=8,
        remaining_tool_calls=6,
    )


@pytest.mark.parametrize(
    "payload, expected_type",
    [
        ({"kind": "assistant_text", "text": "x"}, AssistantText),
        ({"kind": "clarification", "question": "x"}, Clarification),
        ({"kind": "draft", "text": "x"}, Draft),
        (
            {
                "kind": "preview_candidate",
                "tool": "task.create_candidate.v2",
                "arguments": {},
            },
            PreviewCandidate,
        ),
        ({"kind": "blocked", "reason": "x"}, Blocked),
        (
            {
                "kind": "tool_requests",
                "requests": [{"call_id": "c1", "name": "task.query.v1", "arguments": {}}],
            },
            ToolRequests,
        ),
    ],
)
def test_full_terminal_union_parses(payload, expected_type):
    assert isinstance(TERMINAL_ADAPTER.validate_python(payload), expected_type)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "assistant_text", "text": "x", "unexpected": True},
        {"kind": "unknown", "text": "x"},
        {
            "kind": "tool_requests",
            "requests": [
                {
                    "call_id": "c1",
                    "name": "task.query.v1",
                    "arguments": {},
                    "extra": "forbidden",
                }
            ],
        },
    ],
)
def test_terminal_union_rejects_unknown_or_extra_fields(payload):
    with pytest.raises(ValueError):
        TERMINAL_ADAPTER.validate_python(payload)


@pytest.mark.parametrize("page_count", range(1, 7))
def test_bounded_read_pages_rebind_provenance_and_remaining_budget(page_count):
    async def scenario():
        envelope, messages = _context()
        model_turn = 0
        reads = []
        query_pages_requested = 0

        async def invoke(current_messages, turn):
            nonlocal model_turn, query_pages_requested
            model_turn += 1
            assert current_messages
            if query_pages_requested < min(page_count, 3):
                page = query_pages_requested + 1
                if page > 1:
                    assert any(
                        f'"call_id":"page-{page - 1}"' in str(message.get("content", ""))
                        for message in current_messages
                    )
                requests = [
                    ToolRequest(
                        call_id=f"page-{page}",
                        name="task.query.v1",
                        arguments={"cursor": None if page == 1 else f"c{page}"},
                    )
                ]
                query_pages_requested += 1
                extra_count = max(0, page_count - 3)
                if page == 2:
                    extra_batch = min(2, extra_count)
                elif page == 3:
                    extra_batch = extra_count - min(2, extra_count)
                else:
                    extra_batch = 0
                for index in range(extra_batch):
                    extra_number = len(reads) + index + 1
                    extra_name = (
                        "task.aggregate.v1" if extra_number % 2 else "task.inspect_batch.v1"
                    )
                    extra_arguments = (
                        {
                            "filter": {
                                "status": None,
                                "priority": None,
                                "due_from": None,
                                "due_through": None,
                                "title_contains": None,
                            },
                            "group_by": ("status", "priority", "due_precision")[
                                (extra_number // 2) % 3
                            ],
                        }
                        if extra_name == "task.aggregate.v1"
                        else {"ids": [str(uuid4())], "projection": ["id"]}
                    )
                    requests.append(
                        ToolRequest(
                            call_id=f"extra-{extra_number}",
                            name=extra_name,
                            arguments=extra_arguments,
                        )
                    )
                return _completion(ToolRequests(requests=tuple(requests)))
            return _completion(AssistantText(text="Đã đọc xong phạm vi."))

        async def execute(name, arguments):
            page = len(reads) + 1
            reads.append((name, arguments))
            return {
                "rows": [{"id": f"task-{page}", "source_version": f"v{page}"}],
                "count": 1,
                "coverage": "partial" if page < page_count else "complete",
                "omitted_fields": ["body_md"],
                "next_cursor": f"c{page + 1}" if page < page_count else None,
                "data_as_of": datetime.now(UTC).isoformat(),
            }

        async def update(
            current_messages, name, call_id, arguments, result, remaining_turns, remaining_calls
        ):
            nonlocal envelope
            envelope, rebound = rebind_after_read(
                envelope,
                current_messages,
                tool_name=name,
                call_id=call_id,
                arguments=arguments,
                result=result,
                remaining_turns=remaining_turns,
                remaining_tool_calls=remaining_calls,
            )
            return rebound

        limits = LoopLimits(
            max_turns=4,
            max_tool_calls=6,
            max_serialized_bytes=100_000,
            deadline=datetime.now(UTC) + timedelta(seconds=10),
        )
        result = await run_read_loop(
            messages,
            limits=limits,
            invoke_model=invoke,
            execute_read=execute,
            on_context_update=update,
        )
        assert isinstance(result.outcome, AssistantText)
        assert len(reads) == page_count
        assert result.turns <= 4
        query_reads = [(name, arguments) for name, arguments in reads if name == "task.query.v1"]
        assert [arguments["cursor"] for _, arguments in query_reads] == [
            None if page == 1 else f"c{page}" for page in range(1, min(page_count, 3) + 1)
        ]
        sources = envelope.manifest.sources[-page_count:]
        assert len(sources) == page_count
        for index, source in enumerate(sources, start=1):
            payload = {
                "rows": [{"id": f"task-{index}", "source_version": f"v{index}"}],
                "count": 1,
                "coverage": "partial" if index < page_count else "complete",
                "omitted_fields": ["body_md"],
                "next_cursor": f"c{index + 1}" if index < page_count else None,
                "data_as_of": source.data_as_of.isoformat(),
            }
            assert (
                source.content_sha256
                == hashlib.sha256(
                    json.dumps(
                        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
            )
            assert source.omitted_fields == ("body_md",)
            assert source.coverage == ("partial" if index < page_count else "complete")
            assert source.next_cursor == (f"c{index + 1}" if index < page_count else None)
        assert envelope.authority.remaining_tool_calls == 6 - page_count
        assert envelope.manifest.budget.remaining_tool_calls == 6 - page_count
        remaining_turns_after_last_read = 4 - min(page_count, 3)
        assert envelope.authority.remaining_turns == remaining_turns_after_last_read
        assert envelope.manifest.budget.remaining_turns == remaining_turns_after_last_read
        assert result.tool_calls == page_count

    asyncio.run(scenario())


def test_model_timeout_after_dispatch_is_unknown_and_not_retried():
    async def scenario():
        dispatches = 0

        async def invoke(messages, turn):
            nonlocal dispatches
            dispatches += 1
            await asyncio.sleep(1)

        async def execute(name, arguments):
            pytest.fail("no read may run after model timeout")

        with pytest.raises(ProviderDispatchError, match="ended as unknown") as raised:
            await run_read_loop(
                [],
                limits=LoopLimits(
                    max_turns=3,
                    max_tool_calls=3,
                    max_serialized_bytes=10_000,
                    deadline=datetime.now(UTC) + timedelta(milliseconds=30),
                ),
                invoke_model=invoke,
                execute_read=execute,
            )
        assert raised.value.outcome == "unknown"
        assert dispatches == 1

    asyncio.run(scenario())
