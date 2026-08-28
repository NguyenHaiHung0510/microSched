"""PostgreSQL receipts for the 035A session-level scheduler ownership fence."""

import asyncio
import contextlib
import heapq
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4, uuid7

import asyncpg
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.cron_timer as cron
from app.core.cron_timer import (
    SCHEDULER_ADVISORY_LOCK_KEY,
    SCHEDULER_ADVISORY_LOCK_NAMESPACE,
    VN_TZ,
    CronTimer,
    CronTimerOwnershipLost,
    ScheduleKind,
    TimerItem,
)
from app.core.database_urls import async_postgres_url
from app.domain.models import AuthSession
from app.domain.push import ProviderWorkTracker, PushResult
from app.domain.reminder import confirm_reminder_dispatch
from app.domain.tracker import EntryCreate, EntryUpdate, TrackerStore
from scripts.scheduler_ownership_receipt import collect_receipt


async def _wait_for_state(timer: CronTimer, expected: str) -> None:
    for _ in range(200):
        if timer.status == expected:
            return
        await asyncio.sleep(0.01)
    pytest.fail(f"timer did not reach state {expected}")


def _auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        id=uuid4(),
        token_hash=f"scheduler-ownership-test-{uuid4()}",
        user_email="owner@test.local",
        expires_at=now + timedelta(hours=1),
    )


async def _lock_factory(pg_dsn: str) -> asyncpg.Connection:
    return await asyncpg.connect(pg_dsn)


async def _delete_tracker_fixture(
    connection: asyncpg.Connection,
    tracker_id: UUID,
) -> None:
    """Remove one test-only tracker in FK order."""
    await connection.execute(
        "DELETE FROM microsched.reminder_dispatch WHERE subject_id = $1", tracker_id
    )
    await connection.execute("DELETE FROM microsched.entry WHERE tracker_id = $1", tracker_id)
    await connection.execute("DELETE FROM microsched.tracker WHERE id = $1", tracker_id)


async def _insert_after_entry_tracker(connection: asyncpg.Connection, tracker_id: UUID) -> None:
    """Insert an event tracker whose freshness every entry writer can affect."""
    await connection.execute(
        """
        INSERT INTO microsched.tracker
            (id, name, kind, direction, input_mode, reminder_time,
             reminder_mode, reminder_interval_days, reminder_action)
        VALUES ($1, 'enc:v1:ownership-freshness', 'general', 'out', 'event', '08:00',
                'after_entry', 1, 'confirm_event')
        """,
        tracker_id,
    )


@pytest.mark.pg
def test_pg_receipt_counts_only_current_database_exclusive_exact_lock(pg_dsn: str) -> None:
    """The one-shot receipt excludes shared, wrong-key, and other-DB locks."""

    async def scenario() -> None:
        other_database = f"receipt_scope_{uuid4().hex}"
        admin = await asyncpg.connect(pg_dsn)
        shared = None
        wrong_key = None
        other_database_connection = None
        exact = None
        try:
            await admin.execute(f'CREATE DATABASE "{other_database}"')
            shared = await asyncpg.connect(pg_dsn)
            await shared.execute(
                "SELECT pg_advisory_lock_shared($1::integer, $2::integer)",
                SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                SCHEDULER_ADVISORY_LOCK_KEY,
            )
            receipt = await collect_receipt(
                pg_dsn,
                observed_at=datetime.now(UTC),
                commit="test",
            )
            assert receipt["holder_count"] == 0
            await shared.close()
            shared = None

            wrong_key = await asyncpg.connect(pg_dsn)
            await wrong_key.execute(
                "SELECT pg_advisory_lock($1::integer, $2::integer)",
                SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                SCHEDULER_ADVISORY_LOCK_KEY + 1,
            )
            receipt = await collect_receipt(
                pg_dsn,
                observed_at=datetime.now(UTC),
                commit="test",
            )
            assert receipt["holder_count"] == 0

            other_database_connection = await asyncpg.connect(pg_dsn, database=other_database)
            await other_database_connection.execute(
                "SELECT pg_advisory_lock($1::integer, $2::integer)",
                SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                SCHEDULER_ADVISORY_LOCK_KEY,
            )
            receipt = await collect_receipt(
                pg_dsn,
                observed_at=datetime.now(UTC),
                commit="test",
            )
            assert receipt["holder_count"] == 0

            exact = await asyncpg.connect(pg_dsn)
            await exact.execute(
                "SELECT pg_advisory_lock($1::integer, $2::integer)",
                SCHEDULER_ADVISORY_LOCK_NAMESPACE,
                SCHEDULER_ADVISORY_LOCK_KEY,
            )
            receipt = await collect_receipt(
                pg_dsn,
                observed_at=datetime.now(UTC),
                commit="test",
            )
            assert receipt["holder_count"] == 1
        finally:
            for connection in (shared, wrong_key, other_database_connection, exact):
                if connection is not None:
                    await connection.close()
            await admin.execute(f'DROP DATABASE IF EXISTS "{other_database}" WITH (FORCE)')
            await admin.close()

    asyncio.run(scenario())


