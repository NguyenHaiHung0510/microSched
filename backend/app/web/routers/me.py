"""Who-am-I endpoint used by the SPA to decide between app and login screen."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.private_gate import gate_status
from app.web.deps import get_session, require_session

router = APIRouter(tags=["session"])


class SessionInfo(BaseModel):
    """What the signed-in owner is allowed to see about their own session."""

    email: str
    signed_in_at: datetime | None
    expires_at: datetime
    private_until: datetime | None
    private_locked_until: datetime | None
    pin_is_set: bool
    pin_is_bootstrap: bool


@router.get("/me")
async def read_me(
    session: AuthSession = Depends(require_session),
    db: AsyncSession = Depends(get_session),
) -> SessionInfo:
    """Return the signed-in identity and session window."""
    private = await gate_status(db, session)
    return SessionInfo(
        email=session.user_email,
        signed_in_at=session.created_at,
        expires_at=session.expires_at,
        private_until=private.private_until,
        private_locked_until=private.locked_until,
        pin_is_set=private.pin_is_set,
        pin_is_bootstrap=private.pin_is_bootstrap,
    )
