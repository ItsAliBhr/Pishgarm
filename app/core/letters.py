"""Letter text: addressee lines, subject and body (doc 05 §5.3)."""
from __future__ import annotations

import re

from app.core import jalali, money
from app.core.clauses import Issue, fill, placeholders, render_clause
from app.core.draft import Draft
from app.core.num2words_fa import num_to_words, rial_words

BUILTIN_ADDRESSEE_FORMATS = [
    "{company}\n{title_prefix} {contact_title} {contact_name}\n{position} محترم",
    "{title_prefix} {contact_title} {contact_name}\n{position} محترم {company}",
]


def contact_full(contact: dict | None) -> str:
    if not contact:
        return ""
    parts = [contact.get("title_prefix", ""), contact.get("honorific", ""), contact.get("name", "")]
    return " ".join(p for p in parts if p).strip()


def addressee_formats(settings_formats: list[str] | None) -> list[str]:
    out = list(BUILTIN_ADDRESSEE_FORMATS)
    for f in settings_formats or []:
        if f not in out:
            out.append(f)
    return out


def build_addressee(fmt: str, party: dict, contact: dict | None) -> list[str]:
    c = contact or {}
    values = {
        "company": party.get("name", ""),
        "title_prefix": c.get("title_prefix", "") if c.get("name") else "",
        "contact_title": c.get("honorific", "") if c.get("name") else "",
        "contact_name": c.get("name", ""),
        "position": c.get("position", ""),
    }
    lines = []
    for raw in fill(fmt, values).split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line == "محترم":
            continue
        if line.startswith("محترم "):          # «{position} محترم» with an empty position
            line = line[len("محترم "):]
        lines.append(line)
    return lines


def _fmt_field(spec: dict, value) -> str:
    if value in (None, ""):
        return ""
    t = spec.get("type")
    if t == "money":
        try:
            return money.fmt_int(int(value))
        except (TypeError, ValueError):
            return str(value)
    if t == "percent":
        return money.fmt_percent(value)
    return str(value)


def general_values(draft: Draft) -> dict:
    project = draft.project or {}
    vals = {
        "issuer_name": draft.issuer.get("name", ""),
        "issuer_national_id": draft.issuer.get("national_id", ""),
        "customer_name": draft.party.get("name", ""),
        "contact_full": contact_full(draft.contact),
        "project_title": project.get("title", ""),
        "contract_no": project.get("contract_no", ""),
        "contract_date": project.get("contract_date_jalali", ""),
        "today": jalali.fmt(draft.date),
    }
    if draft.accounts:
        a = draft.accounts[0]
        vals.update({"iban": a.iban, "bank": a.bank, "holder": a.holder})
    return vals


def field_values(draft: Draft) -> dict:
    """General variables overridden by the letter type's fields (formatted)."""
    vals = general_values(draft)
    specs = {f["name"]: f for f in (draft.letter_type or {}).get("fields", [])}
    for name, spec in specs.items():
        v = draft.fields.get(name)
        if v not in (None, ""):
            vals[name] = _fmt_field(spec, v)
        elif not spec.get("required") and not vals.get(name):
            vals[name] = ""   # optional and empty: leave a gap rather than a {placeholder}
    amount = draft.fields.get("amount")
    if amount not in (None, ""):
        try:
            a = int(amount)
            vals["amount_words"] = rial_words(a)
            vals["amount_toman"] = money.fmt_int(a // 10)
        except (TypeError, ValueError):
            pass
    return vals


def build_subject(draft: Draft) -> str:
    lt = draft.letter_type or {}
    if not lt:
        return draft.subject
    return re.sub(r"\s+", " ", fill(lt.get("subject_line", ""), field_values(draft))).strip()


def build_body(draft: Draft) -> list[str]:
    if draft.body_override is not None:
        return list(draft.body_override)
    lt = draft.letter_type or {}
    vals = field_values(draft)
    paras = [re.sub(r"[ \t]+", " ", fill(p, vals)).strip() for p in lt.get("body", [])]
    paras = [p for p in paras if p]
    if lt.get("with_items_table") and draft.lines:
        for i, l in enumerate(draft.lines, 1):
            text = f"{i}- {l.description}"
            if l.qty and (l.unit or l.qty != 1):
                text += f" – {money.fmt_decimal(l.qty)} {l.unit}".rstrip()
            if l.unit_price:
                text += f" – {money.fmt_int(l.total)} ریال"
            paras.append(text)
        if any(l.unit_price for l in draft.lines) and len(draft.lines) > 1:
            t = draft.totals
            paras.append(f"جمع کل: {money.fmt_int(t.payable)} ریال ({num_to_words(t.payable)} ریال)")
    for c in draft.clauses:
        if c.code == "PAY_TO_ACCOUNT":
            continue
        paras.append(render_clause(draft, c))
    if lt.get("with_account") and draft.accounts and not any("{iban}" in b for b in lt.get("body", [])):
        acc_clause = next((c for c in draft.clauses if c.code == "PAY_TO_ACCOUNT"), None)
        if acc_clause:
            paras.append(render_clause(draft, acc_clause))
        else:
            a = draft.accounts[0]
            paras.append(f"خواهشمند است مبلغ فوق به شماره شبای {a.iban} نزد بانک {a.bank} به نام {a.holder} واریز گردد.")
    elif any(c.code == "PAY_TO_ACCOUNT" for c in draft.clauses):
        paras.append(render_clause(draft, next(c for c in draft.clauses if c.code == "PAY_TO_ACCOUNT")))
    return paras


def check(draft: Draft) -> list[Issue]:
    issues = []
    lt = draft.letter_type or {}
    for f in lt.get("fields", []):
        if f.get("required") and draft.fields.get(f["name"]) in (None, "") and draft.body_override is None:
            issues.append(Issue("error", f"فیلد «{f.get('label', f['name'])}» خالی است."))
    for text in [build_subject(draft), *build_body(draft)]:
        miss = placeholders(text)
        if miss:
            issues.append(Issue("error", f"جای‌خالیِ پرنشده در متن نامه: {', '.join(sorted(set(miss)))}"))
            break
    if lt.get("with_account") and not draft.accounts:
        issues.append(Issue("warning", "این موضوع نامه شماره حساب لازم دارد ولی حسابی انتخاب نشده است."))
    return issues
