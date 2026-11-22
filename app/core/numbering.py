"""Document numbering (doc 05 §5.4).

Tokens: {yyyy} {yyy} {yy} year; {mm} two-digit month; {m} month without padding;
{seq:0N} sequence; {kind} ن/پ/ف/ص. The personal pattern is {yyy}{m}{seq:02} — the archive's
401100, 401101, 401202 are year 401, month 1/1/2, number 00/01/02 (doc 05 example 405901)."""
from __future__ import annotations

import re

KIND_LETTER = {"letter": "ن", "proforma": "پ", "invoice": "ف", "statement": "ص",
               "attachment_list": "ل"}
INVOICE_FAMILY = {"proforma", "invoice", "statement", "attachment_list"}


def counter_group(kind: str, shared_letter_invoice: bool = False) -> str:
    if shared_letter_invoice:
        return "all"
    return "letter" if kind == "letter" else "invoice_family"


def period_key(scope: str, jyear: int, jmonth: int) -> str:
    if scope == "per_month":
        return f"{jyear:04d}-{jmonth:02d}"
    if scope == "continuous":
        return "all"
    return f"{jyear:04d}"


def format_number(pattern: str, seq: int, jyear: int, jmonth: int, kind: str = "") -> str:
    def repl(m):
        tok, width = m.group(1), m.group(2)
        if tok == "seq":
            return f"{seq:0{int(width)}d}" if width else str(seq)
        return {"yyyy": f"{jyear:04d}", "yyy": f"{jyear:04d}"[-3:], "yy": f"{jyear:04d}"[-2:],
                "mm": f"{jmonth:02d}", "m": str(jmonth), "kind": KIND_LETTER.get(kind, "")}.get(tok, m.group(0))
    return re.sub(r"\{(seq|yyyy|yyy|yy|mm|m|kind)(?::0?(\d+))?\}", repl, pattern or "{seq}")
