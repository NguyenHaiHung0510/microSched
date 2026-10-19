"""Bounded OpenRouter route adapter for Mimi's exact and adaptive lanes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.agent.context import (
    AGENT_RESPONSE_FORMAT,
    AssistantText,
    PreviewCandidate,
    TerminalOutcome,
    ToolRequest,
    ToolRequests,
    parse_terminal_wire,
)
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL, CollectionCandidate
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL, READ_TOOLS, TOOLS
from app.core.settings import Settings, get_settings
from app.domain.tasks import TaskCreate


class RouteContractError(ValueError):
    """The selected route or terminal payload violated Mimi's frozen contract."""

    def __init__(
        self,
        message: str,
        *,
        response_id: str | None = None,
        usage: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
    ):
        super().__init__(message)
        self.response_id = response_id
        self.usage = usage or {}
        self.provider = provider
        self.model = model


class CandidateContractError(RouteContractError):
    """A wholly rejected native candidate turn; never a partial proposal/read."""

    def __init__(self, code: str, tool_names: tuple[str, ...]):
        super().__init__(code)
        self.tool_names = tool_names
        # Only the service can enable feedback after durable accounting.
        self.correction_ready = False

    def correction_permitted(self, receipt, allowed_tools, *, final_only=False):
        if final_only or not set(self.tool_names).issubset(allowed_tools):
            return False
        if not isinstance(receipt, dict) or not receipt.get("id"):
            return False
        cost = receipt.get("usage", {}).get("cost")
        if isinstance(cost, bool) or not isinstance(cost, (str, int, float)):
            return False
        try:
            value = Decimal(str(cost))
        except InvalidOperation:
            return False
        return value.is_finite() and value >= 0


class ProviderDispatchError(RuntimeError):
    """A provider call ended without a usable terminal result."""

    def __init__(
        self,
        outcome: Literal["retryable", "unknown", "failed"],
        status: int | None,
        *,
        response_id: str | None = None,
        diagnostic: dict[str, Any] | None = None,
    ):
        super().__init__(f"provider dispatch ended as {outcome}")
        self.outcome = outcome
        self.status = status
        self.response_id = response_id
        self.diagnostic = diagnostic or {}


@dataclass(frozen=True)
class ProviderCompletion:
    kind: Literal["text", "task", "collection"]
    task: TaskCreate | None
    text: str | None
    response_id: str
    usage: dict[str, Any]
    provider: str | None
    model: str | None
    collection: dict[str, Any] | None = None
    dispatch_attempts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AgentCompletion:
    outcome: TerminalOutcome
    response_id: str
    usage: dict[str, Any]
    provider: str | None
    model: str | None
    dispatch_attempts: list[dict[str, Any]] = field(default_factory=list)


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

COMPACTION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "mimi_compaction_v2",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "constraints", "supersessions", "resolutions"],
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 6000},
                "constraints": {
                    "type": "array",
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["text", "kind", "source_sequence", "source_sha256", "quote"],
                        "properties": {
                            "text": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "kind": {"enum": ["decision", "unresolved"]},
                            "source_sequence": {"type": "integer", "minimum": 1},
                            "source_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                            "quote": {"type": "string", "minLength": 1, "maxLength": 1000},
                        },
                    },
                },
                "supersessions": {
                    "type": "array",
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "prior_id",
                            "source_sequence",
                            "source_sha256",
                            "quote",
                            "replacement_text",
                        ],
                        "properties": {
                            "prior_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                            "source_sequence": {"type": "integer", "minimum": 1},
                            "source_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                            "quote": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "replacement_text": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1000,
                            },
                        },
                    },
                },
                "resolutions": {
                    "type": "array",
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["prior_id", "source_sequence", "source_sha256", "quote"],
                        "properties": {
                            "prior_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                            "source_sequence": {"type": "integer", "minimum": 1},
                            "source_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                            "quote": {"type": "string", "minLength": 1, "maxLength": 1000},
                        },
                    },
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
    if settings.mimi_route_max_input_price is None or settings.mimi_route_max_output_price is None:
        raise RouteContractError("Mimi route price caps are not configured")
    from app.agent.config_policy import finite_price

    return {
        "prompt": float(finite_price(settings.mimi_route_max_input_price)),
        "completion": float(finite_price(settings.mimi_route_max_output_price)),
    }


