"""اطلاعات پایه — searchable lists with add / edit / archive (doc 04 §4.6)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget
from sqlalchemy import select

from app.core.draft import GROUP_FA
from app.core.money import fmt_percent
from app.core.validators import format_iban
from app.db.models import Account, Clause, Issuer, Item, LetterType, Party, Unit
from app.ui import forms
from app.ui.widgets import SearchTable, confirm

PARTY_KIND_FA = forms.PARTY_KINDS
CLAUSE_GROUP_FA = GROUP_FA


def _contact_label(c) -> str:
    text = " ".join(p for p in (c.honorific, c.name) if p)
    return f"{text} ({c.position})" if c.position else text


def _rial(v) -> str:
    return "" if v is None else f"{int(v):,}"


class EditableList(QWidget):
    """SearchTable + «افزودن / ویرایش / حذف» buttons."""

    def __init__(self, page, key: str, headers: list[str], can_add=True, can_delete=True):
        super().__init__()
        self.page, self.key = page, key
        self.table = SearchTable(headers)
        self.table.view.doubleClicked.connect(lambda _: self.page.edit(self.key))
        bar = QHBoxLayout()
        if can_add:
            b = QPushButton("+ افزودن")
            b.setObjectName("primarySmall")
            b.clicked.connect(lambda: self.page.edit(self.key, new=True))
            bar.addWidget(b)
        e = QPushButton("ویرایش")
        e.clicked.connect(lambda: self.page.edit(self.key))
        bar.addWidget(e)
        if can_delete:
            d = QPushButton("حذف")
            d.clicked.connect(lambda: self.page.archive(self.key))
            bar.addWidget(d)
        bar.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.table)

    # compatibility with SearchTable API used elsewhere
    def row_count(self):
        return self.table.row_count()

    @property
    def search(self):
        return self.table.search


MODELS = {"parties": Party, "letter_types": LetterType, "clauses": Clause, "items": Item,
          "accounts": Account, "issuers": Issuer, "units": Unit}
FORMS = {"parties": forms.PartyForm, "letter_types": forms.LetterTypeForm, "clauses": forms.ClauseForm,
         "items": forms.ItemForm, "accounts": forms.AccountForm, "issuers": forms.IssuerForm,
         "units": forms.UnitForm}


class MasterDataPage(QWidget):
    TABS = ["parties", "letter_types", "clauses", "items", "accounts", "issuers", "units"]
    LABELS = {"parties": "اشخاص و شرکت‌ها", "letter_types": "موضوعات نامه", "clauses": "بندها",
              "items": "اقلام", "accounts": "حساب‌ها", "issuers": "سربرگ‌ها", "units": "واحدها"}

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.SessionLocal = SessionLocal
        self.tabs = QTabWidget()
        self.lists: dict[str, EditableList] = {
            "parties": EditableList(self, "parties", ["نام", "نام کوتاه", "نوع", "شناسه ملی", "کد اقتصادی",
                                                      "تلفن", "مخاطبان"]),
            "letter_types": EditableList(self, "letter_types", ["دسته", "عنوان", "خط موضوع"]),
            "clauses": EditableList(self, "clauses", ["گروه", "متن بند", "دفعات استفاده"]),
            "items": EditableList(self, "items", ["شرح", "واحد", "آخرین قیمت واحد (ریال)", "منبع قیمت"]),
            "accounts": EditableList(self, "accounts", ["بانک", "صاحب حساب", "شبا", "سربرگ", "فعال"]),
            "issuers": EditableList(self, "issuers", ["عنوان", "نام در سند", "امضاکننده", "ارزش افزوده پیش‌فرض",
                                                      "الگوی شماره"], can_add=False, can_delete=False),
            "units": EditableList(self, "units", ["واحد"]),
        }
        self.tables = {k: v.table for k, v in self.lists.items()}
        for key in self.TABS:
            self.tabs.addTab(self.lists[key], self.LABELS[key])
        QVBoxLayout(self).addWidget(self.tabs)
        self.refresh()

    def edit(self, key: str, new: bool = False) -> None:
        with self.SessionLocal() as s:
            obj = None
            if not new:
                ident = self.tables[key].selected_id()
                if ident is None:
                    return
                obj = s.get(MODELS[key], ident)
            dlg = FORMS[key](s, obj, self)
            if dlg.exec():
                dlg.save()
        self.refresh()

    def archive(self, key: str) -> None:
        ident = self.tables[key].selected_id()
        if ident is None:
            return
        if not confirm(self, "این مورد از فهرست حذف شود؟ (اسناد قبلی دست نمی‌خورند.)"):
            return
        with self.SessionLocal() as s:
            obj = s.get(MODELS[key], ident)
            obj.is_archived = True
            if key == "accounts":
                obj.active = False
            s.commit()
        self.refresh()

    def refresh(self) -> None:
        with self.SessionLocal() as s:
            def live(m):
                return select(m).where(m.is_archived.is_(False))

            rows = s.scalars(live(Party).order_by(Party.name)).all()
            self.tables["parties"].set_rows(
                [[p.name, p.short_name, PARTY_KIND_FA.get(p.kind, p.kind), p.national_id, p.economic_code, p.phone,
                  "، ".join(filter(None, (_contact_label(c) for c in p.contacts if not c.is_archived)))] for p in rows],
                [p.id for p in rows])
            rows = s.scalars(live(LetterType).order_by(LetterType.category, LetterType.id)).all()
            self.tables["letter_types"].set_rows([[t.category, t.title, t.subject_line] for t in rows], [t.id for t in rows])
            rows = s.scalars(live(Clause).order_by(Clause.sort_order)).all()
            self.tables["clauses"].set_rows([[CLAUSE_GROUP_FA.get(c.group, c.group), c.text, c.usage_count or 0]
                                             for c in rows], [c.id for c in rows])
            rows = s.scalars(live(Item).order_by(Item.code)).all()
            self.tables["items"].set_rows([[i.description, i.unit, _rial(i.last_unit_price), i.last_price_source]
                                           for i in rows], [i.id for i in rows])
            rows = s.scalars(live(Account).order_by(Account.id)).all()
            self.tables["accounts"].set_rows(
                [[a.bank, a.holder, format_iban(a.iban), a.issuer.title if a.issuer else "", "بله" if a.active else "خیر"]
                 for a in rows], [a.id for a in rows], ["" if a.active else "#999" for a in rows])
            rows = s.scalars(live(Issuer).order_by(Issuer.id)).all()
            self.tables["issuers"].set_rows(
                [[i.title, i.name, i.signer_name, f"{fmt_percent(i.default_vat_percent)}٪" if i.vat_enabled_by_default else "خاموش",
                  i.number_pattern] for i in rows], [i.id for i in rows])
            rows = s.scalars(live(Unit).order_by(Unit.sort_order)).all()
            self.tables["units"].set_rows([[u.name] for u in rows], [u.id for u in rows])
