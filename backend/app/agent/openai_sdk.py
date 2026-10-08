"""OpenAI Python SDK transport to OpenRouter for the explicit Mimi alpha lane."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    Timeout,
)

from app.agent.context import AssistantText
from app.agent.openrouter import (
    AgentCompletion,
    ProviderCompletion,
    ProviderDispatchError,
    ProviderEventSink,
    RouteContractError,
    _raise_for_status,
    _route_identity,
    build_request,
    parse_agent_completion,
    parse_compaction_completion,
    parse_completion,
)
from app.core.settings import Settings, get_settings

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_TIMEOUT_SECONDS = 120.0
_CONNECT_TIMEOUT_SECONDS = 10.0
_EXTRA_BODY_FIELDS = ("provider", "reasoning", "session_id", "usage")
_METADATA_HEADERS = {"X-OpenRouter-Metadata": "enabled"}


def _timeout(settings: Settings) -> Timeout:
    seconds = min(float(settings.mimi_run_deadline_seconds), _MAX_TIMEOUT_SECONDS)
    return Timeout(seconds, connect=_CONNECT_TIMEOUT_SECONDS)


def _client(settings: Settings, *, api_key: str, client: Any | None) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key,
        base_url=_OPENROUTER_BASE_URL,
        max_retries=0,
        timeout=_timeout(settings),
        default_headers=_METADATA_HEADERS,
        http_client=client,
    )


def _request_kwargs(request: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Keep the incumbent request shape while routing OpenRouter-only fields via extra_body."""
    body = dict(request)
    extra_body = {name: body.pop(name) for name in _EXTRA_BODY_FIELDS if name in body}
    return {
        **body,
        "extra_body": extra_body,
        "extra_headers": _METADATA_HEADERS,
        "timeout": _timeout(settings),
    }


def _completion_payload(result: Any) -> dict[str, Any]:
    payload = result.model_dump(mode="json", exclude_unset=True)
    if not isinstance(payload, dict):
        raise RouteContractError("provider_terminal_payload_is_not_an_object")
    return payload


def _raise_for_sdk_error(error: Exception, *, response_id: str | None = None) -> None:
    if isinstance(error, APIStatusError):
        try:
            _raise_for_status(error.status_code)
        except ProviderDispatchError as classified:
            if response_id:
                classified.response_id = response_id
            # The response body is provider-controlled and may echo prompts,
            # identities or credentials. Persist only a locally selected,
            # bounded category derived from the HTTP status.
            classified.diagnostic = {
                "category": (
                    "rate_limited"
                    if error.status_code == 429
                    else "provider_rejected"
                    if 400 <= error.status_code < 500
                    else "provider_unavailable"
                )
            }
            raise classified from error
    if isinstance(error, (APITimeoutError, APIConnectionError, APIError)):
        # The SDK exception does not prove whether OpenRouter began generation.
        raise ProviderDispatchError("unknown", None, response_id=response_id) from error
    raise error


async def complete(
    messages: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    client: Any | None = None,
    session_id: str | None = None,
    force_task_tool: bool = False,
    agent_contract: bool = False,
    summary_mode: bool = False,
) -> ProviderCompletion | AgentCompletion:
    """Send one non-streaming chat request with SDK retries disabled."""
    route = settings or get_settings()
    api_key, _ = _route_identity(route)
    request = build_request(
        messages,
        route,
        session_id=session_id,
        force_task_tool=force_task_tool,
        agent_contract=agent_contract,
        summary_mode=summary_mode,
    )
    sdk = _client(route, api_key=api_key, client=client)
    try:
        try:
            result = await sdk.chat.completions.create(**_request_kwargs(request, route))
        except asyncio.CancelledError as error:
            raise ProviderDispatchError("unknown", None) from error
        except (APIStatusError, APITimeoutError, APIConnectionError, APIError) as error:
            _raise_for_sdk_error(error)
        payload = _completion_payload(result)
        if summary_mode:
            return parse_compaction_completion(payload)
        return parse_agent_completion(payload) if agent_contract else parse_completion(payload)
    finally:
        if client is None:
            await sdk.close()


