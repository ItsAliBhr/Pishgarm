"""Document lifecycle: draft ↔ database, numbering, issuing, PDF, statuses, copies, versions."""
from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import paths
from app.core import clauses as clause_rules
from app.core import jalali, letters, money, numbering, pdf_tools
from app.core.context import all_output_text, attachment_list_context, build_context, template_name
from app.core.draft import TITLE_BY_KIND, ClauseSel, Draft, Line
from app.core.files import base_file_name, document_folder, versioned_path
from app.core.render import render_docx
from app.db.models import (Account, AuditLog, Clause, Contact, Document, DocumentAccount,
                           DocumentClause, DocumentFile, DocumentLine, Issuer, LetterType,
                           NumberCounter, Party, PartyClauseDefault, Project)
from app.db.repo import get_setting, output_root
from app.services import tasks as task_service
from app.services.convert import (account_info, clause_sel, contact_dict, issuer_dict,
                                  letter_type_dict, party_dict, project_dict)

log = logging.getLogger(__name__)
LEARN_THRESHOLD = 3


class IssueBlocked(Exception):
    def __init__(self, issues):
        super().__init__("; ".join(i.message for i in issues))
        self.issues = issues


@dataclass
class IssueResult:
    document_id: int
    number: str
    docx: Path
    pdf: Path | None = None
    pdf_error: str = ""
    warnings: list = field(default_factory=list)


def audit(s: Session, action: str, entity: str, entity_id: int | None, summary: str = "") -> None:
    s.add(AuditLog(action=action, entity=entity, entity_id=entity_id, summary=summary))


# ------------------------------------------------------------------ defaults

def default_contact(s: Session, party: Party) -> Contact | None:
    """Last contact used for this party, else its default contact."""
    last = s.scalar(select(Document.contact_id).where(Document.party_id == party.id,
                                                      Document.contact_id.is_not(None))
                    .order_by(Document.id.desc()).limit(1))
    if last:
        c = s.get(Contact, last)
        if c and not c.is_archived:
            return c
    live = [c for c in party.contacts if not c.is_archived]
    return next((c for c in live if c.is_default), live[0] if live else None)


def available_clauses(s: Session, kind: str) -> list[Clause]:
    k = "invoice" if kind == "statement" else kind
    rows = s.scalars(select(Clause).where(Clause.is_archived.is_(False)).order_by(Clause.sort_order)).all()
    return [c for c in rows if not c.applies_to or k in c.applies_to]


def default_clauses(s: Session, kind: str, issuer_code: str, party_id: int | None = None) -> list[ClauseSel]:
    k = "invoice" if kind == "statement" else kind
    learned = set()
    if party_id:
        learned = set(s.scalars(select(PartyClauseDefault.clause_id).where(
            PartyClauseDefault.party_id == party_id, PartyClauseDefault.doc_kind == k,
            PartyClauseDefault.use_count >= LEARN_THRESHOLD)))
    out = []
    for c in available_clauses(s, kind):
        if issuer_code in (c.default_for_issuers or []) or c.id in learned:
            if kind != "proforma" and c.code == "OTH_VALIDITY":
                continue
            if kind == "letter" and c.code != "PAY_TO_ACCOUNT":
                continue
            out.append(clause_sel(c))
    return out


def new_draft(s: Session, kind: str, issuer_id: int) -> Draft:
    issuer = s.get(Issuer, issuer_id)
    accounts = [a for a in s.scalars(select(Account).where(Account.code.in_(issuer.default_account_codes or []),
                                                           Account.active.is_(True)))]
    d = Draft(kind=kind, issuer=issuer_dict(issuer))
    d.title = TITLE_BY_KIND.get(kind, "")
    d.vat_enabled = bool(issuer.vat_enabled_by_default) and kind in ("proforma", "invoice", "statement")
    d.vat_percent = Decimal(str(issuer.default_vat_percent or get_setting(s, "vat_percent_default", 10) or 10))
    if not d.vat_percent:
        d.vat_percent = Decimal(str(get_setting(s, "vat_percent_default", 10)))
    d.show_stamp = bool(issuer.show_stamp_by_default)
    d.show_signature = True
    d.accounts = [account_info(a) for a in accounts]
    d.closing = "با تشکر" if kind == "letter" else "با احترام"
    d.attachment_text = get_setting(s, "attachment_default", "ندارد")
    headers = get_setting(s, "letter_header_lines", ["باسمه تعالی"]) or ["باسمه تعالی"]
    d.header_line = headers[0]
    d.salutation = (get_setting(s, "salutations", ["با سلام و احترام؛"]) or ["با سلام و احترام؛"])[0]
    d.show_seller_national_id = bool(get_setting(s, "personal_invoice_show_national_id", False))
    d.clauses = default_clauses(s, kind, issuer.code)
    d.input_currency = "million_toman"
    return d


