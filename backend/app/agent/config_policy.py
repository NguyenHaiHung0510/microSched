"""Owner-controlled global Mimi limits in the existing durable AppSetting seam.

Prices are manual USD per million token caps, never a market-price feed. The
transaction lock orders saves and dispatch admission; no migration is needed.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app.core.settings import Settings
from app.domain.models import AppSetting

# This is an AppSetting identifier; it is never an API credential.
OPERATING_POLICY_SETTING = "mimi.operating-policy.v1"
POLICY_KEY = OPERATING_POLICY_SETTING
POLICY_LOCK = 17207820261013
INPUT_CODEPOINT_RESOURCE_MAX = 100_000
OPERATING_INPUT_TOKENS = 400_000
OPERATING_OUTPUT_TOKENS = 8_192
PRICE_SANITY_MAX = Decimal("1000")


def finite_price(value) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("price_must_be_finite_decimal")
    try:
        result = Decimal(str(value))
    except InvalidOperation, ValueError, TypeError:
        raise ValueError("price_must_be_finite_decimal") from None
    if not result.is_finite() or not 0 <= result <= PRICE_SANITY_MAX:
        raise ValueError("price_outside_finite_resource_bound")
    return result


def normalize_model_prices(value):
    """Read old saved keys without mutating historical settings or run receipts."""
    from app.agent.route_config import DEEPSEEK_MODEL, LEGACY_DEEPSEEK_MODEL

    if not isinstance(value, dict):
        return value
    prices = dict(value)
    if LEGACY_DEEPSEEK_MODEL in prices:
        prices.setdefault(DEEPSEEK_MODEL, prices.pop(LEGACY_DEEPSEEK_MODEL))
    return prices


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prompt: Annotated[
        Decimal,
        Field(ge=0, le=PRICE_SANITY_MAX, allow_inf_nan=False, max_digits=12, decimal_places=8),
    ]
    completion: Annotated[
        Decimal,
        Field(ge=0, le=PRICE_SANITY_MAX, allow_inf_nan=False, max_digits=12, decimal_places=8),
    ]

    @field_validator("prompt", "completion", mode="before")
    @classmethod
    def validate_price(cls, value):
        return finite_price(value)


class OperatingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    revision: int = Field(ge=0, strict=True)
    input_codepoints: int = Field(
        default=50_000, ge=1_000, le=INPUT_CODEPOINT_RESOURCE_MAX, strict=True
    )
    prices: dict[str, ModelPrice]

    @field_validator("prices", mode="before")
    @classmethod
    def migrate_saved_model_key(cls, value):
        return normalize_model_prices(value)

    @field_validator("prices")
    @classmethod
    def supported_models_only(cls, value):
        from app.agent.route_config import PROFILES

        if set(value) != {p["model"] for p in PROFILES.values()}:
            raise ValueError("price_policy_requires_exact_supported_model_set")
        return value


class PolicyChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_revision: int = Field(ge=0, strict=True)
    input_codepoints: int = Field(ge=1_000, le=INPUT_CODEPOINT_RESOURCE_MAX, strict=True)
    prices: dict[str, ModelPrice]


def bootstrap_policy(settings: Settings) -> OperatingPolicy:
    from app.agent.route_config import PROFILES

    # Explicit initial caps/reference choices, not claims of current live rates.
    initial = {
        "luna": ("0.10", "0.50"),
        "mimo": ("0.43", "0.87"),
        "deepseek": ("0.36", "1.44"),
        "glm": ("0.15", "0.50"),
    }
    prices = {
        p["model"]: {"prompt": initial[k][0], "completion": initial[k][1]}
        for k, p in PROFILES.items()
    }
    return OperatingPolicy(
        revision=0, input_codepoints=settings.mimi_input_codepoints, prices=prices
    )


def policy_storage_value(policy: OperatingPolicy) -> dict:
    """Retain the old durable price key so reverting the binary can read it."""
    from app.agent.route_config import DEEPSEEK_MODEL, LEGACY_DEEPSEEK_MODEL

    value = policy.model_dump(mode="json")
    value["prices"][LEGACY_DEEPSEEK_MODEL] = value["prices"].pop(DEEPSEEK_MODEL)
    return value


def revised_policy(current: OperatingPolicy, change: PolicyChange) -> OperatingPolicy:
    if change.expected_revision != current.revision:
        raise HTTPException(409, "mimi_operating_policy_stale")
    return OperatingPolicy(
        revision=current.revision + 1,
        input_codepoints=change.input_codepoints,
        prices=change.prices,
    )


async def read_policy(db, settings: Settings, *, dispatch=False) -> OperatingPolicy:
    if dispatch:
        # Serialize the first durable seed with saves; subsequent reads use the
        # same short admission lock. Held until transport has started (or a JSON
        # completion returns), so a save cannot overtake an unsent wire.
        await db.execute(select(func.pg_advisory_xact_lock(POLICY_LOCK)))
    row = (
        await db.execute(
            select(AppSetting)
            .where(AppSetting.key == POLICY_KEY)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row:
        return OperatingPolicy.model_validate(row.value)
    initial = bootstrap_policy(settings)
    if dispatch:
        db.add(AppSetting(key=POLICY_KEY, value=policy_storage_value(initial)))
        await db.flush()
    return initial


async def save_policy(db, settings: Settings, change: PolicyChange) -> OperatingPolicy:
    await db.execute(select(func.pg_advisory_xact_lock(POLICY_LOCK)))
    row = (
        await db.execute(
            select(AppSetting)
            .where(AppSetting.key == POLICY_KEY)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    current = OperatingPolicy.model_validate(row.value) if row else bootstrap_policy(settings)
    result = revised_policy(current, change)
    if row is None:
        db.add(AppSetting(key=POLICY_KEY, value=policy_storage_value(result)))
    else:
        row.value = policy_storage_value(result)
    await db.flush()
    return result


def bind_policy(settings: Settings, policy: OperatingPolicy) -> Settings:
    from app.agent.route_config import DEEPSEEK_MODEL, LEGACY_DEEPSEEK_MODEL

    model = settings.mimi_route_model
    price = policy.prices.get(DEEPSEEK_MODEL if model == LEGACY_DEEPSEEK_MODEL else model)
    update = {
        "mimi_operating_policy_revision": policy.revision,
        "mimi_input_codepoints": policy.input_codepoints,
        "mimi_model_price_caps_json": json.dumps(
            {m: p.model_dump(mode="json") for m, p in policy.prices.items()}, sort_keys=True
        ),
    }
    if price is not None:
        update.update(
            mimi_route_max_input_price=price.prompt, mimi_route_max_output_price=price.completion
        )
    return settings.model_copy(update=update)


async def bind_wire_policy(db, settings: Settings) -> Settings:
    # The gateway evaluates its inventory; this boundary binds only Owner policy.
    return bind_policy(settings, await read_policy(db, settings, dispatch=True))


def validate_input(text: str, policy: OperatingPolicy) -> None:
    if len(text) > policy.input_codepoints:
        raise HTTPException(
            422,
            {
                "code": "mimi_input_codepoints_exceeded",
                "limit": policy.input_codepoints,
                "count": len(text),
            },
        )
