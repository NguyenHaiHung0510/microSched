"""Native terminal billing; proof is synthetic, fixture contains numeric scalars only."""

import asyncio
import copy
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_mimi_billing_prices import evidence

from app.agent.billing_prices import (
    attest_text_billing,
    billing_sample,
    enrich_generation_usage,
    safe_generation_billing,
)
from app.agent.observations import accounting_dispatches

IDENTITY = "synthetic-terminal-prices"


def terminal():
    usage = json.loads(
        (Path(__file__).parent / "fixtures/mimi_terminal_usage_scalar.json").read_text()
    )["terminal_usage"]
    # Synthetic eligibility, never a claim about omitted historical proof.
    usage["is_byok"] = False
    attest_text_billing(
        usage,
        {"model": "synthetic/text", "messages": [{"role": "user", "content": "Synthetic"}]},
        IDENTITY,
        response_text=True,
    )
    return usage


def test_terminal_native_no_cache_without_generation_metadata():
    usage = terminal()
    before = copy.deepcopy(usage)
    sample = billing_sample(usage, {}, IDENTITY)
    assert sample is not None
    assert sample["input_uncached"] == (Decimal("8e-8"), 7844)
    assert sample["output"] == (Decimal("5e-7"), 808)
    assert sample["cache_read"] is None and sample["not_applicable"] == ["cache_read"]
    assert sample["unknown_groups"] == []
    assert usage == before and "mimi_billing" not in usage


@pytest.mark.parametrize("cached", [None, 6400])
def test_terminal_output_independent_of_missing_cache_or_discount(cached):
    usage = terminal()
    usage["prompt_tokens_details"].pop("cache_write_tokens")
    if cached is None:
        usage["prompt_tokens_details"].pop("cached_tokens")
    else:
        usage["prompt_tokens_details"]["cached_tokens"] = cached
    sample = billing_sample(usage, {}, IDENTITY)
    assert sample is not None and sample["output"] == (Decimal("5e-7"), 808)
    assert sample["input_uncached"] is None and sample["cache_read"] is None
    assert set(sample["unknown_groups"]) == {"input_uncached", "cache_read"}


@pytest.mark.parametrize(
    "change",
    [
        "byok_missing",
        "byok_null",
        "byok_true",
        "byok_zero",
        "class_missing",
        "class_wrong_id",
        "class_wrong_source",
        "split_missing",
        "charged_mismatch",
        "upstream_mismatch",
        "audio",
        "addon",
    ],
)
def test_terminal_missing_or_contradictory_common_proof_rejects(change):
    usage = terminal()
    if change == "byok_missing":
        usage.pop("is_byok")
    elif change.startswith("byok_"):
        usage["is_byok"] = {"byok_null": None, "byok_true": True, "byok_zero": 0}[change]
    elif change == "class_missing":
        usage.pop("mimi_billing_class")
    elif change == "class_wrong_id":
        usage["mimi_billing_class"]["generation_id"] = "another-generation"
    elif change == "class_wrong_source":
        usage["mimi_billing_class"]["source"] = "provider"
    elif change == "split_missing":
        usage["cost_details"].pop("upstream_inference_prompt_cost")
    elif change == "charged_mismatch":
        usage["cost"] = "0.5"
    elif change == "upstream_mismatch":
        usage["cost_details"]["upstream_inference_cost"] = "0.5"
    elif change == "audio":
        usage["completion_tokens_details"]["audio_tokens"] = 1
    else:
        usage["cost_details"]["server_tool_cost"] = "0.01"
    assert billing_sample(usage, {}, IDENTITY) is None


@pytest.mark.parametrize(
    "field",
    [
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
    ],
)
@pytest.mark.parametrize("invalid", [True, -1, "invalid", 1.5])
def test_terminal_malformed_counts_never_produce_a_price_for_affected_group(field, invalid):
    usage = terminal()
    if field in {"cached_tokens", "cache_write_tokens"}:
        usage["prompt_tokens_details"][field] = invalid
    elif field == "reasoning_tokens":
        usage["completion_tokens_details"][field] = invalid
    else:
        usage[field] = invalid
    sample = billing_sample(usage, {}, IDENTITY)
    assert sample is not None  # Unrelated group remains useful.
    rejected = "output" if field in {"completion_tokens", "reasoning_tokens"} else "input_uncached"
    assert sample[rejected] is None and rejected in sample["unknown_groups"]


