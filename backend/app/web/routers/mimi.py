"""Authenticated, CSRF-protected HTTP surface for Mimi P1."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import (
    ConfirmationDecision,
    FeedbackCreate,
    MessageCreate,
    confirm_change_set,
    conversation_view,
    create_conversation,
    current_conversation,
    list_standard_tasks,
    save_feedback,
    send_message,
)
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.web.deps import get_session, require_session
from app.web.mimi_csrf import require_mimi_csrf

router = APIRouter(prefix="/mimi", tags=["mimi"])
Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def require_mimi_available() -> None:
    settings = get_settings()
    if settings.is_production and not (
        settings.mimi_real_chat_enabled and settings.mimi_live_provider_enabled
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post(
    "/conversations",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
    status_code=status.HTTP_201_CREATED,
)
async def start_conversation(db: Database, session: CurrentSession) -> dict:
    return await create_conversation(db, session)


@router.get(
    "/conversations/current",
    dependencies=[Depends(require_mimi_available)],
)
async def read_current_conversation(db: Database, session: CurrentSession) -> dict | None:
    return await current_conversation(db, session)


@router.get(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_mimi_available)],
)
async def read_conversation(conversation_id: UUID, db: Database, session: CurrentSession) -> dict:
    return await conversation_view(db, session, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def post_message(
    conversation_id: UUID,
    payload: MessageCreate,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await send_message(db, session, conversation_id, payload)


@router.get("/context/tasks", dependencies=[Depends(require_mimi_available)])
async def read_task_context(
    db: Database,
    session: CurrentSession,
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[dict]:
    return await list_standard_tasks(db, session, limit=limit)


@router.post(
    "/change-sets/{change_set_id}/decision",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def decide_change_set(
    change_set_id: UUID,
    payload: ConfirmationDecision,
    db: Database,
    session: CurrentSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict:
    return await confirm_change_set(db, session, change_set_id, payload, idempotency_key)


@router.post(
    "/conversations/{conversation_id}/feedback",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
    status_code=status.HTTP_201_CREATED,
)
async def post_feedback(
    conversation_id: UUID,
    payload: FeedbackCreate,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await save_feedback(db, session, conversation_id, payload)
