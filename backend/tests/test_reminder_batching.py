"""Fast contracts for tracker reminder batching and lock-screen privacy."""

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.cron_timer import VN_TZ, CronTimer
from app.core.database_urls import async_postgres_url
from app.domain import reminder as reminder_module
from app.domain.models import (
    AuthSession,
    Entry,
    PushSubscription,
    ReminderDispatch,
    Tracker,
    TrackerReminderBatch,
    TrackerReminderBatchItem,
)
from app.domain.push import PushResult
from app.domain.reminder import (
    TrackerBatchCandidate,
    TrackerBatchDispatcher,
    _ActiveBatchMember,
    confirm_reminder_dispatch,
)
from app.domain.tracker import EntryCreate, EntryUpdate, TrackerStore


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _SelectorSession:
    def __init__(self, rows):
        self.rows = rows
        self.execute_count = 0
        self.commit_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        return _ScalarRows(self.rows)

    async def commit(self):
        self.commit_count += 1


async def _cleanup_batch_domain(session_factory, tracker_ids, subscription_ids=()) -> None:
    """Delete one test domain in FK order without touching unrelated owner data."""
    async with session_factory() as db:
        dispatch_ids = select(ReminderDispatch.id).where(
            ReminderDispatch.subject_id.in_(tracker_ids)
        )
        batch_ids = list(
            (
                await db.execute(
                    select(TrackerReminderBatchItem.batch_id).where(
                        TrackerReminderBatchItem.dispatch_id.in_(dispatch_ids)
                    )
                )
            ).scalars()
        )
        await db.execute(
            TrackerReminderBatchItem.__table__.delete().where(
                TrackerReminderBatchItem.dispatch_id.in_(dispatch_ids)
            )
        )
        if batch_ids:
            await db.execute(
                TrackerReminderBatch.__table__.delete().where(
                    TrackerReminderBatch.id.in_(batch_ids)
                )
            )
        await db.execute(
            ReminderDispatch.__table__.delete().where(ReminderDispatch.subject_id.in_(tracker_ids))
        )
        await db.execute(Entry.__table__.delete().where(Entry.tracker_id.in_(tracker_ids)))
        if subscription_ids:
            await db.execute(
                PushSubscription.__table__.delete().where(PushSubscription.id.in_(subscription_ids))
            )
        await db.execute(Tracker.__table__.delete().where(Tracker.id.in_(tracker_ids)))
        await db.commit()


def _auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        id=uuid4(),
        token_hash=f"reminder-batching-test-{uuid4()}",
        user_email="owner@test.local",
        expires_at=now + timedelta(hours=1),
        private_until=now + timedelta(hours=1),
    )


def test_batch_selects_only_current_push_subscription_rows(monkeypatch) -> None:
    """Two current rows receive one aggregate call each; removed/terminal receive none."""
    current = [
        PushSubscription(
            id=UUID("019d0000-0000-7000-8000-000000000001"),
            endpoint="https://push.example/current-a",
            p256dh="a",
            auth="a",
        ),
        PushSubscription(
            id=UUID("019d0000-0000-7000-8000-000000000002"),
            endpoint="https://push.example/current-b",
            p256dh="b",
            auth="b",
        ),
    ]
    removed_endpoints = {
        "https://push.example/unsubscribed-before-snapshot",
        "https://push.example/dead-deleted-before-snapshot",
    }
    session = _SelectorSession(current)
    calls: list[str] = []

    async def fake_send_push(_db, subscription, _payload, **_kwargs):
        calls.append(subscription.endpoint)
        return PushResult.SENT

    monkeypatch.setattr(reminder_module, "send_push", fake_send_push)
    dispatcher = TrackerBatchDispatcher()
    result = asyncio.run(
        dispatcher.fanout_current_subscriptions(
            session,
            batch_status="pending",
            payload={"title": "aggregate"},
        )
    )

    assert result.current_count == 2
    assert result.sent_count == 2
    assert calls == [row.endpoint for row in current]
    assert removed_endpoints.isdisjoint(calls)
    assert session.execute_count == 1

    exhausted_session = _SelectorSession(current)
    terminal = asyncio.run(
        dispatcher.fanout_current_subscriptions(
            exhausted_session,
            batch_status="exhausted",
            payload={"title": "must-not-send"},
        )
    )
    assert terminal.current_count == 0
    assert exhausted_session.execute_count == 0
    assert calls == [row.endpoint for row in current]


