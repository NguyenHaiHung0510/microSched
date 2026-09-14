"""Deterministic test doubles for later Mimi orchestration slices."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        self.current += delta
        return self.current


class FaultBarrier:
    """Expose a deterministic in-flight point without sleeping in a test."""

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.release = asyncio.Event()

    async def wait(self) -> None:
        self.reached.set()
        await self.release.wait()


@dataclass
class FakeProvider:
    scripted: deque[dict[str, Any] | Exception]
    barrier: FaultBarrier | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        if self.barrier is not None:
            await self.barrier.wait()
        if not self.scripted:
            raise RuntimeError("fake provider script exhausted")
        outcome = self.scripted.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
