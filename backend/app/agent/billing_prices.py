"""Existing generation GET -> scalar usage metadata -> historical rate projection.

No catalog lookup, raw content, extra retention, provider dispatch or schema changes.
"""

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

# Missing is not zero. These are optional billing evidence, never user content.
TOKEN_FIELDS = (
    "native_tokens_prompt",
    "native_tokens_completion",
    "native_tokens_cached",
    "native_tokens_reasoning",
    "native_tokens_completion_images",
    "num_media_prompt",
    "num_media_completion",
    "num_input_audio_prompt",
    "num_search_results",
    "num_fetches",
)
COST_FIELDS = (
    "total_cost",
    "cache_discount",
    "upstream_inference_cost",
    "upstream_inference_prompt_cost",
    "upstream_inference_completions_cost",
)
GROUPS = ("input_uncached", "cache_read", "output")
EXCLUSIONS = (
    "native_tokens_completion_images",
    "num_media_prompt",
    "num_media_completion",
    "num_input_audio_prompt",
    "num_search_results",
    "num_fetches",
)


def text_response_shape(message: Any) -> bool:
    """Inspect shape only; never persist message text or tool arguments here."""
    if not isinstance(message, dict):
        return False
    if any(message.get(name) is not None for name in ("images", "audio", "video", "annotations")):
        return False
    return message.get("content") is None or isinstance(message["content"], str)


def attest_text_billing(
    usage: dict, request: dict, response_id: str, *, response_text: bool
) -> None:
    """Server observation of the exact built wire, separate from provider counters.

    The SDK supplies no preset/online model or remote plugins in this class.
    Unknown request features or response media cannot inherit this attestation.
    """
    usage.pop("mimi_billing_class", None)  # Provider cannot self-issue server proof.
    allowed = {
        "model",
        "messages",
        "stream",
        "store",
        "reasoning",
        "usage",
        "provider",
        "max_tokens",
        "tool_choice",
        "tools",
        "stream_options",
        "response_format",
        "session_id",
    }
    model = request.get("model")
    messages, tools = request.get("messages"), request.get("tools", [])
    if (
        not response_id
        or not response_text
        or not set(request) <= allowed
        or not isinstance(model, str)
        or model.startswith("@")
        or ":online" in model
        or not isinstance(messages, list)
        or not messages
        or any(not text_response_shape(message) for message in messages)
        or not isinstance(tools, list)
        or any(not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools)
    ):
        return
    usage["mimi_billing_class"] = {
        "version": 1,
        "source": "server_sdk_wire",
        "generation_id": response_id,
        "billing_class": "text_only_no_plugins",
    }


