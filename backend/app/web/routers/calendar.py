"""Authenticated calendar source and event endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.calendar import (
    CalendarImportRejected,
    CalendarStore,
    EventCreate,
    EventNotFound,
    EventRead,
    EventUpdate,
    IcsEventCreationForbidden,
    ImportReport,
    ImportRequest,
    ManualSourceImportForbidden,
    SourceCreate,
    SourceNameTaken,
    SourceNotFound,
    SourceRead,
    SourceUpdate,
)
from app.domain.models import AuthSession
from app.web.deps import get_session, require_session

router = APIRouter(tags=["calendar"])
store = CalendarStore()

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _source_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Calendar source not found",
    )


def _event_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Calendar event not found",
    )


def _name_taken(error: SourceNameTaken) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "source_name_taken",
            "message": "Đã có nguồn lịch cùng tên.",
            "existing_source_id": str(error.existing_source_id),
        },
    )


@router.get("/calendar/sources", response_model=dict[str, list[SourceRead]])
async def list_sources(db: Database, session: CurrentSession) -> dict[str, list[SourceRead]]:
    """List every calendar source without pagination."""
    return {"items": await store.list_sources(db, session)}


@router.post("/calendar/sources", response_model=SourceRead)
async def create_source(
    payload: SourceCreate,
    db: Database,
    session: CurrentSession,
    response: Response,
) -> SourceRead:
    """Create a source or idempotently return an existing explicit ID."""
    try:
        source = await store.create_source(db, session, payload)
    except SourceNameTaken as error:
        raise _name_taken(error) from error
    response.status_code = status.HTTP_201_CREATED if source.created else status.HTTP_200_OK
    return source


@router.patch("/calendar/sources/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    db: Database,
    session: CurrentSession,
) -> SourceRead:
    """Patch source name, color, or visibility."""
    try:
        return await store.update_source(db, session, source_id, payload)
    except SourceNotFound as error:
        raise _source_not_found() from error
    except SourceNameTaken as error:
        raise _name_taken(error) from error


@router.delete("/calendar/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Hard-delete a source and its cascaded events."""
    try:
        await store.delete_source(db, session, source_id)
    except SourceNotFound as error:
        raise _source_not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/calendar/sources/{source_id}/import", response_model=ImportReport)
async def import_source(
    source_id: UUID,
    payload: ImportRequest,
    db: Database,
    session: CurrentSession,
) -> ImportReport:
    """Replace an ICS source's events only after a non-empty safe parse."""
    try:
        return await store.import_into_source(db, session, source_id, payload)
    except SourceNotFound as error:
        raise _source_not_found() from error
    except ManualSourceImportForbidden as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nguồn thủ công không nhận file ICS.",
        ) from error
    except CalendarImportRejected as error:
        detail: str | dict[str, object] = error.message
        if error.skipped:
            detail = {"message": error.message, "skipped": error.skipped}
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        ) from error


@router.get("/calendar/events", response_model=dict[str, list[EventRead]])
async def list_events(
    db: Database,
    session: CurrentSession,
    from_: datetime = Query(default=..., alias="from"),
    to: datetime = Query(default=...),
    include_hidden: bool = Query(default=False),
) -> dict[str, list[EventRead]]:
    """List all visible events intersecting a required timezone-aware range."""
    if from_.tzinfo is None or from_.utcoffset() is None:
        raise HTTPException(status_code=422, detail="from must include a timezone offset")
    if to.tzinfo is None or to.utcoffset() is None:
        raise HTTPException(status_code=422, detail="to must include a timezone offset")
    if from_ >= to:
        raise HTTPException(status_code=422, detail="from must be before to")
    return {
        "items": await store.list_events(db, session, from_, to, include_hidden),
    }


@router.post("/calendar/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(payload: EventCreate, db: Database, session: CurrentSession) -> EventRead:
    """Create one event under a manual source."""
    try:
        return await store.create_event(db, session, payload)
    except SourceNotFound as error:
        raise _source_not_found() from error
    except IcsEventCreationForbidden as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể tạo buổi thủ công dưới nguồn nhập từ file.",
        ) from error


@router.patch("/calendar/events/{event_id}", response_model=EventRead)
async def update_event(
    event_id: UUID,
    payload: EventUpdate,
    db: Database,
    session: CurrentSession,
) -> EventRead:
    """Patch one event without changing its source."""
    try:
        return await store.update_event(db, session, event_id, payload)
    except EventNotFound as error:
        raise _event_not_found() from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Hard-delete one event."""
    try:
        await store.delete_event(db, session, event_id)
    except EventNotFound as error:
        raise _event_not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
