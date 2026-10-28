"""Selector-loop factory for the explicit Windows Postgres-backed Mimi QA app."""

from __future__ import annotations

import asyncio
import selectors


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Return a per-server loop factory without changing process-wide policy."""
    return asyncio.SelectorEventLoop(selectors.SelectSelector())
