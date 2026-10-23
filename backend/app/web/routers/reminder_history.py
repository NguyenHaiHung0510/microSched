"""Unified read-only receipt history; existing reminder APIs keep their semantics."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.reminder_history import HistoryFilter, Origin, Source, Status, list_history
from app.web.deps import get_session, require_session

router = APIRouter(prefix="/reminder-history", tags=["reminder-history"])


@router.get("")
async def listing(
    db: Annotated[AsyncSession, Depends(get_session)],
    session: Annotated[AuthSession, Depends(require_session)],
    response: Response,
    origin: Origin | None = None,
    source: Source | None = None,
    status: Status | None = None,
    handled: Literal["all", "unhandled"] = "all",
    day_from: date | None = None,
    day_to: date | None = None,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=2048),
):
    response.headers["Cache-Control"] = "no-store"
    return await list_history(
        db,
        session,
        HistoryFilter(
            origin=origin,
            source=source,
            status=status,
            handled=handled,
            day_from=day_from,
            day_to=day_to,
        ),
        limit=limit,
        cursor=cursor,
    )
