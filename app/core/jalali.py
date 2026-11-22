"""Jalali dates (display) ↔ Gregorian dates (storage). Workdays = all days except Friday."""
from __future__ import annotations

import re
from datetime import date, timedelta

import jdatetime

from app.core.normalize import normalize_text

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی",
          "بهمن", "اسفند"]
WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def today() -> date:
    return date.today()


def to_jalali(d: date) -> jdatetime.date:
    return jdatetime.date.fromgregorian(date=d)


def fmt(d: date | None, sep: str = "/") -> str:
    if not d:
        return ""
    j = to_jalali(d)
    return f"{j.year:04d}{sep}{j.month:02d}{sep}{j.day:02d}"


def compact(d: date) -> str:
    return fmt(d, "")


def parse(text: str) -> date | None:
    """'1405/9/1', '1405-09-01', '۱۴۰۵/۰۹/۰۱' → Gregorian date. Returns None if empty/invalid."""
    s = normalize_text(text or "")
    m = re.fullmatch(r"(\d{2,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})", s)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if y < 100:
        y += 1400
    try:
        return jdatetime.date(y, mo, d).togregorian()
    except ValueError:
        return None


def is_workday(d: date) -> bool:
    return d.weekday() != 4  # Friday


def add_workdays(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    remaining = abs(int(n))
    cur = d
    while remaining:
        cur += timedelta(days=step)
        if is_workday(cur):
            remaining -= 1
    return cur


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=int(n))


def add_months(d: date, months: int) -> date:
    """Add Jalali months (keeps the day, clamped to month length)."""
    j = to_jalali(d)
    total = j.year * 12 + (j.month - 1) + int(months)
    y, m = divmod(total, 12)
    m += 1
    day = j.day
    while day > 28:
        try:
            return jdatetime.date(y, m, day).togregorian()
        except ValueError:
            day -= 1
    return jdatetime.date(y, m, day).togregorian()


def month_length(y: int, m: int) -> int:
    if m <= 6:
        return 31
    if m <= 11:
        return 30
    return 30 if jdatetime.date(y, 1, 1).isleap() else 29
