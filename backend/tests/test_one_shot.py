"""Contract-level pure tests for one-shot scheduling (no real data or providers)."""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domain.models import CalendarEvent, Task, Tracker
from app.domain.one_shot import LATE_WINDOW, ReminderWrite, resolve_due

NOW = datetime(2030, 1, 2, 10, tzinfo=UTC)


def test_absolute_reminder_is_independent_of_source_deadline():
    for source in [
        Task(title="No deadline"),
        Task(title="Has deadline", due_at=NOW),
        Tracker(name="Tracker"),
        CalendarEvent(title="Event", starts_at=NOW),
    ]:
        assert resolve_due(source, ReminderWrite(mode="absolute", due_at=NOW)) == NOW


@pytest.mark.parametrize("offset", [-2880, -60, -15, 0, 180, 1440])
def test_relative_before_and_after(offset):
    task = Task(title="Deadline", due_precision="datetime", due_at=NOW)
    assert resolve_due(task, ReminderWrite(mode="relative", offset_minutes=offset)) == (
        NOW + timedelta(minutes=offset)
    )


def test_date_only_requires_explicit_anchor_clock():
    task = Task(title="Date", due_precision="date", due_on=date(2030, 1, 2))
    with pytest.raises(HTTPException) as error:
        resolve_due(task, ReminderWrite(mode="relative", offset_minutes=-60))
    assert error.value.status_code == 422
    assert resolve_due(
        task, ReminderWrite(mode="relative", offset_minutes=-60, anchor_time=time(9))
    ) == NOW.replace(hour=1)


def test_missing_anchor_and_tracker_relative_are_rejected():
    for source in [Task(title="None", due_precision="none"), Tracker(name="Tracker")]:
        with pytest.raises(HTTPException):
            resolve_due(source, ReminderWrite(mode="relative", offset_minutes=15))


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "absolute", "due_at": "2030-01-01T10:00:00"},
        {"mode": "relative", "offset_minutes": 0.5},
        {"mode": "relative", "offset_minutes": 525601},
        {"mode": "relative", "offset_minutes": 0, "anchor_time": "09:00:01"},
        {"mode": "absolute", "due_at": NOW, "offset_minutes": 0},
    ],
)
def test_invalid_inputs_fail_validation(payload):
    with pytest.raises(ValidationError):
        ReminderWrite(**payload)


def test_existing_recurring_grace_is_unchanged():
    from app.core.cron_timer import GRACE_WINDOW

    assert GRACE_WINDOW == timedelta(minutes=15)
    assert LATE_WINDOW == timedelta(minutes=45)
