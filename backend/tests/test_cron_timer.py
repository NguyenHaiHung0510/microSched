"""Unit tests for the CronTimer heap, settings validation, and reload sink."""

import asyncio
import heapq
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest

import app.core.cron_timer as cron
from app.core.cron_timer import (
    VN_TZ,
    CronTimer,
    ReloadSink,
    ScheduleKind,
    TimerItem,
    build_cron_timer_if_enabled,
)
from app.core.settings import get_settings
from app.domain.models import ReminderDispatch, Subscription, Tracker
from app.domain.reminder import DispatchOutcome
from app.web import deps


def dummy_factory():
    return None


class FakeResult:
    """Minimal stand-in for SQLAlchemy result objects used by load_snapshot."""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0]

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeDB:
    """Returns queued results in execution order and counts queries."""

    def __init__(self, results: list):
        self.results = list(results)
        self.executions = 0

    async def execute(self, stmt):
        self.executions += 1
        if not self.results:
            raise AssertionError(f"unexpected extra execute: {stmt}")
        return FakeResult(self.results.pop(0))


class FakeFactory:
    """Session factory yielding one FakeDB instance per ``async with``."""

    def __init__(self, db):
        self.db = db

    def __call__(self):
        class Ctx:
            def __init__(self, db):
                self.db = db

            async def __aenter__(self):
                return self.db

            async def __aexit__(self, *args):
                return False

        return Ctx(self.db)


class StubDispatcher:
    """Dispatcher double recording calls and returning a fixed outcome."""

    def __init__(self, outcome: DispatchOutcome):
        self.outcome = outcome
        self.calls = []

    async def dispatch_item(self, db, subject_type, subject_id, dispatched_on, payload_builder):
        self.calls.append((subject_type, subject_id, dispatched_on))
        return self.outcome


def _tracker(
    tracker_id: UUID,
    *,
    reminder_time=None,
    kind="health",
    input_mode="event",
) -> Tracker:
    return Tracker(
        id=tracker_id,
        name="enc:v1:name",
        kind=kind,
        direction="out",
        input_mode=input_mode,
        is_private=False,
        reminder_time=reminder_time,
    )


def _subscription(sub_id: UUID, tracker_id: UUID, *, expires_on, canceled_at=None) -> Subscription:
    return Subscription(
        id=sub_id,
        tracker_id=tracker_id,
        name="enc:v1:sub",
        amount="enc:v1:amount",
        period_count=1,
        period_unit="month",
        started_on=date(2026, 8, 1),
        expires_on=expires_on,
        auto_renew=True,
        canceled_at=canceled_at,
    )


def _dispatch(
    dispatch_id: UUID,
    *,
    subject_type: str,
    subject_id: UUID,
    dispatched_on: date,
    attempt_count: int = 0,
    last_attempt_at=None,
) -> ReminderDispatch:
    return ReminderDispatch(
        id=dispatch_id,
        subject_type=subject_type,
        subject_id=subject_id,
        dispatched_on=dispatched_on,
        status="pending",
        attempt_count=attempt_count,
        last_attempt_at=last_attempt_at,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_cron_timer_disabled_by_default(monkeypatch):
    """Verify build_cron_timer_if_enabled returns None when ENABLE_INPROCESS_CRON is false."""
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "false")
    get_settings.cache_clear()

    timer = build_cron_timer_if_enabled()
    assert timer is None


def test_cron_timer_enabled_returns_instance(monkeypatch):
    """Verify build_cron_timer_if_enabled returns a CronTimer instance when true."""
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "true")
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()

    timer = build_cron_timer_if_enabled(session_factory=dummy_factory)
    assert timer is not None
    assert timer.status == "starting"


def test_build_cron_timer_uses_real_session_factory(monkeypatch):
    """F3: with the flag on, the timer must build from app.core.db, not a ghost module."""
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "true")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/microsched")
    get_settings.cache_clear()
    from app.core import db as db_module

    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()
    try:
        timer = build_cron_timer_if_enabled()
        assert timer is not None
        assert timer.session_factory is not None
    finally:
        db_module.get_engine.cache_clear()
        db_module.get_sessionmaker.cache_clear()
        get_settings.cache_clear()


