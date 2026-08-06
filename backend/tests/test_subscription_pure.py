"""Pure (no-DB) rules of the 011c subscription slice: date math, status, monthly.

These are the tests that catch the two silent-drift traps of the spec: the
anchor-day chain (31/01 → 28/02 → 31/03 → 30/04) and the Decimal-vs-float
division trap on week/day conversions.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.subscription import (
    add_period,
    derive_status,
    monthly_amount,
    round_vnd,
)


def test_add_period_day_and_week_use_timedelta():
    assert add_period(date(2026, 1, 31), 1, "day", anchor_day=31) == date(2026, 2, 1)
    assert add_period(date(2026, 1, 15), 2, "week", anchor_day=15) == date(2026, 1, 29)


def test_add_period_month_clamps_end_of_month():
    assert add_period(date(2026, 1, 31), 1, "month", anchor_day=31) == date(2026, 2, 28)


def test_add_period_month_clamps_leap_february():
    assert add_period(date(2028, 1, 31), 1, "month", anchor_day=31) == date(2028, 2, 29)


def test_add_period_year_keeps_anchor_day():
    assert add_period(date(2026, 12, 31), 1, "year", anchor_day=31) == date(2027, 12, 31)


def test_add_period_chain_does_not_drift_without_anchor():
    """The chain test that catches milestone drift (§4.2).

    31/01 +1m → 28/02 → 31/03 → 30/04. Chaining from the TRUNCATED expires_on
    (anchor_day=28) would give 28/03 → 28/04 — this test goes red then.
    """
    first = add_period(date(2026, 1, 31), 1, "month", anchor_day=31)
    second = add_period(first, 1, "month", anchor_day=31)
    third = add_period(second, 1, "month", anchor_day=31)
    assert [first, second, third] == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_add_period_count_gt_one():
    assert add_period(date(2026, 1, 31), 3, "month", anchor_day=31) == date(2026, 4, 30)


@pytest.mark.parametrize(
    ("expires_on", "canceled_at", "today", "expected"),
    [
        (date(2026, 8, 20), None, date(2026, 8, 6), "active"),
        (date(2026, 8, 20), datetime.now(timezone.utc), date(2026, 8, 6), "canceled"),
        (date(2026, 8, 1), None, date(2026, 8, 6), "expired"),
        # Expired wins over canceled: the UI must not offer renewal-on-canceled
        # for a subscription that has already run out of time (§2.7).
        (date(2026, 8, 1), datetime.now(timezone.utc), date(2026, 8, 6), "expired"),
        (date(2026, 8, 6), None, date(2026, 8, 6), "active"),
    ],
)
def test_derive_status(expires_on, canceled_at, today, expected):
    assert derive_status(expires_on, canceled_at, today) == expected


def test_monthly_amount_month_is_period_count():
    assert monthly_amount(Decimal("300000"), 1, "month") == Decimal("300000")
    assert monthly_amount(Decimal("600000"), 3, "month") == Decimal("200000")


def test_monthly_amount_year_divides_by_twelve():
    assert monthly_amount(Decimal("2400000"), 1, "year") == Decimal("200000")
    assert monthly_amount(Decimal("4800000"), 2, "year") == Decimal("200000")


def test_monthly_amount_week_uses_exact_304375_decimal():
    """A week/day subscription must not raise TypeError (Decimal / float trap).

    ``monthly = amount / months_per_period`` where months for week = 7/30.4375,
    so a weekly 300.000 is 300000 * 30.4375 / 7 ≈ 1.304.464 per month.
    """
    assert monthly_amount(Decimal("300000"), 1, "week") == Decimal("300000") * Decimal(
        "30.4375"
    ) / Decimal(7)
    assert monthly_amount(Decimal("100000"), 30, "day") == Decimal("100000") * Decimal(
        "30.4375"
    ) / Decimal(30)


def test_round_vnd_half_up():
    assert round_vnd(Decimal("1234.5")) == Decimal("1235")
    assert round_vnd(Decimal("1234.4")) == Decimal("1234")
    assert round_vnd(Decimal("1234.499")) == Decimal("1234")
