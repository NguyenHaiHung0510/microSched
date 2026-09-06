"""Synthetic, non-PG recurrence and scoped-query receipts for Task 043."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

import app.domain.tracker as tracker_domain
from app.core.cron_timer import CronTimer
from app.domain.models import AuthSession, Tracker
from app.domain.tracker import TrackerRead, TrackerStore
from app.domain.tracker_schedule import VN_TZ, next_tracker_reminder_at

NOW = datetime(2026, 9, 6, 8, 0, tzinfo=VN_TZ)


def tracker(number=1, **overrides):
    values = dict(
        id=UUID(int=number),
        name="Synthetic tracker",
        kind="general",
        direction="out",
        input_mode="event",
        reminder_time=time(9),
        reminder_mode="fixed",
        reminder_interval_days=5,
        reminder_action="open_tracker",
        is_private=False,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    values.update(overrides)
    return Tracker(**values)


def project(row=None, *, now=NOW, entry=None, anchor=None, dispatched=None):
    return next_tracker_reminder_at(
        row or tracker(),
        now=now,
        last_entry_at=entry,
        last_scheduled_date=anchor,
        dispatched_dates=dispatched or set(),
    )


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (NOW, datetime(2026, 9, 6, 9, tzinfo=VN_TZ)),
        (NOW.replace(hour=9, minute=15), datetime(2026, 9, 6, 9, tzinfo=VN_TZ)),
        (NOW.replace(hour=9, minute=15, second=1), datetime(2026, 9, 7, 9, tzinfo=VN_TZ)),
    ],
)
def test_first_occurrence_uses_nearest_slot_and_inclusive_grace(now, expected):
    assert project(now=now) == expected


@pytest.mark.parametrize(
    ("anchor", "expected_day"),
    [
        (date(2026, 9, 4), 9),
        (date(2026, 8, 20), 9),
        (date(2026, 9, 1), 6),
    ],
)
def test_fixed_five_day_dispatch_anchor_and_missed_cadence(anchor, expected_day):
    assert project(anchor=anchor, entry=NOW - timedelta(days=100)) == datetime(
        2026,
        9,
        expected_day,
        9,
        tzinfo=VN_TZ,
    )


def test_fixed_grace_elapsed_rolls_by_five_not_one():
    assert project(now=NOW.replace(hour=10), anchor=date(2026, 9, 1)) == datetime(
        2026,
        9,
        11,
        9,
        tzinfo=VN_TZ,
    )


@pytest.mark.parametrize(
    "entry",
    [
        datetime(2026, 9, 1, 17, 30, tzinfo=UTC),
        datetime(2026, 9, 1, 17, 30),  # DB naive fallback is UTC, as in the scheduler.
    ],
)
def test_after_entry_uses_vn_civil_date_across_midnight(entry):
    assert project(tracker(reminder_mode="after_entry"), entry=entry) == datetime(
        2026,
        9,
        7,
        9,
        tzinfo=VN_TZ,
    )


@pytest.mark.parametrize(
    ("entry", "expected_day"),
    [
        (None, 6),
        (datetime(2026, 8, 1, tzinfo=UTC), 6),
        (datetime(2026, 9, 10, tzinfo=UTC), 15),
    ],
)
def test_after_entry_missing_stale_future(entry, expected_day):
    assert project(tracker(reminder_mode="after_entry"), entry=entry) == datetime(
        2026,
        9,
        expected_day,
        9,
        tzinfo=VN_TZ,
    )


def test_after_entry_skips_already_claimed_dates_without_using_them_as_freshness():
    assert project(
        tracker(reminder_mode="after_entry"),
        dispatched={date(2026, 9, 6), date(2026, 9, 7)},
    ) == datetime(2026, 9, 8, 9, tzinfo=VN_TZ)


def test_grace_can_retain_previous_vn_date_at_midnight():
    now = datetime(2026, 9, 6, 0, 5, tzinfo=VN_TZ)
    assert project(
        tracker(reminder_time=time(23, 55), reminder_mode="after_entry", reminder_interval_days=1),
        now=now,
        entry=datetime(2026, 9, 4, 12, tzinfo=VN_TZ),
    ) == datetime(2026, 9, 5, 23, 55, tzinfo=VN_TZ)


def test_clock_is_converted_to_vn_before_first_occurrence():
    assert project(now=datetime(2026, 9, 5, 23, tzinfo=UTC)) == datetime(
        2026,
        9,
        6,
        9,
        tzinfo=VN_TZ,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"reminder_time": None},
        {"reminder_interval_days": 0},
        {"reminder_time": time(9, microsecond=1)},
        {"reminder_mode": None},
    ],
)
def test_disabled_or_invalid_config_has_no_projected_occurrence(changes):
    assert project(tracker(**changes)) is None


def test_legacy_daily_medication_and_scheduler_helpers_share_semantics():
    row = tracker(
        kind="health", reminder_mode=None, reminder_interval_days=None, reminder_action=None
    )
    assert project(row, anchor=date(2026, 9, 6)) == datetime(2026, 9, 7, 9, tzinfo=VN_TZ)
    from app.domain import tracker_schedule

    assert CronTimer._fixed_candidate_date is tracker_schedule.fixed_candidate_date
    assert CronTimer._after_entry_candidate_date is tracker_schedule.after_entry_candidate_date
    assert CronTimer._effective_tracker_config is tracker_schedule.effective_tracker_config


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Database:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "Unexpected query (possible N+1)"
        return Result(self.results.pop(0))


def sql(statement):
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def auth():
    return AuthSession(
        token_hash="synthetic", user_email="synthetic@example.test", private_until=None
    )


@pytest.fixture
def frozen_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(tracker_domain, "datetime", Clock)
    monkeypatch.setattr(tracker_domain, "_clear", lambda value: value)


def test_list_projection_batches_only_readable_ids_and_ignores_deleted_entries(frozen_clock):
    fixed, after, disabled = (
        tracker(),
        tracker(2, reminder_mode="after_entry"),
        tracker(
            3,
            reminder_time=None,
            reminder_mode=None,
            reminder_interval_days=None,
            reminder_action=None,
        ),
    )
    # Fake query results supply only the latest NON-deleted entry. The query shape
    # assertion below prevents an implementation from allowing deleted rows back in.
    db = Database(
        [
            [fixed, after, disabled],
            [(after.id, datetime(2026, 9, 1, 17, 30, tzinfo=UTC))],
            [],
            [(fixed.id, date(2026, 9, 4))],
            [(after.id, date(2026, 9, 7))],
        ]
    )
    rows = asyncio.run(TrackerStore().list_trackers(db, auth()))
    assert len(db.statements) == 5
    assert [row.next_reminder_at for row in rows] == [
        datetime(2026, 9, 9, 9, tzinfo=VN_TZ),
        datetime(2026, 9, 8, 9, tzinfo=VN_TZ),
        None,
    ]
    assert rows[0].model_dump(mode="json")["next_reminder_at"].endswith("+07:00")
    gate = sql(db.statements[0])
    assert "tracker.is_private IS false" in gate
    assert "tracker.deleted_at IS NULL" in gate
    for statement in db.statements[1:3]:
        query = sql(statement)
        assert "entry.deleted_at IS NULL" in query
        assert "entry.tracker_id IN" in query
    latest, dates = map(sql, db.statements[3:])
    for query, allowed in ((latest, fixed), (dates, after)):
        assert "reminder_dispatch.subject_type = 'tracker'" in query
        assert f"subject_id IN ('{allowed.id}')" in query
        assert str(disabled.id) not in query
        assert "status" not in query  # pending/failed/sent all anchor recurrence
    assert "max(microsched.reminder_dispatch.dispatched_on)" in latest
    assert "GROUP BY microsched.reminder_dispatch.subject_id" in latest
    assert "dispatched_on >= '2026-08-07'" in dates


def test_hidden_or_deleted_tracker_get_stops_before_dispatch_query():
    db = Database([[]])
    assert asyncio.run(TrackerStore().get_tracker(db, auth(), UUID(int=99))) is None
    assert len(db.statements) == 1
    assert "tracker.is_private IS false" in sql(db.statements[0])
    assert "tracker.deleted_at IS NULL" in sql(db.statements[0])


def test_empty_list_stops_before_aggregate_queries():
    db = Database([[]])
    assert asyncio.run(TrackerStore().list_trackers(db, auth())) == []
    assert len(db.statements) == 1


def test_projection_query_count_does_not_grow_with_tracker_count():
    rows = [tracker(i) for i in range(1, 101)] + [
        tracker(i, reminder_mode="after_entry") for i in range(101, 201)
    ]
    db = Database([[], []])
    result = asyncio.run(TrackerStore()._next_reminders(db, rows, {}, now=NOW))
    assert len(result) == 200
    assert len(db.statements) == 2


def test_disabled_reminders_do_not_query_dispatch_history():
    db = Database([])
    result = asyncio.run(
        TrackerStore()._next_reminders(
            db,
            [tracker(reminder_time=None)],
            {},
            now=NOW,
        )
    )
    assert result == {UUID(int=1): None}
    assert not db.statements


def test_projection_field_is_optional_for_rolling_dto_compatibility():
    assert not TrackerRead.model_fields["next_reminder_at"].is_required()
    assert TrackerRead.model_fields["next_reminder_at"].default is None


@pytest.mark.parametrize("mode", ["fixed", "after_entry"])
def test_unrepresentable_interval_does_not_break_tracker_reads(mode):
    # The existing write contract has no upper bound on positive day intervals.
    assert (
        project(
            tracker(reminder_mode=mode, reminder_interval_days=2_147_483_647),
            anchor=date(2026, 9, 1),
            entry=NOW,
        )
        is None
    )
