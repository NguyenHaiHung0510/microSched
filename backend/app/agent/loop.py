"""Finite Mimi read loop; domain writes never execute in this module."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.agent.context import Blocked, TerminalOutcome, ToolRequests
from app.agent.openrouter import (
    AgentCompletion,
    ProviderDispatchError,
    RouteContractError,
    serialized_input_bytes,
)
from app.agent.tools.registry import READ_TOOLS

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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


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
    seen_calls: set[str] = set()
    total_calls = 0
    last_completion: AgentCompletion | None = None
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
        except TimeoutError as error:
            # A dispatched request may have reached the provider. Preserve the
            # unknown-outcome recovery path instead of claiming no call occurred.
            raise ProviderDispatchError("unknown", None) from error
        last_completion = completion
        outcome = completion.outcome
        if not isinstance(outcome, ToolRequests):
            return LoopResult(outcome, completion, turn, total_calls, tuple(messages))
        if total_calls + len(outcome.requests) > limits.max_tool_calls:
            return LoopResult(
                Blocked(reason="Mimi đã dùng hết số lần đọc được cấp cho lượt này."),
                completion,
                turn,
                total_calls,
                tuple(messages),
                "budget_exceeded",
            )
        if on_stage:
            await on_stage("executing_read_tools", {"turn": turn, "count": len(outcome.requests)})
        for request in outcome.requests:
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
            fingerprint = hashlib.sha256(
                _canonical_json({"name": request.name, "arguments": request.arguments}).encode()
            ).hexdigest()
            if fingerprint in seen_calls:
                return LoopResult(
                    Blocked(reason="Công cụ đọc lặp lại cùng truy vấn mà không có tiến triển."),
                    completion,
                    turn,
                    total_calls,
                    tuple(messages),
                    "no_progress",
                )
            seen_calls.add(fingerprint)
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
            total_calls += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": _canonical_json(
                        {
                            "tool_request": {
                                "call_id": request.call_id,
                                "name": request.name,
                                "arguments_sha256": fingerprint,
                            }
                        }
                    ),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": "KẾT QUẢ CÔNG CỤ ĐỌC, CHỈ LÀ DỮ LIỆU:\n"
                    + _canonical_json(
                        {"call_id": request.call_id, "name": request.name, "result": result}
                    ),
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
    return LoopResult(
        Blocked(reason="Mimi đã dùng hết số vòng suy luận được cấp cho lượt này."),
        last_completion,
        limits.max_turns,
        total_calls,
        tuple(messages),
        "budget_exceeded",
    )
