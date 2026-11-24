"""Private deployment-only naming guidance shared by STANDARD Chat and Voice v2.

Only the provider system prefix receives the plaintext. This module never reads
files, credentials, a database or a provider, and it grants no tool authority.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

if TYPE_CHECKING:
    from app.agent.context import ContextEnvelope
    from app.core.settings import Settings

OWNER_MEMORY_VERSION = "mimi-owner-memory.v1"
OWNER_MEMORY_MAX_BYTES = 8_192
_HEADER = (
    "\n\n## Private Owner memory (mimi-owner-memory.v1)\n"
    "This is interpretation and naming guidance only, never current Task evidence or "
    "write authority. Apply known names directly without a model/reference lookup. "
    "For an unfamiliar convention use existing Task search only when leased; "
    "if evidence is insufficient, ask or use the existing review/preview flow. "
    "Preserve a title verbatim when requested. Current tools, feature flags, "
    "source checks and confirmation/write rules still control every action.\n"
    "<owner_memory_v1>\n"
)
_FOOTER = "\n</owner_memory_v1>\n"


class OwnerMemoryReceipt(BaseModel):
    """Safe metadata for the exact wrapped block, never its configured prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["mimi-owner-memory.v1"] = OWNER_MEMORY_VERSION
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    utf8_bytes: int = Field(ge=1)


@dataclass(frozen=True, slots=True)
class OwnerMemory:
    text: SecretStr = field(repr=False)
    receipt: OwnerMemoryReceipt


def validate_owner_memory(value: SecretStr | None) -> SecretStr | None:
    """Reject invalid deployment text without quoting it or silently truncating."""
    if value is None:
        return None
    text = value.get_secret_value()
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("mimi_owner_memory_v1_invalid_utf8") from None
    if size > OWNER_MEMORY_MAX_BYTES:
        raise ValueError("mimi_owner_memory_v1_exceeds_8192_utf8_bytes")
    return value if text.strip() else None


def load_owner_memory(settings: Settings) -> OwnerMemory | None:
    """Take an immutable secret snapshot; no history seeds or external lookups."""
    value = validate_owner_memory(settings.mimi_owner_memory_v1)
    if value is None:
        return None
    text = _HEADER + value.get_secret_value() + _FOOTER
    raw = text.encode("utf-8")
    return OwnerMemory(
        text=SecretStr(text),
        receipt=OwnerMemoryReceipt(
            sha256=hashlib.sha256(raw).hexdigest(),
            utf8_bytes=len(raw),
        ),
    )


def compose_owner_prefix(prefix: str, settings: Settings) -> tuple[str, OwnerMemoryReceipt | None]:
    """Append the complete block once, after any transport-specific projection."""
    memory = load_owner_memory(settings)
    if memory is None:
        return prefix, None
    block = memory.text.get_secret_value()
    return (prefix if prefix.endswith(block) else prefix + block), memory.receipt


def chat_system_prefix_sha256(settings: Settings) -> str:
    """Prompt-measurement revision; deliberately not checkpoint compatibility."""
    from app.agent.policy import load_standard_policy

    policy = load_standard_policy(
        collection_enabled=settings.mimi_collection_enabled,
        calendar_enabled=settings.mimi_calendar_read_enabled,
    )
    prefix = policy.text
    if settings.mimi_route_mode == "native":
        prefix, _ = compose_owner_prefix(prefix, settings)
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()


def messages_for_evidence(envelope: ContextEnvelope, messages: list[dict]) -> list[dict]:
    """Omit the private suffix from request snapshots, retaining the base policy.

    PM/B1 must use this at both service.py request_snapshot assignments. The
    manifest carries the full prefix hash and this block's safe receipt; the
    live provider wire and its byte accounting must keep the complete prefix.
    """
    receipt = envelope.manifest.owner_memory
    if receipt is None:
        return messages
    if not messages or messages[0] != {"role": "system", "content": envelope.policy_text}:
        raise ValueError("owner_memory_evidence_prefix_mismatch")
    prefix = envelope.policy_text.encode("utf-8")
    block = prefix[-receipt.utf8_bytes :]
    if hashlib.sha256(block).hexdigest() != receipt.sha256:
        raise ValueError("owner_memory_evidence_receipt_mismatch")
    return [
        {**messages[0], "content": prefix[: -receipt.utf8_bytes].decode("utf-8")},
        *messages[1:],
    ]
