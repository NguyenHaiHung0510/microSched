"""Author numeric-only telemetry and material qualification proof, no egress."""

import copy
import json
import time
from pathlib import Path

import pytest
from test_mimi_collection_contracts import catalog, settings
from test_mimi_context import _context
from test_mimi_owner162 import certificate

from app.agent.context_builder import input_composition_observation, serialize_openrouter_messages
from app.agent.route_pool import NoEligibleEndpoint, eligible_pool, qualification_scope


def test_production_import_guard_tracks_approved_defaults_and_runtime_frameworks(capsys):
    from scripts.check_mimi_alpha_runtime import main

    main()
    assert "framework imports PASS; no egress" in capsys.readouterr().out


def test_chat_open_native_routing_needs_no_catalog_or_model_call(monkeypatch):
    import asyncio

    from app.agent import config_policy, route_pool
    from app.web.routers import mimi

    selected = settings(mimi_route_mode="exact")
    seen = []

    async def read(*args, **kwargs):
        return config_policy.bootstrap_policy(selected)

    async def refresh(value):
        seen.append(value)

    monkeypatch.setattr(mimi, "get_settings", lambda: selected)
    monkeypatch.setattr(mimi, "read_policy", read)
    monkeypatch.setattr(route_pool.catalog, "refresh", refresh)

    async def scenario():
        result = await mimi.warm_chat_metadata(None, None)
        assert result == {"status": "not_required_native_routing", "paid_calls": 0}
        assert seen == []

    asyncio.run(scenario())


def test_qualification_reuses_unrelated_policy_but_detects_real_protocol_drift(monkeypatch):
    selected = settings()
    original_scope = qualification_scope(selected)
    changed = selected.model_copy(
        update={
            "mimi_route_max_input_price": 1.5,
            "mimi_route_max_output_price": 6.0,
            "mimi_input_codepoints": 100000,
            "mimi_operating_policy_revision": 77,
            "mimi_compaction_trigger_tokens": 100000,
        }
    )
    assert qualification_scope(changed) == original_scope
    read = Path.read_text
    mode = {"value": "unrelated"}

    def simulated_read(path, *args, **kwargs):
        source = read(path, *args, **kwargs)
        if path.name == "openrouter.py":
            if mode["value"] == "unrelated":
                return source + '\nUNRELATED_REPORT_NOTE = "synthetic"\n'
            if mode["value"] == "parser":
                return source.replace("provider_terminal_empty", "provider_terminal_changed")
            return source.replace(
                'elif agent_contract and route.mimi_text_response_format == "structured":',
                'elif agent_contract and route.mimi_text_response_format == "changed":',
            )
        return source

    monkeypatch.setattr(Path, "read_text", simulated_read)
    assert qualification_scope(selected) == original_scope
    payload = catalog()
    proof = certificate(selected, payload)
    for change in ("parser", "wire"):
        mode["value"] = change
        changed_scope = qualification_scope(selected)
        assert changed_scope != original_scope
        with pytest.raises(NoEligibleEndpoint, match="no_eligible_qualified_endpoint"):
            eligible_pool(
                payload,
                model=selected.mimi_route_model,
                effort="high",
                qualifications=[proof],
                scope_sha256=changed_scope,
            )
    mode["value"] = "unrelated"
    assert eligible_pool(
        payload,
        model=selected.mimi_route_model,
        effort="high",
        qualifications=[proof],
        scope_sha256=original_scope,
    ).tags


def test_event_proof_has_no_daily_renewal_but_expiry_revocation_and_gaps_still_refuse():
    selected = settings()
    payload = catalog()
    proof = certificate(selected, payload)
    proof.pop("expires_at")
    scope = qualification_scope(selected)

    def admit(receipts, data=payload):
        return eligible_pool(
            data,
            model=selected.mimi_route_model,
            effort="high",
            qualifications=receipts,
            scope_sha256=scope,
            now=time.time() + 3 * 86400,
        )

    assert admit([proof]).tags
    expired = {**proof, "expires_at": time.time() - 1}
    revoked = {**proof, "revoked": True}
    missing = {**proof, "evidence_sha256": {}}
    for receipts in ([expired], [proof, revoked], [missing]):
        with pytest.raises(NoEligibleEndpoint):
            admit(receipts)
    bad = copy.deepcopy(payload)
    bad["data"]["endpoints"][0]["revoked"] = True
    with pytest.raises(NoEligibleEndpoint):
        admit([proof], bad)
    assert admit([proof]).tags


def test_composition_partitions_one_wire_no_private_prose_or_synthetic_live_usage():
    selected = settings(mimi_route_max_output_tokens=8192)
    envelope, _ = _context(
        [{"title": "synthetic-hostile-title", "source_version": "v1"}], settings=selected
    )
    envelope = envelope.model_copy(
        update={
            "current_user_turn": "🌸 hỏi tiếp",
            "transcript_suffix": (
                {"role": "user", "content": "previous-only"},
                {"role": "assistant", "content": "previous-answer"},
            ),
            "checkpoint": {"summary": "synthetic-summary", "constraint_ledger": ["synthetic-rule"]},
            "pending_state": {"draft": {"title": "synthetic-pending"}},
        }
    )
    messages = serialize_openrouter_messages(envelope)
    messages.extend(
        [
            {"role": "assistant", "tool_calls": [{"id": "synthetic-read"}]},
            {"role": "tool", "tool_call_id": "synthetic-read", "content": "synthetic-read-result"},
        ]
    )
    result = input_composition_observation(envelope, messages, settings=selected)
    assert result["state"] == "measured_bytes"
    assert result["unit"] == "bytes" and result["provider_framing_tokens"] is None
    assert len(result["categories"]) == len({x["id"] for x in result["categories"]}) == 8
    assert sum(x["value"] for x in result["categories"]) == result["total"]
    assert result["input_envelope"] == 400000 and result["output_reserve"] == 8192
    assert result["compact_trigger"] == 272000
    encoded = json.dumps(result)
    for prose in (
        "synthetic-hostile-title",
        "synthetic-summary",
        "synthetic-rule",
        "synthetic-read-result",
        "previous-answer",
        "synthetic-pending",
    ):
        assert prose not in encoded
    assert "cached_tokens" not in encoded and "prompt_tokens" not in encoded
    bad = copy.deepcopy(messages)
    bad[0]["content"] += " mutated"
    assert input_composition_observation(envelope, bad, settings=selected)["state"] == "unknown"
    assert input_composition_observation(envelope, messages, settings=selected) == result
