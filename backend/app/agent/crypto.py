"""Per-conversation envelope encryption for Mimi persisted content."""

from __future__ import annotations

import base64
import os
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core import crypto

MIMI_CIPHERTEXT_PREFIX = "mimi:v1:"
_KEY_BYTES = 32
_NONCE_BYTES = 12


def create_wrapped_dek() -> str:
    """Create a fresh conversation DEK and wrap it with the app master key."""
    dek = os.urandom(_KEY_BYTES)
    encoded = base64.urlsafe_b64encode(dek).decode("ascii")
    return crypto.encrypt(encoded)


def unwrap_dek(wrapped_dek: str) -> bytes:
    """Unwrap and validate one conversation DEK."""
    try:
        dek = base64.urlsafe_b64decode(crypto.decrypt(wrapped_dek))
    except (ValueError, TypeError) as error:
        raise ValueError("invalid wrapped Mimi conversation key") from error
    if len(dek) != _KEY_BYTES:
        raise ValueError("invalid wrapped Mimi conversation key")
    return dek


def seal_content(dek: bytes, plaintext: str, *, aad: str) -> str:
    """Encrypt UTF-8 content with a conversation DEK and resource-bound AAD."""
    if len(dek) != _KEY_BYTES:
        raise ValueError("Mimi conversation key must be 32 bytes")
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
    return MIMI_CIPHERTEXT_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def open_content(dek: bytes, ciphertext: str, *, aad: str) -> str:
    """Decrypt resource-bound conversation content, failing closed on tampering."""
    if not ciphertext.startswith(MIMI_CIPHERTEXT_PREFIX):
        raise ValueError("value is not mimi:v1 ciphertext")
    blob = base64.urlsafe_b64decode(ciphertext.removeprefix(MIMI_CIPHERTEXT_PREFIX))
    if len(blob) <= _NONCE_BYTES:
        raise ValueError("invalid Mimi ciphertext")
    nonce, sealed = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(dek).decrypt(nonce, sealed, aad.encode("utf-8")).decode("utf-8")


def message_aad(conversation_id: UUID, sequence: int, role: str) -> str:
    return f"mimi-message:{conversation_id}:{sequence}:{role}"


def feedback_aad(conversation_id: UUID, feedback_id: UUID, field: str) -> str:
    return f"mimi-feedback:{conversation_id}:{feedback_id}:{field}"


def change_set_aad(conversation_id: UUID, change_set_id: UUID) -> str:
    return f"mimi-change-set:{conversation_id}:{change_set_id}:operation"
