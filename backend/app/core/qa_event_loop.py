"""Selector-loop factory for the explicit Windows Postgres-backed Mimi QA app."""

from __future__ import annotations

import asyncio
import selectors


def selector_loop_factory(use_subprocess: bool = False):
    """Return a per-server loop factory without changing process-wide policy."""
    del use_subprocess
    return lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