@pytest.mark.parametrize("stored", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        "identity",
        "byok",
        "byok_unknown",
        "prompt",
        "output",
        "cache",
        "reasoning",
        "cost",
        "exclusion",
        "malformed_exclusion",
    ],
)
def test_supplied_generation_negative_proof_cannot_fall_back_to_terminal(stored, change):
    usage = terminal()
    metadata = {
        "id": IDENTITY,
        "is_byok": False,
        "native_tokens_prompt": 7844,
        "native_tokens_completion": 808,
        "native_tokens_cached": 0,
        "native_tokens_reasoning": 547,
        "total_cost": usage["cost"],
    }
    field, value = {
        "identity": ("id", "wrong-generation"),
        "byok": ("is_byok", True),
        "byok_unknown": ("is_byok", None),
        "prompt": ("native_tokens_prompt", 99),
        "output": ("native_tokens_completion", 99),
        "cache": ("native_tokens_cached", 99),
        "reasoning": ("native_tokens_reasoning", 99),
        "cost": ("total_cost", "0.5"),
        "exclusion": ("num_fetches", 1),
        "malformed_exclusion": ("num_fetches", True),
    }[change]
    metadata[field] = value
    if stored:
        metadata["generation_id"] = metadata.pop("id")
        usage["mimi_billing"] = metadata
        metadata = {}
    sample = billing_sample(usage, metadata, IDENTITY)
    if change in {"prompt", "cache"}:
        assert sample is not None and sample["input_uncached"] is None
    elif change in {"output", "reasoning"}:
        assert sample is not None and sample["output"] is None
    else:
        assert sample is None


def test_partial_then_full_price_proof_merges_once_without_false_conflict():
    usage, metadata = evidence()

    def receipt(generation):
        return SimpleNamespace(
            id="synthetic-call",
            run_id="run",
            state="succeeded",
            route={"kind": "openrouter"},
            usage=usage,
            result={"response_id": "synthetic-gen", "generation": generation},
        )

    partial = {k: v for k, v in metadata.items() if k != "cache_discount"}
    dispatches, _ = accounting_dispatches([receipt(partial), receipt(metadata)])
    assert len(dispatches) == 1
    assert dispatches[0]["prices"] == billing_sample(usage, metadata, "synthetic-gen")
    assert "prices" not in dispatches[0]["conflicts"]


def test_partial_merge_does_not_hide_different_measured_prices():
    usage, metadata = evidence()
    changed = {**metadata, "cache_discount": "0.000001"}
    receipts = [
        SimpleNamespace(
            id="synthetic-call",
            run_id="run",
            state="succeeded",
            route={"kind": "openrouter"},
            usage=usage,
            result={"response_id": "synthetic-gen", "generation": item},
        )
        for item in (metadata, changed)
    ]
    dispatches, _ = accounting_dispatches(receipts)
    assert len(dispatches) == 1 and dispatches[0]["prices"] is None
    assert "prices" in dispatches[0]["conflicts"]


@pytest.mark.parametrize("change", ["identity", "malformed_reasoning"])
def test_enrichment_preserves_provided_negative_evidence(monkeypatch, change):
    usage = terminal()
    usage["prompt_tokens_details"]["cached_tokens"] = 6400  # Incomplete, needs optional GET.
    metadata = {
        "id": IDENTITY,
        "is_byok": False,
        "total_cost": usage["cost"],
        "native_tokens_prompt": 7844,
        "native_tokens_completion": 808,
        "native_tokens_cached": 6400,
    }
    if change == "identity":
        metadata["id"] = "wrong-generation"
    else:
        metadata["native_tokens_reasoning"] = True

    async def endpoint(*args, **kwargs):
        return metadata

    monkeypatch.setattr("app.agent.openrouter.get_generation", endpoint)
    asyncio.run(
        enrich_generation_usage(
            usage, IDENTITY, settings=SimpleNamespace(mimi_live_provider_enabled=True)
        )
    )
    assert billing_sample(usage, {}, IDENTITY) is None