def apply_party(s: Session, d: Draft, party_id: int | None, contact_id: int | None = None) -> None:
    party = s.get(Party, party_id) if party_id else None
    d.party = party_dict(party)
    contact = s.get(Contact, contact_id) if contact_id else (default_contact(s, party) if party else None)
    d.contact = contact_dict(contact)


def apply_letter_type(s: Session, d: Draft, letter_type_id: int | None) -> None:
    lt = s.get(LetterType, letter_type_id) if letter_type_id else None
    d.letter_type = letter_type_dict(lt)
    if lt:
        if lt.closing:
            d.closing = lt.closing
        # prefill fields from the project
        p = d.project or {}
        names = {f["name"] for f in lt.fields}
        for key, val in (("project_title", p.get("title")), ("contract_no", p.get("contract_no")),
                         ("contract_date", p.get("contract_date_jalali")),
                         ("retention_percent", p.get("retention_percent")),
                         ("handover_date", jalali.fmt(p["handover_date"]) if p.get("handover_date") else None)):
            if key in names and val not in (None, "") and d.fields.get(key) in (None, ""):
                d.fields[key] = money.fmt_percent(val) if isinstance(val, Decimal) else str(val)
        if "person_name" in names and not d.fields.get("person_name"):
            d.fields["person_name"] = d.issuer.get("name", "")
        keep = [c for c in d.clauses if c.code == "PAY_TO_ACCOUNT" and lt.with_account]
        d.clauses = keep if not lt.with_clauses else d.clauses


# ------------------------------------------------------------------ draft ↔ db

def draft_from_document(s: Session, doc: Document) -> Draft:
    d = Draft(kind=doc.kind, issuer=issuer_dict(doc.issuer))
    d.party = party_dict(doc.party)
    if doc.party and isinstance(doc.fields_json, dict) and doc.fields_json.get("_party_override"):
        d.party.update(doc.fields_json["_party_override"])
    d.contact = contact_dict(doc.contact)
    d.project = project_dict(doc.project)
    d.letter_type = letter_type_dict(doc.letter_type)
    d.date = doc.date_greg or date.today()
    d.number = doc.number or ""
    d.title = doc.title or TITLE_BY_KIND.get(doc.kind, "")
    d.fields = {k: v for k, v in (doc.fields_json or {}).items() if not k.startswith("_")}
    d.subject = doc.subject or ""
    d.salutation = doc.salutation or ""
    d.closing = doc.closing or ""
    d.attachment_text = doc.attachment_text or ""
    d.header_line = doc.header_line or ""
    d.addressee_lines = doc.addressee_lines
    d.addressee_format = doc.addressee_format or 0
    d.body_override = doc.body_override
    d.vat_enabled = bool(doc.vat_enabled)
    d.vat_percent = Decimal(str(doc.vat_percent or 0))
    d.input_currency = doc.input_currency or "million_toman"
    d.show_stamp = bool(doc.show_stamp)
    d.show_signature = bool(doc.show_signature)
    d.tax_serial = doc.tax_serial or ""
    d.list_title = doc.list_title or ""
    d.list_subtitle = doc.list_subtitle or ""
    d.show_seller_national_id = bool(get_setting(s, "personal_invoice_show_national_id", False))
    d.lines = [Line(description=l.description, unit=l.unit, qty=Decimal(str(l.qty)), unit_price=l.unit_price,
                    purchase_price=l.purchase_price,
                    markup_percent=Decimal(str(l.markup_percent)) if l.markup_percent is not None else None,
                    buyer_supplied=l.buyer_supplied, emphasis=l.emphasis, is_service=l.is_service,
                    item_id=l.item_id, category=l.category, note=l.note) for l in doc.lines]
    d.clauses = []
    for dc in doc.clauses:
        c = s.get(Clause, dc.clause_id) if dc.clause_id else None
        if c:
            sel = clause_sel(c, dc.variables_json)
        else:
            sel = ClauseSel(group=dc.group, template=(dc.variables_json or {}).get("_template", dc.rendered_text),
                            values={k: v for k, v in (dc.variables_json or {}).items() if not k.startswith("_")})
        sel.group = dc.group
        d.clauses.append(sel)
    d.accounts = [account_info(s.get(Account, da.account_id)) for da in doc.accounts if s.get(Account, da.account_id)]
    if doc.parent_document_id:
        parent = s.get(Document, doc.parent_document_id)
        d.parent_number = parent.number if parent else ""
    return d