def _rejected_terminal_metadata(response_id, provider, model, usage, finish_reason):
    """Allowlisted terminal facts only; provider prose/partial output is never a receipt."""

    def identity(value):
        return (
            value
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value)
            else None
        )

    def amount(value):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None
        return value if number.is_finite() and number >= 0 else None

    safe_usage = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            safe_usage[key] = value
    cost = amount(usage.get("cost"))
    if cost is not None:
        safe_usage["cost"] = cost
    for key, fields in {
        "prompt_tokens_details": (
            "cached_tokens",
            "cache_write_tokens",
            "audio_tokens",
            "video_tokens",
        ),
        "completion_tokens_details": ("reasoning_tokens", "audio_tokens", "image_tokens"),
    }.items():
        details = usage.get(key)
        if isinstance(details, dict):
            safe_usage[key] = {
                name: value
                for name in fields
                if isinstance(value := details.get(name), int)
                and not isinstance(value, bool)
                and value >= 0
            }
    for key, fields in {
        "cost_details": (
            "upstream_inference_cost",
            "upstream_inference_prompt_cost",
            "upstream_inference_completions_cost",
        ),
        "mimi_timing": ("duration_ms", "connect_ms", "ttft_ms", "output_tokens_per_second"),
    }.items():
        details = usage.get(key)
        if isinstance(details, dict):
            safe_usage[key] = {
                name: value for name in fields if (value := amount(details.get(name))) is not None
            }
    reason = (
        finish_reason
        if finish_reason
        in {None, "stop", "tool_calls", "length", "content_filter", "function_call", "error"}
        else "other"
    )
    receipt = {
        "id": identity(response_id),
        "provider": identity(provider),
        "model": identity(model),
        "usage": safe_usage,
        "finish_reason": reason,
        "cost_available": cost is not None,
    }
    if reason == "other":
        receipt["finish_reason_sha256"] = hashlib.sha256(finish_reason.encode()).hexdigest()
    return receipt


def validate_response_identity(payload: dict, settings: Settings) -> None:
    """Actual identity must match the requested model and admitted provider names.

    A routing variant slug is not a response-provider alias. Explicit aliases
    are trusted qualification configuration, never taken from response prose.
    """
    model, provider = payload.get("model"), payload.get("provider")
    allowed = settings.mimi_route_qualified_provider_names or (
        (settings.mimi_route_provider,) if settings.mimi_route_mode == "exact" else ()
    )
    aliases = json.loads(settings.mimi_route_identity_aliases_json)
    models = {
        settings.mimi_route_model,
        *aliases.get("models", {}).get(settings.mimi_route_model, []),
    }
    providers = {str(p).casefold() for p in allowed if isinstance(p, str)}
    for qualified in allowed:
        providers.update(str(p).casefold() for p in aliases.get("providers", {}).get(qualified, []))
    if (
        not isinstance(model, str)
        or model not in models
        or (
            settings.mimi_route_mode == "native"
            and provider is not None
            and (not isinstance(provider, str) or not provider.strip() or len(provider) > 200)
        )
        or (
            settings.mimi_route_mode != "native"
            and (not isinstance(provider, str) or provider.casefold() not in providers)
        )
    ):
        receipt = _rejected_terminal_metadata(
            payload.get("id"), provider, model, payload.get("usage") or {}, None
        )
        error = RouteContractError(
            "provider_actual_identity_not_qualified",
            response_id=receipt["id"],
            usage=receipt["usage"],
            provider=receipt["provider"],
            model=receipt["model"],
        )
        error.terminal_receipt = receipt
        raise error


def merge_stream_identity(current: str | None, value: Any, *, field: str) -> str | None:
    if value is None:
        return current
    if not isinstance(value, str) or not value.strip():
        raise RouteContractError("provider_stream_identity_invalid")
    matches = current is None or (
        current.casefold() == value.casefold() if field == "provider" else current == value
    )
    if not matches:
        raise RouteContractError("provider_stream_identity_changed")
    return value


