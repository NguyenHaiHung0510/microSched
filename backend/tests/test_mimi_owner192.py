"""Author reproduction: numeric composition versus the actual SDK request bytes."""

import asyncio
import json

import httpx2
import pytest
from test_mimi_collection_contracts import settings
from test_mimi_context import _context

from app.agent import openai_sdk
from app.agent.context_builder import input_composition_observation, serialize_openrouter_messages
from app.agent.loop import finalization_messages, messages_final_only


@pytest.mark.parametrize("final_only", [False, True])
@pytest.mark.parametrize("text_format", ["structured", "natural"])
def test_composition_matches_actual_sdk_projection(final_only, text_format):
    selected = settings(mimi_text_response_format=text_format, mimi_route_max_output_tokens=8192)
    envelope, _ = _context([{"title": '🌸 escaped "synthetic" evidence'}], settings=selected)
    messages = serialize_openrouter_messages(envelope)
    if final_only:
        messages = finalization_messages(messages, "reserved_final_turn")
    captured = []

    async def handler(request):
        body = json.loads(request.content)
        captured.append(
            {key: body[key] for key in ("messages", "tools", "response_format") if key in body}
        )
        return httpx2.Response(
            200,
            json={
                "id": "synthetic-owner192-projection",
                "object": "chat.completion",
                "created": 1,
                "model": selected.mimi_route_model,
                "provider": selected.mimi_route_provider,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"kind": "assistant_text", "text": "Xin chào"}),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7, "cost": 0},
            },
        )

    async def call():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            await openai_sdk.complete(
                messages,
                settings=selected,
                client=client,
                agent_contract=True,
                final_answer_only=messages_final_only(messages),
            )

    asyncio.run(call())
    assert len(captured) == 1
    assert ("tools" not in captured[0]) is final_only
    actual_bytes = len(
        json.dumps(captured[0], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    observed = input_composition_observation(envelope, messages, settings=selected)
    assert observed["state"] == "measured_bytes"
    assert observed["total"] == actual_bytes
    assert sum(item["value"] for item in observed["categories"]) == actual_bytes
    assert observed["provider_framing_tokens"] is None


def test_price_only_revision_keeps_past_usage_but_new_wire_caps_and_material_epoch_change():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.agent.observations import context_revision, prompt_observation
    from app.agent.openrouter import build_request

    prior = settings(mimi_operating_policy_revision=1)
    revised = prior.model_copy(
        update={
            "mimi_operating_policy_revision": 2,
            "mimi_route_max_input_price": 1.5,
            "mimi_input_codepoints": 60000,
        }
    )
    epoch = context_revision(prior, 1, None)
    call = SimpleNamespace(
        id=uuid4(),
        state="succeeded",
        usage={"prompt_tokens": 280000},
        route={
            "kind": "openrouter",
            "purpose": "main",
            "context_revision": epoch,
            "model": prior.mimi_route_model,
            "actual_model": prior.mimi_route_model,
            "actual_provider": prior.mimi_route_provider,
            "providers": [prior.mimi_route_provider],
        },
    )
    assert context_revision(revised, 1, None) == epoch
    assert prompt_observation(call, context_revision(revised, 1, None))["should_compact"] is True
    wire = build_request([{"role": "user", "content": "synthetic"}], settings=revised)
    assert wire["provider"]["max_price"]["prompt"] == 1.5
    changed = revised.model_copy(update={"mimi_route_reasoning_effort": "max"})
    assert context_revision(changed, 1, None) != epoch
    assert prompt_observation(call, context_revision(changed, 1, None))["eligible"] is False
