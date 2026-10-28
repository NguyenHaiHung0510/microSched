"""Versioned Mimi policy text, independent of provider serialization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

POLICY_ID = "mimi-standard-v2"
POLICY_SHA256 = "158ed655d52b157a4884be7ed46d16ecc9efd80370a93ee42fdae5513d24c670"
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
        "6be3cee63fe8edeb3e74eb3d94208ef27bee18c15034a19461c8e3cf920b8faf"
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


def checkpoint_policy_compatible(value: str, *, collection_enabled: bool) -> bool:
    """Only known semantic predecessors; frontier/content/source checks still apply."""
    original = (
        "642e13054d25e81cb53bd9488a6ffbf56f2aeb28646721091bd5d01007eb8c52"
        if collection_enabled
        else "1ffc135a42c8cf04f3d6d17a2a987f399037d00fce48ff9b00425f318a4a44ab"
    )
    previous = (
        {
            "c44ab32f8d41643f219a85cd8dda5371fbdf254410c89f92c281e8a44ea3561e",
            "3c30ed9767edede301f1408614d3a8fb413d3d3e25a8e9c27c9482b1a6ee6f87",
            "f9443f7dec59c73ef92a1feb8af5e4abb87198ab6a676603393c664d60b06c65",
        }
        if collection_enabled
        else set()
    )
    return value in {
        original,
        *previous,
        load_standard_policy(collection_enabled=collection_enabled).sha256,
    }
