"""Postgres-backed private-display gate, PIN rotation, and global throttle."""

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, TypeAlias

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.private_pin import hash_pin, is_valid_pin, verify_pin
from app.core.settings import get_settings
from app.domain.models import AppSetting, AuthSession

logger = logging.getLogger(__name__)

PIN_SETTING_KEY = "private_pin"
THROTTLE_SETTING_KEY = "private_unlock_throttle"
TTL_SETTING_KEY = "private_unlock_ttl_minutes"
DEFAULT_TTL_MINUTES = 36
LOCK_LADDER = ((10, 5), (20, 8), (36, 18))

VerifyOutcome: TypeAlias = (
    Literal["OK"] | tuple[Literal["LOCKED"], int] | tuple[Literal["WRONG"], int] | Literal["NO_PIN"]
)
UnlockOutcome: TypeAlias = tuple[Literal["OK"], datetime] | VerifyOutcome


@dataclass(frozen=True)
class GateStatus:
    """Display-only state returned beside the signed-in session."""

    private_until: datetime | None
    locked_until: datetime | None
    pin_is_set: bool
    pin_is_bootstrap: bool


class WrongPinError(Exception):
    """The current PIN was wrong on the PIN-change path."""

    def __init__(self, remaining: int) -> None:
        self.remaining = remaining
        super().__init__("wrong PIN")


class ThrottleLockedError(Exception):
    """The global PIN verifier is temporarily locked."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("private PIN throttle locked")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_iso(value: datetime) -> str:
    """Serialize an aware UTC timestamp with the required literal Z suffix."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("private throttle timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _retry_after(locked_until: datetime, now: datetime) -> int:
    return max(1, math.ceil((locked_until - now).total_seconds()))


async def _setting(db: AsyncSession, key: str) -> AppSetting | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    return result.scalar_one_or_none()


async def _locked_throttle_row(db: AsyncSession) -> AppSetting:
    """Ensure and row-lock the one global throttle before any read-modify-write."""
    await db.execute(
        insert(AppSetting)
        .values(
            key=THROTTLE_SETTING_KEY,
            value={"fail_count": 0, "locked_until": None},
        )
        .on_conflict_do_nothing(index_elements=[AppSetting.key])
    )
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == THROTTLE_SETTING_KEY).with_for_update()
    )
    return result.scalar_one()


async def _load_or_seed_pin(db: AsyncSession) -> AppSetting | None:
    """Load the PIN row, lazily seeding the immutable bootstrap value once."""
    row = await _setting(db, PIN_SETTING_KEY)
    if row is not None:
        return row

    bootstrap = get_settings().private_pin_bootstrap
    if not bootstrap:
        return None
    if not is_valid_pin(bootstrap):
        logger.warning("PRIVATE_PIN_BOOTSTRAP is invalid; expected exactly six ASCII digits")
        return None

    await db.execute(
        insert(AppSetting)
        .values(
            key=PIN_SETTING_KEY,
            value={"hash": hash_pin(bootstrap), "bootstrap": True},
        )
        .on_conflict_do_nothing(index_elements=[AppSetting.key])
    )
    return await _setting(db, PIN_SETTING_KEY)


def _next_remaining(fail_count: int) -> int:
    for threshold, _minutes in LOCK_LADDER:
        if threshold > fail_count:
            return threshold - fail_count
    return LOCK_LADDER[0][0] - fail_count


async def _verify_under_throttle(
    db: AsyncSession,
    pin: str,
    *,
    throttle_row: AppSetting | None = None,
) -> VerifyOutcome:
    """The only PIN-verification path, including both unlock and PIN rotation."""
    throttle = throttle_row or await _locked_throttle_row(db)
    now = _utc_now()
    locked_until = _parse_utc(throttle.value.get("locked_until"))
    if locked_until is not None and locked_until > now:
        return ("LOCKED", _retry_after(locked_until, now))

    pin_row = await _load_or_seed_pin(db)
    if pin_row is None:
        return "NO_PIN"

    stored_hash = pin_row.value.get("hash")
    if not isinstance(stored_hash, str):
        raise ValueError("private PIN setting has no hash")

    if verify_pin(stored_hash, pin):
        throttle.value = {**throttle.value, "fail_count": 0, "locked_until": None}
        await db.flush()
        return "OK"

    fail_count = int(throttle.value.get("fail_count", 0)) + 1
    lock_minutes = next(
        (minutes for threshold, minutes in LOCK_LADDER if threshold == fail_count),
        None,
    )
    if lock_minutes is not None:
        locked_until = now + timedelta(minutes=lock_minutes)
        stored_count = 0 if fail_count == LOCK_LADDER[-1][0] else fail_count
        throttle.value = {
            **throttle.value,
            "fail_count": stored_count,
            "locked_until": _utc_iso(locked_until),
        }
        await db.flush()
        return ("LOCKED", _retry_after(locked_until, now))

    throttle.value = {**throttle.value, "fail_count": fail_count, "locked_until": None}
    await db.flush()
    return ("WRONG", _next_remaining(fail_count))


