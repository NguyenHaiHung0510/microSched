"""Pure boundary tests for the dashboard period math (no DB needed)."""

from datetime import datetime, timedelta, timezone

from app.domain.dashboard import VN_TZ, _periods


def _now(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=VN_TZ)


def test_f2_previous_period_is_the_whole_previous_month_when_shorter():
    """31/03 compares all 28 days of February, never an elapsed-days truncation."""
    bounds = _periods("2026-03", _now(2026, 3, 31))
    assert bounds.period_start == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.period_end == _now(2026, 3, 31)
    assert bounds.current_period_days == 30
    assert bounds.prev_start == datetime(2026, 2, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 28
    assert bounds.prev_period_truncated is False
    assert bounds.is_future is False


def test_f2_past_month_compares_full_month_to_full_previous_month():
    """A full past February compares to all 31 days of the preceding January."""
    bounds = _periods("2026-02", _now(2026, 8, 5))
    assert bounds.period_end == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.current_period_days == 28
    assert bounds.prev_start == datetime(2026, 1, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 2, 1, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 31
    assert bounds.prev_period_truncated is False


def test_f2_current_partial_month_still_compares_full_previous_month():
    """A partial April report compares all 31 days of March."""
    bounds = _periods("2026-04", _now(2026, 4, 30, 12))
    assert bounds.current_period_days == 29
    assert bounds.prev_start == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 4, 1, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 31
    assert bounds.prev_period_truncated is False


def test_future_month_is_short_circuited():
    """Tháng tương lai: period_end = đầu tháng, không có kỳ trước (không kỳ giả)."""
    bounds = _periods("2026-09", _now(2026, 8, 5))
    assert bounds.is_future is True
    assert bounds.period_end == datetime(2026, 9, 1, tzinfo=VN_TZ)
    assert bounds.current_period_days == 0
    assert bounds.prev_start is None
    assert bounds.prev_end is None
    assert bounds.prev_period_days == 0


def test_current_month_mid_month_previous_window_is_full_calendar_month():
    """A partial May report compares all 30 days of April."""
    bounds = _periods("2026-05", _now(2026, 5, 15))
    assert bounds.current_period_days == 14
    assert bounds.prev_start == datetime(2026, 4, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 5, 1, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 30
    assert bounds.prev_period_truncated is False


def test_current_month_exact_midnight_keeps_full_previous_month():
    """The first instant of a current month is zero selected time, not a future month."""
    bounds = _periods("2026-05", _now(2026, 5, 1, 0))

    assert bounds.is_future is False
    assert bounds.current_period_days == 0
    assert bounds.prev_start == datetime(2026, 4, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 5, 1, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 30


def test_month_validation_still_raises_value_error():
    import pytest

    with pytest.raises(ValueError):
        _periods("not-a-month", _now(2026, 8, 5))


def test_vn_tz_is_fixed_offset_seven_hours():
    assert VN_TZ == timezone(timedelta(hours=7))
