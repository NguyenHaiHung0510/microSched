"""Finite recovery of gateway transport, independent of provider selection."""

from __future__ import annotations

import asyncio
import math
import os
import random
import time
from dataclasses import replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except ValueError, TypeError, OverflowError:
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


async def dispatch(operation, *, settings):
    from app.agent.openrouter import ProviderDispatchError, RouteContractError

    attempts = []
    deadline = time.monotonic() + settings.mimi_run_deadline_seconds
    for number in range(1, 4):
        try:
            # An outer run timeout may be shorter; it remains authoritative.
            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                result = await operation()
        except (ProviderDispatchError, RouteContractError) as error:
            receipt = getattr(error, "terminal_receipt", {})
            attempts.append(
                {
                    "attempt": number,
                    "outcome": getattr(error, "outcome", "failed"),
                    "status": getattr(error, "status", None),
                    "response_id": getattr(error, "response_id", None),
                    "usage": receipt.get("usage", {}),
                    "category": getattr(error, "diagnostic", {}).get("category"),
                }
            )
            error.dispatch_attempts = attempts.copy()
            safe = (
                isinstance(error, ProviderDispatchError)
                and error.outcome == "retryable"
                and not error.response_id
            )
            # Private paid QA reserved one dispatch upstream. Unknown/rejected
            # cost keeps that reservation; never hide extra calls or invent zero.
            if not safe or number == 3 or os.environ.get("MIMI_LOCAL_BUDGET_LEDGER"):
                raise
            delay = max(
                2 ** (number - 1) + random.uniform(0, 0.25),
                error.diagnostic.get("retry_after_seconds", 0),
            )
            if time.monotonic() + delay >= deadline:
                raise
            await asyncio.sleep(delay)
        except TimeoutError as cause:
            error = ProviderDispatchError("unknown", None)
            error.dispatch_attempts = attempts + [
                {
                    "attempt": number,
                    "outcome": "unknown",
                    "status": None,
                    "response_id": None,
                    "usage": {},
                }
            ]
            raise error from cause
        else:
            return replace(
                result,
                dispatch_attempts=attempts
                + [
                    {
                        "attempt": number,
                        "outcome": "succeeded",
                        "status": 200,
                        "response_id": result.response_id,
                        "usage": result.usage,
                    }
                ],
            )
