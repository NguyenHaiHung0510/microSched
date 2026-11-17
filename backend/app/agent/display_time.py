"""A projection for Mimi's human-facing instants; never a storage or lease clock."""

from datetime import datetime

from app.domain.tasks import VIETNAM_TZ


def vietnam_display_time(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("mimi_display_time_requires_offset")
    return value.astimezone(VIETNAM_TZ)
