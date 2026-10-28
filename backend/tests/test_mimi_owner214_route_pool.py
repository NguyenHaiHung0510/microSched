"""Explicit endpoint capabilities and material qualification drift, no provider I/O."""

import copy

import pytest
from test_mimi_collection_contracts import catalog, settings
from test_mimi_owner162 import certificate

from app.agent.route_pool import (
    NoEligibleEndpoint,
    eligible_pool,
    endpoint_fingerprint,
    qualification_scope,
)


@pytest.mark.parametrize("legacy", [None, True, False])
def test_nested_named_function_refusal_excludes_endpoint_then_restore(legacy):
    row = {"supports_tool_choice": {"function": True, "auto": True}}
    if legacy is not None:
        row["supports_tool_choice_function"] = legacy
    payload = catalog(row)
    if legacy is False:
        with pytest.raises(NoEligibleEndpoint, match="no_endpoint_meets_frozen_hard_policy"):
            eligible_pool(payload, model=settings().mimi_route_model, effort="high")
        return
    assert eligible_pool(payload, model=settings().mimi_route_model, effort="high").tags
    refused = copy.deepcopy(payload)
    refused["data"]["endpoints"][0]["supports_tool_choice"]["function"] = False
    with pytest.raises(NoEligibleEndpoint, match="no_endpoint_meets_frozen_hard_policy"):
        eligible_pool(refused, model=settings().mimi_route_model, effort="high")
    assert eligible_pool(payload, model=settings().mimi_route_model, effort="high").tags


def test_nested_capability_drift_invalidates_receipt_but_price_uptime_do_not():
    selected = settings()
    payload = catalog({"supports_tool_choice": {"function": True, "auto": True}})
    proof = certificate(selected, payload)
    scope = qualification_scope(selected)

    def qualified(value):
        return eligible_pool(
            value,
            model=selected.mimi_route_model,
            effort="high",
            qualifications=[proof],
            scope_sha256=scope,
        )

    assert qualified(payload).tags
    drift = copy.deepcopy(payload)
    # Still supports named functions; a different material tool-choice capability
    # needs fresh qualification, independently of the explicit-false filter.
    drift["data"]["endpoints"][0]["supports_tool_choice"]["auto"] = False
    assert endpoint_fingerprint(drift["data"]["endpoints"][0]) != proof["endpoint_sha256"]
    with pytest.raises(NoEligibleEndpoint, match="no_eligible_qualified_endpoint"):
        qualified(drift)
    restored = copy.deepcopy(payload)
    restored["data"]["endpoints"][0].update(
        pricing={"prompt": "0.0000001", "completion": "0.0000005"},
        uptime_last_1d=99.9,
    )
    assert endpoint_fingerprint(restored["data"]["endpoints"][0]) == proof["endpoint_sha256"]
    assert qualified(restored).tags
    assert qualified(payload).tags
