"""Owner/session API. No route here can be reached with only a device bearer."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.domain.migarden.commands import (
    CommandView,
    ConfirmInput,
    Preview,
    PreviewInput,
    confirm,
    prepare,
    request_stop,
)
from app.domain.migarden.configuration import ConfigView, SaveConfig, read_config, save_config
from app.domain.migarden.history_timeline import TimelineView, timeline
from app.domain.migarden.queries import DailyView, HistoryFilter, HistoryView, StateView, daily
from app.domain.migarden.queries import history as query_history
from app.domain.migarden.queries import state as query_state
from app.domain.migarden.storage import read_zone
from app.domain.migarden.wire import Empty
from app.domain.models import AuthSession
from app.web.deps import require_session
from app.web.migarden_http import (
    Database,
    json_body,
    now_utc,
    owner_origin,
    require_enabled,
    verdict,
)
from app.web.migarden_presence import mark_present

router = APIRouter(
    prefix="/migarden",
    tags=["miGarden"],
    dependencies=[Depends(require_enabled), Depends(owner_origin)],
)
Owner = Annotated[AuthSession, Depends(require_session)]


@router.get("/state")
async def state(request: Request, db: Database) -> StateView:
    result = await query_state(db, now_utc())
    if request.headers.get("x-migarden-visible") == "1":
        mark_present(request)
    return result


@router.get("/config")
async def config(db: Database) -> ConfigView:
    return await read_config(db, await read_zone(db))


@router.put("/config")
async def put_config(request: Request, db: Database) -> ConfigView:
    form = await json_body(request, SaveConfig, 4096)
    result = await verdict(lambda: save_config(db, form, now_utc()))
    mark_present(request)
    return result


@router.post("/start/preview")
async def preview(request: Request, db: Database, owner: Owner) -> Preview:
    form = await json_body(request, PreviewInput, 1024)
    result = await verdict(lambda: prepare(db, str(owner.id), form, now_utc))
    mark_present(request)
    return result


@router.post("/start/confirm")
async def confirm_start(request: Request, db: Database, owner: Owner) -> CommandView:
    form = await json_body(request, ConfirmInput, 1024)
    result = await verdict(lambda: confirm(db, str(owner.id), form, now_utc))
    mark_present(request)
    return result


@router.post("/stop")
async def stop(request: Request, db: Database, owner: Owner) -> CommandView:
    await json_body(request, Empty, 1024)
    result = await verdict(lambda: request_stop(db, str(owner.id), now_utc))
    mark_present(request)
    return result


@router.get("/history")
async def history(
    criteria: Annotated[HistoryFilter, Query()], db: Database
) -> HistoryView | TimelineView:
    query = timeline if criteria.view == "sessions" else query_history
    return await verdict(lambda: query(db, criteria, now_utc()))


@router.get("/daily")
async def daily_summary(
    db: Database, days: Annotated[Literal["7", "30"], Query()] = "7"
) -> DailyView:
    return await daily(db, int(days), now_utc())
