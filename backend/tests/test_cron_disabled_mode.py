"""Literal disabled-mode isolation for the in-process reminder timer."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_disabled_create_app_does_not_load_or_construct_cron_runtime() -> None:
    """A fresh disabled process creates no timer, dispatcher singleton, or Event."""
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "local",
            "ENABLE_INPROCESS_CRON": "false",
            "OAUTH_STATE_SECRET": "cron-disabled-test-secret",
        }
    )
    probe = """
import asyncio
import sys
from unittest.mock import patch

from app.main import create_app

with patch.object(asyncio, 'Event', side_effect=AssertionError('disabled mode created Event')):
    app = create_app()

from app.domain import reminder

assert 'app.core.cron_timer' not in sys.modules
assert not hasattr(app.state, 'cron_timer')
assert not hasattr(app.state, 'cron_timer_task')
assert not hasattr(reminder, 'dispatcher')
"""

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.anyio
async def test_enabled_lifespan_builds_one_timer_task(monkeypatch) -> None:
    """The enabled path still owns one timer and stops it with its lifespan."""
    import asyncio

    from app.core import cron_timer
    from app.core.settings import get_settings
    from app.main import create_app, lifespan

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ENABLE_INPROCESS_CRON", "true")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "cron-enabled-test-secret")
    get_settings.cache_clear()

    class Timer:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.stopped = asyncio.Event()

        async def run(self) -> None:
            self.started.set()
            await self.stopped.wait()

        async def stop(self) -> None:
            self.stopped.set()

    timer = Timer()
    monkeypatch.setattr(cron_timer, "build_cron_timer_if_enabled", lambda: timer)
    app = create_app()

    try:
        async with lifespan(app):
            await timer.started.wait()
            assert app.state.cron_timer is timer
            assert app.state.cron_timer_task.done() is False
        assert timer.stopped.is_set()
        assert app.state.cron_timer_task.done()
    finally:
        get_settings.cache_clear()
