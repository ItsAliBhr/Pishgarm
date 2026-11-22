"""Edit dialogs for master data (doc 04 §4.6)."""
from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from sqlalchemy import func, select

from app import paths
from app.core import validators
from app.core.draft import CLAUSE_GROUPS, GROUP_FA, KIND_FA
from app.core.normalize import normalize_text
from app.db.models import Account, Clause, Contact, Issuer, Item, LetterType, Party, Unit
from app.ui.widgets import MoneyEdit, warn

PARTY_KINDS = {"company": "شرکت", "person": "شخص", "bank": "بانک", "government": "دولتی"}
ITEM_CATEGORIES = {"": "—", "refractory": "نسوزکاری", "burner": "مشعل", "fuel": "سیستم سوخت",
                   "automation": "اتوماسیون", "installation": "نصب و خدمات", "goods": "کالا",
                   "service": "خدمات"}
FIELD_TYPES = {"text": "متن", "longtext": "متن بلند", "money": "مبلغ", "int": "عدد", "percent": "درصد",
               "date": "تاریخ", "choice": "انتخابی", "party": "شخص/شرکت"}


def _n(v):
    return normalize_text(v) if isinstance(v, str) else v


class BaseForm(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignLeading)
        self.body = QVBoxLayout(self)
        self.body.addLayout(self.form)
        self.error = QLabel(styleSheet="color:#c62828", wordWrap=True)
        self.error.hide()
        self.buttons = QDialogButtonBox()
        self.buttons.addButton("ذخیره", QDialogButtonBox.AcceptRole)
        self.buttons.addButton("انصراف", QDialogButtonBox.RejectRole)
        self.buttons.accepted.connect(self._try_accept)
        self.buttons.rejected.connect(self.reject)

    def finish_layout(self):
        self.body.addWidget(self.error)
        self.body.addWidget(self.buttons)

    def line(self, label, value="", ltr=False) -> QLineEdit:
        w = QLineEdit(value or "")
        if ltr:
            w.setLayoutDirection(Qt.LeftToRight)
        self.form.addRow(label, w)
        return w

    def text(self, label, value="", height=80) -> QPlainTextEdit:
        w = QPlainTextEdit(value or "")
        w.setFixedHeight(height)
        self.form.addRow(label, w)
        return w

    def check(self, label, value=False) -> QCheckBox:
        w = QCheckBox(label)
        w.setChecked(bool(value))
        self.form.addRow("", w)
        return w

    def combo(self, label, options: dict, value=None) -> QComboBox:
        w = QComboBox()
        for k, v in options.items():
            w.addItem(v, k)
        i = w.findData(value)
        w.setCurrentIndex(max(i, 0))
        self.form.addRow(label, w)
        return w

    def validate(self) -> str | None:
        return None

    def _try_accept(self):
        err = self.validate()
        if err:
            self.error.setText(err)
            self.error.show()
            return
        self.accept()


# ---------------------------------------------------------------- party + contacts

