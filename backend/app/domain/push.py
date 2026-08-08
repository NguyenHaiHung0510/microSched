"""Domain logic for Web Push notifications, subscription management, and pruning."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import StrEnum

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


def validate_push_endpoint(endpoint: str) -> bool:
    """Validate that a Web Push endpoint is an HTTPS URL and not an internal/SSRF target."""
    if not endpoint or not isinstance(endpoint, str):
        return False

    import ipaddress
    from urllib.parse import urlparse

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
    if hostname_lower in ("localhost", "localhost.localdomain"):
        return False

    try:
        ip = ipaddress.ip_address(hostname_lower)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    except ValueError:
        pass

    return True


def _do_webpush_sync(
    endpoint: str,
    p256dh: str,
    auth: str,
    payload_str: str,
    vapid_private_key: str,
    vapid_claims_sub: str,
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
    )
    return response.status_code if response else 200


async def send_push(
    db: AsyncSession,
    subscription: PushSubscription,
    payload: dict,
    timeout_seconds: float = 20.0,
) -> PushResult:
    """Send a Web Push notification to a single PushSubscription with a timeout."""
    settings = get_settings()

    if not settings.vapid_private_key or not settings.vapid_claims_sub:
        logger.error("VAPID keys not configured; cannot send Web Push notification")
        return PushResult.TEMPORARY_FAILURE

    payload_str = json.dumps(payload, ensure_ascii=False)

    try:
        async with asyncio.timeout(timeout_seconds):
            status_code = await asyncio.to_thread(
                _do_webpush_sync,
                subscription.endpoint,
                subscription.p256dh,
                subscription.auth,
                payload_str,
                settings.vapid_private_key,
                settings.vapid_claims_sub,
            )
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
