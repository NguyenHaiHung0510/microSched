"""Authenticated tracker-group / tracker / entry and dashboard HTTP endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dashboard import DashboardResponse, DashboardService
from app.domain.models import AuthSession
from app.domain.tracker import (
    EntryCreate,
    EntryIdConflict,
    EntryInvalid,
    EntryRead,
    EntryUpdate,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    PrivateWriteLocked,
    TrackerCreate,
    TrackerIdConflict,
    TrackerInvalid,
    TrackerNameTaken,
    TrackerRead,
    TrackerStore,
    TrackerUpdate,
)
from app.web.deps import get_session, require_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tracker"])
store = TrackerStore()
dashboard_service = DashboardService()

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _not_found(kind: str = "Tracker") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind} not found")


def _private_locked() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Private mode is locked",
    )


def _tracker_invalid(error: TrackerInvalid | EntryInvalid) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(error),
    )


def _group_response(response: Response, group: GroupRead) -> GroupRead:
    response.status_code = status.HTTP_201_CREATED if group.created else status.HTTP_200_OK
    return group


def _tracker_response(response: Response, tracker: TrackerRead) -> TrackerRead:
    response.status_code = status.HTTP_201_CREATED if tracker.created else status.HTTP_200_OK
    return tracker


def _tz_aware(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{name} must include a timezone offset",
        )


# ------------------------------------------------------------------ groups


@router.get("/tracker/groups", response_model=dict[str, list[GroupRead]])
async def list_groups(db: Database, session: CurrentSession) -> dict[str, list[GroupRead]]:
    """List every tracker group with its live tracker count (no pagination)."""
    return {"items": await store.list_groups(db, session)}


@router.post("/tracker/groups", response_model=GroupRead)
async def create_group(
    payload: GroupCreate,
    db: Database,
    session: CurrentSession,
    response: Response,
) -> GroupRead:
    """Create a group (201) or idempotently return the explicit ID (200); 409 on name."""
    try:
        group = await store.create_group(db, payload)
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Đã có nhóm cùng tên."
        ) from error
    return _group_response(response, group)


@router.patch("/tracker/groups/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: UUID,
    payload: GroupUpdate,
    db: Database,
    session: CurrentSession,
) -> GroupRead:
    """Patch a group's name/color/position; 409 on a taken name."""
    try:
        group = await store.update_group(db, session, group_id, payload)
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Đã có nhóm cùng tên."
        ) from error
    if group is None:
        raise _not_found("Group")
    return group


@router.delete("/tracker/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Hard-delete a group; member trackers drop back to ungrouped."""
    if not await store.delete_group(db, group_id):
        raise _not_found("Group")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ trackers


@router.get("/tracker/trackers", response_model=dict[str, list[TrackerRead]])
async def list_trackers(db: Database, session: CurrentSession) -> dict[str, list[TrackerRead]]:
    """List visible, non-archived trackers with capture metadata (no pagination)."""
    return {"items": await store.list_trackers(db, session)}


@router.post("/tracker/trackers", response_model=TrackerRead)
async def create_tracker(
    payload: TrackerCreate,
    db: Database,
    session: CurrentSession,
    response: Response,
) -> TrackerRead:
    """Create a tracker (201/200 idempotent); 403 private-locked; 409 name; 422 invariant."""
    try:
        tracker = await store.create_tracker(db, session, payload)
    except PrivateWriteLocked as error:
        raise _private_locked() from error
    except TrackerNameTaken as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Đã có tracker cùng tên."
        ) from error
    except TrackerInvalid as error:
        raise _tracker_invalid(error) from error
    except TrackerIdConflict:
        return Response(status_code=status.HTTP_409_CONFLICT)
    return _tracker_response(response, tracker)


@router.get("/tracker/trackers/{tracker_id}", response_model=TrackerRead)
async def read_tracker(tracker_id: UUID, db: Database, session: CurrentSession) -> TrackerRead:
    tracker = await store.get_tracker(db, session, tracker_id)
    if tracker is None:
        raise _not_found()
    return tracker


@router.patch("/tracker/trackers/{tracker_id}", response_model=TrackerRead)
async def update_tracker(
    tracker_id: UUID, payload: TrackerUpdate, db: Database, session: CurrentSession
) -> TrackerRead:
    """Patch a tracker; 422 for unit/input_mode/kind×group violations."""
    try:
        tracker = await store.update_tracker(db, session, tracker_id, payload)
    except PrivateWriteLocked as error:
        raise _private_locked() from error
    except TrackerNameTaken as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Đã có tracker cùng tên."
        ) from error
    except TrackerInvalid as error:
        raise _tracker_invalid(error) from error
    if tracker is None:
        raise _not_found()
    return tracker


