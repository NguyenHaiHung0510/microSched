"""Owner162/164 safety contracts; provider usage is synthetic, never performance proof."""

import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_mimi_collection_contracts import catalog, settings
from test_mimi_context import _context

from app.agent.observations import context_revision, prompt_observation, run_costs
from app.agent.openrouter import RouteContractError, build_request
from app.agent.policy import checkpoint_policy_compatible, load_standard_policy
from app.agent.route_pool import (
    NoEligibleEndpoint,
    eligible_pool,
    endpoint_fingerprint,
    qualification_scope,
)
from app.agent.service import _provider_session_id, _reported_usage


def certificate(selected, payload):
    row = payload["data"]["endpoints"][0]
    return {
        "catalog_tag": row["tag"],
        "routing_slug": "synthetic-provider/verified-fp8",
        "provider_name": "Synthetic Provider",
        "model": selected.mimi_route_model,
        "effort": selected.mimi_route_reasoning_effort,
        "scope_sha256": qualification_scope(selected),
        "endpoint_sha256": endpoint_fingerprint(row),
        "quantization": "fp8",
        "zdr": True,
        "data_collection": "deny",
        "named_function": True,
        "request_families": ["main", "summary", "forced_function"],
        "expires_at": time.time() + 3600,
        "evidence_sha256": {
            a: "a" * 64
            for a in ("routing_slug", "privacy", "effort", "main", "summary", "forced_function")
        },
    }


@pytest.mark.parametrize(
    "violation", ["absent", "expired", "scope", "variant", "privacy", "function", "effort"]
)
def test_dynamic_pool_requires_each_endpoint_certificate_then_restore(violation):
    selected = settings()
    payload = catalog({"tag": "new-provider/fp8"})
    proof = certificate(selected, payload)
    bad = proof.copy()
    if violation == "expired":
        bad["expires_at"] = 0
    if violation == "scope":
        bad["scope_sha256"] = "0" * 64
    if violation == "variant":
        bad["endpoint_sha256"] = "0" * 64
    if violation == "privacy":
        bad["zdr"] = False
    if violation == "function":
        bad["named_function"] = False
    if violation == "effort":
        bad["effort"] = "max"
    with pytest.raises(NoEligibleEndpoint, match="no_eligible_qualified_endpoint"):
        eligible_pool(
            payload,
            model=selected.mimi_route_model,
            effort="high",
            qualifications=[] if violation == "absent" else [bad],
            scope_sha256=qualification_scope(selected),
        )
    restored = eligible_pool(
        payload,
        model=selected.mimi_route_model,
        effort="high",
        qualifications=[proof],
        scope_sha256=qualification_scope(selected),
    )
    assert restored.tags == ("synthetic-provider/verified-fp8",)
    assert restored.provider_names == ("Synthetic Provider",)


def test_native_policy_fences_stale_certificate_and_catalog():
    base = settings(
        mimi_route_mode="adaptive",
        mimi_route_allowed_providers="verified-provider/fp8",
        mimi_route_catalog_checked_at=time.time(),
        mimi_route_qualification_expires_at=time.time() + 3600,
        mimi_route_qualification_sha256="a" * 64,
    )
    wire = build_request([], base, agent_contract=True)
    assert wire["provider"]["only"] == ["verified-provider/fp8"]
    assert "order" not in wire["provider"] and "sort" not in wire["provider"]
    for bad in [
        base.model_copy(update={"mimi_route_qualification_expires_at": 0}),
        base.model_copy(update={"mimi_route_catalog_checked_at": time.time() - 7201}),
    ]:
        with pytest.raises(RouteContractError, match="qualification_stale_or_missing"):
            build_request([], bad, agent_contract=True)


@pytest.mark.parametrize("prompt,compact", [(271999, False), (272000, True), (272001, True)])
def test_provider_prompt_boundary_and_rollback_epoch(prompt, compact):
    selected = settings()
    revision = context_revision(selected, 1, None)
    call = SimpleNamespace(
        id=uuid4(),
        state="succeeded",
        usage={"prompt_tokens": prompt},
        route={
            "purpose": "main",
            "kind": "openrouter",
            "model": selected.mimi_route_model,
            "actual_model": selected.mimi_route_model,
            "actual_provider": "Synthetic Provider",
            "qualified_provider_names": ["Synthetic Provider"],
            "providers": ["synthetic/variant"],
            "context_revision": revision,
        },
    )
    assert prompt_observation(call, revision)["should_compact"] == compact
    rollback = selected.model_copy(update={"mimi_compaction_trigger_tokens": 100000})
    assert context_revision(rollback, 1, None) != revision
    assert not prompt_observation(call, context_revision(rollback, 1, None), trigger_tokens=100000)[
        "eligible"
    ]


def test_cache_observation_missing_is_unknown_and_reused_not_billed():
    call = SimpleNamespace(
        id=uuid4(),
        state="succeeded",
        result={"response_id": "synthetic"},
        route={"kind": "openrouter"},
        usage={
            "prompt_tokens": 100,
            "cost": 0.01,
            "prompt_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 5},
        },
    )
    assert _reported_usage(call.usage)["cached_tokens"] == 80
    assert _reported_usage(call.usage)["cache_write_tokens"] == 5
    assert run_costs([call])["cache_token_ratio"] == 0.8
    call.usage = {"prompt_tokens": 100}
    result = run_costs([call])
    assert result["provider_cached_tokens"] is None and result["cache_unknown_calls"] == 1
    assert result["unknown_cost_calls"] == 1
    call.route["paid_dispatch"] = False
    assert run_costs([call])["main_calls"] == 0


def test_known_checkpoint_semantics_and_unknown_digest_failclosed():
    old = "642e13054d25e81cb53bd9488a6ffbf56f2aeb28646721091bd5d01007eb8c52"
    assert checkpoint_policy_compatible(old, collection_enabled=True)
    assert not checkpoint_policy_compatible(old, collection_enabled=False)
    assert not checkpoint_policy_compatible("0" * 64, collection_enabled=True)
    assert checkpoint_policy_compatible(
        load_standard_policy(collection_enabled=True).sha256, collection_enabled=True
    )


def test_prefix_serialization_and_opaque_conversation_affinity_stay_stable():
    selected = settings()
    one, wire = _context(settings=selected)
    two, other = _context(settings=selected)
    assert wire[:2] == other[:2] and wire[-2] != other[-2]
    assert one.manifest.cache.cache_key_components == two.manifest.cache.cache_key_components
    cid = uuid4()
    sid = _provider_session_id(cid)
    assert sid == _provider_session_id(cid) and sid != _provider_session_id(uuid4())
    assert str(cid) not in sid and len(sid) <= 256


@pytest.mark.parametrize(
    "field,value",
    [("context_length", 272000), ("max_completion_tokens", 8191), ("context_length", None)],
)
def test_pool_capacity_rejection_then_restore(field, value):
    selected = settings()
    valid = catalog()
    bad = catalog({field: value})
    proof = certificate(selected, bad)
    with pytest.raises(NoEligibleEndpoint):
        eligible_pool(
            bad,
            model=selected.mimi_route_model,
            effort="high",
            qualifications=[proof],
            scope_sha256=qualification_scope(selected),
        )
    result = eligible_pool(
        valid,
        model=selected.mimi_route_model,
        effort="high",
        qualifications=[certificate(selected, valid)],
        scope_sha256=qualification_scope(selected),
    )
    assert result.tags
