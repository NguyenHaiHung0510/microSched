"""Authenticated one-shot reminders; source visibility is enforced by the domain."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.domain.models import AuthSession, PushSubscription
from app.domain.one_shot import (
    ReminderRead,
    ReminderWrite,
    SourceKind,
    cancel_reminder,
    get_source,
    list_reminders,
    save_reminder,
    source_open,
)
from app.web.deps import get_session, require_session

router = APIRouter(prefix="/reminders", tags=["reminders"])
Database = Annotated[AsyncSession, Depends(get_session)]
Session = Annotated[AuthSession, Depends(require_session)]


@router.get("/device-status")
async def device_status(db: Database, session: Session):
    return {
        "registered_devices": (
            await db.execute(select(func.count()).select_from(PushSubscription))
        ).scalar_one()
    }


@router.get("/event-detail/{event_id}")
async def event_detail(event_id: UUID, db: Database, session: Session):
    from app.domain.calendar import CalendarStore

    event = await get_source(db, "event", event_id, session)
    if event is None:
        raise HTTPException(404, "Không tìm thấy buổi.")
    return CalendarStore._event_read(event)


@router.get("")
async def listing(
    db: Database,
    session: Session,
    section: Literal["upcoming", "attention", "history", "all", "active"] = "upcoming",
    kind: SourceKind | None = None,
    source_id: UUID | None = None,
    offset: int = Query(0, ge=0, le=10000),
    limit: int = Query(50, ge=1, le=100),
):
    return await list_reminders(
        db, session, kind=kind, source_id=source_id, section=section, offset=offset, limit=limit
    )


@router.put("/{kind}/{source_id}", response_model=ReminderRead)
async def save(
    kind: SourceKind, source_id: UUID, payload: ReminderWrite, db: Database, session: Session
):
    return await save_reminder(db, session, kind, source_id, payload)


@router.get("/source/{kind}/{source_id}")
async def source_metadata(kind: SourceKind, source_id: UUID, db: Database, session: Session):
    source = await get_source(db, kind, source_id, session)
    if source is None:
        raise HTTPException(404, "Không tìm thấy đối tượng.")
    title = source.name if kind == "tracker" else source.title
    return {
        "title": crypto.decrypt(title) if crypto.is_encrypted(title) else title,
        "is_private": getattr(source, "is_private", False),
        "open": source_open(source),
        "updated_at": source.updated_at,
        "anchor_at": getattr(source, "starts_at", None)
        if kind == "event"
        else getattr(source, "due_at", None),
        "anchor_day": getattr(source, "due_on", None),
        "date_only": getattr(source, "all_day", False)
        or getattr(source, "due_precision", None) == "date",
    }


@router.delete("/{reminder_id}", status_code=204)
async def cancel(
    reminder_id: UUID, db: Database, session: Session, revision: int = Query(..., ge=1)
):
    await cancel_reminder(db, session, reminder_id, revision)
    return Response(status_code=204)
