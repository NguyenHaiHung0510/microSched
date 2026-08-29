"""Unit tests for the CronTimer heap, settings validation, and reload sink."""

import asyncio
import heapq
import logging
import sys
import threading
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
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
from app.domain.push import ProviderWorkTracker
from app.domain.reminder import DispatchOutcome, DispatchTelemetry
from app.web import deps

DEFAULT_LOCK_CONNECTION = CronTimer._default_lock_connection


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
        if "to_regclass" in str(stmt):
            # 035A probes the future batch-item table before choosing the
            # recovery query.  Unit fixtures model the pre-0012 schema.
            return FakeResult([])
        if not self.results:
            # Generic tracker scheduling adds two bounded aggregate queries.
            # Older unit fixtures that do not care about their values may omit
            # them; a real unexpected query is still visible through count tests.
            return FakeResult([])
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


class FakeLockConnection:
    """Dedicated advisory-lock test double, isolated from schedule queries."""

    def __init__(self):
        self.closed = False
        self.listener = None
        self.unlock_calls = 0

    async def fetchval(self, query, *args):
        if "pg_try_advisory_lock" in query:
            return True
        if "pg_locks" in query:
            return not self.closed
        raise AssertionError(f"unexpected lock query: {query}")

    async def execute(self, query, *args):
        assert "pg_advisory_unlock" in query
        self.unlock_calls += 1

    def add_termination_listener(self, listener):
        self.listener = listener

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_scheduler_lock(monkeypatch):
    """Keep legacy unit tests DB-free while production uses asyncpg directly."""

    async def open_connection():
        return FakeLockConnection()

    monkeypatch.setattr(CronTimer, "_default_lock_connection", lambda self: open_connection())


class StubDispatcher:
    """Dispatcher double recording calls and returning a fixed outcome."""

    def __init__(self, outcome: DispatchOutcome, *, attempt_count: int | None = None):
        self.outcome = outcome
        self.attempt_count = attempt_count or (4 if outcome == DispatchOutcome.EXHAUSTED else 1)
        self.calls = []

    async def dispatch_item(
        self,
        db,
        subject_type,
        subject_id,
        dispatched_on,
        payload_builder,
        *,
        telemetry=None,
        ownership_guard=None,
    ):
        self.calls.append((subject_type, subject_id, dispatched_on))
        if ownership_guard is not None:
            await ownership_guard()
        if telemetry is not None:
            telemetry(DispatchTelemetry(attempt_count=self.attempt_count))
            telemetry(DispatchTelemetry(attempt_count=self.attempt_count, outcome=self.outcome))
        return self.outcome


def _tracker(
    tracker_id: UUID,
    *,
    reminder_time=None,
    kind="health",
    input_mode="event",
    reminder_mode=None,
    reminder_interval_days=None,
    reminder_action=None,
) -> Tracker:
    return Tracker(
        id=tracker_id,
        name="enc:v1:name",
        kind=kind,
        direction="out",
        input_mode=input_mode,
        is_private=False,
        reminder_time=reminder_time,
        reminder_mode=reminder_mode,
        reminder_interval_days=reminder_interval_days,
        reminder_action=reminder_action,
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


@pytest.mark.anyio
async def test_standby_never_loads_snapshot_or_dispatches(monkeypatch):
    """035A: a lock standby must not touch schedule recovery or delivery state."""

    class StandbyLockConnection(FakeLockConnection):
        async def fetchval(self, query, *args):
            if "pg_try_advisory_lock" in query:
                return False
            raise AssertionError(f"standby must not run lock liveness query: {query}")

    connection = StandbyLockConnection()

    async def open_connection():
        return connection

    monkeypatch.setattr(cron, "OWNERSHIP_ACQUIRE_BACKOFF_SECONDS", (3600,))
    db = FakeDB(results=[])
    dispatcher = StubDispatcher(DispatchOutcome.SENT)
    timer = CronTimer(
        FakeFactory(db),
        reminder_dispatcher=dispatcher,
        lock_connection_factory=open_connection,
    )
    task = asyncio.create_task(timer.run())
    try:
        for _ in range(100):
            if timer.status == "standby":
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("timer did not enter standby")
        assert db.executions == 0
        assert dispatcher.calls == []
    finally:
        await timer.stop()
        await asyncio.wait_for(task, timeout=1)


@pytest.mark.anyio
async def test_default_lock_connection_uses_matching_neon_direct_endpoint(monkeypatch):
    """035A never asks a Neon pooler to hold the session advisory lock."""
    connected_dsns: list[str] = []
    connection = object()

    async def connect(dsn: str):
        connected_dsns.append(dsn)
        return connection

    monkeypatch.setattr(
        cron,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=(
                "postgresql+asyncpg://app_role:fixture-password@"
                "ep-blue-pooler.aws.neon.tech/appdb?ssl=require"
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=connect))
    monkeypatch.setattr(CronTimer, "_default_lock_connection", DEFAULT_LOCK_CONNECTION)

    result = await CronTimer(dummy_factory)._default_lock_connection()

    assert result is connection
    assert len(connected_dsns) == 1
    assert "ep-blue.aws.neon.tech" in connected_dsns[0]
    assert "-pooler" not in connected_dsns[0]


@pytest.mark.anyio
async def test_default_lock_connection_rejects_unsupported_pooler(monkeypatch):
    """A non-Neon pooler cannot become an accidental ownership authority."""
    monkeypatch.setattr(
        cron,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://app_role:fixture-password@pooler.example.invalid/appdb"
        ),
    )
    monkeypatch.setattr(CronTimer, "_default_lock_connection", DEFAULT_LOCK_CONNECTION)

    with pytest.raises(cron.CronTimerOwnershipError, match="supported direct endpoint"):
        await CronTimer(dummy_factory)._default_lock_connection()


