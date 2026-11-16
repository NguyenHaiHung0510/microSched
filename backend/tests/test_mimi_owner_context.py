"""Synthetic, unit-only B2 contracts: no Owner file, provider, database or cost."""

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from app.agent.context_builder import (
    assemble_context,
    input_composition_observation,
    input_projection_observation,
    rebind_after_read,
    rebind_policy_budget,
    serialize_openrouter_messages,
)
from app.agent.contracts import ExecutionLease, Sensitivity
from app.agent.observations import context_revision, prompt_observation
from app.agent.openrouter import RouteContractError, build_request, serialized_input_bytes
from app.agent.owner_context import (
    OWNER_MEMORY_MAX_BYTES,
    OWNER_MEMORY_VERSION,
    chat_system_prefix_sha256,
    compose_owner_prefix,
    load_owner_memory,
    messages_for_evidence,
)
from app.agent.policy import checkpoint_policy_compatible, load_standard_policy
from app.agent.route_config import DEEPSEEK_MODEL, bind_configuration, default_configuration
from app.agent.tools.registry import tools_for_settings
from app.agent.voice_protocol import encoded, setup
from app.agent.voice_v2_protocol import setup_v2
from app.core.settings import Settings

NOW = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
MEMORY = (
    "[SYNTHETIC_ALPHA] is a fictional naming example; task.query.v1 remains literal.\n"
    "## Workflow and confirmation\n"
    "Synthetic Unicode guidance: giữ nguyên tên giả định, không tự cấp quyền.\n"
) * 12
OTHER_MEMORY = "SYNTHETIC_BETA: another fictional naming convention."
CHECKPOINT_ID = UUID(int=9)
HISTORY = (
    {"role": "user", "content": "Synthetic earlier question"},
    {"role": "assistant", "content": "Synthetic earlier reply"},
)
CHECKPOINT = {"summary": "Synthetic retained summary", "frontier": 4}


def settings_for(memory=MEMORY, **overrides):
    values = {
        "app_env": "local",
        "oauth_state_secret": "synthetic-unit-only",
        "mimi_real_chat_enabled": True,
        "mimi_live_provider_enabled": True,
        "mimi_context_v1_enabled": True,
        "mimi_standard_api_key": "synthetic-no-provider",
        "mimi_route_model": "synthetic/unit-only",
        "mimi_route_max_input_price": 0.001,
        "mimi_route_max_output_price": 0.001,
        "mimi_voice_enabled": True,
        "mimi_voice_v2_enabled": True,
        "mimi_calendar_read_enabled": True,
        "mimi_owner_memory_v1": memory,
    }
    return Settings(_env_file=None, **{**values, **overrides})


def context_for(settings=None, *, sensitivity=Sensitivity.STANDARD, user=None):
    settings = settings if settings is not None else settings_for()
    lease = ExecutionLease(
        lease_id=UUID(int=1),
        owner_id=UUID(int=2),
        run_id=UUID(int=3),
        capabilities=tuple(t["function"]["name"] for t in tools_for_settings(settings)),
        issued_at=NOW,
        deadline=NOW + timedelta(minutes=5),
        max_turns=4,
        max_tool_calls=5,
        cost_cap_minor=0,
        sensitivity=sensitivity,
    )
    return assemble_context(
        lease=lease,
        reserved_task_id=UUID(int=5),
        conversation_id=UUID(int=6),
        generation=2,
        request_id="synthetic-b2",
        transcript_suffix=list(HISTORY),
        current_user_turn=user if user is not None else "Synthetic current question",
        task_context=[],
        pending_preview_content=[],
        pending_preview=None,
        pending_draft=None,
        checkpoint=CHECKPOINT.copy(),
        checkpoint_id=CHECKPOINT_ID,
        checkpoint_frontier=4,
        transcript_range=(5, 6),
        settings=settings,
        remaining_turns=4,
        remaining_tool_calls=5,
    )


@pytest.mark.parametrize("value", [None, "", " \r\n\t"])
def test_absent_and_blank_configuration_disable_memory(value):
    selected = settings_for(value)
    assert selected.mimi_owner_memory_v1 is None
    assert load_owner_memory(selected) is None
    envelope, messages = context_for(selected)
    base = load_standard_policy(
        collection_enabled=selected.mimi_collection_enabled,
        calendar_enabled=selected.mimi_calendar_read_enabled,
    )
    assert messages[0] == {"role": "system", "content": base.text}
    assert envelope.manifest.owner_memory is None
    assert envelope.manifest.system_prefix_sha256 == base.sha256
    assert envelope.manifest.cache.cache_key_components[0] == base.sha256
    assert "owner_memory_v1" not in encoded(setup_v2(NOW, selected))
    assert messages_for_evidence(envelope, messages) is messages


