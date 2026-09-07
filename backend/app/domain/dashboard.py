"""Behavior (A1–A4) and finance (F1–F5) dashboard aggregation for the tracker slice.

A single endpoint computes every dashboard number server-side. Money only exists as a
number AFTER the server decrypts it (011a spec §2.3), so letting the client sum would
require shipping the whole month down just to add it back up — and would create a
second place that defines "when does the month start".

Every time boundary is computed in ``+07:00`` via a fixed ``timezone(timedelta(hours=7))``,
deliberately NOT ``zoneinfo``: the slim Python image on Fly does not guarantee tzdata,
and ``ZoneInfoNotFoundError`` would only fire in production. Weeks start on Monday.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain import money
from app.domain import settings as settings_store
from app.domain.models import AuthSession, Entry, Subscription, Tracker, TrackerGroup
from app.domain.reading import not_deleted, readable, with_privacy_gate
from app.domain.subscription import derive_status, monthly_amount

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))


class F3Group(BaseModel):
    """Finance breakdown by tracker group, drillable to trackers."""

    name: str
    total: Decimal
    trackers: list[dict] = Field(default_factory=list)

    @field_serializer("total")
    def _total_as_number(self, value: Decimal) -> int:
        return int(value)


class F4Top(BaseModel):
    """One of the top-5 largest finance entries in the month."""

    entry_id: UUID
    tracker_id: UUID
    tracker_name: str
    amount: Decimal

    @field_serializer("amount")
    def _amount_as_number(self, value: Decimal) -> int:
        return int(value)


class A3Counts(BaseModel):
    """Entry counts for this week / month / year (always relative to today)."""

    week: int
    month: int
    year: int


class A4Trend(BaseModel):
    """This month's entries vs the average of the previous three full months."""

    current_month: int
    prev_avg: Decimal
    trend: str

    @field_serializer("prev_avg")
    def _prev_avg_as_number(self, value: Decimal) -> float:
        """Serialize the count average as a number without truncating (C7)."""
        return float(value.quantize(Decimal("0.01")))


class F6Upcoming(BaseModel):
    """One subscription about to renew within the lead window (max 5, by expiry)."""

    subscription_id: UUID
    name: str
    amount: Decimal | None
    monthly_amount: Decimal | None
    expires_on: date
    days_left: int
    corrupted: bool

    @field_serializer("amount", "monthly_amount")
    def _money_as_number(self, value: Decimal | None) -> int | None:
        if value is None:
            return None
        return int(value)


class F6Summary(BaseModel):
    """Fixed monthly burn (auto-renew only) + the upcoming-renewal shortlist."""

    monthly_burn: Decimal
    subscription_count: int
    upcoming: list[F6Upcoming] = Field(default_factory=list)
    corrupted_subscription_count: int

    @field_serializer("monthly_burn")
    def _burn_as_number(self, value: Decimal) -> int:
        return int(value)


class FinanceMonth(BaseModel):
    """One chronological expense total in the requested report range."""

    month: str
    period_start: datetime
    period_end: datetime
    total: Decimal = Field(default_factory=Decimal)

    @field_serializer("total")
    def _total_as_number(self, value: Decimal) -> int:
        return int(value)


class ActivityDay(BaseModel):
    """A non-sensitive daily entry count for one visible active tracker."""

    tracker_id: UUID
    day: str
    count: int


