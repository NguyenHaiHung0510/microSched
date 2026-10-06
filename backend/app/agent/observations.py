"""Receipt-only context observations and billable run totals; no token estimates."""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

from app.core.settings import Settings

COMPACTION_TRIGGER = 100_000


def context_revision(settings: Settings, config_version: int, checkpoint_id: Any) -> str:
    # Message append and per-request hashes deliberately do not change this epoch.
    from app.agent.context import OUTPUT_SCHEMA_SHA256
    from app.agent.policy import POLICY_SHA256
    from app.agent.tools.registry import REGISTRY_SHA256

    value = {
        "version": 1,
        "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
        "route_config_version": config_version,
        "model": settings.mimi_route_model,
        "provider": settings.mimi_route_provider,
        "quantization": settings.mimi_route_quantization,
        "mode": settings.mimi_route_mode,
        "providers": settings.mimi_allowed_provider_list,
        "effort": settings.mimi_route_reasoning_effort,
        "policy_sha256": POLICY_SHA256,
        "tool_registry_sha256": REGISTRY_SHA256,
        "output_schema_sha256": OUTPUT_SCHEMA_SHA256,
        "text_response_format": settings.mimi_text_response_format,
        "quantizations": settings.mimi_allowed_quantization_list,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def reported_number(value: Any) -> int | float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value >= 0 and math.isfinite(value):
            return value
    return None


def prompt_observation(call: Any, revision: str, *, consumed: bool = False) -> dict[str, Any]:
    result = {
        "context_revision": revision,
        "trigger_tokens": COMPACTION_TRIGGER,
        "source_call_id": str(call.id) if call else None,
        "prompt_tokens": None,
        "eligible": False,
        "should_compact": False,
        "compaction_blocked": False,
        "reason": "missing_main_receipt",
    }
    if call is None:
        return result
    route = call.route or {}
    if route.get("purpose", "main") != "main" or route.get("kind") != "openrouter":
        result["reason"] = "not_main_conversation"
    elif route.get("paid_dispatch") is False:
        result["reason"] = "reused_receipt"
    elif route.get("context_revision") != revision:
        result["reason"] = "stale_context_revision"
    elif (
        call.state != "succeeded"
        or not route.get("actual_provider")
        or route.get("actual_model") != route.get("model")
        or route.get("actual_provider", "").lower()
        not in [str(p).lower() for p in (route.get("providers") or [])]
    ):
        result["reason"] = "unverified_main_route"
    else:
        value = (call.usage or {}).get("prompt_tokens")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            result["reason"] = "prompt_usage_missing"
        else:
            result.update(
                prompt_tokens=value,
                eligible=True,
                should_compact=value >= COMPACTION_TRIGGER and not consumed,
                compaction_blocked=value >= COMPACTION_TRIGGER and consumed,
                reason="compaction_required_unactivated" if consumed else "provider_prompt_usage",
            )
    return result


def run_costs(calls: list[Any]) -> dict[str, Any]:
    """Deduplicate generation receipts; reuse is not another billable dispatch."""
    totals = {"main": Decimal(0), "helper": Decimal(0)}
    counts = {"main": 0, "helper": 0}
    unknown = {"main": 0, "helper": 0}
    seen = set()
    reused = 0
    for call in calls:
        route = call.route or {}
        if route.get("paid_dispatch") is False:
            reused += 1
            continue
        if route.get("kind") != "openrouter" or call.state in {"intent", "fenced"}:
            continue
        identity = (call.result or {}).get("response_id") or str(call.id)
        if identity in seen:
            continue
        seen.add(identity)
        purpose = "helper" if route.get("purpose") == "compaction" else "main"
        counts[purpose] += 1
        cost = reported_number((call.usage or {}).get("cost"))
        if cost is None:
            unknown[purpose] += 1
        else:
            totals[purpose] += Decimal(str(cost))
    return {
        "known_cost_usd": float(sum(totals.values())),
        "main_known_cost_usd": float(totals["main"]),
        "helper_known_cost_usd": float(totals["helper"]),
        "unknown_cost_calls": sum(unknown.values()),
        "main_unknown_cost_calls": unknown["main"],
        "helper_unknown_cost_calls": unknown["helper"],
        "cost_complete": not any(unknown.values()),
        "main_calls": counts["main"],
        "helper_calls": counts["helper"],
        "reused_calls": reused,
    }
