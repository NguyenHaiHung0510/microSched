"""Tests for the read-only reminder delivery diagnostic."""

import asyncio
import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import asyncpg
import pytest

import scripts.reminder_delivery_receipt as receipt_module


def _uuid7() -> UUID:
    timestamp = int(time.time() * 1000)
    random_bits = int.from_bytes(os.urandom(10), "big") & ((1 << 74) - 1)
    value = (timestamp << 80) | (0x7 << 76)
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)


@pytest.mark.parametrize(
    ("window_minutes", "since"),
    [
        (None, None),
        (15, "2026-08-16T00:00:00Z"),
        (0, None),
        (1441, None),
        (None, "2026-08-16T07:00:00+07:00"),
        (None, "2026-08-16T00:00:00"),
        (None, "2026-08-17T00:00:01Z"),
        (None, "2026-08-15T23:59:59Z"),
    ],
)
def test_window_validation_rejects_unsafe_inputs(window_minutes, since):
    observed_at = datetime(2026, 8, 17, tzinfo=UTC)
    with pytest.raises(ValueError):
        receipt_module.resolve_window(
            window_minutes=window_minutes,
            since=since,
            observed_at=observed_at,
        )


def test_window_validation_accepts_bounds_and_preserves_since():
    observed_at = datetime(2026, 8, 17, tzinfo=UTC)
    start, minutes = receipt_module.resolve_window(
        window_minutes=1,
        since=None,
        observed_at=observed_at,
    )
    assert start == observed_at - timedelta(minutes=1)
    assert minutes == 1

    start, minutes = receipt_module.resolve_window(
        window_minutes=None,
        since="2026-08-16T00:00:00Z",
        observed_at=observed_at,
    )
    assert start == observed_at - timedelta(hours=24)
    assert minutes is None


@pytest.mark.anyio
async def test_collect_receipt_is_select_only_stable_and_closes_connection(monkeypatch):
    observed_at = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    window_started_at = observed_at - timedelta(minutes=15)
    sentinel_uuid = "01912345-6789-7000-8000-00000000beef"
    sentinel_endpoint = "https://endpoint.invalid/private-sentinel"

    class FakeConnection:
        def __init__(self):
            self.queries: list[str] = []
            self.closed = False

        async def fetchval(self, query):
            self.queries.append(query)
            if "to_regclass" in query:
                return None
            return 2

        async def fetch(self, query, *args):
            self.queries.append(query)
            assert args == (window_started_at, observed_at)
            return [
                {
                    "kind": "tracker",
                    "occurrence_on": date(2026, 8, 16),
                    "status": "sent",
                    "attempt_count": 1,
                    "dispatch_count": 1,
                    "earliest_created_at": observed_at - timedelta(minutes=10),
                    "latest_created_at": observed_at - timedelta(minutes=10),
                    "earliest_last_attempt_at": observed_at - timedelta(minutes=9),
                    "latest_last_attempt_at": observed_at - timedelta(minutes=9),
                    "confirmed_count": 1,
                }
            ]

        async def close(self):
            self.closed = True

    connection = FakeConnection()

    async def fake_connect(dsn):
        assert dsn.startswith("postgresql://")
        return connection

    monkeypatch.setattr(receipt_module.asyncpg, "connect", fake_connect)
    result = await receipt_module.collect_receipt(
        "postgresql://user:password@localhost/test",
        observed_at=observed_at,
        window_started_at=window_started_at,
        window_minutes=15,
        commit="abc123",
    )

    assert connection.closed is True
    assert len(connection.queries) == 3
    assert all(query.lstrip().upper().startswith("SELECT") for query in connection.queries)
    assert list(result) == [
        "commit",
        "observed_at",
        "window_started_at",
        "window_minutes",
        "push_subscription_count",
        "batch_groups",
        "legacy_unlinked_dispatch_groups",
    ]
    assert result == {
        "commit": "abc123",
        "observed_at": "2026-08-16T12:00:00Z",
        "window_started_at": "2026-08-16T11:45:00Z",
        "window_minutes": 15,
        "push_subscription_count": 2,
        "batch_groups": [],
        "legacy_unlinked_dispatch_groups": [
            {
                "kind": "tracker",
                "occurrence_on": "2026-08-16",
                "status": "sent",
                "attempt_count": 1,
                "dispatch_count": 1,
                "earliest_created_at": "2026-08-16T11:50:00Z",
                "latest_created_at": "2026-08-16T11:50:00Z",
                "earliest_last_attempt_at": "2026-08-16T11:51:00Z",
                "latest_last_attempt_at": "2026-08-16T11:51:00Z",
                "confirmed_count": 1,
            }
        ],
    }
    rendered = json.dumps(result)
    for forbidden in (
        sentinel_uuid,
        sentinel_endpoint,
        "p256dh-private-sentinel",
        "auth-private-sentinel",
        "cookie-private-sentinel",
        "token-private-sentinel",
        "credential-private-sentinel",
        "provider-private-sentinel",
        "ciphertext-private-sentinel",
    ):
        assert forbidden not in rendered


