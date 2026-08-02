"""Pure parser coverage for the intentionally quirky calendar exporter shape."""

import time
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.ics import MAX_BYTES, MAX_EVENTS, parse_ics

FIXTURE = Path(__file__).parent / "fixtures" / "quirky.ics"


def test_quirky_fixture_preserves_metadata_and_safe_timezone() -> None:
    report = parse_ics(FIXTURE.read_text(encoding="utf-8"))

    assert len(report.events) == 5
    assert report.duplicates == 1
    assert len(report.skipped) == 4
    assert len(report.events) + report.duplicates + len(report.skipped) == 10

    first = report.events[0]
    assert first.starts_at.isoformat() == "2026-08-15T07:00:00+07:00"
    assert first.description_md is not None
    assert first.description_md.count("\n") + 1 == 6
    assert [line.split(":", 1)[0] for line in first.description_md.splitlines()] == [
        "Mã môn",
        "Nhóm thi",
        "Tổ thi",
        "Hình thức",
        "Thời gian",
        "Kỳ thi",
    ]
    assert first.location == "Phòng A, tầng 3"
    assert all("UID" not in repr(event) for event in report.events)

    escaped = next(event for event in report.events if event.title.startswith("Ôn tập"))
    assert escaped.title == "Ôn tập, phần 1"
    assert escaped.description_md == "Dòng một\nDòng hai"
    assert escaped.ends_at - escaped.starts_at == timedelta(minutes=90)

    all_day = next(event for event in report.events if event.title == "Ngày cả ngày")
    assert all_day.all_day is True
    assert all_day.ends_at - all_day.starts_at == timedelta(days=1)

    utc_event = next(event for event in report.events if event.title == "Giờ UTC")
    assert utc_event.starts_at.isoformat() == "2026-08-15T08:00:00+07:00"

    labeled = next(event for event in report.events if event.title == "Mô tả có nhãn")
    assert labeled.description_md == "Phần đầu\nNote: mang thẻ\nPhần cuối"
    assert any("RRULE" in reason for reason in report.skipped)
    assert any("TZID" in reason for reason in report.skipped)
    assert any("thiếu tiêu đề" in reason for reason in report.skipped)


def test_parser_does_not_depend_on_host_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "UTC")
    content = "\n".join(
        [
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:UTC independent",
            "DTSTART:20260815T070000",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )
    report = parse_ics(content)
    assert report.events[0].starts_at.isoformat() == "2026-08-15T07:00:00+07:00"


def test_parser_checks_utf8_bytes_before_parsing() -> None:
    with pytest.raises(ValueError, match="maximum size"):
        parse_ics("ấ" * ((MAX_BYTES // 2) + 1))


def test_parser_rejects_too_many_events_before_deep_parse() -> None:
    content = "\n".join(
        ["BEGIN:VCALENDAR"] + ["begin:vevent\nEND:VEVENT"] * (MAX_EVENTS + 1) + ["END:VCALENDAR"]
    )
    with pytest.raises(ValueError, match="too many events"):
        parse_ics(content)


@pytest.mark.parametrize("dtend", [None, "DTEND:broken", "DTEND:20260814", "DTEND:20260815"])
def test_all_day_missing_invalid_or_non_increasing_end_uses_next_day(
    dtend: str | None,
) -> None:
    lines = [
        "BEGIN:VCALENDAR",
        "BEGIN:VEVENT",
        "SUMMARY:All day fallback",
        "DTSTART;VALUE=DATE:20260815",
    ]
    if dtend is not None:
        lines.append(dtend)
    lines.extend(["END:VEVENT", "END:VCALENDAR"])

    report = parse_ics("\n".join(lines))

    assert len(report.events) == 1
    assert report.events[0].ends_at - report.events[0].starts_at == timedelta(days=1)


def test_dtend_tzid_is_skipped_without_echoing_timezone_content() -> None:
    report = parse_ics(
        "\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "SUMMARY:Unsupported end timezone",
                "DTSTART:20260815T070000",
                "DTEND;TZID=Some/PrivateZone:20260815T080000",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
    )

    assert report.events == []
    assert report.skipped == ["Bỏ qua buổi #1: múi giờ TZID chưa hỗ trợ"]


def test_parser_unfold_is_linear_for_large_folded_description() -> None:
    content = "\n".join(
        [
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:Large description",
            "DTSTART:20260815T070000",
            "DESCRIPTION:x",
            *(" x" for _ in range(200_000)),
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )
    started = time.perf_counter()
    report = parse_ics(content)
    elapsed = time.perf_counter() - started
    assert len(report.events) == 1
    assert elapsed < 2
