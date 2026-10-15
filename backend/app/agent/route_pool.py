"""Finite on-demand exact-model endpoint eligibility, with no privacy relaxation.

Native policy enforces ZDR/deny and exact variant slugs. Missing local hard
metadata is a no-eligible result, never a lower privacy or cross-model fallback.
"""

from __future__ import annotations

import ast
import asyncio
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
POOL_TTL_SECONDS = 900
POOL_GRACE_SECONDS = 7200
MAX_CATALOG_BYTES = 2_097_152
CATALOG_TIMEOUT_SECONDS = 2
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
    native_prompt_ceiling: int | None = None
    native_context_floor: int | None = None


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
    input_ceiling=0.36,
    output_ceiling=1.44,
    quantizations=("fp8",),
    now=None,
    qualifications=None,
    scope_sha256=None,
    context_tokens=408_192,
    output_tokens=8192,
):
    if model != ADMITTED_MODEL or effort not in {"low", "high", "max"}:
        raise NoEligibleEndpoint("selected_model_or_effort_not_admitted")
    if not math.isfinite(threshold) or not 95 <= threshold < 100 or window not in {"1d", "30m"}:
        raise NoEligibleEndpoint("uptime_policy_invalid")
    from app.agent.config_policy import finite_price

    try:
        input_ceiling, output_ceiling = finite_price(input_ceiling), finite_price(output_ceiling)
    except ValueError:
        raise NoEligibleEndpoint("approved_price_or_precision_boundary_invalid") from None
    if tuple(quantizations) != ("fp8",):
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
        if row.get("revoked") is True:
            reason = "endpoint_known_revoked"
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
                ("context_length", max(408_192, context_tokens)),
                ("max_completion_tokens", max(8192, output_tokens)),
            )
        ):
            reason = reason or "endpoint_capacity_missing_or_insufficient"
        if row.get("max_prompt_tokens") is not None and (
            type(row["max_prompt_tokens"]) is not int or row["max_prompt_tokens"] < 400_000
        ):
            reason = reason or "endpoint_prompt_capacity_insufficient"
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
    admitted_catalog_tags = set(tags)
    qualification_hash = None
    expires = None
    provider_names = []
    if qualifications is not None:
        at = time.time() if now is None else now
        accepted = {}
        deadlines = []
        revoked_tags = {
            receipt.get("catalog_tag")
            for receipt in qualifications
            if isinstance(receipt, dict)
            and receipt.get("revoked") is True
            and receipt.get("model") == model
            and isinstance(receipt.get("catalog_tag"), str)
        }
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
                or tag in revoked_tags
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
                or receipt.get("revoked") is True
                or (
                    expiry is not None
                    and (
                        not isinstance(expiry, (int, float))
                        or isinstance(expiry, bool)
                        or not math.isfinite(expiry)
                        or not at < expiry
                    )
                )
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
            if expiry is not None:
                deadlines.append(expiry)
            provider_names.append(receipt["provider_name"])
        admitted_catalog_tags = set(accepted)
        tags = list(accepted.values())
        qualification_hash = digest(qualifications)
        expires = min(deadlines) if deadlines else at + POOL_GRACE_SECONDS
        if not tags:
            raise NoEligibleEndpoint("no_eligible_qualified_endpoint")
    if not tags:
        raise NoEligibleEndpoint("no_endpoint_meets_frozen_hard_policy")
    admitted_rows = [
        r for r in rows if isinstance(r, dict) and r.get("tag") in admitted_catalog_tags
    ]
    capacities = [r.get("context_length") for r in admitted_rows]
    if not capacities or any(
        type(v) is not int or not 408_192 <= v <= 16_777_216 for v in capacities
    ):
        raise NoEligibleEndpoint("native_capacity_bound_missing_or_outside_resource_range")
    # The largest permitted endpoint can incur the largest input bill. Separate
    # max_prompt_tokens narrows it only when that native field is present/valid.
    prompt_ceilings = [
        min(r["context_length"], r.get("max_prompt_tokens") or r["context_length"])
        for r in admitted_rows
    ]
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
        max(prompt_ceilings),
        min(capacities),
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
                "max_prompt_tokens",
                "zdr",
                "data_collection",
            )
        }
    )