def _member(*, private: bool, tracker_id: str, dispatch_id: str) -> _ActiveBatchMember:
    tracker = Tracker(
        id=UUID(tracker_id),
        name="enc:v1:fixture-ciphertext",
        kind="health",
        input_mode="event",
        reminder_time=time(8),
        reminder_mode="fixed",
        reminder_interval_days=1,
        reminder_action="confirm_event",
        is_private=private,
    )
    dispatch = ReminderDispatch(
        id=UUID(dispatch_id),
        subject_type="tracker",
        subject_id=tracker.id,
        dispatched_on=date(2026, 8, 29),
    )
    item = TrackerReminderBatchItem(
        id=UUID(dispatch_id[:-1] + "9"),
        batch_id=UUID("019d0000-0000-7000-8000-000000000100"),
        dispatch_id=dispatch.id,
        reminder_mode="fixed",
        reminder_interval_days=1,
        reminder_action="confirm_event",
        input_mode="event",
    )
    return _ActiveBatchMember(item=item, dispatch=dispatch, tracker=tracker)


def _batch() -> TrackerReminderBatch:
    return TrackerReminderBatch(
        id=UUID("019d0000-0000-7000-8000-000000000100"),
        occurrence_on=date(2026, 8, 29),
        reminder_time=time(8),
        generation=1,
    )


def test_batch_payload_public_private_multi_and_decrypt_fallback(monkeypatch, caplog) -> None:
    dispatcher = TrackerBatchDispatcher()
    public = _member(
        private=False,
        tracker_id="019d0000-0000-7000-8000-000000000001",
        dispatch_id="019d0000-0000-7000-8000-000000000011",
    )
    private = _member(
        private=True,
        tracker_id="019d0000-0000-7000-8000-000000000002",
        dispatch_id="019d0000-0000-7000-8000-000000000012",
    )
    decrypt_calls: list[str] = []

    def decrypt_ok(value: str) -> str:
        decrypt_calls.append(value)
        return "Tên tracker công khai"

    monkeypatch.setattr(reminder_module.crypto, "decrypt", decrypt_ok)
    payload = dispatcher._build_payload(_batch(), [public])
    assert payload == {
        "title": "Hi, it's microSched 🌸",
        "body": "Tên tracker công khai",
        "url": f"/reminder-confirm?dispatch={public.dispatch.id}",
        "tag": "msb-" + dispatcher._notification_tag(_batch().id).removeprefix("msb-"),
    }
    assert decrypt_calls == [public.tracker.name]

    decrypt_calls.clear()
    assert dispatcher._build_payload(_batch(), [private])["body"] == ("Bạn có 1 thông báo từ app")
    multi = dispatcher._build_payload(_batch(), [public, private])
    assert multi["body"] == "Bạn có 2 thông báo từ app"
    assert multi["url"] == "/trackers"
    assert decrypt_calls == []

    corrupt = "enc:v1:CORRUPT-SENTINEL-CIPHERTEXT"
    public.tracker.name = corrupt

    def decrypt_fail(_value: str) -> str:
        raise ValueError("UNAVAILABLE-KEY-METADATA")

    monkeypatch.setattr(reminder_module.crypto, "decrypt", decrypt_fail)
    with caplog.at_level(logging.WARNING):
        fallback = dispatcher._build_payload(_batch(), [public])
    assert fallback["body"] == "Bạn có 1 thông báo từ app"
    assert fallback["url"].endswith(str(public.dispatch.id))
    combined_log = " ".join(record.getMessage() for record in caplog.records)
    assert "public_name_decrypt_fallback" in combined_log
    assert corrupt not in combined_log
    assert "UNAVAILABLE-KEY-METADATA" not in combined_log
    assert str(public.tracker.id) not in combined_log
    assert str(public.dispatch.id) not in combined_log


