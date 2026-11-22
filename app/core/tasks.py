"""Automatic follow-up tasks (doc 06 §6.5). Pure: returns what to create; the service layer
stores them with a unique key so they are never duplicated."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core import jalali

DEFAULT_RULES = {
    "proforma_followup_workdays": 3,
    "advance_followup_days": 3,
    "invoice_payment_days": 14,
    "payment_letter_reply_days": 10,
}
PAYMENT_LETTER_CODES = {"PAY_INSTALLMENT", "PAY_SETTLEMENT", "PAY_RETENTION_RELEASE",
                        "PAY_EXPERT_VISIT", "PAY_REFUND_ADVANCE"}


@dataclass
class TaskSpec:
    rule: str
    title: str
    due: date


def on_issue(kind: str, issue_date: date, customer: str, letter_code: str | None = None,
             fields: dict | None = None, validity_days: int | None = None,
             rules: dict | None = None) -> list[TaskSpec]:
    r = {**DEFAULT_RULES, **(rules or {})}
    out = []
    if kind == "proforma":
        days = validity_days if validity_days else r["proforma_followup_workdays"]
        out.append(TaskSpec("proforma_followup", f"پیگیری تأیید پیش‌فاکتور {customer}",
                            jalali.add_workdays(issue_date, int(days))))
    elif kind in ("invoice", "statement"):
        label = "فاکتور" if kind == "invoice" else "صورت‌وضعیت"
        out.append(TaskSpec("payment_followup", f"پیگیری پرداخت {label} {customer}",
                            jalali.add_days(issue_date, r["invoice_payment_days"])))
    elif kind == "letter":
        if letter_code == "PAY_WARNING":
            try:
                n = int((fields or {}).get("deadline_days") or 10)
            except (TypeError, ValueError):
                n = 10
            out.append(TaskSpec("warning_deadline", f"بررسی پایان مهلت اخطار {customer}",
                                jalali.add_days(issue_date, n)))
        elif letter_code in PAYMENT_LETTER_CODES:
            out.append(TaskSpec("letter_reply", f"پیگیری پاسخ نامه به {customer}",
                                jalali.add_days(issue_date, r["payment_letter_reply_days"])))
    return out


def on_accepted(kind: str, d: date, customer: str, advance_text: str = "",
                rules: dict | None = None) -> list[TaskSpec]:
    r = {**DEFAULT_RULES, **(rules or {})}
    if kind != "proforma":
        return []
    title = f"پیگیری واریز پیش‌پرداخت {customer}" + (f" ({advance_text} ریال)" if advance_text else "")
    return [TaskSpec("advance_followup", title, jalali.add_days(d, r["advance_followup_days"]))]


def on_paid(kind: str, d: date, customer: str) -> list[TaskSpec]:
    if kind not in ("invoice", "statement"):
        return []
    return [TaskSpec("close_project", f"بستن پروژه یا ثبت سپرده‌ی {customer}", d)]


def on_handover(handover: date, retention_percent, retention_months: int, customer: str,
                project_title: str) -> list[TaskSpec]:
    if not retention_percent or float(retention_percent) <= 0:
        return []
    from app.core.money import fmt_percent
    return [TaskSpec("retention_release",
                     f"نامه‌ی آزادسازی سپرده‌ی {fmt_percent(retention_percent)}٪ {customer} – {project_title}",
                     jalali.add_months(handover, int(retention_months or 3)))]