def test_build_cron_timer_fails_fast_without_database(monkeypatch):
    """F3: no DB configured with the flag on ⇒ loud RuntimeError, not a silent timer."""
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "true")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    from app.core import db as db_module

    db_module.get_engine.cache_clear()
    db_module.get_sessionmaker.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ENABLE_INPROCESS_CRON"):
            build_cron_timer_if_enabled()
    finally:
        db_module.get_engine.cache_clear()
        db_module.get_sessionmaker.cache_clear()
        get_settings.cache_clear()


@pytest.mark.anyio
async def test_load_snapshot_calls_expiry_lead_days(monkeypatch):
    """F2: load_snapshot must use the REAL settings reader, not get_app_setting."""
    calls = []

    async def fake_lead(db):
        calls.append(db)
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    timer = CronTimer(dummy_factory)
    db = FakeDB(results=[[], [], []])
    await timer.load_snapshot(db, now=datetime(2026, 8, 6, 5, 0, tzinfo=VN_TZ))
    assert len(calls) == 1


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


@pytest.mark.anyio
async def test_tracker_due_at_0800_and_2359_boundaries(monkeypatch):
    """011d §6.2: reminder_time 08:00/23:59 cross the day boundary correctly."""

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    morning = _tracker(UUID("01912345-6789-7000-8000-000000000101"), reminder_time=time(8, 0))
    night = _tracker(UUID("01912345-6789-7000-8000-000000000102"), reminder_time=time(23, 59))

    timer = CronTimer(dummy_factory)
    db = FakeDB(results=[[], [morning, night], []])
    # 10:00 VN: 08:00 has passed → tomorrow; 23:59 is still ahead → today.
    await timer.load_snapshot(db, now=datetime(2026, 8, 6, 10, 0, tzinfo=VN_TZ))
    items = {it[5].subject_id: it[5] for it in timer._heap}
    assert items[morning.id].due_at == datetime(2026, 8, 7, 8, 0, tzinfo=VN_TZ)
    assert items[night.id].due_at == datetime(2026, 8, 6, 23, 59, tzinfo=VN_TZ)
    for item in items.values():
        assert item.due_at.tzinfo is not None
        assert item.due_at.utcoffset() == timedelta(hours=7)

    timer2 = CronTimer(dummy_factory)
    db2 = FakeDB(results=[[], [morning, night], []])
    # 07:00 VN exactly: 08:00 is still ahead → today.
    await timer2.load_snapshot(db2, now=datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ))
    items2 = {it[5].subject_id: it[5] for it in timer2._heap}
    assert items2[morning.id].due_at == datetime(2026, 8, 6, 8, 0, tzinfo=VN_TZ)


@pytest.mark.anyio
async def test_load_snapshot_keeps_occurrences_inside_15_minute_grace(monkeypatch):
    """Restart/reload must enqueue today's occurrence until the grace boundary expires."""

    async def fake_lead(db):
        return 0

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    tracker_id = UUID("01912345-6789-7000-8000-000000000103")
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    tracker_timer = CronTimer(dummy_factory)
    await tracker_timer.load_snapshot(
        FakeDB(results=[[], [tracker], []]),
        now=datetime(2026, 8, 6, 8, 10, tzinfo=VN_TZ),
    )
    tracker_item = next(item[5] for item in tracker_timer._heap)
    assert tracker_item.occurrence_on == date(2026, 8, 6)
    assert tracker_item.due_at == datetime(2026, 8, 6, 8, 0, tzinfo=VN_TZ)

    parent_id = UUID("01912345-6789-7000-8000-000000000104")
    sub_id = UUID("01912345-6789-7000-8000-000000000105")
    sub = _subscription(sub_id, parent_id, expires_on=date(2026, 8, 6))
    parent = _tracker(parent_id, kind="finance", input_mode="money")
    sub_timer = CronTimer(dummy_factory)
    await sub_timer.load_snapshot(
        FakeDB(results=[[], [], [(sub, parent)]]),
        now=datetime(2026, 8, 6, 7, 10, tzinfo=VN_TZ),
    )
    sub_item = next(item[5] for item in sub_timer._heap)
    assert sub_item.occurrence_on == date(2026, 8, 6)
    assert sub_item.due_at == datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ)


