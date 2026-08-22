"""Authenticated task and nested checklist HTTP endpoints."""

from datetime import UTC, datetime, time, timedelta, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.tasks import (
    InvalidTaskCursor,
    PrivateWriteLocked,
    TaskBucket,
    TaskCreate,
    TaskIdConflict,
    TaskItemCreate,
    TaskItemRead,
    TaskItemUpdate,
    TaskListStatus,
    TaskRead,
    TaskStore,
    TaskTimeline,
    TaskUpdate,
)
from app.web.deps import get_session, require_session

router = APIRouter(tags=["task"])
store = TaskStore()
try:
    VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except ZoneInfoNotFoundError:
    # Minimal throwaway Python images can omit the tzdata package. Vietnam has no
    # DST, so the fallback preserves the named-zone civil-time contract without
    # making every backend import fail in that environment.
    VIETNAM_TZ = timezone(timedelta(hours=7))

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


def _private_locked() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Private mode is locked",
    )


@router.get("/tasks", response_model=dict[str, object])
async def list_tasks(
    db: Database,
    session: CurrentSession,
    task_status: TaskListStatus = Query(default="open", alias="status"),
    limit: int = Query(default=100, ge=1, le=100),
    cursor: str | None = Query(default=None),
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    bucket: TaskBucket = Query(default="dated"),
) -> dict[str, object]:
    """List tasks through the bounded cursor/range contract."""
    try:
        from_instant = _parse_instant(from_value)
        to_instant = _parse_instant(to_value)
        page = await store.list_cursor(
            db,
            session,
            status=task_status,
            from_instant=from_instant,
            to_instant=to_instant,
            bucket=bucket,
            limit=limit,
            cursor=cursor,
        )
    except (InvalidTaskCursor, ValueError) as error:
        raise HTTPException(status_code=422, detail="Invalid or expired task cursor") from error
    return page.model_dump(mode="json")


def _parse_instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidTaskCursor("invalid date range") from error
    if result.tzinfo is None:
        raise InvalidTaskCursor("date range must include a timezone offset")
    return result.astimezone(UTC)


def _default_timeline_range() -> tuple[datetime, datetime]:
    today = datetime.now(VIETNAM_TZ).date()
    start = today - timedelta(days=3)
    end = today + timedelta(days=4)
    return (
        datetime.combine(start, time.min, tzinfo=VIETNAM_TZ),
        datetime.combine(end, time.min, tzinfo=VIETNAM_TZ),
    )


@router.get("/tasks/timeline", response_model=TaskTimeline)
async def timeline_tasks(
    db: Database,
    session: CurrentSession,
    task_status: TaskListStatus = Query(default="open", alias="status"),
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=100),
) -> TaskTimeline:
    """Return the seven-day/overdue/undated aggregate wave for TaskScreen."""
    try:
        if from_value is None and to_value is None:
            from_instant, to_instant = _default_timeline_range()
        elif from_value is not None and to_value is not None:
            from_instant = _parse_instant(from_value)
            to_instant = _parse_instant(to_value)
            assert from_instant is not None and to_instant is not None
        else:
            raise InvalidTaskCursor("from and to must be supplied together")
        if to_instant <= from_instant or (to_instant - from_instant).days > 366:
            raise InvalidTaskCursor("invalid timeline range")
        return await store.timeline(
            db,
            session,
            status=task_status,
            from_instant=from_instant,
            to_instant=to_instant,
            limit=limit,
        )
    except (InvalidTaskCursor, ValueError) as error:
        raise HTTPException(status_code=422, detail="Invalid timeline range") from error


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate, db: Database, session: CurrentSession, response: Response
) -> TaskRead | Response:
    """Create a task and initial checklist in one request transaction."""
    try:
        task = await store.create(db, session, payload)
    except TaskIdConflict:
        return Response(status_code=status.HTTP_409_CONFLICT)
    except PrivateWriteLocked as error:
        raise _private_locked() from error
    response.status_code = status.HTTP_201_CREATED if task.created else status.HTTP_200_OK
    return task


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def read_task(task_id: UUID, db: Database, session: CurrentSession) -> TaskRead:
    """Read one visible task."""
    task = await store.get(db, session, task_id)
    if task is None:
        raise _not_found()
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID, payload: TaskUpdate, db: Database, session: CurrentSession
) -> TaskRead:
    """Patch one visible task."""
    try:
        task = await store.update(db, session, task_id, payload)
    except PrivateWriteLocked as error:
        raise _private_locked() from error
    if task is None:
        raise _not_found()
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: UUID, db: Database, session: CurrentSession) -> Response:
    """Soft-delete one visible task."""
    if not await store.soft_delete(db, session, task_id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tasks/{task_id}/restore", response_model=dict[str, str])
async def restore_task(task_id: UUID, db: Database, session: CurrentSession) -> dict[str, str]:
    """Restore one privacy-visible task without returning its content."""
    task = await store.restore(db, session, task_id)
    if task is None:
        raise _not_found()
    return {"id": str(task.id), "status": "restored"}


@router.get("/tasks/{task_id}/items", response_model=list[TaskItemRead])
async def list_task_items(
    task_id: UUID, db: Database, session: CurrentSession
) -> list[TaskItemRead]:
    """List checklist items through their visible parent."""
    items = await store.list_items(db, session, task_id)
    if items is None:
        raise _not_found()
    return items


@router.post(
    "/tasks/{task_id}/items",
    response_model=TaskItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_item(
    task_id: UUID,
    payload: TaskItemCreate,
    db: Database,
    session: CurrentSession,
) -> TaskItemRead:
    """Append a checklist item through its visible, locked parent."""
    item = await store.add_item(db, session, task_id, payload)
    if item is None:
        raise _not_found()
    return item


@router.patch("/tasks/{task_id}/items/{item_id}", response_model=TaskItemRead)
async def update_task_item(
    task_id: UUID,
    item_id: UUID,
    payload: TaskItemUpdate,
    db: Database,
    session: CurrentSession,
) -> TaskItemRead:
    """Patch a checklist item without allowing reparenting."""
    try:
        item = await store.update_item(db, session, task_id, item_id, payload)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    if item is None:
        raise _not_found()
    return item


@router.delete("/tasks/{task_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_item(
    task_id: UUID, item_id: UUID, db: Database, session: CurrentSession
) -> Response:
    """Delete a checklist item through its visible, locked parent."""
    if not await store.delete_item(db, session, task_id, item_id):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