def qualification_scope(settings):
    """Material protocol scope, independently qualified by native receipts.

    Owner172 D11 permits event-only reuse. Keep real parser/transport/schema
    fingerprints and endpoint evidence; unrelated price/input/storage edits do
    not invalidate compatibility. This is not a static marker replacing proof.
    """
    root = Path(__file__).parent
    try:
        aliases = json.loads(settings.mimi_route_identity_aliases_json)
        if not isinstance(aliases, dict):
            raise ValueError()
    except ValueError, TypeError:
        raise NoEligibleEndpoint("identity_alias_manifest_invalid") from None
    protocol_nodes = {
        "openrouter.py": {
            "parse_agent_completion",
            "parse_compaction_completion",
            "parse_completion",
            "validate_task_candidate",
            "validate_response_identity",
            "merge_stream_identity",
            "_provider_policy",
            "_price_policy",
            "_tool_choice",
            "complete",
            "complete_stream",
            "_rejected_terminal_metadata",
            "_input_overflow_error",
        },
        "openai_sdk.py": {
            "_request_kwargs",
            "_completion_payload",
            "_client",
            "_raise_for_sdk_error",
            "complete",
            "complete_stream",
        },
        "context.py": {
            "StrictModel",
            "ToolRequest",
            "ToolRequests",
            "AssistantText",
            "Clarification",
            "Draft",
            "PreviewCandidate",
            "Blocked",
            "parse_terminal_wire",
        },
    }
    fingerprints = {}
    for name, selected in protocol_nodes.items():
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        nodes = {
            node.name: ast.dump(node, include_attributes=False)
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in selected
        }
        if set(nodes) != selected:
            raise NoEligibleEndpoint("compatibility_protocol_source_missing")
        fingerprints[name] = digest(nodes)
        # Wire-format constants and request assignments are protocol, whereas
        # the full builder's byte/resource guards are admission policy. Hash
        # real AST nodes rather than a manually renewed version marker.
        if name == "openai_sdk.py":
            fingerprints["sdk_wire_constants"] = digest(
                [
                    ast.dump(node, include_attributes=False)
                    for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name)
                        and target.id
                        in {"_OPENROUTER_BASE_URL", "_EXTRA_BODY_FIELDS", "_METADATA_HEADERS"}
                        for target in node.targets
                    )
                ]
            )
        if name == "openrouter.py":
            builder = next(
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "build_request"
            )

            def wire_target(target):
                while isinstance(target, ast.Subscript):
                    target = target.value
                return isinstance(target, ast.Name) and target.id in {"request", "active_tools"}

            wire_nodes = [
                statement
                for statement in builder.body
                if any(
                    isinstance(node, (ast.Assign, ast.AnnAssign))
                    and any(
                        wire_target(target)
                        for target in (
                            node.targets if isinstance(node, ast.Assign) else [node.target]
                        )
                    )
                    for node in ast.walk(statement)
                )
            ]
            if not wire_nodes:
                raise NoEligibleEndpoint("compatibility_request_source_missing")
            fingerprints["request_wire_grammar"] = digest(
                [ast.dump(node, include_attributes=False) for node in wire_nodes]
            )
    own_tree = ast.parse((root / "route_pool.py").read_text(encoding="utf-8"))
    fingerprints["route_admission"] = digest(
        {
            node.name: ast.dump(node, include_attributes=False)
            for node in own_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"eligible_pool", "endpoint_fingerprint"}
        }
    )
    from app.agent.context import AGENT_RESPONSE_FORMAT
    from app.agent.openrouter import COMPACTION_RESPONSE_FORMAT
    from app.agent.tools.registry import registry_hash, tools_for_settings

    return digest(
        {
            "protocol_sha256": fingerprints,
            "tool_schema_sha256": registry_hash(tools_for_settings(settings)),
            "response_schemas": digest([AGENT_RESPONSE_FORMAT, COMPACTION_RESPONSE_FORMAT]),
            "model": settings.mimi_route_model,
            "effort": settings.mimi_route_reasoning_effort,
            "forced_choice": settings.mimi_route_forced_tool_choice,
            "collection": settings.mimi_collection_enabled,
            "text_wire": settings.mimi_text_response_format,
            "identity_aliases": digest(aliases),
            "output": settings.mimi_route_max_output_tokens,
            "zdr": settings.mimi_route_require_zdr,
        }
    )


