"""Synthetic HTTP contract tests for the local OpenAI SDK candidate transport."""

import asyncio
import json
from typing import Any

import httpx
import httpx2
import pytest

from app.agent.context import AGENT_RESPONSE_FORMAT, AssistantText, Clarification
from app.agent.openai_sdk import _timeout
from app.agent.openrouter import (
    AgentCompletion,
    ProviderDispatchError,
    build_request,
    complete,
    complete_stream,
    get_generation,
)
from app.core.settings import Settings


def _settings(**overrides: Any) -> Settings:
    values = {
        "app_env": "local",
        "oauth_state_secret": "test",
        "mimi_real_chat_enabled": True,
        "mimi_live_provider_enabled": True,
        "mimi_transport": "openai_sdk",
        "mimi_standard_api_key": "synthetic-no-egress",
        "mimi_route_model": "vendor/model",
        "mimi_route_provider": "provider-a",
        "mimi_route_quantization": "fp8",
        "mimi_route_forced_tool_choice": "required",
        "mimi_route_reasoning_effort": "high",
        "mimi_route_max_input_price": 0.2,
        "mimi_route_max_output_price": 0.8,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_sdk_completion_preserves_full_request_schema_provider_and_cost() -> None:
    messages = [{"role": "user", "content": "synthetic"}]
    expected = build_request(
        messages,
        _settings(),
        session_id="opaque-session",
        force_task_tool=True,
        agent_contract=True,
    )
    captured: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "completion-1",
                "object": "chat.completion",
                "created": 1,
                "model": "vendor/model",
                "provider": "provider-a-actual",
                "system_fingerprint": None,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"kind": "assistant_text", "text": "Xin chào"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 3,
                    "total_tokens": 11,
                    "cost": 0.001,
                },
            },
        )

    transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        result = await complete(
            messages,
            settings=_settings(),
            client=transport,
            session_id="opaque-session",
            agent_contract=True,
            force_task_tool=True,
        )
    finally:
        await transport.aclose()

    assert len(captured) == 1
    assert captured[0].url == "https://openrouter.ai/api/v1/chat/completions"
    assert captured[0].headers["X-OpenRouter-Metadata"] == "enabled"
    assert json.loads(captured[0].content) == expected
    assert expected["response_format"] == AGENT_RESPONSE_FORMAT
    assert expected["provider"]["only"] == ["provider-a"]
    assert expected["reasoning"] == {"effort": "high", "exclude": True}
    assert expected["usage"] == {"include": True}
    assert expected["store"] is False
    assert expected["session_id"] == "opaque-session"
    assert expected["tool_choice"] == "required"
    assert [item["function"]["name"] for item in expected["tools"]] == [
        "task.query.v1",
        "task.aggregate.v1",
        "task.inspect_batch.v1",
        "task.create_candidate.v2",
    ]
    assert isinstance(result.outcome, AssistantText)
    assert result.outcome.text == "Xin chào"
    assert result.provider == "provider-a-actual"
    assert result.usage["cost"] == 0.001


