"""Cookie/Origin authenticated socket and one-use CSRF ticket for Mimi voice."""

import asyncio
import json
from contextlib import suppress
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocketDisconnect

from app.agent.runtime import admit_run, release_run
from app.agent.voice_bridge import VoiceBridge
from app.agent.voice_preferences import VoicePreferences, voice_preference
from app.agent.voice_protocol import VoiceError
from app.agent.voice_store import VoiceStore, voice_available, voice_v2_available
from app.agent.voice_v2_bridge import VoiceV2Bridge, signal_voice_stop
from app.agent.voice_v2_store import VoiceV2Store
from app.core.db import get_sessionmaker
from app.core.sessions import SESSION_COOKIE_NAME
from app.core.settings import get_settings
from app.web.deps import get_session, get_session_store, require_session
from app.web.mimi_auth import require_mimi_workspace_session
from app.web.mimi_csrf import require_mimi_csrf

router = APIRouter(prefix="/mimi", tags=["mimi"])
socket_router = APIRouter()


class VoiceTicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_generation: int = Field(ge=1)


def require_voice_v2():
    if not voice_v2_available(get_settings()):
        raise HTTPException(404, "voice_unavailable")


@router.get(
    "/voice-preferences",
    dependencies=[Depends(require_mimi_workspace_session), Depends(require_voice_v2)],
)
async def get_voice_preferences(db=Depends(get_session), auth=Depends(require_session)):
    settings = await voice_preference(db, auth)
    return JSONResponse(settings.model_dump(), headers={"Cache-Control": "no-store"})


@router.patch(
    "/voice-preferences",
    dependencies=[
        Depends(require_mimi_workspace_session),
        Depends(require_voice_v2),
        Depends(require_mimi_csrf),
    ],
)
async def patch_voice_preferences(
    payload: VoicePreferences, db=Depends(get_session), auth=Depends(require_session)
):
    result = await voice_preference(db, auth, change=payload)
    await db.commit()
    return JSONResponse(result.model_dump(), headers={"Cache-Control": "no-store"})


@router.post(
    "/conversations/{conversation_id}/voice-ticket", dependencies=[Depends(require_mimi_csrf)]
)
async def create_ticket(
    conversation_id: UUID,
    payload: VoiceTicketCreate,
    db=Depends(get_session),
    auth=Depends(require_session),
):
    try:
        value = await VoiceStore.mint(
            db,
            get_sessionmaker(),
            get_settings(),
            auth,
            conversation_id,
            payload.expected_generation,
        )
    except VoiceError as error:
        raise HTTPException(401, str(error)) from None
    # The capability must be committed before the browser can use it.
    await db.commit()
    return JSONResponse(value, headers={"Cache-Control": "no-store"})


@router.post(
    "/conversations/{conversation_id}/voice/{run_id}/stop",
    dependencies=[Depends(require_mimi_csrf)],
)
async def stop_voice(conversation_id: UUID, run_id: UUID, auth=Depends(require_session)):
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(503, "voice_unavailable")
    try:
        await VoiceStore(factory, get_settings(), auth, conversation_id, run_id).stop()
    except VoiceError as error:
        raise HTTPException(401, str(error)) from None
    signal_voice_stop(run_id)
    return {"stopped": True}


def same_origin(socket: WebSocket, settings):
    expected = settings.mimi_public_origin or (
        f"{'https' if socket.url.scheme == 'wss' else 'http'}://{socket.url.netloc}"
    )
    try:
        actual, expected = urlsplit(socket.headers.get("origin", "")), urlsplit(expected)
        return (
            actual.scheme in {"http", "https"}
            and not actual.query
            and not actual.fragment
            and (actual.scheme, actual.netloc, actual.path.rstrip("/"))
            == (expected.scheme, expected.netloc, expected.path.rstrip("/"))
        )
    except ValueError:
        return False


# Explicit socket auth: require_session is Request-only, so this must NOT inherit
# the HTTP protected_api dependency. No other unauthenticated surface is exposed.
@socket_router.websocket("/api/mimi/conversations/{conversation_id}/voice/{run_id}")
async def voice_socket(socket: WebSocket, conversation_id: UUID, run_id: UUID):
    settings, factory = get_settings(), get_sessionmaker()
    store = get_session_store()
    token = socket.cookies.get(SESSION_COOKIE_NAME)
    if (
        not voice_available(settings)
        or factory is None
        or (not same_origin(socket, settings) or not token or store is None)
    ):
        await socket.close(code=1008)
        return
    try:
        auth = await store.load_valid(token)
    except Exception:
        await socket.close(code=1011)
        return
    if auth is None:
        await socket.close(code=1008)
        return
    consumed, admitted = False, False
    voice = VoiceV2Store(factory, settings, auth, conversation_id, run_id)
    try:
        admit_run(run_id)
        admitted = True
        await socket.accept()
        raw = await asyncio.wait_for(socket.receive_text(), timeout=5)
        if len(raw) > 256:
            raise VoiceError("voice_ticket_invalid_or_expired")
        hello = json.loads(raw)
        if (
            not isinstance(hello, dict)
            or set(hello) != {"type", "ticket"}
            or hello["type"] != "ticket"
        ):
            raise VoiceError("voice_ticket_required")
        config, seed, deadline = await voice.consume(hello["ticket"])
        consumed = True
        bridge = VoiceV2Bridge if voice.protocol_version == 2 else VoiceBridge
        await bridge(socket, voice).run(config, seed, deadline)
    except Exception, asyncio.CancelledError:
        # No provider wire/exception/socket repr is emitted to logs or client.
        if consumed:
            with suppress(Exception):
                await voice.finish(
                    reason="voice_server_error"
                    if voice.protocol_version == 2
                    else "voice_disconnected",
                    connected=False,
                    completed_turns=0,
                    usage=[],
                    counters={},
                )
    finally:
        if admitted:
            release_run(run_id)
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(code=1000 if consumed else 1008)