class CatalogCache:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.entries = {}
        self.inflight = {}
        self.errors = {}
        self.last_manual = 0.0

    async def _load(self, model, client):
        owns = client is None
        client = client or httpx.AsyncClient(
            timeout=CATALOG_TIMEOUT_SECONDS, follow_redirects=False
        )
        try:
            async with client.stream(
                "GET",
                "https://openrouter.ai/api/v1/models/" + quote(model, safe="/") + "/endpoints",
            ) as response:
                if response.status_code != 200:
                    raise NoEligibleEndpoint("endpoint_catalog_unavailable")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_CATALOG_BYTES:
                        raise NoEligibleEndpoint("endpoint_catalog_size_exceeded")
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
                raise NoEligibleEndpoint("endpoint_catalog_model_shape_invalid")
            if payload["data"].get("id") != model or not isinstance(
                payload["data"].get("endpoints"), list
            ):
                raise NoEligibleEndpoint("endpoint_catalog_model_shape_invalid")
            # Retain successful empty snapshots: fresh removal must not resurrect
            # a provider from the previous successful metadata in SWR grace.
            entry = (payload, time.time())
            self.entries[model] = entry
            self.errors.pop(model, None)
            return entry
        except (httpx.HTTPError, ValueError) as error:
            self.errors[model] = type(error).__name__
            raise NoEligibleEndpoint("endpoint_catalog_unavailable") from error
        finally:
            if owns:
                await client.aclose()

    async def _single_flight(self, model, client):
        async with self.lock:
            task = self.inflight.get(model)
            if task is None or task.done():
                task = asyncio.create_task(
                    asyncio.wait_for(self._load(model, client), CATALOG_TIMEOUT_SECONDS)
                )
                self.inflight[model] = task
                task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
            return task

    async def refresh(self, settings, *, client=None, manual=False):
        if (
            settings.mimi_route_model != ADMITTED_MODEL
            or settings.mimi_route_reasoning_effort not in {"low", "high", "max"}
        ):
            raise NoEligibleEndpoint("selected_model_or_effort_not_admitted")
        try:
            qualifications = json.loads(settings.mimi_route_qualifications_json)
            if not isinstance(qualifications, list):
                raise ValueError()
        except ValueError, TypeError:
            raise NoEligibleEndpoint("qualification_manifest_invalid") from None
        scope = qualification_scope(settings)
        now = time.time()
        model = settings.mimi_route_model
        prior = self.entries.get(model)
        if manual:
            if now - self.last_manual < MANUAL_REFRESH_COOLDOWN_SECONDS:
                raise NoEligibleEndpoint("manual_catalog_refresh_cooldown")
            self.last_manual = now
        age = now - prior[1] if prior else float("inf")
        if manual or not 0 <= age < POOL_GRACE_SECONDS:
            task = await self._single_flight(model, client)
            try:
                prior = await asyncio.wait_for(asyncio.shield(task), CATALOG_TIMEOUT_SECONDS)
            except TimeoutError:
                raise NoEligibleEndpoint("endpoint_catalog_cold_timeout") from None
        elif age >= POOL_TTL_SECONDS:
            await self._single_flight(model, client)
        payload, fetched_at = prior
        # Raw metadata is reusable; current price/qualification filters are not.
        # This also makes a price reduction effective without another GET.
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
            now=time.time(),
            context_tokens=408_192,
            output_tokens=settings.mimi_route_max_output_tokens,
        )
        from dataclasses import replace

        return replace(pool, checked_at=fetched_at)


catalog = CatalogCache()


async def bind_pool(settings, *, client=None, manual=False):
    pool = await catalog.refresh(settings, client=client, manual=manual)
    return settings.model_copy(
        update={
            "mimi_route_allowed_providers": ",".join(pool.tags),
            "mimi_route_catalog_checked_at": pool.checked_at,
            "mimi_route_catalog_sha256": pool.snapshot_sha256,
            "mimi_route_qualification_sha256": pool.qualification_sha256,
            "mimi_route_qualification_expires_at": min(
                pool.qualification_expires_at, pool.checked_at + POOL_GRACE_SECONDS
            ),
            "mimi_route_qualified_provider_names": pool.provider_names,
            "mimi_route_billing_prompt_ceiling": pool.native_prompt_ceiling,
            "mimi_route_capacity_source": pool.snapshot_sha256,
            "mimi_route_context_tokens": pool.native_context_floor,
        }
    ), pool
