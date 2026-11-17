"""HTTP guards scoped to /api/migarden; errors never echo submitted bodies."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.migarden.storage import Rejected
from app.web.deps import get_session

Database = Annotated[AsyncSession, Depends(get_session, scope="function")]


def now_utc() -> datetime:
    return datetime.now(UTC)


def require_enabled() -> None:
    if not get_settings().migarden_enabled:
        raise HTTPException(404, "Not Found")


async def owner_origin(request: Request) -> None:
    if request.method not in {"POST", "PUT"}:
        return
    expected = get_settings().migarden_public_origin or str(request.base_url).rstrip("/")
    supplied = request.headers.get("origin", "")
    try:
        supplied_origin, expected_origin = urlsplit(supplied), urlsplit(expected)
        same = (
            supplied_origin.scheme == expected_origin.scheme
            and supplied_origin.netloc == expected_origin.netloc
            and not (supplied_origin.path or supplied_origin.query or supplied_origin.fragment)
        )
    except ValueError:
        same = False
    site = request.headers.get("sec-fetch-site")
    if not same or (site is not None and site != "same-origin"):
        raise HTTPException(403, "migarden_origin_mismatch")
    if request.headers.get("x-migarden-csrf") != "1":
        raise HTTPException(403, "migarden_csrf_required")


async def json_body[T: BaseModel](request: Request, schema: type[T], limit: int) -> T:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "migarden_json_required")
    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            length = int(raw_length)
        except ValueError:
            raise HTTPException(400, "migarden_invalid_length") from None
        if not 0 <= length <= limit:
            raise HTTPException(413, "migarden_body_too_large")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "migarden_body_too_large")
        body.extend(chunk)
    try:
        return schema.model_validate_json(body)
    except ValidationError as error:
        errors = [
            {"loc": [str(part)[:128] for part in item["loc"]], "type": item["type"]}
            for item in error.errors(include_input=False, include_url=False)[:12]
        ]
        raise HTTPException(422, {"code": "migarden_invalid_payload", "fields": errors}) from None


async def verdict[T](action: Callable[[], Awaitable[T]]) -> T:
    try:
        return await action()
    except Rejected as error:
        raise HTTPException(error.status, error.code) from None