@pytest.mark.anyio
async def test_lock_connection_loss_is_fatal_before_another_snapshot(monkeypatch):
    """035A: loss of the dedicated connection fails lifespan supervision closed."""

    connection = FakeLockConnection()
    loaded = asyncio.Event()

    async def open_connection():
        return connection

    timer = CronTimer(FakeFactory(object()), lock_connection_factory=open_connection)

    async def snapshot(db):
        loaded.set()

    monkeypatch.setattr(timer, "load_snapshot", snapshot)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(loaded.wait(), timeout=1)
    assert connection.listener is not None
    connection.listener(connection)
    with pytest.raises(cron.CronTimerOwnershipLost):
        await asyncio.wait_for(task, timeout=1)


@pytest.mark.anyio
async def test_abrupt_owner_loss_allows_standby_takeover(monkeypatch):
    """A stopped owner releases the shared fence so the standby alone loads work."""

    class SharedFence:
        owner = None

    class SharedLockConnection(FakeLockConnection):
        def __init__(self, fence: SharedFence):
            super().__init__()
            self.fence = fence

        async def fetchval(self, query, *args):
            if "pg_try_advisory_lock" in query:
                if self.fence.owner is None:
                    self.fence.owner = self
                    return True
                return False
            if "pg_locks" in query:
                return self.fence.owner is self and not self.closed
            raise AssertionError(f"unexpected lock query: {query}")

        async def close(self):
            self.closed = True
            if self.fence.owner is self:
                self.fence.owner = None

    fence = SharedFence()
    first_connection = SharedLockConnection(fence)
    second_connections: list[SharedLockConnection] = []
    first_loaded = asyncio.Event()
    second_loaded = asyncio.Event()

    async def first_factory():
        return first_connection

    async def second_factory():
        connection = SharedLockConnection(fence)
        second_connections.append(connection)
        return connection

    first = CronTimer(FakeFactory(object()), lock_connection_factory=first_factory)
    second = CronTimer(FakeFactory(object()), lock_connection_factory=second_factory)

    async def first_snapshot(db):
        first_loaded.set()

    async def second_snapshot(db):
        second_loaded.set()

    first.load_snapshot = first_snapshot
    second.load_snapshot = second_snapshot
    monkeypatch.setattr(cron, "OWNERSHIP_ACQUIRE_BACKOFF_SECONDS", (0.01,))
    first_task = asyncio.create_task(first.run())
    second_task = asyncio.create_task(second.run())
    try:
        await asyncio.wait_for(first_loaded.wait(), timeout=1)
        for _ in range(100):
            if second.status == "standby":
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("second timer did not enter standby")

        assert first_connection.listener is not None
        first_connection.listener(first_connection)
        with pytest.raises(cron.CronTimerOwnershipLost):
            await asyncio.wait_for(first_task, timeout=1)
        await asyncio.wait_for(second_loaded.wait(), timeout=1)
        assert second.status == "owner"
        assert second_connections
    finally:
        await first.stop()
        await second.stop()
        await asyncio.gather(first_task, second_task, return_exceptions=True)


@pytest.mark.anyio
async def test_lock_loss_cancels_inflight_sender_before_a_second_provider_call():
    """035A: the lost-lock callback cancels the active sender immediately."""

    connection = FakeLockConnection()
    started = asyncio.Event()
    cancelled = asyncio.Event()
    timer = CronTimer(FakeFactory(object()))
    timer._lock_connection = connection
    timer._ownership_active = True
    timer._status = "owner"
    connection.add_termination_listener(timer._on_lock_connection_terminated)

    async def blocked_sender():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    timer._dispatch_task = asyncio.create_task(blocked_sender())
    await asyncio.wait_for(started.wait(), timeout=1)
    assert connection.listener is not None
    connection.listener(connection)
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert timer.status == "ownership_lost"
    assert timer._ownership_lost_event.is_set()