class PartyForm(BaseForm):
    def __init__(self, s, party: Party | None, parent=None):
        super().__init__("شخص / شرکت", parent)
        self.s, self.party = s, party
        p = party or Party(kind="company", name="")
        self.name = self.line("نام کامل:", p.name)
        self.short = self.line("نام کوتاه (نام پوشه):", p.short_name)
        self.kind = self.combo("نوع:", PARTY_KINDS, p.kind)
        self.national_id = self.line("شناسه‌ی ملی / کد ملی:", p.national_id, ltr=True)
        self.economic = self.line("کد اقتصادی:", p.economic_code, ltr=True)
        self.reg = self.line("شماره‌ی ثبت:", p.registration_no, ltr=True)
        self.phone = self.line("تلفن:", p.phone, ltr=True)
        self.fax = self.line("فکس:", p.fax, ltr=True)
        self.postal = self.line("کد پستی:", p.postal_code, ltr=True)
        self.address = self.text("نشانی:", p.address, 60)
        self.archive = self.line("نام پوشه در بایگانی قدیمی:", p.archive_folder)
        self.notes = self.text("یادداشت:", p.notes, 50)

        box = QGroupBox("مخاطبان")
        bl = QVBoxLayout(box)
        self.contacts = QTableWidget(0, 5)
        self.contacts.setHorizontalHeaderLabels(["عنوان", "مهندس/دکتر", "نام", "سمت", "تلفن"])
        self.contacts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.contacts.setSelectionBehavior(QAbstractItemView.SelectRows)
        bl.addWidget(self.contacts)
        row = QHBoxLayout()
        add = QPushButton("+ مخاطب")
        add.clicked.connect(lambda: self._add_contact(None))
        rem = QPushButton("حذف مخاطب")
        rem.clicked.connect(self._remove_contact)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        bl.addLayout(row)
        bl.addWidget(QLabel("ردیف اول مخاطب پیش‌فرض است.", styleSheet="color:#666"))
        self.body.addWidget(box)
        self._contact_ids = []
        for c in (party.contacts if party else []):
            if not c.is_archived:
                self._add_contact(c)
        self.finish_layout()

    def _add_contact(self, c: Contact | None):
        r = self.contacts.rowCount()
        self.contacts.insertRow(r)
        vals = [c.title_prefix if c else "جناب آقای", c.honorific if c else "مهندس",
                c.name if c else "", c.position if c else "", c.phone if c else ""]
        for i, v in enumerate(vals):
            self.contacts.setItem(r, i, QTableWidgetItem(v or ""))
        self._contact_ids.append(c.id if c else None)

    def _remove_contact(self):
        r = self.contacts.currentRow()
        if r >= 0:
            self.contacts.removeRow(r)
            self._contact_ids.pop(r)

    def validate(self):
        if not self.name.text().strip():
            return "نام لازم است."
        nid = normalize_text(self.national_id.text())
        if nid:
            k = self.kind.currentData()
            err = validators.national_code_error(nid) if (k == "person" or len(nid) == 10) else validators.company_id_error(nid)
            if err:
                return err   # a wrong checksum is a real error
        pc = normalize_text(self.postal.text())
        if pc and validators.postal_code_error(pc):
            return validators.postal_code_error(pc)
        return None

    def save(self) -> Party:
        p = self.party
        if p is None:
            n = self.s.scalar(select(func.count(Party.id))) + 1
            p = Party(code=f"P{n:04d}", name="")
            while self.s.scalar(select(Party.id).where(Party.code == p.code)):
                n += 1
                p.code = f"P{n:04d}"
            self.s.add(p)
        p.name, p.short_name = _n(self.name.text()), _n(self.short.text()) or _n(self.name.text())
        p.kind = self.kind.currentData()
        p.national_id, p.economic_code = _n(self.national_id.text()), _n(self.economic.text())
        p.registration_no, p.phone, p.fax = _n(self.reg.text()), _n(self.phone.text()), _n(self.fax.text())
        p.postal_code, p.address = _n(self.postal.text()), _n(self.address.toPlainText())
        p.archive_folder, p.notes = _n(self.archive.text()), _n(self.notes.toPlainText())
        keep = set()
        for r in range(self.contacts.rowCount()):
            vals = [_n(self.contacts.item(r, i).text() if self.contacts.item(r, i) else "") for i in range(5)]
            if not vals[2]:
                continue
            cid = self._contact_ids[r]
            c = self.s.get(Contact, cid) if cid else None
            if c is None:
                c = Contact()
                p.contacts.append(c)
            c.title_prefix, c.honorific, c.name, c.position, c.phone = vals
            c.is_default = not keep and r == min(i for i in range(self.contacts.rowCount())
                                                 if self.contacts.item(i, 2) and self.contacts.item(i, 2).text().strip())
            c.is_archived = False
            keep.add(id(c))
        for c in p.contacts:
            if id(c) not in keep:
                c.is_archived = True   # soft delete: old documents still point at it
                c.is_default = False
        self.s.commit()
        return p


# ---------------------------------------------------------------- account