def _provider_policy(settings: Settings) -> dict[str, Any]:
    shared: dict[str, Any] = {
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": settings.mimi_route_require_zdr,
        "max_price": _price_policy(settings),
    }
    if settings.mimi_route_mode == "native":
        quantizations = list(settings.mimi_allowed_quantization_list)
        if not quantizations and settings.mimi_route_quantization not in {None, "unknown"}:
            quantizations = [settings.mimi_route_quantization]
        return {
            **shared,
            "allow_fallbacks": True,
            **({"quantizations": quantizations} if quantizations else {}),
        }
    if settings.mimi_route_mode == "exact":
        if settings.mimi_route_provider is None or settings.mimi_route_quantization is None:
            raise RouteContractError("exact Mimi route is not configured")
        policy = {
            **shared,
            "order": [settings.mimi_route_provider],
            "only": [settings.mimi_route_provider],
            "allow_fallbacks": False,
        }
        # `unknown` records that exact provider/model metadata did not attest a
        # quantization. Keep the provider pin but do not claim a precision.
        if settings.mimi_route_quantization != "unknown":
            policy["quantizations"] = [settings.mimi_route_quantization]
        return policy
    expires = settings.mimi_route_qualification_expires_at
    checked = settings.mimi_route_catalog_checked_at
    if (
        expires is None
        or checked is None
        or not time.time() < expires
        or not 0 <= time.time() - checked < 7200
        or not settings.mimi_route_qualification_sha256
    ):
        raise RouteContractError("adaptive_endpoint_qualification_stale_or_missing")
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


def serialized_input_bytes(
    messages: list[dict[str, Any]], *, agent_contract: bool, summary_mode: bool = False
) -> int:
    """Bound the full model-visible input, including output and tool schemas."""

    payload = {"messages": messages}
    if summary_mode:
        payload["response_format"] = COMPACTION_RESPONSE_FORMAT
    else:
        payload["tools"] = list(TOOLS) if agent_contract else [TASK_CREATE_TOOL]
    if agent_contract and not summary_mode:
        payload["response_format"] = AGENT_RESPONSE_FORMAT
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def build_request(
    messages: list[dict[str, Any]],
    settings: Settings | None = None,
    *,
    stream: bool = False,
    session_id: str | None = None,
    force_task_tool: bool = False,
    agent_contract: bool = False,
    summary_mode: bool = False,
    final_answer_only: bool = False,
) -> dict[str, Any]:
    """Build either the attributable exact lane or bounded adaptive dogfood lane."""
    route = settings or get_settings()
    _, model = _route_identity(route)
    if final_answer_only and summary_mode:
        raise RouteContractError("final_answer_conflicts_with_summary")
    if summary_mode and agent_contract:
        raise RouteContractError("summary_mode_conflicts_with_agent_contract")
    active_tools = [] if summary_mode else (list(TOOLS) if agent_contract else [TASK_CREATE_TOOL])
    if agent_contract and not route.mimi_collection_enabled:
        active_tools = [
            t
            for t in active_tools
            if t["function"]["name"] not in {"task.freeze_selection.v1", COLLECTION_CANDIDATE_TOOL}
        ]
    # Payload resource bound is independent of provider tokens and 100k trigger.
    if (
        serialized_input_bytes(messages, agent_contract=agent_contract, summary_mode=summary_mode)
        > route.mimi_max_payload_bytes
    ):
        raise RouteContractError("payload_bytes_exceeded")
    if route.mimi_route_mode != "native" and route.mimi_route_context_tokens < 408_192:
        raise RouteContractError("context_overflow_preflight_route_capacity")
    if route.mimi_route_max_output_tokens > route.mimi_route_context_tokens:
        raise RouteContractError("output_reserve_exceeds_route_limit")
    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        # Collection revisions may read before returning their typed replacement;
        # the service owns the terminal gate. Single-create revisions still use
        # the qualified forced tool choice.
        # OpenInference did not advertise `parallel_tool_calls`; omitting the
        # optional parameter keeps `require_parameters=true` routable while the
        # terminal parser independently enforces candidate-only turns and bounded read batches.
        "stream": stream,
        "store": False,
        "reasoning": {
            **(
                {"effort": route.mimi_route_reasoning_effort}
                if route.mimi_route_reasoning_effort != "default"
                else {}
            ),
            "exclude": True,
        },
        "usage": {"include": True},
        "provider": _provider_policy(route),
    }
    if route.mimi_route_mode != "native":
        request["max_tokens"] = route.mimi_route_max_output_tokens
    if final_answer_only:
        request["tool_choice"] = "none"
    elif not summary_mode:
        request["tools"] = active_tools
        request["tool_choice"] = _tool_choice(
            route, force_task_tool=force_task_tool, agent_contract=agent_contract
        )
    if stream:
        request["stream_options"] = {"include_usage": True}
    if summary_mode:
        request["response_format"] = COMPACTION_RESPONSE_FORMAT
    elif agent_contract and route.mimi_text_response_format == "structured":
        request["response_format"] = AGENT_RESPONSE_FORMAT
    if session_id:
        request["session_id"] = session_id
    # Owner184: 400K is an operating target, not a universal byte/token gate.
    # Native capacity/output controls and the explicit payload byte resource cap
    # remain enforced. Provider input overflow is a distinct finite recovery path.
    return request