def token(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value < 2**53 else None


def money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def safe_generation_billing(metadata: dict, response_id: str) -> dict:
    if not isinstance(metadata, dict) or metadata.get("id") != response_id:
        return {}
    result = {
        name: metadata[name] for name in TOKEN_FIELDS if token(metadata.get(name)) is not None
    }
    result.update(
        {
            name: str(value)
            for name in COST_FIELDS
            if (value := money(metadata.get(name))) is not None
        }
    )
    if type(metadata.get("is_byok")) is bool:
        result["is_byok"] = metadata["is_byok"]
    if any(metadata.get(name) is not None and token(metadata[name]) is None for name in EXCLUSIONS):
        result["invalid_exclusion_evidence"] = True
    return {"generation_id": response_id, **result}


async def enrich_generation_usage(usage: dict, response_id: str, *, settings: Any) -> None:
    """One bounded best-effort metadata GET per new terminal; no retries/backfill.

    Caller has released its DB transaction. A timeout cannot re-dispatch the model.
    No negative evidence is synthesized when this optional read is unavailable.
    """
    if not response_id or not settings.mimi_live_provider_enabled:
        return
    from app.agent.openrouter import get_generation

    try:
        sample = billing_sample(usage, {}, response_id)
        if sample and not sample.get("unknown_groups"):
            return
        async with asyncio.timeout(0.8):
            metadata = await get_generation(response_id, settings=settings)
        safe = safe_generation_billing(metadata, response_id)
        if safe:
            prior = usage.get("mimi_billing")
            prior = (
                prior
                if isinstance(prior, dict) and prior.get("generation_id") == response_id
                else {}
            )
            usage["mimi_billing"] = {**prior, **safe}
    except Exception:
        # Auxiliary stats must never turn a useful completion into a failed run.
        # External cancellation still propagates (CancelledError is BaseException).
        return


def billing_sample(usage: dict, generation: dict, response_id: str | None) -> dict | None:
    """Common charged-cost proof, then independent native token groups.

    Generation lookup upstream cost is BYOK-only accounting, not terminal billed
    upstream cost. Retain it in safe metadata but never equate it to this split.
    """
    if not response_id:
        return None
    metadata = usage.get("mimi_billing")
    if not isinstance(metadata, dict) or metadata.get("generation_id") != response_id:
        metadata = safe_generation_billing(generation, response_id)
    if metadata.get("is_byok") is not False:
        return None
    if metadata.get("invalid_exclusion_evidence") is True:
        return None
    classification = usage.get("mimi_billing_class")
    attested = isinstance(classification, dict) and classification == {
        "version": 1,
        "source": "server_sdk_wire",
        "generation_id": response_id,
        "billing_class": "text_only_no_plugins",
    }
    # Null/missing is not zero. Server-attested actual shape is alternative proof;
    # any explicit nonzero/invalid exclusion still defeats it.
    if any(metadata.get(name) is not None and token(metadata[name]) != 0 for name in EXCLUSIONS):
        return None
    if not attested and any(token(metadata.get(name)) != 0 for name in EXCLUSIONS):
        return None
    details = usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        return None
    for section, fields in (
        (details, ("audio_tokens", "video_tokens", "image_tokens")),
        (usage.get("completion_tokens_details") or {}, ("audio_tokens", "image_tokens")),
    ):
        if not isinstance(section, dict) or any(
            name in section and token(section[name]) != 0 for name in fields
        ):
            return None
    costs = usage.get("cost_details") or {}
    if not isinstance(costs, dict):
        return None
    # Both split and charged total come from the same terminal endpoint. Equal
    # matched generation total confirms that the split excludes no billed fee.
    prompt_cost, output_cost = (
        money(costs.get(name))
        for name in ("upstream_inference_prompt_cost", "upstream_inference_completions_cost")
    )
    total, terminal_total = money(metadata.get("total_cost")), money(usage.get("cost"))
    if any(value is None for value in (prompt_cost, output_cost, total, terminal_total)):
        return None
    assert prompt_cost is not None and output_cost is not None
    assert total is not None and terminal_total is not None
    if abs(prompt_cost + output_cost - total) > Decimal("1e-12") or abs(
        terminal_total - total
    ) > Decimal("1e-12"):
        return None
    if "upstream_inference_cost" in costs:
        observed = money(costs["upstream_inference_cost"])
        if observed is None or abs(observed - total) > Decimal("1e-12"):
            return None
    prompt, output, cached = (
        token(metadata.get(name))
        for name in ("native_tokens_prompt", "native_tokens_completion", "native_tokens_cached")
    )
    prompt_ok = bool(prompt) and (
        "prompt_tokens" not in usage or token(usage["prompt_tokens"]) == prompt
    )
    output_ok = bool(output) and (
        "completion_tokens" not in usage or token(usage["completion_tokens"]) == output
    )
    reasoning = metadata.get("native_tokens_reasoning")
    if reasoning is not None and (token(reasoning) is None or output is None or reasoning > output):
        output_ok = False
    cache_ok = cached is not None and prompt is not None and cached <= prompt
    if "cached_tokens" in details and token(details["cached_tokens"]) != cached:
        cache_ok = False
    write_free = token(details.get("cache_write_tokens")) == 0
    discount = money(metadata.get("cache_discount"))
    result = {group: None for group in GROUPS}
    not_applicable = []
    if output_ok:
        result["output"] = (output_cost / output, output)
    if cache_ok and cached == 0:
        not_applicable.append("cache_read")
        if prompt_ok and write_free and (discount == 0 or metadata.get("cache_discount") is None):
            result["input_uncached"] = (prompt_cost / prompt, prompt)
    elif cache_ok and prompt_ok and write_free and discount is not None:
        input_rate = (prompt_cost + discount) / prompt
        cached_rate = input_rate - discount / cached
        if cached_rate >= 0:
            result["cache_read"] = (cached_rate, cached)
            if prompt > cached:
                result["input_uncached"] = (input_rate, prompt - cached)
            else:
                not_applicable.append("input_uncached")
    if not any(result.values()):
        return None
    result["unknown_groups"] = [
        group for group in GROUPS if result[group] is None and group not in not_applicable
    ]
    result["not_applicable"] = not_applicable
    return result


def summarize_prices(dispatches: list[dict]) -> dict:
    result: dict[str, Any] = {"unit": "USD_per_1M_tokens", "source": "matched_native_billing"}
    for group in GROUPS:
        samples = [
            d["prices"][group] for d in dispatches if d.get("prices") and d["prices"].get(group)
        ]
        rates = [rate for rate, _ in samples]
        tokens = sum(weight for _, weight in samples)
        result[group] = {
            "min": str(min(rates) * 1_000_000) if rates else None,
            "weighted_average": str(
                sum(rate * weight for rate, weight in samples) / tokens * 1_000_000
            )
            if tokens
            else None,
            "max": str(max(rates) * 1_000_000) if rates else None,
            "samples": len(samples),
            "tokens": tokens,
            "unknown": sum(
                not d.get("prices") or group in d["prices"].get("unknown_groups", [])
                for d in dispatches
            ),
            "not_applicable": sum(
                group in (d.get("prices") or {}).get("not_applicable", []) for d in dispatches
            ),
        }
    result["matched_dispatches"] = sum(bool(d.get("prices")) for d in dispatches)
    result["unknown_dispatches"] = len(dispatches) - result["matched_dispatches"]
    result["partial_dispatches"] = sum(
        bool((d.get("prices") or {}).get("unknown_groups")) for d in dispatches
    )
    return result
