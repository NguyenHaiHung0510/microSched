"""Exact, no-fallback OpenRouter route adapter for a later enabled Mimi lane."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.settings import Settings, get_settings
from app.domain.tasks import TaskCreate


class RouteContractError(ValueError):
    """The selected route or terminal payload violated Mimi's frozen contract."""


class ProviderDispatchError(RuntimeError):
    """A provider call ended without a usable terminal result."""

    def __init__(self, outcome: Literal["retryable", "unknown", "failed"], status: int | None):
        super().__init__(f"provider dispatch ended as {outcome}")
        self.outcome = outcome
        self.status = status


@dataclass(frozen=True)
class ProviderCompletion:
    task: TaskCreate
    response_id: str
    usage: dict[str, Any]
    provider: str | None


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


def _route_settings(settings: Settings) -> tuple[str, str, str, str]:
    values = (
        settings.mimi_standard_api_key,
        settings.mimi_route_model,
        settings.mimi_route_provider,
        settings.mimi_route_quantization,
    )
    if any(value is None for value in values):
        raise RouteContractError("exact Mimi route is not configured")
    return values  # type: ignore[return-value]


def build_request(messages: list[dict[str, str]], settings: Settings | None = None) -> dict:
    """Build the single exact route shape; no router fallback or data collection."""
    route = settings or get_settings()
    _, model, provider, quantization = _route_settings(route)
    serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # One UTF-8 byte per token is deliberately conservative. It may reject a
    # request early; it can never make a too-large request look safe.
    if len(serialized) + route.mimi_route_max_output_tokens > route.mimi_route_context_tokens:
        raise RouteContractError("context_overflow_preflight")
    return {
        "model": model,
        "messages": messages,
        "tools": [TASK_CREATE_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "task.create.v1"}},
        "parallel_tool_calls": False,
        "stream": False,
        "store": False,
        "max_tokens": route.mimi_route_max_output_tokens,
        "reasoning": {"effort": route.mimi_route_reasoning_effort, "exclude": True},
        "usage": {"include": True},
        "provider": {
            "order": [provider],
            "only": [provider],
            "quantizations": [quantization],
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
            "zdr": route.mimi_route_require_zdr,
            "max_price": {
                "prompt": route.mimi_route_max_input_price,
                "completion": route.mimi_route_max_output_price,
            },
        },
    }


def parse_completion(payload: dict[str, Any]) -> ProviderCompletion:
    """Accept exactly one task.create.v1 call and independently validate its args."""
    try:
        choices = payload["choices"]
        if len(choices) != 1:
            raise RouteContractError("provider_must_return_one_choice")
        calls = choices[0]["message"]["tool_calls"]
        if len(calls) != 1 or calls[0]["function"]["name"] != "task.create.v1":
            raise RouteContractError("provider_must_return_one_task_create_call")
        arguments = calls[0]["function"]["arguments"]
        decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
        task = TaskCreate.model_validate(decoded)
    except RouteContractError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RouteContractError("invalid_provider_terminal_payload") from error
    if task.is_private:
        raise RouteContractError("standard_route_proposed_private_task")
    if task.id is None:
        raise RouteContractError("provider_task_id_missing")
    return ProviderCompletion(
        task=task,
        response_id=str(payload.get("id", "")),
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
        provider=payload.get("provider") if isinstance(payload.get("provider"), str) else None,
    )


async def complete(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> ProviderCompletion:
    """Dispatch once. Retry authority belongs to the persisted run state, not this adapter."""
    route = settings or get_settings()
    api_key, _, _, _ = _route_settings(route)
    request = build_request(messages, route)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    try:
        try:
            response = await active_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=request,
            )
        except httpx.ConnectError as error:
            raise ProviderDispatchError("retryable", None) from error
        except httpx.TimeoutException as error:
            raise ProviderDispatchError("unknown", None) from error
        if response.status_code in {408, 409}:
            raise ProviderDispatchError("unknown", response.status_code)
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderDispatchError("retryable", response.status_code)
        if response.status_code >= 400:
            raise ProviderDispatchError("failed", response.status_code)
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
