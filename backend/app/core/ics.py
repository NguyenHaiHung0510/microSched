"""Small, deliberately defensive iCalendar parser for calendar imports."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

VIETNAM_TZ = timezone(timedelta(hours=7))
DEFAULT_DURATION = timedelta(minutes=90)
MAX_BYTES = 1_048_576
MAX_EVENTS = 5000

_KNOWN_PROPERTIES = {
    "BEGIN",
    "END",
    "VERSION",
    "PRODID",
    "UID",
    "CLASS",
    "SUMMARY",
    "DESCRIPTION",
    "LOCATION",
    "DTSTART",
    "DTEND",
    "DTSTAMP",
    "DURATION",
    "TRANSP",
    "STATUS",
    "CATEGORIES",
    "RRULE",
    "RDATE",
    "EXDATE",
    "SEQUENCE",
    "CREATED",
    "LAST-MODIFIED",
    "ORGANIZER",
    "ATTENDEE",
    "URL",
    "GEO",
    "PRIORITY",
}
_UNSUPPORTED_PROPERTIES = {"RRULE", "RDATE", "EXDATE", "DURATION"}


@dataclass(frozen=True)
class ParsedEvent:
    """One normalized event ready for insertion."""

    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    location: str | None
    description_md: str | None


@dataclass(frozen=True)
class ParseReport:
    """Parser output and safe, content-free skip reasons."""

    events: list[ParsedEvent]
    skipped: list[str]
    duplicates: int


def _property_name(line: str) -> str | None:
    """Return the base property name without parameters, if this is a content line."""
    colon = line.find(":")
    if colon < 1:
        return None
    return line[:colon].split(";", 1)[0].upper()


def _is_known_property(line: str) -> bool:
    name = _property_name(line)
    return name is not None and (name in _KNOWN_PROPERTIES or name.startswith("X-"))


def _unfold(lines: list[str]) -> list[str]:
    """Unfold RFC continuation lines and the exporter-specific broken descriptions."""
    unfolded_parts: list[list[str]] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded_parts:
            unfolded_parts[-1].append(line[1:])
        elif _is_known_property(line) or not unfolded_parts:
            unfolded_parts.append([line])
        else:
            unfolded_parts[-1].extend(("\n", line))
    return ["".join(parts) for parts in unfolded_parts]


def _unescape(value: str) -> str:
    """Decode iCalendar text escapes after unfolding, without creating fake lines."""
    decoded: list[str] = []
    index = 0
    replacements = {"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            next_char = value[index + 1]
            decoded.append(replacements.get(next_char, next_char))
            index += 2
            continue
        decoded.append(char)
        index += 1
    return "".join(decoded)


def _properties(lines: list[str]) -> dict[str, list[tuple[str, str]]]:
    result: dict[str, list[tuple[str, str]]] = {}
    for line in lines:
        colon = line.find(":")
        if colon < 1:
            continue
        left, value = line[:colon], line[colon + 1 :]
        parts = left.split(";")
        name = parts[0].upper()
        result.setdefault(name, []).append((";".join(parts[1:]).upper(), value))
    return result


def _parse_datetime(value: str) -> datetime | None:
    """Parse one supported date/time value without consulting the host timezone."""
    try:
        if value.endswith("Z"):
            return datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(
                tzinfo=UTC
            ).astimezone(VIETNAM_TZ)
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=VIETNAM_TZ)
    except ValueError:
        return None


def _parse_start(value: str, params: str) -> tuple[datetime | None, bool]:
    if "TZID=" in params:
        return None, False
    if len(value) == 8:
        try:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=VIETNAM_TZ), True
        except ValueError:
            return None, False
    return _parse_datetime(value), False


def _parse_end(value: str, *, all_day: bool) -> datetime | None:
    if all_day and len(value) == 8:
        try:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=VIETNAM_TZ)
        except ValueError:
            return None
    if all_day:
        return None
    return _parse_datetime(value)


def parse_ics(text: str) -> ParseReport:
    """Parse supported VEVENTs, rejecting unsafe or ambiguous input early."""
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("ICS content exceeds the maximum size")
    lines = text.splitlines()
    if sum(line.upper() == "BEGIN:VEVENT" for line in lines) > MAX_EVENTS:
        raise ValueError("ICS contains too many events")
    lines = _unfold(lines)
    event_blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.upper() == "BEGIN:VEVENT":
            current = []
        elif line.upper() == "END:VEVENT":
            if current is not None:
                event_blocks.append(current)
            current = None
        elif current is not None:
            current.append(line)

    events: list[ParsedEvent] = []
    skipped: list[str] = []
    seen: set[tuple[str, datetime, datetime, str | None]] = set()
    duplicates = 0

    for number, block in enumerate(event_blocks, start=1):
        properties = _properties(block)
        unsupported = next(
            (name for name in _UNSUPPORTED_PROPERTIES if name in properties), None
        )
        start_entries = properties.get("DTSTART", [])
        if unsupported is not None:
            skipped.append(
                f"Bỏ qua buổi #{number}: có {unsupported} (lịch lặp hoặc thời lượng chưa hỗ trợ)"
            )
            continue
        if not start_entries:
            skipped.append(f"Bỏ qua buổi #{number}: thiếu thời gian bắt đầu")
            continue
        start_params, start_value = start_entries[0]
        starts_at, all_day = _parse_start(start_value, start_params)
        if starts_at is None:
            reason = (
                "múi giờ TZID chưa hỗ trợ"
                if "TZID=" in start_params
                else "thời gian bắt đầu không hợp lệ"
            )
            skipped.append(f"Bỏ qua buổi #{number}: {reason}")
            continue

        title_entries = properties.get("SUMMARY", [])
        title = _unescape(title_entries[0][1]).strip() if title_entries else ""
        if not title:
            skipped.append(f"Bỏ qua buổi #{number}: thiếu tiêu đề")
            continue

        end_entries = properties.get("DTEND", [])
        ends_at: datetime
        if all_day and not end_entries:
            ends_at = starts_at + timedelta(days=1)
        elif end_entries:
            end_params, end_value = end_entries[0]
            if "TZID=" in end_params:
                skipped.append(f"Bỏ qua buổi #{number}: múi giờ TZID chưa hỗ trợ")
                continue
            fallback_end = starts_at + (timedelta(days=1) if all_day else DEFAULT_DURATION)
            ends_at = _parse_end(end_value, all_day=all_day) or fallback_end
        else:
            ends_at = starts_at + (timedelta(days=1) if all_day else DEFAULT_DURATION)
        if ends_at <= starts_at:
            ends_at = starts_at + (timedelta(days=1) if all_day else DEFAULT_DURATION)

        location = None
        if location_entries := properties.get("LOCATION"):
            location = _unescape(location_entries[0][1]).strip() or None
        description = None
        if description_entries := properties.get("DESCRIPTION"):
            description = _unescape(description_entries[0][1]).strip() or None

        key = (title, starts_at, ends_at, location)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        events.append(
            ParsedEvent(
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=all_day,
                location=location,
                description_md=description,
            )
        )

    return ParseReport(events=events, skipped=skipped, duplicates=duplicates)
