"""Authenticated note and nested checklist HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.notes import (
    NoteCreate,
    NoteIdConflict,
    NoteItemCreate,
    NoteItemRead,
    NoteItemUpdate,
    NoteRead,
    NoteStore,
    NoteUpdate,
    PrivateWriteLocked,
)
from app.web.deps import get_session, require_session

router = APIRouter(tags=["note"])
store = NoteStore()

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


def _private_locked() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Private mode is locked",
    )


@router.get("/notes", response_model=dict[str, list[NoteRead]])
async def list_notes(
    db: Database,
    session: CurrentSession,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[NoteRead]]:
    """List visible notes in a stable envelope."""
    return {"items": await store.list(db, session, limit=limit, offset=offset)}


@router.post("/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate, db: Database, session: CurrentSession, response: Response
) -> NoteRead | Response:
    """Create a note and initial checklist in one request transaction."""
    try:
        note = await store.create(db, session, payload)
    except NoteIdConflict:
        return Response(status_code=status.HTTP_409_CONFLICT)
    except PrivateWriteLocked as error:
        raise _private_locked() from error
    response.status_code = status.HTTP_201_CREATED if note.created else status.HTTP_200_OK
    return note


@router.get("/notes/{note_id}", response_model=NoteRead)
async def read_note(note_id: UUID, db: Database, session: CurrentSession) -> NoteRead:
    """Read one visible note."""
    note = await store.get(db, session, note_id)
    if note is None:
        raise _not_found()
    return note


@router.patch("/notes/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: UUID, payload: NoteUpdate, db: Database, session: CurrentSession
) -> NoteRead:
    """Patch one visible note."""
    try:
        note = await store.update(db, session, note_id, payload)
    except PrivateWriteLocked as error:
        raise _private_locked() from error
    if note is None:
        raise _not_found()
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Soft-delete one visible note."""
    if not await store.soft_delete(db, session, note_id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notes/{note_id}/restore", response_model=dict[str, str])
async def restore_note(note_id: UUID, db: Database, session: CurrentSession) -> dict[str, str]:
    """Restore one privacy-visible note without returning its content."""
    note = await store.restore(db, session, note_id)
    if note is None:
        raise _not_found()
    return {"id": str(note.id), "status": "restored"}


@router.get("/notes/{note_id}/items", response_model=list[NoteItemRead])
async def list_note_items(
    note_id: UUID, db: Database, session: CurrentSession
) -> list[NoteItemRead]:
    """List checklist items through their visible parent."""
    items = await store.list_items(db, session, note_id)
    if items is None:
        raise _not_found()
    return items


@router.post(
    "/notes/{note_id}/items",
    response_model=NoteItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_note_item(
    note_id: UUID,
    payload: NoteItemCreate,
    db: Database,
    session: CurrentSession,
) -> NoteItemRead:
    """Append a checklist item through its visible, locked parent."""
    item = await store.add_item(db, session, note_id, payload)
    if item is None:
        raise _not_found()
    return item


@router.patch("/notes/{note_id}/items/{item_id}", response_model=NoteItemRead)
async def update_note_item(
    note_id: UUID,
    item_id: UUID,
    payload: NoteItemUpdate,
    db: Database,
    session: CurrentSession,
) -> NoteItemRead:
    """Patch a checklist item without allowing reparenting."""
    try:
        item = await store.update_item(db, session, note_id, item_id, payload)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    if item is None:
        raise _not_found()
    return item


@router.delete("/notes/{note_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_item(
    note_id: UUID, item_id: UUID, db: Database, session: CurrentSession
) -> Response:
    """Delete a checklist item through its visible, locked parent."""
    if not await store.delete_item(db, session, note_id, item_id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
