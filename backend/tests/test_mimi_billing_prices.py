"""Synthetic accounting and optional enrichment; no DB or real provider egress."""

import asyncio
import copy
import time
from decimal import Decimal
from types import SimpleNamespace

import httpx2
import pytest

from app.agent.billing_prices import (
    billing_sample,
    enrich_generation_usage,
    safe_generation_billing,
    summarize_prices,
)
from app.agent.observations import accounting_dispatches, conversation_metrics


def evidence(prompt=100, cached=50, output=20, rate="0.1", cache_rate="0.01", out_rate="0.5"):
    input_rate, read_rate, output_rate = (
        Decimal(v) / 1_000_000 for v in (rate, cache_rate, out_rate)
    )
    prompt_cost = input_rate * (prompt - cached) + read_rate * cached
    output_cost = output_rate * output
    metadata = {
        "id": "synthetic-gen",
        "is_byok": False,
        "native_tokens_prompt": prompt,
        "native_tokens_completion": output,
        "native_tokens_cached": cached,
        "native_tokens_reasoning": output // 2,
        "native_tokens_completion_images": 0,
        "num_media_prompt": 0,
        "num_media_completion": 0,
        "num_input_audio_prompt": 0,
        "num_search_results": 0,
        "num_fetches": 0,
        "total_cost": str(prompt_cost + output_cost),
        "cache_discount": str((input_rate - read_rate) * cached),
    }
    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": output,
        "cost": metadata["total_cost"],
        "prompt_tokens_details": {"cached_tokens": cached, "cache_write_tokens": 0},
        "cost_details": {
            "upstream_inference_prompt_cost": str(prompt_cost),
            "upstream_inference_completions_cost": str(output_cost),
        },
    }
    return usage, metadata


def test_native_rate_equations_weight_each_token_group_and_do_not_add_reasoning():
    one = billing_sample(*evidence(), "synthetic-gen")
    two = billing_sample(
        *evidence(prompt=900, cached=0, output=80, rate="0.2", out_rate="1"), "synthetic-gen"
    )
    result = summarize_prices([{"prices": one}, {"prices": two}])
    assert Decimal(result["input_uncached"]["min"]) == Decimal("0.1")
    assert (
        Decimal(result["input_uncached"]["weighted_average"])
        == (Decimal("0.1") * 50 + Decimal("0.2") * 900) / 950
    )
    assert Decimal(result["output"]["weighted_average"]) == Decimal("0.9")
    assert result["cache_read"]["samples"] == 1
    assert Decimal(result["cache_read"]["min"]) == Decimal("0.01")
    assert result["output"]["tokens"] == 100


@pytest.mark.parametrize(
    "field,value",
    [
        ("is_byok", True),
        ("is_byok", None),
        ("native_tokens_cached", None),
        ("native_tokens_prompt", 0),
        ("native_tokens_completion", 0),
        ("native_tokens_cached", 101),
        ("native_tokens_reasoning", 21),
        ("num_media_prompt", 1),
        ("num_media_completion", None),
        ("num_fetches", 1),
        ("num_search_results", 1),
        ("native_tokens_completion_images", 1),
        ("total_cost", "0.2"),
        ("cache_discount", "NaN"),
        ("cache_discount", "0.01"),
        ("id", "wrong-generation"),
    ],
)
def test_unknown_or_ineligible_metadata_cannot_become_historical_prices(field, value):
    usage, generation = evidence()
    generation[field] = value
    sample = billing_sample(usage, generation, "synthetic-gen")
    if field in {"native_tokens_cached", "native_tokens_prompt", "cache_discount"}:
        assert sample is not None and sample["output"] is not None
        assert sample["input_uncached"] is None and sample["cache_read"] is None
    elif field in {"native_tokens_completion", "native_tokens_reasoning"}:
        assert sample is not None and sample["output"] is None
        assert sample["input_uncached"] is not None and sample["cache_read"] is not None
    else:
        assert sample is None


def test_cache_write_missing_split_conflicting_usage_and_zero_cache_discount():
    for change in [
        lambda u: u["prompt_tokens_details"].pop("cache_write_tokens"),
        lambda u: u["prompt_tokens_details"].update(cache_write_tokens=1),
        lambda u: u["cost_details"].pop("upstream_inference_prompt_cost"),
        lambda u: u.update(cost="0.4"),
        lambda u: u.update(prompt_tokens=200),
    ]:
        usage, generation = evidence()
        change(usage)
        sample = billing_sample(usage, generation, "synthetic-gen")
        if "upstream_inference_prompt_cost" not in usage["cost_details"] or usage["cost"] == "0.4":
            assert sample is None
        else:
            assert sample is not None and sample["output"] is not None
            assert sample["input_uncached"] is None and sample["cache_read"] is None
    usage, generation = evidence(cached=0)
    generation["cache_discount"] = "0.000001"
    sample = billing_sample(usage, generation, "synthetic-gen")
    assert sample["input_uncached"] is None and sample["output"] is not None
    zero = billing_sample(*evidence(rate="0", cache_rate="0", out_rate="0"), "synthetic-gen")
    assert zero["output"][0] == 0
    all_cache = billing_sample(*evidence(cached=100), "synthetic-gen")
    assert all_cache["input_uncached"] is None and all_cache["cache_read"] is not None
    usage, generation = evidence()
    usage["cost_details"]["upstream_inference_prompt_cost"] = "0.001"
    assert billing_sample(usage, generation, "synthetic-gen") is None
    usage, generation = evidence()
    usage["prompt_tokens_details"]["audio_tokens"] = 1
    assert billing_sample(usage, generation, "synthetic-gen") is None
    usage, generation = evidence()
    usage["mimi_billing"] = safe_generation_billing(generation, "synthetic-gen")
    usage["cost_details"]["upstream_inference_prompt_cost"] = "not-a-cost"
    assert billing_sample(usage, generation, "synthetic-gen") is None


