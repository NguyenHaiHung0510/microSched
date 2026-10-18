"""Owner247 compatibility and monetary admission, entirely synthetic/offline."""

import asyncio
import copy
import json
from decimal import Decimal

import httpx2
import pytest
from test_mimi_collection_budget import historical_budget as _historical_budget

from app.agent import local_budget as budget
from app.agent import openai_sdk
from app.agent.config_policy import OperatingPolicy, bind_policy, bootstrap_policy
from app.agent.openrouter import RouteContractError, build_request, validate_response_identity
from app.agent.route_config import PROFILES, bind_configuration, default_configuration
from app.core.settings import Settings

historical_budget = _historical_budget

OLD_MODEL = "deepseek/deepseek-v4.1-flash"
MODEL = "deepseek/deepseek-v4.1-flash-1017"


def selected(**overrides):
    base = Settings(_env_file=None, app_env="local", **overrides)
    return bind_configuration(
        base, {"profile_id": "deepseek", "effort": "high", "input_tokens": 272000}
    )


def test_profile_default_old_configuration_and_price_compatibility():
    assert PROFILES["deepseek"]["model"] == MODEL
    assert PROFILES["deepseek"]["supported_efforts"] == ["none", "low", "high", "max"]
    for model in (MODEL, OLD_MODEL):
        config = default_configuration(Settings(_env_file=None, mimi_route_model=model))
        assert config["profile_id"] == "deepseek" and config["effort"] == "high"
    base = Settings(_env_file=None, mimi_route_model=OLD_MODEL)
    old = bootstrap_policy(base).model_dump(mode="json")
    old["prices"][OLD_MODEL] = old["prices"].pop(MODEL)
    old["prices"][OLD_MODEL] = {"prompt": "0.31", "completion": "1.23"}
    frozen = copy.deepcopy(old)
    policy = OperatingPolicy.model_validate(old)
    bound = bind_configuration(
        bind_policy(base, policy),
        {"profile_id": "deepseek", "effort": "none", "input_tokens": 272000},
    )
    assert old == frozen  # reading saved prices never rewrites old receipts/settings
    assert bound.mimi_route_model == MODEL and bound.mimi_route_reasoning_effort == "none"
    assert bound.mimi_route_max_input_price == Decimal("0.31")
    assert bound.mimi_route_max_output_price == Decimal("1.23")
    assert policy.revision == frozen["revision"]
    caps = {**old["prices"], MODEL: {"prompt": "0.36", "completion": "1.44"}}
    assert OperatingPolicy.model_validate({**old, "prices": caps}).prices[MODEL].prompt == Decimal(
        ".36"
    )
    validate_response_identity({"model": MODEL, "provider": "Synthetic"}, bound)
    with pytest.raises(RouteContractError, match="identity"):
        validate_response_identity({"model": OLD_MODEL, "provider": "Synthetic"}, bound)


@pytest.mark.parametrize("summary", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_native_wire_has_provider_default_output_and_unchanged_filters(summary, stream):
    for effort in ("none", "low", "high", "max"):
        route = selected(mimi_standard_api_key="synthetic")
        route = route.model_copy(update={"mimi_route_reasoning_effort": effort})
        body = build_request(
            [{"role": "user", "content": "synthetic"}],
            route,
            summary_mode=summary,
            agent_contract=not summary,
            stream=stream,
        )
        assert "max_tokens" not in body and "max_completion_tokens" not in body
        assert body["model"] == MODEL and body["reasoning"]["effort"] == effort
        assert body["provider"] == {
            "require_parameters": True,
            "allow_fallbacks": True,
            "data_collection": "deny",
            "zdr": True,
            "quantizations": ["fp8"],
            "max_price": {"prompt": 0.36, "completion": 1.44},
        }
        legacy = route.model_copy(
            update={"mimi_route_mode": "exact", "mimi_route_provider": "synthetic"}
        )
        assert build_request([], legacy)["max_tokens"] == legacy.mimi_route_max_output_tokens


@pytest.mark.parametrize(
    "caps", [{}, {"max_paid_dispatches": None, "max_conditional_max_dispatches": None}]
)
def test_money_only_accepts_unlimited_count_history_with_full_output_reserve(
    historical_budget, caps
):
    path, ledger, _, meters = historical_budget
    ledger.update(
        budget_mode="money_only", historical_dispatch_count=155, historical_max_dispatch_count=22
    )
    ledger.pop("max_paid_dispatches")
    ledger.pop("max_conditional_max_dispatches")
    ledger.update(caps)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    route = selected().model_copy(update={"mimi_route_reasoning_effort": "max"})
    rid = budget.reserve(route, [], agent_contract=True)
    call = json.loads(path.read_text())["calls"][0]
    assert call["reservation_usd"] == str(Decimal("1.50994944"))
    assert call["output_policy"] == "provider_default"
    assert call["output_cap"] is None and call["output_billing_upper_bound"] == 1048576
    assert len(meters) == 1
    with pytest.raises(RouteContractError, match="prior_spend_unknown"):
        budget.reserve(route, [], agent_contract=True)
    budget.account(route, rid, {"cost": ".001", "completion_tokens": 9000}, "synthetic-generation")
    budget.reserve(route, [], agent_contract=True, summary_mode=True)
    actual = json.loads(path.read_text())
    assert actual["historical_reserved_usd"] == ledger["historical_reserved_usd"]
    assert actual["historical_dispatch_count"] == 155
    assert actual["historical_max_dispatch_count"] == 22
    assert len(actual["calls"]) == 2


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"budget_mode": "typo"}, "mode_invalid"),
        ({"budget_mode": "money_only", "historical_max_dispatch_count": 5}, "history_invalid"),
        ({"budget_mode": "money_only", "cap_usd": ".9"}, "exhausted"),
    ],
)
def test_invalid_or_insufficient_money_never_dispatches(historical_budget, updates, reason):
    path, ledger, _, _ = historical_budget
    ledger.update(updates)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(RouteContractError, match=reason):
        budget.reserve(selected(), [], agent_contract=True)
    assert not json.loads(path.read_text())["calls"]


