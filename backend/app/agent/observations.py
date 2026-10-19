"""Receipt-only context observations and billable run totals; no token estimates."""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

from app.agent.billing_prices import billing_sample, summarize_prices
from app.core.settings import Settings

COMPACTION_TRIGGER = 272_000


def context_revision(settings: Settings, config_version: int, checkpoint_id: Any) -> str:
    # Message append and per-request hashes deliberately do not change this epoch.
    from app.agent.context import OUTPUT_SCHEMA_SHA256
    from app.agent.policy import load_standard_policy
    from app.agent.tools.registry import registry_hash, tools_for_settings

    value = {
        "version": 2,
        "working_projection": settings.mimi_working_projection_enabled,
        "checkpoint_id": str(checkpoint_id) if checkpoint_id else None,
        "route_config_version": config_version,
        "model": settings.mimi_route_model,
        "provider": settings.mimi_route_provider,
        "quantization": settings.mimi_route_quantization,
        "mode": settings.mimi_route_mode,
        "providers": settings.mimi_allowed_provider_list,
        "effort": settings.mimi_route_reasoning_effort,
        "policy_sha256": load_standard_policy(
            collection_enabled=settings.mimi_collection_enabled
        ).sha256,
        "tool_registry_sha256": registry_hash(tools_for_settings(settings)),
        "output_schema_sha256": OUTPUT_SCHEMA_SHA256,
        "text_response_format": settings.mimi_text_response_format,
        "quantizations": settings.mimi_allowed_quantization_list,
        "compaction_trigger_tokens": settings.mimi_compaction_trigger_tokens,
        # Price/future-input policy revision binds each unsent wire, not past usage.
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def reported_number(value: Any) -> int | float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value >= 0 and math.isfinite(value):
            return value
    return None


def prompt_observation(
    call: Any,
    revision: str,
    *,
    consumed: bool = False,
    trigger_tokens: int = COMPACTION_TRIGGER,
    checkpoint_id: Any = None,
    require_projection: bool = False,
) -> dict[str, Any]:
    result = {
        "context_revision": revision,
        "trigger_tokens": trigger_tokens,
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
    elif route.get("paid_dispatch") is False or route.get("dispatch_not_started") is True:
        result["reason"] = "reused_receipt"
    elif route.get("context_revision") != revision:
        result["reason"] = "stale_context_revision"
    elif require_projection and not valid_input_projection(call, checkpoint_id):
        result["reason"] = "projection_measurement_binding_missing_or_stale"
    elif call.state == "failed" and route.get("input_overflow_refusal") is True:
        exhausted = consumed or route.get("overflow_recovery_attempt", 0) >= 1
        result.update(
            should_compact=not exhausted,
            compaction_blocked=exhausted,
            reason="input_overflow_recovery_exhausted"
            if exhausted
            else "typed_input_overflow_refusal",
        )
    elif (
        (
            call.state != "succeeded"
            and not (
                call.state in {"failed", "unknown", "reconciled"}
                and valid_input_projection(call, checkpoint_id)
            )
        )
        or not route.get("model")
        or route.get("actual_model") != route.get("model")
        or (
            route.get("mode") != "native"
            and (
                not route.get("actual_provider")
                or route.get("actual_provider", "").lower()
                not in [
                    str(p).lower()
                    for p in (route.get("qualified_provider_names") or route.get("providers") or [])
                ]
            )
        )
    ):
        result["reason"] = "unverified_main_route"
    else:
        value = (call.usage or {}).get("prompt_tokens")
        if _token(value) is None:
            result["reason"] = "prompt_usage_missing"
        else:
            result.update(
                prompt_tokens=value,
                eligible=True,
                should_compact=value >= trigger_tokens and not consumed,
                compaction_blocked=value >= trigger_tokens and consumed,
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
    cache_observed = cache_unknown = 0
    cached_total = sampled_prompt_total = 0
    for call in calls:
        route = call.route or {}
        if route.get("dispatch_not_started") is True:
            continue  # Local intent/preflight failure is neither paid nor reused.
        if route.get("paid_dispatch") is False:
            reused += 1
            continue
        if route.get("kind") != "openrouter" or call.state in {"intent", "fenced"}:
            continue
        dispatches = route.get("dispatch_attempts")
        if not isinstance(dispatches, list) or not dispatches:
            dispatches = [
                {"response_id": (call.result or {}).get("response_id"), "usage": call.usage or {}}
            ]
        # Network attempts are separate cost observations, even when their
        # logical tool-loop turn eventually succeeds. Missing fees stay unknown.
        for index, dispatch in enumerate(dispatches, 1):
            identity = dispatch.get("response_id") or f"{call.id}:{index}"
            if identity in seen:
                continue
            seen.add(identity)
            purpose = "helper" if route.get("purpose") == "compaction" else "main"
            counts[purpose] += 1
            usage = dispatch.get("usage") or {}
            details = usage.get("prompt_tokens_details") or {}
            cached = reported_number(usage.get("cached_tokens", details.get("cached_tokens")))
            prompt = reported_number(usage.get("prompt_tokens"))
            if cached is not None and prompt is not None and cached <= prompt:
                cache_observed += 1
                cached_total += cached
                sampled_prompt_total += prompt
            else:
                cache_unknown += 1
            cost = reported_number(usage.get("cost"))
            if cost is None:
                unknown[purpose] += 1
            else:
                totals[purpose] += Decimal(str(cost))
    return {
        "cache_observed_calls": cache_observed,
        "cache_unknown_calls": cache_unknown,
        "provider_cached_tokens": cached_total if cache_observed else None,
        "cache_sample_prompt_tokens": sampled_prompt_total if cache_observed else None,
        "cache_token_ratio": cached_total / sampled_prompt_total if sampled_prompt_total else None,
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


MAX_NATIVE_TOKEN = 2**53 - 1


def _token(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= MAX_NATIVE_TOKEN else None


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except ArithmeticError:
        return None


def accounting_dispatches(calls: list[Any]) -> tuple[list[dict[str, Any]], int]:
    """Normalize existing receipts only. Identity aliases never create another charge.

    This is a read projection, not a new ledger or a provider reconciliation call.
    A generation received late fills missing native fields on its original dispatch.
    Conflicting observations remain missing and explicitly anomalous.
    """
    records: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    reused: set[str] = set()
    for call in calls:
        route, result = call.route or {}, call.result or {}
        if route.get("kind") != "openrouter" or route.get("dispatch_not_started") is True:
            continue
        if route.get("paid_dispatch") is False:
            reused.add(str(call.id))
            continue
        attempts = route.get("dispatch_attempts")
        if not isinstance(attempts, list) or not attempts:
            if call.state in {"intent", "fenced"}:
                continue
            attempts = [{"response_id": result.get("response_id"), "usage": call.usage or {}}]
        for index, attempt in enumerate(attempts, 1):
            if not isinstance(attempt, dict):
                attempt = {}
            generation = attempt.get("response_id")
            if index == len(attempts):
                generation = generation or result.get("response_id")
            fallback = f"{call.id}:{index}"
            identity = f"generation:{generation}" if generation else aliases.get(fallback, fallback)
            aliases[fallback] = identity
            # Same durable dispatch first seen without its generation ID.
            if identity != fallback and fallback in records:
                prior = records.pop(fallback)
                if identity not in records:
                    records[identity] = prior
                else:
                    target = records[identity]
                    target["models"].update(prior["models"])
                    target["conflicts"].update(prior["conflicts"])
                    for field in ("input", "output", "reasoning", "cached", "usd", "prices"):
                        old, new = target.get(field), prior.get(field)
                        if old is not None and new is not None and old != new:
                            target["conflicts"].add(field)
                        elif old is None and new is not None:
                            target[field] = new
            usage = attempt.get("usage") or {}
            if not isinstance(usage, dict):
                usage = {}
            if index == len(attempts):
                usage = {**(call.usage or {}), **usage}
            prompt_details = usage.get("prompt_tokens_details")
            prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
            output_details = usage.get("completion_tokens_details")
            output_details = output_details if isinstance(output_details, dict) else {}
            values = {
                "input": _token(usage.get("prompt_tokens")),
                "output": _token(usage.get("completion_tokens")),
                "reasoning": _token(
                    usage.get("reasoning_tokens", output_details.get("reasoning_tokens"))
                ),
                "cached": _token(usage.get("cached_tokens", prompt_details.get("cached_tokens"))),
                "usd": _money(usage.get("cost")),
            }
            late = result.get("generation") or {}
            values["prices"] = billing_sample(
                usage, late if isinstance(late, dict) else {}, generation
            )
            # Reconcile's metadata is authoritative only for this exact generation.
            if generation and isinstance(late, dict) and late.get("id") == generation:
                for key, raw in [
                    ("input", late.get("native_tokens_prompt")),
                    ("output", late.get("native_tokens_completion")),
                    ("usd", late.get("total_cost")),
                ]:
                    value = _money(raw) if key == "usd" else _token(raw)
                    if values[key] is None:
                        values[key] = value
                    elif value is not None and values[key] != value:
                        values[key] = None
                        values.setdefault("conflicts", set()).add(key)
            purpose = route.get("purpose", "main")
            record = records.setdefault(
                identity,
                {
                    "run_id": str(getattr(call, "run_id", "unassigned")),
                    "purpose": "helper"
                    if purpose == "compaction"
                    else "main"
                    if purpose == "main"
                    else "unclassified",
                    "conflicts": set(),
                    "models": set(),
                },
            )
            record["models"].add(str(route.get("actual_model") or route.get("model") or "unknown"))
            record["conflicts"].update(values.pop("conflicts", set()))
            for key, value in values.items():
                if key in record and record[key] is not None and value is not None:
                    if record[key] != value:
                        record["conflicts"].add(key)
                elif value is not None:
                    record[key] = value
    for record in records.values():
        # Validate subsets after partial/late receipts have been merged.
        for subset, whole in [("reasoning", "output"), ("cached", "input")]:
            if record.get(subset) is not None and (
                record.get(whole) is None or record[subset] > record[whole]
            ):
                record["conflicts"].add(subset)
        if record["conflicts"]:
            record["prices"] = None
        for key in record["conflicts"]:
            record[key] = None
    return list(records.values()), len(reused)


def accounting_summary(dispatches: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = len(dispatches)

    def metric(key: str) -> dict[str, Any]:
        values = [d[key] for d in dispatches if d.get(key) is not None]
        total = sum(values, Decimal(0) if key == "usd" else 0) if values else None
        return {
            "known": str(total) if key == "usd" and total is not None else total,
            "observed": len(values),
            "missing": eligible - len(values),
            "complete": len(values) == eligible,
        }

    cache = [d for d in dispatches if d.get("cached") is not None and d.get("input") is not None]
    sample_input = sum(d["input"] for d in cache)
    cached = sum(d["cached"] for d in cache)
    return {
        "eligible_dispatches": eligible,
        "input": metric("input"),
        "output": metric("output"),
        "reasoning": metric("reasoning"),
        "usd": metric("usd"),
        "cache": {
            "cached": cached if cache else None,
            "sample_input": sample_input if cache else None,
            "ratio": cached / sample_input if sample_input else None,
            "observed": len(cache),
            "missing": eligible - len(cache),
            "complete": len(cache) == eligible,
        },
        "purpose_counts": {
            p: sum(d["purpose"] == p for d in dispatches)
            for p in ("main", "helper", "unclassified")
        },
        "anomaly_dispatches": sum(bool(d["conflicts"]) for d in dispatches),
        "native_models": sorted({model for d in dispatches for model in d["models"]}),
        "effective_completion_per_second": None,
    }


def conversation_metrics(
    calls: list[Any],
    runs: list[Any],
    messages: list[Any],
    *,
    as_of: str,
    scope_start: str,
    trigger_tokens: int = COMPACTION_TRIGGER,
) -> dict[str, Any]:
    dispatches, reused = accounting_dispatches(calls)
    measured = None
    for call in calls:
        route = call.route or {}
        observation = prompt_observation(
            call,
            route.get("context_revision"),
            checkpoint_id=(route.get("input_projection") or {}).get("checkpoint_id"),
            require_projection=bool(route.get("input_projection")),
        )
        if observation["eligible"]:
            binding = route.get("input_projection") or {}
            measured = {
                "tokens": observation["prompt_tokens"],
                "as_of": str(getattr(call, "updated_at", as_of)),
                "state": "last_measured_current_projection_pending",
                "request_fingerprint": binding.get("request_fingerprint"),
                "projection_fingerprint": binding.get("projection_fingerprint"),
                "message_frontier": binding.get("message_frontier"),
                "working_frontier": binding.get("working_frontier"),
                "model": route.get("actual_model") or route.get("model"),
            }
    bound = {
        str(m.run_id): str(m.id) for m in messages if m.role == "assistant" and m.run_id is not None
    }
    by_run: dict[str, list[dict[str, Any]]] = {}
    for dispatch in dispatches:
        by_run.setdefault(dispatch["run_id"], []).append(dispatch)
    rows = []
    assigned = set()
    for run in runs:
        run_id = str(run.id)
        assigned.add(run_id)
        rows.append(
            {
                "run_id": run_id,
                "assistant_message_id": bound.get(run_id),
                "state": run.state,
                **accounting_summary(by_run.get(run_id, [])),
            }
        )
    unassigned = [d for d in dispatches if d["run_id"] not in assigned]
    if unassigned:
        rows.append(
            {
                "run_id": None,
                "assistant_message_id": None,
                "state": "unassigned",
                **accounting_summary(unassigned),
            }
        )
    return {
        "version": 1,
        "scope": "all_retained_conversation_receipts",
        "scope_complete": True,
        "scope_start": scope_start,
        "as_of": as_of,
        "provenance": "server_receipts_native_usage_and_matching_generation_metadata",
        "retention": "existing_deletion_policy_no_shadow_history",
        "last_measured_input": measured,
        "context_policy": {
            "operating_input_tokens": 400_000,
            "compaction_trigger_tokens": trigger_tokens,
            "current_projection_measurement": "pending",
        },
        "reused_calls": reused,
        "token_prices": summarize_prices(dispatches),
        **accounting_summary(dispatches),
        "responses": rows,
    }


def valid_input_projection(call, checkpoint_id) -> bool:
    binding = (call.route or {}).get("input_projection")
    return (
        isinstance(binding, dict)
        and binding.get("version") == 1
        and binding.get("request_fingerprint") == call.request_fingerprint
        and isinstance(binding.get("projection_fingerprint"), str)
        and len(binding["projection_fingerprint"]) == 64
        and binding.get("model") == (call.route or {}).get("model")
        and binding.get("checkpoint_id") == (str(checkpoint_id) if checkpoint_id else None)
        and type(binding.get("message_frontier")) is int
        and binding["message_frontier"] >= 0
    )
