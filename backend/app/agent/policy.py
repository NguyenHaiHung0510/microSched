"""Versioned Mimi policy text, independent of provider serialization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

POLICY_ID = "mimi-standard-v2"
POLICY_SHA256 = "60b25fe507b79f823a9db3c01ebe94a5e2aa848218164bade326bf153a73f5e1"
_POLICY_PATH = Path(__file__).with_name("policy") / "mimi-standard-v2.md"


@dataclass(frozen=True)
class MimiPolicy:
    policy_id: str
    sha256: str
    text: str


def load_standard_policy() -> MimiPolicy:
    """Fail closed on encoding or source drift from the versioned local candidate text."""

    raw = _POLICY_PATH.read_bytes()
    text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n")
    if text.startswith("\ufeff") or "\r" in text or not text.endswith("\n"):
        raise ValueError("invalid_mimi_policy_encoding")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != POLICY_SHA256:
        raise ValueError("mimi_policy_digest_mismatch")
    return MimiPolicy(policy_id=POLICY_ID, sha256=digest, text=text)