def save_draft(s: Session, d: Draft, doc_id: int | None = None, attachments: list | None = None,
               party_override: dict | None = None) -> Document:
    """Store the draft (insert or update). Issued documents are not modified here."""
    doc = s.get(Document, doc_id) if doc_id else None
    if doc is None:
        doc = Document(kind=d.kind, issuer_id=d.issuer["id"], status="draft")
        s.add(doc)
    elif doc.status not in ("draft",):
        raise ValueError("سند صادرشده قفل است؛ برای تغییر «نسخه‌ی جدید» بسازید.")
    doc.kind = d.kind
    doc.issuer_id = d.issuer["id"]
    doc.party_id = d.party.get("id") if d.party else None
    doc.contact_id = (d.contact or {}).get("id")
    doc.project_id = (d.project or {}).get("id")
    doc.letter_type_id = (d.letter_type or {}).get("id")
    doc.date_greg = d.date
    doc.date_jalali = jalali.fmt(d.date)
    doc.title = d.title
    fields = dict(d.fields)
    if party_override:
        fields["_party_override"] = party_override
    elif isinstance(doc.fields_json, dict) and doc.fields_json.get("_party_override"):
        fields["_party_override"] = doc.fields_json["_party_override"]
    doc.fields_json = fields
    doc.subject = letters.build_subject(d) if (d.kind == "letter" and d.letter_type) else d.subject
    doc.salutation = d.salutation
    doc.closing = d.closing
    doc.attachment_text = d.attachment_text
    doc.header_line = d.header_line
    doc.addressee_lines = d.addressee_lines
    doc.addressee_format = d.addressee_format
    doc.body_override = d.body_override
    doc.vat_enabled = d.vat_enabled
    doc.vat_percent = d.vat_percent
    doc.input_currency = d.input_currency
    t = d.totals
    doc.subtotal, doc.vat_amount, doc.payable = t.subtotal, t.vat, t.payable
    if d.kind == "letter" and not d.lines:
        amt = d.fields.get("amount")
        try:
            doc.payable = int(amt) if amt not in (None, "") else 0
        except (TypeError, ValueError):
            pass
    doc.show_stamp = d.show_stamp
    doc.show_signature = d.show_signature
    doc.tax_serial = d.tax_serial
    doc.list_title = d.list_title
    doc.list_subtitle = d.list_subtitle
    if attachments is not None:
        doc.attachments = attachments
    if not doc.status or doc.status == "draft":
        doc.number = d.number or ""

    doc.lines.clear()
    for i, l in enumerate(d.lines, 1):
        doc.lines.append(DocumentLine(idx=i, item_id=l.item_id, description=l.description, unit=l.unit,
                                      qty=l.qty, unit_price=int(l.unit_price), purchase_price=l.purchase_price,
                                      markup_percent=l.markup_percent, total=l.total,
                                      buyer_supplied=l.buyer_supplied, emphasis=l.emphasis,
                                      is_service=l.is_service, category=l.category, note=l.note))
    doc.clauses.clear()
    for i, c in enumerate(d.clauses):
        vals = dict(c.values or {})
        if not c.clause_id:
            vals["_template"] = c.template
        doc.clauses.append(DocumentClause(clause_id=c.clause_id, group=c.group, sort_order=i,
                                          rendered_text=clause_rules.render_clause(d, c), variables_json=vals))
    doc.accounts.clear()
    for i, a in enumerate(d.accounts):
        doc.accounts.append(DocumentAccount(account_id=a.id, sort_order=i))
    s.flush()
    return doc


