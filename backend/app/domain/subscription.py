"""Subscription DTOs, pure date/money rules, and the request-scoped store (011c).

The subscription slice mirrors the structure of ``app/domain/tracker.py``
(DTO → exception → stateless store). Three rules from the 011c spec are hard
contracts of this module:

* ``subscription`` is read through its PARENT ``Tracker`` — the privacy and
  soft-delete gates apply to the joined ``Tracker``, never to ``Subscription``
  directly (``models.py`` declares ``__privacy_gate__ = VIA_PARENT``).
* Money is ciphertext at rest, so every sum and every month conversion runs in
  Python on the decrypted ``Decimal`` — never ``func.sum`` / ``ORDER BY`` on
  ``amount``/``list_amount``.
* Renewal reuses the 011a ``TrackerStore.create_entry`` (which owns encryption,
  UUIDv7 checks, timezone rules and the K8 input_mode contract) and only pushes
  ``expires_on`` when the entry was actually created — idempotent retries must
  not move the expiry date twice (§2.4).
"""

import calendar
import logging
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession, Subscription, Tracker
from app.domain.reading import not_deleted, readable, with_privacy_gate
from app.domain.tracker import (
    EntryCreate,
    TrackerStore,
    _amount_in,
    _amount_out,
    _clear,
    _sealed,
)
from app.web.deps import CRON_TIMER_RELOAD_INFO_KEY

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))

# 30.4375 = 365.25 / 12. Must stay a Decimal: ``Decimal / float`` raises
# ``TypeError`` in Python, and a single week/day subscription would 500 the
# whole dashboard (§4.3).
MONTH_DAYS: Final = Decimal("30.4375")

PeriodUnit = Literal["day", "week", "month", "year"]
SubscriptionStatus = Literal["active", "canceled", "expired"]

# List order: active first (soonest expiry on top), then canceled, then expired.
_STATUS_RANK: Final[dict[str, int]] = {"active": 0, "canceled": 1, "expired": 2}

TRACKER_TYPE_MESSAGE = (
    "Đăng ký phải gắn vào một tracker tài chính nhập số tiền — "
    "chọn tracker khác hoặc đổi kiểu nhập của tracker này"
)


def _today_vn() -> date:
    return datetime.now(VN_TZ).date()


