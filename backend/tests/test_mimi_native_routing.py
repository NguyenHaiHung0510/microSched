"""Native routing policy and bounded gateway recovery; no provider traffic."""

import asyncio
import json

import httpx2
import pytest

from app.agent.openrouter import ProviderDispatchError, build_request, complete, complete_stream
from app.agent.route_config import bind_configuration
from app.core.settings import Settings


def settings(**overrides):
    return Settings(
        _env_file=None,
        **{
            "app_env": "local",
            "mimi_standard_api_key": "synthetic-never-sent",
            "mimi_route_model": "deepseek/deepseek-v4.1-flash",
            "mimi_route_mode": "native",
            "mimi_route_allowed_quantizations": "fp8",
            "mimi_route_max_input_price": "0.36",
            "mimi_route_max_output_price": "1.44",
            "mimi_transport": "openai_sdk",
            **overrides,
        },
    )


def terminal():
    return {
        "id": "gen-synthetic",
        "model": "deepseek/deepseek-v4.1-flash",
        "provider": "New Provider / Region",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Xin chào",
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12, "cost": 0.00001},
    }


def test_native_policy_has_no_local_provider_admission():
    for collection in (True, False):
        selected = bind_configuration(
            settings(mimi_collection_enabled=collection),
            {
                "profile_id": "deepseek",
                "effort": "high",
                "input_tokens": 272000,
                "routing_mode": "exact",  # old saved choice cannot restore a provider pin
            },
        )
        assert selected.mimi_route_mode == "native"
        policy = build_request([{"role": "user", "content": "Chào"}], selected)["provider"]
        assert policy == {
            "require_parameters": True,
            "allow_fallbacks": True,
            "data_collection": "deny",
            "zdr": True,
            "quantizations": ["fp8"],
            "max_price": {"prompt": 0.36, "completion": 1.44},
        }


@pytest.mark.parametrize("stream", [False, True])
def test_gateway_connect_retries_are_bounded_and_visible(monkeypatch, stream):
    calls = []
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    async def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) < 3:
            raise httpx2.ConnectError("synthetic connect failure", request=request)
        if stream:
            payload = terminal()
            payload["choices"][0]["delta"] = payload["choices"][0].pop("message")
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n",
            )
        return httpx2.Response(200, json=terminal())

    monkeypatch.setattr("app.agent.gateway_retry.asyncio.sleep", sleep)
    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            fn = complete_stream if stream else complete
            return await fn(
                [{"role": "user", "content": "Chào"}],
                settings=settings(),
                client=client,
                session_id="stable-conversation",
            )

    result = asyncio.run(run())
    assert len(calls) == 3
    assert 1 <= sleeps[0] <= 1.25 and 2 <= sleeps[1] <= 2.25
    assert calls[0] == calls[1] == calls[2]
    assert result.provider == "New Provider / Region"
    assert len(result.dispatch_attempts) == 3
    assert result.dispatch_attempts[0]["outcome"] == "retryable"
    assert result.dispatch_attempts[-1]["outcome"] == "succeeded"


@pytest.mark.parametrize("status,expected", [(429, 3), (401, 1), (402, 1), (503, 1)])
def test_status_retry_policy_and_retry_after(monkeypatch, status, expected):
    calls = 0
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(
            status,
            headers={"retry-after": "4"},
            json={"error": {"message": "must not persist private prose"}},
        )

    monkeypatch.setattr("app.agent.gateway_retry.asyncio.sleep", sleep)
    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError) as caught:
                await complete(
                    [{"role": "user", "content": "Chào"}], settings=settings(), client=client
                )
            return caught.value

    error = asyncio.run(run())
    assert calls == expected
    assert sleeps == ([4, 4] if expected == 3 else [])
    assert len(error.dispatch_attempts) == expected
    assert "private prose" not in repr(error.diagnostic)


def test_ambiguous_read_failure_and_private_budget_never_replay(monkeypatch):
    async def run(error_type):
        calls = 0

        async def handler(request):
            nonlocal calls
            calls += 1
            raise error_type("synthetic", request=request)

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError):
                await complete(
                    [{"role": "user", "content": "Chào"}], settings=settings(), client=client
                )
        assert calls == 1

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    asyncio.run(run(httpx2.ReadTimeout))
    # The application's private paid-QA reservation covers one attempt. Do not
    # silently multiply it or write an invented zero fee for a rejected call.
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", "synthetic-not-opened")
    asyncio.run(run(httpx2.ConnectError))


