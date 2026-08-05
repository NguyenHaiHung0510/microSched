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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain import money
from app.domain.models import AuthSession, Entry, Tracker, TrackerGroup
from app.domain.reading import not_deleted, with_privacy_gate

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
    def _prev_avg_as_number(self, value: Decimal) -> int:
        return int(value)


class DashboardResponse(BaseModel):
    """Aggregated dashboard payload returned by ``GET /api/tracker/dashboard``."""

    period_start: datetime
    period_end: datetime
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
    a2_gap: list[dict] = Field(default_factory=list)
    a3_counts: A3Counts = Field(default_factory=lambda: A3Counts(week=0, month=0, year=0))
    a4_trend: A4Trend = Field(
        default_factory=lambda: A4Trend(current_month=0, prev_avg=Decimal(0), trend="flat")
    )

    @field_serializer("f1_total", "f2_current", "f2_previous", "f5_net")
    def _money_as_number(self, value: Decimal) -> int:
        return int(value)


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """Return ``(month_start, next_month_start)`` in ``+07:00``."""
    year, _, month_num = month.partition("-")
    start = datetime(int(year), int(month_num), 1, tzinfo=VN_TZ)
    if month_num == "12":
        next_start = datetime(int(year) + 1, 1, 1, tzinfo=VN_TZ)
    else:
        next_start = datetime(int(year), int(month_num) + 1, 1, tzinfo=VN_TZ)
    return start, next_start


def _relative_now() -> datetime:
    """Return current time normalized to ``+07:00``."""
    return datetime.now(timezone.utc).astimezone(VN_TZ)


def _monday_of(day: datetime) -> datetime:
    """Return 00:00 (+07) of the Monday starting the week containing ``day``."""
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.weekday())


def _shift_months(start: datetime, count: int) -> datetime:
    """Return the first day ``count`` calendar months before ``start``."""
    year, month = start.year, start.month
    for _ in range(count):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return datetime(year, month, 1, tzinfo=VN_TZ)


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
        self, db: AsyncSession, auth: AuthSession, month_start: datetime, month_end: datetime
    ) -> list[tuple[Entry, Tracker]]:
        """Fetch entries of the requested month through their parent trackers.

        Applies the parent's privacy gate but NOT the parent's soft-delete gate: an
        archived tracker's money history must still count (F1–F5). Privacy is never
        exempted. Only the entry's own soft-delete is filtered.
        """
        stmt = select(Entry, Tracker).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Entry)
        stmt = stmt.where(Entry.occurred_at >= month_start, Entry.occurred_at < month_end)
        result = await db.execute(stmt)
        return [(entry, tracker) for entry, tracker in result]

    async def _fetch_all(self, db: AsyncSession, auth: AuthSession) -> list[tuple[Entry, Tracker]]:
        stmt = select(Entry, Tracker).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Entry)
        result = await db.execute(stmt)
        return [(entry, tracker) for entry, tracker in result]

    async def _fetch_90d(
        self, db: AsyncSession, auth: AuthSession, tracker_id: UUID, since: datetime
    ) -> list[tuple[Entry, Tracker]]:
        stmt = select(Entry, Tracker).join(Tracker, Entry.tracker_id == Tracker.id)
        stmt = with_privacy_gate(stmt, Tracker, auth)
        stmt = not_deleted(stmt, Entry)
        stmt = stmt.where(Entry.tracker_id == tracker_id, Entry.occurred_at >= since)
        stmt = stmt.order_by(Entry.occurred_at)
        result = await db.execute(stmt)
        return [(entry, tracker) for entry, tracker in result]

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

        For each tracker we take the ``window_days`` most recent entries, compute the
        gaps between consecutive ``occurred_at`` values, and average them in Python.
        Fewer than ``min_entries`` ⇒ the tracker is reported with ``enough=False`` so
        the UI writes "chưa đủ dữ liệu" instead of drawing "0 ngày".
        """
        since = now - timedelta(days=window_days)
        trackers = await self._visible_trackers(db, auth)
        result: list[dict] = []
        for tracker in trackers:
            rows = await self._fetch_90d(db, auth, tracker.id, since)
            timestamps = sorted(
                (entry.occurred_at for entry, _ in rows if entry.occurred_at is not None)
            )
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

    async def compute(
        self, db: AsyncSession, auth: AuthSession, *, month: str
    ) -> DashboardResponse:
        """Compute the whole dashboard for one requested month."""
        now = _relative_now()
        month_start, month_end = _month_bounds(month)
        period_end = min(now, month_end)
        period_start = month_start
        current_days = max(1, (period_end - period_start).days)

        month_rows = await self._fetch_month(db, auth, month_start, month_end)

        # F2 compares against the same-length previous period, which lies strictly
        # before [month_start, month_end). Fetch those rows too, or f2_previous is
        # silently zero even when the previous period has spending (§4.2 F2).
        prev_start = period_start - timedelta(days=current_days)
        prev_end = min(period_start, prev_start + timedelta(days=current_days))
        prev_period_truncated = prev_end < prev_start + timedelta(days=current_days)
        prev_rows = await self._fetch_month(db, auth, prev_start, prev_end)
        fetch_rows = month_rows + prev_rows

        a2_gap = await self._a2_gap(db, auth, now)
        corrupted = 0
        decoded: list[tuple[Entry, Tracker, Decimal | None, bool]] = []
        for entry, tracker in fetch_rows:
            amount, bad = self._safe_amount(entry)
            if bad:
                corrupted += 1
            decoded.append((entry, tracker, amount, bad))

        # ---------------- A3 / A4 (relative to today) ---------------------
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
        prev3_rows = await self._fetch_month(db, auth, prev3_start, prev3_end)
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

        # ---------------- F1 / F5 (within the live period) -----------------
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

        # ---------------- F2 (same-length previous period) -----------------
        prev_days = (prev_end - prev_start).days
        f2_previous = Decimal(0)
        f2_current = Decimal(0)
        for entry, tracker, amount, bad in decoded:
            if bad or amount is None or tracker.direction != "out" or entry.occurred_at is None:
                continue
            if month_start <= entry.occurred_at < period_end:
                f2_current += amount
            elif prev_start <= entry.occurred_at < prev_end:
                f2_previous += amount

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
            tids = {tid for group in f3_groups for tid_map in group.trackers for tid in tid_map}
            f4_decoded = [
                (entry, tracker, amount)
                for entry, tracker, amount, bad in decoded
                if not bad
                and amount is not None
                and tracker.direction == "out"
                and tracker.id in tids
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
            and month_start <= entry.occurred_at < month_end
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
            current_period_days=current_days,
            prev_period_days=prev_days,
            prev_period_truncated=prev_period_truncated,
            corrupted_entry_count=corrupted,
            f1_total=f1_total,
            f2_current=f2_current,
            f2_previous=f2_previous,
            f3_groups=f3_groups,
            f4_top=f4_top,
            f5_net=f5_net,
            a2_gap=a2_gap,
            a3_counts=a3_counts,
            a4_trend=a4_trend,
        )
