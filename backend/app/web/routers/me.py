"""Who-am-I endpoint used by the SPA to decide between app and login screen."""

from fastapi import APIRouter, Depends

from app.domain.models import AuthSession
from app.web.deps import require_session

router = APIRouter(tags=["session"])


@router.get("/me")
async def read_me(session: AuthSession = Depends(require_session)) -> dict[str, str]:
    """Return the signed-in identity for the current session."""
    return {"email": session.user_email}
