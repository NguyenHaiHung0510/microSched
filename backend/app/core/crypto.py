"""App-level AES-GCM for the columns that must never reach Neon in the clear.

schema-physical-brief.md §7.1 keeps the master key inside this process and applies
it just before a value is written and just after it is read, so Postgres - and any
leaked Neon dump or backup - only ever sees ciphertext. pgcrypto was rejected for
that exact reason: it would carry the key through SQL to the server.

Every ciphertext is stamped with a fixed ``enc:v1:`` version prefix. Migration 0001
pins the encrypted columns with ``CHECK (... LIKE 'enc:v1:%')``, so a value written
under any other scheme is refused by the database rather than silently stored - a
real format change therefore means a new prefix plus a migration, never an edit here.
"""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.settings import get_settings

# The one public constant: the version tag on every ciphertext, matched by the DB
# CHECK constraints. See the module docstring for why it is hard-coded.
CIPHERTEXT_PREFIX = "enc:v1:"

# 12 bytes is the standard GCM nonce width; a fresh one per call is what keeps
# encrypt() non-deterministic. 32 bytes is the AES-256 key the env value decodes to.
_NONCE_BYTES = 12
_KEY_BYTES = 32

# One operator-facing message for every way the key can be absent or malformed.
_KEY_ERROR = "ENCRYPTION_MASTER_KEY missing/invalid (need 32-byte urlsafe-base64)"


@lru_cache(maxsize=1)
def _cipher() -> AESGCM:
    """Build the AES-GCM object once, lazily, from the configured master key.

    Lazy by contract: importing this module must succeed with no key set - tests set
    the key after import, and the app may import before its environment is complete.
    The key is only required the first time something is actually encrypted.
    """
    raw = get_settings().encryption_master_key
    try:
        key = base64.urlsafe_b64decode(raw) if raw else b""
    except (ValueError, TypeError) as exc:
        # Malformed base64 collapses to the same missing/invalid verdict.
        raise RuntimeError(_KEY_ERROR) from exc
    if len(key) != _KEY_BYTES:
        raise RuntimeError(_KEY_ERROR)
    return AESGCM(key)


def encrypt(plaintext: str) -> str:
    """Seal one string as ``enc:v1:`` + urlsafe-base64(nonce ‖ ciphertext+tag).

    A fresh 12-byte nonce per call makes the output non-deterministic on purpose: the
    same plaintext never encrypts to the same string, so callers must not treat the
    result as stable (K19 dropped the unique index on names for exactly this reason).
    """
    nonce = os.urandom(_NONCE_BYTES)
    sealed = _cipher().encrypt(nonce, plaintext.encode("utf-8"), None)
    return CIPHERTEXT_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Invert :func:`encrypt`, failing loudly on anything that is not our ciphertext.

    A value without the prefix is corrupt or mis-routed and raises ``ValueError``
    rather than being handed back untouched. A wrong key or tampered payload surfaces
    as ``cryptography.exceptions.InvalidTag``, left to propagate on purpose so that
    tampering can never be mistaken for a successful read.
    """
    if not is_encrypted(ciphertext):
        raise ValueError("value is not enc:v1: ciphertext")
    blob = base64.urlsafe_b64decode(ciphertext.removeprefix(CIPHERTEXT_PREFIX))
    nonce, sealed = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return _cipher().decrypt(nonce, sealed, None).decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Report whether a value already carries the ciphertext prefix.

    Lets a caller decide whether a decrypt (or a re-encrypt) is needed without ever
    touching the key.
    """
    return value.startswith(CIPHERTEXT_PREFIX)