@pytest.mark.anyio
async def test_collect_receipt_closes_connection_when_query_fails(monkeypatch):
    class FailingConnection:
        closed = False

        async def fetchval(self, query):
            raise RuntimeError("query-private-sentinel")

        async def close(self):
            self.closed = True

    connection = FailingConnection()

    async def fake_connect(dsn):
        return connection

    monkeypatch.setattr(receipt_module.asyncpg, "connect", fake_connect)
    observed_at = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    with pytest.raises(RuntimeError, match="query-private-sentinel"):
        await receipt_module.collect_receipt(
            "postgresql://user:password@localhost/test",
            observed_at=observed_at,
            window_started_at=observed_at - timedelta(minutes=15),
            window_minutes=15,
            commit="abc123",
        )
    assert connection.closed is True


def test_cli_config_error_prints_only_safe_error_type(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    exit_code = receipt_module.main(["--window-minutes", "15"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "error_type=RuntimeError\n"


def test_cli_argument_error_prints_only_safe_error_type(capsys):
    sentinel = "diagnostic-input-sentinel"
    exit_code = receipt_module.main(["--window-minutes", sentinel])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "error_type=ValueError\n"
    assert sentinel not in captured.err


def test_cli_success_prints_exactly_one_json_object(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/test")
    monkeypatch.setenv("GIT_SHA", "cli-test-sha")

    async def fake_collect(database_url, **kwargs):
        return {
            "commit": kwargs["commit"],
            "observed_at": receipt_module._utc_rfc3339(kwargs["observed_at"]),
            "window_started_at": receipt_module._utc_rfc3339(kwargs["window_started_at"]),
            "window_minutes": kwargs["window_minutes"],
            "push_subscription_count": 0,
            "batch_groups": [],
            "legacy_unlinked_dispatch_groups": [],
        }

    monkeypatch.setattr(receipt_module, "collect_receipt", fake_collect)
    exit_code = receipt_module.main(["--window-minutes", "15"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    result = json.loads(captured.out)
    assert result["commit"] == "cli-test-sha"
    assert result["window_minutes"] == 15
    assert result["push_subscription_count"] == 0
    assert result["batch_groups"] == []
    assert result["legacy_unlinked_dispatch_groups"] == []


@pytest.mark.pg
def test_pg_aggregate_groups_are_exact_deterministic_and_cleaned_up(pg_dsn: str):
    """D-01: real Postgres aggregate covers both timestamp filter paths."""
    push_id = _uuid7()
    tracker_id = _uuid7()
    entry_id = _uuid7()
    dispatch_ids = [_uuid7(), _uuid7()]
    observed_at = datetime.now(UTC).replace(microsecond=0)
    window_started_at = observed_at - timedelta(minutes=15)

    async def scenario():
        conn = await asyncpg.connect(pg_dsn)
        cleanup_error: Exception | None = None
        try:
            await conn.execute(
                "INSERT INTO microsched.push_subscription "
                "(id, endpoint, p256dh, auth, last_seen_at) "
                "VALUES ($1, $2, 'dGVzdA', 'dGVzdA', NOW())",
                push_id,
                f"https://push.example.test/receipt/{push_id}",
            )
            await conn.execute(
                "INSERT INTO microsched.tracker "
                "(id, name, kind, direction, input_mode) "
                "VALUES ($1, 'enc:v1:receipt-test', 'health', 'out', 'event')",
                tracker_id,
            )
            await conn.execute(
                "INSERT INTO microsched.entry (id, tracker_id, occurred_at) VALUES ($1, $2, $3)",
                entry_id,
                tracker_id,
                observed_at - timedelta(minutes=8),
            )
            await conn.execute(
                "INSERT INTO microsched.reminder_dispatch "
                "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                "last_attempt_at, confirmed_entry_id, confirmed_at, created_at) "
                "VALUES ($1, 'tracker', $2, $3, 'sent', 1, $4, $5, $4, $6)",
                dispatch_ids[0],
                tracker_id,
                date(2026, 8, 16),
                observed_at - timedelta(minutes=9),
                entry_id,
                observed_at - timedelta(minutes=10),
            )
            await conn.execute(
                "INSERT INTO microsched.reminder_dispatch "
                "(id, subject_type, subject_id, dispatched_on, status, attempt_count, "
                "last_attempt_at, created_at) "
                "VALUES ($1, 'subscription', $2, $3, 'pending', 2, $4, $5)",
                dispatch_ids[1],
                _uuid7(),
                date(2026, 8, 17),
                observed_at - timedelta(minutes=5),
                observed_at - timedelta(minutes=30),
            )

            result = await receipt_module.collect_receipt(
                pg_dsn,
                observed_at=observed_at,
                window_started_at=window_started_at,
                window_minutes=None,
                commit="pg-test-sha",
            )

            assert result["push_subscription_count"] == 1
            target_groups = [
                group
                for group in result["legacy_unlinked_dispatch_groups"]
                if group["occurrence_on"] in {"2026-08-16", "2026-08-17"}
            ]
            assert target_groups == [
                {
                    "kind": "subscription",
                    "occurrence_on": "2026-08-17",
                    "status": "pending",
                    "attempt_count": 2,
                    "dispatch_count": 1,
                    "earliest_created_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=30)
                    ),
                    "latest_created_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=30)
                    ),
                    "earliest_last_attempt_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=5)
                    ),
                    "latest_last_attempt_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=5)
                    ),
                    "confirmed_count": 0,
                },
                {
                    "kind": "tracker",
                    "occurrence_on": "2026-08-16",
                    "status": "sent",
                    "attempt_count": 1,
                    "dispatch_count": 1,
                    "earliest_created_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=10)
                    ),
                    "latest_created_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=10)
                    ),
                    "earliest_last_attempt_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=9)
                    ),
                    "latest_last_attempt_at": receipt_module._utc_rfc3339(
                        observed_at - timedelta(minutes=9)
                    ),
                    "confirmed_count": 1,
                },
            ]
        finally:
            try:
                await conn.execute(
                    "DELETE FROM microsched.reminder_dispatch WHERE id = ANY($1::uuid[])",
                    dispatch_ids,
                )
                await conn.execute("DELETE FROM microsched.entry WHERE id = $1", entry_id)
                await conn.execute("DELETE FROM microsched.tracker WHERE id = $1", tracker_id)
                await conn.execute(
                    "DELETE FROM microsched.push_subscription WHERE id = $1", push_id
                )
            except Exception as exc:
                cleanup_error = exc

            remaining = await conn.fetchval(
                "SELECT "
                "(SELECT count(*) FROM microsched.reminder_dispatch "
                " WHERE id = ANY($1::uuid[])) + "
                "(SELECT count(*) FROM microsched.entry WHERE id = $2) + "
                "(SELECT count(*) FROM microsched.tracker WHERE id = $3) + "
                "(SELECT count(*) FROM microsched.push_subscription WHERE id = $4)",
                dispatch_ids,
                entry_id,
                tracker_id,
                push_id,
            )
            await conn.close()
            assert cleanup_error is None, f"cleanup failed: {type(cleanup_error).__name__}"
            assert remaining == 0

    asyncio.run(scenario())
