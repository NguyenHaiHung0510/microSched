"""Allowlisted alpha model profiles and immutable per-run configuration.

Endpoint metadata snapshot: 2026-10-06. Route evidence is separate from metadata;
only the default with the strongest existing app receipts is alpha-admitted.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.settings import Settings

PROFILES = {
    "luna": {
        "label": "GPT-6 Luna",
        "model": "openai/gpt-6-luna",
        "provider": "openai",
        "quantization": "unknown",
        "supported_efforts": ["none", "low", "medium", "high"],
        "context_limit": 1_050_000,
        "max_output_tokens": 128_000,
        "output_reserve": 8192,
        "input_price": 0.10,
        "output_price": 0.50,
    },
    "mimo": {
        "label": "MiMo v2.6 Pro",
        "model": "xiaomi/mimo-v2.6-pro",
        "provider": "deepinfra",
        "quantization": "fp8",
        "supported_efforts": ["default"],
        "context_limit": 1_048_576,
        "max_output_tokens": 943_718,
        "output_reserve": 8192,
        "input_price": 0.43,
        "output_price": 0.87,
    },
    "deepseek": {
        "label": "DeepSeek V4.1 Flash",
        "model": "deepseek/deepseek-v4.1-flash",
        "provider": "deepinfra",
        "quantization": "fp8",
        "supported_efforts": ["low", "high"],
        "context_limit": 1_048_576,
        "max_output_tokens": 131_072,
        "output_reserve": 8192,
        # Conservative undiscounted ceiling, not dependence on 30% promotion.
        "input_price": 0.20,
        "output_price": 0.60,
    },
    "glm": {
        "label": "GLM 5.3 Flash",
        "model": "z-ai/glm-5.3-flash",
        "provider": "deepinfra",
        "quantization": "fp4",
        "supported_efforts": ["low", "high"],
        "context_limit": 1_048_576,
        "max_output_tokens": 131_072,
        "output_reserve": 8192,
        # Conservative undiscounted ceiling, not dependence on 50% promotion.
        "input_price": 0.15,
        "output_price": 0.50,
    },
}


class RouteConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile_id: str
    effort: str
    input_tokens: int = Field(ge=32000, le=200000)
    routing_mode: str = "adaptive"
    min_uptime_percent: float = Field(default=95.0, ge=0, lt=100, allow_inf_nan=False)
    uptime_window: str = "1d"


class ConfigurationChange(RouteConfiguration):
    expected_version: int = Field(ge=1)


def profiles_for_ui(settings: Settings) -> list[dict[str, Any]]:
    enabled = settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled
    evidence = {
        "deepseek": (
            True,
            "Task078 app read/create and checkpoint receipts, 2026-10-03; "
            "alpha100k live retake pending",
        ),
        "mimo": (False, "Route smoke exists; alpha tools/compaction continuity not qualified"),
        "glm": (False, "Route smoke exists; alpha tools/compaction continuity not qualified"),
        "luna": (False, "Observed ZDR eligibility404; no successful matching app route"),
    }
    return [
        {
            **{k: v for k, v in p.items() if k not in {"input_price", "output_price"}},
            "id": key,
            "available": enabled and evidence[key][0],
            "evidence": evidence[key][1],
            "compaction_trigger_tokens": 100_000,
            "unavailable_reason": (
                None
                if enabled and evidence[key][0]
                else evidence[key][1]
                if enabled
                else "Model thật chưa được bật ở môi trường này."
            ),
        }
        for key, p in PROFILES.items()
    ]


def validate_configuration(value: dict[str, Any], *, alpha: bool = False) -> RouteConfiguration:
    config = RouteConfiguration.model_validate(value)
    if config.routing_mode not in {"exact", "adaptive"} or config.uptime_window not in {
        "1d",
        "30m",
    }:
        raise HTTPException(status_code=422, detail="mimi_route_policy_invalid")
    profile = PROFILES.get(config.profile_id)
    if profile is None or config.effort not in profile["supported_efforts"]:
        raise HTTPException(status_code=422, detail="mimi_route_selection_not_supported")
    if config.input_tokens not in {32000, 100000, 200000}:
        raise HTTPException(status_code=422, detail="mimi_context_preset_not_supported")
    if alpha and config.input_tokens != 100_000:
        raise HTTPException(status_code=422, detail="mimi_alpha_trigger_requires_100k")
    if config.input_tokens > profile["context_limit"]:
        raise HTTPException(status_code=422, detail="mimi_context_exceeds_model_limit")
    return config


def default_configuration(settings: Settings) -> dict[str, Any]:
    profile_id = next(
        (key for key, p in PROFILES.items() if p["model"] == settings.mimi_route_model), None
    )
    if profile_id is None:
        if (
            settings.mimi_route_model
            and settings.mimi_live_provider_enabled
            and settings.mimi_collection_enabled
        ):
            raise HTTPException(409, "selected_model_not_admitted")
        profile_id = "deepseek" if settings.mimi_collection_enabled else "mimo"
    efforts = PROFILES[profile_id]["supported_efforts"]
    effort = settings.mimi_route_reasoning_effort
    if effort not in efforts:
        if settings.mimi_live_provider_enabled and settings.mimi_collection_enabled:
            raise HTTPException(409, "selected_effort_not_supported")
        effort = "medium" if "medium" in efforts else efforts[0]
    return {"profile_id": profile_id, "effort": effort, "input_tokens": 100000}


def bind_configuration(settings: Settings, value: dict[str, Any]) -> Settings:
    """Copy settings at run admission; later UI changes cannot mutate this copy."""
    # Old saved32k/200k configuration remains history. Every new alpha run
    # observes100k; do not rewrite old receipts or silently reroute a saved model.
    config = validate_configuration(value)
    if settings.mimi_live_provider_enabled:
        availability = {p["id"]: p for p in profiles_for_ui(settings)}
        if not availability[config.profile_id]["available"]:
            raise HTTPException(status_code=409, detail="mimi_route_not_alpha_qualified")
    profile = PROFILES[config.profile_id]
    return settings.model_copy(
        update={
            "mimi_route_mode": config.routing_mode if settings.mimi_collection_enabled else "exact",
            "mimi_route_min_uptime_percent": config.min_uptime_percent,
            "mimi_route_uptime_window": config.uptime_window,
            "mimi_route_allowed_providers": "",
            "mimi_route_allowed_quantizations": "fp8",
            "mimi_route_model": profile["model"],
            "mimi_route_provider": profile["provider"],
            "mimi_route_quantization": profile["quantization"],
            "mimi_route_reasoning_effort": config.effort,
            "mimi_route_context_tokens": profile["context_limit"],
            "mimi_compaction_trigger_tokens": 100_000,
            "mimi_route_max_output_tokens": profile["output_reserve"],
            "mimi_route_max_input_price": profile["input_price"],
            "mimi_route_max_output_price": profile["output_price"],
            # All four frozen exact endpoints advertise named function choice.
            # Revisions still require a typed replacement before server activation.
            "mimi_route_forced_tool_choice": "function",
        }
    )
