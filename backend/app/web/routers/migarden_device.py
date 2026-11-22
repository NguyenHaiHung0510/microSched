"""The Controller's separate bounded HTTPS JSON route."""

from contextlib import asynccontextmanager
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.settings import get_settings
from app.domain.migarden.credentials import TOKEN, allows, digest
from app.domain.migarden.exchange import exchange
from app.domain.migarden.health import ingest_health
from app.domain.migarden.storage import lock_zone, read_zone
from app.domain.migarden.wire import ExchangeEnvelope
from app.web.deps import get_session
from app.web.migarden_http import json_body, now_utc, require_enabled, verdict
from app.web.migarden_presence import hint_idle
from app.web.migarden_quiet import EXTENSION, gate

BODY_LIMIT = 32 * 1024
BURST = 24
PER_SECOND = 8

router = APIRouter(
    prefix="/api/migarden/device",
    tags=["miGarden device"],
    dependencies=[Depends(require_enabled)],
)


def unauthorized() -> HTTPException:
    return HTTPException(401, "Invalid device credential", headers={"WWW-Authenticate": "Bearer"})


def limit_device_load(request: Request, *, known: bool = False) -> None:
    # One singleton Controller per deployment. One bounded bucket per process,
    # no client-controlled map; allow immediate receipt/backlog drain without polling delay.
    now = monotonic()
    bucket = "migarden_exchange_budget_known" if known else "migarden_exchange_budget_unknown"
    last, budget = getattr(request.app.state, bucket, (now, BURST))
    budget = min(BURST, budget + (now - last) * PER_SECOND)
    if budget < 1:
        raise HTTPException(429, "Exchange limit", headers={"Retry-After": "1"})
    setattr(request.app.state, bucket, (now, budget - 1))


@router.post("/exchange", response_model=None)
async def device_exchange(request: Request):
    auth = request.headers.getlist("authorization")
    if len(auth) != 1:
        limit_device_load(request)
        raise unauthorized()
    scheme, _, token = auth[0].partition(" ")
    if scheme.lower() != "bearer" or not TOKEN.fullmatch(token):
        limit_device_load(request)
        raise unauthorized()
    token_hash = digest(token)
    quiet = gate(request)
    limit_device_load(request, known=token_hash == quiet.routing_hash)
    envelope = await json_body(request, ExchangeEnvelope, BODY_LIMIT)
    negotiated = request.headers.get("x-migarden-extension") == EXTENSION
    known = quiet.known(token_hash, envelope.device_id)
    if negotiated:
        if known:
            if not quiet.enter(token_hash, envelope, True):
                # No identity, clock, freshness, config, control or ACK.
                return JSONResponse({"protocol": "migarden.wait.v1", "retry_after_seconds": 5}, 202)
        elif not quiet.bootstrap():
            # A routing hint cannot reject a newly bound credential. Keep the
            # wait transient until the next bounded authoritative lookup.
            raise HTTPException(503, "Exchange retry", headers={"Retry-After": "5"})
    authenticated = False
    try:
        production = get_settings().is_production
        async with asynccontextmanager(get_session)(request) as db:
            observed_zone = await read_zone(db)
            if negotiated:
                quiet.remember_zone(observed_zone)
            if not allows(observed_zone, token_hash, production):
                raise unauthorized()
            zone = await verdict(lambda: lock_zone(db))
            if not allows(zone, token_hash, production) or envelope.device_id != zone.device_id:
                raise unauthorized()
            authenticated = True
            now = now_utc()
            result = await exchange(db, zone, envelope, now)
            if negotiated:
                await ingest_health(db, envelope, zone, now)
            result = await hint_idle(request, db, envelope, result, zone)
            terminal = bool(db.info.get("migarden_new_terminal"))
        # The outer commit above must finish before ACK, negotiation or gate state.
        if negotiated and result.retry_after_seconds == 30:
            quiet.failed()
        elif negotiated:
            quiet.committed(token_hash, envelope, terminal=terminal)
    except HTTPException:
        # Invalid auth/context cannot move the genuine stream's retry clock.
        raise
    except BaseException:
        if negotiated:
            if known or authenticated:
                quiet.failed()
            else:
                quiet.bootstrap_failed()
        raise
    finally:
        if negotiated:
            if known:
                quiet.busy = False
            else:
                quiet.bootstrap_busy = False
    payload = result.model_dump(mode="json")
    if negotiated:
        payload["extension"] = EXTENSION
        if result.retry_after_seconds is None:
            payload["retry_after_seconds"] = 2
    return payload