def test_server_setting_is_secret_frozen_and_excluded_from_dumps(monkeypatch):
    monkeypatch.setenv("MIMI_OWNER_MEMORY_V1", MEMORY)
    selected = Settings(_env_file=None, app_env="local", oauth_state_secret="synthetic")
    assert isinstance(selected.mimi_owner_memory_v1, SecretStr)
    assert selected.mimi_owner_memory_v1.get_secret_value() == MEMORY
    assert "mimi_owner_memory_v1" not in selected.model_dump()
    assert MEMORY not in repr(selected)
    assert MEMORY not in selected.model_dump_json()
    with pytest.raises(ValidationError, match="frozen_field"):
        selected.mimi_owner_memory_v1 = SecretStr(OTHER_MEMORY)
    memory = load_owner_memory(selected)
    with pytest.raises(FrozenInstanceError):
        memory.text = SecretStr(OTHER_MEMORY)
    with pytest.raises(ValidationError, match="frozen_instance"):
        memory.receipt.sha256 = "0" * 64
    assert MEMORY not in repr(memory)
    assert MEMORY not in memory.receipt.model_dump_json()


@pytest.mark.parametrize(
    "overrides",
    [
        {"mimi_max_payload_bytes": 1},
        {"app_env": "not-a-valid-environment"},
        {"mimi_real_chat_enabled": False},
    ],
)
def test_unrelated_configuration_errors_never_echo_private_input(overrides):
    with pytest.raises(ValidationError) as caught:
        settings_for(**overrides)
    assert MEMORY not in str(caught.value)
    assert MEMORY not in caught.value.json()


