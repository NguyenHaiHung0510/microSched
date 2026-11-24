"""Date membership shared by the Calendar store and its bounded STANDARD reader."""

from datetime import date, datetime

from sqlalchemy import and_

from app.domain.models import CalendarEvent, CalendarSource, DayAnnotation


def event_overlap(start: datetime, stop: datetime):
    """A timed event occupies [starts_at, ends_at); touching edges do not overlap."""
    return and_(CalendarEvent.starts_at < stop, CalendarEvent.ends_at > start)


def annotation_overlap(first: date, last: date):
    """Day annotations include both dates."""
    return and_(DayAnnotation.starts_on <= last, DayAnnotation.ends_on >= first)


def from_visible_calendar_sources(stmt):
    return stmt.join_from(
        CalendarEvent, CalendarSource, CalendarSource.id == CalendarEvent.source_id
    ).where(CalendarSource.is_visible.is_(True))