def parse_agent_completion(payload: dict[str, Any]) -> AgentCompletion:
    """Validate one model turn before any server-owned read or preview transition."""

    native_names: tuple[str, ...] = ()
    try:
        choices = payload["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise RouteContractError("provider_must_return_one_choice")
        message = choices[0]["message"]
        if not isinstance(message, dict):
            raise RouteContractError("provider_message_invalid")
        calls = message.get("tool_calls") or []
        raw_content = message.get("content")
        content = raw_content.strip() if isinstance(raw_content, str) else ""
        if calls:
            if not isinstance(calls, list) or len(calls) > 8:
                raise RouteContractError("provider_tool_call_count_invalid")
            # Validate every name before decoding any arguments. A malformed
            # candidate must never mask an unauthorized sibling as repairable.
            native_names = tuple(call["function"]["name"] for call in calls)
            if any(
                not isinstance(n, str)
                or n not in READ_TOOLS | {CREATE_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL}
                for n in native_names
            ):
                native_names = ()
                raise RouteContractError("provider_tool_not_allowed")
            requests: list[ToolRequest] = []
            for index, call in enumerate(calls):
                function = call["function"]
                name = function["name"]
                if name not in READ_TOOLS | {CREATE_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL}:
                    raise RouteContractError("provider_tool_not_allowed")
                arguments = function["arguments"]
                decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
                if not isinstance(decoded, dict):
                    raise RouteContractError("provider_tool_arguments_not_object")
                requests.append(
                    ToolRequest(
                        call_id=str(call.get("id") or f"tool-{index}"),
                        name=name,
                        arguments=decoded,
                    )
                )
            if any(item.name == COLLECTION_CANDIDATE_TOOL for item in requests):
                if len(requests) != 1:
                    raise RouteContractError("candidate_cannot_share_tool_turn")
                candidate = CollectionCandidate.model_validate(requests[0].arguments)
                outcome = PreviewCandidate(
                    tool=COLLECTION_CANDIDATE_TOOL, arguments=candidate.model_dump(mode="json")
                )
            elif any(item.name == CREATE_CANDIDATE_TOOL for item in requests):
                if len(requests) != 1:
                    raise RouteContractError("candidate_cannot_share_tool_turn")
                request = requests[0]
                if set(request.arguments) != {"task"} or not isinstance(
                    request.arguments["task"], dict
                ):
                    raise RouteContractError("candidate_arguments_invalid")
                outcome: TerminalOutcome = PreviewCandidate(
                    tool=CREATE_CANDIDATE_TOOL, arguments=request.arguments["task"]
                )
            else:
                outcome = ToolRequests(requests=tuple(requests))
        elif content:
            try:
                decoded_content = json.loads(content)
            except json.JSONDecodeError:
                outcome = AssistantText(text=content)
            else:
                if isinstance(decoded_content, dict) and "kind" in decoded_content:
                    outcome = parse_terminal_wire(decoded_content)
                else:
                    outcome = AssistantText(text=content)
        else:
            raise RouteContractError("provider_terminal_empty")
        return AgentCompletion(
            outcome=outcome,
            response_id=str(payload.get("id", "")),
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
            provider=payload.get("provider") if isinstance(payload.get("provider"), str) else None,
            model=payload.get("model") if isinstance(payload.get("model"), str) else None,
        )
    except RouteContractError as error:
        if set(native_names) & {CREATE_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL} and str(
            error
        ) in {
            "candidate_cannot_share_tool_turn",
            "candidate_arguments_invalid",
            "provider_tool_arguments_not_object",
        }:
            raise CandidateContractError(str(error), native_names) from error
        raise
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        shape_error = not isinstance(error, ValidationError) or all(
            (
                issue["type"] in {"missing", "string_type", "dict_type", "tuple_type", "too_short"}
                or (
                    issue["type"] == "value_error"
                    and str(issue.get("ctx", {}).get("error")) == "task_due_triad_must_be_complete"
                )
            )
            for issue in error.errors(include_input=False)
        )
        if shape_error and set(native_names) & {CREATE_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL}:
            raise CandidateContractError("invalid_agent_terminal_payload", native_names) from error
        raise RouteContractError("invalid_agent_terminal_payload") from error


def parse_compaction_completion(payload: dict[str, Any]) -> AgentCompletion:
    """Parse the strict summary-only JSON shape; any function call is invalid."""
    try:
        choices = payload["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise RouteContractError("provider_must_return_one_choice")
        if not isinstance(choices[0], dict):
            raise RouteContractError("compaction_summary_payload_invalid")
        if choices[0].get("finish_reason") == "length":
            raise RouteContractError("compaction_summary_output_truncated")
        message = choices[0]["message"]
        if not isinstance(message, dict) or message.get("tool_calls"):
            raise RouteContractError("compaction_requires_summary_not_tool_or_draft")
        raw = message.get("content")
        candidate = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(candidate, dict):
            raise RouteContractError("compaction_summary_payload_invalid")
        return AgentCompletion(
            outcome=AssistantText(
                kind="assistant_text", text=json.dumps(candidate, ensure_ascii=False)
            ),
            response_id=str(payload.get("id", "")),
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
            provider=payload.get("provider") if isinstance(payload.get("provider"), str) else None,
            model=payload.get("model") if isinstance(payload.get("model"), str) else None,
        )
    except (RouteContractError, KeyError, TypeError, ValueError) as error:
        # Do not preserve provider-controlled prose. The observed response/usage
        # survives validation failure so its single reservation can be accounted.
        code = (
            str(error)
            if isinstance(error, RouteContractError)
            else "compaction_summary_payload_invalid"
        )
        raise RouteContractError(
            code,
            response_id=payload.get("id") if isinstance(payload.get("id"), str) else None,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
            provider=payload.get("provider") if isinstance(payload.get("provider"), str) else None,
            model=payload.get("model") if isinstance(payload.get("model"), str) else None,
        ) from error


def _tool_choice(settings: Settings, *, force_task_tool: bool, agent_contract: bool = False) -> Any:
    if not force_task_tool:
        return "auto"
    capability = settings.mimi_route_forced_tool_choice
    if capability == "none":
        raise RouteContractError("route_forced_tool_choice_not_qualified")
    if agent_contract and settings.mimi_collection_enabled and settings.mimi_revision_collection:
        # A changed subset needs current-run reads and a fresh selection before
        # the typed replacement. The service still rejects non-candidate terminals.
        return "auto"
    if capability == "required":
        # Mimi exposes exactly one tool in this request.
        return "required"
    name = (
        (
            COLLECTION_CANDIDATE_TOOL
            if settings.mimi_revision_collection and settings.mimi_collection_enabled
            else CREATE_CANDIDATE_TOOL
        )
        if agent_contract
        else "task.create.v1"
    )
    return {"type": "function", "function": {"name": name}}


def validate_task_candidate(decoded: dict[str, Any], *, require_id: bool = True) -> TaskCreate:
    """One domain validation seam for legacy and context-loop previews."""
    allowed_fields = {
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
    }
    if unknown_fields := set(decoded) - allowed_fields:
        raise RouteContractError(
            "provider_task_schema_invalid_extra_fields_" + "_".join(sorted(unknown_fields))
        )
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
        raise RouteContractError(f"provider_task_schema_invalid_{location}_{error_type}") from error
    if task.is_private:
        raise RouteContractError("standard_route_proposed_private_task")
    if require_id and task.id is None:
        raise RouteContractError("provider_task_id_missing")
    if len(task.title) > 200:
        raise RouteContractError("provider_task_schema_invalid_title_too_long")
    if task.body_md is not None and len(task.body_md) > 20_000:
        raise RouteContractError("provider_task_schema_invalid_body_md_too_long")
    if len(task.items) > 20:
        raise RouteContractError("provider_task_schema_invalid_items_too_long")
    if any(len(item) > 500 for item in task.items):
        raise RouteContractError("provider_task_schema_invalid_items_item_too_long")
    return task


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
        task = validate_task_candidate(decoded)
    except RouteContractError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise RouteContractError("invalid_provider_terminal_payload") from error
    return ProviderCompletion(kind="task", task=task, text=None, **common)


def _input_overflow_error(status_code: int, body: Any) -> ProviderDispatchError | None:
    """Only a machine-typed pre-generation refusal, never echoed message matching."""
    if status_code not in {400, 422} or not isinstance(body, dict) or body.get("id"):
        return None
    usage = body.get("usage")
    if isinstance(usage, dict) and (
        usage.get("completion_tokens", 0) or usage.get("total_tokens", 0)
    ):
        return None
    error = body.get("error")
    if not isinstance(error, dict) or error.get("code") not in {
        "context_length_exceeded",
        "max_context_length_exceeded",
    }:
        return None
    selected = ProviderDispatchError(
        "failed",
        status_code,
        diagnostic={"category": "input_context_overflow", "definite_refusal": True},
    )
    selected.terminal_receipt = _rejected_terminal_metadata(
        None, None, None, body.get("usage") if isinstance(body.get("usage"), dict) else {}, None
    )
    return selected


def _raise_for_status(status_code: int, *, body=None, retry_after: str | None = None) -> None:
    if status_code < 400:
        return
    from app.agent.gateway_retry import retry_after_seconds

    diagnostic = {"category": "provider_unavailable"}
    seconds = retry_after_seconds(retry_after)
    if seconds is not None:
        diagnostic["retry_after_seconds"] = seconds
    envelope = body.get("error", body) if isinstance(body, dict) else {}
    metadata = envelope.get("metadata") if isinstance(envelope, dict) else None
    error_type = metadata.get("error_type") if isinstance(metadata, dict) else None
    outcome = "failed"
    if status_code in {408, 409} or status_code >= 500:
        outcome = "unknown"
    if status_code == 429:
        outcome = "retryable"
        diagnostic["category"] = "rate_limited"
    elif status_code in {429, 502, 503} and error_type == "provider_overloaded":
        outcome = "retryable"
        diagnostic["category"] = error_type
    elif (
        status_code == 402
        and seconds is not None
        and isinstance(metadata, dict)
        and metadata.get("limit_source") == "openrouter_in_flight_budget"
        and metadata.get("reason") == "in_flight_budget_exhausted"
    ):
        outcome = "retryable"
        diagnostic["category"] = "in_flight_budget_exhausted"
    elif status_code < 500 and status_code not in {408, 409}:
        diagnostic["category"] = "provider_rejected"
    error = ProviderDispatchError(outcome, status_code, diagnostic=diagnostic)
    if isinstance(body, dict):
        error.terminal_receipt = _rejected_terminal_metadata(
            body.get("id"),
            body.get("provider"),
            body.get("model"),
            body.get("usage") if isinstance(body.get("usage"), dict) else {},
            None,
        )
        error.response_id = error.terminal_receipt["id"]
        # A generation identity or token usage defeats a pre-generation retry.
        usage = error.terminal_receipt["usage"]
        if outcome == "retryable" and (error.response_id or usage):
            error.outcome = "unknown"
    raise error


def _raise_generation_error(payload: dict) -> None:
    """A JSON error after HTTP200 may already represent a billed generation."""
    envelope = payload.get("error")
    if envelope is None:
        return
    code = envelope.get("code") if isinstance(envelope, dict) else None
    error = ProviderDispatchError(
        "unknown",
        code if type(code) is int and 400 <= code <= 599 else None,
        response_id=payload.get("id"),
        diagnostic={"category": "generation_error"},
    )
    error.terminal_receipt = _rejected_terminal_metadata(
        payload.get("id"),
        payload.get("provider"),
        payload.get("model"),
        payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
        None,
    )
    error.response_id = error.terminal_receipt["id"]
    raise error


async def complete(messages, *, settings=None, **kwargs):
    route = settings or get_settings()

    async def operation():
        return await _complete_once(messages, settings=route, **kwargs)

    if route.mimi_route_mode != "native":
        return await operation()
    from app.agent.gateway_retry import dispatch

    return await dispatch(operation, settings=route)


async def complete_stream(messages, *, settings=None, **kwargs):
    route = settings or get_settings()

    async def operation():
        return await _complete_stream_once(messages, settings=route, **kwargs)

    if route.mimi_route_mode != "native":
        return await operation()
    from app.agent.gateway_retry import dispatch

    return await dispatch(operation, settings=route)


async def _complete_once(
    messages: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    session_id: str | None = None,
    force_task_tool: bool = False,
    agent_contract: bool = False,
    summary_mode: bool = False,
    final_answer_only: bool = False,
) -> ProviderCompletion | AgentCompletion:
    """Dispatch once. Retry authority belongs to persisted run state."""
    route = settings or get_settings()
    if route.mimi_transport == "openai_sdk":
        from app.agent.openai_sdk import complete as complete_with_openai_sdk

        return await complete_with_openai_sdk(
            messages,
            settings=route,
            client=client,
            session_id=session_id,
            force_task_tool=force_task_tool,
            agent_contract=agent_contract,
            summary_mode=summary_mode,
            final_answer_only=final_answer_only,
        )
    api_key, _ = _route_identity(route)
    request = build_request(
        messages,
        route,
        session_id=session_id,
        force_task_tool=force_task_tool,
        agent_contract=agent_contract,
        summary_mode=summary_mode,
        final_answer_only=final_answer_only,
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
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise ProviderDispatchError("retryable", None) from error
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise ProviderDispatchError("unknown", None) from error
        if response.status_code in {400, 422}:
            try:
                overflow = _input_overflow_error(response.status_code, response.json())
            except ValueError:
                overflow = None
            if overflow is not None:
                raise overflow
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = None
            _raise_for_status(
                response.status_code, body=body, retry_after=response.headers.get("retry-after")
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise RouteContractError("provider_terminal_payload_is_not_json") from error
        if not isinstance(payload, dict):
            raise RouteContractError("provider_terminal_payload_is_not_an_object")
        _raise_generation_error(payload)
        try:
            validate_response_identity(payload, route)
            if summary_mode:
                return parse_compaction_completion(payload)
            return parse_agent_completion(payload) if agent_contract else parse_completion(payload)
        except RouteContractError as error:
            choices = payload.get("choices")
            finish = (
                choices[0].get("finish_reason")
                if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
                else None
            )
            receipt = _rejected_terminal_metadata(
                payload.get("id"),
                payload.get("provider"),
                payload.get("model"),
                payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
                finish,
            )
            error.terminal_receipt = receipt
            error.response_id, error.usage = receipt["id"], receipt["usage"]
            error.provider, error.model = receipt["provider"], receipt["model"]
            raise
    finally:
        if owns_client:
            await active_client.aclose()


async def _complete_stream_once(
    messages: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    session_id: str | None = None,
    on_event: ProviderEventSink | None = None,
    force_task_tool: bool = False,
    agent_contract: bool = False,
    summary_mode: bool = False,
    final_answer_only: bool = False,
) -> ProviderCompletion | AgentCompletion:
    """Normalize OpenRouter SSE without exposing raw chunks or partial tool JSON."""
    route = settings or get_settings()
    if route.mimi_transport == "openai_sdk":
        from app.agent.openai_sdk import complete_stream as stream_with_openai_sdk

        return await stream_with_openai_sdk(
            messages,
            settings=route,
            client=client,
            session_id=session_id,
            on_event=on_event,
            force_task_tool=force_task_tool,
            agent_contract=agent_contract,
            summary_mode=summary_mode,
            final_answer_only=final_answer_only,
        )
    api_key, _ = _route_identity(route)
    request = build_request(
        messages,
        route,
        stream=True,
        session_id=session_id,
        force_task_tool=force_task_tool,
        agent_contract=agent_contract,
        summary_mode=summary_mode,
        final_answer_only=final_answer_only,
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
    saw_done = False
    saw_finish_reason = False
    finish_reason: str | None = None
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
                if response.status_code in {400, 422}:
                    await response.aread()
                    try:
                        overflow = _input_overflow_error(response.status_code, response.json())
                    except ValueError:
                        overflow = None
                    if overflow is not None:
                        raise overflow
                if response.status_code >= 400:
                    await response.aread()
                    try:
                        body = response.json()
                    except ValueError:
                        body = None
                    _raise_for_status(
                        response.status_code,
                        body=body,
                        retry_after=response.headers.get("retry-after"),
                    )
                connected_at = time.perf_counter()
                if on_event:
                    await on_event("provider.connected", {"status": response.status_code})
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    if raw == "[DONE]":
                        saw_done = True
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError as error:
                        raise RouteContractError("provider_stream_chunk_is_not_json") from error
                    if not isinstance(chunk, dict):
                        raise RouteContractError("provider_stream_chunk_is_not_an_object")
                    if isinstance(chunk.get("id"), str) and chunk["id"]:
                        if chunk["id"] != response_id:
                            response_id = chunk["id"]
                            if on_event:
                                await on_event(
                                    "provider.response_identity", {"response_id": response_id}
                                )
                    provider = merge_stream_identity(
                        provider, chunk.get("provider"), field="provider"
                    )
                    model = merge_stream_identity(model, chunk.get("model"), field="model")
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]
                    provider_error = chunk.get("error")
                    if provider_error is not None:
                        code = (
                            provider_error.get("code") if isinstance(provider_error, dict) else None
                        )
                        if isinstance(code, int) and code >= 400:
                            _raise_for_status(
                                code,
                                body=chunk,
                                retry_after=response.headers.get("retry-after"),
                            )
                        raise RouteContractError("provider_stream_error_envelope")
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
                        # Do not expose narration until the terminal union is
                        # known. Some compatible providers emit content before
                        # a tool call; replaying it immediately would surface a
                        # false text answer beside a later frozen preview.
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
                if not saw_done and not saw_finish_reason:
                    raise ProviderDispatchError("unknown", None, response_id=response_id or None)
                if finish_reason not in {None, "stop", "tool_calls"}:
                    raise RouteContractError("provider_stream_finish_reason_not_usable")
        except ProviderDispatchError as error:
            if response_id or content_parts or tool_calls or usage:
                error.outcome = "unknown"
            error.response_id = response_id or error.response_id
            if response_id or provider or model or usage or not hasattr(error, "terminal_receipt"):
                error.terminal_receipt = _rejected_terminal_metadata(
                    response_id, provider, model, usage, finish_reason
                )
            raise
        except RouteContractError as error:
            receipt = _rejected_terminal_metadata(
                response_id, provider, model, usage, finish_reason
            )
            error.terminal_receipt = receipt
            error.response_id, error.usage = receipt["id"], receipt["usage"]
            error.provider, error.model = receipt["provider"], receipt["model"]
            raise
        except (asyncio.CancelledError, httpx.TransportError) as error:
            safe_connect = (
                isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout))
                and connected_at is None
                and not (response_id or usage or content_parts or tool_calls)
            )
            interrupted = ProviderDispatchError(
                "retryable" if safe_connect else "unknown",
                None,
                response_id=response_id or None,
            )
            interrupted.terminal_receipt = _rejected_terminal_metadata(
                response_id, provider, model, usage, finish_reason
            )
            raise interrupted from error
        completed_at = time.perf_counter()
        timing = {
            "duration_ms": round((completed_at - started_at) * 1000, 3),
            "connect_ms": (
                round((connected_at - started_at) * 1000, 3) if connected_at is not None else None
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
            validate_response_identity(terminal_payload, route)
            completion = parser(terminal_payload)
        except RouteContractError as error:
            receipt = _rejected_terminal_metadata(
                response_id, provider, model, usage, finish_reason
            )
            error.terminal_receipt = receipt
            error.response_id, error.usage = receipt["id"], receipt["usage"]
            error.provider, error.model = receipt["provider"], receipt["model"]
            raise
        is_text = (
            isinstance(completion, AgentCompletion)
            and isinstance(completion.outcome, AssistantText)
        ) or (isinstance(completion, ProviderCompletion) and completion.kind == "text")
        if is_text and on_event:
            for text in content_parts:
                await on_event("assistant.delta", {"text": text})
        return completion
    finally:
        if owns_client:
            await active_client.aclose()


async def get_generation(
    response_id: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Read canonical generation metadata through HTTPX for reconciliation.

    This read-only endpoint stays on HTTPX for both chat transports; the OpenAI
    SDK does not expose a typed generation endpoint with this contract.
    """
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
        except httpx.TransportError as error:
            # An interrupted metadata read does not establish whether the
            # original generation exists; never re-dispatch it implicitly.
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
