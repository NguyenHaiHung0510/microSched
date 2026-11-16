"""Provider audio lifecycle for Voice v2. Captions never grant write authority."""

from __future__ import annotations

import re
from dataclasses import dataclass

FAST_APPLY_MAX = 5


def offset_ms(value) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,6}(?:\.\d{1,9})?s", value):
        return None
    whole, _, fraction = value[:-1].partition(".")
    return int(whole) * 1000 + int((fraction + "000")[:3])


@dataclass(frozen=True)
class VoiceTurnBinding:
    epoch: int
    turn: int
    call_ids: tuple[str, ...]
    start_ms: int
    end_ms: int

    def matches(self, turn, epoch, count):
        return (
            self.epoch == epoch
            and epoch > 0
            and self.turn == turn
            and turn > 0
            and 0 <= self.start_ms < self.end_ms
            and len(self.call_ids) == count
            and len(set(self.call_ids)) == count
            and all(self.call_ids)
        )


@dataclass
class SpeechWindow:
    """Only ordered VAD offsets in actually forwarded PCM bind an activity.

    Gemini supplies no input turn ID. The bridge assigns a local turn and epoch,
    requires a fresh activity, and fences concurrent activity/cancel/tool events.
    Unlabelled or stale captions are display data only.
    """

    floor_ms: int = -1
    start_ms: int | None = None
    end_ms: int | None = None
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

    def bind(self, epoch, turn, call_ids):
        if self.uncertain or self.start_ms is None or self.end_ms is None:
            return None
        return VoiceTurnBinding(epoch, turn, tuple(call_ids), self.start_ms, self.end_ms)

    def is_retired(self, event):
        end = offset_ms(event.get("endOffset")) if isinstance(event, dict) else None
        return end is not None and end <= self.floor_ms

    def next(self, retired_through_ms):
        return SpeechWindow(floor_ms=max(self.floor_ms, retired_through_ms, self.end_ms or -1))
