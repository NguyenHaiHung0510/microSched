"""Pure Argon2id and ASCII-format contract for the private display PIN."""

import secrets

from app.core.private_pin import hash_pin, is_valid_pin, verify_pin


def generated_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def test_pin_format_accepts_only_six_ascii_digits() -> None:
    assert is_valid_pin(generated_pin())
    for invalid in ("٦٦٦٦٦٦", "²²²²²²", "12345", "1234567", "12a456", "", " 12345"):
        assert not is_valid_pin(invalid)


def test_hash_round_trip_has_the_fixed_fly_safe_parameters() -> None:
    pin = generated_pin()
    wrong = generated_pin()
    while wrong == pin:
        wrong = generated_pin()

    stored = hash_pin(pin)

    assert "$argon2id$v=19$m=19456,t=2,p=1$" in stored
    assert verify_pin(stored, pin) is True
    assert verify_pin(stored, wrong) is False
