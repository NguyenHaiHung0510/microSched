import asyncio
import json

import httpx2
import pytest

from app.agent.openai_sdk import complete
from app.agent.openrouter import ProviderDispatchError, RouteContractError
from app.core.settings import Settings


@pytest.mark.parametrize("finish", ["length", "content_filter", "error", None])
@pytest.mark.parametrize("summary", [False, True])
def test_json_rejected_terminal_preserves_only_metadata(finish, summary):
    async def run():
        settings = Settings(
            _env_file=None,
            app_env="local",
            oauth_state_secret="synthetic",
            mimi_standard_api_key="synthetic",
            mimi_route_model="vendor/model",
            mimi_route_provider="mock",
            mimi_route_quantization="fp8",
            mimi_route_max_input_price=0.2,
            mimi_route_max_output_price=0.6,
            mimi_text_response_format="natural",
        )
        payload = {
            "id": "synthetic-rejected",
            "model": "vendor/model",
            "provider": "Mock",
            "object": "chat.completion",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "summary": "valid synthetic summary",
                                "constraints": [],
                                "supersessions": [],
                                "resolutions": [],
                            }
                        )
                        if summary
                        else "SECRET_PARTIAL",
                    },
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.001},
        }
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=payload))
        ) as client:
            with pytest.raises((RouteContractError, ProviderDispatchError)) as raised:
                await complete(
                    [],
                    settings=settings,
                    client=client,
                    agent_contract=not summary,
                    summary_mode=summary,
                )
        receipt = raised.value.terminal_receipt
        assert receipt["usage"]["cost"] == 0.001 and "SECRET_PARTIAL" not in repr(receipt)
        assert "message" not in receipt and "content" not in receipt
        if finish is None:
            assert raised.value.outcome == "unknown"

    asyncio.run(run())
