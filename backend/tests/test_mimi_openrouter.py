"""No-network contract tests for Mimi's exact OpenRouter route."""

from uuid import uuid7

import pytest

from app.agent.openrouter import RouteContractError, build_request, parse_completion
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
    assert request["parallel_tool_calls"] is False
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
