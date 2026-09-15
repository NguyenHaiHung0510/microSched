"""Mimi-scoped same-origin CSRF guard for every state-changing request."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from app.core.settings import get_settings


async def require_mimi_csrf(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="mimi_json_required"
        )
    if request.headers.get("x-mimi-csrf") != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="mimi_csrf_header_required"
        )
    if request.headers.get("sec-fetch-site", "").lower() != "same-origin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="mimi_cross_site_forbidden"
        )

    origin = request.headers.get("origin")
    configured = get_settings().mimi_public_origin
    expected = configured.rstrip("/") if configured else str(request.base_url).rstrip("/")
    try:
        supplied_origin = urlsplit(origin or "")
        expected_origin = urlsplit(expected)
    except ValueError as error:
        raise HTTPException(status_code=403, detail="mimi_origin_invalid") from error
    if (
        supplied_origin.scheme,
        supplied_origin.netloc,
        supplied_origin.path.rstrip("/"),
    ) != (expected_origin.scheme, expected_origin.netloc, expected_origin.path.rstrip("/")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="mimi_origin_mismatch")
