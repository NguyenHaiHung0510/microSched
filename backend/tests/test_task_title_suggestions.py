"""Synthetic title-only HTTP/query contract; no Postgres or provider is used."""

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import sqlite

from app.domain.models import AuthSession
from app.web.deps import get_session, get_session_store, require_session
from app.web.routers.tasks import router


class TitleDatabase:
    def __init__(self, rows):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("ATTACH DATABASE ':memory:' AS microsched")
        self.connection.execute(
            "CREATE TABLE microsched.task (id INTEGER, title TEXT, body_md TEXT, "
            "is_private BOOLEAN, deleted_at TEXT, created_at TEXT)"
        )
        self.connection.executemany(
            "INSERT INTO microsched.task VALUES (?, ?, 'BODY MUST NOT ESCAPE', ?, ?, ?)", rows
        )
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        compiled = statement.compile(dialect=sqlite.dialect(paramstyle="named"))
        rows = self.connection.execute(str(compiled), compiled.params).fetchall()
        assert list(statement.selected_columns.keys()) == ["title"]
        return SimpleNamespace(scalars=lambda: [row[0] for row in rows])


def request(db, *, unlocked=False, authenticated=True):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def database():
        yield db

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[get_session_store] = lambda: None
    if authenticated:
        now = datetime.now(UTC)
        auth = AuthSession(
            token_hash="synthetic-title-session",
            user_email="synthetic@example.test",
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
            private_until=now + timedelta(minutes=15) if unlocked else None,
        )
        app.dependency_overrides[require_session] = lambda: auth

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://synthetic.test"
        ) as client:
            return await client.get("/api/tasks/title-suggestions")

    return asyncio.run(run())


@pytest.mark.parametrize("unlocked", [False, True])
def test_standard_title_only_read_even_with_private_unlocked(unlocked):
    db = TitleDatabase(
        [
            (1, "[TRAINING] upper body", False, None, "2026-11-15"),
            (2, "[TRAINING] upper body", False, None, "2026-11-16"),
            (3, "PRIVATE SYNTHETIC SENTINEL", True, None, "2026-11-17"),
            (4, "DELETED SYNTHETIC SENTINEL", False, "2026-11-16", "2026-11-17"),
            (5, "enc:v1:synthetic-ciphertext", False, None, "2026-11-17"),
            (6, "  ", False, None, "2026-11-17"),
            (7, " Đọc sách ", False, None, "2026-11-17"),
        ]
    )
    try:
        response = request(db, unlocked=unlocked)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert sorted(response.json(), key=lambda row: row["title"]) == [
            {"title": "[TRAINING] upper body", "count": 2},
            {"title": "Đọc sách", "count": 1},
        ]
        assert len(db.statements) == 1
        assert db.connection.total_changes == 7  # SELECT did not mutate rows.
    finally:
        db.connection.close()


@pytest.mark.parametrize("size", [328, 600])
def test_recent_sample_bounds_before_counting_and_keeps_frequency(size):
    db = TitleDatabase(
        [(i, "Repeated" if i % 2 else f"Title {i}", False, None, "2026-11-16") for i in range(size)]
    )
    try:
        response = request(db)
        assert response.status_code == 200
        data = response.json()
        assert sum(row["count"] for row in data) == min(size, 512)
        assert (
            next(row["count"] for row in data if row["title"] == "Repeated") == min(size, 512) // 2
        )
        if size > 512:
            assert {row["title"] for row in data}.isdisjoint({"Title 0", "Title 86"})
    finally:
        db.connection.close()


def test_unauthenticated_source_is_rejected_before_query():
    db = TitleDatabase([(1, "Title", False, None, "2026-11-16")])
    try:
        response = request(db, authenticated=False)
        assert response.status_code == 401
        assert db.statements == []
    finally:
        db.connection.close()
