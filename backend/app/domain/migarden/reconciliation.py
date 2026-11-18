"""Bounded evidence of reports still needing exact, durable reconciliation."""

import hashlib
import json
import re

from pydantic import TypeAdapter, ValidationError

from app.domain.migarden.wire import Identity

MAX_FAILURES = 512
LEDGER_VERSION = 2
_HASH = re.compile(r"[a-f0-9]{64}")
_IDENTITY = TypeAdapter(Identity)
type FailureKey = tuple[str, str, str]  # provenance kind, boot ID, content SHA-256


def wire_identity(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return _IDENTITY.validate_python(value)
    except ValidationError:
        return None


def failure_key(body: object, report_boot: str | None, envelope_boot: str) -> FailureKey:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return ("report", report_boot, digest) if report_boot else ("envelope", envelope_boot, digest)


def _digest(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _entry(value: object) -> FailureKey | None:
    if isinstance(value, list) and len(value) == 3:
        scope, boot, digest = value
        if scope in ("report", "envelope", "legacy") and wire_identity(boot) and _digest(digest):
            return scope, boot, digest
    return None


def reconcile(
    previous: object, *, accepted: list[FailureKey], failed: list[FailureKey]
) -> dict | None:
    entries: dict[FailureKey, None] = {}
    overflow = legacy = False
    if isinstance(previous, dict):
        if previous.get("version") == LEDGER_VERSION and isinstance(previous.get("entries"), list):
            records = previous["entries"]
            overflow = previous.get("overflow_unknown") is not False or len(records) > MAX_FAILURES
            legacy = previous.get("legacy_unknown") is not False
            for value in records[:MAX_FAILURES]:
                entry = _entry(value)
                if entry is None:
                    legacy = True
                else:
                    entries[entry] = None
        else:
            # The previous implementation could lose whole failures and used the
            # envelope's boot for every report. Keep what is known; do not auto-clear.
            legacy = True
            old = previous.get("fingerprints")
            if isinstance(old, list):
                boot = wire_identity(previous.get("boot_id")) or "legacy-unknown"
                overflow = len(old) > MAX_FAILURES
                for value in old[:MAX_FAILURES]:
                    if _digest(value):
                        entries[("legacy", boot, value)] = None
    elif previous is not None:
        legacy = True

    for key in accepted:
        entries.pop(key, None)
    for key in failed:
        if key in entries:
            continue
        if len(entries) == MAX_FAILURES:
            overflow = True
        else:
            entries[key] = None

    if not (entries or overflow or legacy):
        return None
    return {
        "version": LEDGER_VERSION,
        "entries": [list(key) for key in entries],
        "overflow_unknown": overflow,
        "legacy_unknown": legacy,
    }
