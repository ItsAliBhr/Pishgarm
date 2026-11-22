"""Clause rendering and consistency rules (doc 06 §6.2)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.core import money
from app.core.draft import CLAUSE_GROUPS, ClauseSel, Draft
from app.core.validators import iban_error

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
INSTALL_WORD = "نصب"


@dataclass
class Issue:
    level: str        # "warning" (yellow, does not block) / "error" (blocks issuing)
    message: str

    @property
    def blocking(self) -> bool:
        return self.level == "error"


def placeholders(text: str) -> list[str]:
    return PLACEHOLDER.findall(text or "")


def fill(text: str, values: dict) -> str:
    """Replace {name} with values[name]; unknown names are left in place (and reported)."""
    def repl(m):
        v = values.get(m.group(1))
        return m.group(0) if v is None else str(v)
    return PLACEHOLDER.sub(repl, text or "")


def _num(v, default=0) -> Decimal:
    try:
        return money.parse_decimal(v) if v not in (None, "") else Decimal(default)
    except money.MoneyError:
        return Decimal(default)


def is_service_line(line) -> bool:
    return bool(line.is_service or line.category == "installation" or INSTALL_WORD in (line.description or ""))


def clause_values(draft: Draft, sel: ClauseSel) -> dict:
    """Defaults ← user values ← computed values, all formatted as strings."""
    vals: dict = {}
    for name, spec in (sel.variables or {}).items():
        if isinstance(spec, dict) and "default" in spec:
            vals[name] = spec["default"]
    vals.update({k: v for k, v in (sel.values or {}).items() if v not in (None, "")})

    totals = draft.totals
    payable = totals.payable
    advance_percent = _num(vals.get("advance_percent"), _doc_advance_percent(draft))
    computed = {
        "vat_percent": money.fmt_percent(draft.vat_percent),
        "payable": money.fmt_int(payable),
        "advance_percent": money.fmt_percent(advance_percent),
        "advance_amount": money.fmt_int(money.percent_of(payable, advance_percent)),
        "rest_percent": money.fmt_percent(100 - advance_percent),
        "rest_amount": money.fmt_int(payable - money.percent_of(payable, advance_percent)),
    }
    if sel.code == "PAY_SPLIT_CARDS_INSTALL":
        install_pct = _num(vals.get("install_advance_percent"), 60)
        goods = sum(l.total for l in draft.lines if not is_service_line(l))
        service = sum(l.total for l in draft.lines if is_service_line(l))
        base = goods + money.percent_of(service, install_pct)
        # VAT applies to what is paid in advance as well
        if draft.vat_enabled:
            base += money.vat_amount(base, draft.vat_percent)
        computed["advance_amount"] = money.fmt_int(base)
        computed["install_advance_percent"] = money.fmt_percent(install_pct)
    if draft.accounts:
        a = draft.accounts[0]
        computed.update({"iban": a.iban, "bank": a.bank, "holder": a.holder})
    for k, v in computed.items():
        if k in ("advance_percent", "install_advance_percent") and k in vals:
            vals[k] = money.fmt_percent(_num(vals[k]))
            continue
        vals[k] = v
    for k, v in list(vals.items()):
        if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
            vals[k] = money.fmt_percent(v)
    return vals


def _doc_advance_percent(draft: Draft) -> Decimal:
    for c in draft.clauses:
        if c.code == "PAY_ADV":
            v = (c.values or {}).get("advance_percent")
            if v in (None, ""):
                v = (c.variables or {}).get("advance_percent", {}).get("default", 0)
            return _num(v)
    return Decimal(0)


def render_clause(draft: Draft, sel: ClauseSel) -> str:
    return fill(sel.template, clause_values(draft, sel))


def ordered(draft: Draft) -> list[ClauseSel]:
    """Group order payment → delivery → tax → site → other → note; user order kept inside a
    group; the account clause goes last (doc 05: «بند حساب آخر قرار می‌گیرد»)."""
    order = {g: i for i, g in enumerate(CLAUSE_GROUPS)}
    items = sorted(enumerate(draft.clauses), key=lambda p: (p[1].code == "PAY_TO_ACCOUNT",
                                                             order.get(p[1].group, 99), p[0]))
    return [c for _, c in items]


def rendered_by_group(draft: Draft) -> dict[str, list[str]]:
    out = {g: [] for g in CLAUSE_GROUPS}
    for c in ordered(draft):
        out.setdefault(c.group, []).append(render_clause(draft, c))
    return out


def check(draft: Draft) -> list[Issue]:
    """Consistency warnings and blocking errors for the selected clauses."""
    issues: list[Issue] = []
    codes = {c.code for c in draft.clauses if c.code}
    for c in draft.clauses:
        req = c.requires or {}
        if "vat_enabled" in req and bool(req["vat_enabled"]) != bool(draft.vat_enabled):
            state = "روشن" if draft.vat_enabled else "خاموش"
            issues.append(Issue("warning", f"بند «{_short(c)}» با ارزش افزوده‌ی {state} نمی‌خواند."))
        for ex in c.excludes or []:
            if ex == "category:installation" and any(is_service_line(l) for l in draft.lines):
                issues.append(Issue("warning", f"بند «{_short(c)}» با ردیف نصب در جدول اقلام تناقض دارد."))
        if c.code == "OTH_VALIDITY" and draft.kind in ("invoice", "statement"):
            issues.append(Issue("warning", "بند اعتبار پیش‌فاکتور در فاکتور/صورت‌وضعیت آمده است."))
        if c.code == "PAY_ADV":
            pct = _num(clause_values(draft, c).get("advance_percent"))
            if pct < 0 or pct > 100:
                issues.append(Issue("error", "درصد پیش‌پرداخت باید بین ۰ تا ۱۰۰ باشد (جمع درصدهای پرداخت ≠ ۱۰۰)."))
        missing = placeholders(render_clause(draft, c))
        if missing:
            if c.code == "PAY_TO_ACCOUNT" or set(missing) & {"iban", "bank", "holder"}:
                issues.append(Issue("error", "بند واریز به شبا انتخاب شده ولی هیچ حسابی انتخاب نشده است."))
            else:
                issues.append(Issue("error", f"جای‌خالیِ پرنشده در بند «{_short(c)}»: {', '.join(missing)}"))
    if {"TAX_NET_ALL_DEDUCTIONS", "TAX_NET_PLUS_VAT"} <= codes:
        issues.append(Issue("warning", "دو بند مالیاتی متناقض انتخاب شده است (کسورات بر عهده‌ی کارفرما / ارزش افزوده اضافه می‌شود)."))
    if {"TAX_NOT_CALCULATED", "TAX_INCLUDED"} <= codes:
        issues.append(Issue("warning", "بندهای «مالیات لحاظ نشده» و «مالیات لحاظ شده» با هم آمده‌اند."))
    for a in draft.accounts:
        err = iban_error(a.iban)
        if err:
            issues.append(Issue("error", f"شبای حساب {a.bank}: {err}"))
    return issues


def _short(c: ClauseSel, n: int = 45) -> str:
    t = c.template.replace("\n", " ")
    return t if len(t) <= n else t[:n] + "…"
