"""P2 numeric/identity and encrypted projection contracts; synthetic, no egress."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid7

import pytest

from app.agent import crypto
from app.agent.observations import accounting_dispatches, accounting_summary, conversation_metrics
from app.agent.tool_activity import tool_activity


def call(identity="call", generation="gen", usage=None, **route):
    return SimpleNamespace(
        id=identity,
        run_id="run",
        state="succeeded",
        route={"kind": "openrouter", **route},
        result={"response_id": generation},
        usage=usage or {},
    )


def summary(calls):
    return accounting_summary(accounting_dispatches(calls)[0])


def test_native_subsets_weighted_cache_and_decimal_cost_with_retry_and_reuse():
    first = call(
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "cost": "0.10",
            "reasoning_tokens": 30,
            "cached_tokens": 90,
        }
    )
    helper = call(
        "helper",
        "helper-gen",
        {
            "prompt_tokens": 900,
            "completion_tokens": 60,
            "cost": "0.20",
            "reasoning_tokens": 10,
            "cached_tokens": 90,
        },
        purpose="compaction",
    )
    retry = call(
        "retry",
        "retry-final",
        dispatch_attempts=[
            {"usage": {}, "outcome": "unknown"},
            {"response_id": "retry-final", "usage": {"cost": 0}},
        ],
    )
    dispatches, reused = accounting_dispatches(
        [
            first,
            helper,
            retry,
            first,
            call("reuse", "gen", first.usage, paid_dispatch=False),
            call("preflight", None, dispatch_not_started=True),
        ]
    )
    result = accounting_summary(dispatches)
    assert len(dispatches) == 4 and reused == 1
    assert result["usd"] == {"known": "0.30", "observed": 3, "missing": 1, "complete": False}
    assert result["input"]["known"] == 1000
    assert result["output"]["known"] == 100
    assert result["reasoning"]["known"] == 40  # Included in output, never added to it.
    assert result["cache"]["ratio"] == 0.18  # Token weighted; not mean(90%,10%).
    assert result["cache"]["observed"] == 2 and result["cache"]["missing"] == 2
    assert result["purpose_counts"] == {"main": 3, "helper": 1, "unclassified": 0}
    assert result["effective_completion_per_second"] is None


def test_late_matching_generation_fills_existing_dispatch_without_addition():
    receipt = call(
        usage={"prompt_tokens": 120},
        dispatch_attempts=[
            {"response_id": "gen", "usage": {"prompt_tokens": 120}},
        ],
    )
    receipt.result["generation"] = {
        "id": "gen",
        "native_tokens_prompt": 120,
        "native_tokens_completion": 25,
        "total_cost": "0.0123",
        "tokens_prompt": 99999,
    }
    result = summary([receipt, receipt])
    assert result["eligible_dispatches"] == 1
    assert result["input"]["known"] == 120
    assert result["output"]["known"] == 25
    assert result["usd"]["known"] == "0.0123"
    receipt.result["generation"]["id"] = "different-generation"
    assert summary([receipt])["usd"]["known"] is None


def test_generation_identity_can_arrive_late_and_distinct_redispatches_count():
    early = call("same-durable-call", None, {"cost": "0.1"})
    late = call("same-durable-call", "confirmed", {"cost": "0.1"})
    separate = call("other-call", "another-generation", {"cost": "0.1"})
    result = summary([early, late, separate])
    assert result["eligible_dispatches"] == 2 and result["usd"]["known"] == "0.2"


@pytest.mark.parametrize("bad", [-1, True, 1.5, float("inf"), float("nan"), 2**53])
def test_invalid_native_values_and_subsets_stay_missing(bad):
    receipt = call(
        usage={
            "prompt_tokens": bad,
            "completion_tokens": 10,
            "reasoning_tokens": 11,
            "cached_tokens": 1,
        }
    )
    result = summary([receipt])
    assert result["input"]["known"] is None
    assert result["reasoning"]["known"] is None
    assert result["cache"]["ratio"] is None
    assert result["usd"]["known"] is None


def test_conflicting_same_generation_is_one_anomalous_dispatch_not_two_fees():
    result = summary([call("a", "same", {"cost": "0.1"}), call("b", "same", {"cost": "0.2"})])
    assert result["eligible_dispatches"] == 1
    assert result["usd"]["known"] is None and result["anomaly_dispatches"] == 1


def test_failed_unassigned_rows_and_zero_cache_denominator_remain_visible():
    receipt = call(usage={"cost": 0, "prompt_tokens": 0, "cached_tokens": 0})
    runs = [SimpleNamespace(id="failed", state="halted")]
    result = conversation_metrics([receipt], runs, [], as_of="now", scope_start="start")
    assert len(result["responses"]) == 2
    assert result["responses"][0]["state"] == "halted"
    assert result["responses"][1]["state"] == "unassigned"
    assert result["cache"]["ratio"] is None and result["usd"]["known"] == "0"


def encrypted_event(result, arguments=None):
    dek = b"s" * 32
    row = SimpleNamespace(
        run_id=uuid7(),
        sequence=7,
        kind="tool.read_result",
        payload={
            "tool": "task.query.v1",
            "count": 0,
        },
    )
    body = {
        "arguments": arguments
        or {
            "filter": {"title_contains": "mẫu"},
            "limit": 20,
            "projection": ["title"],
            "cursor": "OPAQUE-CURSOR-SENTINEL",
        },
        "result": result,
    }
    row.payload["body_ciphertext"] = crypto.seal_content(
        dek, json.dumps(body), aad=crypto.event_content_aad(row.run_id, 7, row.kind)
    )
    return row, dek


def test_query_projection_decrypts_allowlist_only_without_rows_ids_or_raw_cursor():
    row, dek = encrypted_event(
        {
            "count": 1,
            "coverage": "partial",
            "data_as_of": datetime.now(UTC).isoformat(),
            "next_cursor": "RAW-NEXT-SENTINEL",
            "rows": [
                {
                    "id": "ROW-ID-SENTINEL",
                    "title": "BODY-SENTINEL",
                    "source_version": 9,
                    "collection_version": 8,
                }
            ],
            "body_md": "PRIVATE-SENTINEL",
            "items": ["CHECKLIST-SENTINEL"],
        }
    )
    original = dict(row.payload)
    projected = tool_activity(row, dek)
    encoded = json.dumps(projected)
    assert projected["query"]["projection"] == ["title"]
    assert projected["query"]["cursor_present"] and projected["query"]["count"] == 1
    assert projected["query"]["intrinsic_provenance"] == ["source_version", "collection_version"]
    for private in [
        "OPAQUE-CURSOR-SENTINEL",
        "RAW-NEXT-SENTINEL",
        "ROW-ID-SENTINEL",
        "BODY-SENTINEL",
        "PRIVATE-SENTINEL",
        "CHECKLIST-SENTINEL",
    ]:
        assert private not in encoded
    assert row.payload == original  # No plaintext persistence.
    # Wrong key/AAD is unavailable, never a zero-match result.
    assert tool_activity(row, b"x" * 32)["state"] == "unavailable"
    row.sequence += 1
    assert tool_activity(row, dek)["query"] is None


def test_error_and_invalid_receipt_never_display_zero_matches():
    row, dek = encrypted_event(
        {"error": {"code": "invalid_task_query_cursor", "message": "UNTRUSTED-ERROR-SENTINEL"}}
    )
    projected = tool_activity(row, dek)
    assert projected["state"] == "error" and projected["query"]["count"] is None
    assert "UNTRUSTED-ERROR-SENTINEL" not in json.dumps(projected)
    row.payload["body_ciphertext"] = "invalid"
    assert tool_activity(row, dek)["query"] is None


def test_current_read_tools_have_basic_labels_and_error_state_without_rich_payload():
    for name in [
        "task.aggregate.v1",
        "task.inspect_batch.v1",
        "task.read_content.v1",
        "task.freeze_selection.v1",
    ]:
        row, dek = encrypted_event({"error": {"code": "synthetic"}, "rows": ["SECRET"]})
        row.payload["tool"] = name
        projected = tool_activity(row, dek)
        assert projected["state"] == "error"
        assert projected["query"] is None
        assert projected["label"] != "Công cụ Task"
        assert "SECRET" not in json.dumps(projected)


def test_partial_receipts_merge_aliases_and_validate_subsets_after_late_whole_count():
    early = call("same", None, {"reasoning_tokens": 3, "cost": "0.1"})
    duplicate = call("other", "generation", {"completion_tokens": 10})
    late = call("same", "generation", {"completion_tokens": 10})
    result = summary([early, duplicate, late])
    assert result["eligible_dispatches"] == 1
    assert result["reasoning"]["known"] == 3
    assert result["usd"]["known"] == "0.1"