class AccountForm(BaseForm):
    def __init__(self, s, acc: Account | None, parent=None):
        super().__init__("حساب بانکی", parent)
        self.s, self.acc = s, acc
        a = acc or Account(code="", active=True)
        issuers = {None: "— (همه)"} | {i.id: i.title for i in s.scalars(select(Issuer))}
        self.issuer = self.combo("سربرگ:", issuers, a.issuer_id)
        self.bank = self.line("بانک:", a.bank)
        self.branch = self.line("شعبه:", a.branch)
        self.holder = self.line("صاحب حساب:", a.holder)
        self.iban = self.line("شبا:", validators.format_iban(a.iban) if a.iban else "", ltr=True)
        self.iban_msg = QLabel(styleSheet="color:#c62828")
        self.form.addRow("", self.iban_msg)
        self.iban.textChanged.connect(self._check_iban)
        self.account_no = self.line("شماره حساب:", a.account_no, ltr=True)
        self.card = self.line("شماره کارت:", a.card_no, ltr=True)
        self.active = self.check("فعال", a.active)
        self.notes = self.text("یادداشت:", a.notes, 50)
        self.finish_layout()

    def _check_iban(self, t):
        err = validators.iban_error(t) if t.strip() else None
        self.iban_msg.setText(err or ("✓ شبا معتبر است" if t.strip() else ""))
        self.iban_msg.setStyleSheet("color:#c62828" if err else "color:#2e7d32")

    def validate(self):
        if not self.bank.text().strip() or not self.holder.text().strip():
            return "بانک و صاحب حساب لازم است."
        return validators.iban_error(self.iban.text())

    def save(self) -> Account:
        a = self.acc
        if a is None:
            n = self.s.scalar(select(func.count(Account.id))) + 1
            a = Account(code=f"ACC{n:03d}")
            self.s.add(a)
        a.issuer_id = self.issuer.currentData()
        a.bank, a.branch, a.holder = _n(self.bank.text()), _n(self.branch.text()), _n(self.holder.text())
        a.iban = validators.clean_iban(self.iban.text())
        a.account_no, a.card_no = _n(self.account_no.text()), _n(self.card.text())
        a.active, a.notes = self.active.isChecked(), _n(self.notes.toPlainText())
        self.s.commit()
        return a


# ---------------------------------------------------------------- item

class ItemForm(BaseForm):
    def __init__(self, s, item: Item | None, parent=None):
        super().__init__("قلم کالا / خدمات", parent)
        self.s, self.item = s, item
        it = item or Item(code="", description="")
        self.desc = self.text("شرح:", it.description, 60)
        units = {u.name: u.name for u in s.scalars(select(Unit).where(Unit.is_archived.is_(False)).order_by(Unit.sort_order))}
        if it.unit and it.unit not in units:
            units[it.unit] = it.unit
        self.unit = self.combo("واحد:", units, it.unit or "عدد")
        cats = dict(ITEM_CATEGORIES)
        if it.category and it.category not in cats:
            cats[it.category] = it.category
        self.category = self.combo("دسته:", cats, it.category or "")
        self.price = MoneyEdit("rial")
        self.price.setValue(it.last_unit_price or 0, "rial")
        self.form.addRow("آخرین قیمت واحد:", self.price)
        self.source = self.line("منبع قیمت:", it.last_price_source)
        self.purchase = MoneyEdit("rial")
        self.purchase.setValue(it.last_purchase_price or 0, "rial")
        self.form.addRow("قیمت خرید (فقط داخلی):", self.purchase)
        self.buyer = self.check("معمولاً تأمین خریدار است", it.buyer_supplied_by_default)
        self.finish_layout()

    def validate(self):
        return None if self.desc.toPlainText().strip() else "شرح لازم است."

    def save(self) -> Item:
        from datetime import date
        it = self.item
        if it is None:
            n = self.s.scalar(select(func.count(Item.id))) + 1
            it = Item(code=f"IT{n:03d}", description="")
            while self.s.scalar(select(Item.id).where(Item.code == it.code)):
                n += 1
                it.code = f"IT{n:03d}"
            self.s.add(it)
        it.description = _n(self.desc.toPlainText())
        it.unit, it.category = self.unit.currentData(), self.category.currentData()
        if self.price.value() != (it.last_unit_price or 0):
            it.last_price_date = date.today()
        it.last_unit_price = self.price.value() or None
        it.last_price_source = _n(self.source.text())
        it.last_purchase_price = self.purchase.value() or None
        it.buyer_supplied_by_default = self.buyer.isChecked()
        self.s.commit()
        return it


# ---------------------------------------------------------------- clause