@pytest.mark.anyio
async def test_graceful_stop_cancels_sender_before_unlock():
    """035A: shutdown never relinquishes ownership while a sender still runs."""

    connection = FakeLockConnection()
    started = asyncio.Event()
    cancelled = asyncio.Event()
    timer = CronTimer(FakeFactory(object()))
    timer._lock_connection = connection
    timer._ownership_active = True
    timer._status = "owner"

    async def blocked_sender():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    timer._dispatch_task = asyncio.create_task(blocked_sender())
    await asyncio.wait_for(started.wait(), timeout=1)
    await timer.stop()

    assert cancelled.is_set()
    assert connection.unlock_calls == 1
    assert connection.closed is True


@pytest.mark.anyio
async def test_graceful_stop_waits_for_uncancellable_provider_thread(monkeypatch):
    """035A P1: cancellation must not unlock while the worker thread still runs."""

    class Dispatcher:
        def __init__(self):
            self.provider_work = ProviderWorkTracker()

    connection = FakeLockConnection()
    dispatcher = Dispatcher()
    timer = CronTimer(FakeFactory(object()), reminder_dispatcher=dispatcher)
    timer._lock_connection = connection
    timer._ownership_active = True
    timer._status = "owner"

    worker_started = asyncio.Event()
    release_worker = threading.Event()
    loop = asyncio.get_running_loop()

    def blocking_provider_call():
        loop.call_soon_threadsafe(worker_started.set)
        release_worker.wait()

    worker = asyncio.create_task(asyncio.to_thread(blocking_provider_call))
    dispatcher.provider_work.track(worker)
    await asyncio.wait_for(worker_started.wait(), timeout=1)
    stop_task = asyncio.create_task(timer.stop())
    try:
        await asyncio.sleep(0)
        assert connection.unlock_calls == 0
        assert connection.closed is False
    finally:
        release_worker.set()
        await asyncio.wait_for(stop_task, timeout=1)
    assert connection.unlock_calls == 1
    assert connection.closed is True


@pytest.mark.anyio
async def test_shutdown_provider_wait_failure_still_releases_ownership():
    """A failed worker drain cannot strand the advisory lock after shutdown."""

    class FailingProviderWork:
        async def wait_for_idle(self, timeout: float) -> bool:
            raise RuntimeError("test-only provider wait failure")

    class Dispatcher:
        provider_work = FailingProviderWork()

    connection = FakeLockConnection()
    timer = CronTimer(FakeFactory(object()), reminder_dispatcher=Dispatcher())
    timer._lock_connection = connection
    timer._ownership_active = True
    timer._status = "owner"

    with pytest.raises(RuntimeError, match="provider wait failure"):
        await timer.stop()

    assert timer.status == "stopped"
    assert connection.unlock_calls == 1
    assert connection.closed is True


@pytest.mark.anyio
async def test_run_loss_transitions_through_stopping_to_stopped(caplog):
    """A fatal ownership loss still emits the complete terminal state sequence."""
    connection = FakeLockConnection()
    loaded = asyncio.Event()

    async def open_connection():
        return connection

    timer = CronTimer(FakeFactory(object()), lock_connection_factory=open_connection)

    async def snapshot(db):
        loaded.set()

    timer.load_snapshot = snapshot
    caplog.set_level(logging.INFO, logger=cron.__name__)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(loaded.wait(), timeout=1)
    assert connection.listener is not None
    connection.listener(connection)

    with pytest.raises(cron.CronTimerOwnershipLost):
        await asyncio.wait_for(task, timeout=1)

    states = [
        record.getMessage().split()[1].split("=", 1)[1]
        for record in caplog.records
        if record.name == cron.__name__
        and record.getMessage().startswith("cron_timer_ownership_transition")
    ]
    assert states[-3:] == ["ownership_lost", "stopping", "stopped"]
    assert timer.status == "stopped"


