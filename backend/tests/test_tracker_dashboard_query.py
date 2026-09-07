"""HTTP-level query parsing tests for the bounded tracker dashboard report."""

from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.domain.dashboard import VN_TZ, DashboardResponse
from app.domain.models import AuthSession
from app.web.deps import get_session, require_session
from app.web.routers import tracker as tracker_router


class _FakeDashboardService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def compute(self, _db, _session, *, month: str, months: int = 1) -> DashboardResponse:
        self.calls.append((month, months))
        start = datetime(2025, 1, 1, tzinfo=VN_TZ)
        return DashboardResponse(
            period_start=start,
            period_end=start,
            report_months=months,
            previous_period_start=None,
            previous_period_end=None,
            current_period_days=0,
            prev_period_days=0,
            prev_period_truncated=False,
            corrupted_entry_count=0,
            activity_month=month,
        )


def _client(monkeypatch) -> tuple[TestClient, _FakeDashboardService]:
    fake_service = _FakeDashboardService()
    monkeypatch.setattr(tracker_router, "dashboard_service", fake_service)
    app = FastAPI()
    app.include_router(
        tracker_router.router,
        prefix="/api",
        dependencies=[Depends(require_session)],
    )

    async def fake_session() -> AuthSession:
        now = datetime.now(VN_TZ)
        return AuthSession(
            token_hash="dashboard-query-test",
            user_email="owner@example.com",
            expires_at=now,
        )

    async def fake_db():
        yield object()

    app.dependency_overrides[require_session] = fake_session
    app.dependency_overrides[get_session] = fake_db
    return TestClient(app), fake_service


def test_dashboard_months_accepts_numeric_http_queries_and_default(monkeypatch) -> None:
    client, fake_service = _client(monkeypatch)
    with client:
        default = client.get("/api/tracker/dashboard?month=2025-01")
        assert default.status_code == 200
        assert default.json()["report_months"] == 1
        for months in (1, 3, 6, 12):
            response = client.get(f"/api/tracker/dashboard?month=2025-01&months={months}")
            assert response.status_code == 200
            assert response.json()["report_months"] == months

    assert [months for _month, months in fake_service.calls] == [1, 1, 3, 6, 12]


def test_dashboard_months_rejects_invalid_http_queries_before_compute(monkeypatch) -> None:
    client, fake_service = _client(monkeypatch)
    with client:
        for value in ("0", "2", "13", "abc"):
            response = client.get(f"/api/tracker/dashboard?month=2025-01&months={value}")
            assert response.status_code == 422

    assert fake_service.calls == []