@pytest.mark.pg
def test_pg_only_one_owner_receipt_and_handoff(pg_dsn: str, monkeypatch) -> None:
    """Two real processes serialize on pg_advisory_lock; standby loads nothing."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        first_loaded = asyncio.Event()
        second_loaded = asyncio.Event()
        first_calls = 0
        second_calls = 0

        async def first_snapshot(db) -> None:
            nonlocal first_calls
            first_calls += 1
            first_loaded.set()

        async def second_snapshot(db) -> None:
            nonlocal second_calls
            second_calls += 1
            second_loaded.set()

        first = CronTimer(maker, lock_connection_factory=lambda: _lock_factory(pg_dsn))
        second = CronTimer(maker, lock_connection_factory=lambda: _lock_factory(pg_dsn))
        first.load_snapshot = first_snapshot
        second.load_snapshot = second_snapshot
        first_task = asyncio.create_task(first.run())
        second_task = asyncio.create_task(second.run())
        try:
            await asyncio.wait_for(first_loaded.wait(), timeout=2)
            await _wait_for_state(second, "standby")
            assert first_calls == 1
            assert second_calls == 0

            first_receipt = await collect_receipt(
                pg_dsn, observed_at=datetime.now(UTC), commit="test"
            )
            assert first_receipt["holder_count"] == 1

            await first.stop()
            await asyncio.wait_for(first_task, timeout=2)
            await asyncio.wait_for(second_loaded.wait(), timeout=2)
            await _wait_for_state(second, "owner")

            handoff_receipt = await collect_receipt(
                pg_dsn, observed_at=datetime.now(UTC), commit="test"
            )
            assert handoff_receipt["holder_count"] == 1
            assert second_calls == 1
        finally:
            await first.stop()
            await second.stop()
            await asyncio.gather(first_task, second_task, return_exceptions=True)
            await engine.dispose()

    monkeypatch.setattr(cron, "OWNERSHIP_ACQUIRE_BACKOFF_SECONDS", (0.01,))
    asyncio.run(scenario())


@pytest.mark.pg
def test_pg_connection_termination_preempts_snapshot_and_dispatch(pg_dsn: str) -> None:
    """A PostgreSQL-terminated lock connection cancels blocked scheduler phases promptly."""

    async def run_phase(phase: str) -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        connections: list[asyncpg.Connection] = []
        terminator = await asyncpg.connect(pg_dsn)
        started = asyncio.Event()
        cancelled = asyncio.Event()
        dispatch_tracker_id: UUID | None = None

        async def lock_factory() -> asyncpg.Connection:
            connection = await asyncpg.connect(pg_dsn)
            connections.append(connection)
            return connection

        if phase == "snapshot":
            timer = CronTimer(maker, lock_connection_factory=lock_factory)

            async def blocked_snapshot(db) -> None:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

            timer.load_snapshot = blocked_snapshot
        else:
            dispatch_tracker_id = uuid4()
            await _insert_after_entry_tracker(terminator, dispatch_tracker_id)

            class BlockingProviderDispatcher:
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
                    assert ownership_guard is not None
                    await ownership_guard()
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        cancelled.set()
                        raise

            timer = CronTimer(
                maker,
                reminder_dispatcher=BlockingProviderDispatcher(),
                lock_connection_factory=lock_factory,
            )

            async def snapshot(db) -> None:
                heapq.heappush(
                    timer._heap,
                    TimerItem(
                        due_at=datetime.now(VN_TZ) - timedelta(seconds=1),
                        occurrence_on=date.today(),
                        kind=ScheduleKind.TRACKER,
                        subject_id=dispatch_tracker_id,
                        reminder_time=time(8, 0),
                        reminder_mode="after_entry",
                        reminder_interval_days=1,
                        reminder_action="confirm_event",
                    ).heap_tuple(),
                )

            timer.load_snapshot = snapshot

        task = asyncio.create_task(timer.run())
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            assert len(connections) == 1
            lock_pid = await connections[0].fetchval("SELECT pg_backend_pid()")
            assert await terminator.fetchval("SELECT pg_terminate_backend($1)", lock_pid)
            with pytest.raises(CronTimerOwnershipLost):
                await asyncio.wait_for(task, timeout=2)
            assert cancelled.is_set()
        finally:
            await timer.stop()
            await asyncio.gather(task, return_exceptions=True)
            if dispatch_tracker_id is not None:
                await _delete_tracker_fixture(terminator, dispatch_tracker_id)
            await terminator.close()
            await engine.dispose()

    asyncio.run(run_phase("snapshot"))
    asyncio.run(run_phase("dispatch"))


@pytest.mark.pg
def test_pg_graceful_stop_retains_lock_for_real_uncancellable_provider_worker(pg_dsn: str) -> None:
    """A real thread-backed provider worker completes before the owner unlocks PG."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        release_worker = asyncio.Event()
        worker_started = asyncio.Event()
        worker_finished = asyncio.Event()

        class ThreadBackedDispatcher:
            def __init__(self) -> None:
                self.provider_work = ProviderWorkTracker()

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
                assert ownership_guard is not None
                await ownership_guard()
                loop = asyncio.get_running_loop()

                def blocking_provider_call() -> None:
                    loop.call_soon_threadsafe(worker_started.set)
                    while not release_worker.is_set():
                        import time as stdlib_time

                        stdlib_time.sleep(0.005)
                    loop.call_soon_threadsafe(worker_finished.set)

                worker = asyncio.create_task(asyncio.to_thread(blocking_provider_call))
                self.provider_work.track(worker)
                await asyncio.shield(worker)
                return PushResult.SENT

        async def snapshot(db) -> None:
            heapq.heappush(
                timer._heap,
                TimerItem(
                    due_at=datetime.now(VN_TZ) - timedelta(seconds=1),
                    occurrence_on=date.today(),
                    kind=ScheduleKind.SUBSCRIPTION,
                    subject_id=uuid4(),
                ).heap_tuple(),
            )

        dispatcher = ThreadBackedDispatcher()
        timer = CronTimer(
            maker,
            reminder_dispatcher=dispatcher,
            lock_connection_factory=lambda: _lock_factory(pg_dsn),
        )
        timer.load_snapshot = snapshot
        timer._process_due_item = lambda item: dispatcher.dispatch_item(
            None,
            "tracker",
            item.subject_id,
            item.occurrence_on,
            lambda _dispatch_id: {},
            ownership_guard=timer._guard_provider_attempt,
        )
        task = asyncio.create_task(timer.run())
        try:
            await asyncio.wait_for(worker_started.wait(), timeout=2)
            stop_task = asyncio.create_task(timer.stop())
            await asyncio.sleep(0.05)
            receipt = await collect_receipt(
                pg_dsn,
                observed_at=datetime.now(UTC),
                commit="test",
            )
            assert receipt["holder_count"] == 1
            assert not stop_task.done()
            release_worker.set()
            await asyncio.wait_for(worker_finished.wait(), timeout=2)
            await asyncio.wait_for(stop_task, timeout=2)
            final_receipt = await collect_receipt(
                pg_dsn,
                observed_at=datetime.now(UTC),
                commit="test",
            )
            assert final_receipt["holder_count"] == 0
        finally:
            release_worker.set()
            await timer.stop()
            await asyncio.gather(task, return_exceptions=True)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_pg_future_batch_antijoin_excludes_linked_pending_dispatch(pg_dsn: str) -> None:
    """035A sees a future item table and recovers only legacy-unlinked pending rows."""

    async def scenario() -> None:
        linked_tracker_id = uuid4()
        unlinked_tracker_id = uuid4()
        linked_dispatch_id = uuid4()
        unlinked_dispatch_id = uuid4()
        connection = await asyncpg.connect(pg_dsn)
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await connection.execute(
                "CREATE TABLE microsched.tracker_reminder_batch_item (dispatch_id uuid PRIMARY KEY)"
            )
            for tracker_id in (linked_tracker_id, unlinked_tracker_id):
                await connection.execute(
                    """
                    INSERT INTO microsched.tracker
                        (id, name, kind, direction, input_mode, reminder_time,
                         reminder_mode, reminder_interval_days, reminder_action)
                    VALUES ($1, 'enc:v1:ownership-test', 'general', 'out', 'event', '08:00',
                            'fixed', 1, 'open_tracker')
                    """,
                    tracker_id,
                )
            for dispatch_id, tracker_id in (
                (linked_dispatch_id, linked_tracker_id),
                (unlinked_dispatch_id, unlinked_tracker_id),
            ):
                await connection.execute(
                    """
                    INSERT INTO microsched.reminder_dispatch
                        (id, subject_type, subject_id, dispatched_on, status, attempt_count,
                         last_attempt_at, created_at)
                    VALUES ($1, 'tracker', $2, CURRENT_DATE, 'pending', 1, NOW(), NOW())
                    """,
                    dispatch_id,
                    tracker_id,
                )
            await connection.execute(
                "INSERT INTO microsched.tracker_reminder_batch_item (dispatch_id) VALUES ($1)",
                linked_dispatch_id,
            )

            timer = CronTimer(maker)
            async with maker() as db:
                await timer.load_snapshot(db, now=datetime.now(VN_TZ))
            recovered_dispatches = {
                item.dispatch_id for *_ignored, item in timer._heap if item.dispatch_id is not None
            }
            assert unlinked_dispatch_id in recovered_dispatches
            assert linked_dispatch_id not in recovered_dispatches
        finally:
            await connection.execute("DROP TABLE IF EXISTS microsched.tracker_reminder_batch_item")
            await connection.execute(
                "DELETE FROM microsched.reminder_dispatch WHERE id = ANY($1::uuid[])",
                [linked_dispatch_id, unlinked_dispatch_id],
            )
            await connection.execute(
                "DELETE FROM microsched.tracker WHERE id = ANY($1::uuid[])",
                [linked_tracker_id, unlinked_tracker_id],
            )
            await connection.close()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_pg_future_terminal_confirmation_statuses_fail_closed(pg_dsn: str) -> None:
    """A 035A binary rejects simulated post-0012 terminal links without an Entry."""

    async def scenario() -> None:
        tracker_id = uuid4()
        dispatch_id = uuid4()
        connection = await asyncpg.connect(pg_dsn)
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await connection.execute(
                "ALTER TABLE microsched.reminder_dispatch "
                "DROP CONSTRAINT ck_reminder_dispatch_status"
            )
            await connection.execute(
                """
                ALTER TABLE microsched.reminder_dispatch
                ADD CONSTRAINT ck_reminder_dispatch_status
                CHECK (status IN ('pending', 'sent', 'no_device', 'cancelled', 'exhausted'))
                """
            )
            await connection.execute(
                """
                INSERT INTO microsched.tracker
                    (id, name, kind, direction, input_mode, reminder_time,
                     reminder_mode, reminder_interval_days, reminder_action)
                VALUES ($1, 'enc:v1:ownership-confirm', 'general', 'out', 'event', '08:00',
                        'fixed', 1, 'confirm_event')
                """,
                tracker_id,
            )
            for status_value in ("cancelled", "exhausted"):
                current_dispatch_id = dispatch_id if status_value == "cancelled" else uuid4()
                await connection.execute(
                    """
                    INSERT INTO microsched.reminder_dispatch
                        (id, subject_type, subject_id, dispatched_on, status, attempt_count,
                         created_at)
                    VALUES ($1, 'tracker', $2, CURRENT_DATE + $3::integer, $4, 0, NOW())
                    """,
                    current_dispatch_id,
                    tracker_id,
                    0 if status_value == "cancelled" else 1,
                    status_value,
                )
                async with maker() as db:
                    with pytest.raises(HTTPException) as error:
                        await confirm_reminder_dispatch(
                            db,
                            current_dispatch_id,
                            UUID("01912345-6789-7000-8000-000000000021"),
                            datetime.now(UTC),
                            _auth(),
                        )
                    assert error.value.status_code == 409
                    await db.rollback()
        finally:
            await connection.execute(
                "DELETE FROM microsched.reminder_dispatch WHERE subject_id = $1", tracker_id
            )
            await connection.execute("DELETE FROM microsched.tracker WHERE id = $1", tracker_id)
            await connection.execute(
                "ALTER TABLE microsched.reminder_dispatch "
                "DROP CONSTRAINT ck_reminder_dispatch_status"
            )
            await connection.execute(
                """
                ALTER TABLE microsched.reminder_dispatch
                ADD CONSTRAINT ck_reminder_dispatch_status
                CHECK (status IN ('pending', 'sent', 'no_device'))
                """
            )
            await connection.close()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_pg_confirmation_matrix_pre_and_post_future_schema(pg_dsn: str) -> None:
    """035A keeps pre-0012 eligibility and fails closed for all later terminals."""

    async def scenario() -> None:
        tracker_id = uuid4()
        connection = await asyncpg.connect(pg_dsn)
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        check_replaced = False
        try:
            await _insert_after_entry_tracker(connection, tracker_id)

            async def insert_dispatch(status_value: str, day_offset: int) -> UUID:
                dispatch_id = uuid4()
                await connection.execute(
                    """
                    INSERT INTO microsched.reminder_dispatch
                        (id, subject_type, subject_id, dispatched_on, status,
                         attempt_count, created_at)
                    VALUES ($1, 'tracker', $2, CURRENT_DATE + $3::integer, $4, 0, NOW())
                    """,
                    dispatch_id,
                    tracker_id,
                    day_offset,
                    status_value,
                )
                return dispatch_id

            async def confirm(dispatch_id: UUID, entry_id: UUID):
                async with maker() as db:
                    return await confirm_reminder_dispatch(
                        db,
                        dispatch_id,
                        entry_id,
                        datetime.now(UTC),
                        _auth(),
                    )

            # The current 0011 schema can represent pending/sent/no_device.
            for day_offset, status_value in enumerate(("pending", "sent"), start=1):
                dispatch_id = await insert_dispatch(status_value, day_offset)
                first_entry_id = uuid7()
                entry, created = await confirm(dispatch_id, first_entry_id)
                assert created is True
                assert entry.id == first_entry_id
                retry_entry, retry_created = await confirm(dispatch_id, uuid7())
                assert retry_created is False
                assert retry_entry.id == first_entry_id
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM microsched.entry WHERE id = $1", first_entry_id
                    )
                ) == 1

            no_device_dispatch_id = await insert_dispatch("no_device", 3)
            entry_count_before = await connection.fetchval(
                "SELECT count(*) FROM microsched.entry WHERE tracker_id = $1", tracker_id
            )
            with pytest.raises(HTTPException) as no_device_error:
                await confirm(no_device_dispatch_id, uuid7())
            assert no_device_error.value.status_code == 409
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM microsched.entry WHERE tracker_id = $1", tracker_id
                )
            ) == entry_count_before

            # Simulate only the post-0012 status expansion locally; 035A does
            # not ship that migration, but rollback must still deny its rows.
            await connection.execute(
                "ALTER TABLE microsched.reminder_dispatch "
                "DROP CONSTRAINT ck_reminder_dispatch_status"
            )
            await connection.execute(
                """
                ALTER TABLE microsched.reminder_dispatch
                ADD CONSTRAINT ck_reminder_dispatch_status
                CHECK (
                    status IN (
                        'pending', 'sent', 'no_device', 'cancelled', 'exhausted', 'future_terminal'
                    )
                )
                """
            )
            check_replaced = True

            for day_offset, status_value in enumerate(
                ("cancelled", "exhausted", "future_terminal"),
                start=4,
            ):
                dispatch_id = await insert_dispatch(status_value, day_offset)
                entry_count_before = await connection.fetchval(
                    "SELECT count(*) FROM microsched.entry WHERE tracker_id = $1", tracker_id
                )
                with pytest.raises(HTTPException) as terminal_error:
                    await confirm(dispatch_id, uuid7())
                assert terminal_error.value.status_code == 409
                assert (
                    await connection.fetchval(
                        "SELECT count(*) FROM microsched.entry WHERE tracker_id = $1", tracker_id
                    )
                ) == entry_count_before
        finally:
            await _delete_tracker_fixture(connection, tracker_id)
            if check_replaced:
                await connection.execute(
                    "ALTER TABLE microsched.reminder_dispatch "
                    "DROP CONSTRAINT ck_reminder_dispatch_status"
                )
                await connection.execute(
                    """
                    ALTER TABLE microsched.reminder_dispatch
                    ADD CONSTRAINT ck_reminder_dispatch_status
                    CHECK (status IN ('pending', 'sent', 'no_device'))
                    """
                )
            await connection.close()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_pg_confirmation_and_after_entry_writers_take_tracker_before_children(pg_dsn: str) -> None:
    """035A's ordered confirmation and all freshness writers avoid tracker-child deadlocks."""

    async def scenario() -> None:
        tracker_id = uuid4()
        dispatch_id = uuid4()
        entry_id = uuid4()
        connection = await asyncpg.connect(pg_dsn)
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _insert_after_entry_tracker(connection, tracker_id)
            await connection.execute(
                """
                INSERT INTO microsched.entry (id, tracker_id, occurred_at)
                VALUES ($1, $2, NOW() - INTERVAL '2 days')
                """,
                entry_id,
                tracker_id,
            )
            await connection.execute(
                """
                INSERT INTO microsched.reminder_dispatch
                    (id, subject_type, subject_id, dispatched_on, status, attempt_count, created_at)
                VALUES ($1, 'tracker', $2, CURRENT_DATE, 'pending', 0, NOW())
                """,
                dispatch_id,
                tracker_id,
            )

            auth = _auth()

            # A pre-send transaction owns tracker first.  The real confirmation
            # must wait there, leaving dispatch unlocked for the pre-send
            # transaction; the old dispatch -> tracker order would deadlock.
            presend = await asyncpg.connect(pg_dsn)
            confirmation_task = None
            try:
                await presend.execute("BEGIN")
                await presend.fetchrow(
                    "SELECT id FROM microsched.tracker WHERE id = $1 FOR UPDATE", tracker_id
                )
                async with maker() as db:
                    confirmation_task = asyncio.create_task(
                        confirm_reminder_dispatch(
                            db,
                            dispatch_id,
                            uuid7(),
                            datetime.now(UTC),
                            auth,
                        )
                    )
                    await asyncio.sleep(0.05)
                    assert not confirmation_task.done()
                    assert await asyncio.wait_for(
                        presend.fetchrow(
                            "SELECT id FROM microsched.reminder_dispatch WHERE id = $1 FOR UPDATE",
                            dispatch_id,
                        ),
                        timeout=2,
                    )
                    await presend.execute("COMMIT")
                    confirmed, was_created = await asyncio.wait_for(confirmation_task, timeout=2)
                    assert was_created is True
                    assert confirmed.id is not None
            finally:
                if confirmation_task is not None and not confirmation_task.done():
                    confirmation_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await confirmation_task
                with contextlib.suppress(Exception):
                    await presend.execute("ROLLBACK")
                await presend.close()

            store = TrackerStore()

            async def assert_writer_waits_for_tracker(
                writer,
                *,
                entry_id_to_probe: UUID | None = None,
            ):
                holder = await asyncpg.connect(pg_dsn)
                probe = await asyncpg.connect(pg_dsn)
                writer_task = None
                try:
                    await holder.execute("BEGIN")
                    await holder.fetchrow(
                        "SELECT id FROM microsched.tracker WHERE id = $1 FOR UPDATE", tracker_id
                    )
                    writer_task = asyncio.create_task(writer())
                    await asyncio.sleep(0.05)
                    assert not writer_task.done()
                    if entry_id_to_probe is not None:
                        await probe.execute("BEGIN")
                        assert await probe.fetchrow(
                            "SELECT id FROM microsched.entry WHERE id = $1 FOR UPDATE NOWAIT",
                            entry_id_to_probe,
                        )
                        await probe.execute("ROLLBACK")
                    await holder.execute("COMMIT")
                    return await asyncio.wait_for(writer_task, timeout=2)
                finally:
                    if writer_task is not None and not writer_task.done():
                        writer_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await writer_task
                    with contextlib.suppress(Exception):
                        await holder.execute("ROLLBACK")
                    with contextlib.suppress(Exception):
                        await probe.execute("ROLLBACK")
                    await holder.close()
                    await probe.close()

            async def create_writer():
                async with maker() as db:
                    result = await store.create_entry(
                        db,
                        auth,
                        EntryCreate(tracker_id=tracker_id, occurred_at=datetime.now(UTC)),
                    )
                    await db.commit()
                    return result

            created_id, created = await assert_writer_waits_for_tracker(create_writer)
            assert created is True

            async def update_writer():
                async with maker() as db:
                    result = await store.update_entry(
                        db,
                        auth,
                        created_id,
                        EntryUpdate(occurred_at=datetime.now(UTC) - timedelta(hours=1)),
                    )
                    await db.commit()
                    return result

            assert (
                await assert_writer_waits_for_tracker(
                    update_writer,
                    entry_id_to_probe=created_id,
                )
                is not None
            )

            async def soft_delete_writer():
                async with maker() as db:
                    result = await store.soft_delete_entry(db, auth, created_id)
                    await db.commit()
                    return result

            assert (
                await assert_writer_waits_for_tracker(
                    soft_delete_writer,
                    entry_id_to_probe=created_id,
                )
                is True
            )

            async def restore_writer():
                async with maker() as db:
                    result = await store.restore_entry(db, auth, created_id)
                    await db.commit()
                    return result

            assert (
                await assert_writer_waits_for_tracker(
                    restore_writer,
                    entry_id_to_probe=created_id,
                )
                is not None
            )
        finally:
            await _delete_tracker_fixture(connection, tracker_id)
            await connection.close()
            await engine.dispose()

    asyncio.run(scenario())
