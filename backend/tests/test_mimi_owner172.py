"""Owner172 approved correction contracts using synthetic inputs and no egress."""

import asyncio
import copy
import json
import time
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_mimi_collection_contracts import catalog, settings
from test_mimi_owner162 import certificate

from app.agent.config_policy import (
    ModelPrice,
    OperatingPolicy,
    PolicyChange,
    bind_policy,
    bootstrap_policy,
    revised_policy,
    validate_input,
)
from app.agent.openrouter import RouteContractError, build_request, validate_response_identity
from app.agent.route_pool import (
    CatalogCache,
    NoEligibleEndpoint,
    eligible_pool,
)
from app.agent.service import MessageCreate, _collection_confirmation_block_reason


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-0.01", "1000.01", True, None, ".000000001"])
def test_price_negative_then_restore(bad):
    with pytest.raises(ValidationError):
        ModelPrice(prompt=bad, completion="1.44")
    assert ModelPrice(prompt=".36", completion="1.44").prompt == Decimal(".36")


def test_revision_model_set_and_lowering_next_snapshot_preserves_sent_snapshot():
    selected = settings()
    first = bootstrap_policy(selected)
    first_wire = bind_policy(selected, first)
    prices = copy.deepcopy(first.model_dump(mode="json")["prices"])
    prices[selected.mimi_route_model] = {"prompt": ".05", "completion": ".10"}
    change = PolicyChange(expected_revision=0, input_codepoints=50_000, prices=prices)
    lower = revised_policy(first, change)
    with pytest.raises(HTTPException, match="policy_stale"):
        revised_policy(lower, change)
    next_wire = bind_policy(selected, lower)
    assert next_wire.mimi_operating_policy_revision == 1
    assert next_wire.mimi_route_max_input_price == Decimal(".05")
    assert first_wire.mimi_route_max_input_price == Decimal(".36")
    del prices[selected.mimi_route_model]
    with pytest.raises(ValidationError, match="supported_model_set"):
        OperatingPolicy(revision=1, prices=prices)


def test_unicode_50k_no_slice_then_overflow_preserves_full_draft():
    policy = bootstrap_policy(settings())
    content = "🌸" * 49_999 + "ệ"
    payload = MessageCreate(client_id="synthetic-50k", content=content)
    validate_input(payload.content, policy)
    assert len(payload.content) == 50_000 and payload.content == content
    overflow = content + "x"
    with pytest.raises(HTTPException) as failure:
        validate_input(overflow, policy)
    assert failure.value.detail == {
        "code": "mimi_input_codepoints_exceeded",
        "limit": 50_000,
        "count": 50_001,
    }
    assert overflow == content + "x"
    assert len(content.encode("utf-8")) > len(content)


@pytest.mark.parametrize("mutate", ["model", "provider", "missing_model", "missing_provider"])
def test_actual_identity_reject_then_restore_preserves_usage(mutate):
    selected = settings()
    terminal = {
        "id": "synthetic-identity",
        "model": selected.mimi_route_model,
        "provider": "DeepInfra",
        "usage": {"prompt_tokens": 8, "cost": 0.001},
    }
    bad = dict(terminal)
    if mutate.startswith("missing_"):
        bad.pop(mutate.removeprefix("missing_"))
    else:
        bad[mutate] = "wrong"
    with pytest.raises(RouteContractError, match="actual_identity") as failure:
        validate_response_identity(bad, selected)
    assert failure.value.terminal_receipt["usage"]["cost"] == 0.001
    validate_response_identity(terminal, selected)


def test_common_capacity_price_and_separate_prompt_capacity_negative_restore():
    selected = settings(mimi_route_max_input_price=0.36, mimi_route_max_output_price=1.44)
    payload = catalog(
        {
            "context_length": 408192,
            "max_prompt_tokens": 400000,
            "pricing": {"prompt": ".00000036", "completion": ".00000144"},
        }
    )
    assert eligible_pool(payload, model=selected.mimi_route_model, effort="high").tags
    for delta in (
        {"context_length": 408191},
        {"max_prompt_tokens": 399999},
        {"pricing": {"prompt": ".00000037", "completion": ".00000144"}},
    ):
        bad = copy.deepcopy(payload)
        bad["data"]["endpoints"][0].update(delta)
        with pytest.raises(NoEligibleEndpoint):
            eligible_pool(bad, model=selected.mimi_route_model, effort="high")
    assert eligible_pool(payload, model=selected.mimi_route_model, effort="high").tags


