"""Authenticated subscription and renewal HTTP endpoints (011c)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.subscription import (
    RenewRequest,
    RenewResult,
    SubscriptionCreate,
    SubscriptionIdConflict,
    SubscriptionInvalid,
    SubscriptionNameTaken,
    SubscriptionParentMissing,
    SubscriptionRead,
    SubscriptionStore,
    SubscriptionUpdate,
)
from app.domain.tracker import EntryIdConflict, EntryInvalid
from app.web.deps import get_session, require_session

router = APIRouter(tags=["subscription"])
store = SubscriptionStore()

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")


def _invalid(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


def _subscription_response(response: Response, subscription: SubscriptionRead) -> SubscriptionRead:
    response.status_code = (
        status.HTTP_201_CREATED if subscription.created else status.HTTP_200_OK
    )
    return subscription


@router.get("/subscriptions", response_model=dict[str, list[SubscriptionRead]])
async def list_subscriptions(
    db: Database,
    session: CurrentSession,
    status_filter: str | None = Query(default=None, alias="status"),
    tracker_id: UUID | None = Query(default=None),
) -> dict[str, list[SubscriptionRead]]:
    """List visible subscriptions; optional status/tracker filters, no pagination."""
    if status_filter is not None and status_filter not in ("active", "canceled", "expired"):
        raise HTTPException(status_code=422, detail="status must be active, canceled or expired")
    return {
        "items": await store.list_subscriptions(
            db, session, status=status_filter, tracker_id=tracker_id
        )
    }


@router.post("/subscriptions", response_model=SubscriptionRead)
async def create_subscription(
    payload: SubscriptionCreate,
    db: Database,
    session: CurrentSession,
    response: Response,
) -> SubscriptionRead:
    """Create a subscription (201/200 idempotent); 409 name; 404 hidden parent; 422 type."""
    try:
        subscription = await store.create_subscription(db, session, payload)
    except SubscriptionParentMissing as error:
        raise _not_found() from error
    except SubscriptionNameTaken as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Đã có đăng ký cùng tên."
        ) from error
    except SubscriptionInvalid as error:
        raise _invalid(error) from error
    except SubscriptionIdConflict:
        return Response(status_code=status.HTTP_409_CONFLICT)
    except ValueError as error:
        raise _invalid(error) from error
    return _subscription_response(response, subscription)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionRead)
async def read_subscription(
    subscription_id: UUID, db: Database, session: CurrentSession
) -> SubscriptionRead:
    subscription = await store.get_subscription(db, session, subscription_id)
    if subscription is None:
        raise _not_found()
    return subscription


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionRead)
async def update_subscription(
    subscription_id: UUID,
    payload: SubscriptionUpdate,
    db: Database,
    session: CurrentSession,
) -> SubscriptionRead:
    """Patch a subscription; 422 on ``expires_on < started_on`` or wrong values."""
    try:
        subscription = await store.update_subscription(db, session, subscription_id, payload)
    except SubscriptionNameTaken as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Đã có đăng ký cùng tên."
        ) from error
    except SubscriptionInvalid as error:
        raise _invalid(error) from error
    except ValueError as error:
        raise _invalid(error) from error
    if subscription is None:
        raise _not_found()
    return subscription


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionRead)
async def cancel_subscription(
    subscription_id: UUID, db: Database, session: CurrentSession
) -> SubscriptionRead:
    """Mark a subscription canceled (keeps its remaining validity)."""
    subscription = await store.cancel_subscription(db, session, subscription_id)
    if subscription is None:
        raise _not_found()
    return subscription


@router.post("/subscriptions/{subscription_id}/uncancel", response_model=SubscriptionRead)
async def uncancel_subscription(
    subscription_id: UUID, db: Database, session: CurrentSession
) -> SubscriptionRead:
    """Clear the canceled mark (changed-mind path)."""
    subscription = await store.uncancel_subscription(db, session, subscription_id)
    if subscription is None:
        raise _not_found()
    return subscription


@router.post("/subscriptions/{subscription_id}/renew", response_model=RenewResult)
async def renew_subscription(
    subscription_id: UUID,
    payload: RenewRequest,
    db: Database,
    session: CurrentSession,
) -> RenewResult:
    """Record one renewal: one entry + one expiry push, atomically (§4.2)."""
    try:
        result = await store.renew(db, session, subscription_id, payload)
    except SubscriptionInvalid as error:
        raise _invalid(error) from error
    except EntryInvalid as error:
        raise _invalid(error) from error
    except EntryIdConflict:
        return Response(status_code=status.HTTP_409_CONFLICT)
    except ValueError as error:
        raise _invalid(error) from error
    if result is None:
        raise _not_found()
    return result


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: UUID, db: Database, session: CurrentSession
) -> Response:
    """Soft-delete a subscription (distinct from cancel)."""
    if not await store.soft_delete_subscription(db, session, subscription_id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/subscriptions/{subscription_id}/restore", response_model=dict[str, str])
async def restore_subscription(
    subscription_id: UUID, db: Database, session: CurrentSession
) -> dict[str, str]:
    """Restore a soft-deleted subscription (re-validates the parent tracker)."""
    try:
        subscription = await store.restore_subscription(db, session, subscription_id)
    except SubscriptionInvalid as error:
        raise _invalid(error) from error
    if subscription is None:
        raise _not_found()
    return {"id": str(subscription.id), "status": "restored"}
