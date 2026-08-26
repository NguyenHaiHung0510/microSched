"""Structure- and typography-preserving text scrambler for microSched QA data.

Replaces character glyphs with deterministic pseudo-random characters while preserving:
  - String length (1:1 character count)
  - Whitespace and line breaks (\r, \n, \t, spaces)
  - Markdown syntax tokens (#, ##, - [ ], - [x], *, _, |, >, `, ~)
  - Markdown list numbering (e.g. '1. ', '2. ')
  - Punctuation (. , : ; ! ? ( ) [ ] { } / \ @)
  - Character classes (Uppercase, Lowercase, Digits, Vietnamese diacritics, CJK)
"""

import hashlib
import re

VN_LOWER = (
    "aáàảãạăắằẳẵặâấầẩẫậeéèẻẽẹêếềểễệiíìỉĩịoóòỏõọôốồổỗộơớờởỡợuúùủũụưứừửữựyýỳỷỹỵbcdghklmnpqrstvx"
)
VN_UPPER = VN_LOWER.upper()
ASCII_DIGITS = "0123456789"

# Regex to identify markdown list prefixes at start of line, e.g. '1. ', '12. '
_MD_NUMBERED_LIST_RE = re.compile(r"^(\s*\d+\.\s+)")


def _char_rng(seed_bytes: bytes, index: int) -> int:
    """Produce a deterministic integer for position index given seed_bytes."""
    digest = hashlib.sha256(seed_bytes + index.to_bytes(4, "big")).digest()
    return int.from_bytes(digest[:4], "big")


def scramble_text(text: str, salt: str = "microsched_qa_salt") -> str:
    """Scramble a string preserving length, markdown syntax, and character classes."""
    if not text:
        return text

    seed = f"{salt}:{len(text)}".encode("utf-8")
    lines = text.split("\n")
    scrambled_lines = []
    global_idx = 0

    for line in lines:
        prefix = ""
        body = line

        # Preserve markdown ordered list numbering (e.g., '1. ', '2. ')
        match = _MD_NUMBERED_LIST_RE.match(line)
        if match:
            prefix = match.group(1)
            body = line[len(prefix) :]
            global_idx += len(prefix)

        line_result = []
        for char in body:
            rand_val = _char_rng(seed, global_idx)
            global_idx += 1

            if char in " \r\t#*_-[]():;,.?!/|`~>{}":
                # Preserve structural formatting & punctuation
                line_result.append(char)
            elif char in ASCII_DIGITS:
                # Scramble number with random digit
                line_result.append(ASCII_DIGITS[rand_val % 10])
            elif char in VN_LOWER:
                # Scramble with matching lowercase character
                line_result.append(VN_LOWER[rand_val % len(VN_LOWER)])
            elif char in VN_UPPER:
                # Scramble with matching uppercase character
                line_result.append(VN_UPPER[rand_val % len(VN_UPPER)])
            elif "\u4e00" <= char <= "\u9fff":
                # CJK Unified Ideographs
                line_result.append(chr(0x4E00 + (rand_val % (0x9FFF - 0x4E00 + 1))))
            elif char.isalpha():
                # Fallback Latin letter
                base = ord("A") if char.isupper() else ord("a")
                line_result.append(chr(base + (rand_val % 26)))
            else:
                line_result.append(char)
        scrambled_lines.append(prefix + "".join(line_result))

    return "\n".join(scrambled_lines)
