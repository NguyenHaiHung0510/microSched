"""Real SDK JSON/SSE serialization with synthetic terminals; zero network egress."""

import asyncio
import copy
import json

import httpx2
import pytest
from test_mimi_openai_sdk import _settings
from test_mimi_owner296 import assert_collection_wire_schema, call, collection, payload, single

from app.agent import openai_sdk
from app.agent.openrouter import CandidateContractError
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL


def response(wire, calls, *, sequence=1, cost=0.001):
    result = payload(calls)
    result.update(
        id=f"synthetic-native-{sequence}",
        model=wire["model"],
        provider="DeepInfra",
        object="chat.completion",
        created=1,
    )
    result["usage"].update(cost=cost, prompt_tokens=800, completion_tokens=100, total_tokens=900)
    if not wire["stream"]:
        return httpx2.Response(200, json=result)
    # Split arguments across native stream fragments, retain usable terminal and usage.
    chunks = []
    for index, native in enumerate(calls):
        args = native["function"]["arguments"]
        for part in range(2):
            fragment = {
                "index": index,
                "function": {
                    "arguments": args[: len(args) // 2] if part == 0 else args[len(args) // 2 :]
                },
            }
            if part == 0:
                fragment.update(id=f"call-{index}", type="function")
                fragment["function"]["name"] = native["function"]["name"]
            chunks.append(
                {
                    **{k: result[k] for k in ("id", "model", "provider", "created")},
                    "object": "chat.completion.chunk",
                    "choices": [
                        {"index": 0, "delta": {"tool_calls": [fragment]}, "finish_reason": None}
                    ],
                }
            )
    chunks.append(
        {
            **{k: result[k] for k in ("id", "model", "provider", "created", "usage")},
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        }
    )
    body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_native_sdk_full_single_or_collection_terminal(streaming, count):
    async def scenario():
        expected = single() if count == 0 else collection(count)
        name = CREATE_CANDIDATE_TOOL if count == 0 else COLLECTION_CANDIDATE_TOOL
        wires = []

        async def handler(request):
            wire = json.loads(request.content)
            wires.append(wire)
            assert_collection_wire_schema(wire)
            assert wire["provider"]["zdr"] and wire["provider"]["data_collection"] == "deny"
            return response(wire, [call(name, expected)])

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            fn = openai_sdk.complete_stream if streaming else openai_sdk.complete
            result = await fn(
                [{"role": "user", "content": "synthetic create"}],
                settings=_settings(mimi_route_mode="native"),
                client=client,
                agent_contract=True,
            )
        assert len(wires) == 1 and result.usage["cost"] == 0.001
        if count:
            assert len(result.outcome.arguments["entries"]) == count
        else:
            assert result.outcome.arguments["title"] == expected["task"]["title"]

    asyncio.run(scenario())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("failure", ["mixed", "schema"])
def test_sdk_rejection_keeps_attempt_usage_and_never_delivers_partial(streaming, failure):
    async def scenario():
        calls = [call(COLLECTION_CANDIDATE_TOOL, collection(2)), call("task.query.v1", {})]
        if failure == "schema":
            args = copy.deepcopy(collection(2))
            args["entries"][1]["fields"].pop("due_at")
            calls = [call(COLLECTION_CANDIDATE_TOOL, args)]
        wires = []

        async def handler(request):
            wire = json.loads(request.content)
            wires.append(wire)
            return response(wire, calls)

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            fn = openai_sdk.complete_stream if streaming else openai_sdk.complete
            with pytest.raises(CandidateContractError) as raised:
                await fn(
                    [{"role": "user", "content": "synthetic create"}],
                    settings=_settings(mimi_route_mode="native"),
                    client=client,
                    agent_contract=True,
                )
        assert len(wires) == 1 and raised.value.correction_ready is False
        assert raised.value.terminal_receipt["usage"]["cost"] == 0.001
        assert raised.value.terminal_receipt["id"] == "synthetic-native-1"

    asyncio.run(scenario())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("privacy", [False, True])
def test_sdk_collection_privacy_field_remains_fatal_and_accounted(streaming, privacy):
    from app.agent.openrouter import RouteContractError

    async def scenario():
        args = collection(2)
        args["entries"][1]["fields"]["is_private"] = privacy
        wires = []

        async def handler(request):
            wire = json.loads(request.content)
            wires.append(wire)
            assert_collection_wire_schema(wire)
            return response(wire, [call(COLLECTION_CANDIDATE_TOOL, args)])

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            fn = openai_sdk.complete_stream if streaming else openai_sdk.complete
            with pytest.raises(
                RouteContractError, match="^invalid_agent_terminal_payload$"
            ) as raised:
                await fn(
                    [{"role": "user", "content": "Synthetic observed shape"}],
                    settings=_settings(mimi_route_mode="native"),
                    client=client,
                    agent_contract=True,
                )
        assert not isinstance(raised.value, CandidateContractError)
        assert len(wires) == 1
        assert raised.value.terminal_receipt["usage"]["cost"] == 0.001

    asyncio.run(scenario())