async def _locked_session(db: AsyncSession, session_id) -> AuthSession:
    result = await db.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise RuntimeError("authenticated session row no longer exists")
    return row


async def _ttl_minutes(db: AsyncSession) -> int:
    row = await _setting(db, TTL_SETTING_KEY)
    if row is None:
        return DEFAULT_TTL_MINUTES
    value = row.value.get("value")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("private unlock TTL setting must be a positive integer")
    return value


async def unlock(db: AsyncSession, session: AuthSession, pin: str) -> UnlockOutcome:
    """Verify the PIN and set the hard per-session display deadline once."""
    outcome = await _verify_under_throttle(db, pin)
    if outcome != "OK":
        return outcome

    row = await _locked_session(db, session.id)
    private_until = _utc_now() + timedelta(minutes=await _ttl_minutes(db))
    # This and lock_now are the only writes to private_until in the application.
    row.private_until = private_until
    await db.flush()
    return ("OK", private_until)


async def lock_now(db: AsyncSession, session: AuthSession) -> None:
    """Close the display gate immediately on the persisted session row."""
    row = await _locked_session(db, session.id)
    row.private_until = None
    await db.flush()


async def set_pin(
    db: AsyncSession,
    session: AuthSession,
    current_pin: str | None,
    new_pin: str,
) -> None:
    """Rotate or establish the PIN without opening or extending the display gate."""
    del session  # Authentication is required by the router; PIN state is global.
    if not is_valid_pin(new_pin):
        raise ValueError("PIN phải đúng 6 chữ số")

    # Lock before even deciding whether a PIN exists. This serializes lazy bootstrap
    # seeding and simultaneous first-time PIN changes under one global order.
    throttle = await _locked_throttle_row(db)
    pin_row = await _load_or_seed_pin(db)
    if pin_row is not None:
        outcome = await _verify_under_throttle(
            db,
            current_pin or "",
            throttle_row=throttle,
        )
        if isinstance(outcome, tuple) and outcome[0] == "LOCKED":
            raise ThrottleLockedError(outcome[1])
        if isinstance(outcome, tuple) and outcome[0] == "WRONG":
            raise WrongPinError(outcome[1])
        if outcome == "NO_PIN":
            raise RuntimeError("private PIN disappeared while its throttle row was locked")

    new_hash = hash_pin(new_pin)
    new_value = {"hash": new_hash, "bootstrap": False}
    await db.execute(
        insert(AppSetting)
        .values(
            key=PIN_SETTING_KEY,
            value=new_value,
        )
        .on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": new_value},
        )
    )
    throttle.value = {**throttle.value, "fail_count": 0, "locked_until": None}
    await db.flush()


async def gate_status(db: AsyncSession, session: AuthSession) -> GateStatus:
    """Read display metadata; data filtering remains reading.py's responsibility."""
    pin_row = await _setting(db, PIN_SETTING_KEY)
    throttle_row = await _setting(db, THROTTLE_SETTING_KEY)
    locked_until = None
    if throttle_row is not None:
        candidate = _parse_utc(throttle_row.value.get("locked_until"))
        if candidate is not None and candidate > _utc_now():
            locked_until = candidate
    return GateStatus(
        private_until=session.private_until,
        locked_until=locked_until,
        pin_is_set=pin_row is not None,
        pin_is_bootstrap=bool(pin_row and pin_row.value.get("bootstrap") is True),
    )
