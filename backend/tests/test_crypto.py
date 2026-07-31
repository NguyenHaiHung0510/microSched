"""Tests for the AES-GCM column seam (008a).

Self-contained by design: every test that needs a key mints a throwaway one in the
environment, so the suite never reads - and can never depend on - the real
ENCRYPTION_MASTER_KEY that lives in a developer's .env.
"""

import base64
import importlib
import os
from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidTag

from app.core import crypto
from app.core.settings import get_settings

# Diacritics exercise the utf-8 round trip; the money-like string mirrors a real
# encrypted column (subscription.amount / entry.amount are stored as ciphertext).
VIETNAMESE = "Đi họp lúc 9h sáng, nhớ mang hồ sơ đã ký tên — phòng 3."
MONEY = "1500000"


@pytest.fixture
def fresh_key(monkeypatch):
    """Point crypto at a random throwaway key, isolated from any real .env value."""
    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", key)
    # Both caches must drop so the new key is actually read this test.
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    yield
    # Leave nothing cached for the next test to trip over.
    get_settings.cache_clear()
    crypto._cipher.cache_clear()


@pytest.mark.parametrize(
    "plaintext",
    [
        "hello world",
        VIETNAMESE,
        "",
        "x" * 10_000,
        MONEY,
    ],
)
def test_round_trip_preserves_the_exact_string(fresh_key, plaintext):
    """decrypt(encrypt(x)) == x for ascii, diacritics, empty, long, and money-like."""
    assert crypto.decrypt(crypto.encrypt(plaintext)) == plaintext


def test_output_is_ascii_with_the_versioned_prefix(fresh_key):
    """The output must satisfy the DB CHECK: starts with enc:v1: and is pure ascii."""
    sealed = crypto.encrypt(VIETNAMESE)
    assert sealed.startswith("enc:v1:")
    assert sealed.startswith(crypto.CIPHERTEXT_PREFIX)
    assert sealed.isascii()


def test_encryption_is_non_deterministic(fresh_key):
    """A fresh nonce per call means two seals differ, yet both decrypt back."""
    first = crypto.encrypt(MONEY)
    second = crypto.encrypt(MONEY)
    assert first != second
    assert crypto.decrypt(first) == MONEY
    assert crypto.decrypt(second) == MONEY


def test_is_encrypted_separates_ciphertext_from_plaintext(fresh_key):
    """is_encrypted keys purely off the prefix, both directions."""
    assert crypto.is_encrypted(crypto.encrypt("secret")) is True
    assert crypto.is_encrypted("secret") is False
    assert crypto.is_encrypted(MONEY) is False


def test_tampered_ciphertext_raises_invalid_tag(fresh_key):
    """Flipping a bit in the sealed bytes must trip the GCM tag, never pass silently."""
    sealed = crypto.encrypt("secret")
    blob = bytearray(base64.urlsafe_b64decode(sealed.removeprefix(crypto.CIPHERTEXT_PREFIX)))
    blob[-1] ^= 0x01  # the trailing byte lives in the authentication tag
    tampered = crypto.CIPHERTEXT_PREFIX + base64.urlsafe_b64encode(bytes(blob)).decode("ascii")
    with pytest.raises(InvalidTag):
        crypto.decrypt(tampered)


def test_decrypting_without_the_prefix_raises_value_error(fresh_key):
    """A value that is not our ciphertext fails loudly instead of passing through."""
    with pytest.raises(ValueError):
        crypto.decrypt("khong-phai-ciphertext")


def test_import_does_not_require_a_key(monkeypatch):
    """Reloading the module with no key present must not raise: import is key-free."""
    monkeypatch.delenv("ENCRYPTION_MASTER_KEY", raising=False)
    crypto._cipher.cache_clear()
    # Reload re-executes the module top level; if it read the key eagerly this would
    # raise. It must not - the key is only touched inside encrypt/decrypt.
    importlib.reload(crypto)


def test_encrypt_without_a_key_raises_runtime_error(monkeypatch):
    """The key is demanded lazily, and its absence is a clear RuntimeError, not a crash."""
    no_key = SimpleNamespace(encryption_master_key=None)
    monkeypatch.setattr(crypto, "get_settings", lambda: no_key)
    crypto._cipher.cache_clear()
    with pytest.raises(RuntimeError):
        crypto.encrypt("secret")
    crypto._cipher.cache_clear()