@pytest.mark.parametrize("summary", [False, True])
def test_actual_sdk_json_wire_omits_generation_cap_and_accounts_usage(summary):
    route = selected(mimi_standard_api_key="synthetic")
    captured = []

    async def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        assert "max_tokens" not in body and "max_completion_tokens" not in body
        content = (
            json.dumps(
                {"summary": "synthetic", "constraints": [], "supersessions": [], "resolutions": []}
            )
            if summary
            else "synthetic"
        )
        return httpx2.Response(
            200,
            json={
                "id": "synthetic-owner247",
                "object": "chat.completion",
                "created": 1,
                "model": MODEL,
                "provider": "Synthetic",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 9000, "cost": 0.01},
            },
        )

    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            return await openai_sdk.complete(
                [{"role": "user", "content": "synthetic"}],
                settings=route,
                client=client,
                summary_mode=summary,
                agent_contract=not summary,
            )

    result = asyncio.run(run())
    assert len(captured) == 1 and result.usage["completion_tokens"] == 9000


def test_storage_preserves_legacy_key_for_binary_rollback_without_mutating_api_policy():
    from app.agent.config_policy import policy_storage_value

    policy = bootstrap_policy(Settings(_env_file=None))
    current = policy.model_dump(mode="json")
    stored = policy_storage_value(policy)
    assert MODEL not in stored["prices"] and OLD_MODEL in stored["prices"]
    assert stored["prices"][OLD_MODEL] == {"prompt": "0.36", "completion": "1.44"}
    assert OperatingPolicy.model_validate(stored) == policy
    assert policy.model_dump(mode="json") == current


@pytest.mark.parametrize("stall", [False, True])
def test_sdk_real_local_http_stream_read_idle_is_not_total_duration(monkeypatch, stall):
    """Exercise the installed SDK/HTTPX timeout, without remote or paid traffic."""
    route = selected(mimi_standard_api_key="synthetic").model_copy(
        update={"mimi_route_reasoning_effort": "max"}
    )
    monkeypatch.setattr(openai_sdk, "_timeout", lambda _: openai_sdk.Timeout(0.2, connect=0.1))
    captured = []

    async def scenario():
        import time

        from app.agent.openrouter import ProviderDispatchError

        handlers = []

        async def serve(reader, writer):
            handlers.append(asyncio.current_task())
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                captured.append(json.loads(await reader.readexactly(length)))
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                    b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
                )

                async def chunk(data):
                    writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                    await writer.drain()

                payload = {
                    "id": "synthetic-idle",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": MODEL,
                    "provider": "Synthetic",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "synthetic"},
                            "finish_reason": None,
                        }
                    ],
                }
                await chunk(("data: " + json.dumps(payload) + "\n\n").encode())
                if stall:
                    await asyncio.sleep(0.8)
                else:
                    for _ in range(6):
                        await asyncio.sleep(0.06)
                        await chunk(b": progress\n\n")
                payload["choices"][0] = {"index": 0, "delta": {}, "finish_reason": "stop"}
                payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 9000, "cost": 0.01}
                await chunk(("data: " + json.dumps(payload) + "\n\n").encode())
                await chunk(b"data: [DONE]\n\n")
                writer.write(b"0\r\n\r\n")
                await writer.drain()
            finally:
                writer.close()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(openai_sdk, "_OPENROUTER_BASE_URL", f"http://127.0.0.1:{port}/v1")
        started = time.monotonic()
        try:
            async with server:
                if stall:
                    with pytest.raises(ProviderDispatchError) as raised:
                        await openai_sdk.complete_stream([], settings=route, agent_contract=True)
                    assert raised.value.outcome == "unknown"
                    assert raised.value.response_id == "synthetic-idle"
                else:
                    result = await openai_sdk.complete_stream(
                        [], settings=route, agent_contract=True
                    )
                    assert result.usage["completion_tokens"] == 9000
                    assert time.monotonic() - started > 0.2
        finally:
            for task in handlers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*handlers, return_exceptions=True)
        assert len(captured) == 1
        assert "max_tokens" not in captured[0] and "max_completion_tokens" not in captured[0]

    asyncio.run(asyncio.wait_for(scenario(), 5))


