"""Correlate provider ASR with current audio; prove only exact whole spoken commands."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from app.agent.task_collection import PreparedCollection

FAST_APPLY_MAX = 5
_SLOP_MS = 300


def offset_ms(value) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,6}(?:\.\d{1,9})?s", value):
        return None
    whole, _, fraction = value[:-1].partition(".")
    return int(whole) * 1000 + int((fraction + "000")[:3])


@dataclass
class SpeechWindow:
    # A Live tool call and caption are not proof of the audio window. VAD and
    # timestamped final ASR must agree. All fields are in-memory and per socket.
    floor_ms: int = -1
    start_ms: int | None = None
    end_ms: int | None = None
    spans: list[tuple[int, int, str]] = field(default_factory=list)
    uncertain: bool = False

    def activity(self, event, forwarded_ms):
        if not isinstance(event, dict):
            self.uncertain = True
            return
        offset = offset_ms(event.get("audioOffset"))
        if offset is None or offset <= self.floor_ms or offset > forwarded_ms:
            self.uncertain = True
        elif event.get("type") == "ACTIVITY_START" and self.start_ms is None and not self.spans:
            self.start_ms = offset
        elif (
            event.get("type") == "ACTIVITY_END"
            and self.start_ms is not None
            and self.end_ms is None
            and offset > self.start_ms
        ):
            self.end_ms = offset
        else:
            self.uncertain = True

    def transcript(self, event, forwarded_ms):
        start, end = offset_ms(event.get("startOffset")), offset_ms(event.get("endOffset"))
        text = event.get("text", "")
        if (
            start is None
            or end is None
            or not self.floor_ms < start < end <= forwarded_ms
            or len(self.spans) >= 64
            or event.get("finished") is False
        ):
            self.uncertain = True
            return
        if self.spans and start < self.spans[-1][1]:
            self.uncertain = True
            return
        self.spans.append((start, end, text))

    def is_retired(self, event) -> bool:
        end = offset_ms(event.get("endOffset")) if isinstance(event, dict) else None
        return end is not None and end <= self.floor_ms

    def prove(self) -> str | None:
        if (
            self.uncertain
            or self.start_ms is None
            or self.end_ms is None
            or not self.spans
            or abs(self.spans[0][0] - self.start_ms) > _SLOP_MS
            or abs(self.spans[-1][1] - self.end_ms) > _SLOP_MS
            or any(b[0] - a[1] > _SLOP_MS for a, b in zip(self.spans, self.spans[1:]))
        ):
            return None
        return " ".join(text.strip() for _, _, text in self.spans if text.strip()) or None

    def next(self, retired_through_ms):
        # A delayed transcription from a retired turn can't become fresh.
        end = max(
            [self.floor_ms, retired_through_ms, self.end_ms or -1, *(s[1] for s in self.spans)]
        )
        return SpeechWindow(floor_ms=end)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().strip().split())


def whole_command(text: str | None) -> str:
    if not text or len(text) > 1400 or any(c in text for c in '?!“”"'):
        return ""
    value = normalized(text).removesuffix(".")
    value = re.sub(r"^(?:mimi[,:]? |please |hãy )+", "", value)
    return value.removesuffix(" giúp tôi").removesuffix(" please")


def spoken_undo(text: str | None) -> bool:
    return whole_command(text) in {
        "hoàn tác",
        "hoàn tác cái vừa làm",
        "hoàn tác lần áp dụng vừa rồi",
        "hoàn tác thay đổi voice vừa rồi",
        "undo",
        "undo last voice change",
        "undo the last voice change",
    }


def _labels(value: str) -> list[str]:
    labels = re.split(r"\s*[,;]\s*|\s+(?:and|và)\s+", value)
    if any(
        not name
        or not any(c.isalnum() for c in name)
        or re.search(
            r"\b(?:then|instead|cancel|delete|reopen|rename|don't|not|if|"
            r"sau đó|đừng|không|nếu|thay vì|xóa|đổi tên|mở lại|tạo việc|tạo task)\b",
            name,
        )
        for name in labels
    ):
        return []
    return labels if len(labels) == len(set(labels)) else []


def _create_values(label: str, today: date | None):
    parts = re.fullmatch(
        r"(.+?) (?:due(?: on)?|hạn(?: ngày)?) "
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|hôm nay|ngày mai|ngày kia|today|tomorrow)",
        label,
    )
    if not parts:
        return label, None
    title, day = parts.groups()
    try:
        if "/" in day:
            d, m, y = map(int, day.split("/"))
            return title, date(y, m, d).isoformat()
        if "-" in day:
            return title, date.fromisoformat(day).isoformat()
        if today:
            future = {"today": 0, "hôm nay": 0, "tomorrow": 1, "ngày mai": 1, "ngày kia": 2}
            return title, date.fromordinal(today.toordinal() + future[day]).isoformat()
        return "", None
    except ValueError:
        return "", None


def spoken_creates(text: str | None, today: date | None):
    create = re.fullmatch(
        r"(?:tạo (?:công việc|task|việc)|create (?:a )?tasks?)"
        r"(?: (?:tên|gọi là|named|called))?(?:[ :]+)(.+)",
        whole_command(text),
    )
    return [_create_values(label, today) for label in _labels(create[1])] if create else []


def exact_plan_match(
    text: str | None, plan: PreparedCollection, *, today: date | None = None
) -> bool:
    """Compare the entire speech against every target and every authorized field.

    Broad natural-language edits still get typed previews. The quick path
    deliberately does not guess references, omitted items, dates or content.
    """
    command = whole_command(text)
    entries = plan.entries
    if not command or not 1 <= len(entries) <= FAST_APPLY_MAX:
        return False
    if any(
        entry.command.children
        or entry.command.reminder.action != "keep"
        or entry.reminder_effect["action"] not in {"keep", "none"}
        for entry in entries
    ):
        return False
    if values := spoken_creates(text, today):
        if len(values) != len(entries) or len({title for title, _ in values}) != len(entries):
            return False
        return all(
            entry.command.action == "create"
            and normalized(entry.after["fields"]["title"]) == title
            and entry.after["fields"]["due_on"] == due
            and entry.after["fields"]["due_precision"] == ("date" if due else "none")
            and entry.after["fields"]["body_md"] is None
            and entry.after["fields"]["priority"] is None
            and entry.after["fields"]["pinned"] is False
            and entry.after["fields"]["status"] == "open"
            and entry.after["fields"]["due_at"] is None
            for entry, (title, due) in zip(entries, values, strict=True)
        )
    if any(entry.command.action != "edit" or not entry.before for entry in entries):
        return False
    titles = [normalized(entry.before["fields"]["title"]) for entry in entries]
    if len(titles) != len(set(titles)):
        return False
    rename = re.fullmatch(r"(?:đổi tên|rename)(?: task| việc)? (.+?) (?:thành|to) (.+)", command)
    if rename:
        fields = entries[0].command.fields
        return (
            len(entries) == 1
            and titles == [rename[1]]
            and set(fields) == {"title"}
            and _labels(rename[2]) == [rename[2]]
            and normalized(fields["title"]) == rename[2]
        )
    for pattern, fields in (
        (r"(?:hoàn thành|complete) (?:task |việc )?(.+)", {"status": "completed"}),
        (r"(?:mở lại|reopen) (?:task |việc )?(.+)", {"status": "open"}),
    ):
        if match := re.fullmatch(pattern, command):
            return _labels(match[1]) == titles and all(
                entry.command.fields == fields for entry in entries
            )
    if match := re.fullmatch(
        r"(?:đặt ưu tiên|set priority)(?: task| việc)? (.+?) (?:thành|to) (p[123])",
        command,
    ):
        return _labels(match[1]) == titles and all(
            entry.command.fields == {"priority": match[2]} for entry in entries
        )
    return False
