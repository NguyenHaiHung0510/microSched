"""Bounded OpenRouter route adapter for Mimi's exact and adaptive lanes."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.core.settings import Settings, get_settings
from app.domain.tasks import TaskCreate


class RouteContractError(ValueError):
    """The selected route or terminal payload violated Mimi's frozen contract."""


class ProviderDispatchError(RuntimeError):
    """A provider call ended without a usable terminal result."""

    def __init__(
        self,
        outcome: Literal["retryable", "unknown", "failed"],
        status: int | None,
        *,
        response_id: str | None = None,
    ):
        super().__init__(f"provider dispatch ended as {outcome}")
        self.outcome = outcome
        self.status = status
        self.response_id = response_id


@dataclass(frozen=True)
class ProviderCompletion:
    kind: Literal["text", "task"]
    task: TaskCreate | None
    text: str | None
    response_id: str
    usage: dict[str, Any]
    provider: str | None
    model: str | None


ProviderEventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


TASK_CREATE_TOOL = {
    "type": "function",
    "function": {
        "name": "task.create.v1",
        "description": (
            "Propose one STANDARD microSched Task. The server still requires confirmation."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "id",
                "title",
                "body_md",
                "status",
                "priority",
                "due_precision",
                "due_on",
                "due_at",
                "is_private",
                "items",
            ],
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "body_md": {"type": ["string", "null"], "maxLength": 20_000},
                "status": {"const": "open"},
                "priority": {"type": ["string", "null"], "enum": ["p1", "p2", "p3", None]},
                "due_precision": {"enum": ["none", "date", "datetime"]},
                "due_on": {"type": ["string", "null"], "format": "date"},
                "due_at": {"type": ["string", "null"], "format": "date-time"},
                "is_private": {"const": False},
                "items": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {"type": "string", "minLength": 1, "maxLength": 500},
                },
            },
        },
    },
}


def _route_identity(settings: Settings) -> tuple[str, str]:
    if settings.mimi_standard_api_key is None or settings.mimi_route_model is None:
        raise RouteContractError("Mimi route key/model is not configured")
    return settings.mimi_standard_api_key, settings.mimi_route_model


def _price_policy(settings: Settings) -> dict[str, float]:
    if (
        settings.mimi_route_max_input_price is None
        or settings.mimi_route_max_output_price is None
    ):
        raise RouteContractError("Mimi route price caps are not configured")
    return {
        "prompt": settings.mimi_route_max_input_price,
        "completion": settings.mimi_route_max_output_price,
    }


def _provider_policy(settings: Settings) -> dict[str, Any]:
    shared: dict[str, Any] = {
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": settings.mimi_route_require_zdr,
        "max_price": _price_policy(settings),
    }
    if settings.mimi_route_mode == "exact":
        if settings.mimi_route_provider is None or settings.mimi_route_quantization is None:
            raise RouteContractError("exact Mimi route is not configured")
        return {
            **shared,
            "order": [settings.mimi_route_provider],
            "only": [settings.mimi_route_provider],
            "quantizations": [settings.mimi_route_quantization],
            "allow_fallbacks": False,
        }
    providers = list(settings.mimi_allowed_provider_list)
    quantizations = list(settings.mimi_allowed_quantization_list)
    if not providers or not quantizations:
        raise RouteContractError("adaptive Mimi route allowlists are not configured")
    # No `order` or `sort`: OpenRouter may use availability/price balancing and
    # sticky routing, but it can never leave these eligible endpoints.
    return {
        **shared,
        "only": providers,
        "quantizations": quantizations,
        "allow_fallbacks": True,
    }


def build_request(
    messages: list[dict[str, str]],
    settings: Settings | None = None,
    *,
    stream: bool = False,
    session_id: str | None = None,
    force_task_tool: bool = False,
) -> dict[str, Any]:
    """Build either the attributable exact lane or bounded adaptive dogfood lane."""
    route = settings or get_settings()
    _, model = _route_identity(route)
    serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # Conservative preflight: it may reject early but cannot make overflow safe.
    if len(serialized) + route.mimi_route_max_output_tokens > route.mimi_route_context_tokens:
        raise RouteContractError("context_overflow_preflight")
    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": [TASK_CREATE_TOOL],
        # Ordinary turns implement Mimi's terminal union. An explicit revision
        # of an existing preview is different: text claiming that a preview was
        # changed is not a state transition, so require the typed replacement.
        "tool_choice": (
            {"type": "function", "function": {"name": "task.create.v1"}}
            if force_task_tool
            else "auto"
        ),
        # OpenInference did not advertise `parallel_tool_calls`; omitting the
        # optional parameter keeps `require_parameters=true` routable while the
        # terminal parser independently enforces at most one tool call.
        "stream": stream,
        "store": False,
        "max_tokens": route.mimi_route_max_output_tokens,
        "reasoning": {"effort": route.mimi_route_reasoning_effort, "exclude": True},
        "usage": {"include": True},
        "provider": _provider_policy(route),
    }
    if stream:
        request["stream_options"] = {"include_usage": True}
    if session_id:
        request["session_id"] = session_id
    return request