# ------------------------------------------------------------------ numbering

def _counter_scope(s: Session, issuer: Issuer, kind: str):
    shared = bool(get_setting(s, "numbering_shared_letter_invoice", False))
    per_issuer = bool(get_setting(s, "numbering_separate_per_issuer", True))
    group = numbering.counter_group(kind, shared)
    issuer_id = issuer.id if per_issuer else None
    return group, issuer_id


def suggest_number(s: Session, d: Draft) -> str:
    issuer = s.get(Issuer, d.issuer["id"])
    j = jalali.to_jalali(d.date)
    group, issuer_id = _counter_scope(s, issuer, d.kind)
    key = numbering.period_key(issuer.number_scope, j.year, j.month)
    c = s.scalar(select(NumberCounter).where(NumberCounter.issuer_id.is_(issuer_id) if issuer_id is None
                                             else NumberCounter.issuer_id == issuer_id,
                                             NumberCounter.group == group, NumberCounter.period_key == key))
    seq = (c.last_seq if c else 0) + 1
    return numbering.format_number(issuer.number_pattern, seq, j.year, j.month, d.kind)


def reserve_number(s: Session, doc: Document) -> str:
    issuer = doc.issuer
    j = jalali.to_jalali(doc.date_greg or date.today())
    group, issuer_id = _counter_scope(s, issuer, doc.kind)
    key = numbering.period_key(issuer.number_scope, j.year, j.month)
    c = s.scalar(select(NumberCounter).where(NumberCounter.issuer_id.is_(issuer_id) if issuer_id is None
                                             else NumberCounter.issuer_id == issuer_id,
                                             NumberCounter.group == group, NumberCounter.period_key == key))
    if c is None:
        c = NumberCounter(issuer_id=issuer_id, group=group, period_key=key, last_seq=0)
        s.add(c)
    while True:
        c.last_seq += 1
        number = numbering.format_number(issuer.number_pattern, c.last_seq, j.year, j.month, doc.kind)
        if not number_taken(s, doc, number):
            break
    doc.number, doc.seq, doc.seq_group, doc.seq_year, doc.seq_month = number, c.last_seq, group, j.year, j.month
    return number


def number_taken(s: Session, doc: Document, number: str) -> bool:
    if not number:
        return False
    group = numbering.counter_group(doc.kind, bool(get_setting(s, "numbering_shared_letter_invoice", False)))
    kinds = ["letter"] if group == "letter" else (list(numbering.INVOICE_FAMILY) if group == "invoice_family"
                                                  else list(numbering.KIND_LETTER))
    q = select(func.count(Document.id)).where(Document.number == number, Document.kind.in_(kinds),
                                              Document.issuer_id == doc.issuer_id, Document.status != "draft",
                                              Document.id != (doc.id or 0))
    if doc.parent_document_id:  # an invoice may legitimately reuse nothing; versions share the doc row
        pass
    return bool(s.scalar(q))


# ------------------------------------------------------------------ validation

def check_draft(s: Session, d: Draft) -> list:
    from app.core.clauses import Issue
    issues = []
    if d.kind != "attachment_list":
        issues += clause_rules.check(d)
    if d.kind == "letter":
        issues += letters.check(d)
    if d.is_money_doc and not d.lines:
        issues.append(Issue("error", "جدول اقلام خالی است."))
    if d.kind != "attachment_list" and not d.party:
        issues.append(Issue("error", "مشتری انتخاب نشده است."))
    supplier = ((d.project or {}).get("supplier_name") or "").strip()
    if supplier and len(supplier) > 2:
        try:
            text = all_output_text(build_context(d))
        except Exception:
            text = ""
        if supplier in text:
            issues.append(Issue("warning", f"نام تأمین‌کننده («{supplier}») در متن خروجی آمده است."))
    return issues


