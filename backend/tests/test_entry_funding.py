"""Task095: actual PG/API relation, opaque privacy and exact finance totals."""

import asyncio
from uuid import UUID

import asyncpg
import pytest
from test_tracker_api import (
    _auth,
    _create_entry,
    _create_tracker,
    _make_client,
    local_settings,  # noqa: F401
)

pytestmark = [pytest.mark.pg, pytest.mark.usefixtures("local_settings")]


async def cleanup(dsn, ids):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "UPDATE microsched.entry SET funding_entry_id=NULL WHERE tracker_id=ANY($1::uuid[])",
            ids,
        )
        await conn.execute("DELETE FROM microsched.entry WHERE tracker_id=ANY($1::uuid[])", ids)
        await conn.execute("DELETE FROM microsched.tracker WHERE id=ANY($1::uuid[])", ids)
    finally:
        await conn.close()


def test_funding_relation_retry_unavailable_and_privacy(pg_dsn):
    async def scenario():
        auth = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth)
        ids = []
        try:
            income = await _create_tracker(
                client, name="095 income", kind="finance", input_mode="money", direction="in"
            )
            expense = await _create_tracker(
                client, name="095 expense", kind="finance", input_mode="money", direction="out"
            )
            secret = await _create_tracker(
                client,
                name="095 source canary",
                kind="finance",
                input_mode="money",
                direction="in",
                is_private=True,
            )
            ids.extend(UUID(t["id"]) for t in (income, expense, secret))

            async def create(tracker, **body):
                r = await _create_entry(client, tracker["id"], **body)
                assert r.status_code == 201, r.text
                return r.json()

            source = await create(income, amount=1500000)
            second = await create(income, amount=1000000)
            hidden = await create(secret, amount=987654)
            spend = await create(expense, amount=500000, funding_entry_id=source["id"])
            read_url = f"/api/tracker/entries/{spend['id']}?include_funding=true"
            assert (await client.get(read_url)).json()["funding"]["source"]["id"] == source["id"]
            default = (await client.get(f"/api/tracker/entries/{spend['id']}")).json()
            assert default["funding"] is None and "funding_entry_id" not in default
            options = (await client.get("/api/tracker/funding-candidates?limit=1")).json()
            assert len(options["items"]) == 1 and options["next_cursor"]
            older = (
                await client.get(
                    "/api/tracker/funding-candidates", params={"cursor": options["next_cursor"]}
                )
            ).json()
            assert len(older["items"]) >= 2
            assert (
                await client.get("/api/tracker/funding-candidates?cursor=bad")
            ).status_code == 422
            assert (
                await client.patch(
                    f"/api/tracker/entries/{spend['id']}", json={"funding_entry_id": spend["id"]}
                )
            ).status_code == 422
            assert (
                await client.patch(
                    f"/api/tracker/entries/{source['id']}", json={"funding_entry_id": second["id"]}
                )
            ).status_code == 422
            conflict = await _create_entry(
                client, expense["id"], id=spend["id"], amount=500000, funding_entry_id=second["id"]
            )
            assert conflict.status_code == 409
            # Soft deletion leaves the expense/reference intact; unrelated PATCH preserves it.
            assert (await client.delete(f"/api/tracker/entries/{source['id']}")).status_code == 204
            assert (await client.get(read_url)).json()["funding"] == {"status": "unavailable"}
            assert (
                await client.patch(
                    f"/api/tracker/entries/{spend['id']}", json={"note_md": "public edit"}
                )
            ).status_code == 200
            assert (await client.get(read_url)).json()["funding"] == {"status": "unavailable"}
            retry = await _create_entry(
                client, expense["id"], id=spend["id"], amount=500000, funding_entry_id=source["id"]
            )
            assert retry.status_code == 200 and retry.json()["id"] == spend["id"]
            assert (
                await client.patch(
                    f"/api/tracker/entries/{spend['id']}", json={"funding_entry_id": hidden["id"]}
                )
            ).status_code == 200
            auth["value"] = _auth(unlocked=False)
            locked = (await client.get(read_url)).json()
            assert locked["funding"] == {"status": "unavailable"}
            assert all(
                value not in str(locked)
                for value in (hidden["id"], secret["id"], "source canary", "987654")
            )
            options = (await client.get("/api/tracker/funding-candidates")).json()
            assert hidden["id"] not in str(options)
            assert (
                await client.patch(
                    f"/api/tracker/entries/{spend['id']}", json={"note_md": "locked public edit"}
                )
            ).status_code == 200
            assert (
                await _create_entry(client, expense["id"], amount=1, funding_entry_id=hidden["id"])
            ).status_code == 422
            assert (
                await client.patch(
                    f"/api/tracker/entries/{spend['id']}", json={"funding_entry_id": None}
                )
            ).status_code == 200
            assert (await client.get(read_url)).json()["funding"] == {"status": "none"}
            assert (await client.get(f"/api/tracker/entries/{second['id']}")).status_code == 200
        finally:
            await client.aclose()
            await engine.dispose()
            await cleanup(pg_dsn, ids)

    asyncio.run(scenario())