def test_two_supplied_metadata_sources_cannot_hide_conflicting_discount():
    usage, metadata = evidence()
    usage["mimi_billing"] = safe_generation_billing(metadata, "synthetic-gen")
    changed = {**metadata, "cache_discount": "0.000001"}
    sample = billing_sample(usage, changed, "synthetic-gen")
    assert sample is not None and sample["output"] is not None
    assert sample["input_uncached"] is None and sample["cache_read"] is None


@pytest.mark.parametrize("stored", [False, True])
@pytest.mark.parametrize(
    "field", ["native_tokens_reasoning", "upstream_inference_prompt_cost", "cache_discount"]
)
def test_malformed_optional_metadata_is_not_sanitized_into_missing_proof(stored, field):
    usage = terminal()
    metadata = {
        "id": IDENTITY,
        "is_byok": False,
        "total_cost": usage["cost"],
        "native_tokens_prompt": 7844,
        "native_tokens_completion": 808,
        "native_tokens_cached": 0,
        field: True,
    }
    if stored:
        usage["mimi_billing"] = safe_generation_billing(metadata, IDENTITY)
        metadata = {}
    sample = billing_sample(usage, metadata, IDENTITY)
    if field == "upstream_inference_prompt_cost":
        assert sample is None
    else:
        assert sample is not None
        assert sample["output" if field == "native_tokens_reasoning" else "input_uncached"] is None


@pytest.mark.parametrize("complete", [False, True])
def test_sdk_terminal_prices_survive_optional_read_timeout(monkeypatch, complete):
    import httpx2
    from test_mimi_openai_sdk import _settings

    from app.agent import openai_sdk
    from app.agent.context import AssistantText

    usage = terminal()
    usage.pop("mimi_billing_class")  # Only the real SDK attestor can issue it.
    if not complete:
        usage["prompt_tokens_details"]["cached_tokens"] = 6400
    model_calls, metadata_calls = [], []

    def handler(request):
        model_calls.append(request.url.path)
        return httpx2.Response(
            200,
            json={
                "id": IDENTITY,
                "object": "chat.completion",
                "created": 1,
                "model": "vendor/model",
                "provider": "provider-a-actual",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"kind":"assistant_text","text":"Synthetic answer"}',
                        },
                    }
                ],
                "usage": usage,
            },
        )

    async def endpoint(*args, **kwargs):
        metadata_calls.append("mock GET")
        await asyncio.sleep(10)  # Existing 0.8s bound must cut this short.

    monkeypatch.setattr("app.agent.openrouter.get_generation", endpoint)
    original_client = openai_sdk._client

    async def run():
        transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        monkeypatch.setattr(
            openai_sdk,
            "_client",
            lambda settings, **kwargs: original_client(
                settings, api_key="synthetic", client=transport
            ),
        )
        result = await openai_sdk.complete(
            [{"role": "user", "content": "Synthetic"}],
            settings=_settings(),
            agent_contract=True,
            force_task_tool=True,
        )
        assert isinstance(result.outcome, AssistantText)
        assert result.outcome.text == "Synthetic answer"
        prices = billing_sample(result.usage, {}, result.response_id)
        assert prices is not None and prices["output"] == (Decimal("5e-7"), 808)
        assert (prices["input_uncached"] is not None) is complete
        assert "mimi_billing" not in result.usage

    asyncio.run(run())
    assert len(model_calls) == 1 and len(metadata_calls) == (0 if complete else 1)


@pytest.mark.parametrize("complete", [True, False])
def test_native_terminal_enrichment_skips_complete_and_keeps_partial_on_failure(
    monkeypatch, complete
):
    usage = terminal()
    if not complete:
        usage["prompt_tokens_details"]["cached_tokens"] = 6400
    calls = []

    async def endpoint(*args, **kwargs):
        calls.append("mock GET")
        raise TimeoutError("Synthetic metadata unavailable")

    monkeypatch.setattr("app.agent.openrouter.get_generation", endpoint)
    asyncio.run(
        enrich_generation_usage(
            usage, IDENTITY, settings=SimpleNamespace(mimi_live_provider_enabled=True)
        )
    )
    assert len(calls) == (0 if complete else 1)
    assert billing_sample(usage, {}, IDENTITY)["output"] == (Decimal("5e-7"), 808)
    assert "mimi_billing" not in usage
