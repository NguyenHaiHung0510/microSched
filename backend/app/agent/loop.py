"""Finite Mimi read loop; domain writes never execute in this module."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError

from app.agent.context import Blocked, TerminalOutcome, ToolRequests
from app.agent.openrouter import (
    AgentCompletion,
    CandidateContractError,
    ProviderDispatchError,
    RouteContractError,
    serialized_input_bytes,
)
from app.agent.tools.registry import READ_TOOLS, validate_read_arguments

InvokeModel = Callable[[list[dict[str, Any]], int], Awaitable[AgentCompletion]]
ExecuteRead = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
StageSink = Callable[[str, dict[str, Any]], Awaitable[None]]
ContextUpdate = Callable[
    [list[dict[str, Any]], str, str, dict[str, Any], dict[str, Any], int, int],
    Awaitable[list[dict[str, Any]]],
]


@dataclass(frozen=True)
class LoopLimits:
    max_turns: int
    max_tool_calls: int
    max_serialized_bytes: int
    deadline: datetime

    def __post_init__(self) -> None:
        if min(self.max_turns, self.max_tool_calls, self.max_serialized_bytes) < 1:
            raise ValueError("mimi_loop_limits_invalid")


@dataclass(frozen=True)
class LoopResult:
    outcome: TerminalOutcome
    completion: AgentCompletion | None
    turns: int
    tool_calls: int
    messages: tuple[dict[str, Any], ...]
    stop_code: Literal["deadline_exceeded", "budget_exceeded", "no_progress"] | None = None

    @property
    def producer_code(self):
        return "agent_loop_stop" if self.stop_code else "provider_text"


FINAL_MARKER = "MIMI_SERVER_FINAL_ANSWER_ONLY_V1"


def messages_final_only(messages):
    return bool(
        messages
        and messages[-1].get("role") == "system"
        and messages[-1].get("content", "").startswith(FINAL_MARKER)
    )


def finalization_messages(messages, reason, not_run=()):
    return [
        *messages,
        {
            "role": "system",
            "content": FINAL_MARKER
            + " "
            + _canonical_json(
                {
                    "reason": reason,
                    "not_run_reads": list(not_run),
                    "instruction": (
                        "Return an honest Vietnamese final/partial answer from completed reads. "
                        "Keep exact selection/page/alias obligations and provenance. "
                        "No more tool calls or proposals. Rejected candidates created no preview "
                        "and wrote no Task; preserve the server's pending preview state. When "
                        "candidate_no_progress, explain the unresolved shape/date limitation; "
                        "do not claim success or ask the user to repeat the same request as a fix."
                    ),
                }
            ),
        },
    ]


def validate_fanout(outcome: ToolRequests) -> dict[str, Any] | None:
    """Reject names fatally; return bounded feedback for a wholly unexecuted bad batch."""
    # Check every name first: a bad schema cannot mask an unauthorized sibling.
    if any(request.name not in READ_TOOLS for request in outcome.requests):
        raise RouteContractError("model_requested_non_read_tool_in_loop")
    invalid = set()
    for request in outcome.requests:
        try:
            validate_read_arguments(request.name, request.arguments)
        except ValidationError:
            invalid.add(request.name)
    if invalid:
        # Never echo input, validator messages or arbitrary field names. These
        # tool names come only from the fixed read allowlist, not model strings.
        return {
            "role": "system",
            "content": _canonical_json(
                {
                    "error": {
                        "code": "invalid_read_arguments",
                        "message": (
                            "The entire read batch was rejected before execution. No reads or "
                            "selections ran; this supplies no data, IDs, versions, membership or "
                            "coverage. Correct arguments for the listed tools using their leased "
                            "schemas and actual prior read receipts, then resubmit the needed "
                            "batch. Do not invent missing values. Each correction uses a normal "
                            "model turn within the existing run limits."
                        ),
                    },
                    "invalid_tools": sorted(invalid),
                    "coverage": "unavailable",
                }
            ),
        }
    return None


def candidate_correction_feedback(error: CandidateContractError):
    """Static schema guidance only: no rejected args, IDs, evidence or authority."""
    return {
        "role": "system",
        "content": _canonical_json(
            {
                "error": {"code": str(error)},
                "issues": list(error.issues),
                "repair_signature": candidate_repair_signature(error),
                "instruction": (
                    "The entire candidate turn was rejected before reads, selections or preview. "
                    "No Task was written; the existing pending preview is unchanged. Correct the "
                    "whole proposal using only leased schemas and actual prior read receipts. "
                    "For multiple new Tasks use ONE task.collection_candidate.v1 call with one "
                    "action=create entry per requested Task, selection_id=null and no existing IDs "
                    "or versions. Never drop requested Tasks or split confirmation. Complete any "
                    "needed reads/selection in a separate read-only turn before a candidate-only "
                    "turn. Collection fields contain title/body_md/status/priority/pinned and the "
                    "complete due_precision/due_on/due_at triad when scheduled. "
                    "Use fields.title for every create. For a civil date use due_precision=date, "
                    "due_on=YYYY-MM-DD, due_at=null; datetime requires a timezone and "
                    "due_on=null; none uses two null siblings. Never clamp an invalid date: "
                    "correct serialization from the supplied facts or clarify invalid facts. "
                    "Checklist operations belong in children, not fields.items. "
                    "Do not invent IDs or fields. "
                    "A correction consumes a normal model turn under the existing limits. If you "
                    "cannot correct safely, clarify or state the limitation; never claim success."
                ),
            }
        ),
    }


def candidate_repair_signature(error):
    # A changed title/prose or call ID is not schema progress. Changed issue paths
    # are progress; a valid candidate is accepted normally, without a retry cap.
    return hashlib.sha256(
        _canonical_json(
            {
                "code": str(error),
                "tools": sorted(error.tool_names),
                "issues": error.issues,
            }
        ).encode()
    ).hexdigest()


def candidate_repair_repeated(messages, error):
    signature = candidate_repair_signature(error)
    current = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    for message in messages[current + 1 :]:
        if message.get("role") != "system":
            continue
        try:
            body = json.loads(message.get("content", ""))
        except TypeError, ValueError:
            continue
        if isinstance(body, dict) and body.get("repair_signature") == signature:
            return True
    return False


def restored_candidate_final_reason(messages):
    """Recover only from app-verified same-run system feedback, never user text."""
    seen = set()
    current = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    for message in messages[current + 1 :]:
        if message.get("role") != "system":
            continue
        try:
            body = json.loads(message.get("content", ""))
        except TypeError, ValueError:
            continue
        signature = body.get("repair_signature") if isinstance(body, dict) else None
        if isinstance(signature, str) and len(signature) == 64:
            if signature in seen:
                return "candidate_no_progress"
            seen.add(signature)
    return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


class ReadProgress:
    """Same-run reads refresh evidence; repeated unchanged results remain bounded.

    A duplicate gets actionable feedback before it can contribute to a stop. We
    evaluate the entire batch so a duplicate never masks a useful sibling read.
    Freeze is executed normally, never memoized; errors supply no authority.
    """

    def __init__(self, messages=()):
        self.results = {}
        self.unchanged_batch = False
        pending = {}
        # Earlier finalized turns are historical data, not reads made by this run.
        current_turn = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1
        )
        for message in messages[current_turn + 1 :]:
            for call in message.get("tool_calls", ()):
                pending[call["id"]] = call["function"]
            if message.get("role") == "tool" and message.get("tool_call_id") in pending:
                call = pending.pop(message["tool_call_id"])
                self.observe(
                    call["name"], json.loads(call["arguments"]), json.loads(message["content"])
                )

    def observe(self, name, arguments, result):
        fingerprint = _canonical_json({"name": name, "arguments": arguments})
        # Timestamp-only changes are not progress. Rows/versions/cursors/errors
        # remain part of the comparison; no snapshot or write authority is reused.
        evidence = _canonical_json({k: v for k, v in result.items() if k != "data_as_of"})
        digest = hashlib.sha256(evidence.encode()).hexdigest()
        duplicate = self.results.get(fingerprint) == digest
        self.results[fingerprint] = digest
        return duplicate


def duplicate_read_feedback():
    return {
        "role": "system",
        "content": _canonical_json(
            {
                "code": "duplicate_read_refreshed",
                "instruction": (
                    "The duplicate read ran again against current sources and consumed the normal "
                    "read allowance. Use actual result, IDs, versions and coverage; no older-run "
                    "receipt was promoted. An unchanged repeat is not progress. Continue useful "
                    "siblings, read missing IDs/pages or correct selection obligations; otherwise "
                    "give an honest partial answer and next step. Never narrow an all-scope "
                    "request "
                    "silently. Further unchanged batches may stop with no_progress."
                ),
            }
        ),
    }


async def run_read_loop(
    initial_messages: list[dict[str, Any]],
    *,
    limits: LoopLimits,
    invoke_model: InvokeModel,
    execute_read: ExecuteRead,
    on_stage: StageSink | None = None,
    on_context_update: ContextUpdate | None = None,
) -> LoopResult:
    """Execute validated reads only; return one terminal outcome or a truthful bound stop."""

    messages = list(initial_messages)
    progress = ReadProgress(messages)
    total_calls = 0
    last_completion: AgentCompletion | None = None
    final_reason = restored_candidate_final_reason(messages)
    for turn in range(1, limits.max_turns + 1):
        if datetime.now(UTC) >= limits.deadline:
            return LoopResult(
                Blocked(reason="Mimi đã chạm thời hạn lượt chạy; bạn có thể tiếp tục sau."),
                last_completion,
                turn - 1,
                total_calls,
                tuple(messages),
                "deadline_exceeded",
            )
        if final_reason or total_calls >= limits.max_tool_calls or turn == limits.max_turns:
            if not messages_final_only(messages):
                messages = finalization_messages(messages, final_reason or "reserved_final_turn")
        if serialized_input_bytes(messages, agent_contract=True) > limits.max_serialized_bytes:
            return LoopResult(
                Blocked(reason="Ngữ cảnh vượt giới hạn đã cấp; cần compact hoặc thu hẹp phạm vi."),
                last_completion,
                turn - 1,
                total_calls,
                tuple(messages),
                "budget_exceeded",
            )
        if on_stage:
            await on_stage("awaiting_model", {"turn": turn})
        remaining = (limits.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return LoopResult(
                Blocked(reason="Mimi đã chạm thời hạn lượt chạy; bạn có thể tiếp tục sau."),
                last_completion,
                turn - 1,
                total_calls,
                tuple(messages),
                "deadline_exceeded",
            )
        try:
            async with asyncio.timeout(remaining):
                completion = await invoke_model(messages, turn)
        except CandidateContractError as error:
            if not error.correction_ready or messages_final_only(messages):
                raise
            if candidate_repair_repeated(messages, error):
                final_reason = "candidate_no_progress"
            messages.append(candidate_correction_feedback(error))
            continue
        except TimeoutError as error:
            # A dispatched request may have reached the provider. Preserve the
            # unknown-outcome recovery path instead of claiming no call occurred.
            raise ProviderDispatchError("unknown", None) from error
        last_completion = completion
        outcome = completion.outcome
        if messages_final_only(messages) and outcome.kind == "preview_candidate":
            raise RouteContractError("model_violated_final_no_tools")
        if not isinstance(outcome, ToolRequests):
            return LoopResult(outcome, completion, turn, total_calls, tuple(messages))
        if messages_final_only(messages):
            if progress.unchanged_batch:
                return LoopResult(
                    Blocked(
                        reason="Đã chạm giới hạn lượt chạy mà các lần đọc vẫn không có "
                        "tiến triển. Chưa ghi thay đổi; cần sửa ID, trang hoặc phạm vi còn thiếu."
                    ),
                    completion,
                    turn,
                    total_calls,
                    tuple(messages),
                    "no_progress",
                )
            raise RouteContractError("model_violated_final_no_tools")
        feedback = validate_fanout(outcome)
        if feedback is not None:
            messages.append(feedback)
            continue
        allowance = max(0, limits.max_tool_calls - total_calls)
        not_run = outcome.requests[allowance:]
        if not_run:
            final_reason = "read_budget_exhausted"
            messages.append(
                {
                    "role": "system",
                    "content": _canonical_json(
                        {
                            "not_run_reads": [r.model_dump(mode="json") for r in not_run],
                            "reason": final_reason,
                        }
                    ),
                }
            )
        if on_stage:
            await on_stage("executing_read_tools", {"turn": turn, "count": len(outcome.requests)})
        stalled_batch = []
        duplicate_seen = False
        for request in outcome.requests[:allowance]:
            if datetime.now(UTC) >= limits.deadline:
                return LoopResult(
                    Blocked(reason="Mimi đã chạm thời hạn lượt chạy; bạn có thể tiếp tục sau."),
                    completion,
                    turn,
                    total_calls,
                    tuple(messages),
                    "deadline_exceeded",
                )
            if request.name not in READ_TOOLS:
                raise RouteContractError("model_requested_non_read_tool_in_loop")
            remaining = (limits.deadline - datetime.now(UTC)).total_seconds()
            try:
                async with asyncio.timeout(max(0, remaining)):
                    result = await execute_read(request.name, request.arguments)
            except TimeoutError:
                return LoopResult(
                    Blocked(reason="Mimi đã chạm thời hạn lượt chạy; bạn có thể tiếp tục sau."),
                    completion,
                    turn,
                    total_calls,
                    tuple(messages),
                    "deadline_exceeded",
                )
            duplicate = progress.observe(request.name, request.arguments, result)
            duplicate_seen |= duplicate
            stalled_batch.append(duplicate)
            total_calls += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": request.call_id,
                            "type": "function",
                            "function": {
                                "name": request.name,
                                "arguments": _canonical_json(request.arguments),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": request.call_id,
                    "content": _canonical_json(result),
                }
            )
            if on_context_update is not None:
                try:
                    messages = await on_context_update(
                        messages,
                        request.name,
                        request.call_id,
                        request.arguments,
                        result,
                        max(0, limits.max_turns - turn),
                        max(0, limits.max_tool_calls - total_calls),
                    )
                except RouteContractError:
                    raise
                except ValueError:
                    return LoopResult(
                        Blocked(reason="Ngữ cảnh vượt giới hạn; cần compact hoặc thu hẹp phạm vi."),
                        completion,
                        turn,
                        total_calls,
                        tuple(messages),
                        "budget_exceeded",
                    )
        progress.unchanged_batch = bool(stalled_batch) and all(stalled_batch)
        if duplicate_seen:
            messages.append(duplicate_read_feedback())
        if stalled_batch and all(stalled_batch) and total_calls >= limits.max_tool_calls:
            return LoopResult(
                Blocked(
                    reason="Công cụ đọc lặp lại cùng truy vấn mà không có tiến triển. "
                    "Chưa có thay đổi nào được ghi; cần sửa phạm vi, ID hoặc trang còn thiếu."
                ),
                completion,
                turn,
                total_calls,
                tuple(messages),
                "no_progress",
            )
    return LoopResult(
        Blocked(reason="Mimi đã dùng hết số vòng suy luận được cấp cho lượt này."),
        last_completion,
        limits.max_turns,
        total_calls,
        tuple(messages),
        "budget_exceeded",
    )
