"""Finite on-demand exact-model endpoint eligibility, with no privacy relaxation.

Native policy enforces ZDR/deny and exact variant slugs. Missing local hard
metadata is a no-eligible result, never a lower privacy or cross-model fallback.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

from app.agent.task_collection import digest

ADMITTED_MODEL = "deepseek/deepseek-v4.1-flash"
POOL_TTL_SECONDS = 300
MAX_CATALOG_BYTES = 2_097_152
CATALOG_TIMEOUT_SECONDS = 10
MANUAL_REFRESH_COOLDOWN_SECONDS = 30


class NoEligibleEndpoint(ValueError):
    pass


@dataclass(frozen=True)
class EndpointPool:
    model: str
    effort: str
    tags: tuple[str, ...]
    quantizations: tuple[str, ...]
    snapshot_sha256: str
    checked_at: float
    threshold: float
    window: str
    exclusions: tuple[str, ...]


def price_per_million(value):
    try:
        price = Decimal(str(value)) * 1_000_000
    except InvalidOperation, ValueError:
        return None
    return price if price.is_finite() and price >= 0 else None


def eligible_pool(
    payload,
    *,
    model,
    effort,
    threshold=95.0,
    window="1d",
    input_ceiling=0.2,
    output_ceiling=0.6,
    quantizations=("fp8",),
    now=None,
):
    if model != ADMITTED_MODEL or effort not in {"low", "high", "max"}:
        raise NoEligibleEndpoint("selected_model_or_effort_not_admitted")
    if not math.isfinite(threshold) or not 0 <= threshold < 100 or window not in {"1d", "30m"}:
        raise NoEligibleEndpoint("uptime_policy_invalid")
    data = payload.get("data")
    if (
        not isinstance(data, dict)
        or data.get("id") != model
        or not isinstance(data.get("endpoints"), list)
    ):
        raise NoEligibleEndpoint("endpoint_catalog_model_shape_invalid")
    rows = data["endpoints"]
    tags = []
    exclusions = []
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            exclusions.append("malformed_endpoint")
            continue
        tag = row.get("tag")
        reason = None
        if (
            not isinstance(tag, str)
            or not tag.strip()
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_/" for c in tag)
        ):
            reason = "endpoint_exact_tag_unknown"
        uptime = row.get(f"uptime_last_{window}")
        if (
            not isinstance(uptime, (int, float))
            or isinstance(uptime, bool)
            or not math.isfinite(uptime)
            or not threshold < uptime <= 100
        ):
            reason = reason or "uptime_missing_or_below_strict_threshold"
        parameters = row.get("supported_parameters", [])
        if not isinstance(parameters, list) or not {"tools", "tool_choice", "reasoning"} <= set(
            parameters
        ):
            reason = reason or "required_parameter_unknown"
        # Profile-supported effort + native require_parameters enforce the wire
        # parameter; an explicitly narrower endpoint effort declaration wins.
        efforts = row.get("supported_reasoning_efforts")
        if efforts is not None and (not isinstance(efforts, list) or effort not in efforts):
            reason = reason or "selected_effort_not_supported"
        if row.get("quantization") not in quantizations:
            reason = reason or "precision_not_qualified"
        pricing = row.get("pricing", {})
        if not isinstance(pricing, dict):
            pricing = {}
        inp = price_per_million(pricing.get("prompt"))
        out = price_per_million(pricing.get("completion"))
        if (
            inp is None
            or out is None
            or inp > Decimal(str(input_ceiling))
            or out > Decimal(str(output_ceiling))
        ):
            reason = reason or "price_missing_or_above_ceiling"
        # ZDR/data collection is enforceable natively; if exposed contradictory
        # metadata exists, refuse it locally too. Absence is not certification.
        if row.get("zdr") is False or row.get("data_collection") == "allow":
            reason = reason or "privacy_ineligible"
        if isinstance(tag, str):
            grouped.setdefault(tag, []).append(reason)
        if reason:
            exclusions.append(reason)
    for tag, reasons in grouped.items():
        if any(reasons):
            continue
        # Base tags match all variants. Admit only when all variants exposed by
        # the same complete catalog pass; suffixed tags select the exact variant.
        if "/" not in tag and any(
            any(rs) for other, rs in grouped.items() if other.startswith(tag + "/")
        ):
            exclusions.append("base_tag_has_ineligible_variant")
            continue
        tags.append(tag)
    if not tags:
        raise NoEligibleEndpoint("no_endpoint_meets_frozen_hard_policy")
    return EndpointPool(
        model,
        effort,
        tuple(sorted(set(tags))),
        tuple(quantizations),
        digest(payload),
        now or time.time(),
        threshold,
        window,
        tuple(exclusions),
    )


class CatalogCache:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.entries = {}
        self.last_manual = 0.0

    async def refresh(self, settings, *, client=None, manual=False):
        key = (
            settings.mimi_route_model,
            settings.mimi_route_reasoning_effort,
            settings.mimi_route_min_uptime_percent,
            settings.mimi_route_uptime_window,
            settings.mimi_route_max_input_price,
            settings.mimi_route_max_output_price,
            settings.mimi_allowed_quantization_list,
        )
        async with self.lock:
            now = time.time()
            prior = self.entries.get(key)
            if manual and now - self.last_manual < MANUAL_REFRESH_COOLDOWN_SECONDS:
                raise NoEligibleEndpoint("manual_catalog_refresh_cooldown")
            if prior and not manual and now - prior.checked_at < POOL_TTL_SECONDS:
                return prior
            if manual:
                self.last_manual = now
            owns = client is None
            client = client or httpx.AsyncClient(
                timeout=CATALOG_TIMEOUT_SECONDS, follow_redirects=False
            )
            try:
                # Public metadata only, no auth/header secret and no model inference.
                async with client.stream(
                    "GET",
                    "https://openrouter.ai/api/v1/models/"
                    + quote(settings.mimi_route_model, safe="/")
                    + "/endpoints",
                ) as response:
                    if response.status_code != 200:
                        raise NoEligibleEndpoint("endpoint_catalog_unavailable")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_CATALOG_BYTES:
                            raise NoEligibleEndpoint("endpoint_catalog_size_exceeded")
                import json

                payload = json.loads(body)
            except (httpx.HTTPError, ValueError) as error:
                raise NoEligibleEndpoint("endpoint_catalog_unavailable") from error
            finally:
                if owns:
                    await client.aclose()
            pool = eligible_pool(
                payload,
                model=settings.mimi_route_model,
                effort=settings.mimi_route_reasoning_effort,
                threshold=settings.mimi_route_min_uptime_percent,
                window=settings.mimi_route_uptime_window,
                input_ceiling=settings.mimi_route_max_input_price,
                output_ceiling=settings.mimi_route_max_output_price,
                quantizations=settings.mimi_allowed_quantization_list,
            )
            self.entries[key] = pool
            return pool


catalog = CatalogCache()


async def bind_pool(settings, *, client=None, manual=False):
    pool = await catalog.refresh(settings, client=client, manual=manual)
    return settings.model_copy(
        update={
            "mimi_route_allowed_providers": ",".join(pool.tags),
            "mimi_route_catalog_checked_at": pool.checked_at,
            "mimi_route_catalog_sha256": pool.snapshot_sha256,
        }
    ), pool
