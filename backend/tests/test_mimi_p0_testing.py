"""Runnable fake-provider/clock/barrier smoke for later Mimi tests."""

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.testing import FakeClock, FakeProvider, FaultBarrier


def test_fake_clock_is_stable_and_explicitly_advanced() -> None:
    clock = FakeClock(datetime(2030, 1, 15, 8, tzinfo=UTC))
    assert clock.now() == datetime(2030, 1, 15, 8, tzinfo=UTC)
    assert clock.advance(timedelta(minutes=30)) == datetime(2030, 1, 15, 8, 30, tzinfo=UTC)


def test_fake_provider_reproduces_failure() -> None:
    provider = FakeProvider(deque([RuntimeError("synthetic upstream failure")]))
    with pytest.raises(RuntimeError, match="synthetic upstream failure"):
        asyncio.run(provider.complete({"input": "fixture"}))
    assert provider.calls == [{"input": "fixture"}]


def test_fault_barrier_reproduces_an_inflight_delay_without_sleeping() -> None:
    async def scenario() -> None:
        barrier = FaultBarrier()
        provider = FakeProvider(deque([{"output": "done"}]), barrier=barrier)
        pending = asyncio.create_task(provider.complete({"input": "fixture"}))
        await barrier.reached.wait()
        assert pending.done() is False
        barrier.release.set()
        assert await pending == {"output": "done"}

    asyncio.run(scenario())
