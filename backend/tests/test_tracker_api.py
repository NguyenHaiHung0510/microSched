"""Postgres-backed coverage for the tracker / entry / dashboard slice (011a)."""

import asyncio
import base64
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

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

pytestmark = pytest.mark.pg


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
        token_hash="tracker-api-test-session",
        user_email="owner@example.com",
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        private_until=(now + timedelta(minutes=15)) if unlocked else None,
    )


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    """A single stable key for the whole module so leftover rows across tests decrypt."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "tracker-api-test-secret")
    monkeypatch.setenv(
        "ENCRYPTION_MASTER_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
    )
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


async def _cleanup(dsn: str, table: str, ids: list[UUID]) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        for row_id in ids:
            if row_id is not None:
                if table == "tracker":
                    # entry.tracker_id -> tracker.id is RESTRICT; drop the entries first
                    # so a routed _cleanup never trips the FK on removal.
                    await conn.execute("DELETE FROM microsched.entry WHERE tracker_id = $1", row_id)
                await conn.execute(f"DELETE FROM microsched.{table} WHERE id = $1", row_id)
    finally:
        await conn.close()


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
    # raise_app_exceptions=False keeps application-level 500s (e.g. the corrupt
    # ciphertext on the single-entry read path) as real HTTP responses instead of
    # re-raising them in-process — matching how a real ASGI server surfaces them.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), engine


async def _create_tracker(client, *, name="Hút thuốc", kind="health", **overrides):
    payload = {"name": name, "kind": kind, "input_mode": "event", **overrides}
    resp = await client.post("/api/tracker/trackers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_entry(client, tracker_id, **overrides):
    payload = {"tracker_id": str(tracker_id), **overrides}
    resp = await client.post("/api/tracker/entries", json=payload)
    return resp


def test_public_tracker_name_is_ciphertext_at_rest(pg_dsn: str):
    """Tạo tracker công khai ⇒ `name` trong DB bắt đầu bằng `enc:v1:` (spec §2.1 #1)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Hoàn toàn công khai")
            tracker_id = UUID(tracker["id"])
            conn = await asyncpg.connect(pg_dsn)
            try:
                stored = await conn.fetchval(
                    "SELECT name FROM microsched.tracker WHERE id = $1", tracker_id
                )
            finally:
                await conn.close()
            assert stored.startswith("enc:v1:")
            assert crypto.decrypt(stored) == "Hoàn toàn công khai"
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_toggle_private_keeps_name_ciphertext(pg_dsn: str):
    """Bật rồi tắt is_private ⇒ name vẫn ciphertext, giải mã ra đúng chuỗi cũ (§2.1 #2)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Thuốc X")
            tracker_id = UUID(tracker["id"])
            assert (
                await client.patch(f"/api/tracker/trackers/{tracker_id}", json={"is_private": True})
            ).status_code == 200
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{tracker_id}", json={"is_private": False}
                )
            ).status_code == 200
            conn = await asyncpg.connect(pg_dsn)
            try:
                stored = await conn.fetchval(
                    "SELECT name FROM microsched.tracker WHERE id = $1", tracker_id
                )
            finally:
                await conn.close()
            assert stored.startswith("enc:v1:")
            assert crypto.decrypt(stored) == "Thuốc X"
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_private_tracker_gated_through_parent(pg_dsn: str):
    """Entry của tracker riêng tư: ẩn khi khoá ở list + F1, hiện lại khi mở (§2.2 + §4.3)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        entry_ids: list[UUID] = []
        tracker_id = None
        try:
            tracker = await _create_tracker(
                client, name="Tiền riêng", kind="finance", input_mode="money", is_private=True
            )
            tracker_id = UUID(tracker["id"])
            resp = await _create_entry(client, tracker_id, amount=100000, list_amount=90000)
            assert resp.status_code == 201
            entry_ids.append(UUID(resp.json()["id"]))

            # Unlocked: entry visible.
            entries = (await client.get("/api/tracker/entries")).json()["items"]
            assert any(UUID(e["id"]) in entry_ids for e in entries)
            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["f1_total"] == 100000

            # Lock the private gate: entry + F1 disappear.
            auth_state["value"] = _auth(unlocked=False)
            entries = (await client.get("/api/tracker/entries")).json()["items"]
            assert all(UUID(e["id"]) not in entry_ids for e in entries)
            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["f1_total"] == 0

            # Reopen: entry + F1 return.
            auth_state["value"] = _auth()
            entries = (await client.get("/api/tracker/entries")).json()["items"]
            assert any(UUID(e["id"]) in entry_ids for e in entries)
            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["f1_total"] == 100000
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "entry", entry_ids)
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_archived_tracker_missing_from_grid_but_in_finance(pg_dsn: str):
    """Tracker archive: biến mất khỏi list, nhưng entry của nó vẫn vào F1 (§4.3 luật 2)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        entry_ids: list[UUID] = []
        tracker_id = None
        try:
            tracker = await _create_tracker(
                client, name="Tiền cũ", kind="finance", input_mode="money"
            )
            tracker_id = UUID(tracker["id"])
            resp = await _create_entry(client, tracker_id, amount=50000)
            assert resp.status_code == 201
            entry_ids.append(UUID(resp.json()["id"]))
            assert (await client.delete(f"/api/tracker/trackers/{tracker_id}")).status_code == 204

            listed = (await client.get("/api/tracker/trackers")).json()["items"]
            assert all(UUID(t["id"]) != tracker_id for t in listed)
            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["f1_total"] == 50000
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "entry", entry_ids)
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_k8_input_mode_validation(pg_dsn: str):
    """3 input_mode × sai field ⇒ 422 (K8), không phải 500."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids: list[UUID] = []
        try:
            event_t = await _create_tracker(client, name="Event", input_mode="event")
            event_id = UUID(event_t["id"])
            tracker_ids.append(event_id)
            money_t = await _create_tracker(
                client, name="Money", kind="finance", input_mode="money"
            )
            money_id = UUID(money_t["id"])
            tracker_ids.append(money_id)
            qty_t = await _create_tracker(client, name="Qty", input_mode="quantity", unit="phút")
            qty_id = UUID(qty_t["id"])
            tracker_ids.append(qty_id)

            # event: amount/quantity forbidden
            assert (await _create_entry(client, event_id, amount=5)).status_code == 422
            assert (await _create_entry(client, event_id, quantity=5)).status_code == 422
            # money: amount required; quantity forbidden
            assert (await _create_entry(client, money_id, quantity=5)).status_code == 422
            assert (await _create_entry(client, money_id)).status_code == 422
            # quantity: quantity required; amount forbidden
            assert (await _create_entry(client, qty_id)).status_code == 422
            assert (await _create_entry(client, qty_id, amount=5)).status_code == 422
            # valid paths
            assert (await _create_entry(client, event_id)).status_code == 201
            assert (await _create_entry(client, money_id, amount=1000)).status_code == 201
            assert (await _create_entry(client, qty_id, quantity=2.5)).status_code == 201
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "entry", [])
            await _cleanup(pg_dsn, "tracker", tracker_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_unit_and_kind_group_traps(pg_dsn: str):
    """unit/input_mode + kind×group: bốn đường vấp ⇒ 422 (bẫy 3, 4)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        created: dict[str, list[UUID]] = {"group": [], "tracker": []}
        try:
            health_group = (
                await client.post(
                    "/api/tracker/groups", json={"name": "Sức khoẻ", "kind": "health"}
                )
            ).json()
            created["group"].append(UUID(health_group["id"]))
            finance_group = (
                await client.post(
                    "/api/tracker/groups", json={"name": "Tài chính", "kind": "finance"}
                )
            ).json()
            created["group"].append(UUID(finance_group["id"]))

            tracker = await _create_tracker(client, name="Thể thao")
            tracker_id = UUID(tracker["id"])
            created["tracker"].append(tracker_id)

            # Changing to quantity without a unit.
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{tracker_id}",
                    json={"input_mode": "quantity"},
                )
            ).status_code == 422

            # Changing away from quantity auto-clears unit (valid).
            money_t = await _create_tracker(
                client, name="Bia", kind="finance", input_mode="quantity", unit="lon"
            )
            money_id = UUID(money_t["id"])
            created["tracker"].append(money_id)
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{money_id}", json={"input_mode": "event"}
                )
            ).status_code == 200
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{money_id}", json={"input_mode": "quantity"}
                )
            ).status_code == 422

            # Assign tracker to a group of a different kind.
            health_tracker = await _create_tracker(client, name="Hút thuốc")
            health_tracker_id = UUID(health_tracker["id"])
            created["tracker"].append(health_tracker_id)
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{health_tracker_id}",
                    json={"group_id": str(finance_group["id"])},
                )
            ).status_code == 422
            # Assign to the correct-kind group.
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{health_tracker_id}",
                    json={"group_id": str(health_group["id"])},
                )
            ).status_code == 200

            # Change kind while holding a same-kind group (health group -> finance).
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{health_tracker_id}",
                    json={"kind": "finance"},
                )
            ).status_code == 422
            # Same PATCH changes kind + drops group.
            assert (
                await client.patch(
                    f"/api/tracker/trackers/{health_tracker_id}",
                    json={"kind": "finance", "group_id": None},
                )
            ).status_code == 200
        finally:
            await client.aclose()
            for group_id in created["group"]:
                await _cleanup(pg_dsn, "tracker_group", [group_id])
            await _cleanup(pg_dsn, "tracker", created["tracker"])
            await engine.dispose()

    asyncio.run(scenario())


def test_entry_idempotent_create(pg_dsn: str):
    """Gửi hai lần cùng id ⇒ một dòng, lần hai trả 200."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Bia", kind="finance", input_mode="money")
            tracker_id = UUID(tracker["id"])
            entry_id = _uuid7()
            payload = {
                "id": str(entry_id),
                "tracker_id": str(tracker_id),
                "amount": 35000,
            }
            first = await client.post("/api/tracker/entries", json=payload)
            repeated = await client.post("/api/tracker/entries", json=payload)
            assert first.status_code == 201
            assert repeated.status_code == 200
            assert first.json() == repeated.json()
            conn = await asyncpg.connect(pg_dsn)
            try:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM microsched.entry WHERE id = $1", entry_id
                    )
                    == 1
                )
            finally:
                await conn.close()
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_dashboard_period_boundaries_and_corrupt_amount(pg_dsn: str):
    """?month= quá khứ → F1 cả tháng; ?month= tương lai → 0; dòng amount hỏng → dashboard 200."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        entry_ids: list[UUID] = []
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Tiền", kind="finance", input_mode="money")
            tracker_id = UUID(tracker["id"])
            # Entry 3 months ago (fully in the past).
            past = datetime.now(UTC) - timedelta(days=70)
            resp = await _create_entry(
                client, tracker_id, amount=40000, occurred_at=past.isoformat()
            )
            assert resp.status_code == 201, resp.text
            entry_ids.append(UUID(resp.json()["id"]))

            past_month = f"{past.year:04d}-{past.month:02d}"
            dash = (await client.get(f"/api/tracker/dashboard?month={past_month}")).json()
            assert dash["f1_total"] == 40000
            # period_end is the end of the past month, not "now".
            end = datetime.fromisoformat(dash["period_end"])
            assert end.day == 1 or end.month != past.month

            future = (datetime.now(UTC) + timedelta(days=45)).strftime("%Y-%m")
            dash = (await client.get(f"/api/tracker/dashboard?month={future}")).json()
            assert dash["f1_total"] == 0

            # Corrupt one amount ciphertext: dashboard still 200, count=1.
            conn = await asyncpg.connect(pg_dsn)
            try:
                await conn.execute(
                    "UPDATE microsched.entry SET amount = $1 WHERE id = $2",
                    "enc:v1:garbage",
                    entry_ids[0],
                )
            finally:
                await conn.close()
            dash = (await client.get(f"/api/tracker/dashboard?month={past_month}")).json()
            assert dash["corrupted_entry_count"] == 1
            # Corrupt row still 500 on the single-entry read path.
            assert (await client.get(f"/api/tracker/entries/{entry_ids[0]}")).status_code == 500
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "entry", entry_ids)
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_tracker_duplicate_name_conflict_within_gate(pg_dsn: str):
    """Trùng tên tracker (trong cổng) ⇒ 409; trùng tên xuyên cổng riêng tư ⇒ vẫn tạo được."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_ids: list[UUID] = []
        try:
            t1 = await _create_tracker(client, name="Thuốc X")
            tracker_ids.append(UUID(t1["id"]))
            duplicate = await client.post(
                "/api/tracker/trackers", json={"name": "Thuốc x", "kind": "health"}
            )
            assert duplicate.status_code == 409

            # A private tracker with the same name is NOT visible while locked, so a
            # public duplicate is allowed (no leak) per spec §2.4.
            private_t = await client.post(
                "/api/tracker/trackers",
                json={"name": "Thuốc Y", "kind": "health", "is_private": True},
            )
            assert private_t.status_code == 201
            tracker_ids.append(UUID(private_t.json()["id"]))
            auth_state["value"] = _auth(unlocked=False)
            allowed = await client.post(
                "/api/tracker/trackers", json={"name": "Thuốc Y", "kind": "health"}
            )
            assert allowed.status_code == 201
            tracker_ids.append(UUID(allowed.json()["id"]))
            auth_state["value"] = _auth()
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", tracker_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_group_crud_idempotency_and_name_conflict(pg_dsn: str):
    """Group unique-name 409; explicit-ID idempotent 200; delete drops members to ungrouped."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        group_ids: list[UUID] = []
        tracker_ids: list[UUID] = []
        try:
            group = (
                await client.post(
                    "/api/tracker/groups", json={"name": "Ăn uống", "kind": "finance"}
                )
            ).json()
            group_id = UUID(group["id"])
            group_ids.append(group_id)

            duplicate = await client.post(
                "/api/tracker/groups", json={"name": "ĂN UỐNG", "kind": "finance"}
            )
            assert duplicate.status_code == 409

            gid = _uuid7()
            group_ids.append(gid)
            payload = {"id": str(gid), "name": "Học tập", "kind": "health"}
            first = await client.post("/api/tracker/groups", json=payload)
            repeated = await client.post("/api/tracker/groups", json=payload)
            assert first.status_code == 201
            assert repeated.status_code == 200
            assert first.json() == repeated.json()

            tracker = await _create_tracker(
                client, name="Sách", kind="finance", group_id=str(group_id)
            )
            tracker_id = UUID(tracker["id"])
            tracker_ids.append(tracker_id)
            assert (await client.delete(f"/api/tracker/groups/{group_id}")).status_code == 204
            listed = (await client.get("/api/tracker/trackers")).json()["items"]
            updated = next(t for t in listed if UUID(t["id"]) == tracker_id)
            assert updated["group_id"] is None
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", tracker_ids)
            await _cleanup(pg_dsn, "tracker_group", group_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_group_count_hides_private_trackers_while_locked(pg_dsn: str):
    """tracker_count không lộ tracker riêng tư khi cổng khoá (C2)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        group_ids: list[UUID] = []
        tracker_ids: list[UUID] = []
        try:
            group = (
                await client.post(
                    "/api/tracker/groups", json={"name": "Nhóm hỗn hợp", "kind": "health"}
                )
            ).json()
            group_id = UUID(group["id"])
            group_ids.append(group_id)

            public_t = await _create_tracker(
                client, name="Công khai", kind="health", group_id=str(group_id)
            )
            tracker_ids.append(UUID(public_t["id"]))
            private_t = await _create_tracker(
                client,
                name="Riêng tư",
                kind="health",
                group_id=str(group_id),
                is_private=True,
            )
            tracker_ids.append(UUID(private_t["id"]))

            groups = (await client.get("/api/tracker/groups")).json()["items"]
            row = next(g for g in groups if UUID(g["id"]) == group_id)
            assert row["tracker_count"] == 2

            auth_state["value"] = _auth(unlocked=False)
            groups = (await client.get("/api/tracker/groups")).json()["items"]
            row = next(g for g in groups if UUID(g["id"]) == group_id)
            assert row["tracker_count"] == 1
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", tracker_ids)
            await _cleanup(pg_dsn, "tracker_group", group_ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_archive_excluded_from_behavior_counts_but_kept_in_finance(pg_dsn: str):
    """Archive: biến mất khỏi A3 (hành vi), entry vẫn vào F1 (C3)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        entry_ids: list[UUID] = []
        tracker_id = None
        try:
            tracker = await _create_tracker(
                client, name="Tiền hôm nay", kind="finance", input_mode="money"
            )
            tracker_id = UUID(tracker["id"])
            resp = await _create_entry(client, tracker_id, amount=25000)
            assert resp.status_code == 201
            entry_ids.append(UUID(resp.json()["id"]))

            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["a3_counts"]["month"] == 1
            assert dash["f1_total"] == 25000

            assert (await client.delete(f"/api/tracker/trackers/{tracker_id}")).status_code == 204
            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["a3_counts"]["month"] == 0
            assert dash["f1_total"] == 25000
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "entry", entry_ids)
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_patch_null_required_fields_rejected(pg_dsn: str):
    """PATCH null cho field bắt buộc ⇒ 422, không nuốt im (M5)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Tracker", kind="health")
            tracker_id = UUID(tracker["id"])
            for field in ("name", "kind", "direction", "input_mode", "is_private"):
                resp = await client.patch(f"/api/tracker/trackers/{tracker_id}", json={field: None})
                assert resp.status_code == 422, (field, resp.text)

            # Optional fields still accept an explicit null (that is how UI clears).
            assert (
                await client.patch(f"/api/tracker/trackers/{tracker_id}", json={"group_id": None})
            ).status_code == 200

            resp = await _create_entry(client, tracker_id)
            assert resp.status_code == 201
            entry_id = resp.json()["id"]
            resp = await client.patch(
                f"/api/tracker/entries/{entry_id}", json={"occurred_at": None}
            )
            assert resp.status_code == 422, resp.text
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_quantity_nonpositive_rejected(pg_dsn: str):
    """quantity <= 0 ⇒ 422 trước khi chạm DB CHECK (M12)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Nước", input_mode="quantity", unit="lon")
            tracker_id = UUID(tracker["id"])
            assert (await _create_entry(client, tracker_id, quantity=0)).status_code == 422
            assert (await _create_entry(client, tracker_id, quantity=-1)).status_code == 422
            assert (await _create_entry(client, tracker_id, quantity=2.5)).status_code == 201
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())


def test_f4_excludes_entries_after_now(pg_dsn: str):
    """F4 chỉ lấy entry trước period_end, không lấy entry tương lai trong tháng (C5)."""

    async def scenario():
        auth_state = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth_state)
        entry_ids: list[UUID] = []
        tracker_id = None
        try:
            tracker = await _create_tracker(client, name="Tiền", kind="finance", input_mode="money")
            tracker_id = UUID(tracker["id"])
            now = datetime.now(UTC)
            past = await _create_entry(
                client,
                tracker_id,
                amount=1000,
                occurred_at=(now - timedelta(hours=1)).isoformat(),
            )
            assert past.status_code == 201
            entry_ids.append(UUID(past.json()["id"]))
            future = await _create_entry(
                client,
                tracker_id,
                amount=5000,
                occurred_at=(now + timedelta(minutes=30)).isoformat(),
            )
            assert future.status_code == 201
            entry_ids.append(UUID(future.json()["id"]))

            dash = (await client.get("/api/tracker/dashboard")).json()
            assert dash["f1_total"] == 1000
            assert [line["amount"] for line in dash["f4_top"]] == [1000]
        finally:
            await client.aclose()
            await _cleanup(pg_dsn, "entry", entry_ids)
            await _cleanup(pg_dsn, "tracker", [tracker_id])
            await engine.dispose()

    asyncio.run(scenario())
