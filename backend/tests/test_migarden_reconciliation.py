"""The support ledger never silently turns unknown losses into proven reports."""

import json

from app.domain.migarden.reconciliation import MAX_FAILURES, failure_key, reconcile


def test_failed_report_bound_preserves_entries_and_latches_overflow():
    failures = [("report", "b" * 128, f"{i:064x}") for i in range(MAX_FAILURES + 1)]
    ledger = None
    for offset in range(0, MAX_FAILURES, 16):
        ledger = reconcile(ledger, accepted=[], failed=failures[offset : offset + 16])
    assert ledger and ledger["entries"] == [list(entry) for entry in failures[:-1]]
    assert not ledger["overflow_unknown"]
    assert len(json.dumps(ledger).encode()) < 112 * 1024

    ledger = reconcile(ledger, accepted=[], failed=failures[-1:])
    assert ledger["entries"] == [list(entry) for entry in failures[:-1]]
    assert ledger["overflow_unknown"]
    for offset in range(0, len(failures), 16):
        ledger = reconcile(ledger, accepted=failures[offset : offset + 16], failed=[])
    assert ledger["entries"] == [] and ledger["overflow_unknown"]


def test_legacy_and_envelope_provenance_cannot_be_cleared_by_other_context():
    body = {"event_id": "event-example", "kind": "unknown"}
    claimed = failure_key(body, "boot-1", "packet-1")
    envelope = failure_key(body, None, "packet-1")
    old = {"boot_id": "packet-0", "fingerprints": [claimed[-1]]}

    ledger = reconcile(old, accepted=[claimed], failed=[envelope])
    ledger = reconcile(ledger, accepted=[claimed], failed=[])
    assert ledger["entries"] == [["legacy", "packet-0", claimed[-1]], list(envelope)]
    assert ledger["legacy_unknown"]
    ledger = reconcile(ledger, accepted=[envelope], failed=[])
    assert ledger["entries"] == [["legacy", "packet-0", claimed[-1]]]
    assert ledger["legacy_unknown"]
