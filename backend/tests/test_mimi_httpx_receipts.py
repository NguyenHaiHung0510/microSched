"""Observed HTTPX receipts survive refusal and interruption without replay."""

import asyncio
import json

import httpx
import pytest
from test_mimi_native_routing import settings, terminal

from app.agent.openrouter import (
    ProviderDispatchError,
    RouteContractError,
    complete,
    complete_stream,
)


@pytest.mark.parametrize("stream", [False, True])
def test_rejected_terminal_retains_observed_metadata(monkeypatch, stream):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        payload = terminal()
        payload["provider"] = "Synthetic"
        payload["choices"][0]["message"]["content"] = ""
        payload["usage"] = {"cost": 0.001, "private_prose": "never persist"}
        if stream:
            payload["choices"][0]["delta"] = payload["choices"][0].pop("message")
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(RouteContractError) as caught:
                await (complete_stream if stream else complete)(
                    [{"role": "user", "content": "synthetic"}],
                    settings=settings(mimi_transport="httpx"),
                    client=client,
                )
            error = caught.value
            assert error.response_id == "gen-synthetic"
            assert error.terminal_receipt["usage"]["cost"] == 0.001
            assert error.dispatch_attempts[0]["usage"]["cost"] == 0.001
            assert "private_prose" not in error.terminal_receipt["usage"]
            assert "never persist" not in repr(error.terminal_receipt)
        assert calls == 1

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["cancel", "read_timeout", "read_error", "connect_error"])
def test_interrupted_stream_retains_receipt_and_never_replays(monkeypatch, failure):
    async def run():
        observed = asyncio.Event()
        blocked = asyncio.Event()
        calls = 0

        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"id":"gen-observed","choices":[],"usage":{"cost":0.002}}\n\n'
                observed.set()
                if failure == "cancel":
                    await blocked.wait()
                else:
                    cls = {
                        "read_timeout": httpx.ReadTimeout,
                        "read_error": httpx.ReadError,
                        "connect_error": httpx.ConnectError,
                    }[failure]
                    raise cls("synthetic after response headers")

        async def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Stream()
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task = asyncio.create_task(
                complete_stream(
                    [{"role": "user", "content": "synthetic"}],
                    settings=settings(mimi_transport="httpx"),
                    client=client,
                )
            )
            await observed.wait()
            if failure == "cancel":
                task.cancel()
            with pytest.raises(ProviderDispatchError) as caught:
                await task
            error = caught.value
            assert error.outcome == "unknown"
            assert error.response_id == "gen-observed"
            assert error.terminal_receipt["usage"]["cost"] == 0.002
            assert error.dispatch_attempts[0]["usage"]["cost"] == 0.002
        assert calls == 1

    monkeypatch.delenv("MIMI_LOCAL_BUDGET_LEDGER", raising=False)
    asyncio.run(run())