async def complete_stream(
    messages: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    client: Any | None = None,
    session_id: str | None = None,
    on_event: ProviderEventSink | None = None,
    force_task_tool: bool = False,
    agent_contract: bool = False,
    summary_mode: bool = False,
) -> ProviderCompletion | AgentCompletion:
    """Consume typed SDK chunks, buffer the terminal union, then expose text only."""
    route = settings or get_settings()
    api_key, _ = _route_identity(route)
    request = build_request(
        messages,
        route,
        stream=True,
        session_id=session_id,
        force_task_tool=force_task_tool,
        agent_contract=agent_contract,
        summary_mode=summary_mode,
    )
    sdk = _client(route, api_key=api_key, client=client)
    content_parts: list[str] = []
    tool_calls: dict[int, dict[str, str]] = {}
    response_id = ""
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] = {}
    started_at = time.perf_counter()
    connected_at: float | None = None
    first_output_at: float | None = None
    saw_finish_reason = False
    finish_reason: str | None = None
    try:
        try:
            stream = await sdk.chat.completions.create(**_request_kwargs(request, route))
        except asyncio.CancelledError as error:
            raise ProviderDispatchError("unknown", None) from error
        except (APIStatusError, APITimeoutError, APIConnectionError, APIError) as error:
            _raise_for_sdk_error(error)

        connected_at = time.perf_counter()
        if on_event:
            # The SDK returns a stream only after receiving a successful HTTP status.
            await on_event("provider.connected", {"status": 200})
        async with stream:
            async for sdk_chunk in stream:
                chunk = _completion_payload(sdk_chunk)
                provider_error = chunk.get("error")
                if provider_error is not None:
                    code = provider_error.get("code") if isinstance(provider_error, dict) else None
                    if isinstance(code, int) and code >= 400:
                        _raise_for_status(code)
                    raise RouteContractError("provider_stream_error_envelope")
                if isinstance(chunk.get("id"), str) and chunk["id"]:
                    if chunk["id"] != response_id:
                        response_id = chunk["id"]
                        if on_event:
                            await on_event(
                                "provider.response_identity", {"response_id": response_id}
                            )
                if isinstance(chunk.get("provider"), str):
                    provider = chunk["provider"]
                if isinstance(chunk.get("model"), str):
                    model = chunk["model"]
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                choices = chunk.get("choices")
                if not isinstance(choices, list):
                    raise RouteContractError("provider_stream_choices_invalid")
                if not choices:
                    continue
                if len(choices) != 1 or not isinstance(choices[0], dict):
                    raise RouteContractError("provider_stream_must_return_one_choice")
                if isinstance(choices[0].get("finish_reason"), str):
                    saw_finish_reason = True
                    finish_reason = choices[0]["finish_reason"]
                delta = choices[0].get("delta")
                if not isinstance(delta, dict):
                    continue
                text = delta.get("content")
                if isinstance(text, str) and text:
                    if first_output_at is None:
                        first_output_at = time.perf_counter()
                    content_parts.append(text)
                raw_calls = delta.get("tool_calls")
                if isinstance(raw_calls, list):
                    for raw_call in raw_calls:
                        if not isinstance(raw_call, dict):
                            continue
                        index = raw_call.get("index", 0)
                        if not isinstance(index, int):
                            raise RouteContractError("provider_tool_call_index_invalid")
                        target = tool_calls.setdefault(
                            index, {"id": "", "name": "", "arguments": ""}
                        )
                        if isinstance(raw_call.get("id"), str):
                            target["id"] += raw_call["id"]
                        function = raw_call.get("function")
                        if isinstance(function, dict):
                            if isinstance(function.get("name"), str):
                                target["name"] += function["name"]
                            if isinstance(function.get("arguments"), str):
                                target["arguments"] += function["arguments"]
        if not saw_finish_reason:
            raise ProviderDispatchError("unknown", None, response_id=response_id or None)
        if finish_reason not in {None, "stop", "tool_calls"}:
            raise RouteContractError("provider_stream_finish_reason_not_usable")
    except asyncio.CancelledError as error:
        raise ProviderDispatchError("unknown", None, response_id=response_id or None) from error
    except (APIStatusError, APITimeoutError, APIConnectionError, APIError) as error:
        _raise_for_sdk_error(error, response_id=response_id or None)
    finally:
        # Always close SDK-owned connections; cancellation is converted to an
        # unknown dispatch above so the durable receipt is committed for reconcile.
        if client is None:
            await sdk.close()

    completed_at = time.perf_counter()
    timing: dict[str, Any] = {
        "duration_ms": round((completed_at - started_at) * 1000, 3),
        "connect_ms": (
            round((connected_at - started_at) * 1000, 3) if connected_at is not None else None
        ),
        "ttft_ms": (
            round((first_output_at - started_at) * 1000, 3) if first_output_at is not None else None
        ),
    }
    completion_tokens = usage.get("completion_tokens")
    if isinstance(completion_tokens, int) and completed_at > started_at:
        timing["output_tokens_per_second"] = round(
            completion_tokens / (completed_at - started_at), 3
        )
    usage = {**usage, "mimi_timing": timing}
    terminal_calls = [
        {
            "id": item["id"],
            "function": {"name": item["name"], "arguments": item["arguments"]},
        }
        for _, item in sorted(tool_calls.items())
    ]
    parser = (
        parse_compaction_completion
        if summary_mode
        else (parse_agent_completion if agent_contract else parse_completion)
    )
    terminal_payload = {
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
    try:
        completion = parser(terminal_payload)
    except RouteContractError as error:
        # No request/headers/reasoning: only the buffered public terminal wire.
        error.terminal_receipt = terminal_payload
        raise
    is_text = (
        isinstance(completion, AgentCompletion) and isinstance(completion.outcome, AssistantText)
    ) or (isinstance(completion, ProviderCompletion) and completion.kind == "text")
    # Agent text is delivered by the app's canonical terminal snapshot after
    # pause/lease/checkpoint validation. Buffered SDK chunks are not an app
    # delivery receipt and must not bypass that boundary or create tiny DB writes.
    if is_text and on_event and not agent_contract and not summary_mode:
        await on_event("assistant.delta", {"text": completion.text})
    return completion
