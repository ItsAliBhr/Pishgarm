"""Text normalisation applied before storing (doc 03): Arabic ي/ك → ی/ک, Persian/Arabic digits → Latin."""
from __future__ import annotations

_TRANS = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک",
    **{chr(0x06F0 + i): str(i) for i in range(10)},   # Persian digits
    **{chr(0x0660 + i): str(i) for i in range(10)},   # Arabic-Indic digits
})


def normalize_text(value):
    if not isinstance(value, str):
        return value
    return value.translate(_TRANS).strip()


def to_persian_digits(value: str) -> str:
    return "".join(chr(0x06F0 + int(c)) if c.isascii() and c.isdigit() else c for c in str(value))
