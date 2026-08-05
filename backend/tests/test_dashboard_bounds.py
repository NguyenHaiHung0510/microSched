"""Pure boundary tests for the dashboard period math (no DB needed)."""

from datetime import datetime, timedelta, timezone

from app.domain.dashboard import VN_TZ, _periods


def _now(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=VN_TZ)


def test_f2_previous_period_truncated_when_previous_month_is_shorter():
    """31/03: kỳ trước cắt tại đầu tháng 3 → 28 ngày, truncated=true (spec §4.3)."""
    bounds = _periods("2026-03", _now(2026, 3, 31))
    assert bounds.period_start == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.period_end == _now(2026, 3, 31)
    assert bounds.current_period_days == 30
    assert bounds.prev_start == datetime(2026, 2, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 28
    assert bounds.prev_period_truncated is True
    assert bounds.is_future is False


def test_f2_past_month_compares_full_month_to_full_previous_month():
    """Tháng quá khứ: period_end = cuối tháng, kỳ trước = cùng thời lượng đã trôi.

    The operative F2 definition is "cùng thời lượng" (elapsed duration), not
    "whole previous calendar month": February has 28 days, so the previous
    window is the first 28 days of January (Jan 1 → Jan 29) and is NOT
    truncated (January is longer).
    """
    bounds = _periods("2026-02", _now(2026, 8, 5))
    assert bounds.period_end == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.current_period_days == 28
    assert bounds.prev_start == datetime(2026, 1, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 1, 29, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 28
    assert bounds.prev_period_truncated is False


def test_f2_no_truncation_when_previous_month_is_longer():
    """Ngày 30/4: kỳ trước kéo 29 ngày từ 01/03, tháng 3 dài hơn nên không cắt."""
    bounds = _periods("2026-04", _now(2026, 4, 30, 12))
    assert bounds.current_period_days == 29
    assert bounds.prev_start == datetime(2026, 3, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 3, 30, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 29
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


def test_current_month_mid_month_previous_window_matches_elapsed():
    """Ngày 15/05: kỳ trước bắt đầu 01/04, kéo 14 ngày (không cắt — tháng 4 đủ dài)."""
    bounds = _periods("2026-05", _now(2026, 5, 15))
    assert bounds.current_period_days == 14
    assert bounds.prev_start == datetime(2026, 4, 1, tzinfo=VN_TZ)
    assert bounds.prev_end == datetime(2026, 4, 15, tzinfo=VN_TZ)
    assert bounds.prev_period_days == 14
    assert bounds.prev_period_truncated is False


def test_month_validation_still_raises_value_error():
    import pytest

    with pytest.raises(ValueError):
        _periods("not-a-month", _now(2026, 8, 5))


def test_vn_tz_is_fixed_offset_seven_hours():
    assert VN_TZ == timezone(timedelta(hours=7))