class ClauseForm(BaseForm):
    def __init__(self, s, clause: Clause | None, parent=None):
        super().__init__("بند", parent)
        self.s, self.clause = s, clause
        c = clause or Clause(code="", group="other", text="")
        self.group = self.combo("گروه:", {g: GROUP_FA[g] for g in CLAUSE_GROUPS}, c.group)
        self.body_text = self.text("متن بند:", c.text, 90)
        self.form.addRow("", QLabel("متغیرها را با {نام} بنویسید، مثل {advance_percent}. متغیرهای آماده: "
                                    "{advance_amount} {rest_percent} {rest_amount} {vat_percent} {payable} {iban} {bank} {holder}",
                                    wordWrap=True, styleSheet="color:#666"))
        vars_text = "\n".join(f"{k}={(v or {}).get('default', '')}" for k, v in (c.variables or {}).items())
        self.vars = self.text("مقدار پیش‌فرض متغیرها (هر خط: نام=مقدار):", vars_text, 60)
        box = QWidget()
        hl = QHBoxLayout(box)
        hl.setContentsMargins(0, 0, 0, 0)
        self.applies = {}
        for k in ("proforma", "invoice", "letter"):
            cb = QCheckBox(KIND_FA[k] + (" / صورت‌وضعیت" if k == "invoice" else ""))
            cb.setChecked(k in (c.applies_to or ["proforma", "invoice"]))
            self.applies[k] = cb
            hl.addWidget(cb)
        self.form.addRow("برای:", box)
        box2 = QWidget()
        hl2 = QHBoxLayout(box2)
        hl2.setContentsMargins(0, 0, 0, 0)
        self.defaults = {}
        for i in s.scalars(select(Issuer)):
            cb = QCheckBox(i.title)
            cb.setChecked(i.code in (c.default_for_issuers or []))
            self.defaults[i.code] = cb
            hl2.addWidget(cb)
        self.form.addRow("پیش‌فرض برای سربرگ:", box2)
        vat = (c.requires or {}).get("vat_enabled")
        self.requires = self.combo("سازگاری با ارزش افزوده:", {"any": "فرقی نمی‌کند", "on": "فقط وقتی روشن است",
                                                                "off": "فقط وقتی خاموش است"},
                                   "any" if vat is None else ("on" if vat else "off"))
        self.no_install = self.check("با ردیف نصب ناسازگار است", "category:installation" in (c.excludes or []))
        self.finish_layout()

    def validate(self):
        return None if self.body_text.toPlainText().strip() else "متن بند لازم است."

    def save(self) -> Clause:
        c = self.clause
        if c is None:
            n = self.s.scalar(select(func.count(Clause.id))) + 1
            c = Clause(code=f"USER_{n:03d}", group="other", text="",
                       sort_order=(self.s.scalar(select(func.max(Clause.sort_order))) or 0) + 1)
            while self.s.scalar(select(Clause.id).where(Clause.code == c.code)):
                n += 1
                c.code = f"USER_{n:03d}"
            self.s.add(c)
        c.group = self.group.currentData()
        c.text = _n(self.body_text.toPlainText())
        variables = {}
        for line in self.vars.toPlainText().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), _n(v.strip())
                if k:
                    try:
                        dv = int(v) if v.isdigit() else float(v)
                    except ValueError:
                        dv = v
                    variables[k] = {"type": "text", "default": dv}
        c.variables = variables
        c.applies_to = [k for k, cb in self.applies.items() if cb.isChecked()]
        c.default_for_issuers = [k for k, cb in self.defaults.items() if cb.isChecked()]
        r = self.requires.currentData()
        c.requires = {} if r == "any" else {"vat_enabled": r == "on"}
        c.excludes = ["category:installation"] if self.no_install.isChecked() else []
        self.s.commit()
        return c


# ---------------------------------------------------------------- letter type

