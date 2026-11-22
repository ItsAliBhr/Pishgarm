"""Issuing flow against the seeded database (phases 1–3 acceptance at the service level)."""
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pypdf import PageObject, PdfReader, PdfWriter
from sqlalchemy import select

from app.core import jalali, pdf_tools
from app.core.draft import Line
from app.db.models import Document, Issuer, LetterType, Party, Project, Task
from app.services import documents as docs
from app.services import projects as proj


def _ids(s):
    company = s.scalar(select(Issuer).where(Issuer.code == "COMPANY"))
    personal = s.scalar(select(Issuer).where(Issuer.code == "PERSONAL"))
    return company, personal


def _party(s, needle):
    return s.scalar(select(Party).where(Party.name.contains(needle)))


def _text(p: Path) -> str:
    import re
    with zipfile.ZipFile(p) as z:
        return re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode("utf-8"))


@pytest.fixture
def fake_pdf(monkeypatch):
    """Stand-in for Word: write a one-page PDF (A4 portrait or Letter landscape)."""
    def convert(docx, pdf):
        w = PdfWriter()
        w.add_page(PageObject.create_blank_page(width=842, height=595))
        with open(pdf, "wb") as f:
            w.write(f)
        return "fake"
    monkeypatch.setattr(pdf_tools, "docx_to_pdf", convert)
    return convert


def test_company_proforma_issue_and_invoice(db):
    with db() as s:
        company, _ = _ids(s)
        party = _party(s, "ناب")
        d = docs.new_draft(s, "proforma", company.id)
        docs.apply_party(s, d, party.id)
        d.lines = [Line("مشعل 2000 کیلووات", "عدد", Decimal(2), 3_500_000_000)]
        assert d.vat_enabled and d.show_stamp
        assert {c.code for c in d.clauses} >= {"PAY_ADV", "PAY_TO_ACCOUNT", "TAX_NET_PLUS_VAT", "OTH_VALIDITY"}
        assert docs.suggest_number(s, d).endswith("/" + str(jalali.to_jalali(date.today()).year))
        doc = docs.save_draft(s, d)
        s.commit()
        r = docs.issue(s, doc.id)
        assert r.number.startswith("001/")
        assert r.docx.exists() and r.docx.parent.name == "عمومی"
        text = _text(r.docx)
        assert "7,700,000,000" in text and "IR740190000000118420332008" in text
        assert s.get(Document, doc.id).status == "issued"
        # follow-up task, due after 3 workdays
        t = s.scalar(select(Task).where(Task.document_id == doc.id))
        assert t.source == "auto:proforma_followup" and t.due_date > date.today()
        # issuing twice is refused; a new version keeps the number and writes -v2
        with pytest.raises(ValueError):
            docs.issue(s, doc.id)
        docs.new_version(s, doc.id)
        r2 = docs.issue(s, doc.id)
        assert r2.number == r.number and r2.docx.name.endswith(" -v2.docx") and r.docx.exists()
        assert s.scalar(select(Task).where(Task.document_id == doc.id).order_by(Task.id.desc())).id == t.id

        # golden 5: invoice from proforma
        inv = docs.make_invoice_from(s, doc.id)
        di = docs.draft_from_document(s, inv)
        assert di.title == "فاکتور فروش و خدمات"
        assert "OTH_VALIDITY" not in {c.code for c in di.clauses}
        assert any(r.number in c.template for c in di.clauses)
        ri = docs.issue(s, inv.id)
        assert ri.number == r.number[:0] + "002/" + r.number.split("/")[1]  # invoice family shares the counter


def test_personal_numbering_and_letter_counter(db):
    with db() as s:
        _, personal = _ids(s)
        party = _party(s, "خیام")
        lt = s.scalar(select(LetterType).where(LetterType.code == "PAY_ATTENDANCE_REPORT"))
        d = docs.new_draft(s, "letter", personal.id)
        docs.apply_party(s, d, party.id)
        docs.apply_letter_type(s, d, lt.id)
        d.fields.update({"date_from": "1402/04/01", "date_to": "1402/04/31", "days": "16"})
        assert d.fields["person_name"] == "قربانعلی بهرامی"
        doc = docs.save_draft(s, d)
        r = docs.issue(s, doc.id)
        j = jalali.to_jalali(date.today())
        assert r.number == f"{str(j.year)[-3:]}{j.month}01"
        text = _text(r.docx)
        assert "از تاریخ 1402/04/01 تا 1402/04/31 به مدت 16 روز" in text
        assert "باسمه تعالی" in text