@pytest.mark.anyio
async def test_sdk_stream_buffers_text_until_strict_terminal_and_keeps_receipts() -> None:
    messages = [{"role": "user", "content": "synthetic"}]
    expected = build_request(
        messages, _settings(), stream=True, session_id="opaque-session", agent_contract=True
    )
    captured: list[httpx2.Request] = []
    events: list[tuple[str, dict[str, Any]]] = []
    chunks = [
        {
            "id": "stream-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "vendor/model",
            "provider": "provider-a-actual",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": json.dumps(
                            {"kind": "clarification", "text": "Bạn muốn ngày nào?"},
                            ensure_ascii=False,
                        )
                    },
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": "stream-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "vendor/model",
            "provider": "provider-a-actual",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        {
            "id": "stream-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "vendor/model",
            "provider": "provider-a-actual",
            "choices": [],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 4,
                "total_tokens": 12,
                "cost": 0.002,
            },
        },
    ]
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    body += "data: [DONE]\n\n"

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async def sink(kind: str, payload: dict[str, Any]) -> None:
        events.append((kind, payload))

    transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        result = await complete_stream(
            messages,
            settings=_settings(),
            client=transport,
            session_id="opaque-session",
            agent_contract=True,
            on_event=sink,
        )
    finally:
        await transport.aclose()

    assert len(captured) == 1
    assert json.loads(captured[0].content) == expected
    assert expected["response_format"] == AGENT_RESPONSE_FORMAT
    assert expected["stream_options"] == {"include_usage": True}
    assert isinstance(result.outcome, Clarification)
    assert result.outcome.question == "Bạn muốn ngày nào?"
    assert result.provider == "provider-a-actual"
    assert result.usage["cost"] == 0.002
    assert [kind for kind, _ in events] == [
        "provider.connected",
        "provider.response_identity",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "outcome", "streaming"),
    [
        (429, "retryable", False),
        (500, "unknown", False),
        (429, "retryable", True),
        (500, "unknown", True),
    ],
)
async def test_sdk_status_errors_are_counted_once(
    status: int, outcome: str, streaming: bool
) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(status, json={"error": {"message": "synthetic"}})

    transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises(ProviderDispatchError) as raised:
            dispatch = complete_stream if streaming else complete
            await dispatch(
                [{"role": "user", "content": "synthetic"}],
                settings=_settings(),
                client=transport,
            )
    finally:
        await transport.aclose()

    assert raised.value.outcome == outcome
    assert raised.value.status == status
    assert calls == 1


@pytest.mark.anyio
async def test_sdk_provider_error_text_never_enters_diagnostic_or_persistable_result() -> None:
    private_markers = [
        "COPIED_USER_SENTENCE_078",
        "Bearer ordinary-looking-secret",
        "ghp_unprefixedcredentialexample",
        "person@example.invalid",
        "identifying-text-078",
    ]
    body = {
        "error": {
            "message": " ".join(private_markers),
            "code": "provider-code-" + private_markers[2],
            "type": "provider-type-" + private_markers[3],
            "param": "provider-param-" + private_markers[4],
        }
    }
    transport = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(400, json=body))
    )
    try:
        with pytest.raises(ProviderDispatchError) as raised:
            await complete(
                [{"role": "user", "content": private_markers[0]}],
                settings=_settings(),
                client=transport,
            )
    finally:
        await transport.aclose()

    persisted_result = json.dumps(
        {"status": raised.value.status, "diagnostic": raised.value.diagnostic}
    )
    assert raised.value.outcome == "failed"
    assert raised.value.status == 400
    assert raised.value.diagnostic == {"category": "provider_rejected"}
    assert all(marker not in persisted_result for marker in private_markers)


