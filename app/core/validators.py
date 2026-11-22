"""Validators (doc 06 §6.3). Each returns None when valid, or a short Persian error message."""
from __future__ import annotations

import re

from app.core.normalize import normalize_text


def clean_iban(value: str) -> str:
    v = normalize_text(value or "").upper().replace(" ", "").replace("-", "")
    if v and v[0].isdigit():
        v = "IR" + v
    return v


def iban_error(value: str) -> str | None:
    v = clean_iban(value)
    if not v.startswith("IR"):
        return "شبا باید با IR شروع شود."
    digits = v[2:]
    if not digits.isdigit():
        return "شبا فقط باید رقم داشته باشد."
    if len(digits) != 24:
        return f"این شبا {len(digits)} رقم دارد؛ باید ۲۴ رقم باشد."
    rearranged = digits[2:] + "1827" + digits[:2]  # I=18, R=27
    if int(rearranged) % 97 != 1:
        return "رقم کنترل شبا درست نیست؛ یکی از رقم‌ها اشتباه است."
    return None


def format_iban(value: str) -> str:
    v = clean_iban(value)
    return " ".join(v[i:i + 4] for i in range(0, len(v), 4))


def national_code_error(value: str) -> str | None:
    """کد ملی شخص: ۱۰ رقم با رقم کنترل."""
    v = normalize_text(value or "")
    if not re.fullmatch(r"\d{10}", v):
        return "کد ملی باید ۱۰ رقم باشد."
    if len(set(v)) == 1:
        return "کد ملی معتبر نیست."
    s = sum(int(v[i]) * (10 - i) for i in range(9)) % 11
    check = int(v[9])
    if (s < 2 and check == s) or (s >= 2 and check == 11 - s):
        return None
    return "رقم کنترل کد ملی درست نیست."


def company_id_error(value: str) -> str | None:
    """شناسه‌ی ملی شرکت: ۱۱ رقم با رقم کنترل."""
    v = normalize_text(value or "")
    if not re.fullmatch(r"\d{11}", v):
        return "شناسه‌ی ملی باید ۱۱ رقم باشد."
    d = int(v[9]) + 2
    coeffs = (29, 27, 23, 19, 17, 29, 27, 23, 19, 17)
    s = sum((int(v[i]) + d) * coeffs[i] for i in range(10)) % 11
    if s == 10:
        s = 0
    return None if s == int(v[10]) else "رقم کنترل شناسه‌ی ملی درست نیست."


def postal_code_error(value: str) -> str | None:
    v = normalize_text(value or "")
    return None if re.fullmatch(r"\d{10}", v) else "کد پستی باید ۱۰ رقم باشد."
