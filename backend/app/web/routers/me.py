"""Who-am-I endpoint used by the SPA to decide between app and login screen."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.domain.models import AuthSession
from app.web.deps import require_session

router = APIRouter(tags=["session"])


class SessionInfo(BaseModel):
    """What the signed-in owner is allowed to see about their own session."""

    email: str
    signed_in_at: datetime | None
    expires_at: datetime


@router.get("/me")
async def read_me(session: AuthSession = Depends(require_session)) -> SessionInfo:
    """Return the signed-in identity and session window."""
    return SessionInfo(
        email=session.user_email,
        signed_in_at=session.created_at,
        expires_at=session.expires_at,
    )