@pytest.mark.parametrize("cost", [None, "1.6"])
def test_money_only_keeps_unknown_and_excessive_liabilities(historical_budget, cost):
    path, ledger, _, _ = historical_budget
    ledger.update(
        budget_mode="money_only", max_paid_dispatches=None, max_conditional_max_dispatches=None
    )
    path.write_text(json.dumps(ledger), encoding="utf-8")
    route = selected()
    rid = budget.reserve(route, [], agent_contract=True)
    reason = "current_spend_unknown" if cost is None else "provider_cost_exceeded_reservation"
    with pytest.raises(RouteContractError, match=reason):
        budget.account(route, rid, {} if cost is None else {"cost": cost}, "synthetic-liability")
    with pytest.raises(RouteContractError, match="prior_spend_unknown|prior_reservation_exceeded"):
        budget.reserve(route, [], agent_contract=True)
    observed = json.loads(path.read_text())
    assert len(observed["calls"]) == 1
    assert observed["calls"][0]["charged_or_reserved_usd"] == (
        "1.50994944" if cost is None else cost
    )
    assert observed["historical_reserved_usd"] == ledger["historical_reserved_usd"]


@pytest.mark.parametrize(
    "prompt_price,completion_price", [(".36", "1.44"), ("2", ".1"), ("0", "0")]
)
def test_shared_context_monetary_bound_covers_provider_variants_and_price_order(
    historical_budget, prompt_price, completion_price
):
    path, ledger, _, _ = historical_budget
    ledger.update(
        budget_mode="money_only", max_paid_dispatches=None, max_conditional_max_dispatches=None
    )
    path.write_text(json.dumps(ledger), encoding="utf-8")
    route = selected().model_copy(
        update={
            "mimi_route_max_input_price": Decimal(prompt_price),
            "mimi_route_max_output_price": Decimal(completion_price),
        }
    )
    budget.reserve(route, [], agent_contract=True)
    call = json.loads(path.read_text())["calls"][0]
    window = 1048576
    reserve = Decimal(call["reservation_usd"])
    assert (
        reserve == Decimal(window) * max(Decimal(prompt_price), Decimal(completion_price)) / 1000000
    )
    assert call["reservation_basis"] == "shared_context_window_max_price"
    assert call["context_billing_upper_bound"] == window
    # Completion includes reasoning. Cover known1017 endpoint maxima as well as
    # the full shared window; no provider maximum is sent on the wire.
    for completion in (0, 131072, 393216, 943718, window):
        prompt = window - completion
        actual = (prompt * Decimal(prompt_price) + completion * Decimal(completion_price)) / 1000000
        assert actual <= reserve


def test_money_only_refuses_inconsistent_context_bound_before_meter(historical_budget, monkeypatch):
    path, ledger, _, _ = historical_budget
    ledger.update(budget_mode="money_only")
    path.write_text(json.dumps(ledger), encoding="utf-8")
    route = selected().model_copy(update={"mimi_route_billing_prompt_ceiling": 272000})
    monkeypatch.setattr(budget, "key_meter", lambda _: pytest.fail("invalid bound before meter"))
    with pytest.raises(RouteContractError, match="native_context_bound"):
        budget.reserve(route, [], agent_contract=True)
    assert not json.loads(path.read_text())["calls"]


@pytest.mark.parametrize("remaining,allowed", [("2.296089995", True), ("1.89", False)])
def test_supplied_successor_schema_preserves_headroom_and_full_old_hold(
    historical_budget, monkeypatch, remaining, allowed
):
    path, ledger, _, _ = historical_budget
    ledger.update(
        budget_mode="money_only",
        cap_usd="2.450605966",
        baseline_key_usage=".549233754",
        historical_dispatch_count=55,
        historical_max_dispatch_count=2,
        historical_accounted_usd=".1545159824",
        historical_reserved_usd=".38928384",
        max_paid_dispatches=None,
        max_conditional_max_dispatches=None,
    )
    path.write_text(json.dumps(ledger), encoding="utf-8")
    monkeypatch.setattr(budget, "key_meter", lambda _: (Decimal(".703910005"), Decimal(remaining)))
    route = selected()
    if allowed:
        budget.reserve(route, [], agent_contract=True)
        assert json.loads(path.read_text())["calls"][0]["reservation_usd"] == "1.50994944"
    else:
        with pytest.raises(RouteContractError, match="key_meter_exhausted"):
            budget.reserve(route, [], agent_contract=True)
        assert not json.loads(path.read_text())["calls"]
    actual = json.loads(path.read_text())
    assert actual["historical_reserved_usd"] == ".38928384"
    assert (
        actual["historical_dispatch_count"] == 55 and actual["historical_max_dispatch_count"] == 2
    )
