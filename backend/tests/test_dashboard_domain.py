"""Database-free bounds and disclosure guards for the tracker dashboard report."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.dashboard import VN_TZ, DashboardService, _finance_month_bounds, _periods
from app.domain.models import AuthSession


class _StatementRows:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _PrivacyAwareSession:
    """A no-DB executor whose synthetic rows follow the compiled tracker predicate."""

    def __init__(self) -> None:
        self.sql = ""
        self.public = ("public-entry", "public-tracker")
        self.private = ("private-entry", "private-tracker")

    async def execute(self, statement):
        self.sql = str(statement).lower()
        rows = [self.public]
        if "tracker.is_private is false" not in self.sql:
            rows.append(self.private)
        return _StatementRows(rows)


def test_absolute_report_range_uses_full_previous_months_across_leap_year() -> None:
    """A partial March report still compares against all of February, including leap day."""
    now = datetime(2024, 3, 1, 9, 30, tzinfo=VN_TZ)

    period = _periods("2024-03", now, months=3)

    assert period.period_start == datetime(2024, 1, 1, tzinfo=VN_TZ)
    assert period.period_end == now
    assert period.prev_start == datetime(2023, 10, 1, tzinfo=VN_TZ)
    assert period.prev_end == datetime(2024, 1, 1, tzinfo=VN_TZ)
    assert period.prev_period_days == 92
    assert period.prev_period_truncated is False

    monthly = _finance_month_bounds("2024-03", 3, now)
    assert [(item.month, item.period_end) for item in monthly] == [
        ("2024-01", datetime(2024, 2, 1, tzinfo=VN_TZ)),
        ("2024-02", datetime(2024, 3, 1, tzinfo=VN_TZ)),
        ("2024-03", now),
    ]


def test_first_day_has_no_fake_zero_length_previous_comparison() -> None:
    period = _periods("2025-05", datetime(2025, 5, 1, 0, 1, tzinfo=VN_TZ))

    assert period.current_period_days == 0
    assert period.prev_start == datetime(2025, 4, 1, tzinfo=VN_TZ)
    assert period.prev_end == datetime(2025, 5, 1, tzinfo=VN_TZ)
    assert period.prev_period_days == 30


@pytest.mark.parametrize("month", ["2025-2", "2025-00", "2025-13", "nope"])
def test_month_format_is_strict(month: str) -> None:
    with pytest.raises(ValueError):
        _periods(month, datetime(2025, 5, 2, tzinfo=VN_TZ), months=1)


def test_year_underflow_and_future_selection_are_bounded() -> None:
    now = datetime(2025, 5, 2, tzinfo=VN_TZ)
    with pytest.raises(ValueError):
        _periods("0001-01", now, months=1)
    with pytest.raises(ValueError):
        _periods("2025-05", now, months=2)

    future = _periods("2025-06", now, months=1)
    assert future.is_future is True
    assert future.period_start == future.period_end
    assert future.prev_start is None


def test_activity_is_sparse_and_excludes_archived_and_future_rows() -> None:
    visible_id, archived_id = uuid4(), uuid4()
    selected_start = datetime(2025, 5, 1, tzinfo=VN_TZ)
    period_end = datetime(2025, 5, 2, 12, tzinfo=VN_TZ)
    rows = [
        (
            SimpleNamespace(occurred_at=datetime(2025, 5, 1, 10, tzinfo=VN_TZ)),
            SimpleNamespace(id=visible_id, deleted_at=None),
            None,
            False,
        ),
        (
            SimpleNamespace(occurred_at=datetime(2025, 5, 1, 11, tzinfo=VN_TZ)),
            SimpleNamespace(id=visible_id, deleted_at=None),
            None,
            False,
        ),
        (
            # SQLite test fixtures can round-trip a timestamp without tzinfo; it
            # remains a +07 local timestamp for this report.
            SimpleNamespace(occurred_at=datetime(2025, 5, 1, 11, 30)),
            SimpleNamespace(id=visible_id, deleted_at=None),
            None,
            False,
        ),
        (
            SimpleNamespace(occurred_at=datetime(2025, 5, 1, 10, tzinfo=VN_TZ)),
            SimpleNamespace(id=archived_id, deleted_at=datetime(2025, 5, 1, tzinfo=VN_TZ)),
            None,
            False,
        ),
        (
            SimpleNamespace(occurred_at=datetime(2025, 5, 2, 13, tzinfo=VN_TZ)),
            SimpleNamespace(id=visible_id, deleted_at=None),
            None,
            False,
        ),
    ]

    activity = DashboardService._activity_days(rows, selected_start, period_end)

    assert [item.model_dump(mode="json") for item in activity] == [
        {"tracker_id": str(visible_id), "day": "2025-05-01", "count": 3}
    ]


def test_dashboard_activity_source_keeps_locked_private_tracker_sql_gate() -> None:
    """Removing the parent privacy gate makes the activity source return a private row."""

    async def scenario() -> None:
        now = datetime.now(UTC)
        locked = AuthSession(
            token_hash="dashboard-privacy-guard",
            user_email="owner@example.com",
            expires_at=now + timedelta(days=1),
            private_until=None,
        )
        db = _PrivacyAwareSession()
        rows = await DashboardService()._fetch_month(
            db,
            locked,
            datetime(2025, 5, 1, tzinfo=VN_TZ),
            datetime(2025, 6, 1, tzinfo=VN_TZ),
        )

        assert "tracker.is_private is false" in db.sql
        assert rows == [db.public]

    asyncio.run(scenario())
