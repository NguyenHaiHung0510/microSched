"""Allowlisted public settings endpoints (011c §4.5, §2.1)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import settings as settings_store
from app.domain.models import AuthSession
from app.web.deps import get_session, require_session

router = APIRouter(tags=["settings"])

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


class SettingWrite(BaseModel):
    value: Any


def _not_found() -> HTTPException:
    """One 404 for EVERY key outside the allowlist — secret keys included (§2.1)."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")


@router.get("/settings", response_model=dict[str, list[dict[str, Any]]])
async def list_settings(db: Database, session: CurrentSession) -> dict[str, list[dict[str, Any]]]:
    """List only the allowlisted keys with effective (default-applied) values."""
    try:
        return {"items": await settings_store.list_public_settings(db)}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/settings/{key}", response_model=dict[str, Any])
async def get_setting(key: str, db: Database, session: CurrentSession) -> dict[str, Any]:
    """Read one allowlisted key; 404 for any other key (no distinction, no leak)."""
    try:
        item = await settings_store.get_public_setting(db, key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if item is None:
        raise _not_found()
    return item


@router.patch("/settings/{key}", response_model=dict[str, Any])
async def patch_setting(
    key: str, payload: SettingWrite, db: Database, session: CurrentSession
) -> dict[str, Any]:
    """Upsert one allowlisted key; 404 outside the allowlist, 422 for a bad value."""
    try:
        item = await settings_store.set_public_setting(db, key, payload.value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if item is None:
        raise _not_found()
    return item
