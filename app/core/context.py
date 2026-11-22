"""Build the docxtpl context for each template (doc 05 §5.2). All numbers are passed as
formatted strings; the templates never compute anything. Purchase prices, markups and
supplier names never enter a context."""
from __future__ import annotations

from app.core import clauses as clause_rules
from app.core import jalali, money
from app.core.draft import TITLE_BY_KIND, Draft
from app.core.letters import build_addressee, build_body, build_subject
from app.core.num2words_fa import rial_words

PARTY_KEYS = ("name", "address", "postal_code", "national_id", "economic_code", "registration_no",
              "phone", "fax")
BUYER_SUPPLIED_NOTE = "اقلامی که با رنگ دیگر مشخص شده است توسط خریدار تأمین می‌گردد."


def _party_block(d: dict, hide_national_id: bool = False) -> dict:
    out = {k: (d.get(k) or "") for k in PARTY_KEYS}
    if not out["phone"] and d.get("mobile"):
        out["phone"] = d["mobile"]
    if hide_national_id:
        out["national_id"] = ""
    return out


def proforma_context(draft: Draft, persian_digits: bool = False) -> dict:
    fi = lambda n: money.fmt_int(n, persian_digits)  # noqa: E731
    t = draft.totals
    items = []
    for i, l in enumerate(draft.lines, 1):
        items.append({
            "idx": i, "description": l.description, "unit": l.unit,
            "qty": money.fmt_decimal(l.qty),
            "unit_price": fi(l.unit_price) if l.unit_price else "-",
            "total": fi(l.total) if l.unit_price else "-",
        })
    groups = clause_rules.rendered_by_group(draft)
    flat = [clause_rules.render_clause(draft, c) for c in clause_rules.ordered(draft)]
    personal = draft.issuer.get("kind") == "personal"
    return {
        "title": draft.title or TITLE_BY_KIND.get(draft.kind, ""),
        "date": jalali.fmt(draft.date),
        "number": draft.number,
        "seller": _party_block(draft.issuer, hide_national_id=personal and not draft.show_seller_national_id),
        "buyer": _party_block(draft.party),
        "items": items,
        "totals": {
            "vat_enabled": t.vat_enabled,
            "subtotal": fi(t.subtotal),
            "subtotal_words": rial_words(t.subtotal),
            "vat_percent": money.fmt_percent(t.vat_percent),
            "vat": fi(t.vat),
            "payable_label": "قابل پرداخت" if t.vat_enabled else "جمع کل",
            "payable": fi(t.payable),
            "payable_words": rial_words(t.payable),
        },
        "clauses": flat,
        "payment_clauses": groups.get("payment", []),
        "delivery_clauses": groups.get("delivery", []),
        "other_clauses": groups.get("tax", []) + groups.get("site", []) + groups.get("other", []),
        "note_clauses": groups.get("note", []),
        "closing": draft.closing or "با احترام",
        "signer_name": draft.issuer.get("signer_name", ""),
        "show_stamp": bool(draft.show_stamp),
        "show_signature": bool(draft.show_signature),
    }


def letter_context(draft: Draft) -> dict:
    lines = draft.addressee_lines
    if lines is None:
        from app.core.letters import BUILTIN_ADDRESSEE_FORMATS
        lines = build_addressee(BUILTIN_ADDRESSEE_FORMATS[0], draft.party, draft.contact)
    personal = draft.issuer.get("kind") == "personal"
    return {
        "header_line": draft.header_line if personal else "",
        "date": jalali.fmt(draft.date),
        "number": draft.number,
        "attachment": draft.attachment_text or "",
        "addressee_lines": [l for l in lines if l.strip()],
        "subject": build_subject(draft) if draft.letter_type else draft.subject,
        "salutation": draft.salutation,
        "body_paragraphs": build_body(draft),
        "closing": draft.closing,
        "signer_name": draft.issuer.get("signer_name", ""),
        "signer_title": draft.issuer.get("signer_title", "") if not personal else "",
        "show_stamp": bool(draft.show_stamp),
        "show_signature": bool(draft.show_signature),
        "signature_image": (draft.issuer.get("signature_image") or "") if (personal and draft.show_signature) else "",
    }


def attachment_list_context(draft: Draft) -> dict:
    items = [{"idx": i, "description": l.description, "qty": money.fmt_decimal(l.qty),
              "unit": l.unit, "buyer_supplied": bool(l.buyer_supplied), "emphasis": bool(l.emphasis)}
             for i, l in enumerate(draft.lines, 1)]
    project_title = (draft.project or {}).get("title", "")
    return {
        "title": draft.list_title or (f"لیست اقلام {project_title}".strip()),
        "subtitle": draft.list_subtitle,
        "items": items,
        "footer_note": BUYER_SUPPLIED_NOTE if any(i["buyer_supplied"] for i in items) else "",
    }


def build_context(draft: Draft, persian_digits: bool = False) -> dict:
    if draft.kind == "letter":
        return letter_context(draft)
    if draft.kind == "attachment_list":
        return attachment_list_context(draft)
    return proforma_context(draft, persian_digits)


def template_name(draft: Draft) -> str:
    i = draft.issuer
    if draft.kind == "letter":
        return i.get("letter_template") or f"letter_{i.get('kind', 'company')}.docx"
    if draft.kind == "attachment_list":
        return "attachment_list.docx"
    key = {"proforma": "proforma_template", "invoice": "invoice_template",
           "statement": "statement_template"}[draft.kind]
    return i.get(key) or f"proforma_{i.get('kind', 'company')}.docx"


def all_output_text(context: dict) -> str:
    """Every string in a context, for confidentiality checks."""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(context)
    return "\n".join(out)