def parse_completion(payload: dict[str, Any]) -> ProviderCompletion:
    """Accept ordinary assistant text XOR exactly one validated task proposal."""
    try:
        choices = payload["choices"]
        if len(choices) != 1:
            raise RouteContractError("provider_must_return_one_choice")
        message = choices[0]["message"]
        raw_content = message.get("content")
        content = raw_content.strip() if isinstance(raw_content, str) else ""
        calls = message.get("tool_calls") or []
        common = {
            "response_id": str(payload.get("id", "")),
            "usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
            "provider": (
                payload.get("provider") if isinstance(payload.get("provider"), str) else None
            ),
            "model": payload.get("model") if isinstance(payload.get("model"), str) else None,
        }
        # Some OpenAI-compatible providers emit a short narration alongside a
        # single tool call. The tool proposal is the only canonical terminal
        # result; discard the untrusted narration rather than failing an
        # otherwise valid preview. Multiple or unknown calls still fail below.
        if content and not calls:
            return ProviderCompletion(kind="text", task=None, text=content, **common)
        if len(calls) != 1 or calls[0]["function"]["name"] != "task.create.v1":
            raise RouteContractError("provider_must_return_text_or_one_task_create_call")
        arguments = calls[0]["function"]["arguments"]
        try:
            decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError as error:
            raise RouteContractError("provider_tool_arguments_not_json") from error
        if not isinstance(decoded, dict):
            raise RouteContractError("provider_tool_arguments_not_object")
        # P1 owns the lifecycle state. A provider has no legitimate choice for
        # this field, so normalize it at the trust boundary rather than letting
        # harmless casing/default drift turn a valid preview into a dead run.
        decoded = {**decoded, "status": "open"}
        # Providers sometimes populate both nullable schedule siblings despite
        # the strict schema. Precision is authoritative; clear only the sibling
        # that cannot be represented by that precision, while still requiring
        # the selected value itself to validate below.
        if decoded.get("due_precision") == "datetime":
            decoded["due_on"] = None
        elif decoded.get("due_precision") == "date":
            decoded["due_at"] = None
        elif decoded.get("due_precision") == "none":
            decoded["due_on"] = None
            decoded["due_at"] = None
        try:
            task = TaskCreate.model_validate(decoded)
        except ValidationError as error:
            first = error.errors(include_url=False, include_context=False, include_input=False)[0]
            location = "_".join(str(item) for item in first["loc"]) or "root"
            error_type = str(first["type"])
            raise RouteContractError(
                f"provider_task_schema_invalid_{location}_{error_type}"
            ) from error
    except RouteContractError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RouteContractError("invalid_provider_terminal_payload") from error
    if task.is_private:
        raise RouteContractError("standard_route_proposed_private_task")
    if task.id is None:
        raise RouteContractError("provider_task_id_missing")
    return ProviderCompletion(kind="task", task=task, text=None, **common)


def _raise_for_status(status_code: int) -> None:
    if status_code in {408, 409}:
        raise ProviderDispatchError("unknown", status_code)
    if status_code == 429 or status_code >= 500:
        raise ProviderDispatchError("retryable", status_code)
    if status_code >= 400:
        raise ProviderDispatchError("failed", status_code)


async def complete(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    session_id: str | None = None,
    force_task_tool: bool = False,
) -> ProviderCompletion:
    """Dispatch once. Retry authority belongs to persisted run state."""
    route = settings or get_settings()
    api_key, _ = _route_identity(route)
    request = build_request(
        messages,
        route,
        session_id=session_id,
        force_task_tool=force_task_tool,
    )
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(float(route.mimi_run_deadline_seconds), connect=10.0)
    )
    try:
        try:
            response = await active_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-OpenRouter-Metadata": "enabled",
                },
                json=request,
            )
        except httpx.ConnectError as error:
            raise ProviderDispatchError("retryable", None) from error
        except httpx.TimeoutException as error:
            raise ProviderDispatchError("unknown", None) from error
        _raise_for_status(response.status_code)
        try:
            payload = response.json()
        except ValueError as error:
            raise RouteContractError("provider_terminal_payload_is_not_json") from error
        if not isinstance(payload, dict):
            raise RouteContractError("provider_terminal_payload_is_not_an_object")
        return parse_completion(payload)
    finally:
        if owns_client:
            await active_client.aclose()