@router.delete("/tracker/trackers/{tracker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tracker(tracker_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Archive a tracker (soft-delete); 422 while live subscriptions are attached."""
    try:
        deleted = await store.soft_delete_tracker(db, session, tracker_id)
    except TrackerInvalid as error:
        raise _tracker_invalid(error) from error
    if not deleted:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tracker/trackers/{tracker_id}/restore", response_model=dict[str, str])
async def restore_tracker(
    tracker_id: UUID, db: Database, session: CurrentSession
) -> dict[str, str]:
    tracker = await store.restore_tracker(db, session, tracker_id)
    if tracker is None:
        raise _not_found()
    return {"id": str(tracker.id), "status": "restored"}


# ------------------------------------------------------------------ entries


@router.get("/tracker/entries", response_model=dict[str, list[EntryRead]])
async def list_entries(
    db: Database,
    session: CurrentSession,
    tracker_id: UUID | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[EntryRead]]:
    """List visible entries, optionally filtered and paginated."""
    _tz_aware(from_, "from")
    _tz_aware(to, "to")
    if from_ is not None and to is not None and from_ >= to:
        raise HTTPException(status_code=422, detail="from must be before to")
    return {
        "items": await store.list_entries(
            db, session, tracker_id=tracker_id, from_=from_, to=to, limit=limit, offset=offset
        )
    }


@router.post("/tracker/entries", response_model=EntryRead)
async def create_entry(
    payload: EntryCreate,
    db: Database,
    session: CurrentSession,
    response: Response,
) -> EntryRead:
    """Log one entry (one-tap capture); 422 on K8 input_mode violations."""
    try:
        entry_id, created = await store.create_entry(db, session, payload)
    except EntryInvalid as error:
        raise _tracker_invalid(error) from error
    except EntryIdConflict:
        return Response(status_code=status.HTTP_409_CONFLICT)
    except Exception as error:
        if isinstance(error, ValueError):
            raise HTTPException(status_code=422, detail=str(error)) from error
        raise
    entry = await store.get_entry(db, session, entry_id)
    if entry is None:
        raise _not_found("Entry")
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return entry


@router.get("/tracker/entries/{entry_id}", response_model=EntryRead)
async def read_entry(entry_id: UUID, db: Database, session: CurrentSession) -> EntryRead:
    entry = await store.get_entry(db, session, entry_id)
    if entry is None:
        raise _not_found("Entry")
    return entry


@router.patch("/tracker/entries/{entry_id}", response_model=EntryRead)
async def update_entry(
    entry_id: UUID, payload: EntryUpdate, db: Database, session: CurrentSession
) -> EntryRead:
    """Enrich an entry (time/money/note); never reparent."""
    try:
        entry = await store.update_entry(db, session, entry_id, payload)
    except EntryInvalid as error:
        raise _tracker_invalid(error) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if entry is None:
        raise _not_found("Entry")
    return entry


@router.delete("/tracker/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Soft-delete an entry — this is the one-tap undo button."""
    if not await store.soft_delete_entry(db, session, entry_id):
        raise _not_found("Entry")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tracker/entries/{entry_id}/restore", response_model=dict[str, str])
async def restore_entry(entry_id: UUID, db: Database, session: CurrentSession) -> dict[str, str]:
    entry = await store.restore_entry(db, session, entry_id)
    if entry is None:
        raise _not_found("Entry")
    return {"id": str(entry.id), "status": "restored"}


# ------------------------------------------------------------------ dashboard


@router.get("/tracker/dashboard", response_model=DashboardResponse)
async def dashboard(
    db: Database,
    session: CurrentSession,
    month: str | None = Query(default=None),
) -> DashboardResponse:
    """Compute behavior + finance dashboard for ``month=YYYY-MM`` (default = current +07)."""
    if month is None:
        vn_now = datetime.now(timezone(timedelta(hours=7)))
        month = f"{vn_now.year:04d}-{vn_now.month:02d}"
    try:
        return await dashboard_service.compute(db, session, month=month)
    except ValueError:
        raise HTTPException(status_code=422, detail="month must look like YYYY-MM")
