"""Public ``app_setting`` access through a hard allowlist (011c §2.1, §4.4).

``app_setting`` is SHARED with the private gate: ``private_pin``,
``private_unlock_throttle`` and ``private_unlock_ttl_minutes`` live in the same
table and a generic settings CRUD would leak the PIN hash (a 10^6 keyspace
invites offline brute force) or let the throttle/TTL be rewritten. Therefore:

* every query in this module filters ``AppSetting.key`` against the allowlist —
  a key supplied by the client is NEVER used as a bare ``WHERE key = ...``;
* keys outside the allowlist get a single ``404`` on BOTH GET and PATCH —
  one code for every unknown key, with no way to tell a real secret key from a
  made-up one (§2.1);
* a row with an invalid stored value raises loudly on the settings read path,
  while ``expiry_lead_days()`` (the 011b cron / F6 read) degrades to the
  default 3 + ``logger.error`` so one bad JSON row cannot kill the morning
  reminder run.

Value shape mirrors ``private_gate.py``: ``{"value": <scalar>}``. Note the
bool-before-int trap: ``isinstance(True, int)`` is True in Python, so the int
check must reject booleans explicitly.
"""

import logging
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AppSetting

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SettingSpec:
    """One allowlisted setting: type, default, and (optional) int bounds."""

    key: str
    kind: type
    default: Any
    minimum: int | None = None
    maximum: int | None = None

    def validate(self, value: Any) -> Any:
        """Validate a candidate value; raises ``ValueError`` (→ 422) when wrong."""
        if self.kind is bool:
            if not isinstance(value, bool):
                raise ValueError(f"'{self.key}' phải là giá trị đúng/sai.")
            return value
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"'{self.key}' phải là số nguyên.")
        if self.minimum is not None and (value < self.minimum or value > self.maximum):
            raise ValueError(f"'{self.key}' phải từ {self.minimum} đến {self.maximum}.")
        return value


PUBLIC_SETTING_SPECS: Final[dict[str, SettingSpec]] = {
    "subscription_expiry_lead_days": SettingSpec(
        key="subscription_expiry_lead_days",
        kind=int,
        default=3,
        minimum=0,
        maximum=30,
    ),
    "show_list_price": SettingSpec(key="show_list_price", kind=bool, default=True),
}

PUBLIC_SETTING_KEYS: Final[frozenset[str]] = frozenset(PUBLIC_SETTING_SPECS)


def public_spec(key: str) -> SettingSpec | None:
    """Return the spec only when ``key`` is allowlisted; None otherwise."""
    return PUBLIC_SETTING_SPECS.get(key)


async def _row(db: AsyncSession, key: str) -> AppSetting | None:
    """Read one setting row, always constrained to the allowlist (§2.1 hard rule)."""
    result = await db.execute(
        select(AppSetting).where(
            AppSetting.key == key,
            AppSetting.key.in_(PUBLIC_SETTING_KEYS),
        )
    )
    return result.scalar_one_or_none()


def _scalar(row: AppSetting) -> Any:
    if not isinstance(row.value, dict):
        return None
    return row.value.get("value")


async def list_public_settings(db: AsyncSession) -> list[dict[str, Any]]:
    """List every allowlisted key with its effective (default-applied) value."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.key.in_(PUBLIC_SETTING_KEYS))
    )
    rows = {row.key: row for row in result.scalars()}
    items: list[dict[str, Any]] = []
    for key, spec in PUBLIC_SETTING_SPECS.items():
        row = rows.get(key)
        if row is None:
            items.append({"key": key, "value": spec.default})
            continue
        try:
            items.append({"key": key, "value": spec.validate(_scalar(row))})
        except ValueError as error:
            # Loud path: corrupt stored data must not be silently "fixed".
            raise ValueError(f"Cài đặt '{key}' trong cơ sở dữ liệu không hợp lệ.") from error
    return items


async def get_public_setting(db: AsyncSession, key: str) -> dict[str, Any] | None:
    """Read one allowlisted key; None when the key is outside the allowlist."""
    spec = public_spec(key)
    if spec is None:
        return None
    row = await _row(db, key)
    if row is None:
        return {"key": key, "value": spec.default}
    try:
        return {"key": key, "value": spec.validate(_scalar(row))}
    except ValueError as error:
        raise ValueError(f"Cài đặt '{key}' trong cơ sở dữ liệu không hợp lệ.") from error


async def set_public_setting(
    db: AsyncSession, key: str, value: Any
) -> dict[str, Any] | None:
    """Upsert one allowlisted key; None when the key is outside the allowlist."""
    spec = public_spec(key)
    if spec is None:
        return None
    validated = spec.validate(value)  # ValueError → 422 for a valid key + bad value
    await db.execute(
        insert(AppSetting)
        .values(key=key, value={"value": validated})
        .on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": {"value": validated}},
        )
    )
    return {"key": key, "value": validated}


async def expiry_lead_days(db: AsyncSession) -> int:
    """Tolerant lead-days read for F6 upcoming and the 011b reminder cron.

    A missing row means the default (3); a corrupt row logs loudly and still
    returns the default — one bad JSON value must not kill the reminder run.
    """
    spec = PUBLIC_SETTING_SPECS["subscription_expiry_lead_days"]
    row = await _row(db, "subscription_expiry_lead_days")
    if row is None:
        return spec.default
    try:
        return spec.validate(_scalar(row))
    except ValueError:
        logger.error(
            "app_setting 'subscription_expiry_lead_days' is invalid; using default %s",
            spec.default,
        )
        return spec.default


async def show_list_price(db: AsyncSession) -> bool:
    """Tolerant list-price read; a corrupt row logs and falls back to ``True``."""
    spec = PUBLIC_SETTING_SPECS["show_list_price"]
    row = await _row(db, "show_list_price")
    if row is None:
        return spec.default
    try:
        return spec.validate(_scalar(row))
    except ValueError:
        logger.error("app_setting 'show_list_price' is invalid; using default %s", spec.default)
        return spec.default