@pytest.mark.anyio
async def test_subscription_candidates_and_lead_change(monkeypatch):
    """011d §6.2: lead-day window candidates at 07:00 VN; reload picks up a lead change."""
    lead = {"value": 3}

    async def fake_lead(db):
        return lead["value"]

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    sub = _subscription(
        UUID("01912345-6789-7000-8000-000000000201"),
        UUID("01912345-6789-7000-8000-000000000202"),
        expires_on=date(2026, 8, 16),
    )
    parent = _tracker(
        UUID("01912345-6789-7000-8000-000000000202"), kind="finance", input_mode="money"
    )
    now = datetime(2026, 8, 6, 5, 0, tzinfo=VN_TZ)

    timer = CronTimer(dummy_factory)
    await timer.load_snapshot(FakeDB(results=[[], [], [(sub, parent)]]), now=now)
    items = [it[5] for it in timer._heap]
    dates = sorted(item.occurrence_on for item in items)
    # lead 3 → first_date = max(today, expires-3) = 13/08. Snapshot enqueues ONE
    # future occurrence per subject; the day-by-day chain (up to expires_on) is
    # extended inside _process_due_item (F6), never pre-materialized.
    assert dates == [date(2026, 8, 13)]
    for item in items:
        assert item.due_at == datetime.combine(item.occurrence_on, time(7, 0), tzinfo=VN_TZ)

    lead["value"] = 1
    timer2 = CronTimer(dummy_factory)
    await timer2.load_snapshot(FakeDB(results=[[], [], [(sub, parent)]]), now=now)
    dates2 = sorted(it[5].occurrence_on for it in timer2._heap)
    # lead 1 → first_date = 15/08; the lead change is visible on reload.
    assert dates2 == [date(2026, 8, 15)]


@pytest.mark.anyio
async def test_pending_recovery_keeps_dispatch_id_and_backoff(monkeypatch):
    """011d §6.2: crash recovery rehydrates the SAME dispatch id with bounded backoff."""

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    now = datetime(2026, 8, 6, 8, 0, tzinfo=VN_TZ)
    last_at = (now - timedelta(minutes=5)).astimezone(UTC)
    tracker_id = UUID("01912345-6789-7000-8000-000000000301")
    parent_id = UUID("01912345-6789-7000-8000-000000000302")
    sub_id = UUID("01912345-6789-7000-8000-000000000303")
    did1 = UUID("01912345-6789-7000-8000-000000000304")
    did2 = UUID("01912345-6789-7000-8000-000000000305")
    pending = [
        _dispatch(
            did1,
            subject_type="tracker",
            subject_id=tracker_id,
            dispatched_on=date(2026, 8, 6),
            attempt_count=1,
            last_attempt_at=last_at,
        ),
        _dispatch(
            did2,
            subject_type="subscription",
            subject_id=sub_id,
            dispatched_on=date(2026, 8, 6),
            attempt_count=3,
            last_attempt_at=last_at,
        ),
    ]
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    sub = _subscription(sub_id, parent_id, expires_on=date(2026, 8, 10))
    parent = _tracker(parent_id, kind="finance", input_mode="money")

    timer = CronTimer(dummy_factory)
    db = FakeDB(results=[pending, [tracker], [(sub, parent)]])
    await timer.load_snapshot(db, now=now)
    items = {it[5].dispatch_id: it[5] for it in timer._heap}
    p1 = items[did1]
    assert p1.is_pending_recovery is True
    assert p1.dispatch_id == did1
    assert p1.occurrence_on == date(2026, 8, 6)
    assert p1.retry_count == 1
    assert p1.due_at == now  # attempt 1 → 30s backoff, but now already past it

    p2 = items[did2]
    assert p2.dispatch_id == did2
    assert p2.due_at == max(now, last_at.astimezone(VN_TZ) + timedelta(seconds=600))


