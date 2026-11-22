"""اطلاعات پایه — read-only lists for phase 0; edit forms arrive in phase 1."""
from __future__ import annotations

from sqlalchemy import select
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.core.validators import format_iban
from app.db.models import Account, Clause, Issuer, Item, LetterType, Party, Unit
from app.ui.widgets import SearchTable

PARTY_KIND_FA = {"company": "شرکت", "person": "شخص", "bank": "بانک", "government": "دولتی"}
CLAUSE_GROUP_FA = {"payment": "شرایط پرداخت", "delivery": "حمل و زمان", "tax": "مالیات و بیمه",
                   "site": "تعهدات کارفرما", "other": "سایر", "note": "توضیحات"}


def _contact_label(c) -> str:
    text = " ".join(p for p in (c.honorific, c.name) if p)
    return f"{text} ({c.position})" if c.position else text


def _rial(v) -> str:
    return "" if v is None else f"{int(v):,}"


class MasterDataPage(QWidget):
    TABS = ["parties", "letter_types", "clauses", "items", "accounts", "issuers", "units"]

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.SessionLocal = SessionLocal
        self.tabs = QTabWidget()
        self.tables: dict[str, SearchTable] = {
            "parties": SearchTable(["نام", "نام کوتاه", "نوع", "شناسه ملی", "کد اقتصادی", "تلفن",
                                    "مخاطبان"]),
            "letter_types": SearchTable(["دسته", "عنوان", "خط موضوع"]),
            "clauses": SearchTable(["گروه", "متن بند", "کد"]),
            "items": SearchTable(["شرح", "واحد", "آخرین قیمت واحد (ریال)", "منبع قیمت"]),
            "accounts": SearchTable(["بانک", "صاحب حساب", "شبا", "سربرگ", "فعال"]),
            "issuers": SearchTable(["عنوان", "نام در سند", "امضاکننده", "ارزش افزوده پیش‌فرض",
                                    "الگوی شماره"]),
            "units": SearchTable(["واحد"]),
        }
        labels = {"parties": "اشخاص و شرکت‌ها", "letter_types": "موضوعات نامه", "clauses": "بندها",
                  "items": "اقلام", "accounts": "حساب‌ها", "issuers": "سربرگ‌ها", "units": "واحدها"}
        for key in self.TABS:
            self.tabs.addTab(self.tables[key], labels[key])
        QVBoxLayout(self).addWidget(self.tabs)
        self.refresh()

    def refresh(self) -> None:
        with self.SessionLocal() as s:
            live = lambda m: select(m).where(m.is_archived.is_(False))  # noqa: E731
            self.tables["parties"].set_rows([
                [p.name, p.short_name, PARTY_KIND_FA.get(p.kind, p.kind), p.national_id,
                 p.economic_code, p.phone, "، ".join(filter(None, (_contact_label(c) for c in p.contacts)))]
                for p in s.scalars(live(Party).order_by(Party.name))])
            self.tables["letter_types"].set_rows([
                [t.category, t.title, t.subject_line]
                for t in s.scalars(live(LetterType).order_by(LetterType.category, LetterType.id))])
            self.tables["clauses"].set_rows([
                [CLAUSE_GROUP_FA.get(c.group, c.group), c.text, c.code]
                for c in s.scalars(live(Clause).order_by(Clause.sort_order))])
            self.tables["items"].set_rows([
                [i.description, i.unit, _rial(i.last_unit_price), i.last_price_source]
                for i in s.scalars(live(Item).order_by(Item.code))])
            self.tables["accounts"].set_rows([
                [a.bank, a.holder, format_iban(a.iban), a.issuer.title if a.issuer else "",
                 "بله" if a.active else "خیر"]
                for a in s.scalars(live(Account).order_by(Account.id))])
            self.tables["issuers"].set_rows([
                [i.title, i.name, i.signer_name,
                 f"{i.default_vat_percent:g}٪" if i.vat_enabled_by_default else "خاموش",
                 i.number_pattern]
                for i in s.scalars(live(Issuer).order_by(Issuer.id))])
            self.tables["units"].set_rows([[u.name] for u in s.scalars(live(Unit).order_by(Unit.sort_order))])
