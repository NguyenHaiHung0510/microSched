"""Web Push subscription and confirmation endpoints."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    if not await validate_push_endpoint(body.endpoint):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid push endpoint URL",
        )

    # The endpoint is the device's natural key.  Use the database unique key as
    # the idempotency boundary so two saves from the same browser cannot race
    # through separate SELECT-then-INSERT windows.
    existing_id = await db.scalar(
        select(PushSubscription.id).where(PushSubscription.endpoint == body.endpoint)
    )
    now_utc = datetime.now(timezone.utc)
    insert_stmt = pg_insert(PushSubscription).values(
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=body.user_agent,
        last_seen_at=now_utc,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[PushSubscription.endpoint],
        set_={
            "p256dh": insert_stmt.excluded.p256dh,
            "auth": insert_stmt.excluded.auth,
            "user_agent": func.coalesce(
                insert_stmt.excluded.user_agent,
                PushSubscription.user_agent,
            ),
            "last_seen_at": now_utc,
        },
    ).returning(PushSubscription.id)
    subscription_id = (await db.execute(upsert_stmt)).scalar_one()
    await db.commit()
    return {
        "id": str(subscription_id),
        "status": "updated" if existing_id is not None else "created",
    }


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
    entry, created = await confirm_reminder_dispatch(
        db,
        dispatch_id=dispatch_id,
        entry_id=body.entry_id,
        occurred_at=body.occurred_at,
        auth=auth,
    )
    return {
        "confirmed_entry_id": str(getattr(entry, "id")),
        "created": created,
    }
