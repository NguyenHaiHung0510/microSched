"""The Controller's separate bounded HTTPS JSON route."""

from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.settings import get_settings
from app.domain.migarden.credentials import TOKEN, allows, digest
from app.domain.migarden.exchange import exchange
from app.domain.migarden.storage import lock_zone, read_zone
from app.domain.migarden.wire import ExchangeIn, ExchangeOut
from app.web.migarden_http import Database, json_body, now_utc, require_enabled, verdict

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


def limit_device_load(request: Request) -> None:
    # One singleton Controller per deployment. One bounded bucket per process,
    # no client-controlled map; allow immediate receipt/backlog drain without polling delay.
    now = monotonic()
    last, budget = getattr(request.app.state, "migarden_exchange_budget", (now, BURST))
    budget = min(BURST, budget + (now - last) * PER_SECOND)
    if budget < 1:
        raise HTTPException(429, "Exchange limit", headers={"Retry-After": "1"})
    request.app.state.migarden_exchange_budget = (now, budget - 1)


@router.post("/exchange")
async def device_exchange(request: Request, db: Database) -> ExchangeOut:
    auth = request.headers.getlist("authorization")
    if len(auth) != 1:
        raise unauthorized()
    scheme, _, token = auth[0].partition(" ")
    if scheme.lower() != "bearer" or not TOKEN.fullmatch(token):
        raise unauthorized()
    token_hash = digest(token)
    production = get_settings().is_production
    if not allows(await read_zone(db), token_hash, production):
        raise unauthorized()
    limit_device_load(request)
    packet = await json_body(request, ExchangeIn, BODY_LIMIT)
    zone = await verdict(lambda: lock_zone(db))
    if not allows(zone, token_hash, production) or packet.device_id != zone.device_id:
        raise unauthorized()
    return await verdict(lambda: exchange(db, zone, packet, now_utc()))