# ------------------------------------------------------------------ issuing

def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def doc_folder(s: Session, doc: Document) -> Path:
    party = doc.party
    short = (party.short_name or party.name) if party else "بدون مشتری"
    folder = document_folder(output_root(s), short, doc.project.title if doc.project else None)
    if doc.project and doc.project.folder_path != str(folder):
        doc.project.folder_path = str(folder)
    return folder


def _render_document(s: Session, doc: Document, d: Draft) -> Path:
    folder = doc_folder(s, doc)
    folder.mkdir(parents=True, exist_ok=True)
    short = (doc.party.short_name or doc.party.name) if doc.party else ""
    base = base_file_name(doc.kind, short, doc.number, doc.date_greg, doc.subject if doc.kind == "letter" else "")
    out, version = versioned_path(folder, base, ".docx", doc.version or 1)
    ctx = build_context(d, bool(get_setting(s, "output_digits_persian", False)))
    render_docx(paths.template_path(template_name(d)), ctx, out)
    doc.version = version
    doc.files.append(DocumentFile(role="docx", path=str(out), version=version, sha256=_sha(out)))
    return out


def issue(s: Session, doc_id: int, make_pdf: bool = False, force_warnings: bool = True) -> IssueResult:
    """Reserve the number, render the Word file into the project folder, mark issued, create
    automatic tasks and learn clause defaults. Blocking errors raise IssueBlocked."""
    doc = s.get(Document, doc_id)
    if doc.status not in ("draft",):
        raise ValueError("این سند قبلاً صادر شده است.")
    d = draft_from_document(s, doc)
    issues = check_draft(s, d)
    errors = [i for i in issues if i.blocking]
    if errors:
        raise IssueBlocked(errors)
    if not doc.number:
        reserve_number(s, doc)
    elif number_taken(s, doc, doc.number):
        issues.append(clause_rules.Issue("warning", f"شماره‌ی {doc.number} قبلاً برای سند دیگری استفاده شده است."))
    d.number = doc.number
    for dc, sel in zip(doc.clauses, d.clauses):
        dc.rendered_text = clause_rules.render_clause(d, sel)   # snapshot at issue time
    docx = _render_document(s, doc, d)
    doc.status = "issued"
    doc.issued_at = datetime.now()
    doc.subject = letters.build_subject(d) if d.kind == "letter" and d.letter_type else doc.subject
    _learn(s, doc)
    _project_after_issue(s, doc)
    task_service.after_issue(s, doc, d)
    audit(s, "issue", "document", doc.id, f"{doc.kind} {doc.number}")
    s.commit()
    result = IssueResult(doc.id, doc.number, docx, warnings=[i for i in issues if not i.blocking])
    if make_pdf:
        try:
            result.pdf = make_document_pdf(s, doc.id)
        except pdf_tools.PdfUnavailable as e:
            result.pdf_error = str(e)
    return result


def _learn(s: Session, doc: Document) -> None:
    kind = "invoice" if doc.kind == "statement" else doc.kind
    for dc in doc.clauses:
        if not dc.clause_id:
            continue
        c = s.get(Clause, dc.clause_id)
        c.usage_count = (c.usage_count or 0) + 1
        if doc.party_id:
            row = s.scalar(select(PartyClauseDefault).where(PartyClauseDefault.party_id == doc.party_id,
                                                            PartyClauseDefault.clause_id == c.id,
                                                            PartyClauseDefault.doc_kind == kind))
            if row is None:
                row = PartyClauseDefault(party_id=doc.party_id, clause_id=c.id, doc_kind=kind, use_count=0)
                s.add(row)
            row.use_count += 1


