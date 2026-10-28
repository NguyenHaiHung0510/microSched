"""Notification text and the real UTF-8 transport budget, without arbitrary prose caps."""

import json
import re

from app.core import crypto

# RFC8291 supports at least3993 plaintext octets; leave room below that transport floor.
PUSH_JSON_MAX_BYTES = 3500
MORE_TEXT = "… Mở để xem đầy đủ."
PRIVATE_TITLE = "Nhắc nhở microSched"
PRIVATE_BODY = "Có một lời nhắc bạn đã đặt. Mở microSched để xem."


def public_text(value: str | None) -> str:
    """Call only after visibility classification; never surface unreadable ciphertext."""
    if not value:
        return ""
    try:
        value = crypto.decrypt(value) if crypto.is_encrypted(value) else value
    except Exception:
        return ""
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value).strip()


def encode_push_payload(payload: dict) -> str:
    """Keep full copy when it fits; shorten only display text, preserving routing metadata."""
    result = dict(payload)

    def encoded() -> str:
        return json.dumps(result, ensure_ascii=False)

    def fits() -> bool:
        return len(encoded().encode("utf-8")) <= PUSH_JSON_MAX_BYTES

    if fits():
        return encoded()
    for field in ("body", "title"):
        value = result.get(field)
        if not isinstance(value, str) or not value:
            continue
        suffix = MORE_TEXT if field == "body" else "…"
        result[field] = suffix
        if not fits():
            continue
        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            result[field] = value[:middle].rstrip() + suffix
            if fits():
                low = middle
            else:
                high = middle - 1
        result[field] = value[:low].rstrip() + suffix
        return encoded()
    raise ValueError("Notification routing metadata exceeds the push transport budget")
