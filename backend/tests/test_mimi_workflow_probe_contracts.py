from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.workflow_probe.contracts import (
    NOTE_ADAPTER,
    TASK_ADAPTER,
    Confirmation,
    ProbeBlocked,
    Record,
    authorize_confirmation,
    encode_frame,
    freeze_preview,
)

NOW = datetime(2026, 9, 30, tzinfo=UTC)


@pytest.fixture
def preview():
    return freeze_preview(
        TASK_ADAPTER,
        (Record("a", 3, "Synthetic title"),),
        owner="owner-a",
        generation=2,
        policy="policy-v1",
    )


def authorize(preview, confirmation, **changes):
    parameters = {
        "source_versions": {"a": 3},
        "policy": "policy-v1",
        "now": NOW,
        "expires_at": NOW + timedelta(hours=24),
    }
    parameters.update(changes)
    return authorize_confirmation(preview, confirmation, **parameters)


@pytest.mark.parametrize("adapter", [TASK_ADAPTER, NOTE_ADAPTER])
def test_both_domains_use_same_materialization_and_authority_gate(adapter):
    preview = freeze_preview(
        adapter,
        (Record("a", 3, "Synthetic title"),),
        owner="owner-a",
        generation=2,
        policy="policy-v1",
    )
    confirmation = Confirmation("owner-a", 2, preview.digest)
    assert authorize(preview, confirmation) == (("a", adapter.title_prefix + "Synthetic title"),)
    assert preview.sources[0].title == "Synthetic title"


@pytest.mark.parametrize(
    "change",
    [
        {"owner": "owner-b"},
        {"generation": 3},
        {"generation": True},
        {"preview_digest": "not-the-frozen-preview"},
    ],
)
def test_confirmation_from_another_authority_is_rejected(preview, change):
    confirmation = replace(Confirmation("owner-a", 2, preview.digest), **change)
    with pytest.raises(ProbeBlocked, match="confirmation_mismatch"):
        authorize(preview, confirmation)


@pytest.mark.parametrize("versions", [{"a": 4}, {}, {"a": 3, "b": 1}, {"a": 3.0}])
def test_stale_or_expanded_snapshot_requires_new_preview(preview, versions):
    with pytest.raises(ProbeBlocked, match="source_requires_repreview"):
        authorize(preview, Confirmation("owner-a", 2, preview.digest), source_versions=versions)


def test_exact_old_confirmation_cannot_execute_after_expiry_or_policy_change(preview):
    confirmation = Confirmation("owner-a", 2, preview.digest)
    with pytest.raises(ProbeBlocked, match="run_expired"):
        authorize(preview, confirmation, now=NOW + timedelta(hours=24))
    with pytest.raises(ProbeBlocked, match="policy_requires_repreview"):
        authorize(preview, confirmation, policy="policy-v2")


def test_duplicate_and_oversized_selection_rejected():
    for records, reason in [
        ((Record("a", 1, "x"), Record("a", 1, "y")), "duplicate_source"),
        (tuple(Record(str(i), 1, "x") for i in range(17)), "selection_budget_exceeded"),
    ]:
        with pytest.raises(ProbeBlocked, match=reason):
            freeze_preview(TASK_ADAPTER, records, owner="a", generation=1, policy="p")


def test_frame_budget_counts_utf8_bytes():
    with pytest.raises(ProbeBlocked, match="frame_budget_exceeded"):
        encode_frame({"synthetic": "ữ" * 24000})