def test_total_wire_guard_includes_schema_read_growth_and_output_separately():
    selected = settings()
    normal = [{"role": "user", "content": "🌸" * 50_000}]
    request = build_request(normal, selected, agent_contract=True)
    assert request["messages"] == normal
    grown = [*normal, {"role": "tool", "content": "x" * 450_000}]
    # Owner184 A allows temporary operating-target overshoot; the full Unicode
    # input and tool growth survive, without treating bytes as native tokens.
    assert build_request(grown, selected, agent_contract=True)["messages"] == grown
    over_resource = [*grown, {"role": "tool", "content": "x" * selected.mimi_max_payload_bytes}]
    with pytest.raises(RouteContractError, match="payload_bytes_exceeded"):
        build_request(over_resource, selected, agent_contract=True)
    assert over_resource[-1]["content"] == "x" * selected.mimi_max_payload_bytes
    assert (
        build_request(normal, selected, agent_contract=True)["max_tokens"]
        == selected.mimi_route_max_output_tokens
    )


def test_preview_survives_new_generation_but_revoked_lease_still_blocks():
    conv = SimpleNamespace(sensitivity="standard", is_private=False, generation=900)
    run = SimpleNamespace(generation=2, execution_lease={"capabilities": ["task.collection.v1"]})
    from app.agent.service import COLLECTION_TOOL

    run.execution_lease["capabilities"] = [COLLECTION_TOOL]
    assert _collection_confirmation_block_reason(conv, run) is None
    run.execution_lease["revoked_at"] = "synthetic"
    assert (
        _collection_confirmation_block_reason(conv, run)
        == "change_set_collection_lease_not_authorized"
    )


def test_metadata_singleflight_swr_failed_refresh_age_and_fresh_empty():
    async def scenario():
        selected = settings()
        payload = catalog()
        proof = certificate(selected, payload)
        selected = selected.model_copy(
            update={"mimi_route_qualifications_json": json.dumps([proof])}
        )
        cache = CatalogCache()
        calls = []
        mode = {"value": "valid"}

        def handler(request):
            calls.append(request)
            if mode["value"] == "fail":
                return httpx.Response(503)
            data = (
                payload
                if mode["value"] == "valid"
                else {"data": {"id": selected.mimi_route_model, "endpoints": []}}
            )
            return httpx.Response(200, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            one, two = await asyncio.gather(
                cache.refresh(selected, client=client), cache.refresh(selected, client=client)
            )
            assert len(calls) == 1 and one.tags == two.tags
            successful_at = time.time() - 901
            cache.entries[selected.mimi_route_model] = (payload, successful_at)
            mode["value"] = "fail"
            stale = await cache.refresh(selected, client=client)
            assert stale.checked_at == successful_at
            await asyncio.gather(cache.inflight[selected.mimi_route_model], return_exceptions=True)
            assert cache.entries[selected.mimi_route_model][1] == successful_at
            mode["value"] = "empty"
            await cache.refresh(selected, client=client)
            await cache.inflight[selected.mimi_route_model]
            with pytest.raises(NoEligibleEndpoint):
                await cache.refresh(selected, client=client)

    asyncio.run(scenario())


def test_cached_metadata_refilters_lower_price_and_expired_qualification_without_get():
    async def scenario():
        selected = settings()
        payload = catalog()
        proof = certificate(selected, payload)
        selected = selected.model_copy(
            update={"mimi_route_qualifications_json": json.dumps([proof])}
        )
        cache = CatalogCache()
        cache.entries[selected.mimi_route_model] = (payload, time.time())
        assert (await cache.refresh(selected)).tags
        with pytest.raises(NoEligibleEndpoint):
            await cache.refresh(selected.model_copy(update={"mimi_route_max_input_price": 0.01}))
        proof["expires_at"] = time.time() - 1
        with pytest.raises(NoEligibleEndpoint):
            await cache.refresh(
                selected.model_copy(update={"mimi_route_qualifications_json": json.dumps([proof])})
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("transport_name", ["httpx", "openai_sdk"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "violation", ["wrong_model", "wrong_provider", "missing_provider", "valid"]
)
def test_transport_rejects_unqualified_identity_before_exposing_text(
    transport_name, stream, violation
):
    async def scenario():
        from app.agent.openrouter import complete, complete_stream

        if transport_name == "openai_sdk":
            pytest.importorskip("openai")
            import httpx2 as wire_http
        else:
            wire_http = httpx
        selected = settings(mimi_transport=transport_name)
        payload = {
            "id": "synthetic-172-wire",
            "object": "chat.completion",
            "created": 1,
            "model": selected.mimi_route_model,
            "provider": "DeepInfra",
            "usage": {"prompt_tokens": 8, "completion_tokens": 2, "cost": 0.001},
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": '{"kind":"assistant_text","text":"Synthetic reply"}',
                    },
                }
            ],
        }
        if violation == "wrong_model":
            payload["model"] = "wrong/model"
        elif violation == "wrong_provider":
            payload["provider"] = "Wrong Provider"
        elif violation == "missing_provider":
            payload.pop("provider")
        events = []

        async def event(kind, value):
            events.append((kind, value))

        def handler(request):
            if not stream:
                return wire_http.Response(200, json=payload)
            chunk = {
                **payload,
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "delta": {"content": payload["choices"][0]["message"]["content"]},
                    }
                ],
            }
            body = ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
            return wire_http.Response(
                200, headers={"content-type": "text/event-stream"}, content=body
            )

        async with wire_http.AsyncClient(transport=wire_http.MockTransport(handler)) as client:
            invoke = complete_stream if stream else complete
            options = {"on_event": event} if stream else {}
            if violation == "valid":
                result = await invoke(
                    [], settings=selected, client=client, agent_contract=True, **options
                )
                assert result.model == selected.mimi_route_model and result.provider == "DeepInfra"
            else:
                with pytest.raises(RouteContractError, match="actual_identity") as failure:
                    await invoke(
                        [], settings=selected, client=client, agent_contract=True, **options
                    )
                assert failure.value.terminal_receipt["usage"]["cost"] == 0.001
                assert all(kind != "assistant.delta" for kind, value in events)

    asyncio.run(scenario())


