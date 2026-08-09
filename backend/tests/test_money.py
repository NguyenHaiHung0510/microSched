"""Executable boundary tests for the money plaintext contract (no DB needed)."""

from decimal import Decimal

import pytest

from app.domain import money


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal(0), "0"),
        (Decimal("1"), "1"),
        (Decimal("1.0"), "1"),
        (Decimal("0.0"), "0"),
        (Decimal("-0"), "0"),
        (Decimal("0E+5"), "0"),
        (Decimal("100.00"), "100"),
        (Decimal("1E+2"), "100"),
        (Decimal("1E+13"), "10000000000000"),  # 14 digits via exponent
        (Decimal("600000"), "600000"),
        (Decimal("99999999999999"), "99999999999999"),  # 14 digits (C2 ceiling)
    ],
)
def test_to_storage_round_trip(value, expected):
    stored = money.to_storage(value)
    assert stored == expected
    assert money.from_storage(stored) == value


def test_to_storage_rejects_fractional():
    with pytest.raises(ValueError):
        money.to_storage(Decimal("100.50"))


def test_to_storage_rejects_negative():
    with pytest.raises(ValueError):
        money.to_storage(Decimal("-5"))


def test_to_storage_rejects_over_14_digits():
    with pytest.raises(ValueError):
        money.to_storage(Decimal("100000000000000"))  # 15 digits
    with pytest.raises(ValueError):
        money.to_storage(Decimal("1E+14"))  # 15 digits via exponent
    with pytest.raises(ValueError):
        money.to_storage(Decimal("100000000000000.0"))  # 15 digits, integral


def test_from_storage_rejects_garbage():
    for raw in ("", "abc", "1.5", "-1", "01", "600000.00", " 600000"):
        with pytest.raises(ValueError):
            money.from_storage(raw)


def test_from_storage_rejects_unknown_future_shapes():
    with pytest.raises(ValueError):
        money.from_storage("enc:v1:AAAA")


def test_from_storage_accepts_leading_zero_only_for_zero():
    assert money.from_storage("0") == Decimal(0)
    with pytest.raises(ValueError):
        money.from_storage("00")
