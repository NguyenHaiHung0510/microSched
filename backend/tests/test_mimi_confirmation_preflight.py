"""Read-only eligibility never rebases a preview or replaces authoritative POST."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.agent import service


@pytest.mark.parametrize(
    "boundary,reason",
    [
        ("fresh", None),
        ("frontier", "change_set_frontier_stale"),
        ("privacy", "task_collection_conversation_not_standard"),
        ("lease", "change_set_collection_lease_not_authorized"),
        ("revoked", "change_set_collection_lease_not_authorized"),
        ("expired", "change_set_expired"),
        ("stale", "change_set_stale"),
        ("disabled", "mimi_collection_feature_disabled"),
    ],
)
def test_collection_preflight_reports_only_known_binding_checks(monkeypatch, boundary, reason):
    now = datetime.now(UTC)
    conv = SimpleNamespace(sensitivity="standard", is_private=False, generation=3)
    run = SimpleNamespace(generation=2, execution_lease={"capabilities": [service.COLLECTION_TOOL]})
    row = SimpleNamespace(state="pending", expires_at=now + timedelta(minutes=180))
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(mimi_collection_enabled=boundary != "disabled"),
    )
    if boundary == "frontier":
        conv.generation += 1
    elif boundary == "privacy":
        conv.sensitivity = "private"
        conv.is_private = True
    elif boundary == "lease":
        run.execution_lease = {"capabilities": []}
    elif boundary == "revoked":
        run.execution_lease = {
            "capabilities": [service.COLLECTION_TOOL],
            "revoked_at": now.isoformat(),
        }
    elif boundary == "expired":
        row.expires_at = now
    elif boundary == "stale":
        row.state = "stale"
    before = (conv.generation, row.state, row.expires_at, dict(run.execution_lease))
    assert service._collection_confirmation_preflight(conv, run, row, now) == {
        "status": "blocked" if reason else "eligible",
        "reason": reason,
    }
    assert (conv.generation, row.state, row.expires_at, run.execution_lease) == before