def test_eight_kibibyte_utf8_limit_preserves_the_complete_reviewed_text():
    text = "đ" * (OWNER_MEMORY_MAX_BYTES // 2)
    selected = settings_for(text)
    memory = load_owner_memory(selected)
    assert memory.text.get_secret_value().endswith(text + "\n</owner_memory_v1>\n")
    assert memory.receipt.utf8_bytes > OWNER_MEMORY_MAX_BYTES
    envelope, messages = context_for(selected)
    assert text in messages[0]["content"]
    assert text in setup_v2(NOW, selected)["setup"]["systemInstruction"]["parts"][0]["text"]
    assert serialized_input_bytes(messages, agent_contract=True, calendar_enabled=True) <= (
        envelope.manifest.budget.serialized_input_upper_bound
    )


@pytest.mark.parametrize(
    "value,code",
    [
        ("đ" * (OWNER_MEMORY_MAX_BYTES // 2) + "x", "exceeds_8192_utf8_bytes"),
        ("SYNTHETIC_CANARY" + "x" * OWNER_MEMORY_MAX_BYTES, "exceeds_8192_utf8_bytes"),
        ("SYNTHETIC_CANARY\ud800", "invalid_utf8"),
    ],
    ids=["utf8-over-bound", "ascii-over-bound", "invalid-utf8"],
)
def test_invalid_or_oversized_memory_fails_without_leaking_or_truncating(value, code):
    with pytest.raises(ValidationError, match=code) as caught:
        settings_for(value)
    assert "SYNTHETIC_CANARY" not in str(caught.value)
    assert "SYNTHETIC_CANARY" not in caught.value.json()
    assert not caught.value.errors()[0]["input"] == value


@pytest.mark.parametrize("collection", [False, True])
@pytest.mark.parametrize("calendar", [False, True])
def test_chat_voice_receive_the_identical_block_after_projection(collection, calendar):
    selected = settings_for(
        mimi_collection_enabled=collection,
        mimi_calendar_read_enabled=calendar,
    )
    assert 1_536 < len(MEMORY.encode()) < OWNER_MEMORY_MAX_BYTES
    envelope, messages = context_for(selected)
    memory = load_owner_memory(selected)
    block = memory.text.get_secret_value()
    live = setup_v2(NOW, selected)
    live_text = live["setup"]["systemInstruction"]["parts"][0]["text"]
    base = load_standard_policy(collection_enabled=collection, calendar_enabled=calendar)
    assert messages[0] == {"role": "system", "content": base.text + block}
    assert live_text.endswith(block)
    assert messages[0]["content"].count("<owner_memory_v1>") == 1
    assert live_text.count("<owner_memory_v1>") == 1
    assert MEMORY in live_text  # Neither workflow projection nor tool-name rewrites touch it.
    assert "task.query.v1" in block
    assert "clientContent" not in live
    assert "historyConfig" not in live["setup"]
    assert "initialHistory" not in encoded(live)
    assert "SYNTHETIC_ALPHA" not in json.dumps(messages[1:])
    assert "SYNTHETIC_ALPHA" not in json.dumps(live["setup"]["tools"])
    assert live["setup"]["generationConfig"] == setup(NOW)["setup"]["generationConfig"]
    assert load_owner_memory(selected).receipt == envelope.manifest.owner_memory


def test_prefix_append_is_idempotent_without_normalizing_configured_text():
    selected = settings_for(" \r\nSYNTHETIC exact whitespace \t\r\n")
    once, receipt = compose_owner_prefix("Synthetic base", selected)
    twice, repeated = compose_owner_prefix(once, selected)
    assert twice == once
    assert receipt == repeated
    assert " \r\nSYNTHETIC exact whitespace \t\r\n" in once
    assert hashlib.sha256(once.encode()).hexdigest() == hashlib.sha256(twice.encode()).hexdigest()


def test_voice_v1_and_feature_eligibility_are_unchanged():
    from app.agent.voice_store import voice_available, voice_v2_available

    selected = Settings(
        _env_file=None,
        app_env="local",
        oauth_state_secret="synthetic",
        mimi_owner_memory_v1=MEMORY,
    )
    assert not selected.mimi_real_chat_enabled
    assert not selected.mimi_live_provider_enabled
    assert not selected.mimi_context_v1_enabled
    assert not selected.mimi_voice_enabled
    assert not selected.mimi_voice_v2_enabled
    assert not voice_available(selected)
    assert not voice_v2_available(selected)
    old = setup(NOW)
    assert "SYNTHETIC_ALPHA" not in encoded(old)
    assert "owner_memory_v1" not in encoded(old)
    assert "sessionResumption" not in old["setup"]
    assert "contextWindowCompression" not in old["setup"]


def test_non_native_chat_does_not_receive_native_owner_memory():
    selected = settings_for(
        mimi_route_mode="exact",
        mimi_route_provider="synthetic-provider",
        mimi_route_quantization="synthetic-quantization",
    )
    envelope, messages = context_for(selected)
    assert envelope.manifest.owner_memory is None
    assert "SYNTHETIC_ALPHA" not in messages[0]["content"]
    assert envelope.manifest.policy_sha256 == envelope.manifest.system_prefix_sha256


def test_private_lease_cannot_be_relabelled_as_standard():
    with pytest.raises(ValueError, match="standard_context_required"):
        context_for(sensitivity=Sensitivity.PRIVATE)


def test_memory_revision_changes_prefix_and_cache_without_discarding_checkpoint_history():
    contexts = [context_for(settings_for(m)) for m in (None, MEMORY, OTHER_MEMORY, None)]
    policy_hashes = set()
    prefix_hashes = []
    cache_tails = []
    for envelope, messages in contexts:
        manifest = envelope.manifest
        policy_hashes.add(manifest.policy_sha256)
        prefix_hashes.append(manifest.system_prefix_sha256)
        cache_tails.append(manifest.cache.cache_key_components[1:])
        assert (
            manifest.system_prefix_sha256
            == hashlib.sha256(messages[0]["content"].encode()).hexdigest()
        )
        assert manifest.cache.cache_key_components[0] == manifest.system_prefix_sha256
        assert checkpoint_policy_compatible(manifest.policy_sha256, collection_enabled=False)
        assert envelope.checkpoint == CHECKPOINT
        assert envelope.transcript_suffix == HISTORY
        assert manifest.checkpoint_id == CHECKPOINT_ID
        assert manifest.checkpoint_frontier == 4
        assert manifest.transcript_range == (5, 6)
        assert list(HISTORY) == messages[3:5]
    assert len(policy_hashes) == 1
    assert len(set(prefix_hashes)) == 3
    assert prefix_hashes[0] == prefix_hashes[-1]
    assert all(tail == cache_tails[0] for tail in cache_tails)


def test_read_and_budget_rebinding_keep_one_frozen_block_and_account_for_it():
    selected = settings_for()
    envelope, messages = context_for(selected)
    messages.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "synthetic-read",
                        "type": "function",
                        "function": {"name": "task.query.v1", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "synthetic-read", "content": "{}"},
        ]
    )
    updated, rebound = rebind_after_read(
        envelope,
        messages,
        tool_name="task.query.v1",
        call_id="synthetic-read",
        arguments={},
        result={"rows": [], "count": 0, "coverage": "complete", "data_as_of": NOW.isoformat()},
        remaining_turns=3,
        remaining_tool_calls=4,
    )
    # Deployment input is immutable for this live frame, including config reloads.
    rotated = selected.model_copy(update={"mimi_owner_memory_v1": SecretStr(OTHER_MEMORY)})
    refreshed, wire = rebind_policy_budget(
        updated,
        rebound,
        settings=rotated,
        remaining_turns=2,
        remaining_tool_calls=3,
    )
    assert wire[0] == messages[0]
    assert MEMORY in wire[0]["content"]
    assert OTHER_MEMORY not in wire[0]["content"]
    assert wire[0]["content"].count("<owner_memory_v1>") == 1
    assert refreshed.manifest.owner_memory == envelope.manifest.owner_memory
    assert refreshed.manifest.system_prefix_sha256 == envelope.manifest.system_prefix_sha256
    assert refreshed.checkpoint == CHECKPOINT
    assert refreshed.transcript_suffix == HISTORY
    assert wire[-1] == messages[-1]
    assert serialized_input_bytes(wire, agent_contract=True, calendar_enabled=True) <= (
        refreshed.manifest.budget.serialized_input_upper_bound
    )


def test_safe_receipts_envelope_dumps_evidence_and_telemetry_omit_the_block(caplog):
    from app.agent.service import _manifest_receipt

    selected = settings_for()
    envelope, messages = context_for(selected)
    original = json.dumps(messages)
    evidence = messages_for_evidence(envelope, messages)
    assert json.dumps(messages) == original
    assert evidence[1:] == messages[1:]
    assert (
        evidence[0]["content"]
        == load_standard_policy(collection_enabled=False, calendar_enabled=True).text
    )
    manifest = envelope.manifest.model_dump(mode="json")
    assert manifest["owner_memory"]["version"] == OWNER_MEMORY_VERSION
    assert manifest["owner_memory"]["sha256"] == load_owner_memory(selected).receipt.sha256
    assert manifest["system_prefix_sha256"] == chat_system_prefix_sha256(selected)
    assert "policy_text" not in envelope.model_dump()
    composition = input_composition_observation(envelope, messages, settings=selected)
    projection = input_projection_observation(envelope, messages, settings=selected)
    assert composition["state"] == "measured_bytes"
    assert sum(row["value"] for row in composition["categories"]) == composition["total"]
    assert all(row["value"] >= 0 for row in composition["categories"])
    for value in (
        selected.model_dump_json(),
        repr(selected),
        repr(envelope),
        repr(load_owner_memory(selected)),
        json.dumps(manifest),
        json.dumps(evidence),
        json.dumps(_manifest_receipt(envelope)),
        json.dumps(composition),
        json.dumps(projection),
        caplog.text,
    ):
        assert "SYNTHETIC_ALPHA" not in value
        assert "owner_memory_v1>\n[SYNTHETIC" not in value
    assert serialize_openrouter_messages(envelope) == messages


def test_evidence_redaction_rejects_a_mismatched_wire_or_receipt():
    envelope, messages = context_for()
    with pytest.raises(ValueError, match="owner_memory_evidence_prefix_mismatch"):
        messages_for_evidence(envelope, [{"role": "system", "content": "Synthetic wrong prefix"}])
    broken = envelope.model_copy(
        update={
            "manifest": envelope.manifest.model_copy(
                update={
                    "owner_memory": envelope.manifest.owner_memory.model_copy(
                        update={"sha256": "0" * 64}
                    ),
                }
            ),
        }
    )
    with pytest.raises(ValueError, match="owner_memory_evidence_receipt_mismatch"):
        messages_for_evidence(broken, messages)


def test_native_payload_accounting_contains_full_memory_and_keeps_resource_guard():
    selected = settings_for()
    envelope, messages = context_for(selected)
    disabled, disabled_messages = context_for(settings_for(None))
    request = build_request(messages, settings=selected, agent_contract=True)
    assert request["messages"][0] == messages[0]
    assert MEMORY in request["messages"][0]["content"]
    assert serialized_input_bytes(messages, agent_contract=True, calendar_enabled=True) > (
        serialized_input_bytes(disabled_messages, agent_contract=True, calendar_enabled=True)
    )
    assert envelope.manifest.budget.serialized_input_upper_bound > (
        disabled.manifest.budget.serialized_input_upper_bound
    )
    limited = settings_for(mimi_max_payload_bytes=65_536)
    oversized, wire = context_for(limited, user="Synthetic input " * 6_000)
    assert MEMORY in wire[0]["content"]
    assert oversized.manifest.budget.serialized_input_upper_bound > 65_536
    with pytest.raises(RouteContractError, match="payload_bytes_exceeded"):
        build_request(wire, settings=limited, agent_contract=True)


def test_prompt_revision_helper_tracks_memory_without_changing_base_compatibility():
    disabled = settings_for(None)
    enabled = settings_for()
    changed = settings_for(OTHER_MEMORY)
    assert (
        len(
            {
                chat_system_prefix_sha256(disabled),
                chat_system_prefix_sha256(enabled),
                chat_system_prefix_sha256(changed),
            }
        )
        == 3
    )
    assert (
        chat_system_prefix_sha256(enabled) == context_for(enabled)[0].manifest.system_prefix_sha256
    )
    assert context_for(disabled)[0].manifest.policy_sha256 == (
        context_for(enabled)[0].manifest.policy_sha256
    )


@pytest.mark.parametrize(
    "collection,legacy_revision",
    [
        (False, "3b9352e05a1178dc738f32bea1bff938b33d6dfae5752b2cac4781ddb016ecca"),
        (True, "099a5728365f411e7c959a14a4375d115bbd68ce9089c97051b901cee54a27cd"),
    ],
)
def test_no_memory_keeps_the_legacy_prompt_observation_epoch(collection, legacy_revision):
    # Actual pre-followup revisions at 442ec89 with the synthetic native settings.
    for absent in (None, "", " \r\n\t"):
        selected = settings_for(absent, mimi_collection_enabled=collection)
        assert context_revision(selected, 7, CHECKPOINT_ID) == legacy_revision
    injected_blank = settings_for(None, mimi_collection_enabled=collection).model_copy(
        update={"mimi_owner_memory_v1": SecretStr(" \t")}
    )
    assert context_revision(injected_blank, 7, CHECKPOINT_ID) == legacy_revision


@pytest.mark.parametrize(
    "overrides",
    [
        {"mimi_real_chat_enabled": False, "mimi_live_provider_enabled": False},
        {"mimi_live_provider_enabled": False},
        {"mimi_context_v1_enabled": False},
        {
            "mimi_route_mode": "exact",
            "mimi_route_provider": "synthetic-provider",
            "mimi_route_quantization": "synthetic-quantization",
        },
    ],
    ids=["chat-disabled", "live-disabled", "context-disabled", "not-native"],
)
def test_configured_but_inactive_memory_keeps_the_existing_prompt_epoch(overrides):
    assert context_revision(settings_for(**overrides), 7, CHECKPOINT_ID) == context_revision(
        settings_for(None, **overrides), 7, CHECKPOINT_ID
    )


def test_active_memory_refreshes_deployed_native_prompt_receipts_only():
    # Exercise the deployment's native profile binding with synthetic, in-memory settings.
    deployment = settings_for(
        app_env="production",
        mimi_public_origin="https://synthetic.example.test",
        mimi_collection_enabled=True,
        mimi_runner="langgraph",
        mimi_transport="openai_sdk",
        mimi_route_model=DEEPSEEK_MODEL,
    )
    active = bind_configuration(deployment, default_configuration(deployment))
    rotated = active.model_copy(update={"mimi_owner_memory_v1": SecretStr(OTHER_MEMORY)})
    disabled = active.model_copy(update={"mimi_owner_memory_v1": None})
    before, enabled, changed = (
        context_revision(config, 7, CHECKPOINT_ID) for config in (disabled, active, rotated)
    )
    assert active.mimi_route_mode == "native"
    assert len({before, enabled, changed}) == 3
    assert context_revision(active.model_copy(), 7, CHECKPOINT_ID) == enabled

    receipt = SimpleNamespace(
        id=UUID(int=10),
        state="succeeded",
        route={
            "purpose": "main",
            "kind": "openrouter",
            "mode": active.mimi_route_mode,
            "context_revision": enabled,
            "model": active.mimi_route_model,
            "actual_model": active.mimi_route_model,
        },
        usage={"prompt_tokens": 42},
    )
    assert prompt_observation(receipt, enabled)["prompt_tokens"] == 42
    for other in (before, changed):
        assert prompt_observation(receipt, other)["reason"] == "stale_context_revision"

    base_policy = load_standard_policy(collection_enabled=True, calendar_enabled=True)
    for config in (disabled, active, rotated):
        envelope, wire = context_for(config)
        assert envelope.manifest.policy_sha256 == base_policy.sha256
        assert checkpoint_policy_compatible(
            envelope.manifest.policy_sha256, collection_enabled=True
        )
        assert envelope.manifest.checkpoint_id == CHECKPOINT_ID
        assert envelope.checkpoint == CHECKPOINT
        assert envelope.transcript_suffix == HISTORY
        assert (
            envelope.manifest.system_prefix_sha256
            == hashlib.sha256(wire[0]["content"].encode()).hexdigest()
        )


# Frozen pre-B2 source 0e0ed187abc39439331a4a244d2c8fa733b2dff8, clock NOW.
# Synthetic context_for fixture; SHA256 of canonical JSON and exact request bytes.
PRE_B2_OFF_FIXTURES = {
    "collection=False,calendar=False": {
        "manifest_sha256": "16e949ac163f007043e129ffe23bd6ff4e39e994f34c1cfa8414dd3af8cdbc49",
        "envelope_sha256": "58c9bf2cd005654085806f5300d40636576188d53c1a93fab4a4fbfdb006ded0",
        "messages_sha256": "3d420fa65b16f414876002a4c0504c46d1e400a0d14cba66537346a696015f0e",
        "authority_sha256": "1926450d40c46b4606fd879fe654969fd2046d70987b5bfafb060882e545f67d",
        "request_sha256": "170f8a67ae462562840844f43d605d56401bae1ac3c2431b822bb87a6e6c89dc",
        "projection_sha256": "bd374b43efce08ebeed3dd817b4d67c9247b7d581e5790434aa08bac76c5e6f8",
        "serialized_input_bytes": 27759,
        "bound": 27759,
    },
    "collection=False,calendar=True": {
        "manifest_sha256": "43034c4691542b18a8e416dbf5cebde8f24e36667b58a62ff4385a65d4b96aa3",
        "envelope_sha256": "03f505b5fdd5ed56d4c0f029fb51f6084d726f0477ef5f7fc7e69f748de2c421",
        "messages_sha256": "1ca124cf0f9e5df2591f0798395a12b76af8c374f99228973ed0b28b785b1e9c",
        "authority_sha256": "4c6417b61849b2682ba2e879c9fd3b683a423d634d2ca55b48051260df08b43e",
        "request_sha256": "b263127ffd69526712766e857e5bb1439d3a65766bc24d8b0f4e1e1db324c7ca",
        "projection_sha256": "56b7ee3226ca9ea5aa98cabb05008c5abd4e54f99580ac0ad23e55cb36365dd6",
        "serialized_input_bytes": 31331,
        "bound": 31331,
    },
    "collection=True,calendar=False": {
        "manifest_sha256": "d7f2ac19fc6a7828acf8a906345ecf40d4c460fcf9e0bc53e44211a9fbdad807",
        "envelope_sha256": "d1218de66a5dc338c617bfcf1e09994a305ecb8386d73d7d0435d72fbfb5efd2",
        "messages_sha256": "c21e13b9b07179da11111e950afd90d7c8aca40a336fa8bc8b8bc0c38792c594",
        "authority_sha256": "13932b0fdb7274120522d76d52658282f2d34ef3d4efd8fcd0d31a9942fb45e0",
        "request_sha256": "08724ab34ba463b0f12a98144cf7db305bcfb27923862df6e070bf18939872cf",
        "projection_sha256": "77a598b98b428c19f641efccf4938a615616517230e4ca5befda36647bdcdcdd",
        "serialized_input_bytes": 39187,
        "bound": 39187,
    },
    "collection=True,calendar=True": {
        "manifest_sha256": "6f30d1f144ba5ab8b597742ad6f955af2751d97f3ea684ece8fc3b07e03b168f",
        "envelope_sha256": "24f7546fef6899e110a5863c6adac3c06d812b08a8f6928c7f68dc3033c694d5",
        "messages_sha256": "ca1f7c04afd5cb88cff54c2c7e2566ee069b7aea3c15e04ea1044efb6e8b4216",
        "authority_sha256": "6f770f9866c5e63323a71ef6b79b4a775e0a7bb32ae238479ba7e1168a80b213",
        "request_sha256": "6883e8b4239daf0f9e3eb4c8c9684f7d51588dded10fe563af46c9eb8abd88d6",
        "projection_sha256": "0a4fc80eafb51d6fb8c1d09670ae7b567ce1fb22cb3e4a9ee7ed36563be53d7a",
        "serialized_input_bytes": 42759,
        "bound": 42759,
    },
}


@pytest.mark.parametrize(
    "collection,calendar", [(False, False), (False, True), (True, False), (True, True)]
)
@pytest.mark.parametrize("memory", [None, "", " \r\n\t"], ids=["unset", "empty", "whitespace"])
def test_memory_off_wire_matches_exact_pre_b2_source_fixture(
    monkeypatch, collection, calendar, memory
):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr("app.agent.context_builder.datetime", FrozenDateTime)
    selected = settings_for(
        memory, mimi_collection_enabled=collection, mimi_calendar_read_enabled=calendar
    )
    envelope, messages = context_for(selected)
    projection = input_projection_observation(envelope, messages, settings=selected)
    authority = json.loads(messages[-2]["content"])
    expected = PRE_B2_OFF_FIXTURES[f"collection={collection},calendar={calendar}"]

    def digest(value):
        return hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
            ).encode("utf-8")
        ).hexdigest()

    assert {
        "manifest_sha256": envelope.manifest.sha256(),
        "envelope_sha256": digest(envelope.model_dump(mode="json")),
        "messages_sha256": digest(messages),
        "authority_sha256": digest(authority),
        "request_sha256": digest(build_request(messages, settings=selected, agent_contract=True)),
        "projection_sha256": digest(projection),
        "serialized_input_bytes": serialized_input_bytes(
            messages, agent_contract=True, calendar_enabled=calendar
        ),
        "bound": envelope.manifest.budget.serialized_input_upper_bound,
    } == expected
    assert projection["request_fingerprint"] == expected["request_sha256"]
    assert messages_for_evidence(envelope, messages) is messages
    assert (
        envelope.manifest.system_prefix_sha256
        == hashlib.sha256(envelope.policy_text.encode("utf-8")).hexdigest()
    )

    for dumped in (
        envelope.manifest.model_dump(),
        json.loads(envelope.manifest.model_dump_json()),
        envelope.model_dump()["manifest"],
        authority["context_manifest"],
        projection,
    ):
        assert "system_prefix_sha256" not in dumped
        assert "owner_memory" not in dumped


