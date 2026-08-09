"""Postgres-backed API coverage for calendar import and CRUD protections."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.main import create_app
from app.web.deps import get_session, require_session

FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "quirky.ics").read_text(encoding="utf-8")
SINGLE_EVENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Buổi kiểm tra
DTSTART:20260815T070000
DTEND:20260815T090000
END:VEVENT
END:VCALENDAR"""


def _auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="calendar-api-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(minutes=15),
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    """Keep API tests independent of developer and production secrets."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "calendar-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_calendar_endpoints_require_authentication() -> None:
    """Every endpoint stays behind the single protected API mount."""

    async def scenario() -> None:
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        source_id = uuid4()
        event_id = uuid4()
        requests = [
            ("GET", "/api/calendar/sources", None),
            ("POST", "/api/calendar/sources", {"name": "x", "kind": "manual"}),
            ("PATCH", f"/api/calendar/sources/{source_id}", {"name": "x"}),
            ("DELETE", f"/api/calendar/sources/{source_id}", None),
            (
                "POST",
                f"/api/calendar/sources/{source_id}/import",
                {"filename": "x.ics", "content": FIXTURE_TEXT},
            ),
            (
                "GET",
                "/api/calendar/events?from=2026-08-15T00:00:00%2B07:00&"
                "to=2026-08-16T00:00:00%2B07:00",
                None,
            ),
            (
                "POST",
                "/api/calendar/events",
                {
                    "source_id": str(source_id),
                    "title": "x",
                    "starts_at": "2026-08-15T07:00:00+07:00",
                    "ends_at": "2026-08-15T08:00:00+07:00",
                },
            ),
            ("PATCH", f"/api/calendar/events/{event_id}", {"title": "x"}),
            ("DELETE", f"/api/calendar/events/{event_id}", None),
        ]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for method, path, body in requests:
                response = await client.request(method, path, json=body)
                assert response.status_code == 401, (method, path, response.text)

    asyncio.run(scenario())


def test_oversized_import_body_is_rejected_before_json_parsing() -> None:
    """The raw Content-Length guard protects the import route before FastAPI reads JSON."""

    async def scenario() -> None:
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/calendar/sources/{uuid4()}/import",
                content=b"x" * (2 * 1024 * 1024 + 1),
                headers={"content-type": "application/json"},
            )
            assert response.status_code == 413

    asyncio.run(scenario())


@pytest.mark.pg
def test_calendar_crud_import_visibility_and_safety(pg_dsn: str) -> None:
    """Import replacement, kind rules, filters, conflicts, and cascades use real DB behavior."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()

        async def current_session() -> AuthSession:
            return _auth()

        async def request_session():
            async with maker() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        app.dependency_overrides[require_session] = current_session
        app.dependency_overrides[get_session] = request_session
        transport = httpx.ASGITransport(app=app)
        source_ids: list[UUID] = []
        event_ids: list[UUID] = []
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/calendar/sources",
                    json={"name": "Lịch học test", "kind": "ics", "color": "sky"},
                )
                assert created.status_code == 201
                source = created.json()
                source_id = UUID(source["id"])
                source_ids.append(source_id)
                imported = await client.post(
                    f"/api/calendar/sources/{source_id}/import",
                    json={"filename": "quirky.ics", "content": FIXTURE_TEXT},
                )
                assert imported.status_code == 200
                assert imported.json()["parsed"] == 10
                assert imported.json()["inserted"] == 5
                assert imported.json()["removed"] == 0
                source_items = (await client.get("/api/calendar/sources")).json()["items"]
                assert source_items[0]["event_count"] == 5

                repeated = await client.post(
                    f"/api/calendar/sources/{source_id}/import",
                    json={"filename": "quirky.ics", "content": FIXTURE_TEXT},
                )
                assert repeated.status_code == 200
                assert repeated.json()["removed"] == 5
                source_items = (await client.get("/api/calendar/sources")).json()["items"]
                assert source_items[0]["event_count"] == 5

                many_events = "\n".join(
                    ["BEGIN:VCALENDAR"]
                    + [
                        "BEGIN:VEVENT\n"
                        f"SUMMARY:Buổi {number}\n"
                        f"DTSTART:20260815T{number // 60:02d}{number % 60:02d}00\n"
                        f"DTEND:20260815T{(number // 60 + 1):02d}{number % 60:02d}00\n"
                        "END:VEVENT"
                        for number in range(150)
                    ]
                    + ["END:VCALENDAR"]
                )
                many = await client.post(
                    f"/api/calendar/sources/{source_id}/import",
                    json={"filename": "many.ics", "content": many_events},
                )
                assert many.status_code == 200
                assert many.json()["inserted"] == 150
                listed_many = await client.get(
                    "/api/calendar/events?from=2026-08-15T00:00:00%2B07:00&"
                    "to=2026-08-16T00:00:00%2B07:00"
                )
                assert len(listed_many.json()["items"]) == 150

                garbage = await client.post(
                    f"/api/calendar/sources/{source_id}/import",
                    json={"filename": "garbage.ics", "content": "BEGIN:VCALENDAR\nEND:VCALENDAR"},
                )
                assert garbage.status_code == 422
                source_items = (await client.get("/api/calendar/sources")).json()["items"]
                assert source_items[0]["event_count"] == 150

                name_conflict = await client.post(
                    "/api/calendar/sources",
                    json={"name": "LỊCH HỌC TEST", "kind": "manual"},
                )
                assert name_conflict.status_code == 409
                assert name_conflict.json()["detail"]["existing_source_id"] == str(source_id)

                idempotent = await client.post(
                    "/api/calendar/sources",
                    json={"id": str(source_id), "name": "Khác", "kind": "manual"},
                )
                assert idempotent.status_code == 200
                assert idempotent.json()["id"] == str(source_id)

                manual_response = await client.post(
                    "/api/calendar/sources",
                    json={"name": "Lịch thủ công", "kind": "manual", "color": "rose"},
                )
                assert manual_response.status_code == 201
                manual_id = UUID(manual_response.json()["id"])
                source_ids.append(manual_id)
                manual_import = await client.post(
                    f"/api/calendar/sources/{manual_id}/import",
                    json={"filename": "x.ics", "content": FIXTURE_TEXT},
                )
                assert manual_import.status_code == 409
                patch_conflict = await client.patch(
                    f"/api/calendar/sources/{manual_id}", json={"name": "LỊCH HỌC TEST"}
                )
                assert patch_conflict.status_code == 409

                forbidden_event = await client.post(
                    "/api/calendar/events",
                    json={
                        "source_id": str(source_id),
                        "title": "Không được tạo dưới ICS",
                        "starts_at": "2026-08-15T07:00:00+07:00",
                        "ends_at": "2026-08-15T08:00:00+07:00",
                    },
                )
                assert forbidden_event.status_code == 409

                event_response = await client.post(
                    "/api/calendar/events",
                    json={
                        "source_id": str(manual_id),
                        "title": "Buổi thủ công",
                        "starts_at": "2026-08-15T07:00:00+07:00",
                        "ends_at": "2026-08-15T09:00:00+07:00",
                        "location": "Phòng họp",
                    },
                )
                assert event_response.status_code == 201
                event_id = UUID(event_response.json()["id"])
                event_ids.append(event_id)
                overlap = await client.get(
                    "/api/calendar/events?from=2026-08-15T08:00:00%2B07:00&"
                    "to=2026-08-15T08:30:00%2B07:00"
                )
                assert event_id in {UUID(item["id"]) for item in overlap.json()["items"]}

                reparent = await client.patch(
                    f"/api/calendar/events/{event_id}",
                    json={"source_id": str(source_id), "title": "Đã sửa"},
                )
                assert reparent.status_code == 200
                assert reparent.json()["source_id"] == str(manual_id)
                assert reparent.json()["title"] == "Đã sửa"

                hidden = await client.patch(
                    f"/api/calendar/sources/{manual_id}", json={"is_visible": False}
                )
                assert hidden.status_code == 200
                visible = await client.get(
                    "/api/calendar/events?from=2026-08-15T00:00:00%2B07:00&"
                    "to=2026-08-16T00:00:00%2B07:00"
                )
                all_events = await client.get(
                    "/api/calendar/events?from=2026-08-15T00:00:00%2B07:00&"
                    "to=2026-08-16T00:00:00%2B07:00&include_hidden=true"
                )
                assert event_id not in {UUID(item["id"]) for item in visible.json()["items"]}
                assert event_id in {UUID(item["id"]) for item in all_events.json()["items"]}

                deleted_event = await client.delete(f"/api/calendar/events/{event_id}")
                assert deleted_event.status_code == 204
                source_items = (await client.get("/api/calendar/sources")).json()["items"]
                manual_item = next(item for item in source_items if item["id"] == str(manual_id))
                assert manual_item["event_count"] == 0

                cascade_response = await client.post(
                    "/api/calendar/sources",
                    json={"name": "Nguồn cascade", "kind": "ics"},
                )
                cascade_id = UUID(cascade_response.json()["id"])
                source_ids.append(cascade_id)
                assert (
                    await client.post(
                        f"/api/calendar/sources/{cascade_id}/import",
                        json={"filename": "one.ics", "content": SINGLE_EVENT_ICS},
                    )
                ).status_code == 200
                deleted_source = await client.delete(f"/api/calendar/sources/{cascade_id}")
                assert deleted_source.status_code == 204
                remaining = (await client.get("/api/calendar/sources")).json()["items"]
                assert all(item["id"] != str(cascade_id) for item in remaining)
                assert any(item["id"] == str(source_id) for item in remaining)

                missing_import = await client.post(
                    f"/api/calendar/sources/{uuid4()}/import",
                    json={"filename": "x.ics", "content": FIXTURE_TEXT},
                )
                assert missing_import.status_code == 404
        finally:
            connection = await asyncpg.connect(pg_dsn)
            try:
                for source_id in source_ids:
                    await connection.execute(
                        "DELETE FROM microsched.calendar_source WHERE id = $1", source_id
                    )
            finally:
                await connection.close()
            await engine.dispose()

    asyncio.run(scenario())
