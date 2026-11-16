"""Correlate provider ASR with current audio; prove only exact whole spoken commands."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from app.agent.task_collection import PreparedCollection

FAST_APPLY_MAX = 5
_SLOP_MS = 300
_COUNTS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "một": 1,
    "two": 2,
    "hai": 2,
    "three": 3,
    "ba": 3,
    "four": 4,
    "bốn": 4,
    "five": 5,
    "năm": 5,
    "six": 6,
    "sáu": 6,
    "seven": 7,
    "bảy": 7,
    "eight": 8,
    "tám": 8,
    "nine": 9,
    "chín": 9,
    "ten": 10,
    "mười": 10,
}


def offset_ms(value) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,6}(?:\.\d{1,9})?s", value):
        return None
    whole, _, fraction = value[:-1].partition(".")
    return int(whole) * 1000 + int((fraction + "000")[:3])


@dataclass
class SpeechWindow:
    # A Live tool call and caption are not proof of the audio window. VAD and
    # final ASR must agree. Transcript offsets are optional extra evidence.
    floor_ms: int = -1
    start_ms: int | None = None
    end_ms: int | None = None
    spans: list[tuple[int | None, int | None, str]] = field(default_factory=list)
    uncertain: bool = False
    conflicted: bool = False

    def activity(self, event, forwarded_ms):
        if not isinstance(event, dict):
            self.uncertain = True
            return
        offset = offset_ms(event.get("audioOffset"))
        if offset is None or offset <= self.floor_ms or offset > forwarded_ms:
            self.uncertain = True
        elif event.get("type") == "ACTIVITY_START" and self.start_ms is None:
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
            self.conflicted = True

    def transcript(self, event, forwarded_ms):
        # inputTranscription is final. interimInputTranscription is handled
        # separately; a compatibility finished=False never grants authority.
        if event.get("finished") is False:
            return
        text = event.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return
        start, end = offset_ms(event.get("startOffset")), offset_ms(event.get("endOffset"))
        timed = "startOffset" in event or "endOffset" in event
        if timed and (
            start is None or end is None or not self.floor_ms < start < end <= forwarded_ms
        ):
            self.uncertain = True
            self.conflicted = True
            return
        if len(self.spans) >= 64 or (
            self.spans and (not timed or self.spans[-1][1] is None or start < self.spans[-1][1])
        ):
            self.uncertain = True
            self.conflicted = True
            return
        self.spans.append((start, end, text))

    def is_retired(self, event) -> bool:
        end = offset_ms(event.get("endOffset")) if isinstance(event, dict) else None
        if end is not None:
            return end <= self.floor_ms
        # An unlabelled final arriving between utterances cannot be reassigned
        # to the next command. First-utterance events may precede VAD.
        return self.floor_ms >= 0 and self.start_ms is None

    def prove(self) -> str | None:
        if self.uncertain or self.start_ms is None or self.end_ms is None or not self.spans:
            return None
        if self.spans[0][0] is not None and (
            abs(self.spans[0][0] - self.start_ms) > _SLOP_MS
            or abs(self.spans[-1][1] - self.end_ms) > _SLOP_MS
            or any(b[0] - a[1] > _SLOP_MS for a, b in zip(self.spans, self.spans[1:]))
        ):
            return None
        return " ".join(text.strip() for _, _, text in self.spans if text.strip()) or None

    def next(self, retired_through_ms):
        # A delayed transcription from a retired turn can't become fresh.
        end = max(
            [
                self.floor_ms,
                retired_through_ms,
                self.end_ms or -1,
                *(s[1] for s in self.spans if s[1] is not None),
            ]
        )
        return SpeechWindow(floor_ms=end)


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().strip().split())


def title_matches(spoken: str, candidate: str) -> bool:
    """Only a canonical bracket prefix may differ; literal punctuation stays exact."""
    spoken, candidate = normalized(spoken), normalized(candidate)
    if spoken == candidate:
        return True
    if "[" in spoken or "]" in spoken:
        return False
    prefix = re.fullmatch(r"\[([^\W_]+(?: [^\W_]+){0,3})\]\s*(.+)", candidate)
    return bool(prefix and spoken == f"{prefix[1]} {prefix[2]}")


def whole_command(text: str | None, *, limit=1400) -> str:
    if not text or len(text) > limit or any(c in text for c in '?!“”"'):
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
        "hoàn tác thay đổi vừa rồi",
        "undo the last change",
        "undo latest",
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
    scope = create_scope(text, today)
    return list(scope.names or ()) if scope is not None and not scope.ambiguous else []


@dataclass(frozen=True)
class CreateScope:
    count: int | None
    names: tuple[tuple[str, str | None], ...] | None
    ambiguous: bool = False


def create_scope(text: str | None, today: date | None) -> CreateScope | None:
    """Capture a declared count/list independently of the model's proposal size."""
    value = whole_command(text, limit=16_384)
    prefix = re.match(r"^(?:tạo|thêm|create|add)\s+", value)
    if not prefix:
        return None
    rest = value[prefix.end() :]
    header = re.match(
        r"(?:(các|những|the following|the|\d{1,3}|" + "|".join(_COUNTS) + r")\s+)?"
        r"(?:new\s+)?(?:công việc|việc|tasks?)\b(.*)$",
        rest,
    )
    if not header:
        return None
    quantifier, tail = header.groups()
    count = (
        int(quantifier)
        if quantifier and quantifier.isascii() and quantifier.isdigit()
        else _COUNTS.get(quantifier)
    )
    tail = re.sub(
        r"^[ :]*(?:(?:sau đây|sau|có tên|tên|gọi là|bao gồm|gồm|named|called|as follows)"
        r"[ :]*)?",
        "",
        tail,
    ).strip()
    if not tail:
        return CreateScope(count, None, ambiguous=count is None)
    # Rich content/generation requires manual review; its declared target count
    # is still a binding. A named range or ellipsis is not an enumerated set.
    if re.search(r"\b(?:đến|through|until|vân vân|etc)\b|\.{2,}|…", tail):
        return CreateScope(count, None, ambiguous=True)
    if re.search(
        r"\b(?:mô tả|nội dung|checklist|description|body|với các bước|with steps)\b", tail
    ):
        return CreateScope(count, None)
    labels = _labels(tail)
    values = tuple(_create_values(label, today) for label in labels)
    plural = quantifier in {"các", "những", "the following", "the"}
    ambiguous = (
        not values
        or any(not name for name, _ in values)
        or (count is not None and count != len(values))
        or (plural and len(values) < 2)
        or len({title for title, _ in values}) != len(values)
    )
    return CreateScope(count or len(values), values, ambiguous)


def spoken_edit_targets(text: str | None) -> list[str] | None:
    value = whole_command(text)
    for pattern in (
        r"(?:hoàn thành|complete|mở lại|reopen) "
        r"(?:(?:các |những |the )?(?:tasks?|việc|công việc) )?(.+)",
        r"(?:đổi tên|rename)(?: task| việc)? (.+?) (?:thành|to) .+",
        r"(?:đặt ưu tiên|set priority)(?: task| việc)? (.+?) (?:thành|to) p[123]",
    ):
        if match := re.fullmatch(pattern, value):
            return _labels(match[1])
    return None


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
            and title_matches(title, entry.after["fields"]["title"])
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
        (
            r"(?:hoàn thành|complete) (?:(?:các |những |the )?(?:tasks?|việc|công việc) )?(.+)",
            {"status": "completed"},
        ),
        (
            r"(?:mở lại|reopen) (?:(?:các |những |the )?(?:tasks?|việc|công việc) )?(.+)",
            {"status": "open"},
        ),
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
