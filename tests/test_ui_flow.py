"""Drive the real widgets: wizard end-to-end for a proforma and a letter, plus every page."""
from decimal import Decimal

import pytest
from sqlalchemy import select

pytest.importorskip("PySide6")


@pytest.fixture
def qapp(monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from app.ui.app import create_app, load_fonts
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: True))
    app = create_app(["test"])
    load_fonts(app)
    return app


def _issuer(db, code):
    from app.db.models import Issuer
    with db() as s:
        return s.scalar(select(Issuer).where(Issuer.code == code)).id


def _party(db, needle):
    from app.db.models import Party
    with db() as s:
        return s.scalar(select(Party).where(Party.name.contains(needle))).id


def test_wizard_proforma_end_to_end(qapp, db):
    from app.core.draft import Line
    from app.db.models import Document
    from app.ui.wizard import DocumentWizard
    w = DocumentWizard(db)
    w._pick_kind("proforma")
    w._pick_issuer(_issuer(db, "COMPANY"))
    assert w.current == 2
    w.party_combo.set_current_id(_party(db, "تیکمه"))
    w.go(3)
    w.lines_money.add_line(Line("مشعل دوگانه‌سوز 2000 کیلووات", "عدد", Decimal(2), 0))
    item = w.lines_money.table.item(0, 3)
    item.setText("350")           # «دونه‌ای ۳۵۰ میلیون» in million toman
    assert w.draft.lines[0].unit_price == 3_500_000_000
    assert "7,700,000,000" in w.totals_label.text()
    w.go(4)
    assert any(c.code == "PAY_TO_ACCOUNT" for c in w.draft.clauses)
    w.go(5)
    w._make_word()
    assert w.issued
    with db() as s:
        d = s.get(Document, w.doc_id)
        assert d.status == "issued" and d.payable == 7_700_000_000 and d.number
    w.close()


def test_wizard_letter_retention(qapp, db):
    from app.db.models import Document, LetterType
    from app.ui.wizard import DocumentWizard
    with db() as s:
        lt = s.scalar(select(LetterType).where(LetterType.code == "PAY_RETENTION_RELEASE")).id
    w = DocumentWizard(db, preset={"kind": "letter", "issuer_id": _issuer(db, "COMPANY"),
                                   "party_id": _party(db, "پردیس"), "letter_type": "PAY_RETENTION_RELEASE"})
    assert w.current == 2
    w.go(3)
    assert w.letter_type_combo.current_id() == lt
    w.field_widgets["project_title"].setText("نسوزکاری کوره پیشگرم")
    w._set_field("project_title", "نسوزکاری کوره پیشگرم")
    assert "نسوزکاری کوره پیشگرم" in w.body_edit.toPlainText()
    w.edit_text_btn.setChecked(True)
    w.body_edit.setPlainText(w.body_edit.toPlainText() + "\nبند دستی")
    w.go(4)
    w.go(5)
    w._make_word()
    with db() as s:
        d = s.get(Document, w.doc_id)
        assert d.status == "issued" and d.body_override[-1] == "بند دستی"
    w.close()


def test_draft_autosaved_and_reopened(qapp, db):
    from app.db.models import Document
    from app.ui.wizard import DocumentWizard
    w = DocumentWizard(db, preset={"kind": "attachment_list", "issuer_id": _issuer(db, "PERSONAL")})
    w.go(3)
    w.list_title.setText("لیست اقلام سیستم سوخت")
    w.close()
    with db() as s:
        d = s.scalars(select(Document)).first()
        assert d.status == "draft" and d.list_title == "لیست اقلام سیستم سوخت"
        doc_id = d.id
    w2 = DocumentWizard(db, doc_id=doc_id)
    assert w2.current == 2 and w2.draft.list_title == "لیست اقلام سیستم سوخت"
    w2.close()


def test_all_pages_render(qapp, db):
    from app.ui.main_window import MainWindow
    win = MainWindow(db)
    for sec in win.SECTIONS:
        win.go_to(sec)
        qapp.processEvents()
    for key in win.master_data.TABS:
        assert win.master_data.tables[key].row_count() > 0
    win.close()


def test_master_forms_open(qapp, db):
    from app.db.models import Account, Clause, Issuer, Item, LetterType, Party
    from app.ui import forms
    with db() as s:
        for form, model in ((forms.PartyForm, Party), (forms.AccountForm, Account), (forms.ItemForm, Item),
                            (forms.ClauseForm, Clause), (forms.LetterTypeForm, LetterType), (forms.IssuerForm, Issuer)):
            f = form(s, s.scalars(select(model)).first())
            assert f.validate() is None, form.__name__
            f.save()
        bad = forms.AccountForm(s, None)
        bad.bank.setText("تجارت")
        bad.holder.setText("x")
        bad.iban.setText("IR80180000000344646318580")
        assert bad.validate() == "این شبا 23 رقم دارد؛ باید ۲۴ رقم باشد."
