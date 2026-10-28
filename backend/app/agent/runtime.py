"""Process-owned supervision for active Mimi runs.

Durable state lives in PostgreSQL. This registry only owns live coroutine
lifetimes so an HTTP disconnect does not cancel provider work accidentally.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from app.core.db import get_engine
from app.core.settings import get_settings

logger = logging.getLogger(__name__)


class OwnerPauseRequested(Exception):
    """Pause after a durable boundary, without cancelling a paid dispatch."""


def run_guard_key(run_id: UUID) -> int:
    """Namespace a signed PostgreSQL advisory key to one durable Mimi run."""

    digest = hashlib.sha256(b"microsched.mimi.run.v1:" + run_id.bytes).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def hold_run_guard(run_id: UUID):
    """Keep one transaction lock while this process can dispatch a provider call.

    A crashed process releases the PostgreSQL lock, without a periodic Neon
    heartbeat. The lock is operational ownership, not user/model authority.
    """

    engine = get_engine()
    if engine is None:
        raise RuntimeError("mimi_run_guard_database_unavailable")
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": run_guard_key(run_id)}
            )
            yield


_admitted_runs: set[UUID] = set()


def admit_run(run_id: UUID) -> None:
    """Fail fast before creating a worker or a long-lived run-guard connection.

    No queue or timer. This app already has one process; this allowance protects
    its15-connection ORM pool while leaving ordinary Task paths unmodified.
    """
    if run_id in _admitted_runs:
        raise HTTPException(status_code=409, detail="mimi_run_already_admitted")
    if len(_admitted_runs) >= get_settings().mimi_max_active_runs:
        raise HTTPException(status_code=503, detail="mimi_busy_try_later")
    _admitted_runs.add(run_id)


def release_run(run_id: UUID) -> None:
    _admitted_runs.discard(run_id)


@asynccontextmanager
async def hold_run_guard_if_enabled(run_id: UUID, *, already_admitted: bool = False):
    if not already_admitted:
        admit_run(run_id)
    try:
        settings = get_settings()
        if settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled:
            async with hold_run_guard(run_id):
                yield
        else:
            yield
    finally:
        release_run(run_id)


class MimiRunSupervisor:
    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._stopping = False

    def start(self, run_id: UUID, work: Awaitable[None]) -> None:
        if self._stopping:
            raise RuntimeError("Mimi run supervisor is stopping")
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            raise RuntimeError("Mimi run is already supervised")
        task = asyncio.create_task(work, name=f"mimi-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._forget(run_id, completed))

    def _forget(self, run_id: UUID, completed: asyncio.Task[None]) -> None:
        # Cancellation before the coroutine starts never enters its finally.
        release_run(run_id)
        if self._tasks.get(run_id) is completed:
            self._tasks.pop(run_id, None)
        # Retrieve the exception so detached failures never become an unhandled
        # task warning. The worker persists its own truthful terminal state.
        if not completed.cancelled():
            error = completed.exception()
            if error is not None:
                logger.error(
                    "mimi_supervised_run_failed run_id=%s",
                    run_id,
                    exc_info=(type(error), error, error.__traceback__),
                )

    def cancel(self, run_id: UUID) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def active(self, run_id: UUID) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    async def stop(self) -> None:
        self._stopping = True
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
