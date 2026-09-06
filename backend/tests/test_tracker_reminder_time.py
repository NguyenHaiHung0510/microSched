"""Whole-second guard coverage for the 035A reminder writer fence."""

import asyncio
from datetime import time

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.domain.tracker import TrackerCreate, TrackerInvalid, TrackerUpdate, _canonical_reminder
from app.web.deps import get_session, require_session
from app.web.routers.tracker import router


@pytest.mark.parametrize("dto", (TrackerCreate, TrackerUpdate))
def test_reminder_time_dtos_accept_whole_seconds(dto) -> None:
    """The future fence permits the exact second precision it requires."""
    payload = {"reminder_time": "08:30:00"}
    if dto is TrackerCreate:
        payload.update({"name": "Nhắc giờ", "kind": "health"})

    parsed = dto(**payload)

    assert parsed.reminder_time == time(8, 30)


@pytest.mark.parametrize("dto", (TrackerCreate, TrackerUpdate))
def test_reminder_time_dtos_reject_fractional_seconds(dto) -> None:
    """035A must reject a fractional reminder time before a future DB CHECK exists."""
    payload = {
        "reminder_time": "08:30:00.000001",
    }
    if dto is TrackerCreate:
        payload.update({"name": "Nhắc giờ", "kind": "health"})

    with pytest.raises(ValidationError, match="chính xác đến giây"):
        dto(**payload)


def test_reminder_domain_rejects_fractional_seconds() -> None:
    """The store's canonicalizer must also defend non-HTTP callers."""
    with pytest.raises(TrackerInvalid, match="chính xác đến giây"):
        _canonical_reminder(
            kind="health",
            input_mode="event",
            reminder_time=time(8, 30, 0, 1),
            reminder_text=None,
            reminder_mode="fixed",
            reminder_interval_days=1,
            reminder_action="confirm_event",
            allow_legacy=False,
            interval_was_omitted=False,
        )


def test_tracker_api_rejects_fractional_seconds_before_database_access() -> None:
    """POST and PATCH return FastAPI's 422 without invoking a tracker writer."""

    async def scenario() -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api")

        async def fake_db():
            yield object()

        async def fake_auth():
            return object()

        app.dependency_overrides[get_session] = fake_db
        app.dependency_overrides[require_session] = fake_auth
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/tracker/trackers",
                json={
                    "name": "Nhắc giờ",
                    "kind": "health",
                    "reminder_time": "08:30:00.000001",
                },
            )
            patched = await client.patch(
                "/api/tracker/trackers/01912345-6789-7000-8000-000000000001",
                json={"reminder_time": "08:30:00.000001"},
            )

        for response in (created, patched):
            assert response.status_code == 422
            assert "chính xác đến giây" in response.text

    asyncio.run(scenario())
