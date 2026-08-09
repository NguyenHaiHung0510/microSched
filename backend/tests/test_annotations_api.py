"""API coverage for the 010b day_annotation slice, including the privacy gate."""

import asyncio
import base64
import os
import time
from datetime import UTC, datetime, timedelta
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


def _uuid7() -> UUID:
    timestamp = int(time.time() * 1000)
    random_bits = int.from_bytes(os.urandom(10), "big") & ((1 << 74) - 1)
    value = (timestamp << 80) | (0x7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


def _auth(*, unlocked: bool = True) -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="annotation-api-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    """Keep API tests independent of developer and production secrets."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "annotation-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_annotation_endpoints_require_authentication() -> None:
    """Every endpoint stays behind the single protected API mount."""

    async def scenario() -> None:
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        annotation_id = uuid4()
        requests = [
            (
                "GET",
                "/api/calendar/annotations?from=2026-08-20&to=2026-08-25",
                None,
            ),
            (
                "POST",
                "/api/calendar/annotations",
                {"starts_on": "2026-08-20", "label": "Về quê"},
            ),
            ("PATCH", f"/api/calendar/annotations/{annotation_id}", {"label": "x"}),
            ("DELETE", f"/api/calendar/annotations/{annotation_id}", None),
        ]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for method, path, body in requests:
                response = await client.request(method, path, json=body)
                assert response.status_code == 401, (method, path, response.text)

    asyncio.run(scenario())


@pytest.mark.pg
def test_annotation_crud_validation_and_idempotency(pg_dsn: str) -> None:
    """Range intersection, merged validation, null rejection, and repeated IDs."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        auth = _auth()

        async def current_session() -> AuthSession:
            return auth

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
        annotation_ids: list[UUID] = []
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/calendar/annotations",
                    json={
                        "starts_on": "2026-08-20",
                        "ends_on": "2026-08-25",
                        "label": "Về quê",
                        "color": "rose",
                    },
                )
                assert created.status_code == 201
                annotation = created.json()
                annotation_id = UUID(annotation["id"])
                annotation_ids.append(annotation_id)

                # Giao nhau bao gồm hai đầu: ngày 24 vẫn thấy dấu 20-25/08.
                single_day = await client.get(
                    "/api/calendar/annotations?from=2026-08-24&to=2026-08-24"
                )
                assert single_day.status_code == 200
                assert annotation_id in {UUID(item["id"]) for item in single_day.json()["items"]}

                # ends_on < starts_on ngay ở DTO => 422, không phải 500.
                reversed_range = await client.post(
                    "/api/calendar/annotations",
                    json={"starts_on": "2026-08-25", "ends_on": "2026-08-20", "label": "Sai"},
                )
                assert reversed_range.status_code == 422

                # Patch chỉ starts_on làm merged starts_on > ends_on => 422 ở store.
                broken_merge = await client.patch(
                    f"/api/calendar/annotations/{annotation_id}",
                    json={"starts_on": "2026-08-30"},
                )
                assert broken_merge.status_code == 422

                # Label null bị từ chối ở DTO, không rơi xuống IntegrityError.
                null_label = await client.patch(
                    f"/api/calendar/annotations/{annotation_id}",
                    json={"label": None},
                )
                assert null_label.status_code == 422

                # Trùng id khi POST => 200 + bản cũ, không tạo bản hai.
                repeated = await client.post(
                    "/api/calendar/annotations",
                    json={
                        "id": str(annotation_id),
                        "starts_on": "2026-08-20",
                        "label": "Bản khác",
                    },
                )
                assert repeated.status_code == 200
                assert repeated.json()["id"] == str(annotation_id)
                assert repeated.json()["label"] == "Về quê"
                listed = await client.get("/api/calendar/annotations?from=2026-08-20&to=2026-08-25")
                assert len(listed.json()["items"]) == 1

                # color null xoá màu thật (nullable, không bị từ chối như label).
                cleared_color = await client.patch(
                    f"/api/calendar/annotations/{annotation_id}",
                    json={"color": None},
                )
                assert cleared_color.status_code == 200
                assert cleared_color.json()["color"] is None

                # label toàn khoảng trắng bị từ chối ở cả tạo và patch.
                blank_label = await client.post(
                    "/api/calendar/annotations",
                    json={"starts_on": "2026-09-01", "label": "   "},
                )
                assert blank_label.status_code == 422
                blank_patch = await client.patch(
                    f"/api/calendar/annotations/{annotation_id}",
                    json={"label": "   "},
                )
                assert blank_patch.status_code == 422

                # Xoá thật và biến mất khỏi danh sách.
                deleted = await client.delete(f"/api/calendar/annotations/{annotation_id}")
                assert deleted.status_code == 204
                after_delete = await client.get(
                    "/api/calendar/annotations?from=2026-08-20&to=2026-08-25"
                )
                assert annotation_id not in {
                    UUID(item["id"]) for item in after_delete.json()["items"]
                }

                missing = await client.patch(
                    f"/api/calendar/annotations/{uuid4()}",
                    json={"label": "x"},
                )
                assert missing.status_code == 404
        finally:
            connection = await asyncpg.connect(pg_dsn)
            try:
                for annotation_id in annotation_ids:
                    await connection.execute(
                        "DELETE FROM microsched.day_annotation WHERE id = $1",
                        annotation_id,
                    )
            finally:
                await connection.close()
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.pg
def test_annotation_privacy_gate_filters_locked_sessions(pg_dsn: str) -> None:
    """readable() really hides private annotations while the session is locked."""

    async def scenario() -> None:
        engine = create_async_engine(async_postgres_url(pg_dsn))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        holder: dict[str, AuthSession] = {"session": _auth(unlocked=True)}

        async def current_session() -> AuthSession:
            return holder["session"]

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
        annotation_ids: list[UUID] = []
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                private_id = _uuid7()
                annotation_ids.append(private_id)
                created = await client.post(
                    "/api/calendar/annotations",
                    json={
                        "id": str(private_id),
                        "starts_on": "2026-10-01",
                        "label": "Sinh nhật mẹ",
                        "is_private": True,
                    },
                )
                assert created.status_code == 201

                visible_unlocked = await client.get(
                    "/api/calendar/annotations?from=2026-10-01&to=2026-10-01"
                )
                assert private_id in {UUID(item["id"]) for item in visible_unlocked.json()["items"]}

                # Khoá lại phiên: dấu riêng tư biến mất khỏi cùng khoảng ngày.
                holder["session"] = _auth(unlocked=False)
                visible_locked = await client.get(
                    "/api/calendar/annotations?from=2026-10-01&to=2026-10-01"
                )
                assert private_id not in {
                    UUID(item["id"]) for item in visible_locked.json()["items"]
                }

                # Patch một dấu công khai thành riêng tư (phiên đã mở khoá): đọc
                # lại ngay sau vẫn thấy — patch không tự khoá phiên hiện tại.
                holder["session"] = _auth(unlocked=True)
                public_id = _uuid7()
                annotation_ids.append(public_id)
                public = await client.post(
                    "/api/calendar/annotations",
                    json={
                        "id": str(public_id),
                        "starts_on": "2026-10-02",
                        "label": "Dọn nhà",
                    },
                )
                assert public.status_code == 201
                toggled = await client.patch(
                    f"/api/calendar/annotations/{public_id}",
                    json={"is_private": True},
                )
                assert toggled.status_code == 200
                assert toggled.json()["is_private"] is True
                after_toggle = await client.get(
                    "/api/calendar/annotations?from=2026-10-02&to=2026-10-02"
                )
                assert public_id in {UUID(item["id"]) for item in after_toggle.json()["items"]}
        finally:
            connection = await asyncpg.connect(pg_dsn)
            try:
                for annotation_id in annotation_ids:
                    await connection.execute(
                        "DELETE FROM microsched.day_annotation WHERE id = $1",
                        annotation_id,
                    )
            finally:
                await connection.close()
            await engine.dispose()

    asyncio.run(scenario())