async def complete_stream(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    session_id: str | None = None,
    on_event: ProviderEventSink | None = None,
    force_task_tool: bool = False,
) -> ProviderCompletion:
    """Normalize OpenRouter SSE without exposing raw chunks or partial tool JSON."""
    route = settings or get_settings()
    api_key, _ = _route_identity(route)
    request = build_request(
        messages,
        route,
        stream=True,
        session_id=session_id,
        force_task_tool=force_task_tool,
    )
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(float(route.mimi_run_deadline_seconds), connect=10.0)
    )
    content_parts: list[str] = []
    tool_calls: dict[int, dict[str, str]] = {}
    response_id = ""
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] = {}
    started_at = time.perf_counter()
    connected_at: float | None = None
    first_output_at: float | None = None
    try:
        try:
            async with active_client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-OpenRouter-Metadata": "enabled",
                },
                json=request,
            ) as response:
                _raise_for_status(response.status_code)
                connected_at = time.perf_counter()
                if on_event:
                    await on_event("provider.connected", {"status": response.status_code})
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError as error:
                        raise RouteContractError("provider_stream_chunk_is_not_json") from error
                    if not isinstance(chunk, dict):
                        raise RouteContractError("provider_stream_chunk_is_not_an_object")
                    if isinstance(chunk.get("id"), str):
                        response_id = chunk["id"]
                    if isinstance(chunk.get("provider"), str):
                        provider = chunk["provider"]
                    if isinstance(chunk.get("model"), str):
                        model = chunk["model"]
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta")
                    if not isinstance(delta, dict):
                        continue
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        if first_output_at is None:
                            first_output_at = time.perf_counter()
                        content_parts.append(text)
                        if on_event:
                            await on_event("assistant.delta", {"text": text})
                    raw_calls = delta.get("tool_calls")
                    if isinstance(raw_calls, list):
                        for raw_call in raw_calls:
                            if not isinstance(raw_call, dict):
                                continue
                            index = raw_call.get("index", 0)
                            if not isinstance(index, int):
                                raise RouteContractError("provider_tool_call_index_invalid")
                            target = tool_calls.setdefault(index, {"name": "", "arguments": ""})
                            function = raw_call.get("function")
                            if isinstance(function, dict):
                                if isinstance(function.get("name"), str):
                                    target["name"] += function["name"]
                                if isinstance(function.get("arguments"), str):
                                    target["arguments"] += function["arguments"]
        except httpx.ConnectError as error:
            raise ProviderDispatchError("retryable", None) from error
        except (httpx.TimeoutException, httpx.ReadError) as error:
            raise ProviderDispatchError(
                "unknown", None, response_id=response_id or None
            ) from error
        completed_at = time.perf_counter()
        timing = {
            "duration_ms": round((completed_at - started_at) * 1000, 3),
            "connect_ms": (
                round((connected_at - started_at) * 1000, 3)
                if connected_at is not None
                else None
            ),
            "ttft_ms": (
                round((first_output_at - started_at) * 1000, 3)
                if first_output_at is not None
                else None
            ),
        }
        completion_tokens = usage.get("completion_tokens")
        if isinstance(completion_tokens, int) and completed_at > started_at:
            timing["output_tokens_per_second"] = round(
                completion_tokens / (completed_at - started_at), 3
            )
        usage = {**usage, "mimi_timing": timing}
        terminal_calls = [
            {"function": {"name": item["name"], "arguments": item["arguments"]}}
            for _, item in sorted(tool_calls.items())
        ]
        return parse_completion(
            {
                "id": response_id,
                "provider": provider,
                "model": model,
                "usage": usage,
                "choices": [
                    {
                        "message": {
                            "content": "".join(content_parts),
                            "tool_calls": terminal_calls,
                        }
                    }
                ],
            }
        )
    finally:
        if owns_client:
            await active_client.aclose()


async def get_generation(
    response_id: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Read OpenRouter's canonical generation metadata for reconciliation."""
    route = settings or get_settings()
    api_key, _ = _route_identity(route)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))
    try:
        try:
            response = await active_client.get(
                "https://openrouter.ai/api/v1/generation",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"id": response_id},
            )
        except httpx.ConnectError as error:
            raise ProviderDispatchError("retryable", None) from error
        except httpx.TimeoutException as error:
            raise ProviderDispatchError("unknown", None, response_id=response_id) from error
        _raise_for_status(response.status_code)
        try:
            payload = response.json()
        except ValueError as error:
            raise RouteContractError("provider_generation_payload_is_not_json") from error
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RouteContractError("provider_generation_payload_is_not_an_object")
        return data
    finally:
        if owns_client:
            await active_client.aclose()