class LetterTypeForm(BaseForm):
    def __init__(self, s, lt: LetterType | None, parent=None):
        super().__init__("موضوع نامه", parent)
        self.setMinimumWidth(760)
        self.s, self.lt = s, lt
        t = lt or LetterType(code="", title="", body=[], fields=[])
        self.category = self.line("دسته:", t.category)
        self.title_e = self.line("عنوان:", t.title)
        self.subject = self.line("خط موضوع:", t.subject_line)
        self.fields_tbl = QTableWidget(0, 4)
        self.fields_tbl.setHorizontalHeaderLabels(["نام (انگلیسی)", "برچسب", "نوع", "الزامی"])
        self.fields_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fields_tbl.setMinimumHeight(150)
        for f in t.fields or []:
            self._add_field(f)
        fb = QHBoxLayout()
        a = QPushButton("+ فیلد")
        a.clicked.connect(lambda: self._add_field({}))
        r = QPushButton("حذف فیلد")
        r.clicked.connect(lambda: self.fields_tbl.removeRow(self.fields_tbl.currentRow()))
        fb.addWidget(a)
        fb.addWidget(r)
        fb.addStretch(1)
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.fields_tbl)
        fl.addLayout(fb)
        self.form.addRow("فیلدها:", fw)
        self.body_e = self.text("متن (هر پاراگراف در یک خط؛ جای‌خالی با {نام_فیلد}):", "\n".join(t.body or []), 140)
        self.form.addRow("", QLabel("متغیرهای عمومی: {customer_name} {issuer_name} {issuer_national_id} {contact_full} "
                                    "{project_title} {contract_no} {contract_date} {amount_words} {iban} {bank} {holder} {today}",
                                    wordWrap=True, styleSheet="color:#666"))
        self.closing = self.line("عبارت پایانی:", t.closing)
        self.with_items = self.check("جدول ردیف‌ها دارد", t.with_items_table)
        self.with_clauses = self.check("بندهای انتخابی دارد", t.with_clauses)
        self.with_account = self.check("شماره حساب دارد", t.with_account)
        self.preview = QLabel(wordWrap=True, styleSheet="background:#f7f7f7; padding:6px")
        self.form.addRow("پیش‌نمایش با مقادیر نمونه:", self.preview)
        self.body_e.textChanged.connect(self._preview)
        self._preview()
        self.finish_layout()

    def _add_field(self, f: dict):
        r = self.fields_tbl.rowCount()
        self.fields_tbl.insertRow(r)
        self.fields_tbl.setItem(r, 0, QTableWidgetItem(f.get("name", "")))
        self.fields_tbl.setItem(r, 1, QTableWidgetItem(f.get("label", "")))
        cb = QComboBox()
        for k, v in FIELD_TYPES.items():
            cb.addItem(v, k)
        cb.setCurrentIndex(max(cb.findData(f.get("type", "text")), 0))
        self.fields_tbl.setCellWidget(r, 2, cb)
        chk = QTableWidgetItem()
        chk.setCheckState(Qt.Checked if f.get("required") else Qt.Unchecked)
        self.fields_tbl.setItem(r, 3, chk)

    def _fields(self) -> list[dict]:
        out = []
        for r in range(self.fields_tbl.rowCount()):
            name = (self.fields_tbl.item(r, 0).text() if self.fields_tbl.item(r, 0) else "").strip()
            if not name:
                continue
            out.append({"name": name, "label": _n(self.fields_tbl.item(r, 1).text() if self.fields_tbl.item(r, 1) else name),
                        "type": self.fields_tbl.cellWidget(r, 2).currentData(),
                        "required": self.fields_tbl.item(r, 3).checkState() == Qt.Checked})
        return out

    def _preview(self):
        from app.core.clauses import fill
        sample = {f["name"]: f"[{f['label']}]" for f in self._fields()}
        sample.update({"customer_name": "شرکت نمونه", "issuer_name": "شرکت پیشگرم سازان", "amount_words": "[مبلغ به حروف]"})
        self.preview.setText("<br>".join(fill(p, sample) for p in self.body_e.toPlainText().splitlines() if p.strip()))

    def validate(self):
        return None if self.title_e.text().strip() else "عنوان لازم است."

    def save(self) -> LetterType:
        t = self.lt
        if t is None:
            n = self.s.scalar(select(func.count(LetterType.id))) + 1
            t = LetterType(code=f"USER_LT_{n:03d}", title="")
            while self.s.scalar(select(LetterType.id).where(LetterType.code == t.code)):
                n += 1
                t.code = f"USER_LT_{n:03d}"
            self.s.add(t)
        t.category, t.title, t.subject_line = _n(self.category.text()), _n(self.title_e.text()), _n(self.subject.text())
        t.fields = self._fields()
        t.body = [_n(p) for p in self.body_e.toPlainText().splitlines() if p.strip()]
        t.closing = _n(self.closing.text())
        t.with_items_table, t.with_clauses, t.with_account = (self.with_items.isChecked(),
                                                              self.with_clauses.isChecked(), self.with_account.isChecked())
        self.s.commit()
        return t


# ---------------------------------------------------------------- issuer (letterhead)

