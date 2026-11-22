"""Money math (doc 06 §6.1). Money is always integer Rial; quantities may be decimal."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.normalize import normalize_text

UNIT_FACTORS = {"rial": 1, "toman": 10, "million_toman": 10_000_000}
UNIT_LABELS = {"rial": "ریال", "toman": "تومان", "million_toman": "میلیون تومان"}


class MoneyError(ValueError):
    pass


def _clean_number(text) -> str:
    s = normalize_text(str(text if text is not None else ""))
    for sep in (",", "،", "٬", " ", "‌", "_"):
        s = s.replace(sep, "")
    return s.replace("٫", ".").replace("/", ".")


def parse_decimal(text) -> Decimal:
    s = _clean_number(text)
    if not s:
        return Decimal(0)
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise MoneyError(f"عدد معتبر نیست: {text}") from e


def to_rial(text_or_value, unit: str = "rial") -> int:
    """Parse user input in rial / toman / million toman into integer Rial."""
    value = text_or_value if isinstance(text_or_value, (int, Decimal)) else parse_decimal(text_or_value)
    return int((Decimal(value) * UNIT_FACTORS[unit]).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_rial(rial: int, unit: str) -> Decimal:
    v = Decimal(int(rial)) / UNIT_FACTORS[unit]
    return v.normalize() if v != v.to_integral() else v.quantize(Decimal(1))


def line_total(qty, unit_price: int) -> int:
    return int((Decimal(str(qty)) * int(unit_price)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def vat_amount(subtotal: int, percent) -> int:
    return int((Decimal(int(subtotal)) * Decimal(str(percent)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def percent_of(amount: int, percent) -> int:
    return vat_amount(amount, percent)


def markup_price(purchase_price: int, markup_percent, step: int = 1) -> int:
    raw = Decimal(int(purchase_price)) * (1 + Decimal(str(markup_percent)) / 100)
    step = max(int(step or 1), 1)
    return int((raw / step).to_integral_value(rounding=ROUND_CEILING)) * step


@dataclass(frozen=True)
class Totals:
    subtotal: int
    vat_enabled: bool
    vat_percent: Decimal
    vat: int
    payable: int


def compute_totals(line_totals, vat_enabled: bool, vat_percent) -> Totals:
    subtotal = sum(int(t) for t in line_totals)
    pct = Decimal(str(vat_percent or 0))
    vat = vat_amount(subtotal, pct) if vat_enabled else 0
    return Totals(subtotal, bool(vat_enabled), pct, vat, subtotal + vat)


def fmt_int(n, persian_digits: bool = False) -> str:
    s = f"{int(n):,}"
    if persian_digits:
        from app.core.normalize import to_persian_digits
        s = to_persian_digits(s).replace(",", "٬")
    return s


def fmt_decimal(v) -> str:
    """Quantities and percents: 2 → '2', 2.50 → '2.5', 16.67 → '16.67'."""
    d = Decimal(str(v))
    if d == d.to_integral():
        return f"{int(d):,}" if abs(d) >= 10000 else str(int(d))
    return format(d.normalize(), "f")


def fmt_percent(v) -> str:
    d = Decimal(str(v))
    return str(int(d)) if d == d.to_integral() else format(d.normalize(), "f")