def _project_after_issue(s: Session, doc: Document) -> None:
    p = doc.project
    if p and doc.kind in ("invoice", "statement") and p.status == "open":
        p.status = "waiting_payment"


def latest_file(doc: Document, role: str) -> DocumentFile | None:
    files = [f for f in doc.files if f.role == role]
    return max(files, key=lambda f: (f.version, f.id)) if files else None


def make_document_pdf(s: Session, doc_id: int) -> Path:
    doc = s.get(Document, doc_id)
    docx = latest_file(doc, "docx")
    if not docx:
        raise ValueError("ابتدا فایل Word را بسازید.")
    pdf = Path(docx.path).with_suffix(".pdf")
    pdf_tools.docx_to_pdf(Path(docx.path), pdf)
    doc.files.append(DocumentFile(role="pdf", path=str(pdf), version=docx.version, sha256=_sha(pdf)))
    s.commit()
    return pdf


def attachments_dir(doc_id: int) -> Path:
    p = paths.data_dir() / "attachments" / str(doc_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def store_attachment(doc_id: int, source: Path) -> Path:
    """Keep a private copy of an attached drawing/PDF so later edits of the source don't matter."""
    source = Path(source)
    dest, _ = versioned_path(attachments_dir(doc_id), source.stem, source.suffix.lower())
    shutil.copy2(source, dest)
    return dest


def make_full_pdf(s: Session, doc_id: int) -> Path:
    """Document PDF + attachments (drawing, items list, other PDFs) in the user's order, all
    pages the same size. Saved next to the Word file with « (کامل)»."""
    doc = s.get(Document, doc_id)
    docx = latest_file(doc, "docx")
    if not docx:
        raise ValueError("ابتدا فایل Word را بسازید.")
    pdf = latest_file(doc, "pdf")
    if not pdf or pdf.version != docx.version or not Path(pdf.path).exists():
        make_document_pdf(s, doc_id)
        pdf = latest_file(doc, "pdf")
    work = attachments_dir(doc.id) / "_build"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    order = doc.attachments or []
    if not any(a.get("type") == "document" for a in order):
        order = [{"type": "document"}] + order
    d = None
    for i, a in enumerate(order):
        t = a.get("type")
        if t == "document":
            parts.append(Path(pdf.path))
        elif t == "items_list":
            d = d or draft_from_document(s, doc)
            if a.get("title"):
                d.list_title = a["title"]
            if a.get("subtitle") is not None:
                d.list_subtitle = a.get("subtitle", "")
            ldocx = work / f"{i}-list.docx"
            ldocx.unlink(missing_ok=True)
            render_docx(paths.template_path("attachment_list.docx"), attachment_list_context(d), ldocx)
            lpdf = work / f"{i}-list.pdf"
            pdf_tools.docx_to_pdf(ldocx, lpdf)
            parts.append(lpdf)
        elif t == "file":
            src = Path(a["path"])
            if not src.exists():
                raise FileNotFoundError(f"پیوست پیدا نشد: {src}")
            if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"):
                p = pdf_tools.image_to_pdf(src, work / f"{i}-img.pdf")
            else:
                p = src
            regions = {int(k): [tuple(r) for r in v] for k, v in (a.get("erase") or {}).items()}
            if regions:
                p = pdf_tools.erase_regions(p, work / f"{i}-erased.pdf", regions)
            parts.append(p)
    docx_path = Path(docx.path)
    out, _ = versioned_path(docx_path.parent, docx_path.stem, ".pdf", tag=" (کامل)")
    pdf_tools.merge_same_size(parts, out)
    doc.files.append(DocumentFile(role="merged_pdf", path=str(out), version=docx.version, sha256=_sha(out)))
    s.commit()
    return out


# ------------------------------------------------------------------ statuses & derived documents

ALLOWED = {
    "issued": {"sent", "accepted", "rejected", "paid", "void"},
    "sent": {"accepted", "rejected", "paid", "void"},
    "accepted": {"paid", "void", "sent"},
    "rejected": {"void", "sent"},
    "paid": {"void"},
    "draft": {"void"},
    "void": set(),
}


def set_status(s: Session, doc_id: int, status: str) -> None:
    doc = s.get(Document, doc_id)
    if status not in ALLOWED.get(doc.status, set()) and status != "void":
        raise ValueError("تغییر وضعیت مجاز نیست.")
    doc.status = status
    task_service.after_status(s, doc, status)
    if status == "paid" and doc.project and doc.project.status == "waiting_payment":
        doc.project.status = "retention" if (doc.project.retention_percent or 0) > 0 else "closed"
    audit(s, "status", "document", doc.id, status)
    s.commit()


def copy_document(s: Session, doc_id: int, party_id: int | None = None, kind: str | None = None) -> Document:
    """New draft with the same content (optionally another customer or another kind)."""
    src = s.get(Document, doc_id)
    d = draft_from_document(s, src)
    d.kind = kind or src.kind
    d.number = ""
    d.date = date.today()
    if party_id and party_id != src.party_id:
        apply_party(s, d, party_id)
        d.addressee_lines = None
        d.project = None
    attachments = [dict(a) for a in (src.attachments or []) if a.get("type") != "file"]
    doc = save_draft(s, d, attachments=attachments)
    for a in src.attachments or []:   # copy private attachment files too
        if a.get("type") == "file" and Path(a["path"]).exists():
            nb = dict(a, path=str(store_attachment(doc.id, Path(a["path"]))))
            doc.attachments = list(doc.attachments or []) + [nb]
    s.commit()
    return doc


def make_invoice_from(s: Session, proforma_id: int, kind: str = "invoice") -> Document:
    """«ساخت فاکتور از این پیش‌فاکتور» (doc 04 §4.3)."""
    src = s.get(Document, proforma_id)
    d = draft_from_document(s, src)
    d.kind = kind
    d.title = TITLE_BY_KIND[kind]
    d.number = ""
    d.date = date.today()
    d.clauses = [c for c in d.clauses if c.code != "OTH_VALIDITY"]
    if src.number:
        d.clauses.append(ClauseSel(group="other", template=f"این فاکتور مطابق پیش‌فاکتور شماره‌ی {src.number} مورخ {src.date_jalali} صادر شده است."))
    doc = save_draft(s, d, attachments=[a for a in (src.attachments or []) if a.get("type") != "file"])
    doc.parent_document_id = src.id
    s.commit()
    return doc


def new_version(s: Session, doc_id: int) -> Document:
    """Unlock an issued document for editing; the next issue keeps the number and writes -v2."""
    doc = s.get(Document, doc_id)
    if doc.status == "draft":
        return doc
    doc.status = "draft"
    doc.version = (doc.version or 1) + 1
    audit(s, "new_version", "document", doc.id, f"v{doc.version}")
    s.commit()
    return doc


def register_final(s: Session, doc_id: int, source: Path) -> Path:
    """«بارگذاری نسخه‌ی نهایی»: copy the hand-edited Word/PDF next to the others as the sent file."""
    doc = s.get(Document, doc_id)
    source = Path(source)
    folder = doc_folder(s, doc)
    folder.mkdir(parents=True, exist_ok=True)
    short = (doc.party.short_name or doc.party.name) if doc.party else ""
    base = base_file_name(doc.kind, short, doc.number, doc.date_greg, doc.subject if doc.kind == "letter" else "")
    dest, _ = versioned_path(folder, base, source.suffix.lower(), tag=" (نهایی)")
    shutil.copy2(source, dest)
    doc.files.append(DocumentFile(role="final", path=str(dest), version=doc.version or 1, sha256=_sha(dest)))
    audit(s, "final_file", "document", doc.id, str(dest))
    s.commit()
    return dest


def delete_draft(s: Session, doc_id: int) -> None:
    doc = s.get(Document, doc_id)
    if doc.status == "draft" and not doc.files:
        doc.is_archived = True
        s.commit()
    else:
        raise ValueError("فقط پیش‌نویس بدون فایل را می‌شود حذف کرد؛ سند صادرشده را «باطل» کنید.")
