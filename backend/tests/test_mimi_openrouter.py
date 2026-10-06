"""No-network contract tests for Mimi's exact OpenRouter route."""

import json
from uuid import uuid7

import httpx
import pytest

from app.agent.openrouter import (
    ProviderDispatchError,
    RouteContractError,
    _raise_for_status,
    build_request,
    complete_stream,
    get_generation,
    parse_completion,
    serialized_input_bytes,
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
        "mimi_route_forced_tool_choice": "required",
        "mimi_route_max_input_price": 0.2,
        "mimi_route_max_output_price": 0.8,
    }
    values.update(overrides)
    return Settings(**values)


def test_gateway_5xx_is_unknown_not_safe_to_retry() -> None:
    with pytest.raises(ProviderDispatchError) as raised:
        _raise_for_status(500)
    assert raised.value.outcome == "unknown"
    with pytest.raises(ProviderDispatchError) as throttled:
        _raise_for_status(429)
    assert throttled.value.outcome == "retryable"


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


def test_unknown_exact_quantization_keeps_provider_pin_without_claiming_precision() -> None:
    request = build_request(
        [{"role": "user", "content": "hello"}],
        _settings(mimi_route_quantization="unknown"),
    )
    assert request["provider"]["only"] == ["provider-a"]
    assert request["provider"]["order"] == ["provider-a"]
    assert request["provider"]["allow_fallbacks"] is False
    assert "quantizations" not in request["provider"]


def test_default_reasoning_effort_omits_effort_but_keeps_reasoning_excluded() -> None:
    request = build_request(
        [{"role": "user", "content": "hello"}],
        _settings(mimi_route_reasoning_effort="default"),
    )
    assert request["reasoning"] == {"exclude": True}


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


def test_explicit_preview_revision_can_require_the_task_tool() -> None:
    request = build_request(
        [{"role": "user", "content": "Sửa preview"}],
        _settings(),
        force_task_tool=True,
    )
    assert request["tool_choice"] == "required"
    assert [tool["function"]["name"] for tool in request["tools"]] == ["task.create.v1"]


def test_unqualified_route_rejects_forced_tool_before_dispatch() -> None:
    settings = _settings(mimi_route_forced_tool_choice="none")
    with pytest.raises(RouteContractError, match="route_forced_tool_choice_not_qualified"):
        build_request(
            [{"role": "user", "content": "Sửa preview"}],
            settings,
            force_task_tool=True,
        )


def test_function_qualified_route_uses_named_tool_choice() -> None:
    request = build_request(
        [{"role": "user", "content": "Sửa preview"}],
        _settings(mimi_route_forced_tool_choice="function"),
        force_task_tool=True,
    )
    assert request["tool_choice"] == {
        "type": "function",
        "function": {"name": "task.create.v1"},
    }


def test_preflight_refuses_overflow_instead_of_truncating() -> None:
    settings = _settings(
        mimi_route_context_tokens=16_384,
        mimi_route_max_output_tokens=4_096,
    )
    request = build_request([{"role": "user", "content": "x" * 13_000}], settings)
    assert len(request["messages"][0]["content"]) == 13_000


def test_selected_32k_request_checks_policy_tools_current_pending_checkpoint_suffix_and_reserve():
    settings = _settings(mimi_route_context_tokens=32_000, mimi_route_max_output_tokens=8_192)
    oversized = [
        {"role": "system", "content": "FIXED_POLICY_AND_CAPABILITIES " + "p" * 13_000},
        {"role": "user", "content": "OLD_HISTORY " + "h" * 12_000},
        {"role": "assistant", "content": "OLD_REPLY " + "r" * 8_000},
    ]
    request = build_request(oversized, settings, agent_contract=True)
    assert request["messages"] == oversized

    compacted = [
        {"role": "system", "content": "FIXED_POLICY_AND_CAPABILITIES " + "p" * 6_000},
        {"role": "system", "content": "checkpoint + active constraint citations " + "c" * 2_000},
        {"role": "assistant", "content": "retained transcript suffix " + "s" * 1_500},
        {"role": "system", "content": "exact server pending preview object " + "d" * 1_000},
        {"role": "user", "content": "current user input " + "u" * 1_000},
    ]
    request = build_request(compacted, settings, agent_contract=True)
    serialized = serialized_input_bytes(compacted, agent_contract=True)
    assert serialized + request["max_tokens"] <= 32_000
    assert request["tools"] and request["response_format"]


