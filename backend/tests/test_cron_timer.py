"""Unit tests for the CronTimer heap, settings validation, and reload sink."""

from datetime import date, datetime
from uuid import UUID

from app.core.cron_timer import (
    VN_TZ,
    CronTimer,
    ReloadSink,
    ScheduleKind,
    TimerItem,
    build_cron_timer_if_enabled,
)
from app.core.settings import get_settings


def dummy_factory():
    return None


def test_cron_timer_disabled_by_default(monkeypatch):
    """Verify build_cron_timer_if_enabled returns None when ENABLE_INPROCESS_CRON is false."""
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "false")
    get_settings.cache_clear()

    timer = build_cron_timer_if_enabled()
    assert timer is None


def test_cron_timer_enabled_returns_instance(monkeypatch):
    """Verify build_cron_timer_if_enabled returns a CronTimer instance when true."""
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "true")
    get_settings.cache_clear()

    timer = build_cron_timer_if_enabled(session_factory=dummy_factory)
    assert timer is not None
    assert timer.status == "starting"


def test_timer_item_heap_ordering():
    """Verify TimerItem ordering in min-heap by due_at, kind_order, subject_id."""
    due1 = datetime(2026, 8, 6, 8, 0, tzinfo=VN_TZ)
    due2 = datetime(2026, 8, 6, 9, 0, tzinfo=VN_TZ)

    id_a = UUID("01912345-6789-7000-8000-000000000001")
    id_b = UUID("01912345-6789-7000-8000-000000000002")

    item1 = TimerItem(
        due_at=due1,
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.TRACKER,
        subject_id=id_a,
    )
    item2 = TimerItem(
        due_at=due2,
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.TRACKER,
        subject_id=id_a,
    )
    item3 = TimerItem(
        due_at=due1,
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.SUBSCRIPTION,
        subject_id=id_b,
    )

    # due1 < due2, so item1 < item2
    assert item1.heap_tuple() < item2.heap_tuple()
    # at same due1, tracker (kind_order 0) < subscription (kind_order 1), so item1 < item3
    assert item1.heap_tuple() < item3.heap_tuple()


def test_health_snapshot():
    """Verify RAM-only health snapshot structure."""
    timer = CronTimer(dummy_factory)

    snapshot = timer.health_snapshot()
    assert snapshot["status"] == "starting"
    assert snapshot["queue_size"] == 0
    assert snapshot["next_due"] is None
    assert snapshot["mode"] == "inprocess"


def test_reload_sink_request_reload():
    """Verify ReloadSink sets event on CronTimer."""
    timer = CronTimer(dummy_factory)
    sink = ReloadSink(timer)

    assert not timer.reload_event.is_set()
    sink.request_reload("unit_test")
    assert timer.reload_event.is_set()
    assert timer._reload_reason == "unit_test"
