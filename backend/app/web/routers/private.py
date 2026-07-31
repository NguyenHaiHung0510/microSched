"""Authenticated endpoints for the private-display gate and PIN rotation."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuthSession
from app.domain.private_gate import (
    ThrottleLockedError,
    WrongPinError,
    lock_now,
    set_pin,
    unlock,
)
from app.web.deps import get_session, require_session

router = APIRouter(prefix="/private", tags=["private"])

Database = Annotated[AsyncSession, Depends(get_session)]
CurrentSession = Annotated[AuthSession, Depends(require_session)]
Pin = Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class UnlockRequest(BaseModel):
    pin: Pin


class UnlockResponse(BaseModel):
    private_until: datetime


class SetPinRequest(BaseModel):
    current_pin: str | None = None
    new_pin: str


def _wrong(remaining: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Sai PIN", "remaining": remaining},
    )


def _locked(retry_after_seconds: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Đang khoá tạm",
            "retry_after_seconds": retry_after_seconds,
        },
        headers={"Retry-After": str(retry_after_seconds)},
    )


@router.post("/unlock", response_model=UnlockResponse)
async def unlock_private(
    payload: UnlockRequest,
    db: Database,
    session: CurrentSession,
) -> UnlockResponse | JSONResponse:
    """Verify the PIN under the global throttle and open this session once."""
    outcome = await unlock(db, session, payload.pin)
    if outcome == "NO_PIN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chưa đặt PIN")
    if isinstance(outcome, tuple) and outcome[0] == "WRONG":
        return _wrong(outcome[1])
    if isinstance(outcome, tuple) and outcome[0] == "LOCKED":
        return _locked(outcome[1])
    if isinstance(outcome, tuple) and outcome[0] == "OK":
        return UnlockResponse(private_until=outcome[1])
    raise RuntimeError("unexpected private unlock outcome")


@router.post("/lock", status_code=status.HTTP_204_NO_CONTENT)
async def lock_private(db: Database, session: CurrentSession) -> Response:
    """Close this session's display gate immediately."""
    await lock_now(db, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/pin",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def change_private_pin(
    payload: SetPinRequest,
    db: Database,
    session: CurrentSession,
) -> Response | JSONResponse:
    """Set or rotate the global PIN through the same throttled verifier."""
    try:
        await set_pin(db, session, payload.current_pin, payload.new_pin)
    except WrongPinError as error:
        return _wrong(error.remaining)
    except ThrottleLockedError as error:
        return _locked(error.retry_after_seconds)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PIN phải đúng 6 chữ số",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
