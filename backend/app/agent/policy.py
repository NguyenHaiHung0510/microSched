"""Versioned Mimi policy text, independent of provider serialization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

POLICY_ID = "mimi-standard-v2"
POLICY_SHA256 = "1ffc135a42c8cf04f3d6d17a2a987f399037d00fce48ff9b00425f318a4a44ab"
_POLICY_PATH = Path(__file__).with_name("policy") / "mimi-standard-v2.md"


@dataclass(frozen=True)
class MimiPolicy:
    policy_id: str
    sha256: str
    text: str


def load_standard_policy(*, collection_enabled: bool | None = None) -> MimiPolicy:
    """Fail closed on encoding or source drift from the versioned local candidate text."""

    if collection_enabled is None:
        from app.core.settings import get_settings

        collection_enabled = get_settings().mimi_collection_enabled
    path = _POLICY_PATH.with_name("mimi-standard-v3.md") if collection_enabled else _POLICY_PATH
    expected_sha256 = (
        "8cf35b4fdbb223410f9cfa6f22d8aa57a667e096d99a0444d0a73415d6b8afef"
        if collection_enabled
        else POLICY_SHA256
    )
    policy_id = "mimi-standard-v3" if collection_enabled else POLICY_ID
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n")
    if text.startswith("\ufeff") or "\r" in text or not text.endswith("\n"):
        raise ValueError("invalid_mimi_policy_encoding")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != expected_sha256:
        raise ValueError("mimi_policy_digest_mismatch")
    return MimiPolicy(policy_id=policy_id, sha256=digest, text=text)