def test_batch_key_keeps_vn_date_and_whole_second_exact() -> None:
    dispatcher = TrackerBatchDispatcher()
    first = dispatcher._advisory_key(date(2026, 8, 29), time(8, 0, 0))
    next_second = dispatcher._advisory_key(date(2026, 8, 29), time(8, 0, 1))
    next_date = dispatcher._advisory_key(date(2026, 8, 30), time(8, 0, 0))
    assert len({first, next_second, next_date}) == 3

    candidate = TrackerBatchCandidate(
        tracker_id=UUID("019d0000-0000-7000-8000-000000000001"),
        occurrence_on=date(2026, 8, 29),
        reminder_time=time(8),
        reminder_mode="after_entry",
        reminder_interval_days=3,
        reminder_action="open_tracker",
    )
    tracker = SimpleNamespace(
        kind="general",
        input_mode="event",
        reminder_time=time(8),
        reminder_mode="after_entry",
        reminder_interval_days=3,
        reminder_action="open_tracker",
    )
    assert dispatcher._candidate_is_due(
        candidate=candidate, tracker=tracker, latest_entry_on=date(2026, 8, 26)
    )
    assert not dispatcher._candidate_is_due(
        candidate=candidate, tracker=tracker, latest_entry_on=date(2026, 8, 29)
    )


