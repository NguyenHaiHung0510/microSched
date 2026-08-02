"""Argon2id seam for the six-digit private-display PIN.

The PIN only authorizes the display gate. It must never be used as encryption key
material, or as input to any key derivation: a one-million-value secret is suitable
only because the encrypted data remains protected by the independent app-held key.
This module deliberately does not import ``app.core.crypto`` and returns no key
material.
"""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

PIN_LENGTH = 6
_TIME_COST = 2
_MEMORY_COST_KIB = 19_456
_PARALLELISM = 1
_ASCII_DIGITS = frozenset("0123456789")


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    """Build the fixed, Fly-256MB-safe Argon2id hasher once and lazily.

    Do not replace these values with RFC_9106_LOW_MEMORY: that profile consumes
    64 MiB with four lanes. The PIN space remains only 10^6 values, so spending
    scarce production RAM would not turn it into an at-rest encryption secret.
    """
    return PasswordHasher(
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST_KIB,
        parallelism=_PARALLELISM,
    )


def is_valid_pin(value: str) -> bool:
    """Accept exactly six ASCII digits, not the wider Unicode digit category."""
    return len(value) == PIN_LENGTH and all(character in _ASCII_DIGITS for character in value)


def hash_pin(pin: str) -> str:
    """Hash one validated display PIN with the fixed Argon2id parameters."""
    if not is_valid_pin(pin):
        raise ValueError("PIN must contain exactly six ASCII digits")
    return _hasher().hash(pin)


def verify_pin(stored_hash: str, pin: str) -> bool:
    """Verify a PIN; a mismatch is ordinary, while a corrupt hash stays loud."""
    try:
        return _hasher().verify(stored_hash, pin)
    except VerifyMismatchError:
        return False
