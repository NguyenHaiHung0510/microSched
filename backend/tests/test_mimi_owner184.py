"""Meaningful Owner184 guard/provenance regressions, synthetic and no egress."""

import copy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_mimi_collection_contracts import catalog, settings
from test_mimi_owner162 import certificate

from app.agent import local_budget
from app.agent.observations import context_revision, prompt_observation
from app.agent.openrouter import RouteContractError, _input_overflow_error, build_request
from app.agent.route_pool import NoEligibleEndpoint, eligible_pool, qualification_scope


def test_soft_target_preserves_heavy_full_input_and_real_byte_resource_limit():
    selected = settings()
    content = "ệ" * 200_000
    request = build_request([{"role": "user", "content": content}], selected)
    assert request["messages"][0]["content"] == content
    assert len(content.encode()) > 400_000
    assert request["max_tokens"] == selected.mimi_route_max_output_tokens
    with pytest.raises(RouteContractError, match="payload_bytes_exceeded"):
        build_request([{"role": "user", "content": "ệ" * 800_000}], selected)
    assert build_request([{"role": "user", "content": content}], selected) == request


@pytest.mark.parametrize(
    "filename,old,new",
    [
        ("openrouter.py", '"data_collection": "deny"', '"data_collection": "allow"'),
        (
            "openrouter.py",
            '"completion": float(finite_price(settings.mimi_route_max_output_price))',
            '"completion": 0.0',
        ),
        ("route_pool.py", 'receipt.get("zdr") is not True', 'receipt.get("zdr") is False'),
        ("route_pool.py", '"max_prompt_tokens",', '"OTHER_PROMPT_CAPACITY",'),
    ],
)
def test_actual_routing_helper_body_drift_refuses_stale_proof_then_restores(
    monkeypatch, filename, old, new
):
    selected, payload = settings(), catalog()
    scope = qualification_scope(selected)
    proof = certificate(selected, payload)
    original = Path.read_text

    def changed(path, *a, **k):
        text = original(path, *a, **k)
        return text.replace(old, new) if path.name == filename else text

    with monkeypatch.context() as altered:
        altered.setattr(Path, "read_text", changed)
        drift = qualification_scope(selected)
        assert drift != scope
        with pytest.raises(NoEligibleEndpoint, match="no_eligible_qualified_endpoint"):
            eligible_pool(
                payload,
                model=selected.mimi_route_model,
                effort="high",
                qualifications=[proof],
                scope_sha256=drift,
            )
    assert qualification_scope(selected) == scope
    assert eligible_pool(
        payload,
        model=selected.mimi_route_model,
        effort="high",
        qualifications=[proof],
        scope_sha256=scope,
    ).tags


def test_native_financial_ceiling_covers_largest_admitted_endpoint_not_operating_floor():
    payload = catalog(
        {"tag": "deepinfra/a", "context_length": 600_000, "max_prompt_tokens": 500_000},
        {"tag": "deepinfra/b", "context_length": 1_200_000},
    )
    pool = eligible_pool(payload, model=settings().mimi_route_model, effort="high")
    assert pool.native_prompt_ceiling == 1_200_000 and pool.native_context_floor == 600_000
    bad = copy.deepcopy(payload)
    bad["data"]["endpoints"][1]["context_length"] = 17_000_000
    with pytest.raises(NoEligibleEndpoint, match="native_capacity_bound"):
        eligible_pool(bad, model=settings().mimi_route_model, effort="high")
    assert (
        eligible_pool(
            payload, model=settings().mimi_route_model, effort="high"
        ).native_prompt_ceiling
        == 1_200_000
    )


def test_unknown_native_financial_bound_refuses_before_meter_or_journal(monkeypatch, tmp_path):
    ledger = tmp_path / "only-synthetic.json"
    ledger.write_text("{}")
    monkeypatch.setenv("MIMI_LOCAL_BUDGET_LEDGER", str(ledger))

    def forbidden(*a):
        raise AssertionError("native bound must be established before any key-meter I/O")

    monkeypatch.setattr(local_budget, "key_meter", forbidden)
    with pytest.raises(RouteContractError, match="native_capacity_bound_missing"):
        local_budget.reserve(settings(), [], agent_contract=False)
    assert ledger.read_text() == "{}"


def test_typed_input_refusal_is_separate_from_length_generic_413_or_partial_generation():
    body = {"error": {"code": "context_length_exceeded"}, "usage": {"cost": 0}}
    failure = _input_overflow_error(400, body)
    assert failure.outcome == "failed" and failure.diagnostic["definite_refusal"] is True
    assert failure.terminal_receipt["usage"] == {"cost": 0}
    for status, candidate in [
        (413, body),
        (500, body),
        (400, {"error": {"code": 400, "message": "context_length_exceeded"}}),
        (400, body | {"id": "gen-partial"}),
        (400, body | {"usage": {"completion_tokens": 1}}),
    ]:
        assert _input_overflow_error(status, candidate) is None
    assert _input_overflow_error(400, body).diagnostic == failure.diagnostic


def test_refused_call_recovery_is_finite_and_never_uses_unknown_or_model_changed_anchor():
    selected = settings()
    revision = context_revision(selected, 1, None)
    call = SimpleNamespace(
        id=uuid4(),
        state="failed",
        usage={},
        route={
            "kind": "openrouter",
            "purpose": "main",
            "context_revision": revision,
            "input_overflow_refusal": True,
        },
    )
    assert prompt_observation(call, revision)["should_compact"] is True
    assert prompt_observation(call, revision, consumed=True)["compaction_blocked"] is True
    call.route["overflow_recovery_attempt"] = 1
    assert prompt_observation(call, revision)["compaction_blocked"] is True
    call.state = "unknown"
    assert prompt_observation(call, revision)["should_compact"] is False
    call.state = "failed"
    call.route["overflow_recovery_attempt"] = 0
    assert prompt_observation(call, "different-model-epoch")["should_compact"] is False
    assert prompt_observation(None, revision)["prompt_tokens"] is None


def test_actual_sdk_mocktransport_preserves_typed_refusal_and_generic_413_distinction():
    import asyncio

    import httpx2

    from app.agent import openai_sdk
    from app.agent.openrouter import ProviderDispatchError

    async def scenario():
        async def handler(request):
            assert request.url.path.endswith("/chat/completions")
            return httpx2.Response(
                400,
                json={"error": {"code": "context_length_exceeded", "message": "UNTRUSTED_ECHO"}},
            )

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            with pytest.raises(ProviderDispatchError) as caught:
                await openai_sdk.complete(
                    [{"role": "user", "content": "synthetic"}], settings=settings(), client=client
                )
            assert caught.value.diagnostic == {
                "category": "input_context_overflow",
                "definite_refusal": True,
            }
            assert "UNTRUSTED_ECHO" not in str(caught.value.diagnostic)

    asyncio.run(scenario())