@pytest.mark.pg
def test_same_key_two_trackers_two_current_endpoints_is_one_batch_two_calls(
    pg_dsn: str, monkeypatch
) -> None:
    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        tracker_ids = [
            UUID("019d1000-0000-7000-8000-000000000001"),
            UUID("019d1000-0000-7000-8000-000000000002"),
        ]
        subscription_ids = [
            UUID("019d1000-0000-7000-8000-000000000011"),
            UUID("019d1000-0000-7000-8000-000000000012"),
        ]
        provider_calls: list[str] = []

        async def fake_send_push(_db, subscription, payload, **_kwargs):
            provider_calls.append(subscription.endpoint)
            assert payload["body"] == "Bạn có 2 thông báo từ app"
            assert payload["url"] == "/trackers"
            return PushResult.SENT

        monkeypatch.setattr(reminder_module, "send_push", fake_send_push)
        batch_id = None
        try:
            async with session_factory() as db:
                for index, tracker_id in enumerate(tracker_ids):
                    db.add(
                        Tracker(
                            id=tracker_id,
                            name=f"enc:v1:fixture-{index}",
                            kind="general",
                            input_mode="event",
                            reminder_time=time(8),
                            reminder_mode="fixed",
                            reminder_interval_days=1,
                            reminder_action="open_tracker",
                            is_private=index == 1,
                        )
                    )
                for index, subscription_id in enumerate(subscription_ids):
                    db.add(
                        PushSubscription(
                            id=subscription_id,
                            endpoint=f"https://push.example/current-{index}",
                            p256dh="fixture",
                            auth="fixture",
                        )
                    )
                await db.commit()

                dispatcher = TrackerBatchDispatcher()
                batch_id = await dispatcher.claim_batch(
                    db,
                    [
                        TrackerBatchCandidate(
                            tracker_id=tracker_id,
                            occurrence_on=date(2026, 8, 29),
                            reminder_time=time(8),
                            reminder_mode="fixed",
                            reminder_interval_days=1,
                            reminder_action="open_tracker",
                        )
                        for tracker_id in tracker_ids
                    ],
                )
                assert batch_id is not None
                assert (await dispatcher.dispatch_batch(db, batch_id)).value == "sent"

                batch = (
                    await db.execute(
                        select(TrackerReminderBatch).where(TrackerReminderBatch.id == batch_id)
                    )
                ).scalar_one()
                item_count = (
                    await db.execute(
                        select(func.count(TrackerReminderBatchItem.id)).where(
                            TrackerReminderBatchItem.batch_id == batch_id
                        )
                    )
                ).scalar_one()
                linked = list(
                    (
                        await db.execute(
                            select(ReminderDispatch).where(
                                ReminderDispatch.subject_id.in_(tracker_ids),
                                ReminderDispatch.dispatched_on == date(2026, 8, 29),
                            )
                        )
                    ).scalars()
                )
                assert batch.status == "sent"
                assert batch.attempt_count == 1
                assert item_count == 2
                assert len(linked) == 2
                assert all(row.status == "sent" for row in linked)
                assert all(row.attempt_count == 0 and row.last_attempt_at is None for row in linked)
                assert provider_calls == [
                    "https://push.example/current-0",
                    "https://push.example/current-1",
                ]
        finally:
            async with session_factory() as db:
                if batch_id is not None:
                    await db.execute(
                        TrackerReminderBatchItem.__table__.delete().where(
                            TrackerReminderBatchItem.batch_id == batch_id
                        )
                    )
                    await db.execute(
                        TrackerReminderBatch.__table__.delete().where(
                            TrackerReminderBatch.id == batch_id
                        )
                    )
                await db.execute(
                    ReminderDispatch.__table__.delete().where(
                        ReminderDispatch.subject_id.in_(tracker_ids)
                    )
                )
                await db.execute(
                    PushSubscription.__table__.delete().where(
                        PushSubscription.id.in_(subscription_ids)
                    )
                )
                await db.execute(Tracker.__table__.delete().where(Tracker.id.in_(tracker_ids)))
                await db.commit()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_batch_retry_reuses_membership_and_fourth_temporary_exhausts(
    pg_dsn: str, monkeypatch
) -> None:
    """Attempts belong to one durable batch; linked dispatch counters stay legacy-zero."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        tracker_id = uuid4()
        subscription_id = uuid4()
        calls: list[str] = []
        warning_receipts: list[str] = []

        async def temporary(_db, subscription, _payload, **_kwargs):
            calls.append(subscription.endpoint)
            return PushResult.TEMPORARY_FAILURE

        monkeypatch.setattr(reminder_module, "send_push", temporary)
        monkeypatch.setattr(
            reminder_module.logger,
            "warning",
            lambda template, *args: warning_receipts.append(template % args),
        )
        try:
            async with session_factory() as db:
                db.add(
                    Tracker(
                        id=tracker_id,
                        name="enc:v1:retry-fixture",
                        kind="general",
                        input_mode="event",
                        reminder_time=time(8),
                        reminder_mode="fixed",
                        reminder_interval_days=1,
                        reminder_action="open_tracker",
                        is_private=True,
                    )
                )
                db.add(
                    PushSubscription(
                        id=subscription_id,
                        endpoint="https://push.example/retry",
                        p256dh="fixture",
                        auth="fixture",
                    )
                )
                await db.commit()
                candidate = TrackerBatchCandidate(
                    tracker_id=tracker_id,
                    occurrence_on=date(2026, 8, 30),
                    reminder_time=time(8),
                    reminder_mode="fixed",
                    reminder_interval_days=1,
                    reminder_action="open_tracker",
                )
                batch_id = await TrackerBatchDispatcher().claim_batch(db, [candidate])
                assert batch_id is not None
                original_membership = list(
                    (
                        await db.execute(
                            select(
                                TrackerReminderBatchItem.id,
                                TrackerReminderBatchItem.dispatch_id,
                            ).where(TrackerReminderBatchItem.batch_id == batch_id)
                        )
                    ).all()
                )

                outcomes = []
                for _ in range(4):
                    # A fresh dispatcher simulates process restart: authority
                    # must come from the committed batch, never heap regrouping.
                    outcomes.append(
                        (await TrackerBatchDispatcher().dispatch_batch(db, batch_id)).value
                    )
                assert outcomes == [
                    "temporary_failure",
                    "temporary_failure",
                    "temporary_failure",
                    "exhausted",
                ]
                assert len(calls) == 4
                assert (
                    await TrackerBatchDispatcher().dispatch_batch(db, batch_id)
                ).value == "exhausted"
                assert len(calls) == 4

                batch_row = (
                    await db.execute(
                        select(
                            TrackerReminderBatch.status,
                            TrackerReminderBatch.attempt_count,
                        ).where(TrackerReminderBatch.id == batch_id)
                    )
                ).one()
                item_row = (
                    await db.execute(
                        select(
                            TrackerReminderBatchItem.id,
                            TrackerReminderBatchItem.dispatch_id,
                            TrackerReminderBatchItem.state,
                            ReminderDispatch.status,
                            ReminderDispatch.attempt_count,
                            ReminderDispatch.last_attempt_at,
                        )
                        .join(
                            ReminderDispatch,
                            ReminderDispatch.id == TrackerReminderBatchItem.dispatch_id,
                        )
                        .where(TrackerReminderBatchItem.batch_id == batch_id)
                    )
                ).one()
                assert batch_row == ("exhausted", 4)
                assert item_row[:2] == original_membership[0]
                assert item_row[2:] == ("exhausted", "exhausted", 0, None)
                log_text = " ".join(warning_receipts)
                assert "outcome=manual_required" in log_text
                assert str(batch_id) not in log_text
                assert str(tracker_id) not in log_text

                next_occurrence = TrackerBatchCandidate(
                    tracker_id=candidate.tracker_id,
                    occurrence_on=date(2026, 8, 31),
                    reminder_time=candidate.reminder_time,
                    reminder_mode=candidate.reminder_mode,
                    reminder_interval_days=candidate.reminder_interval_days,
                    reminder_action=candidate.reminder_action,
                )
                next_batch_id = await TrackerBatchDispatcher().claim_batch(db, [next_occurrence])
                assert next_batch_id is not None
                next_batch = await db.get(TrackerReminderBatch, next_batch_id)
                assert next_batch is not None
                next_batch.attempt_count = 4
                await db.commit()
                calls_before_crash_recovery = len(calls)
                assert (
                    await TrackerBatchDispatcher().dispatch_batch(db, next_batch_id)
                ).value == "exhausted"
                assert len(calls) == calls_before_crash_recovery
                assert sum("outcome=manual_required" in row for row in warning_receipts) == 2
        finally:
            await _cleanup_batch_domain(session_factory, [tracker_id], [subscription_id])
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_restart_exhausts_batch_older_than_recovery_window_without_network(
    pg_dsn: str, monkeypatch
) -> None:
    """A >24h outage closes linked pending rows once and emits manual-required telemetry."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        tracker_id, subscription_id = uuid4(), uuid4()
        provider_calls = 0
        warning_receipts: list[str] = []
        now_vn = datetime(2026, 9, 4, 8, 0, tzinfo=VN_TZ)

        async def forbidden_send(*_args, **_kwargs):
            nonlocal provider_calls
            provider_calls += 1
            raise AssertionError("expired recovery must not start provider work")

        monkeypatch.setattr(reminder_module, "send_push", forbidden_send)
        monkeypatch.setattr(
            reminder_module.logger,
            "warning",
            lambda template, *args: warning_receipts.append(template % args),
        )
        try:
            async with session_factory() as db:
                db.add(
                    Tracker(
                        id=tracker_id,
                        name="enc:v1:stale-recovery-fixture",
                        kind="general",
                        input_mode="event",
                        reminder_time=time(8),
                        reminder_mode="fixed",
                        reminder_interval_days=1,
                        reminder_action="open_tracker",
                        is_private=True,
                    )
                )
                db.add(
                    PushSubscription(
                        id=subscription_id,
                        endpoint="https://push.example/stale-recovery",
                        p256dh="fixture",
                        auth="fixture",
                    )
                )
                await db.commit()
                dispatcher = TrackerBatchDispatcher()
                batch_id = await dispatcher.claim_batch(
                    db,
                    [
                        TrackerBatchCandidate(
                            tracker_id=tracker_id,
                            occurrence_on=now_vn.date(),
                            reminder_time=time(8),
                            reminder_mode="fixed",
                            reminder_interval_days=1,
                            reminder_action="open_tracker",
                        )
                    ],
                )
                assert batch_id is not None
                batch = await db.get(TrackerReminderBatch, batch_id)
                assert batch is not None
                batch.attempt_count = 1
                batch.last_attempt_at = (now_vn - timedelta(hours=25)).astimezone(UTC)
                await db.commit()

                timer = CronTimer(session_factory, tracker_batch_dispatcher=dispatcher)
                await timer.load_snapshot(db, now=now_vn)
                assert timer._pending_manual_required["exhausted"] == 1
                assert all(item[5].batch_id != batch_id for item in timer._heap)

                terminal = (
                    await db.execute(
                        select(
                            TrackerReminderBatch.status,
                            TrackerReminderBatch.attempt_count,
                            TrackerReminderBatchItem.state,
                            ReminderDispatch.status,
                            ReminderDispatch.attempt_count,
                        )
                        .join(
                            TrackerReminderBatchItem,
                            TrackerReminderBatchItem.batch_id == TrackerReminderBatch.id,
                        )
                        .join(
                            ReminderDispatch,
                            ReminderDispatch.id == TrackerReminderBatchItem.dispatch_id,
                        )
                        .where(TrackerReminderBatch.id == batch_id)
                    )
                ).one()
                assert terminal == ("exhausted", 1, "exhausted", "exhausted", 0)
                linked_pending = (
                    await db.execute(
                        select(func.count(ReminderDispatch.id))
                        .join(
                            TrackerReminderBatchItem,
                            TrackerReminderBatchItem.dispatch_id == ReminderDispatch.id,
                        )
                        .where(
                            TrackerReminderBatchItem.batch_id == batch_id,
                            ReminderDispatch.status == "pending",
                        )
                    )
                ).scalar_one()
                assert linked_pending == 0
                assert provider_calls == 0

                receipt_count = sum(
                    "reason=recovery_window_expired" in receipt for receipt in warning_receipts
                )
                assert receipt_count == 1
                log_text = "\n".join(warning_receipts)
                assert "outcome=manual_required" in log_text
                assert str(batch_id) not in log_text
                assert str(tracker_id) not in log_text

                restarted = CronTimer(
                    session_factory,
                    tracker_batch_dispatcher=TrackerBatchDispatcher(),
                )
                await restarted.load_snapshot(db, now=now_vn + timedelta(minutes=1))
                assert restarted._pending_manual_required["exhausted"] == 0
                assert provider_calls == 0
                assert (
                    sum("reason=recovery_window_expired" in receipt for receipt in warning_receipts)
                    == receipt_count
                )
        finally:
            await _cleanup_batch_domain(session_factory, [tracker_id], [subscription_id])
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_presend_revalidation_cancels_changed_member_and_uses_current_privacy(
    pg_dsn: str, monkeypatch
) -> None:
    """Changed config is cancelled while a privacy toggle changes the live payload."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        changed_id, private_id, subscription_id = uuid4(), uuid4(), uuid4()
        payloads: list[dict] = []

        async def sent(_db, _subscription, payload, **_kwargs):
            payloads.append(payload)
            return PushResult.SENT

        def forbidden_decrypt(_value: str) -> str:
            raise AssertionError("single-private revalidation must not decrypt")

        monkeypatch.setattr(reminder_module, "send_push", sent)
        monkeypatch.setattr(reminder_module.crypto, "decrypt", forbidden_decrypt)
        try:
            async with session_factory() as db:
                for tracker_id in (changed_id, private_id):
                    db.add(
                        Tracker(
                            id=tracker_id,
                            name="enc:v1:must-not-leak",
                            kind="general",
                            input_mode="event",
                            reminder_time=time(9),
                            reminder_mode="fixed",
                            reminder_interval_days=1,
                            reminder_action="open_tracker",
                            is_private=False,
                        )
                    )
                db.add(
                    PushSubscription(
                        id=subscription_id,
                        endpoint="https://push.example/revalidate",
                        p256dh="fixture",
                        auth="fixture",
                    )
                )
                await db.commit()
                candidates = [
                    TrackerBatchCandidate(
                        tracker_id=tracker_id,
                        occurrence_on=date(2026, 9, 1),
                        reminder_time=time(9),
                        reminder_mode="fixed",
                        reminder_interval_days=1,
                        reminder_action="open_tracker",
                    )
                    for tracker_id in (changed_id, private_id)
                ]
                dispatcher = TrackerBatchDispatcher()
                batch_id = await dispatcher.claim_batch(db, candidates)
                assert batch_id is not None

                changed = await db.get(Tracker, changed_id)
                private = await db.get(Tracker, private_id)
                assert changed is not None and private is not None
                changed.reminder_time = time(9, 0, 1)
                private.is_private = True
                await db.commit()

                assert (await dispatcher.dispatch_batch(db, batch_id)).value == "sent"
                assert payloads == [
                    {
                        "title": "Hi, it's microSched 🌸",
                        "body": "Bạn có 1 thông báo từ app",
                        "url": "/trackers",
                        "tag": dispatcher._notification_tag(batch_id),
                    }
                ]
                rows = list(
                    (
                        await db.execute(
                            select(
                                ReminderDispatch.subject_id,
                                TrackerReminderBatchItem.state,
                                ReminderDispatch.status,
                            )
                            .join(
                                TrackerReminderBatchItem,
                                TrackerReminderBatchItem.dispatch_id == ReminderDispatch.id,
                            )
                            .where(TrackerReminderBatchItem.batch_id == batch_id)
                        )
                    ).all()
                )
                assert {row for row in rows} == {
                    (changed_id, "cancelled", "cancelled"),
                    (private_id, "sent", "sent"),
                }
        finally:
            await _cleanup_batch_domain(
                session_factory,
                [changed_id, private_id],
                [subscription_id],
            )
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_concurrent_same_key_claim_commits_one_generation(pg_dsn: str) -> None:
    """The dedicated advisory key serializes max-generation and membership claim."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        tracker_ids = [uuid4(), uuid4()]
        try:
            async with session_factory() as db:
                for tracker_id in tracker_ids:
                    db.add(
                        Tracker(
                            id=tracker_id,
                            name="enc:v1:concurrent-fixture",
                            kind="general",
                            input_mode="event",
                            reminder_time=time(10),
                            reminder_mode="fixed",
                            reminder_interval_days=1,
                            reminder_action="open_tracker",
                            is_private=True,
                        )
                    )
                await db.commit()
            candidates = [
                TrackerBatchCandidate(
                    tracker_id=tracker_id,
                    occurrence_on=date(2026, 9, 2),
                    reminder_time=time(10),
                    reminder_mode="fixed",
                    reminder_interval_days=1,
                    reminder_action="open_tracker",
                )
                for tracker_id in tracker_ids
            ]

            async def claim():
                async with session_factory() as db:
                    return await TrackerBatchDispatcher().claim_batch(db, candidates)

            results = await asyncio.gather(claim(), claim())
            assert sum(result is not None for result in results) == 1
            async with session_factory() as db:
                batch_count = (
                    await db.execute(
                        select(func.count(TrackerReminderBatch.id)).where(
                            TrackerReminderBatch.occurrence_on == date(2026, 9, 2),
                            TrackerReminderBatch.reminder_time == time(10),
                        )
                    )
                ).scalar_one()
                item_count = (
                    await db.execute(
                        select(func.count(TrackerReminderBatchItem.id)).where(
                            TrackerReminderBatchItem.batch_id
                            == next(result for result in results if result is not None)
                        )
                    )
                ).scalar_one()
                assert (batch_count, item_count) == (1, 2)
        finally:
            await _cleanup_batch_domain(session_factory, tracker_ids)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
