"""Authenticated day-annotation endpoints for the 010b calendar grid."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.annotations import (
    AnnotationCreate,
    AnnotationNotFound,
    AnnotationRead,
    AnnotationStore,
    AnnotationUpdate,
)
from app.domain.models import AuthSession
from app.web.deps import get_session, require_session

router = APIRouter(tags=["calendar"])
store = AnnotationStore()

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Day annotation not found",
    )


@router.get("/calendar/annotations", response_model=dict[str, list[AnnotationRead]])
async def list_annotations(
    db: Database,
    session: CurrentSession,
    from_: date = Query(default=..., alias="from"),
    to: date = Query(default=...),
) -> dict[str, list[AnnotationRead]]:
    """List every annotation intersecting an inclusive YYYY-MM-DD range."""
    if from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must be on or before to",
        )
    return {"items": await store.list_annotations(db, session, from_, to)}


@router.post("/calendar/annotations", response_model=AnnotationRead)
async def create_annotation(
    payload: AnnotationCreate,
    db: Database,
    session: CurrentSession,
    response: Response,
) -> AnnotationRead:
    """Create an annotation or idempotently return an existing explicit ID."""
    annotation = await store.create(db, session, payload)
    response.status_code = status.HTTP_201_CREATED if annotation.created else status.HTTP_200_OK
    return annotation


@router.patch("/calendar/annotations/{annotation_id}", response_model=AnnotationRead)
async def update_annotation(
    annotation_id: UUID,
    payload: AnnotationUpdate,
    db: Database,
    session: CurrentSession,
) -> AnnotationRead:
    """Patch one annotation, rejecting invalid merged date ranges."""
    try:
        return await store.update(db, session, annotation_id, payload)
    except AnnotationNotFound as error:
        raise _not_found() from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.delete(
    "/calendar/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_annotation(
    annotation_id: UUID,
    db: Database,
    session: CurrentSession,
) -> Response:
    """Hard-delete one annotation."""
    try:
        await store.delete(db, session, annotation_id)
    except AnnotationNotFound as error:
        raise _not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
