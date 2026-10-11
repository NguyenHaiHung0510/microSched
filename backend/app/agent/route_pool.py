"""Finite on-demand exact-model endpoint eligibility, with no privacy relaxation.

Native policy enforces ZDR/deny and exact variant slugs. Missing local hard
metadata is a no-eligible result, never a lower privacy or cross-model fallback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
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
    qualification_sha256: str | None = None
    qualification_expires_at: float | None = None
    provider_names: tuple[str, ...] = ()


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
    qualifications=None,
    scope_sha256=None,
    context_tokens=1_048_576,
    output_tokens=8192,
):
    if model != ADMITTED_MODEL or effort not in {"low", "high", "max"}:
        raise NoEligibleEndpoint("selected_model_or_effort_not_admitted")
    if not math.isfinite(threshold) or not 95 <= threshold < 100 or window not in {"1d", "30m"}:
        raise NoEligibleEndpoint("uptime_policy_invalid")
    if (
        not 0 <= input_ceiling <= 0.20
        or not 0 <= output_ceiling <= 0.60
        or tuple(quantizations) != ("fp8",)
    ):
        raise NoEligibleEndpoint("approved_price_or_precision_boundary_invalid")
    if not isinstance(payload, dict):
        raise NoEligibleEndpoint("endpoint_catalog_model_shape_invalid")
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
        if row.get("supports_tool_choice_function") is False:
            reason = reason or "named_function_explicitly_unsupported"
        # Profile-supported effort + native require_parameters enforce the wire
        # parameter; an explicitly narrower endpoint effort declaration wins.
        efforts = row.get("supported_reasoning_efforts")
        if efforts is not None and (not isinstance(efforts, list) or effort not in efforts):
            reason = reason or "selected_effort_not_supported"
        if row.get("quantization") not in quantizations:
            reason = reason or "precision_not_qualified"
        if any(
            type(row.get(field)) is not int or row[field] < bound
            for field, bound in (
                ("context_length", context_tokens),
                ("max_completion_tokens", output_tokens),
            )
        ):
            reason = reason or "endpoint_capacity_missing_or_insufficient"
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
    qualification_hash = None
    expires = None
    provider_names = []
    if qualifications is not None:
        at = time.time() if now is None else now
        accepted = {}
        deadlines = []
        for receipt in qualifications:
            if not isinstance(receipt, dict):
                continue
            tag = receipt.get("catalog_tag")
            slug = receipt.get("routing_slug")
            expiry = receipt.get("expires_at")
            evidence = receipt.get("evidence_sha256", {})
            if (
                not isinstance(receipt.get("provider_name"), str)
                or not receipt["provider_name"].strip()
                or tag not in tags
                or not isinstance(slug, str)
                or not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9_-]+)+", slug)
                or receipt.get("model") != model
                or receipt.get("effort") != effort
                or receipt.get("scope_sha256") != scope_sha256
                or any(
                    receipt.get("endpoint_sha256") != endpoint_fingerprint(r)
                    for r in rows
                    if isinstance(r, dict) and r.get("tag") == tag
                )
                or receipt.get("quantization") not in quantizations
                or receipt.get("zdr") is not True
                or receipt.get("data_collection") != "deny"
                or receipt.get("named_function") is not True
                or not isinstance(receipt.get("request_families"), list)
                or any(not isinstance(family, str) for family in receipt["request_families"])
                or set(receipt["request_families"]) != {"main", "summary", "forced_function"}
                or not isinstance(expiry, (int, float))
                or isinstance(expiry, bool)
                or not math.isfinite(expiry)
                or not at < expiry <= at + 86400
                or not isinstance(evidence, dict)
                or any(
                    not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get(axis, "")))
                    for axis in (
                        "routing_slug",
                        "privacy",
                        "effort",
                        "main",
                        "summary",
                        "forced_function",
                    )
                )
            ):
                continue
            # A catalog label is never presumed to be a documented routing slug.
            # Mapping and exact variant proof belong to the trusted receipt.
            if tag in accepted and accepted[tag] != slug:
                raise NoEligibleEndpoint("qualification_slug_conflict")
            accepted[tag] = slug
            deadlines.append(expiry)
            provider_names.append(receipt["provider_name"])
        tags = list(accepted.values())
        qualification_hash = digest(qualifications)
        expires = min(deadlines) if deadlines else None
        if not tags:
            raise NoEligibleEndpoint("no_eligible_qualified_endpoint")
    if not tags:
        raise NoEligibleEndpoint("no_endpoint_meets_frozen_hard_policy")
    return EndpointPool(
        model,
        effort,
        tuple(sorted(set(tags))),
        tuple(quantizations),
        digest(payload),
        time.time() if now is None else now,
        threshold,
        window,
        tuple(exclusions),
        qualification_hash,
        expires,
        tuple(sorted(set(provider_names))),
    )


def endpoint_fingerprint(row):
    """Material endpoint variant/capability drift, excluding volatile price/uptime."""
    return digest(
        {
            key: row.get(key)
            for key in (
                "tag",
                "name",
                "model_id",
                "provider_name",
                "quantization",
                "supported_parameters",
                "supported_reasoning_efforts",
                "supports_tool_choice_function",
                "context_length",
                "max_completion_tokens",
                "zdr",
                "data_collection",
            )
        }
    )


def qualification_scope(settings):
    """Exact immutable source/policy/config epoch for trusted endpoint receipts."""
    root = Path(__file__).parent
    files = (
        "route_pool.py",
        "route_config.py",
        "openrouter.py",
        "openai_sdk.py",
        "context_builder.py",
        "context.py",
        "policy.py",
        "service.py",
        "tools/registry.py",
        "policy/mimi-standard-v2.md",
        "policy/mimi-standard-v3.md",
        "policy/mimi-compaction-v2.md",
    )
    return digest(
        {
            "settings_source": hashlib.sha256(
                (root.parent / "core/settings.py").read_bytes()
            ).hexdigest(),
            "sources": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files
            },
            "model": settings.mimi_route_model,
            "effort": settings.mimi_route_reasoning_effort,
            "forced_choice": settings.mimi_route_forced_tool_choice,
            "compact_trigger": settings.mimi_compaction_trigger_tokens,
            "collection": settings.mimi_collection_enabled,
            "text_wire": settings.mimi_text_response_format,
            "output": settings.mimi_route_max_output_tokens,
            "context": settings.mimi_route_context_tokens,
            "zdr": settings.mimi_route_require_zdr,
        }
    )


class CatalogCache:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.entries = {}
        self.last_manual = 0.0

    async def refresh(self, settings, *, client=None, manual=False):
        try:
            qualifications = json.loads(settings.mimi_route_qualifications_json)
            if not isinstance(qualifications, list):
                raise ValueError()
        except ValueError, TypeError:
            raise NoEligibleEndpoint("qualification_manifest_invalid") from None
        scope = qualification_scope(settings)
        key = (
            digest(qualifications),
            scope,
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
            if (
                prior
                and not manual
                and now - prior.checked_at < POOL_TTL_SECONDS
                and prior.qualification_expires_at is not None
                and now < prior.qualification_expires_at
            ):
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
                qualifications=qualifications,
                scope_sha256=scope,
                now=now,
                context_tokens=settings.mimi_route_context_tokens,
                output_tokens=settings.mimi_route_max_output_tokens,
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
            "mimi_route_qualification_sha256": pool.qualification_sha256,
            "mimi_route_qualification_expires_at": pool.qualification_expires_at,
            "mimi_route_qualified_provider_names": pool.provider_names,
        }
    ), pool
