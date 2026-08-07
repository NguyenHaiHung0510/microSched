"""Postgres-backed coverage for the subscription slice + F6 (011c)."""

import asyncio
import base64
import calendar
import os
import time
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import crypto
from app.core.database_urls import async_postgres_url
from app.core.settings import get_settings
from app.domain.models import AuthSession
from app.domain.tracker import _amount_out
from app.main import create_app
from app.web.deps import get_session, require_session

pytestmark = pytest.mark.pg

VN_TZ = timezone(timedelta(hours=7))


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
        token_hash=f"subscription-api-test-{_uuid7()}",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "subscription-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


def _make_client(pg_dsn: str, auth_state: dict):
    engine = create_async_engine(async_postgres_url(pg_dsn))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def current_session() -> AuthSession:
        return auth_state["value"]

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
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), engine


async def _create_tracker(client, *, kind="finance", input_mode="money", **overrides):
    payload = {"name": f"Tracker {_uuid7()}", "kind": kind, "input_mode": input_mode, **overrides}
    resp = await client.post("/api/tracker/trackers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _today_vn() -> str:
    return datetime.now(VN_TZ).date().isoformat()


async def _create_subscription(
    client, tracker_id, *, name=None, amount="300000", period_count=1, period_unit="month",
    started_on=None, expires_on=None, auto_renew=False, **overrides,
):
    payload = {
        "name": name or f"Sub {_uuid7()}",
        "tracker_id": str(tracker_id),
        "amount": amount,
        "period_count": period_count,
        "period_unit": period_unit,
        "started_on": started_on or _today_vn(),
        "expires_on": expires_on or _today_vn(),
        "auto_renew": auto_renew,
        **overrides,
    }
    resp = await client.post("/api/subscriptions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _cleanup(dsn: str, *, tracker_ids=None, subscription_ids=None, setting_keys=None):
    conn = await asyncpg.connect(dsn)
    try:
        if tracker_ids:
            await conn.execute(
                "DELETE FROM microsched.entry WHERE tracker_id = ANY($1::uuid[])", tracker_ids
            )
        if subscription_ids:
            await conn.execute(
                "DELETE FROM microsched.subscription WHERE id = ANY($1::uuid[])",
                subscription_ids,
            )
        if tracker_ids:
            await conn.execute(
                "DELETE FROM microsched.subscription WHERE tracker_id = ANY($1::uuid[])",
                tracker_ids,
            )
            await conn.execute(
                "DELETE FROM microsched.tracker WHERE id = ANY($1::uuid[])", tracker_ids
            )
        if setting_keys:
            await conn.execute(
                "DELETE FROM microsched.app_setting WHERE key = ANY($1::text[])", setting_keys
            )
    finally:
        await conn.close()


def test_create_subscription_is_idempotent_by_id(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub_id = _uuid7()
            payload = {
                "id": str(sub_id),
                "name": "Netflix",
                "tracker_id": tracker["id"],
                "amount": "260000",
                "period_count": 1,
                "period_unit": "month",
                "started_on": _today_vn(),
                "expires_on": _today_vn(),
                "auto_renew": True,
            }
            first = await client.post("/api/subscriptions", json=payload)
            assert first.status_code == 201, first.text
            second = await client.post("/api/subscriptions", json=payload)
            assert second.status_code == 200, second.text
            assert second.json()["id"] == str(sub_id)
            subscription_ids.append(sub_id)
            listed = await client.get("/api/subscriptions")
            assert listed.status_code == 200
            assert len(listed.json()["items"]) == 1
            assert listed.json()["items"][0]["status"] == "active"
            assert listed.json()["items"][0]["days_left"] == 0
            assert listed.json()["items"][0]["monthly_amount"] == 260000
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_tracker_type_guard_and_reverse_guard(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            event_tracker = await _create_tracker(client, kind="health", input_mode="event")
            tracker_ids.append(UUID(event_tracker["id"]))
            resp = await client.post(
                "/api/subscriptions",
                json={
                    "name": "Sub sai tracker",
                    "tracker_id": event_tracker["id"],
                    "amount": "100000",
                    "started_on": _today_vn(),
                    "expires_on": _today_vn(),
                },
            )
            assert resp.status_code == 422, resp.text
            assert "tài chính nhập số tiền" in resp.json()["detail"]

            money_tracker = await _create_tracker(client)
            tracker_ids.append(UUID(money_tracker["id"]))
            sub = await _create_subscription(client, money_tracker["id"], auto_renew=True)
            subscription_ids.append(UUID(sub["id"]))

            # Switching the tracker away from money with a live subscription ⇒ 422.
            resp = await client.patch(
                f"/api/tracker/trackers/{money_tracker['id']}",
                json={"input_mode": "event"},
            )
            assert resp.status_code == 422, resp.text
            assert "1 đăng ký" in resp.json()["detail"]

            # Archiving the tracker with a live subscription ⇒ 422.
            resp = await client.delete(f"/api/tracker/trackers/{money_tracker['id']}")
            assert resp.status_code == 422, resp.text
            assert "xoá hoặc chuyển chúng trước" in resp.json()["detail"]

            # Soft-delete the sub: now the tracker CAN change...
            resp = await client.delete(f"/api/subscriptions/{sub['id']}")
            assert resp.status_code == 204, resp.text
            resp = await client.patch(
                f"/api/tracker/trackers/{money_tracker['id']}", json={"input_mode": "event"}
            )
            assert resp.status_code == 200, resp.text

            # ...but restore re-validates finance + money (§2.5 back door).
            resp = await client.post(f"/api/subscriptions/{sub['id']}/restore")
            assert resp.status_code == 422, resp.text
            assert "tài chính nhập số tiền" in resp.json()["detail"]
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_renew_is_idempotent_and_pushes_expiry_once(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            # The anchor chain must stay in the future for any CI run date: use
            # the LAST DAY of the current month (always >= today in +07:00).
            today = datetime.now(VN_TZ).date()
            starts = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            starts_iso = starts.isoformat()
            sub = await _create_subscription(
                client,
                tracker["id"],
                name=f"Sub {_uuid7()}",
                amount="300000",
                started_on=starts_iso,
                expires_on=starts_iso,
                auto_renew=True,
            )
            subscription_ids.append(UUID(sub["id"]))
            entry_id = str(_uuid7())
            payload = {"entry_id": entry_id, "amount": "300000"}
            first = await client.post(f"/api/subscriptions/{sub['id']}/renew", json=payload)
            assert first.status_code == 200, first.text
            assert first.json()["created"] is True
            first_expiry = first.json()["subscription"]["expires_on"]

            def next_month_anchored(day: str, anchor: int) -> str:
                """One period forward, keeping the ORIGINAL anchor day (§4.2)."""
                value = date.fromisoformat(day)
                if value.month == 12:
                    year, month = value.year + 1, 1
                else:
                    year, month = value.year, value.month + 1
                return date(
                    year, month, min(anchor, calendar.monthrange(year, month)[1])
                ).isoformat()

            assert first_expiry == next_month_anchored(starts_iso, starts.day)

            second = await client.post(f"/api/subscriptions/{sub['id']}/renew", json=payload)
            assert second.status_code == 200, second.text
            assert second.json()["created"] is False
            assert second.json()["subscription"]["expires_on"] == first_expiry

            conn = await asyncpg.connect(pg_dsn)
            try:
                count = await conn.fetchval(
                    "SELECT count(*) FROM microsched.entry WHERE subscription_id = $1",
                    sub["id"],
                )
                assert count == 1
            finally:
                await conn.close()


            # A chained renewal keeps the anchor day: 31/01 → 28/02 → 31/03 (§4.2).
            third = await client.post(
                f"/api/subscriptions/{sub['id']}/renew",
                    json={"entry_id": str(_uuid7())},
            )
            assert third.status_code == 200, third.text
            assert third.json()["subscription"]["expires_on"] == next_month_anchored(
                first_expiry, starts.day
            )
            if starts.day == 31:
                assert third.json()["subscription"]["expires_on"].endswith("-31")
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_renew_lapsed_subscription_resumes_from_today(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            three_months_ago = (datetime.now(VN_TZ).date() - timedelta(days=90)).isoformat()
            sub = await _create_subscription(
                client,
                tracker["id"],
                amount="300000",
                started_on=three_months_ago,
                expires_on=three_months_ago,
            )
            subscription_ids.append(UUID(sub["id"]))
            resp = await client.post(
                f"/api/subscriptions/{sub['id']}/renew", json={"entry_id": str(_uuid7())}
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["created"] is True
            assert body["subscription"]["status"] == "active"
            assert body["subscription"]["expires_on"] > _today_vn()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_renew_client_expiry_validation(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub = await _create_subscription(
                client, tracker["id"], expires_on="2026-08-10", started_on="2026-08-01"
            )
            subscription_ids.append(UUID(sub["id"]))
            resp = await client.post(
                f"/api/subscriptions/{sub['id']}/renew",
                json={"entry_id": str(_uuid7()), "new_expires_on": "2026-08-10"},
            )
            assert resp.status_code == 422, resp.text
            resp = await client.post(
                f"/api/subscriptions/{sub['id']}/renew",
                json={"entry_id": str(_uuid7()), "new_expires_on": "2026-08-11"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["subscription"]["expires_on"] == "2026-08-11"
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_clear_canceled_is_opt_in(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub = await _create_subscription(client, tracker["id"])
            subscription_ids.append(UUID(sub["id"]))
            resp = await client.post(f"/api/subscriptions/{sub['id']}/cancel")
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "canceled"

            resp = await client.post(
                f"/api/subscriptions/{sub['id']}/renew", json={"entry_id": str(_uuid7())}
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["subscription"]["canceled_at"] is not None

            resp = await client.post(
                f"/api/subscriptions/{sub['id']}/renew",
                json={"entry_id": str(_uuid7()), "clear_canceled": True},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["subscription"]["canceled_at"] is None
            assert resp.json()["subscription"]["status"] == "active"

            resp = await client.post(f"/api/subscriptions/{sub['id']}/uncancel")
            assert resp.status_code == 200, resp.text
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_f6_burn_counts_and_conversions(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            tomorrow = (datetime.now(VN_TZ).date() + timedelta(days=1)).isoformat()
            yesterday = (datetime.now(VN_TZ).date() - timedelta(days=1)).isoformat()
            month_sub = await _create_subscription(
                client, tracker["id"], amount="260000", auto_renew=True, expires_on=tomorrow
            )
            week_sub = await _create_subscription(
                client,
                tracker["id"],
                name="Tuần",
                amount="300000",
                period_unit="week",
                auto_renew=True,
                expires_on=tomorrow,
            )
            year_sub = await _create_subscription(
                client,
                tracker["id"],
                name="Năm",
                amount="2400000",
                period_unit="year",
                auto_renew=True,
                expires_on=tomorrow,
            )
            day_sub = await _create_subscription(
                client,
                tracker["id"],
                name="Ngày",
                amount="100000",
                period_count=30,
                period_unit="day",
                auto_renew=True,
                expires_on=tomorrow,
            )
            no_auto = await _create_subscription(
                client,
                tracker["id"],
                name="Không tự gia hạn",
                auto_renew=False,
                expires_on=tomorrow,
            )
            expired = await _create_subscription(
                client, tracker["id"], name="Hết hạn", auto_renew=True,
                started_on=yesterday, expires_on=yesterday,
            )
            subscription_ids = [UUID(item["id"]) for item in
                [month_sub, week_sub, year_sub, day_sub, no_auto, expired]]

            resp = await client.get("/api/tracker/dashboard")
            assert resp.status_code == 200, resp.text
            f6 = resp.json()["f6"]
            assert f6["corrupted_subscription_count"] == 0
            # 260000 + 300000*7/30.4375 + 2400000/12 + 100000*30/30.4375, rounded once.
            expected = (
                Decimal("260000")
                + Decimal("300000") * Decimal("30.4375") / Decimal(7)
                + Decimal("200000")
                + Decimal("100000") * Decimal("30.4375") / Decimal(30)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            assert f6["monthly_burn"] == int(expected)
            assert f6["subscription_count"] == 4

            # ?month= is ignored: F6 is a snapshot of today (§4.3).
            past = await client.get("/api/tracker/dashboard?month=2026-01")
            assert past.status_code == 200, past.text
            assert past.json()["f6"]["monthly_burn"] == f6["monthly_burn"]
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_f6_corrupted_amount_stays_in_upcoming(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            tomorrow = (datetime.now(VN_TZ).date() + timedelta(days=1)).isoformat()
            good = await _create_subscription(
                client, tracker["id"], amount="100000", auto_renew=True, expires_on=tomorrow
            )
            bad = await _create_subscription(
                client, tracker["id"], name="Sắp trừ tiền", amount="200000", auto_renew=True,
                expires_on=tomorrow,
            )
            subscription_ids = [UUID(good["id"]), UUID(bad["id"])]
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "UPDATE microsched.subscription SET amount = 'enc:v1:garbage' WHERE id = $1",
                    bad["id"],
                )
            finally:
                await conn.close()

            resp = await client.get("/api/tracker/dashboard")
            assert resp.status_code == 200, resp.text
            f6 = resp.json()["f6"]
            assert f6["corrupted_subscription_count"] == 1
            assert f6["monthly_burn"] == 100000
            item = next(
                (row for row in f6["upcoming"] if row["subscription_id"] == bad["id"]), None
            )
            assert item is not None
            assert item["amount"] is None
            assert item["corrupted"] is True
            assert item["name"] == "Sắp trừ tiền"
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_private_tracker_hides_subscriptions_when_locked(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            private_tracker = await _create_tracker(client, is_private=True)
            tracker_ids.append(UUID(private_tracker["id"]))
            tomorrow = (datetime.now(VN_TZ).date() + timedelta(days=1)).isoformat()
            sub = await _create_subscription(
                client, private_tracker["id"], name="Sub riêng tư", auto_renew=True,
                expires_on=tomorrow,
            )
            subscription_ids.append(UUID(sub["id"]))

            locked_client, locked_engine = _make_client(pg_dsn, {"value": _auth(unlocked=False)})
            try:
                resp = await locked_client.get("/api/subscriptions")
                assert resp.status_code == 200
                assert resp.json()["items"] == []
                resp = await locked_client.get(f"/api/subscriptions/{sub['id']}")
                assert resp.status_code == 404
                resp = await locked_client.get("/api/tracker/dashboard")
                assert resp.status_code == 200
                assert resp.json()["f6"]["monthly_burn"] == 0
                assert resp.json()["f6"]["upcoming"] == []
            finally:
                await locked_client.aclose()
                await locked_engine.dispose()

            resp = await client.get("/api/subscriptions")
            assert resp.status_code == 200
            assert [item["id"] for item in resp.json()["items"]] == [sub["id"]]
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_subscription_update_validation_and_name_conflict(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub = await _create_subscription(client, tracker["id"])
            subscription_ids.append(UUID(sub["id"]))

            resp = await client.patch(
                f"/api/subscriptions/{sub['id']}",
                json={"started_on": "2026-08-20", "expires_on": "2026-08-10"},
            )
            assert resp.status_code == 422, resp.text

            resp = await client.post(
                "/api/subscriptions",
                json={
                    "name": sub["name"],
                    "tracker_id": tracker["id"],
                    "amount": "100000",
                    "started_on": _today_vn(),
                    "expires_on": _today_vn(),
                },
            )
            assert resp.status_code == 409, resp.text
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_subscription_expired_and_canceled_not_in_burn(pg_dsn: str):
    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            tomorrow = (datetime.now(VN_TZ).date() + timedelta(days=1)).isoformat()
            live = await _create_subscription(
                client, tracker["id"], amount="150000", auto_renew=True, expires_on=tomorrow
            )
            canceled = await _create_subscription(
                client, tracker["id"], name="Đã huỷ", amount="999000", auto_renew=True,
                expires_on=tomorrow,
            )
            await client.post(f"/api/subscriptions/{canceled['id']}/cancel")
            subscription_ids = [UUID(live["id"]), UUID(canceled["id"])]

            resp = await client.get("/api/tracker/dashboard")
            assert resp.status_code == 200, resp.text
            f6 = resp.json()["f6"]
            assert f6["monthly_burn"] == 150000
            assert f6["subscription_count"] == 1
            assert all(row["subscription_id"] != canceled["id"] for row in f6["upcoming"])

            listed = await client.get("/api/subscriptions")
            statuses = {item["status"] for item in listed.json()["items"]}
            assert statuses == {"active", "canceled"}
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_renew_entry_id_conflict_is_409_not_retry(pg_dsn: str):
    """Cùng entry_id nhưng thuộc bản ghi KHÁC ⇒ 409, không nuốt thành retry (§2.4).

    Cùng tracker nhưng khác subscription, và khác tracker — cả hai đều là xung
    đột thật, không phải lần gửi lại của chính mình. Khi gỡ guard so
    ``tracker_id``/``subscription_id`` trong ``create_entry``, bài này đỏ.
    """

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker_a = await _create_tracker(client)
            tracker_ids.append(UUID(tracker_a["id"]))
            tracker_b = await _create_tracker(client)
            tracker_ids.append(UUID(tracker_b["id"]))
            today = datetime.now(VN_TZ).date()
            starts = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            starts_iso = starts.isoformat()
            sub_a = await _create_subscription(
                client, tracker_a["id"], name=f"Sub A {_uuid7()}",
                started_on=starts_iso, expires_on=starts_iso,
            )
            sub_b_same_tracker = await _create_subscription(
                client, tracker_a["id"], name=f"Sub B {_uuid7()}",
                started_on=starts_iso, expires_on=starts_iso,
            )
            sub_c_other_tracker = await _create_subscription(
                client, tracker_b["id"], name=f"Sub C {_uuid7()}",
                started_on=starts_iso, expires_on=starts_iso,
            )
            subscription_ids = [
                UUID(item["id"]) for item in [sub_a, sub_b_same_tracker, sub_c_other_tracker]
            ]

            entry_id = str(_uuid7())
            first = await client.post(
                f"/api/subscriptions/{sub_a['id']}/renew",
                json={"entry_id": entry_id, "amount": "300000"},
            )
            assert first.status_code == 200, first.text
            assert first.json()["created"] is True

            same_tracker = await client.post(
                f"/api/subscriptions/{sub_b_same_tracker['id']}/renew",
                json={"entry_id": entry_id, "amount": "300000"},
            )
            assert same_tracker.status_code == 409, same_tracker.text

            other_tracker = await client.post(
                f"/api/subscriptions/{sub_c_other_tracker['id']}/renew",
                json={"entry_id": entry_id, "amount": "300000"},
            )
            assert other_tracker.status_code == 409, other_tracker.text

            conn = await asyncpg.connect(pg_dsn)
            try:
                count = await conn.fetchval(
                    "SELECT count(*) FROM microsched.entry WHERE id = $1", entry_id
                )
                assert count == 1
                # The rejected renewals must not have pushed their expiry.
                for sub in (sub_b_same_tracker, sub_c_other_tracker):
                    stored = await conn.fetchval(
                        "SELECT expires_on FROM microsched.subscription WHERE id = $1",
                        sub["id"],
                    )
                    assert str(stored) == starts_iso
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_renew_corrupt_amount_returns_422_guided(pg_dsn: str):
    """Amount hỏng (parse lẫn tampered tag) ⇒ 422 tiếng Việt, không 500 (§4.2).

    Gỡ ``renew_amount_or_raise`` (cho ``InvalidTag``/``ValueError`` bay ra) thì
    bài này đỏ: tampered tag trở thành 500, plain garbage trở thành 422 với
    message kỹ thuật tiếng Anh — cả hai đều sai hợp đồng.

    Lưu ý tầng DB: CHECK ``amount LIKE 'enc:v1:%'`` khiến một giá trị KHÔNG có
    prefix không bao giờ nằm được trong cột, nên dạng "parse lỗi" ở đây phải là
    một blob có prefix nhưng không giải mã được (b64 hợp lệ về cú pháp CHECK,
    vỡ ngay trong ``decrypt``) — không phải chuỗi thường như ở unit test.
    """

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            tomorrow = (datetime.now(VN_TZ).date() + timedelta(days=1)).isoformat()
            parse_broken = await _create_subscription(
                client, tracker["id"], name=f"Sub parse {_uuid7()}", expires_on=tomorrow
            )
            tag_broken = await _create_subscription(
                client, tracker["id"], name=f"Sub tag {_uuid7()}", expires_on=tomorrow
            )
            subscription_ids = [UUID(parse_broken["id"]), UUID(tag_broken["id"])]

            conn = await asyncpg.connect(pg_dsn)
            try:
                # Form 1: prefix hợp lệ nhưng không phải ciphertext thật — lọt
                # qua CHECK rồi vỡ trong decrypt (ValueError), không phải 500.
                await conn.execute(
                    "UPDATE microsched.subscription SET amount = 'enc:v1:AAAA' "
                    "WHERE id = $1",
                    parse_broken["id"],
                )
                # Form 2: ciphertext hợp lệ nhưng tag bị sửa → InvalidTag.
                sealed = _amount_out(Decimal("300000"))
                flip_at = len(sealed) // 2
                tampered = (
                    sealed[:flip_at]
                    + ("A" if sealed[flip_at] != "A" else "B")
                    + sealed[flip_at + 1 :]
                )
                await conn.execute(
                    "UPDATE microsched.subscription SET amount = $1 WHERE id = $2",
                    tampered,
                    tag_broken["id"],
                )
            finally:
                await conn.close()

            # 1. SUB-03: when amount is omitted in payload, corrupt stored amount returns 422 guided
            for sub in (parse_broken, tag_broken):
                resp = await client.post(
                    f"/api/subscriptions/{sub['id']}/renew",
                    json={"entry_id": str(_uuid7())},
                )
                assert resp.status_code == 422, resp.text
                assert "sửa số tiền" in resp.json()["detail"]

            # 2. SUB-03: when amount is provided in payload, renew succeeds
            #    without decoding corrupt stored amount
            for sub in (parse_broken, tag_broken):
                resp = await client.post(
                    f"/api/subscriptions/{sub['id']}/renew",
                    json={"entry_id": str(_uuid7()), "amount": "300000"},
                )
                assert resp.status_code == 200, resp.text

            conn = await asyncpg.connect(pg_dsn)
            try:
                count = await conn.fetchval(
                    "SELECT count(*) FROM microsched.entry "
                    "WHERE subscription_id = ANY($1::uuid[])",
                    [UUID(sub["id"]) for sub in (parse_broken, tag_broken)],
                )
                assert count == 2
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_renew_two_tabs_same_entry_id_creates_one_entry(pg_dsn: str):
    """Hai tab cùng bấm gia hạn với CÙNG entry_id ⇒ đúng một entry, một lần đẩy hạn.

    ``SELECT … FOR UPDATE`` trên hàng sub + ``ON CONFLICT DO NOTHING`` trên entry
    làm hai request chạy tuần tự hoá; kẻ thua trả ``created=False`` và không đụng
    ``expires_on``. Chạy qua hai client độc lập = hai transaction thật.
    """

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            today = datetime.now(VN_TZ).date()
            starts = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            starts_iso = starts.isoformat()
            sub = await _create_subscription(
                client, tracker["id"], name=f"Sub {_uuid7()}",
                started_on=starts_iso, expires_on=starts_iso, auto_renew=True,
            )
            subscription_ids.append(UUID(sub["id"]))
            entry_id = str(_uuid7())
            payload = {"entry_id": entry_id, "amount": "300000"}

            client2, engine2 = _make_client(pg_dsn, auth_state)
            try:
                first, second = await asyncio.gather(
                    client.post(f"/api/subscriptions/{sub['id']}/renew", json=payload),
                    client2.post(f"/api/subscriptions/{sub['id']}/renew", json=payload),
                )
            finally:
                await client2.aclose()
                await engine2.dispose()

            assert first.status_code == 200, first.text
            assert second.status_code == 200, second.text
            created_flags = sorted([first.json()["created"], second.json()["created"]])
            assert created_flags == [False, True], (first.text, second.text)
            assert (
                first.json()["subscription"]["expires_on"]
                == second.json()["subscription"]["expires_on"]
            )

            def next_month_anchored(day: str, anchor: int) -> str:
                value = date.fromisoformat(day)
                if value.month == 12:
                    year, month = value.year + 1, 1
                else:
                    year, month = value.year, value.month + 1
                return date(
                    year, month, min(anchor, calendar.monthrange(year, month)[1])
                ).isoformat()

            assert first.json()["subscription"]["expires_on"] == next_month_anchored(
                starts_iso, starts.day
            )
            conn = await asyncpg.connect(pg_dsn)
            try:
                count = await conn.fetchval(
                    "SELECT count(*) FROM microsched.entry WHERE subscription_id = $1",
                    sub["id"],
                )
                assert count == 1
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_get_subscription_tampered_tag_returns_422(pg_dsn: str):
    """SUB-02: reading a single subscription with a tampered tag returns 422, non-500."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub = await _create_subscription(client, tracker["id"])
            subscription_ids.append(UUID(sub["id"]))

            conn = await asyncpg.connect(pg_dsn)
            try:
                sealed = _amount_out(Decimal("500000"))
                flip_at = len(sealed) // 2
                tampered = (
                    sealed[:flip_at]
                    + ("A" if sealed[flip_at] != "A" else "B")
                    + sealed[flip_at + 1 :]
                )
                await conn.execute(
                    "UPDATE microsched.subscription SET amount = $1 WHERE id = $2",
                    tampered,
                    sub["id"],
                )
            finally:
                await conn.close()

            resp = await client.get(f"/api/subscriptions/{sub['id']}")
            assert resp.status_code == 422, resp.text
            assert resp.status_code != 500
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())


def test_restore_subscription_checks_kind_even_if_tracker_archived(pg_dsn: str):
    """SUB-01: sequence archive tracker ? switch kind ? restore sub ? 422."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids = []
        subscription_ids = []
        try:
            tracker = await _create_tracker(client)
            tracker_ids.append(UUID(tracker["id"]))
            sub = await _create_subscription(client, tracker["id"])
            subscription_ids.append(UUID(sub["id"]))

            # 1. Soft-delete subscription
            del_resp = await client.delete(f"/api/subscriptions/{sub['id']}")
            assert del_resp.status_code == 204

            # 2. Archive (soft-delete) parent tracker in DB
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "UPDATE microsched.tracker SET deleted_at = NOW(), "
                    "input_mode = 'event', kind = 'health' WHERE id = $1",
                    UUID(tracker["id"]),
                )
            finally:
                await conn.close()

            # 3. Restore subscription: must check parent tracker kind via
            #    with_privacy_gate and raise 422
            resp = await client.post(f"/api/subscriptions/{sub['id']}/restore")
            assert resp.status_code == 422, resp.text
            assert "t\u00e0i ch\u00ednh" in resp.json()["detail"]
        finally:
            await client.aclose()
            await engine.dispose()
            await _cleanup(
                pg_dsn, tracker_ids=tracker_ids, subscription_ids=subscription_ids
            )

    asyncio.run(scenario())