@pytest.mark.anyio
async def test_dead_pending_rows_are_receipted_not_dropped(monkeypatch):
    """F11: exhausted/expired/ineligible pending rows log + counter, never silently vanish."""

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    now = datetime(2026, 8, 6, 8, 0, tzinfo=VN_TZ)
    tracker_id = UUID("01912345-6789-7000-8000-000000000401")
    ghost_id = UUID("01912345-6789-7000-8000-000000000402")
    pending = [
        _dispatch(
            UUID("01912345-6789-7000-8000-000000000411"),
            subject_type="tracker",
            subject_id=tracker_id,
            dispatched_on=date(2026, 8, 6),
            attempt_count=4,
            last_attempt_at=(now - timedelta(minutes=1)).astimezone(UTC),
        ),
        _dispatch(
            UUID("01912345-6789-7000-8000-000000000412"),
            subject_type="tracker",
            subject_id=tracker_id,
            dispatched_on=date(2026, 8, 5),
            attempt_count=1,
            last_attempt_at=(now - timedelta(hours=25)).astimezone(UTC),
        ),
        _dispatch(
            UUID("01912345-6789-7000-8000-000000000413"),
            subject_type="tracker",
            subject_id=ghost_id,
            dispatched_on=date(2026, 8, 6),
            attempt_count=1,
            last_attempt_at=(now - timedelta(minutes=1)).astimezone(UTC),
        ),
    ]
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    timer = CronTimer(dummy_factory)
    db = FakeDB(results=[pending, [tracker], []])
    await timer.load_snapshot(db, now=now)
    assert timer._pending_manual_required == {"expired": 1, "exhausted": 1, "ineligible": 1}
    queued = [it[5] for it in timer._heap]
    for dead_id in (
        UUID("01912345-6789-7000-8000-000000000411"),
        UUID("01912345-6789-7000-8000-000000000412"),
        UUID("01912345-6789-7000-8000-000000000413"),
    ):
        assert all(item.dispatch_id != dead_id for item in queued)


@pytest.mark.anyio
async def test_exhausted_outcome_is_receipted_and_next_day_scheduled(monkeypatch):
    """F10+F11: EXHAUSTED at dispatch logs a receipt and does not swallow tomorrow."""
    stub = StubDispatcher(DispatchOutcome.EXHAUSTED)
    monkeypatch.setattr(cron, "dispatcher", stub)
    now = datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ)
    tracker_id = UUID("01912345-6789-7000-8000-000000000501")
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    timer = CronTimer(FakeFactory(FakeDB(results=[[tracker]])))
    item = TimerItem(
        due_at=now,
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.TRACKER,
        subject_id=tracker_id,
        reminder_time=time(8, 0),
        retry_count=3,
        is_pending_recovery=True,
    )
    await timer._process_due_item(item, now=now)
    assert timer._pending_manual_required["exhausted"] == 1
    assert len(stub.calls) == 1
    next_item = timer._heap[0][5]
    assert next_item.occurrence_on == date(2026, 8, 7)
    assert next_item.due_at == datetime(2026, 8, 7, 8, 0, tzinfo=VN_TZ)


