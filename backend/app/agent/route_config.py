"""Allowlisted local model profiles and immutable per-run configuration.

Snapshot evidence: OpenRouter public models/endpoints, 2026-10-01. This is a
local candidate packet, not a benchmark champion or production default.
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
        "context_limit": 1_050_000,
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


class ConfigurationChange(RouteConfiguration):
    expected_version: int = Field(ge=1)


def profiles_for_ui(settings: Settings) -> list[dict[str, Any]]:
    enabled = (
        settings.app_env == "local"
        and settings.mimi_live_provider_enabled
        and settings.mimi_route_model in {p["model"] for p in PROFILES.values()}
    )
    return [
        {
            **{k: v for k, v in p.items() if k not in {"input_price", "output_price"}},
            "id": key,
            "available": enabled,
            "unavailable_reason": None if enabled else "Model thật chưa được bật ở môi trường này.",
        }
        for key, p in PROFILES.items()
    ]


def validate_configuration(value: dict[str, Any]) -> RouteConfiguration:
    config = RouteConfiguration.model_validate(value)
    profile = PROFILES.get(config.profile_id)
    if profile is None or config.effort not in profile["supported_efforts"]:
        raise HTTPException(status_code=422, detail="mimi_route_selection_not_supported")
    if config.input_tokens not in {32000, 100000, 200000}:
        raise HTTPException(status_code=422, detail="mimi_context_preset_not_supported")
    if config.input_tokens > profile["context_limit"]:
        raise HTTPException(status_code=422, detail="mimi_context_exceeds_model_limit")
    return config


def default_configuration(settings: Settings) -> dict[str, Any]:
    profile_id = next(
        (key for key, p in PROFILES.items() if p["model"] == settings.mimi_route_model), "mimo"
    )
    efforts = PROFILES[profile_id]["supported_efforts"]
    effort = settings.mimi_route_reasoning_effort
    if effort not in efforts:
        effort = "medium" if "medium" in efforts else efforts[0]
    return {"profile_id": profile_id, "effort": effort, "input_tokens": 100000}


def bind_configuration(settings: Settings, value: dict[str, Any]) -> Settings:
    """Copy settings at run admission; later UI changes cannot mutate this copy."""
    config = validate_configuration(value)
    profile = PROFILES[config.profile_id]
    return settings.model_copy(
        update={
            "mimi_route_mode": "exact",
            "mimi_route_model": profile["model"],
            "mimi_route_provider": profile["provider"],
            "mimi_route_quantization": profile["quantization"],
            "mimi_route_reasoning_effort": config.effort,
            "mimi_route_context_tokens": config.input_tokens,
            "mimi_route_max_output_tokens": profile["output_reserve"],
            "mimi_route_max_input_price": profile["input_price"],
            "mimi_route_max_output_price": profile["output_price"],
        }
    )
