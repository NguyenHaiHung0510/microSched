"""Forecast only. Local firmware evaluates opportunities and admits watering."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from app.domain.migarden.wire import (
    ConfigurationBundle,
    Daily,
    Interval,
    Once,
    Schedule,
    Weekly,
    WireModel,
)

HANOI = timedelta(hours=7)
ONE_MINUTE = timedelta(minutes=1)
ONE_DAY = timedelta(days=1)


def local_day(at: datetime) -> date:
    return (at + HANOI).date()


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, UTC) - HANOI


class Forecast(WireModel):
    status: Literal["no_applied_config", "paused", "no_future_occurrence", "scheduled"]
    config_ref: str | None = None
    next_at: datetime | None = None
    day: date | None = None
    duration_seconds: int | None = None
    day_total_seconds: int | None = None


def first_at_or_after(schedule: Schedule, lower: datetime) -> datetime | None:
    lower = max(lower, schedule.effective_from)
    pattern = schedule.recurrence
    if isinstance(pattern, Once):
        candidate = pattern.at if pattern.at >= lower else None
    elif isinstance(pattern, Interval):
        step = timedelta(minutes=pattern.interval_minutes)
        elapsed = lower - pattern.anchor_at
        count = max(0, -(-elapsed // step))
        try:
            candidate = pattern.anchor_at + step * count
        except OverflowError:
            candidate = None
    else:
        assert isinstance(pattern, (Daily, Weekly))
        hour, minute = map(int, pattern.at_local_time.split(":"))
        candidate = None
        for offset in range(8):
            day = local_day(lower) + timedelta(days=offset)
            if isinstance(pattern, Weekly) and day.isoweekday() not in pattern.days_of_week:
                continue
            slot = day_start(day) + timedelta(hours=hour, minutes=minute)
            if slot >= lower:
                candidate = slot
                break
    if (
        candidate is not None
        and schedule.effective_until is not None
        and candidate >= schedule.effective_until
    ):
        return None
    return candidate


def forecast(bundle: ConfigurationBundle | None, now: datetime) -> Forecast:
    if bundle is None:
        return Forecast(status="no_applied_config")
    schedule = bundle.schedule
    if not schedule.enabled:
        return Forecast(status="paused", config_ref=bundle.config_ref)
    next_at = first_at_or_after(schedule, now + timedelta(microseconds=1))
    if next_at is None:
        return Forecast(status="no_future_occurrence", config_ref=bundle.config_ref)
    day = local_day(next_at)
    count = 1
    if isinstance(schedule.recurrence, Interval):
        end = day_start(day) + ONE_DAY
        if schedule.effective_until is not None:
            end = min(end, schedule.effective_until)
        step = ONE_MINUTE * schedule.recurrence.interval_minutes
        count = -(-(end - next_at) // step)
    return Forecast(
        status="scheduled",
        config_ref=bundle.config_ref,
        next_at=next_at,
        day=day,
        duration_seconds=schedule.duration_seconds,
        day_total_seconds=count * schedule.duration_seconds,
    )