def _uuid7() -> UUID:
    """A monotonic-ish UUIDv7 generated server-side when the client omits entry_id."""
    import os
    import time

    timestamp = int(time.time() * 1000)
    random_bits = int.from_bytes(os.urandom(10), "big") & ((1 << 74) - 1)
    value = (timestamp << 80) | (0x7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_period(d: date, count: int, unit: str, anchor_day: int) -> date:
    """Add ``count`` whole periods to ``d``; month/year clamp to the anchor day.

    ``day``/``week`` are plain ``timedelta`` arithmetic. ``month``/``year`` are
    calendar-month arithmetic with end-of-month clamping anchored to
    ``anchor_day`` (the subscription's ``started_on.day``, §4.2): 31/01 + 1
    month → 28/02 (29/02 in leap years), and the NEXT step returns to 31/03 —
    chaining from a truncated ``expires_on`` would otherwise drift the payment
    day one direction forever (31/01 → 28/02 → 28/03 → …).
    """
    if unit == "day":
        return d + timedelta(days=count)
    if unit == "week":
        return d + timedelta(days=count * 7)
    months = count * (12 if unit == "year" else 1)
    total = d.year * 12 + (d.month - 1) + months
    year, zero_based_month = divmod(total, 12)
    month = zero_based_month + 1
    return date(year, month, min(anchor_day, _days_in_month(year, month)))


def derive_status(
    expires_on: date, canceled_at: datetime | None, today: date
) -> SubscriptionStatus:
    """Derive the status from stored columns only — never store it (§2.7).

    ``expired`` wins over ``canceled``: a canceled subscription that has run
    out of time is expired, and a canceled one still in its window stays
    "canceled" so the UI can offer "Ghi gia hạn" for the changed-mind path.
    """
    if expires_on < today:
        return "expired"
    if canceled_at is not None:
        return "canceled"
    return "active"


def monthly_amount(amount: Decimal, period_count: int, period_unit: str) -> Decimal:
    """Convert one period's amount to a monthly figure, UNROUNDED.

    ``month = period_count``; ``year = period_count * 12``;
    ``week = period_count * 7 / 30.4375``; ``day = period_count / 30.4375``.
    Callers round once (ROUND_HALF_UP) at the API boundary; the F6 burn sum
    must add the unrounded values and round only the total (§4.3).
    """
    if period_unit == "month":
        months = Decimal(period_count)
    elif period_unit == "year":
        months = Decimal(period_count) * Decimal(12)
    elif period_unit == "week":
        months = Decimal(period_count) * Decimal(7) / MONTH_DAYS
    else:
        months = Decimal(period_count) / MONTH_DAYS
    return amount / months


def round_vnd(value: Decimal) -> Decimal:
    """Round a VND figure to whole dong with ROUND_HALF_UP."""
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def renew_base(expires_on: date, today: date) -> date:
    """Anchor the next period: a lapsed subscription resumes from TODAY.

    Spec §4.2 veto #8: renewing a subscription that expired months ago from the
    stale milestone would land the new expiry in the past — the owner just paid
    and the app still reports ``expired``. ``max()`` leaves a live subscription
    untouched (the veto only fires when the old milestone is already past).
    """
    return max(expires_on, today)


class SubscriptionCreate(BaseModel):
    """Fields accepted when creating a subscription."""

    id: UUID | None = None
    name: str
    tracker_id: UUID
    amount: Decimal
    list_amount: Decimal | None = None
    period_count: int = Field(default=1, gt=0)
    period_unit: PeriodUnit = "month"
    started_on: date
    expires_on: date
    auto_renew: bool = False
    note_md: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "SubscriptionCreate":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Không được để trống tên.")
        if self.expires_on < self.started_on:
            raise ValueError("Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.")
        if self.id is not None and self.id.version != 7:
            raise ValueError("id must be a UUIDv7")
        if self.note_md is not None:
            self.note_md = self.note_md.strip() or None
        return self


class SubscriptionUpdate(BaseModel):
    """Patch semantics for a subscription; ``tracker_id`` is intentionally absent.

    Reparenting is forbidden (011c §4.1): the subscription may already have
    entries charged to the original tracker, and moving it would skew F3/F6
    history. Change it by soft-deleting and creating a new one.
    """

    name: str | None = None
    amount: Decimal | None = None
    list_amount: Decimal | None = None
    period_count: int | None = Field(default=None, gt=0)
    period_unit: PeriodUnit | None = None
    started_on: date | None = None
    expires_on: date | None = None
    auto_renew: bool | None = None
    note_md: str | None = None
    canceled_at: datetime | None = None

    @model_validator(mode="after")
    def normalize(self) -> "SubscriptionUpdate":
        if "name" in self.model_fields_set and self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("Không được để trống tên.")
        if "note_md" in self.model_fields_set and self.note_md is not None:
            self.note_md = self.note_md.strip() or None
        if (
            "canceled_at" in self.model_fields_set
            and self.canceled_at is not None
            and (self.canceled_at.tzinfo is None or self.canceled_at.utcoffset() is None)
        ):
            raise ValueError("canceled_at must include a timezone offset")
        return self


class SubscriptionRead(BaseModel):
    """Decrypted subscription at the API boundary; ``status`` is derived (§2.7)."""

    id: UUID
    tracker_id: UUID
    name: str
    amount: Decimal | None
    list_amount: Decimal | None
    period_count: int
    period_unit: PeriodUnit
    started_on: date
    expires_on: date
    auto_renew: bool
    canceled_at: datetime | None
    note_md: str | None
    deleted_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    status: SubscriptionStatus
    days_left: int
    monthly_amount: Decimal | None
    corrupted: bool = False
    created: bool | None = Field(default=None, exclude=True)

    @field_serializer("amount", "list_amount", "monthly_amount")
    def _money_as_number(self, value: Decimal | None) -> int | None:
        if value is None:
            return None
        return int(value)


class RenewRequest(BaseModel):
    """Renewal payload; every field absent falls back to the subscription's own values."""

    entry_id: UUID | None = None
    amount: Decimal | None = None
    occurred_at: datetime | None = None
    new_expires_on: date | None = None
    note_md: str | None = None
    clear_canceled: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "RenewRequest":
        if self.entry_id is not None and self.entry_id.version != 7:
            raise ValueError("entry_id must be a UUIDv7")
        if self.occurred_at is not None and (
            self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None
        ):
            raise ValueError("occurred_at must include a timezone offset")
        if self.note_md is not None:
            self.note_md = self.note_md.strip() or None
        return self


class RenewResult(BaseModel):
    """One renewal attempt; ``created=False`` means the request was a retry (§2.4)."""

    subscription: SubscriptionRead
    entry_id: UUID
    created: bool


class SubscriptionNameTaken(Exception):
    """A visible subscription with the same decrypted name already exists."""


class SubscriptionIdConflict(Exception):
    """A client-selected ID belongs to a subscription row hidden by a reading gate."""


class SubscriptionInvalid(Exception):
    """A write violates a subscription invariant (→ 422)."""


class SubscriptionParentMissing(Exception):
    """The parent tracker is not readable through the gate (→ 404, no leak)."""


RENEW_AMOUNT_UNREADABLE_MESSAGE = (
    "Không đọc được số tiền của đăng ký — sửa số tiền trước khi gia hạn."
)


def renew_amount_or_raise(raw_amount: str) -> Decimal:
    """Decrypt/parse the stored amount for a renewal, failing LOUDLY as 422.

    The physical column is NOT NULL, but a corrupt row still happens (bad
    base64 → ``ValueError``; tampered tag → ``InvalidTag``). Renewal cannot
    record a money entry without a real amount, so both forms must surface as
    the guided 422 below — never a 500. The list/F6 paths stay tolerant (§4.3);
    this is the one place where a corrupt amount BLOCKS the write.
    """
    try:
        amount = _amount_in(raw_amount)
    except Exception:
        logger.error("Renew blocked: subscription amount unreadable")
        raise SubscriptionInvalid(RENEW_AMOUNT_UNREADABLE_MESSAGE) from None
    if amount is None:
        raise SubscriptionInvalid(RENEW_AMOUNT_UNREADABLE_MESSAGE)
    return amount


class SubscriptionStore:
    """Stateless subscription persistence; joins the request transaction."""

    def __init__(self) -> None:
        self.tracker_store = TrackerStore()

    # --------------------------------------------------------------- helpers

    async def _subscription(
        self,
        db: AsyncSession,
        auth: AuthSession,
        subscription_id: UUID,
        *,
        for_update: bool = False,
    ) -> Subscription | None:
        """Read one subscription through its visible parent tracker (§2.2)."""
        stmt = (
            select(Subscription)
            .join(Tracker, Subscription.tracker_id == Tracker.id)
            .where(Subscription.id == subscription_id)
        )
        stmt = readable(stmt, Tracker, auth)  # privacy + soft-delete of the PARENT
        stmt = not_deleted(stmt, Subscription)  # soft-delete of the subscription itself
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _parent_tracker(
        self, db: AsyncSession, auth: AuthSession, tracker_id: UUID
    ) -> Tracker | None:
        stmt = readable(select(Tracker).where(Tracker.id == tracker_id), Tracker, auth)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _assert_tracker_kind(self, tracker: Tracker) -> None:
        """Block the late-renewal 422: a subscription must live on a money tracker (§2.5)."""
        if tracker.kind != "finance" or tracker.input_mode != "money":
            raise SubscriptionInvalid(TRACKER_TYPE_MESSAGE)

    async def _subscription_name_taken(
        self,
        db: AsyncSession,
        auth: AuthSession,
        name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Duplicate-name scan INSIDE the privacy gate (K19, §2.6)."""
        stmt = select(Subscription).join(Tracker, Subscription.tracker_id == Tracker.id)
        stmt = readable(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Subscription)
        result = await db.execute(stmt)
        wanted = name.casefold()
        for subscription in result.scalars():
            if exclude_id is not None and subscription.id == exclude_id:
                continue
            try:
                stored_name = _clear(subscription.name)
            except Exception:
                logger.warning(
                    "Skipped an unreadable subscription name in duplicate scan (id=%s)",
                    subscription.id,
                )
                continue
            if stored_name is not None and stored_name.casefold() == wanted:
                return True
        return False

    def _subscription_read(
        self,
        subscription: Subscription,
        today: date,
        *,
        tolerant: bool = False,
    ) -> SubscriptionRead | None:
        """Build a SubscriptionRead; ``tolerant`` keeps corrupt-amount rows visible.

        The single-row read path stays loud (a corrupt row is a wrong key or a
        foreign writer — both must fail visibly), while the list path keeps a
        subscription with an unreadable AMOUNT (name still readable) with
        ``amount: null`` + ``corrupted: true`` so the owner can still see which
        charge is about to hit (§4.3). A corrupt NAME makes the row useless, so
        the list drops it and returns ``None``.
        """
        try:
            name = _clear(subscription.name)
        except Exception:
            if not tolerant:
                raise
            logger.error("Subscription list skipped an unreadable name (id=%s)", subscription.id)
            return None
        amount = None
        corrupted = False
        try:
            amount = _amount_in(subscription.amount)
        except Exception:
            if not tolerant:
                raise
            logger.error(
                "Subscription amount unreadable (id=%s); showing without an amount",
                subscription.id,
            )
            corrupted = True
        list_amount = None
        try:
            list_amount = _amount_in(subscription.list_amount)
        except Exception:
            if not tolerant:
                raise
            logger.error(
                "Subscription list_amount unreadable (id=%s); hiding the list price",
                subscription.id,
            )
        monthly = (
            monthly_amount(amount, subscription.period_count, subscription.period_unit)
            if amount is not None
            else None
        )
        return SubscriptionRead(
            id=subscription.id,
            tracker_id=subscription.tracker_id,
            name=name,
            amount=amount,
            list_amount=list_amount,
            period_count=subscription.period_count,
            period_unit=subscription.period_unit,
            started_on=subscription.started_on,
            expires_on=subscription.expires_on,
            auto_renew=subscription.auto_renew,
            canceled_at=subscription.canceled_at,
            note_md=_clear(subscription.note_md),
            deleted_at=subscription.deleted_at,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
            status=derive_status(subscription.expires_on, subscription.canceled_at, today),
            days_left=(subscription.expires_on - today).days,
            monthly_amount=round_vnd(monthly) if monthly is not None else None,
            corrupted=corrupted,
        )

    # ------------------------------------------------------------ read paths

    async def list_subscriptions(
        self,
        db: AsyncSession,
        auth: AuthSession,
        *,
        status: SubscriptionStatus | None = None,
        tracker_id: UUID | None = None,
    ) -> list[SubscriptionRead]:
        """List visible subscriptions (no pagination — a few dozen rows).

        ``expires_on`` is a plain DATE, so the SQL sort is safe and uses
        ``ix_subscription_expires_on``; the status grouping happens in Python
        with a stable sort so each status keeps expiry order.
        """
        today = _today_vn()
        stmt = select(Subscription).join(Tracker, Subscription.tracker_id == Tracker.id)
        stmt = readable(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Subscription)
        if tracker_id is not None:
            stmt = stmt.where(Subscription.tracker_id == tracker_id)
        stmt = stmt.order_by(Subscription.expires_on)
        result = await db.execute(stmt)
        rows: list[SubscriptionRead] = []
        for subscription in result.scalars():
            read = self._subscription_read(subscription, today, tolerant=True)
            if read is None:
                continue
            if status is not None and read.status != status:
                continue
            rows.append(read)
        rows.sort(key=lambda read: _STATUS_RANK[read.status])
        return rows

    async def get_subscription(
        self, db: AsyncSession, auth: AuthSession, subscription_id: UUID
    ) -> SubscriptionRead | None:
        subscription = await self._subscription(db, auth, subscription_id)
        if subscription is None:
            return None
        try:
            return self._subscription_read(subscription, _today_vn())
        except Exception as error:
            logger.error("get_subscription unreadable row id=%s: %s", subscription_id, error)
            raise SubscriptionInvalid(
                "Dữ liệu đăng ký trong cơ sở dữ liệu không hợp lệ."
            ) from error

    # ----------------------------------------------------------- write paths

    async def create_subscription(
        self, db: AsyncSession, auth: AuthSession, payload: SubscriptionCreate
    ) -> SubscriptionRead:
        """Create a subscription, or idempotently return the explicit ID."""
        tracker = await self._parent_tracker(db, auth, payload.tracker_id)
        if tracker is None:
            raise SubscriptionParentMissing
        self._assert_tracker_kind(tracker)
        if payload.id is not None:
            existing = await self._subscription(db, auth, payload.id)
            if existing is not None:
                read = self._subscription_read(existing, _today_vn())
                read.created = False
                return read
        if await self._subscription_name_taken(db, auth, payload.name):
            raise SubscriptionNameTaken

        values = {
            "name": _sealed(payload.name),
            "tracker_id": payload.tracker_id,
            "amount": _amount_out(payload.amount),
            "list_amount": _amount_out(payload.list_amount),
            "period_count": payload.period_count,
            "period_unit": payload.period_unit,
            "started_on": payload.started_on,
            "expires_on": payload.expires_on,
            "auto_renew": payload.auto_renew,
            "note_md": _sealed(payload.note_md),
        }
        if payload.id is None:
            subscription = Subscription(**values)
            db.add(subscription)
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:create"
            await db.flush()
        else:
            inserted_id = (
                await db.execute(
                    insert(Subscription)
                    .values(id=payload.id, **values)
                    .on_conflict_do_nothing(index_elements=[Subscription.id])
                    .returning(Subscription.id)
                )
            ).scalar_one_or_none()
            if inserted_id is None:
                physical = await db.execute(
                    select(Subscription.id).where(Subscription.id == payload.id)
                )
                if physical.scalar_one_or_none() is not None:
                    raise SubscriptionIdConflict
                raise RuntimeError("conflicting subscription disappeared before it could be read")
            inserted = await db.execute(select(Subscription).where(Subscription.id == inserted_id))
            subscription = inserted.scalar_one()
            db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:create"
        read = self._subscription_read(subscription, _today_vn())
        read.created = True
        return read

    async def update_subscription(
        self,
        db: AsyncSession,
        auth: AuthSession,
        subscription_id: UUID,
        payload: SubscriptionUpdate,
    ) -> SubscriptionRead | None:
        """Patch a subscription; ``tracker_id`` cannot change (no reparent)."""
        subscription = await self._subscription(db, auth, subscription_id, for_update=True)
        if subscription is None:
            return None
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            if await self._subscription_name_taken(
                db, auth, changes["name"], exclude_id=subscription.id
            ):
                raise SubscriptionNameTaken
            changes["name"] = _sealed(changes["name"])
        if "amount" in changes:
            changes["amount"] = _amount_out(changes["amount"])
        if "list_amount" in changes:
            changes["list_amount"] = _amount_out(changes["list_amount"])
        if "note_md" in changes:
            changes["note_md"] = _sealed(changes["note_md"])

        effective_started = changes.get("started_on", subscription.started_on)
        effective_expires = changes.get("expires_on", subscription.expires_on)
        if effective_expires < effective_started:
            raise SubscriptionInvalid("Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.")

        for field in (
            "amount",
            "list_amount",
            "period_count",
            "period_unit",
            "started_on",
            "expires_on",
            "auto_renew",
            "canceled_at",
            "note_md",
        ):
            if field in changes:
                setattr(subscription, field, changes[field])
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:update"
        await db.flush()
        return self._subscription_read(subscription, _today_vn())

    async def cancel_subscription(
        self, db: AsyncSession, auth: AuthSession, subscription_id: UUID
    ) -> SubscriptionRead | None:
        """Mark canceled (``canceled_at``) — cancel is NOT soft-delete (§4.1 trap 3)."""
        subscription = await self._subscription(db, auth, subscription_id, for_update=True)
        if subscription is None:
            return None
        subscription.canceled_at = datetime.now(UTC)
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:cancel"
        await db.flush()
        return self._subscription_read(subscription, _today_vn())

    async def uncancel_subscription(
        self, db: AsyncSession, auth: AuthSession, subscription_id: UUID
    ) -> SubscriptionRead | None:
        subscription = await self._subscription(db, auth, subscription_id, for_update=True)
        if subscription is None:
            return None
        subscription.canceled_at = None
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:uncancel"
        await db.flush()
        return self._subscription_read(subscription, _today_vn())

    async def soft_delete_subscription(
        self, db: AsyncSession, auth: AuthSession, subscription_id: UUID
    ) -> bool:
        subscription = await self._subscription(db, auth, subscription_id)
        if subscription is None:
            return False
        subscription.deleted_at = datetime.now(UTC)
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:soft_delete"
        await db.flush()
        return True

    async def restore_subscription(
        self, db: AsyncSession, auth: AuthSession, subscription_id: UUID
    ) -> Subscription | None:
        """Restore a soft-deleted subscription, re-validating the parent tracker.

        The re-validation closes the back door around the §2.5 guard: someone
        could soft-delete every subscription, switch the tracker away from
        money, then restore — so restore re-checks finance + money.
        """
        stmt = (
            select(Subscription)
            .join(Tracker, Subscription.tracker_id == Tracker.id)
            .where(Subscription.id == subscription_id)
        )
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = stmt.where(Subscription.deleted_at.is_not(None))
        subscription = (await db.execute(stmt)).scalar_one_or_none()
        if subscription is None:
            return await self._subscription(db, auth, subscription_id)
        parent_stmt = with_privacy_gate(
            select(Tracker).where(Tracker.id == subscription.tracker_id), Tracker, auth
        )
        parent_tracker = (await db.execute(parent_stmt)).scalar_one_or_none()
        if parent_tracker is not None:
            self._assert_tracker_kind(parent_tracker)
        subscription.deleted_at = None
        db.info[CRON_TIMER_RELOAD_INFO_KEY] = "subscription:restore"
        await db.flush()
        return subscription

    # -------------------------------------------------------------- renewal

    async def renew(
        self,
        db: AsyncSession,
        auth: AuthSession,
        subscription_id: UUID,
        payload: RenewRequest,
    ) -> RenewResult | None:
        """Record one real renewal: one entry + one pushed expiry, atomically.

        Order (spec §4.2): lock the subscription row FOR UPDATE, verify the
        parent tracker is still finance+money, compute defaults, create the
        entry THROUGH the 011a store (never a second INSERT), and only when the
        entry was actually created push ``expires_on``. A duplicate request
        with the same ``entry_id`` gets ``created=False`` and leaves
        ``expires_on`` untouched.
        """
        subscription = await self._subscription(db, auth, subscription_id, for_update=True)
        if subscription is None:
            return None
        tracker = await self._parent_tracker(db, auth, subscription.tracker_id)
        if tracker is None:
            return None
        self._assert_tracker_kind(tracker)

        today = _today_vn()
        if payload.amount is not None:
            amount = payload.amount
        else:
            amount = renew_amount_or_raise(subscription.amount)
        occurred_at = payload.occurred_at or datetime.now(UTC)
        entry_id = payload.entry_id or _uuid7()

        if payload.new_expires_on is not None:
            if payload.new_expires_on <= subscription.expires_on:
                raise SubscriptionInvalid("Ngày hết hạn mới phải sau ngày hết hạn hiện tại.")
            if payload.new_expires_on < subscription.started_on:
                raise SubscriptionInvalid("Ngày hết hạn mới phải sau hoặc bằng ngày bắt đầu.")
            new_expires_on = payload.new_expires_on
        else:
            # A lapsed subscription resumes from TODAY, not from the stale past
            # milestone (§4.2); for a live one max() is the current expires_on.
            new_expires_on = add_period(
                renew_base(subscription.expires_on, today),
                subscription.period_count,
                subscription.period_unit,
                subscription.started_on.day,
            )

        entry_payload = EntryCreate(
            id=entry_id,
            tracker_id=subscription.tracker_id,
            occurred_at=occurred_at,
            amount=amount,
            note_md=payload.note_md,
        )
        entry_id, created = await self.tracker_store.create_entry(
            db, auth, entry_payload, subscription_id=subscription.id
        )
        if not created:
            # Retry of an already-recorded renewal: NEVER push expires_on twice.
            return RenewResult(
                subscription=self._subscription_read(subscription, today, tolerant=True),
                entry_id=entry_id,
                created=False,
            )
        subscription.expires_on = new_expires_on
        if payload.clear_canceled:
            # Only an explicit owner decision clears the canceled mark (§4.1).
            subscription.canceled_at = None
        await db.flush()
        return RenewResult(
            subscription=self._subscription_read(subscription, today, tolerant=True),
            entry_id=entry_id,
            created=True,
        )
