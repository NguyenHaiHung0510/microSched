"""Authenticated task and nested checklist HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.tasks import (
    TaskCreate,
    TaskItemCreate,
    TaskItemRead,
    TaskItemUpdate,
    TaskListStatus,
    TaskRead,
    TaskStore,
    TaskUpdate,
)
from app.web.deps import get_session, require_session

router = APIRouter(tags=["task"])
store = TaskStore()

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@router.get("/tasks", response_model=dict[str, list[TaskRead]])
async def list_tasks(
    db: Database,
    session: CurrentSession,
    task_status: TaskListStatus = Query(default="open", alias="status"),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, list[TaskRead]]:
    """List visible tasks in a stable envelope."""
    return {"items": await store.list(db, session, status=task_status, limit=limit, offset=offset)}


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, db: Database, session: CurrentSession) -> TaskRead:
    """Create a task and initial checklist in one request transaction."""
    return await store.create(db, session, payload)


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
    task = await store.update(db, session, task_id, payload)
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
async def restore_task(
    task_id: UUID, db: Database, session: CurrentSession
) -> dict[str, str]:
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
