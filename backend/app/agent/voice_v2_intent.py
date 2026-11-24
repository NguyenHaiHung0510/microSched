"""Provider audio lifecycle for Voice v2. Captions never grant write authority."""

from __future__ import annotations

import re
from dataclasses import dataclass

FAST_APPLY_MAX = 5
SAMPLE_RATE = 16_000
# A finite proof suffix; an older window can still bind if the retained part
# contains signal. No audio values are retained, only sample-presence bits.
SIGNAL_WINDOW_SAMPLES = 30 * SAMPLE_RATE


def _offset_ns(value) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,6}(?:\.\d{1,9})?s", value):
        return None
    whole, _, fraction = value[:-1].partition(".")
    return int(whole) * 1_000_000_000 + int(fraction.ljust(9, "0"))


def offset_ms(value) -> int | None:
    ns = _offset_ns(value)
    return None if ns is None else ns // 1_000_000


def _sample_at_or_after(ns):
    return (ns * SAMPLE_RATE + 999_999_999) // 1_000_000_000


class SignalWindow:
    def __init__(self, floor=0):
        self.total = self.floor = floor
        self._presence = bytearray(SIGNAL_WINDOW_SAMPLES)

    def record(self, pcm):
        flags = bytes(sample != 0 for sample in memoryview(pcm).cast("H"))
        index = self.total % SIGNAL_WINDOW_SAMPLES
        first = min(len(flags), SIGNAL_WINDOW_SAMPLES - index)
        self._presence[index : index + first] = flags[:first]
        if first != len(flags):
            self._presence[: len(flags) - first] = flags[first:]
        self.total += len(flags)

    def contains(self, start, end):
        start = max(start, self.floor, self.total - SIGNAL_WINDOW_SAMPLES)
        end = min(end, self.total)
        if end <= start:
            return False
        index = start % SIGNAL_WINDOW_SAMPLES
        first = min(end - start, SIGNAL_WINDOW_SAMPLES - index)
        return (
            self._presence.find(b"\x01", index, index + first) != -1
            or self._presence.find(b"\x01", 0, end - start - first) != -1
        )


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
    start_sample: int | None = None
    end_sample: int | None = None

    def has_signal(self, signal):
        return (
            self.start_sample is not None
            and self.end_sample is not None
            and signal.contains(self.start_sample, self.end_sample)
        )

    def activity(self, event, forwarded_ms):
        if not isinstance(event, dict):
            self.uncertain = True
            return
        ns = _offset_ns(event.get("audioOffset"))
        if ns is None:
            self.uncertain = True
            return
        offset = ns // 1_000_000
        if offset <= self.floor_ms or ns > forwarded_ms * 1_000_000:
            self.uncertain = True
        elif event.get("type") == "ACTIVITY_START" and self.start_ms is None:
            self.start_ms = offset
            self.start_sample = _sample_at_or_after(ns)
        elif (
            event.get("type") == "ACTIVITY_END"
            and self.start_ms is not None
            and self.end_ms is None
            and offset > self.start_ms
        ):
            self.end_ms = offset
            self.end_sample = _sample_at_or_after(ns)
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