@pytest.mark.parametrize(
    ("mutation_case", "expected_outcome", "expected_provider_calls"),
    [
        ("create", "cancelled", 0),
        ("update_occurred_at", "cancelled", 0),
        ("soft_delete", "sent", 1),
        ("restore", "cancelled", 0),
        ("confirmation", "cancelled", 0),
    ],
    ids=[
        "entry-create-before-presend",
        "entry-update-occurred-at-before-presend",
        "entry-soft-delete-before-presend",
        "entry-restore-before-presend",
        "confirmation-before-presend",
    ],
)
def test_entry_mutation_commit_before_presend_controls_delivery(
    pg_dsn: str,
    monkeypatch,
    mutation_case: str,
    expected_outcome: str,
    expected_provider_calls: int,
) -> None:
    """Each freshness writer commits before pre-send and determines the observed outcome."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        tracker_id, subscription_id, entry_id = uuid4(), uuid4(), uuid4()
        occurrence_on = date(2026, 9, 6)
        old_at = datetime(2026, 9, 4, 1, tzinfo=UTC)
        fresh_at = datetime(2026, 9, 6, 1, tzinfo=UTC)
        reminder_action = "confirm_event" if mutation_case == "confirmation" else "open_tracker"
        provider_calls: list[dict] = []

        async def sent(_db, _subscription, payload, **_kwargs):
            provider_calls.append(payload)
            return PushResult.SENT

        monkeypatch.setattr(reminder_module, "send_push", sent)
        try:
            async with session_factory() as db:
                db.add(
                    Tracker(
                        id=tracker_id,
                        name="enc:v1:entry-race-fixture",
                        kind="general",
                        input_mode="event",
                        reminder_time=time(12),
                        reminder_mode="after_entry",
                        reminder_interval_days=1,
                        reminder_action=reminder_action,
                        is_private=True,
                    )
                )
                db.add(
                    PushSubscription(
                        id=subscription_id,
                        endpoint=f"https://push.example/entry-race-{mutation_case}",
                        p256dh="fixture",
                        auth="fixture",
                    )
                )
                await db.commit()
                if mutation_case in {"update_occurred_at", "soft_delete"}:
                    db.add(Entry(id=entry_id, tracker_id=tracker_id, occurred_at=old_at))
                elif mutation_case == "restore":
                    db.add(
                        Entry(
                            id=entry_id,
                            tracker_id=tracker_id,
                            occurred_at=fresh_at,
                            deleted_at=fresh_at + timedelta(minutes=1),
                        )
                    )
                await db.commit()
                batch_id = await TrackerBatchDispatcher().claim_batch(
                    db,
                    [
                        TrackerBatchCandidate(
                            tracker_id=tracker_id,
                            occurrence_on=occurrence_on,
                            reminder_time=time(12),
                            reminder_mode="after_entry",
                            reminder_interval_days=1,
                            reminder_action=reminder_action,
                        )
                    ],
                )
                assert batch_id is not None
                dispatch_id = (
                    await db.execute(
                        select(TrackerReminderBatchItem.dispatch_id).where(
                            TrackerReminderBatchItem.batch_id == batch_id
                        )
                    )
                ).scalar_one()

            store = TrackerStore()
            auth = _auth()
            async with session_factory() as writer_db:
                if mutation_case == "create":
                    _created_id, created = await store.create_entry(
                        writer_db,
                        auth,
                        EntryCreate(tracker_id=tracker_id, occurred_at=fresh_at),
                    )
                    assert created is True
                    await writer_db.commit()
                elif mutation_case == "update_occurred_at":
                    updated = await store.update_entry(
                        writer_db,
                        auth,
                        entry_id,
                        EntryUpdate(occurred_at=fresh_at),
                    )
                    assert updated is not None
                    await writer_db.commit()
                elif mutation_case == "soft_delete":
                    assert await store.soft_delete_entry(writer_db, auth, entry_id) is True
                    await writer_db.commit()
                elif mutation_case == "restore":
                    restored = await store.restore_entry(writer_db, auth, entry_id)
                    assert restored is not None
                    await writer_db.commit()
                else:
                    _entry, created = await confirm_reminder_dispatch(
                        writer_db,
                        dispatch_id,
                        uuid7(),
                        fresh_at,
                        auth,
                    )
                    assert created is True

            # A new session and dispatcher make the writer commit the exact
            # authority boundary before pre-send revalidation begins.
            async with session_factory() as send_db:
                outcome = await TrackerBatchDispatcher().dispatch_batch(send_db, batch_id)
                terminal = (
                    await send_db.execute(
                        select(
                            TrackerReminderBatch.status,
                            TrackerReminderBatch.attempt_count,
                            TrackerReminderBatchItem.state,
                            ReminderDispatch.status,
                        )
                        .join(
                            TrackerReminderBatchItem,
                            TrackerReminderBatchItem.batch_id == TrackerReminderBatch.id,
                        )
                        .join(
                            ReminderDispatch,
                            ReminderDispatch.id == TrackerReminderBatchItem.dispatch_id,
                        )
                        .where(TrackerReminderBatch.id == batch_id)
                    )
                ).one()
            assert outcome.value == expected_outcome
            assert len(provider_calls) == expected_provider_calls
            expected_attempts = 1 if expected_outcome == "sent" else 0
            assert terminal == (
                expected_outcome,
                expected_attempts,
                expected_outcome,
                expected_outcome,
            )
        finally:
            await _cleanup_batch_domain(session_factory, [tracker_id], [subscription_id])
            await engine.dispose()

    asyncio.run(scenario())