def test_blocking_errors(db):
    with db() as s:
        company, _ = _ids(s)
        d = docs.new_draft(s, "proforma", company.id)
        doc = docs.save_draft(s, d)
        with pytest.raises(docs.IssueBlocked) as e:
            docs.issue(s, doc.id)
        msgs = " ".join(i.message for i in e.value.issues)
        assert "اقلام" in msgs and "مشتری" in msgs


def test_warning_letter_creates_deadline_task(db):
    with db() as s:
        company, _ = _ids(s)
        party = _party(s, "گل‌گهر")
        lt = s.scalar(select(LetterType).where(LetterType.code == "PAY_WARNING"))
        d = docs.new_draft(s, "letter", company.id)
        docs.apply_party(s, d, party.id)
        docs.apply_letter_type(s, d, lt.id)
        d.fields.update({"warning_no": "دوم", "deadline_days": "10", "contract_no": "1404/N.A/24590"})
        doc = docs.save_draft(s, d)
        docs.issue(s, doc.id)
        t = s.scalar(select(Task).where(Task.document_id == doc.id))
        assert (t.due_date - doc.date_greg).days == 10 and "مهلت" in t.title


def test_handover_retention_task(db):
    with db() as s:
        party = _party(s, "پردیس")
        p = Project(party_id=party.id, title="نسوزکاری کوره", retention_percent=Decimal(10), retention_months=3,
                    handover_date=jalali.parse("1405/06/26"))
        proj.save_project(s, p)
        t = s.scalar(select(Task).where(Task.project_id == p.id))
        assert jalali.fmt(t.due_date) == "1405/09/26"
        assert t.action["letter_type"] == "PAY_RETENTION_RELEASE"
        proj.save_project(s, p)   # never duplicated
        assert len(s.scalars(select(Task).where(Task.project_id == p.id)).all()) == 1


def test_learning_defaults(db):
    with db() as s:
        company, _ = _ids(s)
        party = _party(s, "ناب")
        extra = "SITE_CONSUMABLES"
        for _ in range(3):
            d = docs.new_draft(s, "proforma", company.id)
            docs.apply_party(s, d, party.id)
            from app.db.models import Clause
            from app.services.convert import clause_sel
            d.clauses.append(clause_sel(s.scalar(select(Clause).where(Clause.code == extra))))
            d.lines = [Line("x", "عدد", Decimal(1), 1000)]
            docs.issue(s, docs.save_draft(s, d).id)
        codes = {c.code for c in docs.default_clauses(s, "proforma", "COMPANY", party.id)}
        assert extra in codes
        assert extra not in {c.code for c in docs.default_clauses(s, "proforma", "COMPANY", None)}


def test_full_pdf_merge_same_size(db, fake_pdf, tmp_path):
    from PIL import Image
    with db() as s:
        _, personal = _ids(s)
        party = _party(s, "ناب")
        d = docs.new_draft(s, "proforma", personal.id)
        docs.apply_party(s, d, party.id)
        d.lines = [Line("اقلام سیستم سوخت", "مجموعه", Decimal(1), 20_200_000_000),
                   Line("مشعل موجود", "عدد", Decimal(17), 0, buyer_supplied=True)]
        doc = docs.save_draft(s, d)
        img = tmp_path / "pid.png"
        Image.new("RGB", (1200, 800), "black").save(img)
        stored = docs.store_attachment(doc.id, img)
        doc.attachments = [{"type": "document"}, {"type": "file", "path": str(stored),
                                                  "erase": {"0": [[0.7, 0.8, 1.0, 1.0]]}},
                           {"type": "items_list", "title": "لیست اقلام سیستم سوخت", "subtitle": "17 مشعل"}]
        s.commit()
        docs.issue(s, doc.id)
        out = docs.make_full_pdf(s, doc.id)
        assert out.name.endswith("(کامل).pdf")
        pages = PdfReader(str(out)).pages
        assert len(pages) == 3
        sizes = {tuple(sorted((round(float(p.mediabox.width)), round(float(p.mediabox.height))))) for p in pages}
        assert len(sizes) == 1
        # erased corner is white
        im = pdf_tools.render_page(out, 1, 40)
        assert im.getpixel((im.width - 3, im.height - 3)) == (255, 255, 255)


def test_receivables(db):
    with db() as s:
        company, _ = _ids(s)
        party = _party(s, "سرمد")
        d = docs.new_draft(s, "statement", company.id)
        docs.apply_party(s, d, party.id)
        d.lines = [Line("نسوزکاری", "کیلوگرم", Decimal(45000), 81_700)]
        doc = docs.save_draft(s, d)
        docs.issue(s, doc.id)
        rec = proj.receivables(s)
        assert rec and rec[0].amount == doc.payable
        docs.set_status(s, doc.id, "paid")
        assert not proj.receivables(s)