@pytest.mark.anyio
async def test_sdk_summary_dispatch_omits_tools_and_tool_choice() -> None:
    captured: list[dict[str, Any]] = []
    candidate = {"summary": "ok", "constraints": [], "supersessions": [], "resolutions": []}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "summary-1",
                "object": "chat.completion",
                "created": 1,
                "model": "vendor/model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(candidate)},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

    transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        result = await complete(
            [{"role": "system", "content": "summary"}],
            settings=_settings(),
            client=transport,
            summary_mode=True,
        )
    finally:
        await transport.aclose()

    assert isinstance(result, AgentCompletion)
    assert len(captured) == 1
    assert "tools" not in captured[0]
    assert "tool_choice" not in captured[0]
    assert captured[0]["response_format"]["json_schema"]["strict"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("streaming", [False, True])
async def test_sdk_timeout_is_unknown_and_counted_once(streaming: bool) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        raise httpx2.ReadTimeout("synthetic timeout", request=request)

    transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises(ProviderDispatchError) as raised:
            dispatch = complete_stream if streaming else complete
            await dispatch(
                [{"role": "user", "content": "synthetic"}],
                settings=_settings(),
                client=transport,
            )
    finally:
        await transport.aclose()

    assert raised.value.outcome == "unknown"
    assert calls == 1


@pytest.mark.anyio
async def test_sdk_stream_cancellation_is_unknown_single_dispatch_and_closes_stream() -> None:
    entered = asyncio.Event()
    closed = asyncio.Event()
    calls = 0
    first = {
        "id": "cancelled-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "vendor/model",
        "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}],
    }

    class HangingStream(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield f"data: {json.dumps(first)}\n\n".encode()
            entered.set()
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            closed.set()

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(
            200,
            stream=HangingStream(),
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    task = asyncio.create_task(
        complete_stream(
            [{"role": "user", "content": "synthetic"}],
            settings=_settings(),
            client=transport,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(ProviderDispatchError) as raised:
            await task
    finally:
        await transport.aclose()

    assert raised.value.outcome == "unknown"
    assert raised.value.response_id == "cancelled-stream"
    assert calls == 1
    assert closed.is_set()


def test_sdk_transport_is_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="local-candidate-only"):
        Settings(mimi_transport="openai_sdk")


@pytest.mark.anyio
async def test_sdk_stream_timeout_preserves_generation_for_reconcile() -> None:
    first = {
        "id": "known-before-timeout",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "vendor/model",
        "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}],
    }
    calls = 0

    class InterruptedStream(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield f"data: {json.dumps(first)}\n\n".encode()
            raise httpx2.ReadTimeout("synthetic stream timeout")

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx2.Response(
            200, stream=InterruptedStream(), headers={"content-type": "text/event-stream"}
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ProviderDispatchError) as raised:
            await complete_stream(
                [{"role": "user", "content": "synthetic"}], settings=_settings(), client=client
            )
    assert raised.value.outcome == "unknown"
    assert raised.value.response_id == "known-before-timeout"
    assert calls == 1


def test_sdk_timeout_is_bounded_and_uses_ten_second_connect_timeout() -> None:
    timeout = _timeout(_settings(mimi_run_deadline_seconds=7_200))

    assert timeout.connect == 10.0
    assert timeout.read == 120.0
    assert timeout.write == 120.0
    assert timeout.pool == 120.0


@pytest.mark.anyio
async def test_generation_metadata_stays_on_canonical_httpx_path() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={"data": {"id": "generation-1", "provider_name": "provider-a"}},
        )

    transport = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        metadata = await get_generation("generation-1", settings=_settings(), client=transport)
    finally:
        await transport.aclose()

    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/api/v1/generation"
    assert metadata == {"id": "generation-1", "provider_name": "provider-a"}


@pytest.mark.anyio
async def test_agent_text_waits_for_app_delivery_and_rejected_wire_keeps_safe_receipt():
    events = []

    async def sink(kind, payload):
        events.append(kind)

    def response(content):
        chunk = {
            "id": "known-terminal",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "vendor/model",
            "provider": "provider-a",
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": "stop"}],
        }
        return httpx2.Response(
            200,
            text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: response(json.dumps({"kind": "assistant_text", "text": "Xin chào"}))
        )
    ) as c:
        result = await complete_stream(
            [{"role": "user", "content": "synthetic"}],
            settings=_settings(),
            client=c,
            agent_contract=True,
            on_event=sink,
        )
    assert result.outcome.text == "Xin chào"
    assert "assistant.delta" not in events
    from app.agent.openrouter import RouteContractError

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda request: response(json.dumps({"kind": "invented_authority", "text": "bad"}))
        )
    ) as c:
        with pytest.raises(RouteContractError) as rejected:
            await complete_stream(
                [{"role": "user", "content": "synthetic"}],
                settings=_settings(),
                client=c,
                agent_contract=True,
            )
    receipt = rejected.value.terminal_receipt
    assert receipt["id"] == "known-terminal"
    assert set(receipt) == {"id", "provider", "model", "usage", "choices"}
    assert "reasoning" not in receipt["choices"][0]["message"]