def test_aliases_are_bound_to_the_requested_identity_not_global_route_escape():
    selected = settings(
        mimi_route_identity_aliases_json=json.dumps(
            {
                "models": {"other/model": ["wrong/model"]},
                "providers": {"Other Provider": ["Wrong Provider"]},
            }
        )
    )
    with pytest.raises(RouteContractError):
        validate_response_identity({"model": "wrong/model", "provider": "Wrong Provider"}, selected)
    selected = settings(
        mimi_route_identity_aliases_json=json.dumps(
            {
                "models": {selected.mimi_route_model: ["qualified/model-alias"]},
                "providers": {"deepinfra": ["Qualified Provider Alias"]},
            }
        )
    )
    validate_response_identity(
        {"model": "qualified/model-alias", "provider": "Qualified Provider Alias"}, selected
    )


def test_rebinding_policy_revision_keeps_pending_read_and_transcript_bytes():
    from test_mimi_context import _context

    from app.agent.context_builder import rebind_policy_budget

    selected = settings()
    envelope, messages = _context(settings=selected)
    original = copy.deepcopy(messages)
    updated, rebound = rebind_policy_budget(
        envelope,
        messages,
        settings=selected.model_copy(update={"mimi_operating_policy_revision": 9}),
    )
    assert updated.manifest.budget.operating_policy_revision == 9
    assert rebound[:-2] == original[:-2] and rebound[-1] == original[-1]
    assert rebound[-2] != original[-2] and messages == original
    assert updated.pending_state == envelope.pending_state
    assert updated.domain_evidence == envelope.domain_evidence


def test_metadata_hard_expiry_and_cold_timeout_are_finite(monkeypatch):
    from app.agent import route_pool

    async def scenario():
        selected = settings()
        payload = catalog()
        proof = certificate(selected, payload)
        selected = selected.model_copy(
            update={"mimi_route_qualifications_json": json.dumps([proof])}
        )
        cache = CatalogCache()
        cache.entries[selected.mimi_route_model] = (payload, time.time() - 7201)

        async def fail(request):
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(NoEligibleEndpoint):
                await cache.refresh(selected, client=client)
        monkeypatch.setattr(route_pool, "CATALOG_TIMEOUT_SECONDS", 0.02)

        async def stalled(request):
            await asyncio.sleep(1)
            return httpx.Response(200, json=payload)

        cold = CatalogCache()
        async with httpx.AsyncClient(transport=httpx.MockTransport(stalled)) as client:
            started = time.monotonic()
            with pytest.raises(NoEligibleEndpoint):
                await cold.refresh(selected, client=client)
            assert time.monotonic() - started < 0.3
            await asyncio.gather(*cold.inflight.values(), return_exceptions=True)
            assert not cold.entries

    asyncio.run(scenario())


def test_current_policy_does_not_call_local_provider_admission(monkeypatch):
    from app.agent import config_policy, route_pool

    async def scenario():
        selected = settings(mimi_route_mode="adaptive")

        async def read(*args, **kwargs):
            return bootstrap_policy(selected)

        async def empty(*args, **kwargs):
            raise NoEligibleEndpoint("no_eligible_qualified_endpoint")

        monkeypatch.setattr(config_policy, "read_policy", read)
        monkeypatch.setattr(route_pool, "bind_pool", empty)
        result = await config_policy.bind_wire_policy(None, selected)
        assert (
            result.mimi_route_max_input_price
            == bootstrap_policy(selected).prices[selected.mimi_route_model].prompt
        )

    asyncio.run(scenario())
