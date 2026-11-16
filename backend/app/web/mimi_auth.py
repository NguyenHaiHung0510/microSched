"""Workspace login gate for Mimi routes; app-wide sessions keep their own contract."""

from typing import Annotated

from fastapi import Depends

from app.agent.owner_workspace import require_workspace_login
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.web.deps import require_session


async def require_mimi_workspace_session(auth: Annotated[AuthSession, Depends(require_session)]):
    settings = get_settings()
    if settings.mimi_owner_workspace_enabled:
        require_workspace_login(auth, settings)
