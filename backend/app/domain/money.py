"""Plaintext serialization contract for VND amounts stored as ciphertext.

Encrypted money columns (``tracker.amount``, ``entry.amount``, ``entry.list_amount``)
hold the ciphertext of a STRING, not a number. What that string looks like is a
contract between the write path and the read path — if the two sides disagreed,
``"600000"`` vs ``"600000.00"`` would round-trip to different ``Decimal`` values with
no test going red, and the break would surface only as a wrong sum.

Locked shape (K18 / K5, ``tracking-brief.md`` §10): plaintext money is a whole
decimal string, unsigned, unseparated, no trailing zeros — matching
``^(0|[1-9][0-9]{0,13})$`` (14 digits = the ``NUMERIC(14,0)`` ceiling of C2).
Validation happens here in the app layer because the physical column is ``TEXT``
(K18): K5's ``>= 0`` and C2's 14-digit ceiling no longer exist as DB CHECKs for these
encrypted columns, so this module is their replacement.
"""

import re
from decimal import Decimal

MAX_VND_DIGITS = 14

_STORAGE_RE = re.compile(r"^(0|[1-9][0-9]{0,13})$")


def to_storage(value: Decimal) -> str:
    """Validate and canonicalize a VND amount for storage; raise ``ValueError`` in Vietnamese.

    The amount must be an integer VND value: no fractional part (VND has none — K18),
    non-negative (0 is a valid trial amount — K5), and at most 14 digits (C2 ceiling).
    Money is always stored positive; the sign is a display concern of
    ``tracker.direction`` and must never be folded into the number (spec §3 item 6).
    """
    if not isinstance(value, Decimal):
        raise ValueError("Số tiền phải là một số thập phân.")
    if not value.is_finite():
        raise ValueError("Số tiền không hợp lệ.")
    if value < 0:
        raise ValueError("Số tiền không được âm.")
    if value != value.to_integral_value():
        raise ValueError("Số tiền phải là số nguyên (VND không có phần lẻ).")
    if len(value.as_tuple().digits) > MAX_VND_DIGITS:
        raise ValueError(f"Số tiền vượt quá {MAX_VND_DIGITS} chữ số.")
    return format(value, "f")


def from_storage(raw: str) -> Decimal:
    """Invert :func:`to_storage`; a non-matching string raises ``ValueError`` (never guesses).

    A stored value that does not match the canonical form means either a wrong key or
    a value written by a different path — both must fail loudly rather than returning
    ``Decimal(0)`` and silently dropping a charge.
    """
    if not isinstance(raw, str) or not _STORAGE_RE.match(raw):
        raise ValueError("Số tiền lưu trữ không hợp lệ.")
    return Decimal(raw)