@pytest.mark.anyio
async def test_stop_cancels_hung_lock_connection_attempt(monkeypatch):
    """Shutdown cancels an in-flight connect rather than waiting for its timeout."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hanging_factory():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(cron, "OWNERSHIP_CONNECTION_TIMEOUT_SECONDS", 3600)
    timer = CronTimer(FakeFactory(object()), lock_connection_factory=hanging_factory)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.wait_for(timer.stop(), timeout=1)
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    await asyncio.wait_for(task, timeout=1)
    assert timer.status == "stopped"


@pytest.mark.anyio
async def test_acquire_timeout_closes_connection_and_enters_standby(monkeypatch):
    """A hung pg_try_advisory_lock is bounded, closed, and never treated as owner."""

    class HangingLockConnection(FakeLockConnection):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def fetchval(self, query, *args):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

    connection = HangingLockConnection()

    async def open_connection():
        return connection

    monkeypatch.setattr(cron, "OWNERSHIP_CONNECTION_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(cron, "OWNERSHIP_ACQUIRE_BACKOFF_SECONDS", (3600,))
    timer = CronTimer(FakeFactory(object()), lock_connection_factory=open_connection)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(connection.started.wait(), timeout=1)
    await asyncio.wait_for(connection.cancelled.wait(), timeout=1)
    for _ in range(100):
        if timer.status == "standby":
            break
        await asyncio.sleep(0)
    else:
        pytest.fail("timer did not enter standby after bounded acquisition timeout")
    assert connection.closed is True
    assert timer._ownership_active is False
    await timer.stop()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.anyio
async def test_lock_loss_preempts_blocked_snapshot(monkeypatch):
    """035A P1: a lost lock interrupts snapshot work before a second recovery."""

    connection = FakeLockConnection()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def open_connection():
        return connection

    timer = CronTimer(FakeFactory(object()), lock_connection_factory=open_connection)

    async def blocked_snapshot(db):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(timer, "load_snapshot", blocked_snapshot)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(started.wait(), timeout=1)
    assert connection.listener is not None
    connection.listener(connection)
    with pytest.raises(cron.CronTimerOwnershipLost):
        await asyncio.wait_for(task, timeout=1)
    assert cancelled.is_set()


@pytest.mark.anyio
async def test_lock_loss_preempts_blocked_reload_recovery(monkeypatch):
    """035A P1: reload recovery cannot continue after a dedicated-lock loss."""

    connection = FakeLockConnection()
    startup_done = asyncio.Event()
    reload_started = asyncio.Event()
    reload_cancelled = asyncio.Event()

    async def open_connection():
        return connection

    timer = CronTimer(FakeFactory(object()), lock_connection_factory=open_connection)
    loads = 0

    async def snapshot(db):
        nonlocal loads
        loads += 1
        if loads == 1:
            startup_done.set()
            return
        reload_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            reload_cancelled.set()
            raise

    monkeypatch.setattr(timer, "load_snapshot", snapshot)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(startup_done.wait(), timeout=1)
    timer.request_reload("test")
    await asyncio.wait_for(reload_started.wait(), timeout=1)
    assert connection.listener is not None
    connection.listener(connection)
    with pytest.raises(cron.CronTimerOwnershipLost):
        await asyncio.wait_for(task, timeout=1)
    assert reload_cancelled.is_set()
    assert loads == 2


@pytest.mark.anyio
async def test_future_batch_schema_adds_pending_recovery_antijoin(monkeypatch):
    """035A: post-0012 linked pending rows never enter legacy recovery."""

    class FutureSchemaDB(FakeDB):
        def __init__(self):
            super().__init__([[], [], []])
            self.statements = []

        async def execute(self, stmt):
            self.executions += 1
            self.statements.append(str(stmt))
            if "to_regclass" in str(stmt):
                return FakeResult(["microsched.tracker_reminder_batch_item"])
            if not self.results:
                return FakeResult([])
            return FakeResult(self.results.pop(0))

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    db = FutureSchemaDB()
    timer = CronTimer(dummy_factory)
    await timer.load_snapshot(db, now=datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ))

    assert any(
        "tracker_reminder_batch_item" in statement and "NOT EXISTS" in statement
        for statement in db.statements
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


def test_fixed_interval_rolls_forward_by_the_configured_multiple():
    now = datetime(2026, 8, 10, 10, 0, tzinfo=VN_TZ)
    candidate = CronTimer._fixed_candidate_date(
        now_vn=now,
        reminder_time=time(8, 0),
        interval_days=3,
        last_scheduled_date=date(2026, 8, 1),
    )

    assert candidate == date(2026, 8, 13)


def test_after_entry_uses_vn_freshness_and_skips_dispatched_dates():
    now = datetime(2026, 8, 10, 7, 30, tzinfo=VN_TZ)
    candidate = CronTimer._after_entry_candidate_date(
        now_vn=now,
        reminder_time=time(8, 0),
        interval_days=3,
        last_entry_date=date(2026, 8, 7),
        dispatched_dates={date(2026, 8, 10)},
    )

    assert candidate == date(2026, 8, 11)


@pytest.mark.anyio
async def test_generic_after_entry_schedule_uses_bounded_aggregate_results(monkeypatch):
    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    tracker_id = UUID("01912345-6789-7000-8000-000000000019")
    tracker = _tracker(
        tracker_id,
        kind="general",
        input_mode="event",
        reminder_time=time(8, 0),
        reminder_mode="after_entry",
        reminder_interval_days=3,
        reminder_action="open_tracker",
    )
    # pending, tracker, subscription, max(entry), all tracker dispatch dates
    db = FakeDB(
        results=[
            [],
            [tracker],
            [],
            [(tracker_id, datetime(2026, 8, 3, 17, 30, tzinfo=UTC))],
            [(tracker_id, date(2026, 8, 6))],
        ]
    )
    timer = CronTimer(dummy_factory)

    await timer.load_snapshot(db, now=datetime(2026, 8, 6, 7, 30, tzinfo=VN_TZ))

    item = next(row[-1] for row in timer._heap if row[-1].kind == ScheduleKind.TRACKER)
    assert item.occurrence_on == date(2026, 8, 7)
    assert item.reminder_action == "open_tracker"
    assert item.last_entry_date == date(2026, 8, 4)
    assert db.executions == 6


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
    # localhost is never a declared prod host, so the fail-closed local guard
    # must not fire for this synthetic URL. Keep the raw env var in sync with
    # the value Settings will actually use.
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/microsched")
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
    # The contract is "DATABASE_URL absent"; keep the developer's real .env out.
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
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


@pytest.mark.anyio
async def test_queue_loaded_receipt_uses_none_for_empty_heap(monkeypatch, caplog):
    """O-01: an empty snapshot emits one parseable literal deadline."""

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    db = FakeDB(results=[[], [], []])
    timer = CronTimer(dummy_factory)
    caplog.set_level(logging.WARNING, logger=cron.__name__)

    await timer.load_snapshot(db, now=datetime(2026, 8, 16, 8, 0, tzinfo=VN_TZ))

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == cron.__name__
        and record.getMessage().startswith("cron_timer_queue_loaded")
    ]
    assert len(messages) == 1
    event_name, *field_tokens = messages[0].split()
    assert event_name == "cron_timer_queue_loaded"
    assert dict(token.split("=", 1) for token in field_tokens) == {
        "reason": "init",
        "tracker_count": "0",
        "subscription_count": "0",
        "lead_days": "3",
        "queue_size": "0",
        "next_due_at": "none",
        "pending_recovered_count": "0",
        "pending_manual_required_count": "0",
        "invalid_tracker_schedule_count": "0",
    }
    assert db.executions == 4


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
    assert snapshot["next_due_at"] is None
    assert snapshot["last_reload_at"] is None
    assert snapshot["last_dispatch_at"] is None
    assert snapshot["consecutive_loop_failures"] == 0
    assert "next_due" not in snapshot
    assert "last_reload" not in snapshot
    assert "last_dispatch" not in snapshot
    assert "loop_failures" not in snapshot
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
async def test_dead_pending_rows_are_receipted_not_dropped(monkeypatch, caplog):
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
    caplog.set_level(logging.WARNING, logger=cron.__name__)
    await timer.load_snapshot(db, now=now)
    assert timer._pending_manual_required == {"expired": 1, "exhausted": 1, "ineligible": 1}
    queued = [it[5] for it in timer._heap]
    for dead_id in (
        UUID("01912345-6789-7000-8000-000000000411"),
        UUID("01912345-6789-7000-8000-000000000412"),
        UUID("01912345-6789-7000-8000-000000000413"),
    ):
        assert all(item.dispatch_id != dead_id for item in queued)
    manual_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == cron.__name__
        and record.getMessage().startswith("cron_timer_pending_manual_required")
    ]
    assert len(manual_messages) == 3
    assert all("occurrence_ref=" in message for message in manual_messages)
    joined = "\n".join(manual_messages)
    assert all(str(pending_row.subject_id) not in joined for pending_row in pending)
    assert all(str(pending_row.id) not in joined for pending_row in pending)


@pytest.mark.anyio
async def test_exhausted_outcome_is_receipted_and_next_day_scheduled(monkeypatch, caplog):
    """F10+F11: EXHAUSTED at dispatch logs a receipt and does not swallow tomorrow."""
    stub = StubDispatcher(DispatchOutcome.EXHAUSTED)
    now = datetime(2026, 8, 6, 7, 0, tzinfo=VN_TZ)
    tracker_id = UUID("01912345-6789-7000-8000-000000000501")
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    timer = CronTimer(FakeFactory(FakeDB(results=[[tracker]])), reminder_dispatcher=stub)
    item = TimerItem(
        due_at=now,
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.TRACKER,
        subject_id=tracker_id,
        reminder_time=time(8, 0),
        retry_count=3,
        is_pending_recovery=True,
    )
    caplog.set_level(logging.WARNING, logger=cron.__name__)
    await timer._process_due_item(item, now=now)
    assert timer._pending_manual_required["exhausted"] == 1
    assert len(stub.calls) == 1
    next_item = timer._heap[0][5]
    assert next_item.occurrence_on == date(2026, 8, 7)
    assert next_item.due_at == datetime(2026, 8, 7, 8, 0, tzinfo=VN_TZ)
    manual_message = next(
        record.getMessage()
        for record in caplog.records
        if record.name == cron.__name__
        and record.getMessage().startswith("cron_timer_pending_manual_required")
    )
    assert str(tracker_id) not in manual_message
    assert "occurrence_ref=" in manual_message


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
    timer = CronTimer(FakeFactory(FakeDB(results=[[(sub, parent)]])), reminder_dispatcher=stub)
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
    timer2 = CronTimer(FakeFactory(FakeDB(results=[[(sub, parent)]])), reminder_dispatcher=stub2)
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
    timer3 = CronTimer(FakeFactory(FakeDB(results=[[(sub, parent)]])), reminder_dispatcher=stub3)
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
    item, now, expected_due, caplog
):
    """011d §1.5: stale non-pending work skips delivery but preserves the future chain."""
    timer = CronTimer(dummy_factory)

    class ExplodingDB:
        async def execute(self, stmt):
            raise AssertionError("grace-skipped item must not touch the database")

    timer.session_factory = FakeFactory(ExplodingDB())
    caplog.set_level(logging.WARNING, logger=cron.__name__)
    await timer._process_due_item(item, now=now)
    assert len(timer._heap) == 1
    next_item = timer._heap[0][5]
    assert next_item.kind == item.kind
    assert next_item.subject_id == item.subject_id
    assert next_item.occurrence_on == expected_due.date()
    assert next_item.due_at == expected_due
    assert next_item.is_pending_recovery is False
    stale_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == cron.__name__ and "cron_timer_stale" in record.getMessage()
    ]
    assert len(stale_messages) == 1
    assert "reason=overdue_item" in stale_messages[0]
    assert f"kind={item.kind.value}" in stale_messages[0]
    assert str(item.subject_id) not in stale_messages[0]
    assert "occurrence_ref=" in stale_messages[0]
    assert f"occurrence_on={item.occurrence_on}" in stale_messages[0]
    assert "payload" not in stale_messages[0]
    assert "endpoint" not in stale_messages[0]


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
async def test_timer_item_exception_log_excludes_exception_text(monkeypatch, caplog):
    """A hostile exception message must never become a timer log payload."""
    timer = CronTimer(FakeFactory(object()))
    item = TimerItem(
        due_at=datetime.now(VN_TZ) - timedelta(minutes=1),
        occurrence_on=date(2026, 8, 6),
        kind=ScheduleKind.TRACKER,
        subject_id=UUID("01912345-6789-7000-8000-000000000802"),
    )

    loaded = False

    async def fake_load_snapshot(db):
        nonlocal loaded
        if not loaded:
            loaded = True
            heapq.heappush(timer._heap, item.heap_tuple())

    async def secret_failure(due_item):
        assert due_item == item
        raise RuntimeError("push endpoint secret-like-value")

    monkeypatch.setattr(timer, "load_snapshot", fake_load_snapshot)
    monkeypatch.setattr(timer, "_process_due_item", secret_failure)
    caplog.set_level(logging.ERROR, logger=cron.__name__)

    task = asyncio.create_task(timer.run())
    await asyncio.sleep(0.05)
    await timer.stop()
    await asyncio.wait_for(task, timeout=2)

    timer_messages = [
        record.getMessage() for record in caplog.records if record.name == cron.__name__
    ]
    assert any("error_type=RuntimeError" in message for message in timer_messages)
    assert all("secret-like-value" not in message for message in timer_messages)
    assert all(str(item.subject_id) not in message for message in timer_messages)


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
    assert db.executions == 4, "exactly the one startup snapshot, no polling"
    timer.request_reload("test")
    await asyncio.sleep(0.1)
    assert db.executions == 8, "reload after the commit marker"
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
    assert timer.status == "owner"
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
    assert timer.status == "stopped"


@pytest.mark.anyio
async def test_stop_interrupts_long_snapshot_retry_backoff(monkeypatch):
    """Shutdown must not wait for the 30/120/600-second recovery sleeps."""
    monkeypatch.setattr(cron, "SNAPSHOT_RETRY_BACKOFF_SECONDS", (3600, 3600, 3600))
    timer = CronTimer(FakeFactory(object()))
    attempted = asyncio.Event()

    async def broken_load_snapshot(db):
        attempted.set()
        raise RuntimeError("synthetic snapshot failure")

    monkeypatch.setattr(timer, "load_snapshot", broken_load_snapshot)
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(attempted.wait(), timeout=1)

    await timer.stop()
    await asyncio.wait_for(task, timeout=0.25)
    assert task.done()


@pytest.mark.anyio
async def test_stop_interrupts_long_top_level_failure_backoff(monkeypatch):
    """Unexpected-loop backoff is bounded during runtime and interruptible on shutdown."""
    monkeypatch.setattr(cron, "LOOP_FAILURE_BACKOFF_SECONDS", 3600)
    timer = CronTimer(FakeFactory(object()))
    loop_failed = asyncio.Event()

    async def empty_snapshot(db):
        return None

    class BrokenReloadEvent:
        def is_set(self):
            return False

        def set(self):
            return None

        async def wait(self):
            loop_failed.set()
            raise RuntimeError("synthetic top-level failure")

    monkeypatch.setattr(timer, "load_snapshot", empty_snapshot)
    timer.reload_event = BrokenReloadEvent()
    task = asyncio.create_task(timer.run())
    await asyncio.wait_for(loop_failed.wait(), timeout=1)
    while timer._loop_failures != 1:
        await asyncio.sleep(0)
    assert timer.status == "owner"

    await timer.stop()
    await asyncio.wait_for(task, timeout=0.25)
    assert task.done()


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

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "true")
    get_settings.cache_clear()
    sink_context = deps.get_cron_reload_sink()
    token = sink_context.set(FakeSink())
    try:
        session = FakeSession()
        monkeypatch.setattr(deps, "get_sessionmaker", lambda: FakeFactory(session))

        async def consume_ok():
            async for _db in deps.get_session():
                _db.info[deps.CRON_TIMER_RELOAD_INFO_KEY] = "subscription:renew"

        await consume_ok()
        assert session.committed is True
        assert calls == ["subscription:renew"]
        assert deps.CRON_TIMER_RELOAD_INFO_KEY not in session.info

        # A commit failure after the request wrote its marker must roll back and
        # must NOT reach the reload sink — the DB never observed the change.
        calls.clear()
        session2 = FakeSession(fail_commit=True)
        monkeypatch.setattr(deps, "get_sessionmaker", lambda: FakeFactory(session2))

        try:
            async for _db in deps.get_session():
                _db.info[deps.CRON_TIMER_RELOAD_INFO_KEY] = "subscription:renew"
        except RuntimeError:
            pass

        assert session2.rolled_back is True
        assert calls == [], "rollback must never reach the reload sink"
        assert deps.CRON_TIMER_RELOAD_INFO_KEY not in session2.info
    finally:
        sink_context.reset(token)
        get_settings.cache_clear()


@pytest.mark.anyio
async def test_cron_timer_run_emits_warning_startup_and_safe_queue_receipts(monkeypatch, caplog):
    """011e: the real startup path emits only the locked, safe receipts."""

    fixed_now = datetime(2026, 8, 24, 6, 0, tzinfo=VN_TZ)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    async def fake_lead(db):
        return 3

    monkeypatch.setattr(cron, "datetime", FixedDateTime)
    monkeypatch.setattr(cron, "expiry_lead_days", fake_lead)
    tracker_id = UUID("01912345-6789-7000-8000-000000000901")
    parent_id = UUID("01912345-6789-7000-8000-000000000902")
    sub_id = UUID("01912345-6789-7000-8000-000000000903")
    sentinel_tracker_name = "enc:v1:safe-tracker-name-sentinel"
    sentinel_reminder_text = "safe-reminder-text-sentinel"
    sentinel_subscription_name = "enc:v1:safe-subscription-name-sentinel"
    sentinel_subscription_note = "safe-subscription-note-sentinel"

    tracker = _tracker(tracker_id, reminder_time=time(23, 59))
    tracker.name = sentinel_tracker_name
    tracker.reminder_text = sentinel_reminder_text
    sub = _subscription(
        sub_id,
        parent_id,
        expires_on=fixed_now.date() + timedelta(days=2),
    )
    sub.name = sentinel_subscription_name
    sub.note_md = sentinel_subscription_note
    parent = _tracker(parent_id, kind="finance", input_mode="money")
    db = FakeDB(results=[[], [tracker], [(sub, parent)]])
    timer = CronTimer(FakeFactory(db))

    caplog.set_level(logging.WARNING, logger=cron.__name__)
    task = asyncio.create_task(timer.run())
    try:
        for _ in range(100):
            if any(
                record.name == cron.__name__ and "cron_timer_queue_loaded" in record.getMessage()
                for record in caplog.records
            ):
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("CronTimer.run() did not finish its startup snapshot")
    finally:
        await timer.stop()
        await asyncio.wait_for(task, timeout=1)

    timer_records = [record for record in caplog.records if record.name == cron.__name__]
    ownership_records = [
        record
        for record in timer_records
        if record.getMessage().startswith("cron_timer_ownership_transition")
    ]
    queue_records = [
        record
        for record in timer_records
        if record.getMessage().startswith("cron_timer_queue_loaded")
    ]

    assert len(ownership_records) == 2
    assert [record.levelno for record in ownership_records] == [logging.WARNING, logging.WARNING]
    assert [record.getMessage() for record in ownership_records] == [
        "cron_timer_ownership_transition state=starting lock_ref=scheduler_035_v1 commit=unknown",
        "cron_timer_ownership_transition state=owner lock_ref=scheduler_035_v1 commit=unknown",
    ]

    assert len(queue_records) == 1
    assert queue_records[0].levelno == logging.WARNING
    queue_message = queue_records[0].getMessage()
    event_name, *field_tokens = queue_message.split()
    queue_fields = dict(token.split("=", maxsplit=1) for token in field_tokens)
    assert event_name == "cron_timer_queue_loaded"
    assert queue_fields == {
        "reason": "startup",
        "tracker_count": "1",
        "subscription_count": "1",
        "lead_days": "3",
        "queue_size": "2",
        "next_due_at": "2026-08-24T07:00:00+07:00",
        "pending_recovered_count": "0",
        "pending_manual_required_count": "0",
        "invalid_tracker_schedule_count": "0",
    }

    for sentinel in (
        sentinel_tracker_name,
        sentinel_reminder_text,
        sentinel_subscription_name,
        sentinel_subscription_note,
    ):
        assert sentinel not in queue_message


@pytest.mark.anyio
async def test_cron_timer_dispatch_receipt_ordering(caplog):
    """O-02/O-03: one invocation emits one safe, ordered pair."""
    tracker_id = UUID("01912345-6789-7000-8000-000000000a01")
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    tracker.name = "enc:v1:receipt-name-sentinel"
    tracker.reminder_text = "receipt-text-sentinel"
    due_at = datetime(2026, 8, 16, 8, 0, tzinfo=VN_TZ)
    stub = StubDispatcher(DispatchOutcome.SENT, attempt_count=2)
    timer = CronTimer(FakeFactory(FakeDB(results=[[tracker]])), reminder_dispatcher=stub)
    item = TimerItem(
        due_at=due_at,
        occurrence_on=due_at.date(),
        kind=ScheduleKind.TRACKER,
        subject_id=tracker_id,
        reminder_time=time(8, 0),
    )
    caplog.set_level(logging.WARNING, logger=cron.__name__)

    await timer._process_due_item(item, now=due_at)

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == cron.__name__ and "cron_timer_dispatch_" in record.getMessage()
    ]
    assert len(messages) == 2
    joined = "\n".join(messages)
    for forbidden in (
        str(tracker_id),
        tracker.name,
        tracker.reminder_text,
        "https://receipt-endpoint.invalid/sentinel",
        "p256dh-receipt-sentinel",
        "cookie-receipt-sentinel",
        "token-receipt-sentinel",
        "credential-receipt-sentinel",
        "provider-response-receipt-sentinel",
    ):
        assert forbidden not in joined

    started_tokens = messages[0].split()
    finished_tokens = messages[1].split()
    assert started_tokens[0] == "cron_timer_dispatch_started"
    assert finished_tokens[0] == "cron_timer_dispatch_finished"
    started = dict(token.split("=", 1) for token in started_tokens[1:])
    finished = dict(token.split("=", 1) for token in finished_tokens[1:])
    assert started == {
        "kind": "tracker",
        "due_at": due_at.isoformat(),
        "occurrence_on": due_at.date().isoformat(),
        "attempt_count": "2",
        "occurrence_ref": started["occurrence_ref"],
    }
    assert len(started["occurrence_ref"]) == 16
    assert all(character in "0123456789abcdef" for character in started["occurrence_ref"])
    assert finished == {
        "kind": "tracker",
        "due_at": due_at.isoformat(),
        "occurrence_on": due_at.date().isoformat(),
        "outcome": "sent",
        "attempt_count": "2",
        "occurrence_ref": started["occurrence_ref"],
    }


@pytest.mark.anyio
async def test_reload_within_grace_terminal_reentry_keeps_same_occurrence_ref(caplog):
    """A terminal reload may repeat the safe pair without another network attempt."""
    tracker_id = UUID("01912345-6789-7000-8000-000000000a02")
    tracker = _tracker(tracker_id, reminder_time=time(8, 0))
    due_at = datetime(2026, 8, 16, 8, 0, tzinfo=VN_TZ)
    stub = StubDispatcher(DispatchOutcome.SENT, attempt_count=1)
    timer = CronTimer(FakeFactory(FakeDB(results=[[tracker], [tracker]])), reminder_dispatcher=stub)
    item = TimerItem(
        due_at=due_at,
        occurrence_on=due_at.date(),
        kind=ScheduleKind.TRACKER,
        subject_id=tracker_id,
        reminder_time=time(8, 0),
    )
    caplog.set_level(logging.WARNING, logger=cron.__name__)

    await timer._process_due_item(item, now=due_at)
    await timer._process_due_item(item, now=due_at)

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == cron.__name__ and "cron_timer_dispatch_" in record.getMessage()
    ]
    assert [message.split()[0] for message in messages] == [
        "cron_timer_dispatch_started",
        "cron_timer_dispatch_finished",
        "cron_timer_dispatch_started",
        "cron_timer_dispatch_finished",
    ]
    refs = [
        dict(token.split("=", 1) for token in message.split()[1:])["occurrence_ref"]
        for message in messages
    ]
    assert len(set(refs)) == 1
    assert len(stub.calls) == 2
