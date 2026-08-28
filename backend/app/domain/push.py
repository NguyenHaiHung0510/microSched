"""Domain logic for Web Push notifications, subscription management, and pruning."""

import asyncio
import ipaddress
import json
import logging
import socket
from contextlib import suppress
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pywebpush import WebPushException, webpush
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.models import PushSubscription

logger = logging.getLogger(__name__)


class PushResult(StrEnum):
    """Outcome of attempting to deliver a Web Push notification to a subscription."""

    SENT = "sent"
    TEMPORARY_FAILURE = "temporary_failure"
    DEAD_SUBSCRIPTION = "dead_subscription"


class ProviderWorkTracker:
    """Track real worker-thread Web Push calls across coroutine cancellation.

    ``asyncio.to_thread`` cannot stop a synchronous socket call when its awaiter
    is cancelled.  The scheduler uses this registry during shutdown so it keeps
    its advisory lock until the actual provider worker is finished.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def track(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)

        def discard(completed: asyncio.Task[Any]) -> None:
            self._tasks.discard(completed)
            # A worker that outlived a cancelled sender must not later emit an
            # unobserved-task warning.  Normal callers still await its result.
            with suppress(asyncio.CancelledError):
                completed.exception()

        task.add_done_callback(discard)

    @property
    def pending_count(self) -> int:
        return len(self._tasks)

    async def wait_for_idle(self, timeout_seconds: float) -> bool:
        """Wait for every registered worker, returning false at the hard bound."""
        if not self._tasks:
            return True
        _, pending = await asyncio.wait(set(self._tasks), timeout=timeout_seconds)
        return not pending


def _resolve_endpoint_ips(hostname: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname synchronously; callers must keep this off the event loop."""
    answers = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    return {ipaddress.ip_address(answer[4][0]) for answer in answers}


async def validate_push_endpoint(endpoint: str) -> bool:
    """Accept only HTTPS endpoints whose literal or resolved IPs are all public.

    DNS resolution happens in a worker thread so subscription requests do not
    block the ASGI event loop.  A hostname with even one non-public answer is
    rejected to prevent split-horizon/DNS-rebinding SSRF.
    """
    if not endpoint or not isinstance(endpoint, str):
        return False

    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False

    if parsed.scheme != "https":
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "localhost.localdomain") or hostname_lower.endswith(
        ".internal"
    ):
        return False

    try:
        ip = ipaddress.ip_address(hostname_lower)
        return ip.is_global
    except ValueError:
        try:
            resolved_ips = await asyncio.to_thread(_resolve_endpoint_ips, hostname_lower)
        except OSError, ValueError:
            return False

    return bool(resolved_ips) and all(ip.is_global for ip in resolved_ips)


def _do_webpush_sync(
    endpoint: str,
    p256dh: str,
    auth: str,
    payload_str: str,
    vapid_private_key: str,
    vapid_claims_sub: str,
    timeout_seconds: float,
) -> int:
    """Synchronous wrapper for pywebpush call."""
    sub_info = {
        "endpoint": endpoint,
        "keys": {
            "p256dh": p256dh,
            "auth": auth,
        },
    }
    vapid_claims = {"sub": vapid_claims_sub}
    response = webpush(
        subscription_info=sub_info,
        data=payload_str,
        vapid_private_key=vapid_private_key,
        vapid_claims=vapid_claims,
        timeout=timeout_seconds,
    )
    return response.status_code if response else 200


async def send_push(
    db: AsyncSession,
    subscription: PushSubscription,
    payload: dict,
    timeout_seconds: float = 20.0,
    provider_work_tracker: ProviderWorkTracker | None = None,
) -> PushResult:
    """Send a Web Push notification to a single PushSubscription with a timeout."""
    settings = get_settings()

    if not settings.vapid_private_key or not settings.vapid_claims_sub:
        logger.error("VAPID keys not configured; cannot send Web Push notification")
        return PushResult.TEMPORARY_FAILURE

    payload_str = json.dumps(payload, ensure_ascii=False)

    try:
        async with asyncio.timeout(timeout_seconds):
            # Validate again immediately before a network send: a subscription
            # can outlive its original DNS answer, so save-time validation alone
            # cannot protect against DNS rebinding.
            if not await validate_push_endpoint(subscription.endpoint):
                logger.warning(
                    "Rejected non-public Web Push endpoint before send for subscription %s",
                    subscription.id,
                )
                return PushResult.TEMPORARY_FAILURE
            worker = asyncio.create_task(
                asyncio.to_thread(
                    _do_webpush_sync,
                    subscription.endpoint,
                    subscription.p256dh,
                    subscription.auth,
                    payload_str,
                    settings.vapid_private_key,
                    settings.vapid_claims_sub,
                    timeout_seconds,
                ),
                name="microsched-web-push-worker",
            )
            if provider_work_tracker is not None:
                provider_work_tracker.track(worker)
            # Shield keeps the worker task alive when a scheduler shutdown or
            # lost-lock cancellation interrupts this coroutine.  The timer then
            # waits for the actual worker before it relinquishes ownership.
            status_code = await asyncio.shield(worker)
            if status_code in (200, 201, 202):
                subscription.last_seen_at = datetime.now(timezone.utc)
                await db.commit()
                return PushResult.SENT
            return PushResult.TEMPORARY_FAILURE
    except TimeoutError:
        logger.warning(
            "Web Push timeout for subscription %s after %s seconds",
            subscription.id,
            timeout_seconds,
        )
        return PushResult.TEMPORARY_FAILURE
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (404, 410):
            logger.info(
                "Push service returned %s for subscription %s; deleting dead subscription",
                status_code,
                subscription.id,
            )
            stmt = delete(PushSubscription).where(PushSubscription.id == subscription.id)
            await db.execute(stmt)
            await db.commit()
            return PushResult.DEAD_SUBSCRIPTION

        # WebPushException text includes provider response bodies in pywebpush;
        # keep logs to the status and opaque subscription id only.
        logger.warning(
            "WebPushException status %s for subscription %s",
            status_code,
            subscription.id,
        )
        return PushResult.TEMPORARY_FAILURE
    except Exception as exc:
        logger.error(
            "Unexpected exception sending push to subscription %s: %s",
            subscription.id,
            type(exc).__name__,
        )
        return PushResult.TEMPORARY_FAILURE