def test_projection_deduplicates_generations_reuses_and_conflicting_receipts():
    usage, generation = evidence()
    receipt = SimpleNamespace(
        id="call",
        run_id="run",
        state="succeeded",
        route={"kind": "openrouter"},
        usage=usage,
        result={"response_id": "synthetic-gen", "generation": generation},
    )
    reused = copy.deepcopy(receipt)
    reused.id, reused.route["paid_dispatch"] = "reuse", False
    result = conversation_metrics(
        [receipt, receipt, reused], [], [], as_of="now", scope_start="start"
    )
    assert result["token_prices"]["matched_dispatches"] == 1
    assert result["token_prices"]["output"]["tokens"] == 20
    conflicting = copy.deepcopy(receipt)
    conflicting.usage["cost"] = "0.5"
    dispatches, _ = accounting_dispatches([receipt, conflicting])
    assert summarize_prices(dispatches)["matched_dispatches"] == 0


def test_safe_scalar_allowlist_drops_raw_content_and_never_fills_absent_fields():
    _, metadata = evidence()
    metadata.update(prompt="PRIVATE-SENTINEL", api_key="SECRET-SENTINEL", provider_responses=[{}])
    safe = safe_generation_billing(metadata, "synthetic-gen")
    assert "SENTINEL" not in repr(safe)
    assert "cache_write_tokens" not in safe
    assert safe_generation_billing(metadata, "other") == {}
    assert safe_generation_billing({"id": "g"}, "g") == {"generation_id": "g"}


@pytest.mark.parametrize(
    "mode", ["success", "failure", "timeout", "malformed", "sufficient", "offline"]
)
def test_auxiliary_read_is_bounded_nonfatal_reuses_evidence_and_never_replays(monkeypatch, mode):
    usage, generation = evidence()
    calls = []

    async def endpoint(identity, **kwargs):
        calls.append(identity)
        if mode == "failure":
            raise RuntimeError("fake endpoint unavailable")
        if mode == "timeout":
            await asyncio.sleep(10)
        return None if mode == "malformed" else generation

    monkeypatch.setattr("app.agent.openrouter.get_generation", endpoint)
    if mode == "sufficient":
        usage["mimi_billing"] = safe_generation_billing(generation, "synthetic-gen")
    completion = SimpleNamespace(text="Câu trả lời hữu ích", usage=usage)
    started = time.perf_counter()
    asyncio.run(
        enrich_generation_usage(
            completion.usage,
            "synthetic-gen",
            settings=SimpleNamespace(mimi_live_provider_enabled=mode != "offline"),
        )
    )
    elapsed = time.perf_counter() - started
    assert completion.text == "Câu trả lời hữu ích"
    assert len(calls) == (0 if mode in {"sufficient", "offline"} else 1)
    assert elapsed < 1.2
    print(f"metadata_read_mode={mode} elapsed_ms={elapsed * 1000:.2f} calls={len(calls)}")
    if mode == "success":
        assert billing_sample(usage, {}, "synthetic-gen") is not None
    elif mode not in {"sufficient"}:
        assert "mimi_billing" not in usage


@pytest.mark.parametrize("mode", ["failure", "timeout"])
def test_actual_sdk_completion_survives_optional_metadata_failure(monkeypatch, mode):
    from test_mimi_openai_sdk import _settings

    from app.agent import openai_sdk
    from app.agent.context import AssistantText

    model_calls, metadata_calls = [], []

    def handler(request):
        model_calls.append(request.url.path)
        return httpx2.Response(
            200,
            json={
                "id": "synthetic-gen",
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
                            "content": '{"kind":"assistant_text","text":"Câu trả lời hữu ích"}',
                        },
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3, "cost": 0.001},
            },
        )

    async def endpoint(identity, **kwargs):
        metadata_calls.append(identity)
        if mode == "timeout":
            await asyncio.sleep(10)
        raise RuntimeError("synthetic endpoint failure")

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
            [{"role": "user", "content": "synthetic"}],
            settings=_settings(),
            agent_contract=True,
            force_task_tool=True,
        )
        assert isinstance(result.outcome, AssistantText)
        assert result.outcome.text == "Câu trả lời hữu ích"
        assert result.response_id == "synthetic-gen" and result.usage["cost"] == 0.001

    started = time.perf_counter()
    asyncio.run(run())
    elapsed = time.perf_counter() - started
    assert model_calls == ["/api/v1/chat/completions"]
    assert metadata_calls == ["synthetic-gen"]
    print(
        f"sdk_answer_metadata_{mode} elapsed_ms={elapsed * 1000:.2f} model_calls=1 metadata_reads=1"
    )