@pytest.mark.anyio
async def test_subscription_chain_schedules_next_day_and_retry_backoff(monkeypatch):
    """F6+F10: SENT schedules the next day; TEMPORARY_FAILURE retries with backoff."""

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    now = datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ)
    parent_id = UUID("01912345-6789-7000-8000-000000000601")
    sub_id = UUID("01912345-6789-7000-8000-000000000602")
    sub = _subscription(sub_id, parent_id, expires_on=date(2026, 8, 10))
    parent = _tracker(parent_id, kind="finance", input_mode="money")

    stub = StubDispatcher(DispatchOutcome.SENT)
    monkeypatch.setattr(cron, "dispatcher", stub)
    timer = CronTimer(FakeFactory(FakeDB(results=[[(sub, parent)]])))
    item = TimerItem(
        due_at=now,
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.SUBSCRIPTION,
        subject_id=sub_id,
        expires_on=date(2026, 8, 10),
    )
    await timer._process_due_item(item, now=now)
    next_item = timer._heap[0][5]
    assert next_item.occurrence_on == date(2026, 8, 7)
    assert next_item.due_at == datetime(2026, 8, 7, 7, 0, tzinfo=VN_TZ)
    assert next_item.kind == ScheduleKind.SUBSCRIPTION

    # TEMPORARY_FAILURE on the FIRST attempt → retry in 30s, same occurrence.
    stub2 = StubDispatcher(DispatchOutcome.TEMPORARY_FAILURE)
    monkeypatch.setattr(cron, "dispatcher", stub2)
    timer2 = CronTimer(FakeFactory(FakeDB(results=[[(sub, parent)]])))
    item2 = TimerItem(
        due_at=now,
        occurrence_on=date(2026, 8, 7),
        kind=ScheduleKind.SUBSCRIPTION,
        subject_id=sub_id,
        expires_on=date(2026, 8, 10),
    )
    await timer2._process_due_item(item2, now=now)
    retry_item = timer2._heap[0][5]
    assert retry_item.occurrence_on == date(2026, 8, 7)
    assert retry_item.retry_count == 1
    assert retry_item.due_at == now + timedelta(seconds=30)
    assert retry_item.is_pending_recovery is True

    # TEMPORARY_FAILURE on the FINAL attempt (retry_count=3) → next day (F10).
    stub3 = StubDispatcher(DispatchOutcome.TEMPORARY_FAILURE)
    monkeypatch.setattr(cron, "dispatcher", stub3)
    timer3 = CronTimer(FakeFactory(FakeDB(results=[[(sub, parent)]])))
    item3 = TimerItem(
        due_at=now,
        occurrence_on=date(2026, 8, 7),
        kind=ScheduleKind.SUBSCRIPTION,
        subject_id=sub_id,
        expires_on=date(2026, 8, 10),
        retry_count=3,
        is_pending_recovery=True,
    )
    await timer3._process_due_item(item3, now=now)
    next_item3 = timer3._heap[0][5]
    assert next_item3.occurrence_on == date(2026, 8, 8)
    assert next_item3.retry_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("item", "now", "expected_due"),
    [
        (
            TimerItem(
                due_at=datetime(2026, 8, 6, 7, 40, tzinfo=VN_TZ),
                occurrence_on=date(2026, 8, 6),
                kind=ScheduleKind.TRACKER,
                subject_id=UUID("01912345-6789-7000-8000-000000000701"),
                reminder_time=time(7, 40),
            ),
            datetime(2026, 8, 6, 8, 0, tzinfo=VN_TZ),
            datetime(2026, 8, 7, 7, 40, tzinfo=VN_TZ),
        ),
        (
            TimerItem(
                due_at=datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ),
                occurrence_on=date(2026, 8, 6),
                kind=ScheduleKind.SUBSCRIPTION,
                subject_id=UUID("01912345-6789-7000-8000-000000000702"),
                expires_on=date(2026, 8, 7),
            ),
            datetime(2026, 8, 6, 7, 20, tzinfo=VN_TZ),
            datetime(2026, 8, 7, 7, 0, tzinfo=VN_TZ),
        ),
    ],
)
async def test_stale_non_pending_item_skips_old_occurrence_and_schedules_next(
    item, now, expected_due
):
    """011d §1.5: stale non-pending work skips delivery but preserves the future chain."""
    timer = CronTimer(dummy_factory)

    class ExplodingDB:
        async def execute(self, stmt):
            raise AssertionError("grace-skipped item must not touch the database")

    timer.session_factory = FakeFactory(ExplodingDB())
    await timer._process_due_item(item, now=now)
    assert len(timer._heap) == 1
    next_item = timer._heap[0][5]
    assert next_item.kind == item.kind
    assert next_item.subject_id == item.subject_id
    assert next_item.occurrence_on == expected_due.date()
    assert next_item.due_at == expected_due
    assert next_item.is_pending_recovery is False


@pytest.mark.anyio
async def test_item_exception_does_not_kill_loop(monkeypatch):
    """A processing failure requests a rebuild instead of dropping its occurrence."""

    timer = CronTimer(FakeFactory(object()))
    loads = 0
    item = TimerItem(
        due_at=datetime.now(VN_TZ) - timedelta(minutes=1),
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.TRACKER,
        subject_id=UUID("01912345-6789-7000-8000-000000000801"),
    )

    async def fake_load_snapshot(db):
        nonlocal loads
        loads += 1
        if loads == 1:
            heapq.heappush(timer._heap, item.heap_tuple())

    async def boom_process(due_item):
        assert due_item == item
        raise RuntimeError("synthetic dispatch DB failure")

    monkeypatch.setattr(timer, "load_snapshot", fake_load_snapshot)
    monkeypatch.setattr(timer, "_process_due_item", boom_process)
    task = asyncio.create_task(timer.run())
    await asyncio.sleep(0.05)
    assert task.done() is False, "the loop must survive a failing item"
    assert loads >= 2, "failure must rebuild from durable pending/schedule sources"
    await timer.stop()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.anyio
