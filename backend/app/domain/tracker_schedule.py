"""Canonical tracker recurrence dates shared by the timer and read projections.

These helpers describe planned occurrences, including the timer's 15-minute grace.
They do not describe push delivery, pending recovery or retry attempt timestamps.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

from app.domain.models import Tracker

VN_TZ = timezone(timedelta(hours=7))
GRACE_WINDOW = timedelta(minutes=15)


def effective_tracker_config(
    tracker: Tracker,
) -> tuple[str, int, str, time] | None:
    """Return an enabled config, including the rolling legacy writer shape."""
    if tracker.reminder_time is None:
        return None
    if tracker.reminder_time.microsecond:
        # 035A is deployed before the database CHECK arrives.  An old or
        # direct-SQL writer can still leave a fractional row, which must
        # never become a rounded or fractional batch key in RAM.
        return None
    if (
        tracker.kind == "health"
        and tracker.input_mode == "event"
        and tracker.reminder_mode is None
        and tracker.reminder_interval_days is None
        and tracker.reminder_action is None
    ):
        return "fixed", 1, "confirm_event", tracker.reminder_time
    if (
        tracker.reminder_mode not in {"fixed", "after_entry"}
        or tracker.reminder_interval_days is None
        or tracker.reminder_interval_days <= 0
        or tracker.reminder_action not in {"confirm_event", "open_tracker"}
        or (tracker.reminder_action == "confirm_event" and tracker.input_mode != "event")
    ):
        return None
    return (
        tracker.reminder_mode,
        tracker.reminder_interval_days,
        tracker.reminder_action,
        tracker.reminder_time,
    )


def fixed_candidate_date(
    *,
    now_vn: datetime,
    reminder_time: time,
    interval_days: int,
    last_scheduled_date: date | None,
) -> date:
    """Choose the next fixed cadence date without burst catch-up."""
    if last_scheduled_date is None:
        candidate = now_vn.date()
        if datetime.combine(candidate, reminder_time, tzinfo=VN_TZ) < now_vn - GRACE_WINDOW:
            candidate += timedelta(days=1)
        return candidate
    candidate = last_scheduled_date + timedelta(days=interval_days)
    while datetime.combine(candidate, reminder_time, tzinfo=VN_TZ) < now_vn - GRACE_WINDOW:
        candidate += timedelta(days=interval_days)
    return candidate


def after_entry_candidate_date(
    *,
    now_vn: datetime,
    reminder_time: time,
    interval_days: int,
    last_entry_date: date | None,
    dispatched_dates: set[date],
) -> date:
    """Choose a civil VN date, using entry freshness rather than notifications."""
    freshness = (
        last_entry_date + timedelta(days=interval_days) if last_entry_date is not None else None
    )
    if freshness is not None and datetime.combine(freshness, reminder_time, tzinfo=VN_TZ) >= (
        now_vn - GRACE_WINDOW
    ):
        candidate = freshness
    else:
        candidate = now_vn.date()
        if datetime.combine(candidate, reminder_time, tzinfo=VN_TZ) < now_vn - GRACE_WINDOW:
            candidate += timedelta(days=1)
    while candidate in dispatched_dates:
        candidate += timedelta(days=1)
    return candidate


def next_tracker_reminder_at(
    tracker: Tracker,
    *,
    now: datetime,
    last_entry_at: datetime | None,
    last_scheduled_date: date | None,
    dispatched_dates: set[date],
) -> datetime | None:
    """Project the next planned VN occurrence, never a promise of push delivery.

    An occurrence within the grace window may be up to 15 minutes in the past.
    Claimed/pending/terminal dispatches all count as scheduled occurrences; their
    retries are separate from this projection. Disabled/unrepresentable schedules yield null.
    """
    config = effective_tracker_config(tracker)
    if config is None:
        return None
    mode, interval_days, _action, reminder_time = config
    now_vn = now.astimezone(VN_TZ)
    try:
        if mode == "fixed":
            candidate = fixed_candidate_date(
                now_vn=now_vn,
                reminder_time=reminder_time,
                interval_days=interval_days,
                last_scheduled_date=last_scheduled_date,
            )
        else:
            if last_entry_at is not None and last_entry_at.tzinfo is None:
                last_entry_at = last_entry_at.replace(tzinfo=UTC)
            candidate = after_entry_candidate_date(
                now_vn=now_vn,
                reminder_time=reminder_time,
                interval_days=interval_days,
                last_entry_date=(
                    last_entry_at.astimezone(VN_TZ).date() if last_entry_at is not None else None
                ),
                dispatched_dates=dispatched_dates,
            )
        return datetime.combine(candidate, reminder_time, tzinfo=VN_TZ)
    except OverflowError:
        # Positive intervals have no write-side upper bound. An unrepresentable
        # projection must not make an otherwise-readable tracker fail with 500.
        return None
