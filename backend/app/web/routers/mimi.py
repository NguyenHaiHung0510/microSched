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

from app.agent.notifications import (
    DevicePreferenceChange,
    DevicePreferenceProof,
    acknowledge,
    list_attention,
    read_preference,
    resolve_locator,
    set_preference,
)
from app.agent.policy import load_standard_policy
from app.agent.route_config import ConfigurationChange, profiles_for_ui
from app.agent.runtime import admit_run, hold_run_guard_if_enabled, release_run
from app.agent.service import (
    ConfirmationDecision,
    ConversationCreate,
    ConversationRename,
    ConversationStateChange,
    DraftDirectionDecision,
    FeedbackCreate,
    MessageCreate,
    _owner_id,
    confirm_change_set,
    conversation_checkpoint_view,
    conversation_configuration,
    conversation_view,
    create_conversation,
    current_conversation,
    decide_draft_direction,
    ensure_message_admissible,
    finish_interrupted_run,
    list_conversations,
    list_standard_tasks,
    prepare_run_resume,
    read_execution_receipt,
    reconcile_unknown_run,
    rename_conversation,
    request_run_pause,
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


@router.get("/capabilities", dependencies=[Depends(require_mimi_available)])
async def mimi_capabilities(_session: CurrentSession) -> dict:
    """Expose only non-secret route capability actually configured for this app."""

    settings = get_settings()
    from app.agent.workflow_pilot import pilot_available

    return {
        "workflow_pilot_enabled": pilot_available(settings),
        "context_v1_enabled": settings.mimi_context_v1_enabled,
        "live_provider_enabled": settings.mimi_live_provider_enabled,
        "requested_model": (
            settings.mimi_route_model if settings.mimi_live_provider_enabled else None
        ),
        "requested_effort": (
            settings.mimi_route_reasoning_effort if settings.mimi_live_provider_enabled else None
        ),
        "route_mode": settings.mimi_route_mode if settings.mimi_live_provider_enabled else None,
        "model_selection_enabled": (
            settings.mimi_context_v1_enabled and settings.mimi_live_provider_enabled
        ),
        "context_policy": "observed_prompt_trigger",
        "compaction_trigger_tokens": settings.mimi_compaction_trigger_tokens,
        "payload_limit_bytes": settings.mimi_max_payload_bytes,
        "model_profiles": profiles_for_ui(settings),
        "conversation_planning_mode": "prose",
        "runner": settings.mimi_runner,
        "context_limit": settings.mimi_route_context_tokens,
        "output_reserve": settings.mimi_route_max_output_tokens,
        "collection_enabled": settings.mimi_collection_enabled,
        "notifications_enabled": settings.mimi_notifications_enabled,
        "policy_id": load_standard_policy().policy_id if settings.mimi_context_v1_enabled else None,
        "policy_sha256": load_standard_policy().sha256
        if settings.mimi_context_v1_enabled
        else None,
    }


async def _observe_run(
    factory, supervisor, auth, run_id: UUID, conversation_id: UUID, *, after: int = 0
):
    yield _encode_sse("run.reserved", {"run_id": str(run_id)})
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
    return await list_conversations(db, session, state=state, limit=limit, cursor=cursor)


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


@router.get(
    "/conversations/{conversation_id}/context",
    dependencies=[Depends(require_mimi_available)],
)
async def read_conversation_context(
    conversation_id: UUID, db: Database, session: CurrentSession
) -> dict:
    return await conversation_checkpoint_view(db, session, conversation_id)


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


@router.get(
    "/conversations/{conversation_id}/configuration", dependencies=[Depends(require_mimi_available)]
)
async def read_conversation_configuration(
    conversation_id: UUID,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await conversation_configuration(db, session, conversation_id)


@router.put(
    "/conversations/{conversation_id}/configuration",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def change_conversation_configuration(
    conversation_id: UUID,
    payload: ConfigurationChange,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await conversation_configuration(db, session, conversation_id, payload)


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
    return await set_conversation_archived(db, session, conversation_id, payload, archived=True)


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
    return await set_conversation_archived(db, session, conversation_id, payload, archived=False)


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
    await ensure_message_admissible(db, session, conversation_id, payload)
    run_id = uuid7()
    async with hold_run_guard_if_enabled(run_id):
        return await send_message(db, session, conversation_id, payload, reserved_run_id=run_id)


@router.post(
    "/conversations/{conversation_id}/draft-direction",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def post_draft_direction(
    conversation_id: UUID,
    payload: DraftDirectionDecision,
    db: Database,
    session: CurrentSession,
) -> dict:
    return await decide_draft_direction(db, session, conversation_id, payload)


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def stream_message(
    conversation_id: UUID,
    payload: MessageCreate,
    request: Request,
    db: Database,
    session: CurrentSession,
) -> StreamingResponse:
    """Start server-owned work and observe it over a disconnect-safe SSE stream."""
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    await ensure_message_admissible(db, session, conversation_id, payload)
    run_id = uuid7()
    detached_session = AuthSession.model_validate(session.model_dump())
    # Authentication is complete; do not retain its ORM checkout for the SSE lifetime.
    await db.commit()

    async def work_body() -> None:
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
            except Exception as error:
                # SDK/driver chains can contain echoed requests or SQL values.
                # Durable run/call receipts keep the bounded diagnostic.
                logger.error(
                    "mimi_run_worker_failed run_id=%s error_type=%s status=%s",
                    run_id,
                    type(error).__name__,
                    error.status_code if isinstance(error, HTTPException) else None,
                )
                await worker_db.rollback()
                async with factory() as terminal_db:
                    await finish_interrupted_run(
                        terminal_db,
                        detached_session,
                        run_id,
                        cancelled=False,
                    )
                    await terminal_db.commit()

    async def work() -> None:
        async with hold_run_guard_if_enabled(run_id, already_admitted=True):
            await work_body()

    supervisor = request.app.state.mimi_run_supervisor
    admit_run(run_id)
    coroutine = work()
    try:
        supervisor.start(run_id, coroutine)
    except Exception:
        coroutine.close()
        release_run(run_id)
        raise

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


@router.get(
    "/runs/{run_id}/events/stream",
    dependencies=[Depends(require_mimi_available)],
)
async def observe_existing_run(
    run_id: UUID,
    request: Request,
    db: Database,
    session: CurrentSession,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """Reattach to a durable run without creating a new model turn."""

    snapshot = await run_events_after(db, session, run_id, after=after)
    await db.commit()
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    detached_session = AuthSession.model_validate(session.model_dump())
    return StreamingResponse(
        _observe_run(
            factory,
            request.app.state.mimi_run_supervisor,
            detached_session,
            run_id,
            snapshot["conversation_id"],
            after=after,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    "/runs/{run_id}/pause",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def pause_run(run_id: UUID, db: Database, session: CurrentSession) -> dict:
    return await request_run_pause(db, session, run_id)


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

    async def work_body() -> None:
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

    async def work() -> None:
        async with hold_run_guard_if_enabled(successor_id, already_admitted=True):
            await work_body()

    supervisor = request.app.state.mimi_run_supervisor
    admit_run(successor_id)
    coroutine = work()
    try:
        supervisor.start(successor_id, coroutine)
    except Exception:
        coroutine.close()
        release_run(successor_id)
        raise
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
    result = await confirm_change_set(db, session, change_set_id, payload, idempotency_key)
    # Yield-dependency cleanup may run after HTTP success headers. Keep the
    # Task, receipt and idempotency commit ahead of every success response.
    try:
        await db.commit()
    except Exception as error:
        await db.rollback()
        # Driver exceptions may embed SQL parameters or connection details.
        logger.error(
            "mimi_confirmation_commit_failed change_set_id=%s error_type=%s",
            change_set_id,
            type(error).__name__,
        )
        raise HTTPException(status_code=503, detail="mimi_confirmation_commit_failed") from None
    return result


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


async def require_mimi_notifications():
    if not get_settings().mimi_notifications_enabled:
        raise HTTPException(404, "Mimi attention is disabled")


@router.post(
    "/devices/preference/read",
    dependencies=[
        Depends(require_mimi_available),
        Depends(require_mimi_csrf),
        Depends(require_mimi_notifications),
    ],
)
async def read_mimi_device_preference(
    payload: DevicePreferenceProof, db: Database, session: CurrentSession
):
    # Proof stays in a CSRF-protected body, never URL/query/referrer state.
    return await read_preference(db, _owner_id(session), payload)


@router.post(
    "/devices/preference",
    dependencies=[
        Depends(require_mimi_available),
        Depends(require_mimi_csrf),
        Depends(require_mimi_notifications),
    ],
)
async def change_mimi_device_preference(
    payload: DevicePreferenceChange, db: Database, session: CurrentSession
):
    return await set_preference(db, _owner_id(session), payload)


@router.get(
    "/attention",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_notifications)],
)
async def read_mimi_attention(db: Database, session: CurrentSession):
    return await list_attention(db, _owner_id(session))


@router.post(
    "/attention/{intent_id}/read",
    dependencies=[
        Depends(require_mimi_available),
        Depends(require_mimi_csrf),
        Depends(require_mimi_notifications),
    ],
)
async def read_mimi_attention_ack(intent_id: UUID, db: Database, session: CurrentSession):
    return await acknowledge(db, _owner_id(session), intent_id)


@router.get(
    "/attention/resolve/{locator}",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_notifications)],
)
async def resolve_mimi_attention(locator: str, db: Database, session: CurrentSession):
    if not 1 <= len(locator) <= 100:
        raise HTTPException(404, "Mimi attention not found")
    return await resolve_locator(db, _owner_id(session), locator)


@router.get(
    "/conversations/{conversation_id}/evidence/{bundle_id}",
    dependencies=[Depends(require_mimi_available)],
)
async def read_mimi_evidence(
    conversation_id: UUID, bundle_id: UUID, db: Database, session: CurrentSession
):
    from app.agent.evidence import read_evidence
    from app.agent.service import _conversation

    conversation = await _conversation(db, session, conversation_id)
    return await read_evidence(db, conversation, bundle_id)


@router.get(
    "/conversations/{conversation_id}/change-sets/{change_set_id}/receipt",
    dependencies=[Depends(require_mimi_available)],
)
async def read_mimi_execution_receipt(
    conversation_id: UUID,
    change_set_id: UUID,
    db: Database,
    session: CurrentSession,
    digest: Annotated[str, Query(min_length=64, max_length=64, pattern="^[0-9a-f]{64}$")],
    nonce: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)],
):
    return await read_execution_receipt(
        db, session, conversation_id, change_set_id, digest, nonce, idempotency_key
    )


@router.post(
    "/receipts/{receipt_id}/undo-preview",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def prepare_mimi_undo(receipt_id: UUID, db: Database, session: CurrentSession):
    from app.agent.service import prepare_receipt_undo

    return await prepare_receipt_undo(db, session, receipt_id)


@router.get(
    "/conversations/{conversation_id}/selections/{selection_id}",
    dependencies=[Depends(require_mimi_available)],
)
async def read_mimi_selection(
    conversation_id: UUID, selection_id: UUID, db: Database, session: CurrentSession
):
    from app.agent import crypto
    from app.agent.selection import load_selection
    from app.agent.service import _conversation

    if not get_settings().mimi_collection_enabled:
        raise HTTPException(404, "Mimi collections are disabled")
    conversation = await _conversation(db, session, conversation_id)
    if conversation.is_private or conversation.sensitivity != "standard":
        raise HTTPException(404, "Mimi selection not found")
    return await load_selection(
        db, conversation.id, selection_id, crypto.unwrap_dek(conversation.dek_wrapped)
    )


@router.post(
    "/conversations/{conversation_id}/provider-pool/refresh",
    dependencies=[Depends(require_mimi_available), Depends(require_mimi_csrf)],
)
async def refresh_mimi_provider_pool(conversation_id: UUID, db: Database, session: CurrentSession):
    from app.agent.route_config import bind_configuration, default_configuration
    from app.agent.route_pool import NoEligibleEndpoint, bind_pool
    from app.agent.service import _conversation

    settings = get_settings()
    if not settings.mimi_collection_enabled or not settings.mimi_live_provider_enabled:
        raise HTTPException(404, "Mimi endpoint pool is disabled")
    conversation = await _conversation(db, session, conversation_id)
    if conversation.is_private or conversation.sensitivity != "standard":
        raise HTTPException(404, "Mimi endpoint pool not found")
    selected = bind_configuration(
        settings, conversation.route_config or default_configuration(settings)
    )
    try:
        _, pool = await bind_pool(selected, manual=True)
    except NoEligibleEndpoint as error:
        raise HTTPException(409, str(error)) from error
    return {
        "model": pool.model,
        "effort": pool.effort,
        "tags": pool.tags,
        "checked_at": pool.checked_at,
        "snapshot_sha256": pool.snapshot_sha256,
        "min_uptime_percent": pool.threshold,
        "window": pool.window,
        "exclusions": pool.exclusions,
        "qualification": "METADATA_ONLY_NO_MODEL_CALL",
    }
