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
        if billing_sample(usage, {}, response_id) is not None:
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
    """Derive only when native counts, exclusions and the cost split reconcile."""
    if not response_id:
        return None
    metadata = usage.get("mimi_billing")
    if not isinstance(metadata, dict) or metadata.get("generation_id") != response_id:
        metadata = safe_generation_billing(generation, response_id)
    if metadata.get("is_byok") is not False:
        return None
    prompt, output, cached = (
        token(metadata.get(name))
        for name in ("native_tokens_prompt", "native_tokens_completion", "native_tokens_cached")
    )
    if not prompt or not output or cached is None or cached > prompt:
        return None
    if any(
        token(metadata.get(name)) != 0
        for name in (
            "native_tokens_completion_images",
            "num_media_prompt",
            "num_media_completion",
            "num_input_audio_prompt",
            "num_search_results",
            "num_fetches",
        )
    ):
        return None
    details = usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict) or token(details.get("cache_write_tokens")) != 0:
        return None
    # Native cache is a subset of prompt; reasoning is a subset of output.
    if token(metadata.get("native_tokens_reasoning")) is not None:
        if metadata["native_tokens_reasoning"] > output:
            return None
    for name, expected in (("prompt_tokens", prompt), ("completion_tokens", output)):
        if name in usage and token(usage[name]) != expected:
            return None
    if "cached_tokens" in details and token(details["cached_tokens"]) != cached:
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
    for name in ("upstream_inference_prompt_cost", "upstream_inference_completions_cost"):
        if name in metadata and name in costs:
            native_cost, receipt_cost = money(metadata[name]), money(costs[name])
            if (
                native_cost is None
                or receipt_cost is None
                or abs(native_cost - receipt_cost) > Decimal("1e-12")
            ):
                return None
    # Prefer native billing split when explicitly present, otherwise the matched
    # terminal's upstream split. Non-BYOK + equal totals excludes an extra fee.
    prompt_cost, output_cost = (
        money(metadata.get(name, costs.get(name)))
        for name in ("upstream_inference_prompt_cost", "upstream_inference_completions_cost")
    )
    total, discount = (money(metadata.get(name)) for name in ("total_cost", "cache_discount"))
    if any(value is None for value in (prompt_cost, output_cost, total, discount)):
        return None
    assert prompt_cost is not None and output_cost is not None
    assert total is not None and discount is not None
    if abs(prompt_cost + output_cost - total) > Decimal("1e-12"):
        return None
    for observed in (
        usage.get("cost"),
        costs.get("upstream_inference_cost"),
        metadata.get("upstream_inference_cost"),
    ):
        if observed is not None and (
            money(observed) is None or abs(money(observed) - total) > Decimal("1e-12")
        ):
            return None
    if cached == 0 and discount != 0:
        return None
    input_rate = (prompt_cost + discount) / prompt
    cached_rate = input_rate - discount / cached if cached else None
    if cached_rate is not None and cached_rate < 0:
        return None
    return {
        "input_uncached": (input_rate, prompt - cached) if prompt > cached else None,
        "cache_read": (cached_rate, cached) if cached else None,
        "output": (output_cost / output, output),
    }


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
        }
    result["matched_dispatches"] = sum(bool(d.get("prices")) for d in dispatches)
    result["unknown_dispatches"] = len(dispatches) - result["matched_dispatches"]
    return result