async def test_empty_heap_waits_without_queries(monkeypatch):
    """011d §6.2/§6.4: an empty queue waits forever and never queries."""

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    db = FakeDB(results=[[], [], [], [], [], []])
    timer = CronTimer(FakeFactory(db))
    task = asyncio.create_task(timer.run())
    await asyncio.sleep(0.1)
    assert db.executions == 3, "exactly the one startup snapshot, no polling"
    timer.request_reload("test")
    await asyncio.sleep(0.1)
    assert db.executions == 6, "reload after the commit marker"
    await timer.stop()
    await asyncio.wait_for(task, timeout=2)
    assert task.done()


@pytest.mark.anyio
async def test_snapshot_reload_retries_then_recovers(monkeypatch):
    """011d §2.2: failure retries 30s → 2m → 10m, then resumes only on success."""

    monkeypatch.setattr(cron, "SNAPSHOT_RETRY_BACKOFF_SECONDS", (0.01, 0.01, 0.01))
    timer = CronTimer(FakeFactory(object()))
    attempts = 0

    async def flaky_load_snapshot(db):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("synthetic snapshot failure")

    monkeypatch.setattr(timer, "load_snapshot", flaky_load_snapshot)
    task = asyncio.create_task(timer.run())
    await asyncio.sleep(0.05)
    assert attempts == 3
    assert timer.status == "running"
    await timer.stop()
    await asyncio.wait_for(task, timeout=2)
    assert task.done()


@pytest.mark.anyio
async def test_snapshot_reload_fails_after_three_retries(monkeypatch):
    """A permanently broken DB must fail lifecycle supervision, never wait for mutation."""

    monkeypatch.setattr(cron, "SNAPSHOT_RETRY_BACKOFF_SECONDS", (0, 0, 0))
    timer = CronTimer(FakeFactory(object()))
    attempts = 0

    async def broken_load_snapshot(db):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("synthetic permanent snapshot failure")

    monkeypatch.setattr(timer, "load_snapshot", broken_load_snapshot)
    with pytest.raises(cron.CronTimerReloadFailure):
        await timer.run()
    assert attempts == 4
    assert timer.status == "degraded"


@pytest.mark.anyio
async def test_get_session_reload_marker_only_after_commit(monkeypatch):
    """F4: the marker triggers a reload only on commit; rollback must not."""
    calls = []

    class FakeSink:
        def request_reload(self, reason: str) -> None:
            calls.append(reason)

    class FakeSession:
        def __init__(self, fail_commit: bool = False):
            self.info = {}
            self.committed = False
            self.rolled_back = False
            self.fail_commit = fail_commit

        async def commit(self):
            self.committed = True
            if self.fail_commit:
                raise RuntimeError("commit boom")

        async def rollback(self):
            self.rolled_back = True

    class FakeFactory:
        def __init__(self, session):
            self.session = session

        def __call__(self):
            class Ctx:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, *args):
                    return False

            return Ctx(self.session)

    token = deps.cron_reload_sink.set(FakeSink())
    try:
        session = FakeSession()
        monkeypatch.setattr(deps, "get_sessionmaker", lambda: FakeFactory(session))

        async def consume_ok():
            async for _db in deps.get_session():
                _db.info[deps.CRON_TIMER_RELOAD_INFO_KEY] = "tracker:reminder_time"

        await consume_ok()
        assert session.committed is True
        assert calls == ["tracker:reminder_time"]
        assert deps.CRON_TIMER_RELOAD_INFO_KEY not in session.info

        # A commit failure after the request wrote its marker must roll back and
        # must NOT reach the reload sink — the DB never observed the change.
        calls.clear()
        session2 = FakeSession(fail_commit=True)
        monkeypatch.setattr(deps, "get_sessionmaker", lambda: FakeFactory(session2))

        try:
            async for _db in deps.get_session():
                _db.info[deps.CRON_TIMER_RELOAD_INFO_KEY] = "tracker:reminder_time"
        except RuntimeError:
            pass

        assert session2.rolled_back is True
        assert calls == [], "rollback must never reach the reload sink"
        assert deps.CRON_TIMER_RELOAD_INFO_KEY not in session2.info
    finally:
        deps.cron_reload_sink.reset(token)