class DashboardResponse(BaseModel):
    """Aggregated dashboard payload returned by ``GET /api/tracker/dashboard``."""

    period_start: datetime
    period_end: datetime
    report_months: int = 1
    previous_period_start: datetime | None = None
    previous_period_end: datetime | None = None
    current_period_days: int
    prev_period_days: int
    prev_period_truncated: bool
    corrupted_entry_count: int
    f1_total: Decimal = Field(default_factory=Decimal)
    f2_current: Decimal = Field(default_factory=Decimal)
    f2_previous: Decimal = Field(default_factory=Decimal)
    f3_groups: list[F3Group] = Field(default_factory=list)
    f4_top: list[F4Top] = Field(default_factory=list)
    f5_net: Decimal = Field(default_factory=Decimal)
    finance_months: list[FinanceMonth] = Field(default_factory=list)
    activity_month: str
    activity_days: list[ActivityDay] = Field(default_factory=list)
    a2_gap: list[dict] = Field(default_factory=list)
    a3_counts: A3Counts = Field(default_factory=lambda: A3Counts(week=0, month=0, year=0))
    a4_trend: A4Trend = Field(
        default_factory=lambda: A4Trend(current_month=0, prev_avg=Decimal(0), trend="flat")
    )
    f6: F6Summary = Field(
        default_factory=lambda: F6Summary(
            monthly_burn=Decimal(0), subscription_count=0, corrupted_subscription_count=0
        )
    )

    @field_serializer("f1_total", "f2_current", "f2_previous", "f5_net")
    def _money_as_number(self, value: Decimal) -> int:
        return int(value)


_MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")
REPORT_MONTHS = frozenset({1, 3, 6, 12})


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """Return ``(month_start, next_month_start)`` in ``+07:00``."""
    match = _MONTH_RE.fullmatch(month)
    if match is None:
        raise ValueError("month must look like YYYY-MM")
    year = int(match["year"])
    month_num = int(match["month"])
    if year < 1 or (year == 9999 and month_num == 12):
        raise ValueError("month is outside the supported calendar range")
    start = datetime(year, month_num, 1, tzinfo=VN_TZ)
    if month_num == 12:
        next_start = datetime(year + 1, 1, 1, tzinfo=VN_TZ)
    else:
        next_start = datetime(year, month_num + 1, 1, tzinfo=VN_TZ)
    return start, next_start


def _relative_now() -> datetime:
    """Return current time normalized to ``+07:00``."""
    return datetime.now(timezone.utc).astimezone(VN_TZ)


