"""Web Push subscription and confirmation endpoints."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.models import AuthSession, PushSubscription
from app.domain.push import validate_push_endpoint
from app.domain.reminder import confirm_reminder_dispatch
from app.web.deps import get_session, require_session

router = APIRouter(tags=["push"])


class PushSubscribeRequest(BaseModel):
    """Payload for registering or updating a Web Push subscription."""

    endpoint: str = Field(min_length=1)
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)
    user_agent: str | None = None


class PushUnsubscribeRequest(BaseModel):
    """Payload for removing a Web Push subscription."""

    endpoint: str = Field(min_length=1)


class ConfirmReminderRequest(BaseModel):
    """Payload for confirming a medication reminder occurrence."""

    entry_id: UUID
    occurred_at: datetime


@router.get("/push/vapid-public-key")
async def get_vapid_public_key(
    _auth: Annotated[AuthSession, Depends(require_session)],
) -> dict[str, str]:
    """Expose the VAPID public key for frontend push subscription setup."""
    settings = get_settings()
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID public key is not configured",
        )
    return {"public_key": settings.vapid_public_key}


@router.post("/push/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    body: PushSubscribeRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _auth: Annotated[AuthSession, Depends(require_session)],
) -> dict[str, str]:
    """Register or update a device Web Push subscription."""
    if not validate_push_endpoint(body.endpoint):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid push endpoint URL",
        )

    stmt = select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing is not None:
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        if body.user_agent is not None:
            existing.user_agent = body.user_agent
        existing.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
        return {"id": str(existing.id), "status": "updated"}

    new_sub = PushSubscription(
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=body.user_agent,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_sub)
    return {"id": str(new_sub.id), "status": "created"}


@router.delete("/push/subscribe")
async def unsubscribe_push(
    body: PushUnsubscribeRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _auth: Annotated[AuthSession, Depends(require_session)],
) -> dict[str, str]:
    """Unregister a device Web Push subscription by endpoint."""
    stmt = delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted"}


@router.post("/reminder-dispatch/{dispatch_id}/confirm")
async def confirm_reminder(
    dispatch_id: UUID,
    body: ConfirmReminderRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    auth: Annotated[AuthSession, Depends(require_session)],
) -> dict[str, object]:
    """Idempotently confirm a medication reminder dispatch and create an Entry."""
    now_utc = datetime.now(timezone.utc)
    unlocked = bool(auth.private_until and auth.private_until > now_utc)
    entry, created = await confirm_reminder_dispatch(
        db,
        dispatch_id=dispatch_id,
        entry_id=body.entry_id,
        occurred_at=body.occurred_at,
        is_private_unlocked=unlocked,
    )
    return {
        "confirmed_entry_id": str(getattr(entry, "id")),
        "created": created,
    }