class IssuerForm(BaseForm):
    def __init__(self, s, issuer: Issuer, parent=None):
        super().__init__("سربرگ", parent)
        self.s, self.i = s, issuer
        i = issuer
        self.title_e = self.line("عنوان در برنامه:", i.title)
        self.name = self.line("نام در سند:", i.name)
        self.signer = self.line("نام امضاکننده:", i.signer_name)
        self.signer_title = self.line("سمت امضاکننده:", i.signer_title)
        self.national_id = self.line("شناسه/کد ملی:", i.national_id, ltr=True)
        self.economic = self.line("کد اقتصادی:", i.economic_code, ltr=True)
        self.reg = self.line("شماره‌ی ثبت:", i.registration_no, ltr=True)
        self.phone = self.line("تلفن:", i.phone, ltr=True)
        self.mobile = self.line("موبایل:", i.mobile, ltr=True)
        self.fax = self.line("فکس:", i.fax, ltr=True)
        self.postal = self.line("کد پستی:", i.postal_code, ltr=True)
        self.address = self.text("نشانی:", i.address, 50)
        self.vat_on = self.check("ارزش افزوده به‌طور پیش‌فرض روشن", i.vat_enabled_by_default)
        self.vat = QDoubleSpinBox(decimals=2, maximum=100)
        self.vat.setValue(float(i.default_vat_percent or 0))
        self.form.addRow("درصد ارزش افزوده:", self.vat)
        self.stamp_on = self.check("مهر به‌طور پیش‌فرض روشن", i.show_stamp_by_default)
        self.pattern = self.line("الگوی شماره:", i.number_pattern, ltr=True)
        self.form.addRow("", QLabel("{seq:03} شماره‌ی ترتیبی سه‌رقمی، {yyyy} سال، {yyy} سه رقم آخر سال، {mm} ماه دورقمی، "
                                    "{m} ماه، {kind} حرف نوع سند", wordWrap=True, styleSheet="color:#666"))
        self.scope = self.combo("شروع دوباره‌ی شماره:", {"per_year": "هر سال", "per_month": "هر ماه",
                                                          "continuous": "هرگز"}, i.number_scope)
        accs = s.scalars(select(Account).where(Account.is_archived.is_(False))).all()
        accw = QWidget()
        al = QVBoxLayout(accw)
        al.setContentsMargins(0, 0, 0, 0)
        self.acc_checks = {}
        for a in accs:
            cb = QCheckBox(f"{a.bank} – {a.holder} – {a.iban}")
            cb.setChecked(a.code in (i.default_account_codes or []))
            self.acc_checks[a.code] = cb
            al.addWidget(cb)
        self.form.addRow("حساب‌های پیش‌فرض:", accw)
        self.stamp_path = self._image_row("تصویر مهر:", i.stamp_image)
        self.sign_path = self._image_row("تصویر امضا:", i.signature_image)
        self.finish_layout()

    def _image_row(self, label, value):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        e = QLineEdit(value or "")
        e.setReadOnly(True)
        b = QPushButton("انتخاب…")

        def pick():
            f, _ = QFileDialog.getOpenFileName(self, label, "", "Images (*.png *.jpg *.jpeg)")
            if f:
                dest = paths.user_assets_dir() / Path(f).name
                if Path(f) != dest:
                    shutil.copy2(f, dest)
                e.setText(str(dest))
        b.clicked.connect(pick)
        h.addWidget(e, 1)
        h.addWidget(b)
        self.form.addRow(label, w)
        return e

    def save(self) -> Issuer:
        i = self.i
        i.title, i.name, i.signer_name = _n(self.title_e.text()), _n(self.name.text()), _n(self.signer.text())
        i.signer_title, i.national_id = _n(self.signer_title.text()), _n(self.national_id.text())
        i.economic_code, i.registration_no = _n(self.economic.text()), _n(self.reg.text())
        i.phone, i.mobile, i.fax = _n(self.phone.text()), _n(self.mobile.text()), _n(self.fax.text())
        i.postal_code, i.address = _n(self.postal.text()), _n(self.address.toPlainText())
        i.vat_enabled_by_default, i.default_vat_percent = self.vat_on.isChecked(), Decimal(str(self.vat.value()))
        i.show_stamp_by_default = self.stamp_on.isChecked()
        i.number_pattern, i.number_scope = self.pattern.text().strip(), self.scope.currentData()
        i.default_account_codes = [k for k, cb in self.acc_checks.items() if cb.isChecked()]
        i.stamp_image = self.stamp_path.text() or None
        i.signature_image = self.sign_path.text() or None
        self.s.commit()
        return i


class UnitForm(BaseForm):
    def __init__(self, s, unit: Unit | None, parent=None):
        super().__init__("واحد", parent)
        self.s, self.unit = s, unit
        self.name = self.line("نام واحد:", unit.name if unit else "")
        self.finish_layout()

    def validate(self):
        name = _n(self.name.text())
        if not name:
            return "نام لازم است."
        other = self.s.scalar(select(Unit).where(Unit.name == name))
        if other and other is not self.unit:
            return "این واحد وجود دارد."
        return None

    def save(self) -> Unit:
        u = self.unit
        if u is None:
            u = Unit(name="", sort_order=(self.s.scalar(select(func.max(Unit.sort_order))) or 0) + 1)
            self.s.add(u)
        u.name = _n(self.name.text())
        self.s.commit()
        return u
