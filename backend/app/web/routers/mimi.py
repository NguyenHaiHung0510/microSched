"""Authenticated, CSRF-protected HTTP surface for Mimi P1."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Annotated, Literal
from uuid import UUID, uuid7

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import (
    ConfirmationDecision,
    ConversationCreate,
    ConversationRename,
    ConversationStateChange,
    FeedbackCreate,
    MessageCreate,
    confirm_change_set,
    conversation_view,
    create_conversation,
    current_conversation,
    finish_interrupted_run,
    list_conversations,
    list_standard_tasks,
    prepare_run_resume,
    reconcile_unknown_run,
    rename_conversation,
    run_events_after,
    save_feedback,
    send_message,
    set_conversation_archived,
)
from app.core.db import get_sessionmaker
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.web.deps import get_session, require_session
from app.web.mimi_csrf import require_mimi_csrf

router = APIRouter(prefix="/mimi", tags=["mimi"])
logger = logging.getLogger(__name__)
Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]


def require_mimi_available() -> None:
    settings = get_settings()
    if settings.is_production and not (
        settings.mimi_real_chat_enabled and settings.mimi_live_provider_enabled
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _encode_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


async def _observe_run(factory, supervisor, auth, run_id: UUID, conversation_id: UUID):
    yield _encode_sse("run.reserved", {"run_id": str(run_id)})
    after = 0
    last_emit = time.monotonic()
    terminal_states = {
        "waiting_confirmation",
        "completed",
        "halted",
        "cancelled",
        "retryable",
        "outcome_unknown",
        "deadline_exceeded",
        "budget_exceeded",
    }
    while True:
        await asyncio.sleep(0.75)
        async with factory() as read_db:
            try:
                snapshot = await run_events_after(read_db, auth, run_id, after=after)
            except HTTPException as error:
                if error.status_code == 404 and supervisor.active(run_id):
                    if time.monotonic() - last_emit >= 15:
                        yield _encode_sse("run.heartbeat", {"run_id": str(run_id)})
                        last_emit = time.monotonic()
                    continue
                if error.status_code == 404:
                    conversation = await conversation_view(read_db, auth, conversation_id)
                    yield _encode_sse("conversation.snapshot", conversation)
                    return
                raise
            for item in snapshot["events"]:
                after = max(after, int(item["sequence"]))
                yield _encode_sse(item["kind"], item)
                last_emit = time.monotonic()
            if snapshot["state"] in terminal_states:
                conversation = await conversation_view(read_db, auth, conversation_id)
                yield _encode_sse("conversation.snapshot", conversation)
                return
            if time.monotonic() - last_emit >= 15:
                yield _encode_sse(
                    "run.heartbeat",
                    {"run_id": str(run_id), "state": snapshot["state"]},
                )
                last_emit = time.monotonic()


@router.post(
    "/conversations",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
    status_code=status.HTTP_201_CREATED,
)
async def start_conversation(
    payload: ConversationCreate, db: Database, session: CurrentSession
) -> dict:
    return await create_conversation(db, session, payload)


@router.get(
    "/conversations",
    dependencies=[Depends(require_mimi_available)],
)
async def read_conversations(
    db: Database,
    session: CurrentSession,
    state: Annotated[Literal["active", "archived", "all"], Query()] = "active",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> dict:
    return await list_conversations(
        db, session, state=state, limit=limit, cursor=cursor
    )


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


@router.patch(
    "/conversations/{conversation_id}",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def patch_conversation(
    conversation_id: UUID,
    payload: ConversationRename,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await rename_conversation(db, session, conversation_id, payload)


@router.post(
    "/conversations/{conversation_id}/archive",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def archive_conversation(
    conversation_id: UUID,
    payload: ConversationStateChange,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await set_conversation_archived(
        db, session, conversation_id, payload, archived=True
    )


@router.post(
    "/conversations/{conversation_id}/restore",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def restore_conversation(
    conversation_id: UUID,
    payload: ConversationStateChange,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await set_conversation_archived(
        db, session, conversation_id, payload, archived=False
    )


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


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def stream_message(
    conversation_id: UUID,
    payload: MessageCreate,
    request: Request,
    session: CurrentSession,
) -> StreamingResponse:
    """Start server-owned work and observe it over a disconnect-safe SSE stream."""
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    run_id = uuid7()
    detached_session = AuthSession.model_validate(session.model_dump())

    async def work() -> None:
        async with factory() as worker_db:
            try:
                await send_message(
                    worker_db,
                    detached_session,
                    conversation_id,
                    payload,
                    reserved_run_id=run_id,
                    provider_stream=True,
                )
                await worker_db.commit()
            except asyncio.CancelledError:
                await worker_db.rollback()
                async with factory() as terminal_db:
                    await finish_interrupted_run(
                        terminal_db,
                        detached_session,
                        run_id,
                        cancelled=True,
                    )
                    await terminal_db.commit()
                raise
            except Exception:
                logger.exception("mimi_run_worker_failed run_id=%s", run_id)
                await worker_db.rollback()
                async with factory() as terminal_db:
                    await finish_interrupted_run(
                        terminal_db,
                        detached_session,
                        run_id,
                        cancelled=False,
                    )
                    await terminal_db.commit()

    supervisor = request.app.state.mimi_run_supervisor
    supervisor.start(run_id, work())

    return StreamingResponse(
        _observe_run(factory, supervisor, detached_session, run_id, conversation_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/runs/{run_id}/events",
    dependencies=[Depends(require_mimi_available)],
)
async def read_run_events(
    run_id: UUID,
    db: Database,
    session: CurrentSession,
    after: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    return await run_events_after(db, session, run_id, after=after)


@router.post(
    "/runs/{run_id}/cancel",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_run(
    run_id: UUID,
    request: Request,
    db: Database,
    session: CurrentSession,
) -> dict:
    # Resolve ownership before consulting process-local state; UUID entropy is
    # never an authorization boundary.
    await run_events_after(db, session, run_id, after=0)
    supervisor = request.app.state.mimi_run_supervisor
    if not supervisor.cancel(run_id):
        raise HTTPException(status_code=409, detail="mimi_run_not_active_in_this_process")
    return {"run_id": run_id, "state": "cancelling"}


@router.post(
    "/runs/{run_id}/reconcile",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def reconcile_run(run_id: UUID, db: Database, session: CurrentSession) -> dict:
    return await reconcile_unknown_run(db, session, run_id)


@router.post(
    "/runs/{run_id}/resume",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def resume_run(
    run_id: UUID,
    request: Request,
    db: Database,
    session: CurrentSession,
) -> StreamingResponse:
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    conversation_id, successor_id, payload = await prepare_run_resume(db, session, run_id)
    await db.commit()
    detached_session = AuthSession.model_validate(session.model_dump())

    async def work() -> None:
        async with factory() as worker_db:
            try:
                await send_message(
                    worker_db,
                    detached_session,
                    conversation_id,
                    payload,
                    reserved_run_id=successor_id,
                    provider_stream=True,
                    record_user_message=False,
                    parent_run_id=run_id,
                )
                await worker_db.commit()
            except asyncio.CancelledError:
                await worker_db.rollback()
                async with factory() as terminal_db:
                    await finish_interrupted_run(
                        terminal_db,
                        detached_session,
                        successor_id,
                        cancelled=True,
                    )
                    await terminal_db.commit()
                raise
            except Exception:
                logger.exception("mimi_resume_worker_failed run_id=%s", successor_id)
                await worker_db.rollback()
                async with factory() as terminal_db:
                    await finish_interrupted_run(
                        terminal_db,
                        detached_session,
                        successor_id,
                        cancelled=False,
                    )
                    await terminal_db.commit()

    supervisor = request.app.state.mimi_run_supervisor
    supervisor.start(successor_id, work())
    return StreamingResponse(
        _observe_run(
            factory,
            supervisor,
            detached_session,
            successor_id,
            conversation_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