def _as_vn(value: datetime) -> datetime:
    """Normalize PostgreSQL-aware and SQLite-synthetic timestamps to the report zone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=VN_TZ)
    return value.astimezone(VN_TZ)


def _monday_of(day: datetime) -> datetime:
    """Return 00:00 (+07) of the Monday starting the week containing ``day``."""
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.weekday())


def _shift_months(start: datetime, count: int) -> datetime:
    """Return the first day ``count`` calendar months before ``start``."""
    target = start.year * 12 + (start.month - 1) - count
    year, month_index = divmod(target, 12)
    if year < 1:
        raise ValueError("month range predates year 0001")
    return datetime(year, month_index + 1, 1, tzinfo=VN_TZ)


@dataclass
class PeriodBounds:
    """Pure boundary math for one dashboard month (unit-testable, no DB)."""

    period_start: datetime
    period_end: datetime
    current_period_days: int
    prev_start: datetime | None
    prev_end: datetime | None
    prev_period_days: int
    prev_period_truncated: bool
    is_future: bool


def _periods(month: str, now: datetime, months: int = 1) -> PeriodBounds:
    """Compute every dashboard time boundary for ``month`` relative to ``now``.

    The selected range covers an absolute count of calendar months ending in
    ``month``. The selected current month ends at ``now``; every earlier selected
    month is complete. F2's comparison is the whole preceding count of calendar
    months, never a same-elapsed-days window.
    """
    if months not in REPORT_MONTHS:
        raise ValueError("months must be one of 1, 3, 6, 12")
    month_start, month_end = _month_bounds(month)
    period_start = _shift_months(month_start, months - 1)
    if month_start > now:
        return PeriodBounds(
            period_start=period_start,
            period_end=period_start,
            current_period_days=0,
            prev_start=None,
            prev_end=None,
            prev_period_days=0,
            prev_period_truncated=False,
            is_future=True,
        )
    period_end = min(now, month_end)
    if period_end < period_start:
        return PeriodBounds(
            period_start=period_start,
            period_end=month_start,
            current_period_days=0,
            prev_start=None,
            prev_end=None,
            prev_period_days=0,
            prev_period_truncated=False,
            is_future=True,
        )
    current_days = (period_end - period_start).days
    prev_start = _shift_months(period_start, months)
    prev_end = period_start
    return PeriodBounds(
        period_start=period_start,
        period_end=period_end,
        current_period_days=current_days,
        prev_start=prev_start,
        prev_end=prev_end,
        prev_period_days=(prev_end - prev_start).days,
        prev_period_truncated=False,
        is_future=False,
    )


def _finance_month_bounds(month: str, months: int, now: datetime) -> list[FinanceMonth]:
    """Build chronological selected-month labels and their bounded half-open periods."""
    selected_start, _ = _month_bounds(month)
    result: list[FinanceMonth] = []
    for offset in range(months - 1, -1, -1):
        start = _shift_months(selected_start, offset)
        _, end = _month_bounds(f"{start.year:04d}-{start.month:02d}")
        bounded_end = min(now, end)
        if bounded_end < start:
            bounded_end = start
        result.append(
            FinanceMonth(
                month=f"{start.year:04d}-{start.month:02d}",
                period_start=start,
                period_end=bounded_end,
            )
        )
    return result


class DashboardService:
    """Stateless dashboard aggregation; joins the request transaction."""

    @staticmethod
    def _safe_amount(entry: Entry) -> tuple[Decimal | None, bool]:
        """Decrypt one entry amount; return ``(value, corrupted)``.

        On the aggregation path a single corrupt row must not take down the whole
        dashboard (hundreds of rows per request). We log only the entry id (never the
        ciphertext or any fragment) and count it into ``corrupted_entry_count``. The
        single-entry read path keeps raising loudly instead.
        """
        if entry.amount is None:
            return None, False
        try:
            return money.from_storage(crypto.decrypt(entry.amount)), False
        except Exception:
            logger.error(
                "Dashboard skipped an unreadable entry.amount (id=%s); results may be incomplete",
                entry.id,
            )
            return None, True

    async def _fetch_month(
        self,
        db: AsyncSession,
        auth: AuthSession,
        month_start: datetime,
        month_end: datetime,
        *,
        include_archived: bool = True,
    ) -> list[tuple[Entry, Tracker]]:
        """Fetch entries of the requested month through their parent trackers.

        Applies the parent's privacy gate but NOT the parent's soft-delete gate: an
        archived tracker's money history must still count (F1–F5). A4's previous-
        three-months count is behavior, so it passes ``include_archived=False``
        (spec §4.3: archives disappear from A1–A4). Privacy is never exempted.
        Only the entry's own soft-delete is filtered.
        """
        stmt = select(Entry, Tracker).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = with_privacy_gate(stmt, Tracker, auth)
        if not include_archived:
            stmt = not_deleted(stmt, Tracker)
        stmt = not_deleted(stmt, Entry)
        stmt = stmt.where(Entry.occurred_at >= month_start, Entry.occurred_at < month_end)
        result = await db.execute(stmt)
        return [(entry, tracker) for entry, tracker in result]

    async def _fetch_all(self, db: AsyncSession, auth: AuthSession) -> list[tuple[Entry, Tracker]]:
        """Fetch every visible entry for the behavior counts (A3/A4 only).

        Unlike the F1–F5 aggregation path, behavior metrics DO apply the parent's
        soft-delete gate: an archived tracker disappears from "tuần/tháng/năm này"
        (spec §4.3), while its money history stays in F1–F5.
        """
        stmt = select(Entry, Tracker).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Tracker)
        stmt = not_deleted(stmt, Entry)
        result = await db.execute(stmt)
        return [(entry, tracker) for entry, tracker in result]

    @staticmethod
    def _activity_days(
        rows: list[tuple[Entry, Tracker, Decimal | None, bool]],
        selected_month_start: datetime,
        period_end: datetime,
    ) -> list[ActivityDay]:
        """Return sparse selected-month counts from already parent-gated rows."""
        activity_counts: dict[tuple[UUID, str], int] = {}
        for entry, tracker, _amount, _bad in rows:
            if tracker.deleted_at is not None or entry.occurred_at is None:
                continue
            occurred_at = _as_vn(entry.occurred_at)
            if not (selected_month_start <= occurred_at < period_end):
                continue
            local_day = occurred_at.date().isoformat()
            key = (tracker.id, local_day)
            activity_counts[key] = activity_counts.get(key, 0) + 1
        return [
            ActivityDay(tracker_id=tracker_id, day=day, count=count)
            for (tracker_id, day), count in sorted(
                activity_counts.items(), key=lambda item: item[0]
            )
        ]

    async def _visible_trackers(self, db: AsyncSession, auth: AuthSession) -> list[Tracker]:
        from app.domain.reading import readable

        stmt = readable(select(Tracker), Tracker, auth)
        result = await db.execute(stmt)
        return list(result.scalars())

    async def _a2_gap(
        self,
        db: AsyncSession,
        auth: AuthSession,
        now: datetime,
        window_days: int = 90,
        min_entries: int = 3,
    ) -> list[dict]:
        """Gap (current vs average) for every visible tracker with enough data.

        One batched query fetches every visible tracker's entries in the
        ``window_days`` window (no N+1 — M1); gaps between consecutive
        ``occurred_at`` values are averaged in Python. Fewer than ``min_entries``
        ⇒ the tracker is reported with ``enough=False`` so the UI writes
        "chưa đủ dữ liệu" instead of drawing "0 ngày".
        """
        since = now - timedelta(days=window_days)
        trackers = await self._visible_trackers(db, auth)
        if not trackers:
            return []
        tracker_ids = [tracker.id for tracker in trackers]
        stmt = select(Entry, Tracker).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Entry)
        stmt = stmt.where(Entry.tracker_id.in_(tracker_ids), Entry.occurred_at >= since)
        stmt = stmt.order_by(Entry.tracker_id, Entry.occurred_at)
        rows = await db.execute(stmt)

        by_tracker: dict[UUID, list[datetime]] = {}
        for entry, _tracker in rows:
            if entry.occurred_at is not None:
                by_tracker.setdefault(entry.tracker_id, []).append(entry.occurred_at)

        result: list[dict] = []
        for tracker in trackers:
            timestamps = sorted(by_tracker.get(tracker.id, []))
            if len(timestamps) < min_entries:
                result.append(
                    {
                        "tracker_id": str(tracker.id),
                        "current_days": None,
                        "avg_days": None,
                        "enough": False,
                    }
                )
                continue
            gaps = [
                (timestamps[i + 1] - timestamps[i]).total_seconds() / 86400
                for i in range(len(timestamps) - 1)
            ]
            avg_days = sum(gaps) / len(gaps) if gaps else 0.0
            current_days = (now - timestamps[-1]).total_seconds() / 86400
            result.append(
                {
                    "tracker_id": str(tracker.id),
                    "current_days": round(current_days, 1),
                    "avg_days": round(avg_days, 1),
                    "enough": True,
                }
            )
        return result

    @staticmethod
    def _decrypt_name(tracker: Tracker) -> str:
        if tracker.name is None:
            return ""
        return crypto.decrypt(tracker.name)

    async def _f6(self, db: AsyncSession, auth: AuthSession) -> F6Summary:
        """Monthly fixed burn + upcoming renewals — a snapshot of TODAY (§4.3).

        F6 deliberately ignores ``?month=``: F1–F5 look backward at a chosen
        month, while F6 answers "how much am I committed to every month from
        now on". A subscription counts when ALL hold: ``auto_renew``, not
        canceled, ``expires_on >= today_vn``, and readable through the
        parent-tracker gate (§2.2 — archived or locked-private parents hide
        their subscriptions with no "some items hidden" note).

        Amounts are summed as unrounded Decimals; the total is rounded once
        with ROUND_HALF_UP. A corrupted AMOUNT keeps the row in ``upcoming``
        (``amount: null`` + ``corrupted: true``) when the NAME is still
        readable — hiding a charge that is about to hit is worse than showing
        a hole in the number. A corrupted name drops the row entirely.
        """
        today = _relative_now().date()
        stmt = select(Subscription, Tracker).join(Tracker, Subscription.tracker_id == Tracker.id)
        stmt = readable(stmt, Tracker, auth)  # privacy + soft-delete of the PARENT
        stmt = not_deleted(stmt, Subscription)  # soft-delete of the subscription itself
        rows = await db.execute(stmt)

        lead_days = await settings_store.expiry_lead_days(db)
        burn = Decimal(0)
        count = 0
        corrupted = 0
        upcoming: list[F6Upcoming] = []
        for subscription, _tracker in rows:
            if derive_status(subscription.expires_on, subscription.canceled_at, today) != "active":
                continue
            try:
                name = crypto.decrypt(subscription.name)
            except Exception:
                logger.error(
                    "F6 skipped a subscription with an unreadable name (id=%s); "
                    "results may be incomplete",
                    subscription.id,
                )
                corrupted += 1
                continue
            amount: Decimal | None = None
            bad = False
            try:
                amount = money.from_storage(crypto.decrypt(subscription.amount))
            except Exception:
                logger.error(
                    "F6 skipped an unreadable subscription.amount (id=%s); "
                    "results may be incomplete",
                    subscription.id,
                )
                bad = True
                corrupted += 1
            monthly: Decimal | None = None
            if not bad:
                monthly = monthly_amount(
                    amount, subscription.period_count, subscription.period_unit
                )
                if subscription.auto_renew:
                    burn += monthly
                    count += 1
            days_left = (subscription.expires_on - today).days
            if days_left <= lead_days:
                upcoming.append(
                    F6Upcoming(
                        subscription_id=subscription.id,
                        name=name,
                        amount=amount,
                        monthly_amount=(
                            monthly.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                            if monthly is not None
                            else None
                        ),
                        expires_on=subscription.expires_on,
                        days_left=days_left,
                        corrupted=bad,
                    )
                )
        upcoming.sort(key=lambda item: item.expires_on)
        return F6Summary(
            monthly_burn=burn.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
            subscription_count=count,
            upcoming=upcoming[:5],
            corrupted_subscription_count=corrupted,
        )

    async def compute(
        self, db: AsyncSession, auth: AuthSession, *, month: str, months: int = 1
    ) -> DashboardResponse:
        """Compute the dashboard for an absolute selected calendar-month range."""
        now = _relative_now()
        period = _periods(month, now, months)
        period_start = period.period_start
        period_end = period.period_end
        finance_months = _finance_month_bounds(month, months, now)
        f6 = await self._f6(db, auth)

        # ---------------- A3 / A4 (relative to today) ---------------------
        a2_gap = await self._a2_gap(db, auth, now)
        all_rows = await self._fetch_all(db, auth)
        week_start = _monday_of(now).replace(tzinfo=VN_TZ)
        month_start_now = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        a3_week = a3_month = a3_year = 0
        for entry, _tracker in all_rows:
            if entry.occurred_at is None:
                continue
            if entry.occurred_at >= week_start:
                a3_week += 1
            if entry.occurred_at >= month_start_now:
                a3_month += 1
            if entry.occurred_at >= year_start:
                a3_year += 1

        # A4: current month entries vs avg of previous three full months.
        prev3_start = _shift_months(month_start_now, 3)
        prev3_end = month_start_now
        prev3_rows = await self._fetch_month(
            db, auth, prev3_start, prev3_end, include_archived=False
        )
        prev3_count = sum(1 for entry, _ in prev3_rows if entry.occurred_at is not None)
        prev_avg = Decimal(prev3_count) / Decimal(3) if prev3_count else Decimal(0)
        if a3_month > prev_avg:
            trend = "up"
        elif a3_month < prev_avg:
            trend = "down"
        else:
            trend = "flat"
        a4_trend = A4Trend(current_month=a3_month, prev_avg=prev_avg, trend=trend)
        a3_counts = A3Counts(week=a3_week, month=a3_month, year=a3_year)

        # A future month has no finance data yet: every F metric is zero and no
        # month/previous-period query runs (spec §4.3 — no fake 1-day period).
        if period.is_future:
            return DashboardResponse(
                period_start=period_start,
                period_end=period_end,
                report_months=months,
                previous_period_start=None,
                previous_period_end=None,
                current_period_days=0,
                prev_period_days=0,
                prev_period_truncated=False,
                corrupted_entry_count=0,
                f1_total=Decimal(0),
                f2_current=Decimal(0),
                f2_previous=Decimal(0),
                f3_groups=[],
                f4_top=[],
                f5_net=Decimal(0),
                finance_months=finance_months,
                activity_month=month,
                activity_days=[],
                a2_gap=a2_gap,
                a3_counts=a3_counts,
                a4_trend=a4_trend,
                f6=f6,
            )

        month_start = period_start
        prev_start = period.prev_start
        prev_end = period.prev_end
        month_rows = await self._fetch_month(db, auth, month_start, period_end)
        prev_rows = await self._fetch_month(db, auth, prev_start, prev_end)
        fetch_rows = month_rows + prev_rows

        corrupted = 0
        decoded: list[tuple[Entry, Tracker, Decimal | None, bool]] = []
        for entry, tracker in fetch_rows:
            amount, bad = self._safe_amount(entry)
            if bad:
                corrupted += 1
            decoded.append((entry, tracker, amount, bad))

        # ---------------- F1 / F5 (within the selected range) -------------
        f1_total = Decimal(0)
        in_total = Decimal(0)
        for entry, tracker, amount, bad in decoded:
            if bad or amount is None or entry.occurred_at is None:
                continue
            if month_start <= entry.occurred_at < period_end:
                if tracker.direction == "out":
                    f1_total += amount
                else:
                    in_total += amount
        f5_net = in_total - f1_total

        # ---------------- F2 (whole preceding calendar-month range) --------
        f2_previous = Decimal(0)
        f2_current = Decimal(0)
        for entry, tracker, amount, bad in decoded:
            if bad or amount is None or tracker.direction != "out" or entry.occurred_at is None:
                continue
            if month_start <= entry.occurred_at < period_end:
                f2_current += amount
            elif prev_start <= entry.occurred_at < prev_end:
                f2_previous += amount

        # Monthly expense bars reuse the selected-range rows already fetched above.
        # They deliberately contain only direction=out totals, matching F1/F2.
        monthly_totals = {item.month: Decimal(0) for item in finance_months}
        for entry, tracker, amount, bad in decoded:
            if (
                bad
                or amount is None
                or tracker.direction != "out"
                or entry.occurred_at is None
                or not (period_start <= entry.occurred_at < period_end)
            ):
                continue
            local = _as_vn(entry.occurred_at)
            key = f"{local.year:04d}-{local.month:02d}"
            if key in monthly_totals:
                monthly_totals[key] += amount
        finance_months = [
            item.model_copy(update={"total": monthly_totals[item.month]}) for item in finance_months
        ]

        # Activity is a compact visualization aid, never a finance payload: active
        # (not archived), visible parent trackers, selected month only, and positive
        # daily counts. It reuses the parent-gated rows from the selected query.
        selected_month_start, _ = _month_bounds(month)
        activity_days = self._activity_days(decoded, selected_month_start, period_end)

        # ---------------- F3 / F4 ------------------------------------------
        group_totals: dict[UUID | None, Decimal] = {}
        group_trackers: dict[UUID | None, dict[UUID, Decimal]] = {}
        tracker_names: dict[UUID, str] = {}
        for entry, tracker, amount, bad in decoded:
            if bad or amount is None or tracker.direction != "out" or entry.occurred_at is None:
                continue
            if month_start <= entry.occurred_at < period_end:
                group_totals[tracker.group_id] = (
                    group_totals.get(tracker.group_id, Decimal(0)) + amount
                )
                inner = group_trackers.setdefault(tracker.group_id, {})
                inner[tracker.id] = inner.get(tracker.id, Decimal(0)) + amount

        if group_totals:
            ids = [gid for gid in group_totals if gid is not None]
            group_names: dict[UUID, str] = {}
            if ids:
                grp_res = await db.execute(
                    select(TrackerGroup.id, TrackerGroup.name).where(TrackerGroup.id.in_(ids))
                )
                group_names = dict(grp_res.all())

            f3_groups: list[F3Group] = []
            for group_id, total in group_totals.items():
                name = group_names.get(group_id) if group_id is not None else "Chưa nhóm"
                trackers = []
                for tid, ttotal in group_trackers.get(group_id, {}).items():
                    trackers.append({"tracker_id": str(tid), "name": None, "total": ttotal})
                f3_groups.append(F3Group(name=name, total=total, trackers=trackers))
            f3_groups.sort(key=lambda g: g.total, reverse=True)

            # Resolve tracker names for F3/F4 in one pass.
            tids = {UUID(line["tracker_id"]) for group in f3_groups for line in group.trackers}
            f4_decoded = [
                (entry, tracker, amount)
                for entry, tracker, amount, bad in decoded
                if not bad
                and amount is not None
                and tracker.direction == "out"
                and tracker.id in tids
                and entry.occurred_at is not None
                and month_start <= entry.occurred_at < period_end
            ]
            for _entry, tracker, _amount in f4_decoded:
                if tracker.id not in tracker_names:
                    tracker_names[tracker.id] = self._decrypt_name(tracker)
            for group in f3_groups:
                for line in group.trackers:
                    line["name"] = tracker_names.get(UUID(line["tracker_id"]), "")
        else:
            f3_groups = []

        # F4 top-5 by amount (Python sort — never SQL ORDER BY on ciphertext).
        f4_all = [
            (entry, tracker, amount)
            for entry, tracker, amount, bad in decoded
            if not bad
            and amount is not None
            and tracker.direction == "out"
            and entry.occurred_at is not None
            and month_start <= entry.occurred_at < period_end
        ]
        f4_all.sort(key=lambda item: item[2] or Decimal(0), reverse=True)
        f4_top: list[F4Top] = []
        for entry, tracker, amount in f4_all[:5]:
            if tracker.id not in tracker_names:
                tracker_names[tracker.id] = self._decrypt_name(tracker)
            f4_top.append(
                F4Top(
                    entry_id=entry.id,
                    tracker_id=tracker.id,
                    tracker_name=tracker_names[tracker.id],
                    amount=amount,
                )
            )

        return DashboardResponse(
            period_start=period_start,
            period_end=period_end,
            report_months=months,
            previous_period_start=prev_start,
            previous_period_end=prev_end,
            current_period_days=period.current_period_days,
            prev_period_days=period.prev_period_days,
            prev_period_truncated=period.prev_period_truncated,
            corrupted_entry_count=corrupted,
            f1_total=f1_total,
            f2_current=f2_current,
            f2_previous=f2_previous,
            f3_groups=f3_groups,
            f4_top=f4_top,
            f5_net=f5_net,
            finance_months=finance_months,
            activity_month=month,
            activity_days=activity_days,
            a2_gap=a2_gap,
            a3_counts=a3_counts,
            a4_trend=a4_trend,
            f6=f6,
        )