@pytest.mark.parametrize("partial", ["text", "tool", "identity"])
def test_partial_sse_error_is_unknown_and_never_replayed(monkeypatch, partial):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        delta = (
            {"content": "partial"}
            if partial == "text"
            else {"tool_calls": [{"index": 0, "function": {"arguments": "{"}}]}
            if partial == "tool"
            else {}
        )
        first = {"choices": [{"index": 0, "delta": delta}], "usage": {"cost": 0.001}}
        if partial == "identity":
            first["id"] = "gen-synthetic-partial"
        failure = {"id": "gen-synthetic-partial", "error": {"code": 429}, "usage": {"cost": 0.001}}
        data = "".join("data: " + json.dumps(frame) + "\n\n" for frame in [first, failure])
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=data)

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError) as caught:
                await complete_stream(
                    [{"role": "user", "content": "Chào"}], settings=settings(), client=client
                )
            assert caught.value.outcome == "unknown"
            assert caught.value.response_id == (
                "gen-synthetic-partial" if partial == "identity" else None
            )
            assert caught.value.terminal_receipt["usage"]["cost"] == 0.001
        assert calls == 1

    asyncio.run(run())


def test_retry_after_beyond_deadline_does_not_delay_or_dispatch(monkeypatch):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(429, headers={"retry-after": "3600"}, json={"error": {}})

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError):
                await complete(
                    [{"role": "user", "content": "Chào"}],
                    settings=settings(mimi_run_deadline_seconds=30),
                    client=client,
                )
        assert calls == 1

    asyncio.run(run())


def test_native_optional_provider_and_model_guard(monkeypatch):
    from app.agent.openrouter import RouteContractError, validate_response_identity

    payload = terminal()
    payload.pop("provider")
    validate_response_identity(payload, settings())  # metadata unavailable, not a rejected route
    payload["model"] = "other/model"
    with pytest.raises(RouteContractError):
        validate_response_identity(payload, settings())


@pytest.mark.parametrize(
    "status,metadata,expected",
    [
        (503, {"error_type": "provider_overloaded"}, 3),
        (
            402,
            {"limit_source": "openrouter_in_flight_budget", "reason": "in_flight_budget_exhausted"},
            3,
        ),
        (402, {"limit_source": "openrouter_credits", "reason": "weight_exceeds_budget"}, 1),
        (401, {"error_type": "provider_overloaded"}, 1),
    ],
)
def test_documented_transient_categories_only(monkeypatch, status, metadata, expected):
    calls = 0

    async def sleep(delay):
        pass

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(
            status, headers={"retry-after": "1"}, json={"error": {"metadata": metadata}}
        )

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    monkeypatch.setattr("app.agent.gateway_retry.asyncio.sleep", sleep)

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError):
                await complete(
                    [{"role": "user", "content": "Chào"}], settings=settings(), client=client
                )
        assert calls == expected

    asyncio.run(run())


@pytest.mark.parametrize("transport", ["httpx", "openai_sdk"])
def test_json_error_inside_http200_preserves_receipt_without_retry(monkeypatch, transport):
    import httpx

    module = httpx2 if transport == "openai_sdk" else httpx
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return module.Response(
            200,
            json={
                "id": "gen-synthetic-error",
                "usage": {"cost": 0.001},
                "error": {"code": 429, "message": "private prose"},
            },
        )

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)

    async def run():
        async with module.AsyncClient(transport=module.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError) as caught:
                await complete(
                    [{"role": "user", "content": "Chào"}],
                    settings=settings(mimi_transport=transport),
                    client=client,
                )
            assert caught.value.outcome == "unknown"
            assert caught.value.response_id == "gen-synthetic-error"
            assert caught.value.terminal_receipt["usage"]["cost"] == 0.001
            assert "private prose" not in repr(caught.value.diagnostic)
        assert calls == 1

    asyncio.run(run())
