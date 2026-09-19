"""Process-owned Mimi run lifecycle remains independent from observation."""

import asyncio
from uuid import uuid7

from app.agent.runtime import MimiRunSupervisor


def test_supervisor_keeps_work_alive_until_explicit_cancel() -> None:
    async def scenario() -> None:
        supervisor = MimiRunSupervisor()
        run_id = uuid7()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def work() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        supervisor.start(run_id, work())
        await started.wait()
        assert supervisor.active(run_id)
        # No observer handle participates in ownership. Only the explicit
        # supervisor cancel path terminates the server-owned coroutine.
        await asyncio.sleep(0)
        assert supervisor.active(run_id)
        assert supervisor.cancel(run_id)
        await cancelled.wait()
        await asyncio.sleep(0)
        assert not supervisor.active(run_id)
        await supervisor.stop()

    asyncio.run(scenario())


def test_supervisor_shutdown_cancels_all_active_work() -> None:
    async def scenario() -> None:
        supervisor = MimiRunSupervisor()
        run_ids = [uuid7(), uuid7()]
        completed = 0

        async def work() -> None:
            nonlocal completed
            try:
                await asyncio.Event().wait()
            finally:
                completed += 1

        for run_id in run_ids:
            supervisor.start(run_id, work())
        await asyncio.sleep(0)
        await supervisor.stop()
        assert completed == 2
        assert all(not supervisor.active(run_id) for run_id in run_ids)

    asyncio.run(scenario())
