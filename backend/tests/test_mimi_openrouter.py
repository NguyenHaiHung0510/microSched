"""No-network contract tests for Mimi's exact OpenRouter route."""

import json
from uuid import uuid7

import httpx
import pytest

from app.agent.openrouter import (
    RouteContractError,
    build_request,
    complete_stream,
    get_generation,
    parse_completion,
)
from app.core.settings import Settings


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "local",
        "oauth_state_secret": "test",
        "mimi_real_chat_enabled": True,
        "mimi_live_provider_enabled": True,
        "mimi_standard_api_key": "test-not-a-real-key",
        "mimi_route_model": "vendor/model",
        "mimi_route_provider": "provider-a",
        "mimi_route_quantization": "fp8",
        "mimi_route_max_input_price": 0.2,
        "mimi_route_max_output_price": 0.8,
    }
    values.update(overrides)
    return Settings(**values)


def test_request_pins_provider_quantization_parameters_zdr_and_price() -> None:
    request = build_request([{"role": "user", "content": "Tạo task"}], _settings())
    assert request["model"] == "vendor/model"
    assert request["store"] is False
    assert request["tool_choice"] == "auto"
    assert "parallel_tool_calls" not in request
    assert request["provider"] == {
        "order": ["provider-a"],
        "only": ["provider-a"],
        "quantizations": ["fp8"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
        "max_price": {"prompt": 0.2, "completion": 0.8},
    }


def test_adaptive_request_has_bounded_pool_without_manual_order() -> None:
    settings = _settings(
        mimi_route_mode="adaptive",
        mimi_route_provider=None,
        mimi_route_quantization=None,
        mimi_route_allowed_providers="provider-a, provider-b",
        mimi_route_allowed_quantizations="fp8, bf16",
    )
    request = build_request(
        [{"role": "user", "content": "hello"}],
        settings,
        stream=True,
        session_id="opaque-session",
    )
    assert request["session_id"] == "opaque-session"
    assert request["stream_options"] == {"include_usage": True}
    assert request["provider"] == {
        "only": ["provider-a", "provider-b"],
        "quantizations": ["fp8", "bf16"],
        "allow_fallbacks": True,
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
        "max_price": {"prompt": 0.2, "completion": 0.8},
    }
    assert "order" not in request["provider"]
    assert "sort" not in request["provider"]


def test_preflight_refuses_overflow_instead_of_truncating() -> None:
    settings = _settings(
        mimi_route_context_tokens=16_384,
        mimi_route_max_output_tokens=4_096,
    )
    with pytest.raises(RouteContractError, match="context_overflow_preflight"):
        build_request([{"role": "user", "content": "x" * 13_000}], settings)


def test_terminal_tool_args_are_independently_validated() -> None:
    task_id = uuid7()
    completion = parse_completion(
        {
            "id": "generation-1",
            "provider": "provider-a",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "task.create.v1",
                                    "arguments": {
                                        "id": str(task_id),
                                        "title": "Task hợp lệ",
                                        "body_md": None,
                                        "status": "open",
                                        "priority": None,
                                        "due_precision": "none",
                                        "due_on": None,
                                        "due_at": None,
                                        "is_private": False,
                                        "items": [],
                                    },
                                }
                            }
                        ]
                    }
                }
            ],
        }
    )
    assert completion.task.id == task_id
    assert completion.provider == "provider-a"
    assert completion.kind == "task"


def test_terminal_text_is_valid_but_mixed_text_and_tool_is_rejected() -> None:
    completion = parse_completion(
        {
            "id": "generation-text",
            "model": "vendor/model",
            "choices": [{"message": {"content": "Xin chào!", "tool_calls": []}}],
        }
    )
    assert completion.kind == "text"
    assert completion.text == "Xin chào!"
    assert completion.task is None
    with pytest.raises(RouteContractError, match="text_xor_tool"):
        parse_completion(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Mình sẽ tạo task.",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "task.create.v1",
                                        "arguments": {},
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        )


@pytest.mark.anyio
async def test_stream_normalizes_text_deltas_and_usage() -> None:
    observed: list[tuple[str, dict]] = []

    async def sink(kind: str, payload: dict) -> None:
        observed.append((kind, payload))

    chunks = [
        {
            "id": "generation-stream",
            "model": "vendor/model",
            "provider": "provider-a",
            "choices": [{"delta": {"content": "Xin "}}],
        },
        {
            "id": "generation-stream",
            "model": "vendor/model",
            "provider": "provider-a",
            "choices": [{"delta": {"content": "chào"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 2},
        },
    ]
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert sent["stream"] is True
        assert sent["session_id"] == "opaque-session"
        return httpx.Response(200, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        completion = await complete_stream(
            [{"role": "user", "content": "hello"}],
            settings=_settings(),
            client=client,
            session_id="opaque-session",
            on_event=sink,
        )
    assert completion.kind == "text"
    assert completion.text == "Xin chào"
    assert completion.provider == "provider-a"
    assert completion.usage["prompt_tokens"] == 8
    assert completion.usage["completion_tokens"] == 2
    assert completion.usage["mimi_timing"]["duration_ms"] >= 0
    assert completion.usage["mimi_timing"]["ttft_ms"] is not None
    assert completion.usage["mimi_timing"]["output_tokens_per_second"] > 0
    assert observed == [
        ("provider.connected", {"status": 200}),
        ("assistant.delta", {"text": "Xin "}),
        ("assistant.delta", {"text": "chào"}),
    ]


@pytest.mark.anyio
async def test_generation_reconciliation_reads_only_canonical_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["id"] == "generation-stream"
        assert request.headers["Authorization"] == "Bearer test-not-a-real-key"
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "generation-stream",
                    "provider_name": "provider-a",
                    "total_cost": 0.001,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        metadata = await get_generation(
            "generation-stream", settings=_settings(), client=client
        )
    assert metadata == {
        "id": "generation-stream",
        "provider_name": "provider-a",
        "total_cost": 0.001,
    }


def test_terminal_payload_cannot_cross_standard_private_boundary() -> None:
    with pytest.raises(RouteContractError):
        parse_completion(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "task.create.v1",
                                        "arguments": {
                                            "id": str(uuid7()),
                                            "title": "X",
                                            "is_private": True,
                                        },
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )
