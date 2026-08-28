"""Targeted tests for task and checklist whitespace rejection guards (DTO and HTTP API)."""

import asyncio
import base64
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core import crypto
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.domain.tasks import TaskCreate, TaskItemCreate, TaskItemUpdate
from app.main import create_app
from app.web.deps import get_session, require_session


def _test_auth() -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        token_hash="whitespace-guard-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=now + timedelta(minutes=15),
    )


async def _dummy_db():
    yield None


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "whitespace-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def test_task_create_rejects_whitespace_only_items() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(title="Valid Title", items=["   "])
    assert "must not be blank" in str(exc_info.value)

    # Multiple items with one whitespace
    with pytest.raises(ValidationError) as exc_info:
        TaskCreate(title="Valid Title", items=["Item 1", "  \t\n  ", "Item 3"])
    assert "must not be blank" in str(exc_info.value)

    # Valid non-empty items pass
    task = TaskCreate(title="Valid Title", items=["Item 1", "Item 2"])
    assert task.items == ["Item 1", "Item 2"]


def test_task_item_create_rejects_whitespace_content() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TaskItemCreate(content="   ")
    assert "content must not be blank" in str(exc_info.value)

    # Valid content passes
    item = TaskItemCreate(content="Valid content")
    assert item.content == "Valid content"


def test_task_item_update_rejects_whitespace_content() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TaskItemUpdate(content="   ")
    assert "content must not be blank" in str(exc_info.value)

    # Omitting content is allowed for update (partial patch)
    item_omitted = TaskItemUpdate(is_completed=True)
    assert item_omitted.content is None
    assert item_omitted.is_completed is True

    # Valid content passes
    item_valid = TaskItemUpdate(content="Updated content")
    assert item_valid.content == "Updated content"


def test_http_api_task_create_rejects_whitespace_only_items() -> None:
    """HTTP POST /api/tasks returns 422 Unprocessable Entity when items contain blank string."""

    async def scenario():
        app = create_app()
        app.dependency_overrides[require_session] = _test_auth
        app.dependency_overrides[get_session] = _dummy_db
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/tasks",
                json={"title": "Học bài", "items": ["   "]},
            )
            assert response.status_code == 422
            assert "must not be blank" in response.text

    asyncio.run(scenario())


def test_http_api_task_child_add_rejects_whitespace_content() -> None:
    """HTTP POST /api/tasks/{taskId}/items returns 422 when content is whitespace-only."""

    async def scenario():
        app = create_app()
        app.dependency_overrides[require_session] = _test_auth
        app.dependency_overrides[get_session] = _dummy_db
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            task_id = uuid4()
            response = await client.post(
                f"/api/tasks/{task_id}/items",
                json={"content": "  \t\n  "},
            )
            assert response.status_code == 422
            assert "content must not be blank" in response.text

    asyncio.run(scenario())


def test_http_api_task_child_update_rejects_whitespace_content() -> None:
    """HTTP PATCH /api/tasks/{taskId}/items/{itemId} returns 422 when content is whitespace-only."""

    async def scenario():
        app = create_app()
        app.dependency_overrides[require_session] = _test_auth
        app.dependency_overrides[get_session] = _dummy_db
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            task_id = uuid4()
            item_id = uuid4()
            response = await client.patch(
                f"/api/tasks/{task_id}/items/{item_id}",
                json={"content": "   "},
            )
            assert response.status_code == 422
            assert "content must not be blank" in response.text

    asyncio.run(scenario())