def test_summary_mode_has_strict_summary_schema_and_no_function_tools_or_choice():
    settings = _settings(mimi_route_context_tokens=32_000, mimi_route_max_output_tokens=2_048)
    messages = [
        {"role": "system", "content": "compact safely"},
        {"role": "user", "content": "synthetic source"},
    ]
    request = build_request(messages, settings, summary_mode=True)
    assert "tools" not in request
    assert "tool_choice" not in request
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["max_tokens"] == 2_048
    assert (
        serialized_input_bytes(messages, agent_contract=False, summary_mode=True) + 2_048 <= 32_000
    )


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


def test_terminal_tool_validation_reports_only_safe_field_and_type() -> None:
    with pytest.raises(
        RouteContractError,
        match=r"provider_task_schema_invalid_id_uuid_parsing",
    ):
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
                                            "id": "not-a-uuid",
                                            "title": "secret title must not enter the error",
                                        },
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )


def test_terminal_tool_server_owns_open_status() -> None:
    task_id = uuid7()
    completion = parse_completion(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "task.create.v1",
                                    "arguments": {
                                        "id": str(task_id),
                                        "title": "Task STANDARD",
                                        "status": "pending",
                                        "is_private": False,
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )
    assert completion.task is not None
    assert completion.task.status == "open"


def test_terminal_tool_canonicalizes_schedule_sibling_from_precision() -> None:
    task_id = uuid7()
    completion = parse_completion(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "task.create.v1",
                                    "arguments": {
                                        "id": str(task_id),
                                        "title": "Task có giờ",
                                        "due_precision": "datetime",
                                        "due_on": "2026-09-20",
                                        "due_at": "2026-09-20T21:00:00+07:00",
                                        "is_private": False,
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )
    assert completion.task is not None
    assert completion.task.due_on is None
    assert completion.task.due_at is not None


def test_terminal_text_is_valid_and_single_tool_wins_over_narration() -> None:
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
    task_id = uuid7()
    mixed = parse_completion(
        {
            "choices": [
                {
                    "message": {
                        "content": "Mình sẽ tạo task.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "task.create.v1",
                                    "arguments": {
                                        "id": str(task_id),
                                        "title": "Task có preview",
                                        "is_private": False,
                                    },
                                }
                            }
                        ],
                    }
                }
            ]
        }
    )
    assert mixed.kind == "task"
    assert mixed.text is None
    assert mixed.task is not None
    assert mixed.task.title == "Task có preview"


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
        ("provider.response_identity", {"response_id": "generation-stream"}),
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
        metadata = await get_generation("generation-stream", settings=_settings(), client=client)
    assert metadata == {
        "id": "generation-stream",
        "provider_name": "provider-a",
        "total_cost": 0.001,
    }


@pytest.mark.anyio
@pytest.mark.parametrize("transport_error", [httpx.ReadError, httpx.RemoteProtocolError])
async def test_generation_reconciliation_transport_failure_is_unknown_without_retry(
    transport_error: type[httpx.TransportError],
) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise transport_error("synthetic metadata transport failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderDispatchError) as raised:
            await get_generation("generation-stream", settings=_settings(), client=client)

    assert raised.value.outcome == "unknown"
    assert raised.value.response_id == "generation-stream"
    assert requests == 1


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


def test_native_chat_keeps_tool_and_privacy_contract_without_forcing_text_json():
    settings = _settings(mimi_text_response_format="natural")
    request = build_request(
        [{"role": "user", "content": "Đếm công việc"}], settings, agent_contract=True
    )
    assert "response_format" not in request
    assert request["tools"]
    assert request["tool_choice"] == "auto"
    assert request["provider"]["require_parameters"] is True
    assert request["provider"]["data_collection"] == "deny"
    assert request["store"] is False


def test_native_chat_option_is_supported_in_production():
    assert Settings(_env_file=None, mimi_text_response_format="natural").is_production
