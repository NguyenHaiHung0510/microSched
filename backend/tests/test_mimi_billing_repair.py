"""Owner296 grouped price repair: endpoint semantics and group-specific proof."""

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
    safe_generation_billing,
    summarize_prices,
)
from app.agent.observations import conversation_metrics


def actual_sample():
    sample = json.loads(
        (Path(__file__).parent / "fixtures/mimi_billing_scalar.json").read_text(encoding="utf-8")
    )
    return sample["terminal_usage"], sample["metadata"]


def attest(usage, identity):
    usage["mimi_billing_class"] = {
        "version": 1,
        "source": "server_sdk_wire",
        "generation_id": identity,
        "billing_class": "text_only_no_plugins",
    }
    return usage


@pytest.mark.parametrize("upstream", [0, None])
def test_peer01_generation_upstream_is_not_terminal_charged_cost(upstream):
    usage, metadata = actual_sample()
    # Isolate endpoint semantics with explicit synthetic zero exclusion evidence.
    metadata.update(
        {
            key: 0
            for key in (
                "native_tokens_completion_images",
                "num_media_prompt",
                "num_media_completion",
                "num_input_audio_prompt",
                "num_search_results",
                "num_fetches",
            )
        }
    )
    metadata["upstream_inference_cost"] = upstream
    sample = billing_sample(usage, metadata, metadata["id"])
    assert sample is not None
    assert sample["output"] == (Decimal("0.0000005"), 259)
    # Same-meaning actual charged total/split mismatches must still fail closed.
    for broken in ("total_cost",):
        bad = {**metadata, broken: "0.1"}
        assert billing_sample(usage, bad, metadata["id"]) is None
    bad_usage = copy.deepcopy(usage)
    bad_usage["cost_details"]["upstream_inference_cost"] = "0.1"
    assert billing_sample(bad_usage, metadata, metadata["id"]) is None


@pytest.mark.parametrize("mode", ["discount_missing", "cached_missing", "no_cache"])
def test_peer02_each_price_group_uses_only_its_own_proof(mode):
    usage, metadata = evidence(cached=0 if mode == "no_cache" else 50)
    metadata.pop("cache_discount")
    if mode == "cached_missing":
        metadata.pop("native_tokens_cached")
        usage["prompt_tokens_details"].pop("cached_tokens")
    sample = billing_sample(usage, metadata, metadata["id"])
    assert sample is not None
    assert sample["output"] == (Decimal("0.0000005"), 20)
    assert sample["cache_read"] is None
    assert sample["input_uncached"] == ((Decimal("0.0000001"), 100) if mode == "no_cache" else None)


def test_exact_scalar_stays_unknown_without_shape_proof_and_derives_when_bound():
    usage, metadata = actual_sample()
    original = copy.deepcopy(metadata)
    assert billing_sample(usage, metadata, metadata["id"]) is None
    attest(usage, metadata["id"])
    usage["mimi_billing"] = safe_generation_billing(metadata, metadata["id"])
    sample = billing_sample(usage, {}, metadata["id"])
    assert sample is not None
    assert [sample[key][0] * 1_000_000 for key in ("input_uncached", "cache_read", "output")] == [
        Decimal("0.08"),
        Decimal("0.008"),
        Decimal("0.5"),
    ]
    assert metadata == original  # Nulls and the endpoint-specific upstream0 were not rewritten.


def test_partial_coverage_counts_do_not_call_output_only_dispatch_complete():
    usage, metadata = evidence()
    metadata.pop("cache_discount")
    call = SimpleNamespace(
        id="c",
        run_id="r",
        state="succeeded",
        route={"kind": "openrouter"},
        usage=usage,
        result={"response_id": metadata["id"], "generation": metadata},
    )
    result = conversation_metrics([call], [], [], as_of="now", scope_start="start")["token_prices"]
    assert result["matched_dispatches"] == 1
    assert result["partial_dispatches"] == 1
    assert result["unknown_dispatches"] == 0
    assert result["output"]["samples"] == 1
    assert result["input_uncached"]["unknown"] == 1
    assert result["cache_read"]["unknown"] == 1
    _, uncached_metadata = evidence(cached=0)
    uncached_usage, _ = evidence(cached=0)
    uncached = billing_sample(uncached_usage, uncached_metadata, uncached_metadata["id"])
    assert summarize_prices([{"prices": uncached}])["cache_read"]["not_applicable"] == 1


@pytest.mark.parametrize("change", ["plugins", "preset", "online", "media", "response", "wrong_id"])
def test_classification_is_bound_server_shape_and_explicit_evidence_still_wins(change):
    usage, metadata = actual_sample()
    request = {"model": "vendor/text", "messages": [{"role": "user", "content": "synthetic"}]}
    if change == "plugins":
        request["plugins"] = [{"id": "web"}]
    elif change == "preset":
        request["model"] = "@preset/unknown"
    elif change == "online":
        request["model"] += ":online"
    elif change == "media":
        request["messages"][0]["content"] = [{"type": "image_url", "image_url": "sentinel"}]
    usage["mimi_billing_class"] = {"provider_self_issued": True}
    attest_text_billing(usage, request, metadata["id"], response_text=change != "response")
    if change == "wrong_id":
        usage["mimi_billing_class"]["generation_id"] = "different-generation"
    assert billing_sample(usage, metadata, metadata["id"]) is None


@pytest.mark.parametrize(
    "field", ["num_search_results", "num_media_prompt", "native_tokens_completion_images"]
)
def test_bound_classification_cannot_override_explicit_nonzero_or_invalid_counter(field):
    usage, metadata = actual_sample()
    attest(usage, metadata["id"])
    for contradiction in (1, -1, True, "invalid"):
        metadata[field] = contradiction
        assert billing_sample(usage, metadata, metadata["id"]) is None


def test_missing_native_output_does_not_invent_output_but_retains_input_groups():
    usage, metadata = evidence()
    metadata.pop("native_tokens_completion")
    sample = billing_sample(usage, metadata, metadata["id"])
    assert sample["output"] is None and sample["input_uncached"] is not None
    assert "output" in sample["unknown_groups"]


def test_sdk_shape_attests_current_safe_scalar_without_defaults_or_network(monkeypatch):
    import asyncio

    import httpx2
    from test_mimi_openai_sdk import _settings

    from app.agent import openai_sdk

    usage, metadata = actual_sample()
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx2.Response(
            200,
            json={
                "id": metadata["id"],
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
                            "content": '{"kind":"assistant_text","text":"Hữu ích"}',
                        },
                    }
                ],
                "usage": usage,
            },
        )

    async def forbidden(*args, **kwargs):
        raise AssertionError("Injected clients must not GET metadata")

    monkeypatch.setattr("app.agent.openrouter.get_generation", forbidden)

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as transport:
            result = await openai_sdk.complete(
                [{"role": "user", "content": "synthetic"}],
                settings=_settings(_env_file=None),
                client=transport,
                agent_contract=True,
            )
        result.usage["mimi_billing"] = safe_generation_billing(metadata, result.response_id)
        sample = billing_sample(result.usage, {}, result.response_id)
        assert sample["input_uncached"][0] * 1_000_000 == Decimal("0.08")
        assert sample["cache_read"][0] * 1_000_000 == Decimal("0.008")
        assert sample["output"][0] * 1_000_000 == Decimal("0.5")
        assert "num_media_prompt" not in result.usage["mimi_billing"]
        assert "synthetic" not in repr(result.usage["mimi_billing_class"]).replace(
            metadata["id"], ""
        )

    asyncio.run(run())
    assert requests == ["/api/v1/chat/completions"]