@pytest.mark.parametrize("collection", [False, True])
@pytest.mark.parametrize("calendar", [False, True])
def test_active_memory_keeps_full_metadata_on_manifest_authority_and_projection(
    collection, calendar
):
    selected = settings_for(mimi_collection_enabled=collection, mimi_calendar_read_enabled=calendar)
    envelope, messages = context_for(selected)
    projection = input_projection_observation(envelope, messages, settings=selected)
    receipt = load_owner_memory(selected).receipt
    prefix_sha256 = hashlib.sha256(messages[0]["content"].encode("utf-8")).hexdigest()
    for dumped in (
        envelope.manifest.model_dump(mode="json"),
        json.loads(envelope.manifest.model_dump_json()),
        envelope.model_dump(mode="json")["manifest"],
        json.loads(messages[-2]["content"])["context_manifest"],
        projection,
    ):
        assert dumped["system_prefix_sha256"] == prefix_sha256
        assert dumped["owner_memory"] == receipt.model_dump(mode="json")
        assert "SYNTHETIC_ALPHA" not in json.dumps(dumped)
    assert receipt.utf8_bytes == len(load_owner_memory(selected).text.get_secret_value().encode())
    assert messages[0]["content"].endswith(load_owner_memory(selected).text.get_secret_value())
    assert serialized_input_bytes(messages, agent_contract=True, calendar_enabled=calendar) == (
        envelope.manifest.budget.serialized_input_upper_bound
    )
    assert envelope.checkpoint == CHECKPOINT
    assert envelope.transcript_suffix == HISTORY
