"""Integer → Persian words, in the style of the company's documents (doc 06 §6.1):
zeros are skipped and «هزار» is said instead of «یک هزار»."""
from __future__ import annotations

_ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = ["", "هزار", "میلیون", "میلیارد", "هزار میلیارد", "میلیون میلیارد"]


def _three(n: int) -> str:
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if 10 <= r < 20:
        parts.append(_TEENS[r - 10])
    else:
        t, o = divmod(r, 10)
        if t:
            parts.append(_TENS[t])
        if o:
            parts.append(_ONES[o])
    return " و ".join(parts)


def num_to_words(n: int) -> str:
    n = int(n)
    if n == 0:
        return "صفر"
    if n < 0:
        return "منفی " + num_to_words(-n)
    groups = []
    i = 0
    while n:
        n, g = divmod(n, 1000)
        if g:
            if i == 1 and g == 1:
                groups.append("هزار")
            else:
                word = _three(g)
                groups.append(f"{word} {_SCALES[i]}".strip() if i < len(_SCALES) else word)
        i += 1
    return " و ".join(reversed(groups))


def rial_words(n: int) -> str:
    return f"{num_to_words(n)} ریال"
