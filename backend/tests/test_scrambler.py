"""Unit tests for the structure-preserving QA scrambler."""

import os

from app.core.scrambler import scramble_text
from scripts.prepare_qa_branch import _decrypt_value, _encrypt_value


def test_scramble_preserves_length():
    raw = "- [ ] Khám răng ở BV Bạch Mai lúc 09:30 (500k tiền mặt)"
    scrambled = scramble_text(raw)
    assert len(scrambled) == len(raw)
    assert scrambled.startswith("- [ ] ")
    assert "(" in scrambled and ")" in scrambled
    assert ":" in scrambled
    assert scrambled != raw


def test_scramble_preserves_markdown_numbered_lists():
    raw = "1. Mục đầu tiên\n2. Mục thứ hai\n10. Mục thứ mười"
    scrambled = scramble_text(raw)
    lines = scrambled.splitlines()
    assert lines[0].startswith("1. ")
    assert lines[1].startswith("2. ")
    assert lines[2].startswith("10. ")
    assert len(scrambled) == len(raw)


def test_scramble_preserves_markdown_headings_and_tables():
    raw = "# Tiêu đề 1\n## Tiêu đề 2\n| Cột 1 | Cột 2 |\n|---|---|\n| A | B |"
    scrambled = scramble_text(raw)
    assert scrambled.startswith("# ")
    assert "## " in scrambled
    assert "|---|---|" in scrambled
    assert len(scrambled) == len(raw)


def test_scramble_deterministic_with_same_salt():
    raw = "Một chuỗi văn bản kiểm thử bí mật 123456"
    res1 = scramble_text(raw, salt="salt_a")
    res2 = scramble_text(raw, salt="salt_a")
    res3 = scramble_text(raw, salt="salt_b")
    assert res1 == res2
    assert res1 != res3
    assert len(res1) == len(raw)


def test_scramble_digits_are_scrambled():
    raw = "Số CCCD: 012345678901, số thẻ: 987654321"
    scrambled = scramble_text(raw)
    assert len(scrambled) == len(raw)
    assert "012345678901" not in scrambled
    assert "987654321" not in scrambled


def test_scramble_cjk_characters():
    raw = "买奶茶 (Mua trà sữa)"
    scrambled = scramble_text(raw)
    assert len(scrambled) == len(raw)
    assert "(" in scrambled and ")" in scrambled
    assert scrambled != raw


def test_qa_branch_crypto_helpers():
    key = os.urandom(32)
    qa_key = os.urandom(32)
    raw_text = "- [ ] Đi khám răng tại BV Bạch Mai lúc 09:30"
    encrypted = _encrypt_value(key, raw_text)
    assert encrypted.startswith("enc:v1:")
    decrypted = _decrypt_value(key, encrypted)
    assert decrypted == raw_text
    re_encrypted = _encrypt_value(qa_key, scramble_text(decrypted))
    assert _decrypt_value(qa_key, re_encrypted) != raw_text
    assert len(_decrypt_value(qa_key, re_encrypted)) == len(raw_text)