def test_funding_report_exactly_once_and_opaque_unavailable(pg_dsn):
    async def scenario():
        auth = {"value": _auth()}
        client, engine = _make_client(pg_dsn, auth)
        ids = []
        try:
            income = await _create_tracker(
                client, name="095 report income", kind="finance", input_mode="money", direction="in"
            )
            expense = await _create_tracker(
                client,
                name="095 report expense",
                kind="finance",
                input_mode="money",
                direction="out",
            )
            other = await _create_tracker(
                client,
                name="095 report expense two",
                kind="finance",
                input_mode="money",
                direction="out",
            )
            ids.extend(UUID(t["id"]) for t in (income, expense, other))

            async def create(tracker, **body):
                r = await _create_entry(
                    client, tracker["id"], occurred_at="2024-02-15T02:00:00Z", **body
                )
                assert r.status_code == 201, r.text
                return r.json()

            r = await _create_entry(
                client, income["id"], amount=1500000, occurred_at="2024-01-22T02:00:00Z"
            )
            assert r.status_code == 201
            first = r.json()
            second = await create(income, amount=1000000)
            a = await create(expense, amount=500000, funding_entry_id=first["id"])
            await create(other, amount=120000, funding_entry_id=first["id"])
            await create(expense, amount=250000, funding_entry_id=second["id"])
            await create(expense, amount=80000)
            url = "/api/tracker/funding-report?month=2024-02"
            report = (await client.get(url)).json()
            assert report["expense_total"] == 950000 and report["income_total"] == 1000000
            assert report["net"] == 50000
            buckets = {b["key"]: b for b in report["buckets"]}
            assert sorted(b["total"] for b in buckets.values()) == [80000, 250000, 620000]
            assert len(buckets[first["id"]]["trackers"]) == 2
            assert sum(e["amount"] for e in buckets[first["id"]]["expenses"]) == 620000
            dashboard = (await client.get("/api/tracker/dashboard?month=2024-02")).json()
            assert (
                dashboard["f1_total"] == report["expense_total"]
                and dashboard["f5_net"] == report["net"]
            )
            assert (await client.delete(f"/api/tracker/trackers/{other['id']}")).status_code == 204
            assert (await client.get(url)).json()["expense_total"] == 950000
            assert (await client.delete(f"/api/tracker/entries/{first['id']}")).status_code == 204
            report = (await client.get(url)).json()
            unavailable = next(b for b in report["buckets"] if b["key"] == "unavailable")
            assert unavailable["source"] is None and unavailable["total"] == 620000
            assert first["id"] not in str(report)
            # Archiving IS soft-delete in this domain: no new source selection/link,
            # while archived expense parents keep their existing finance history.
            assert (await client.delete(f"/api/tracker/trackers/{income['id']}")).status_code == 204
            assert second["id"] not in str(
                (await client.get("/api/tracker/funding-candidates")).json()
            )
            assert (
                await _create_entry(client, expense["id"], amount=1, funding_entry_id=second["id"])
            ).status_code == 422
            report = (await client.get(url)).json()
            assert report["expense_total"] == 950000
            assert (
                next(b for b in report["buckets"] if b["key"] == "unavailable")["total"] == 870000
            )
            assert (
                await client.patch(
                    f"/api/tracker/entries/{a['id']}", json={"note_md": "keep historical source"}
                )
            ).status_code == 200

            assert (await client.delete(f"/api/tracker/entries/{a['id']}")).status_code == 204
            assert (await client.get(url)).json()["expense_total"] == 450000
            assert (
                await client.get("/api/tracker/funding-report?month=2024-02&months=2")
            ).status_code == 422
        finally:
            await client.aclose()
            await engine.dispose()
            await cleanup(pg_dsn, ids)

    asyncio.run(scenario())
