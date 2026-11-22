"""«سند جدید» wizard: type → letterhead → customer → content → clauses → attachments & output
(doc 04 §4.2). Drafts are saved automatically on every step change."""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QScrollArea, QSplitter, QStackedWidget, QVBoxLayout, QWidget)
from sqlalchemy import select

from app.core import jalali, letters, money
from app.core.clauses import Issue
from app.core.context import build_context
from app.core.draft import KIND_FA, TITLE_BY_KIND, Draft
from app.core.num2words_fa import rial_words
from app.db.models import (Account, Clause, Contact, Document, Issuer, Item, LetterType, Party,
                           Project, Unit)
from app.db.repo import get_setting
from app.services import documents as docs
from app.services.convert import account_info, clause_sel, party_dict, project_dict
from app.ui.clause_picker import ClausePicker
from app.ui.erase_dialog import EraseDialog
from app.ui.lines_editor import LinesEditor
from app.ui.widgets import (IssuesBox, JalaliDateEdit, MoneyEdit, SearchCombo, confirm, info, warn)
from app.ui.worker import run_busy

STEPS = ["نوع سند", "سربرگ", "مشتری و پروژه", "محتوا", "بندها و حساب", "پیوست‌ها و خروجی"]
KIND_ORDER = ["letter", "proforma", "invoice", "statement", "attachment_list"]
KIND_HINT = {"letter": "اعلام قیمت، درخواست پرداخت، اخطار، …", "proforma": "پیش‌فاکتور فروش و خدمات",
             "invoice": "فاکتور فروش و خدمات", "statement": "صورت وضعیت کار انجام‌شده",
             "attachment_list": "لیست اقلام (پیوست)"}
BUYER_FIELDS = [("address", "نشانی"), ("phone", "تلفن"), ("national_id", "شناسه‌ی ملی"),
                ("economic_code", "کد اقتصادی"), ("registration_no", "شماره‌ی ثبت"), ("postal_code", "کد پستی")]
NEW_PROJECT = "__new__"


def card(text: str, sub: str = "") -> QPushButton:
    b = QPushButton(f"{text}\n{sub}" if sub else text)
    b.setCheckable(True)
    b.setObjectName("card")
    b.setMinimumSize(180, 90)
    return b


def _choice_options(field: dict, settings_refs: list[str]) -> list[str]:
    name = field.get("name")
    if name == "reference":
        return settings_refs
    if name == "warning_no":
        return ["اول", "دوم", "سوم"]
    if name == "person_title":
        return ["آقای", "خانم"]
    m = re.search(r"\(([^)]*/[^)]*)\)", field.get("label", ""))
    return [o.strip() for o in m.group(1).split("/")] if m else []


class DocumentWizard(QDialog):
    def __init__(self, SessionLocal, doc_id: int | None = None, preset: dict | None = None, parent=None):
        super().__init__(parent)
        self.S = SessionLocal
        self.setWindowTitle("سند جدید")
        self.resize(1280, 820)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.doc_id = doc_id
        self.preset = preset or {}
        self.kind: str | None = self.preset.get("kind")
        self.issuer_id: int | None = self.preset.get("issuer_id")
        self.draft: Draft | None = None
        self.attachments: list = [{"type": "document"}]
        self.party_override: dict | None = None
        self.issued = False
        self.current = 0
        self._loading = False

        with self.S() as s:
            self.settings_refs = get_setting(s, "references", []) or []
            self.salutations = get_setting(s, "salutations", []) or []
            self.closings = get_setting(s, "closings", []) or []
            self.header_lines = get_setting(s, "letter_header_lines", ["باسمه تعالی"]) or ["باسمه تعالی"]
            self.addr_formats = letters.addressee_formats(get_setting(s, "addressee_formats", []))
            self.markup_step = int(get_setting(s, "markup_round_step_rial", 1) or 1)

        # ---------------- layout: steps bar / pages + summary / buttons
        self.step_buttons = []
        bar = QHBoxLayout()
        for i, name in enumerate(STEPS):
            b = QPushButton(f"{i + 1}. {name}")
            b.setCheckable(True)
            b.setObjectName("step")
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=i: self.go(k))
            bar.addWidget(b)
            self.step_buttons.append(b)

        self.pages = QStackedWidget()
        for build in (self._build_type, self._build_issuer, self._build_party, self._build_content,
                      self._build_clauses, self._build_output):
            w = build()
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(w)
            sc.setFrameShape(QFrame.NoFrame)
            self.pages.addWidget(sc)

        self.summary = QLabel(wordWrap=True)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setAlignment(Qt.AlignTop)
        self.summary_issues = IssuesBox()
        sv = QVBoxLayout()
        sv.addWidget(QLabel("<b>خلاصه</b>"))
        sv.addWidget(self.summary)
        sv.addWidget(self.summary_issues)
        sv.addStretch(1)
        sw = QFrame()
        sw.setObjectName("summary")
        sw.setLayout(sv)
        sw.setMinimumWidth(270)
        sw.setMaximumWidth(340)

        split = QHBoxLayout()
        split.addWidget(self.pages, 1)
        split.addWidget(sw)

        self.prev_btn = QPushButton("→ قبلی")
        self.prev_btn.clicked.connect(lambda: self.go(self.current - 1))
        self.next_btn = QPushButton("بعدی ←")
        self.next_btn.setObjectName("primary")
        self.next_btn.clicked.connect(lambda: self.go(self.current + 1))
        self.save_btn = QPushButton("ذخیره‌ی پیش‌نویس")
        self.save_btn.clicked.connect(lambda: (self.collect(), self.save(), info(self, "پیش‌نویس ذخیره شد.")))
        close = QPushButton("بستن")
        close.setToolTip("پیش‌نویس ذخیره می‌شود و از صفحه‌ی «اسناد» قابل ادامه است.")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(close)
        bottom.addWidget(self.save_btn)
        bottom.addStretch(1)
        bottom.addWidget(self.prev_btn)
        bottom.addWidget(self.next_btn)

        lay = QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addLayout(split, 1)
        lay.addLayout(bottom)

        if doc_id:
            self._load_existing(doc_id)
        elif self.kind and self.issuer_id:
            self._ensure_draft()
            self._enter(2)
        elif self.kind:
            self._enter(1)
        else:
            self._enter(0)

    # ================================================================ step 1: type
    def _build_type(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>چه سندی می‌خواهید بسازید؟</h2>"))
        grid = QGridLayout()
        self.kind_cards = {}
        for i, k in enumerate(KIND_ORDER):
            c = card(KIND_FA[k], KIND_HINT[k])
            c.clicked.connect(lambda _=False, kk=k: self._pick_kind(kk))
            grid.addWidget(c, i // 3, i % 3)
            self.kind_cards[k] = c
        lay.addLayout(grid)
        box = QGroupBox("یا کپی از یک سند قبلی…")
        bl = QHBoxLayout(box)
        self.copy_combo = SearchCombo(placeholder="نام مشتری، شماره یا موضوع را تایپ کنید…")
        self.copy_other_party = SearchCombo(placeholder="(اختیاری) برای مشتری دیگر")
        b = QPushButton("کپی و ادامه")
        b.clicked.connect(self._copy_from)
        bl.addWidget(self.copy_combo, 2)
        bl.addWidget(self.copy_other_party, 1)
        bl.addWidget(b)
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _fill_copy_sources(self):
        with self.S() as s:
            rows = s.scalars(select(Document).where(Document.is_archived.is_(False), Document.kind != "attachment_list")
                             .order_by(Document.id.desc()).limit(500)).all()
            items = []
            for d in rows:
                who = d.party.short_name or d.party.name if d.party else ""
                items.append((f"{KIND_FA[d.kind]} {d.number or '(پیش‌نویس)'} – {who} – {d.subject or d.title} – {d.date_jalali}", d.id))
            self.copy_combo.set_items(items, keep=False)
            self.copy_other_party.set_items(self._party_items(s), keep=False)

    def _pick_kind(self, k):
        for kk, c in self.kind_cards.items():
            c.setChecked(kk == k)
        self.kind = k
        self.go(1)

    def _copy_from(self):
        src = self.copy_combo.current_id()
        if not src:
            return
        with self.S() as s:
            doc = docs.copy_document(s, src, self.copy_other_party.current_id())
            new_id = doc.id
        self._load_existing(new_id)

    # ================================================================ step 2: issuer
    def _build_issuer(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>با کدام سربرگ؟</h2>"))
        row = QHBoxLayout()
        self.issuer_cards = {}
        with self.S() as s:
            for i in s.scalars(select(Issuer).where(Issuer.is_archived.is_(False)).order_by(Issuer.id)):
                sub = "ارزش افزوده و مهر روشن" if i.vat_enabled_by_default else "بدون ارزش افزوده"
                c = card(i.title, sub)
                c.setMinimumSize(300, 110)
                c.clicked.connect(lambda _=False, iid=i.id: self._pick_issuer(iid))
                row.addWidget(c)
                self.issuer_cards[i.id] = c
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(QLabel("سربرگ تعیین می‌کند: ارزش افزوده، مهر، حساب‌های پیش‌فرض، قالب Word و الگوی شماره.",
                             styleSheet="color:#666"))
        lay.addStretch(1)
        return w

    def _pick_issuer(self, iid):
        for k, c in self.issuer_cards.items():
            c.setChecked(k == iid)
        self.issuer_id = iid
        self._ensure_draft()
        self.go(2)

    def _ensure_draft(self):
        """Create the draft for (kind, issuer); keep what was entered when either changes."""
        old = self.draft
        if old and old.kind == self.kind and old.issuer.get("id") == self.issuer_id:
            return
        with self.S() as s:
            d = docs.new_draft(s, self.kind, self.issuer_id)
            if old:
                d.party, d.contact, d.project, d.date = old.party, old.contact, old.project, old.date
                d.lines, d.fields, d.letter_type = old.lines, old.fields, old.letter_type
                d.list_title, d.list_subtitle = old.list_title, old.list_subtitle
            else:
                if self.preset.get("project_id"):
                    d.project = project_dict(s.get(Project, self.preset["project_id"]))
                pid = self.preset.get("party_id") or (d.project or {}).get("party_id")
                if pid:
                    docs.apply_party(s, d, pid)
                if self.preset.get("letter_type"):
                    lt = s.scalar(select(LetterType).where(LetterType.code == self.preset["letter_type"]))
                    if lt:
                        docs.apply_letter_type(s, d, lt.id)
            if d.party.get("id"):
                d.clauses = docs.default_clauses(s, d.kind, d.issuer["code"], d.party["id"])
                if d.kind == "letter" and d.letter_type and not d.letter_type.get("with_clauses"):
                    d.clauses = [c for c in d.clauses if c.code == "PAY_TO_ACCOUNT" and d.letter_type.get("with_account")]
            self.draft = d
            self.setWindowTitle(f"{KIND_FA[self.kind]} – {d.issuer.get('title', '')}")

    # ================================================================ step 3: party & project
    def _party_items(self, s):
        rows = s.scalars(select(Party).where(Party.is_archived.is_(False)).order_by(Party.name)).all()
        return [(p.name + (f" ({p.short_name})" if p.short_name and p.short_name not in p.name else ""), p.id) for p in rows]

    def _build_party(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        f = QFormLayout()
        prow = QHBoxLayout()
        self.party_combo = SearchCombo(placeholder="چند حرف از نام مشتری…")
        self.party_combo.idChanged.connect(self._on_party)
        addp = QPushButton("+ افزودن")
        addp.clicked.connect(self._new_party)
        editp = QPushButton("ویرایش…")
        editp.clicked.connect(self._edit_party)
        prow.addWidget(self.party_combo, 1)
        prow.addWidget(addp)
        prow.addWidget(editp)
        f.addRow("مشتری / گیرنده:", prow)
        self.buyer_edits = {}
        for key, label in BUYER_FIELDS:
            e = QLineEdit()
            if key != "address":
                e.setLayoutDirection(Qt.LeftToRight)
            e.textEdited.connect(lambda _t: self._update_summary())
            self.buyer_edits[key] = e
            f.addRow(label + ":", e)
        self.save_to_book = QCheckBox("تغییرات این اطلاعات در دفتر هم ذخیره شود")
        self.save_to_book.setChecked(True)
        f.addRow("", self.save_to_book)
        crow = QHBoxLayout()
        self.contact_combo = QComboBox()
        self.contact_combo.currentIndexChanged.connect(lambda _: self._on_contact())
        crow.addWidget(self.contact_combo, 1)
        f.addRow("مخاطب:", crow)
        prj = QHBoxLayout()
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(lambda _: self._on_project())
        self.new_project = QLineEdit(placeholderText="عنوان پروژه‌ی جدید")
        self.new_project.hide()
        prj.addWidget(self.project_combo, 1)
        prj.addWidget(self.new_project, 1)
        f.addRow("پروژه (پوشه):", prj)
        self.date_edit = JalaliDateEdit()
        self.date_edit.dateChanged.connect(lambda _: self._on_date())
        f.addRow("تاریخ:", self.date_edit)
        nrow = QHBoxLayout()
        self.number_edit = QLineEdit()
        self.number_edit.setLayoutDirection(Qt.LeftToRight)
        self.number_edit.setMaximumWidth(160)
        self.number_hint = QLabel(styleSheet="color:#666")
        nrow.addWidget(self.number_edit)
        nrow.addWidget(self.number_hint, 1)
        f.addRow("شماره:", nrow)
        lay.addLayout(f)

        self.addr_box = QGroupBox("گیرنده‌ی نامه")
        al = QFormLayout(self.addr_box)
        self.addr_format = QComboBox()
        for fmt in self.addr_formats:
            self.addr_format.addItem(fmt.replace("\n", " ⏎ "), fmt)
        self.addr_format.currentIndexChanged.connect(lambda _: self._rebuild_addressee())
        self.addr_text = QPlainTextEdit()
        self.addr_text.setFixedHeight(80)
        self.addr_manual = QCheckBox("ویرایش دستی")
        self.addr_manual.toggled.connect(lambda on: (self.addr_text.setReadOnly(not on),
                                                     None if on else self._rebuild_addressee()))
        self.addr_text.setReadOnly(True)
        al.addRow("چینش:", self.addr_format)
        al.addRow("خطوط:", self.addr_text)
        al.addRow("", self.addr_manual)
        lay.addWidget(self.addr_box)
        lay.addStretch(1)
        return w

    def _load_party_step(self):
        d = self.draft
        self._loading = True
        with self.S() as s:
            self.party_combo.set_items(self._party_items(s), keep=False)
        self.party_combo.set_current_id(d.party.get("id"))
        self._fill_party_fields()
        self.date_edit.setDate(d.date)
        self.number_edit.setText(d.number)
        self._refresh_number_hint()
        self.addr_box.setVisible(d.kind == "letter")
        if d.kind == "letter":
            self.addr_format.setCurrentIndex(min(d.addressee_format, self.addr_format.count() - 1))
            self.addr_manual.setChecked(d.addressee_lines is not None)
            if d.addressee_lines is not None:
                self.addr_text.setPlainText("\n".join(d.addressee_lines))
        self._loading = False
        if d.kind == "letter" and d.addressee_lines is None:
            self._rebuild_addressee()

    def _fill_party_fields(self):
        d = self.draft
        for key, e in self.buyer_edits.items():
            e.setText(str(d.party.get(key) or ""))
        self.contact_combo.blockSignals(True)
        self.contact_combo.clear()
        self.contact_combo.addItem("— بدون مخاطب —", None)
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("بدون پروژه (عمومی)", None)
        if d.party.get("id"):
            with self.S() as s:
                p = s.get(Party, d.party["id"])
                for c in p.contacts:
                    if not c.is_archived:
                        self.contact_combo.addItem(letters.contact_full(
                            {"title_prefix": c.title_prefix, "honorific": c.honorific, "name": c.name})
                            + (f" – {c.position}" if c.position else ""), c.id)
                for pr in s.scalars(select(Project).where(Project.party_id == p.id, Project.is_archived.is_(False),
                                                          Project.status.not_in(["closed", "cancelled"]))
                                    .order_by(Project.id.desc())):
                    self.project_combo.addItem(pr.title, pr.id)
        self.project_combo.addItem("+ پروژه‌ی جدید…", NEW_PROJECT)
        ci = self.contact_combo.findData((d.contact or {}).get("id"))
        self.contact_combo.setCurrentIndex(max(ci, 0))
        pi = self.project_combo.findData((d.project or {}).get("id"))
        self.project_combo.setCurrentIndex(max(pi, 0))
        self.contact_combo.blockSignals(False)
        self.project_combo.blockSignals(False)
        self.new_project.setVisible(False)

    def _on_party(self, pid):
        if self._loading or self.draft is None:
            return
        with self.S() as s:
            docs.apply_party(s, self.draft, pid)
            self.draft.project = None
            # learned defaults for this customer
            if pid:
                learned = docs.default_clauses(s, self.draft.kind, self.draft.issuer["code"], pid)
                have = {c.code for c in self.draft.clauses}
                if self.draft.kind != "letter":
                    self.draft.clauses += [c for c in learned if c.code not in have]
        self.party_override = None
        self._fill_party_fields()
        self._rebuild_addressee()
        self._update_summary()

    def _on_contact(self):
        if self._loading or self.draft is None:
            return
        cid = self.contact_combo.currentData()
        with self.S() as s:
            from app.services.convert import contact_dict
            self.draft.contact = contact_dict(s.get(Contact, cid)) if cid else None
        self._rebuild_addressee()

    def _on_project(self):
        if self._loading or self.draft is None:
            return
        pid = self.project_combo.currentData()
        self.new_project.setVisible(pid == NEW_PROJECT)
        if pid == NEW_PROJECT:
            self.new_project.setFocus()
            return
        with self.S() as s:
            self.draft.project = project_dict(s.get(Project, pid)) if pid else None
        self._update_summary()

    def _on_date(self):
        if self.draft:
            self.draft.date = self.date_edit.date()
            self._refresh_number_hint()

    def _refresh_number_hint(self):
        if not self.draft:
            return
        with self.S() as s:
            suggested = docs.suggest_number(s, self.draft)
        self.number_edit.setPlaceholderText(suggested)
        self.number_hint.setText(f"شماره‌ی پیشنهادی {suggested}؛ هنگام صدور رزرو می‌شود. خالی بگذارید تا خودکار باشد.")

    def _rebuild_addressee(self):
        if self.draft is None or self.draft.kind != "letter" or self.addr_manual.isChecked():
            return
        fmt = self.addr_format.currentData() or self.addr_formats[0]
        party = dict(self.draft.party)
        self.addr_text.setPlainText("\n".join(letters.build_addressee(fmt, party, self.draft.contact)))

    def _new_party(self):
        from app.ui.forms import PartyForm
        with self.S() as s:
            dlg = PartyForm(s, None, self)
            if dlg.exec():
                p = dlg.save()
                pid = p.id
                self.party_combo.set_items(self._party_items(s), keep=False)
            else:
                return
        self.party_combo.set_current_id(pid)

    def _edit_party(self):
        pid = self.party_combo.current_id()
        if not pid:
            return
        from app.ui.forms import PartyForm
        with self.S() as s:
            dlg = PartyForm(s, s.get(Party, pid), self)
            if dlg.exec():
                dlg.save()
        self._on_party(pid)

    def _collect_party(self):
        d = self.draft
        if d is None:
            return
        d.date = self.date_edit.date() or d.date
        d.number = self.number_edit.text().strip()
        edited = {k: e.text().strip() for k, e in self.buyer_edits.items()}
        if d.party.get("id"):
            changed = {k: v for k, v in edited.items() if (d.party.get(k) or "") != v}
            if changed:
                if self.save_to_book.isChecked():
                    with self.S() as s:
                        p = s.get(Party, d.party["id"])
                        for k, v in changed.items():
                            setattr(p, k, v)
                        s.commit()
                    self.party_override = None
                else:
                    self.party_override = changed
                d.party.update(changed)
        if self.project_combo.currentData() == NEW_PROJECT and self.new_project.text().strip() and d.party.get("id"):
            with self.S() as s:
                pr = Project(party_id=d.party["id"], title=self.new_project.text().strip(),
                             retention_percent=Decimal(str(get_setting(s, "retention_percent_default", 10))),
                             retention_months=int(get_setting(s, "retention_months_default", 3)))
                s.add(pr)
                s.commit()
                d.project = project_dict(pr)
                pid = pr.id
            self._loading = True
            self.project_combo.insertItem(1, pr.title, pid)
            self.project_combo.setCurrentIndex(1)
            self.new_project.hide()
            self.new_project.clear()
            self._loading = False
        if d.kind == "letter":
            d.addressee_format = self.addr_format.currentIndex()
            d.addressee_lines = ([l for l in self.addr_text.toPlainText().splitlines() if l.strip()]
                                 if self.addr_manual.isChecked() else None)

    # ================================================================ step 4: content
    def _build_content(self):
        self.content_stack = QStackedWidget()
        # --- money documents
        mw = QWidget()
        ml = QVBoxLayout(mw)
        tr = QHBoxLayout()
        self.title_edit = QComboBox()
        self.title_edit.setEditable(True)
        tr.addWidget(QLabel("عنوان سند:"))
        tr.addWidget(self.title_edit, 1)
        ml.addLayout(tr)
        self.lines_money = LinesEditor("money")
        self.lines_money.changed.connect(self._on_lines)
        ml.addWidget(self.lines_money, 1)
        vr = QHBoxLayout()
        self.vat_check = QCheckBox("ارزش افزوده")
        self.vat_check.toggled.connect(lambda _: self._on_vat())
        self.vat_spin = QDoubleSpinBox(decimals=2, maximum=100)
        self.vat_spin.setSuffix(" ٪")
        self.vat_spin.valueChanged.connect(lambda _: self._on_vat())
        vr.addWidget(self.vat_check)
        vr.addWidget(self.vat_spin)
        vr.addStretch(1)
        ml.addLayout(vr)
        self.totals_label = QLabel(styleSheet="font-size:12pt; background:#f3f7ff; padding:8px; border-radius:6px")
        self.totals_label.setWordWrap(True)
        ml.addWidget(self.totals_label)
        self.content_stack.addWidget(mw)

        # --- letters
        lw = QWidget()
        ll = QVBoxLayout(lw)
        top = QFormLayout()
        self.letter_type_combo = SearchCombo(placeholder="موضوع نامه را جست‌وجو کنید (مثلاً «سپرده» یا «اخطار»)…")
        self.letter_type_combo.idChanged.connect(self._on_letter_type)
        top.addRow("موضوع:", self.letter_type_combo)
        self.fields_box = QGroupBox("اطلاعات نامه")
        self.fields_form = QFormLayout(self.fields_box)
        self.field_widgets = {}
        ll.addLayout(top)
        ll.addWidget(self.fields_box)
        self.letter_lines = LinesEditor("letter")
        self.letter_lines.changed.connect(self._on_lines)
        ll.addWidget(self.letter_lines)
        opts = QFormLayout()
        self.subject_form = opts
        self.free_subject = QLineEdit(placeholderText="موضوع (برای نامه‌ی بدون موضوع آماده)")
        self.free_subject.textEdited.connect(lambda _: self._letter_changed())
        opts.addRow("خط موضوع:", self.free_subject)
        self.salutation = QComboBox(editable=True)
        self.salutation.addItems(self.salutations)
        self.salutation.currentTextChanged.connect(lambda _: self._letter_changed())
        self.closing = QComboBox(editable=True)
        self.closing.addItems(self.closings)
        self.closing.currentTextChanged.connect(lambda _: self._letter_changed())
        self.header_line = QComboBox(editable=True)
        self.header_line.addItems(self.header_lines)
        self.attach_text = QLineEdit()
        row = QHBoxLayout()
        for lbl, wdg in (("سلام:", self.salutation), ("پایان:", self.closing), ("سرنامه:", self.header_line),
                         ("پیوست:", self.attach_text)):
            row.addWidget(QLabel(lbl))
            row.addWidget(wdg, 1)
        opts.addRow(row)
        ll.addLayout(opts)
        hb = QHBoxLayout()
        hb.addWidget(QLabel("<b>متن نامه</b>"))
        self.manual_tag = QLabel(" متن دستی ", styleSheet="background:#ffca28; border-radius:4px")
        self.manual_tag.hide()
        self.edit_text_btn = QPushButton("ویرایش متن")
        self.edit_text_btn.setCheckable(True)
        self.edit_text_btn.toggled.connect(self._toggle_manual)
        hb.addWidget(self.manual_tag)
        hb.addStretch(1)
        hb.addWidget(self.edit_text_btn)
        ll.addLayout(hb)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setReadOnly(True)
        self.body_edit.setMinimumHeight(200)
        self.body_edit.textChanged.connect(self._on_body_typed)
        ll.addWidget(self.body_edit, 1)
        self.content_stack.addWidget(lw)

        # --- attachment list
        aw = QWidget()
        al = QVBoxLayout(aw)
        af = QFormLayout()
        self.list_title = QLineEdit()
        self.list_subtitle = QLineEdit()
        af.addRow("عنوان لیست:", self.list_title)
        af.addRow("زیرعنوان:", self.list_subtitle)
        al.addLayout(af)
        self.list_lines = LinesEditor("list")
        self.list_lines.changed.connect(self._on_lines)
        al.addWidget(self.list_lines, 1)
        self.content_stack.addWidget(aw)
        return self.content_stack

    def _catalog(self, s):
        items = s.scalars(select(Item).where(Item.is_archived.is_(False)).order_by(Item.code)).all()
        units = [u.name for u in s.scalars(select(Unit).where(Unit.is_archived.is_(False)).order_by(Unit.sort_order))]
        return [(i.id, i.description, i.unit, i.last_unit_price or 0, i.category, i.buyer_supplied_by_default,
                 i.last_purchase_price) for i in items], units

    def _load_content(self):
        d = self.draft
        self._loading = True
        with self.S() as s:
            catalog, units = self._catalog(s)
            for ed in (self.lines_money, self.letter_lines, self.list_lines):
                ed.set_catalog(catalog, units)
                ed.markup_step = self.markup_step
            if d.kind == "letter":
                lts = s.scalars(select(LetterType).where(LetterType.is_archived.is_(False))
                                .order_by(LetterType.category, LetterType.id)).all()
                self.letter_type_combo.set_items([(f"{t.category} – {t.title}", t.id) for t in lts], keep=False)
        if d.is_money_doc:
            self.content_stack.setCurrentIndex(0)
            self.title_edit.clear()
            self.title_edit.addItems(list(dict.fromkeys([d.title or TITLE_BY_KIND[d.kind], TITLE_BY_KIND[d.kind],
                                                         "پیش‌فاکتور", "فاکتور", "صورت وضعیت"])))
            self.title_edit.setCurrentText(d.title or TITLE_BY_KIND[d.kind])
            self.lines_money.set_unit(d.input_currency)
            self.lines_money.set_lines(d.lines)
            self.vat_check.setChecked(d.vat_enabled)
            self.vat_spin.setValue(float(d.vat_percent))
        elif d.kind == "letter":
            self.content_stack.setCurrentIndex(1)
            self.letter_type_combo.set_current_id((d.letter_type or {}).get("id"))
            self._build_field_widgets()
            self.salutation.setCurrentText(d.salutation)
            self.closing.setCurrentText(d.closing)
            self.header_line.setCurrentText(d.header_line)
            self.header_line.setEnabled(d.issuer.get("kind") == "personal")
            self.attach_text.setText(d.attachment_text)
            self.free_subject.setText(d.subject)
            self.letter_lines.set_unit(d.input_currency)
            self.letter_lines.set_lines(d.lines)
            self.edit_text_btn.setChecked(d.body_override is not None)
        else:
            self.content_stack.setCurrentIndex(2)
            self.list_title.setText(d.list_title or f"لیست اقلام {(d.project or {}).get('title', '')}".strip())
            self.list_subtitle.setText(d.list_subtitle)
            self.list_lines.set_lines(d.lines)
        self._loading = False
        self._refresh_letter()
        self._refresh_totals()

    def _on_lines(self):
        if self._loading or not self.draft:
            return
        ed = {0: self.lines_money, 1: self.letter_lines, 2: self.list_lines}[self.content_stack.currentIndex()]
        self.draft.lines = ed.lines()
        self.draft.input_currency = ed.input_unit()
        self._refresh_totals()
        self._refresh_letter()

    def _on_vat(self):
        if self._loading or not self.draft:
            return
        self.draft.vat_enabled = self.vat_check.isChecked()
        self.draft.vat_percent = Decimal(str(self.vat_spin.value()))
        self.vat_spin.setEnabled(self.draft.vat_enabled)
        self._refresh_totals()

    def _refresh_totals(self):
        d = self.draft
        if not d:
            return
        t = d.totals
        if d.vat_enabled:
            txt = (f"جمع: <b>{money.fmt_int(t.subtotal)}</b> ریال &nbsp;|&nbsp; ارزش افزوده {money.fmt_percent(t.vat_percent)}٪: "
                   f"<b>{money.fmt_int(t.vat)}</b> &nbsp;|&nbsp; قابل پرداخت: <b>{money.fmt_int(t.payable)}</b> ریال<br>"
                   f"{rial_words(t.payable)}")
        else:
            txt = f"جمع کل: <b>{money.fmt_int(t.payable)}</b> ریال<br>{rial_words(t.payable)}"
        self.totals_label.setText(txt)
        self._update_summary()

    # --- letter fields
    def _on_letter_type(self, ltid):
        if self._loading or not self.draft:
            return
        with self.S() as s:
            docs.apply_letter_type(s, self.draft, ltid)
            if self.draft.letter_type and self.draft.letter_type.get("with_account") and \
                    not any(c.code == "PAY_TO_ACCOUNT" for c in self.draft.clauses):
                c = s.scalar(select(Clause).where(Clause.code == "PAY_TO_ACCOUNT"))
                if c:
                    self.draft.clauses.append(clause_sel(c))
        self.draft.body_override = None
        self._loading = True
        self.edit_text_btn.setChecked(False)
        self.closing.setCurrentText(self.draft.closing)
        self._loading = False
        self._build_field_widgets()
        self._refresh_letter()

    def _build_field_widgets(self):
        while self.fields_form.rowCount():
            self.fields_form.removeRow(0)
        self.field_widgets = {}
        lt = self.draft.letter_type or {}
        self.letter_lines.setVisible(bool(lt.get("with_items_table")))
        self.subject_form.setRowVisible(self.free_subject, not lt)
        self.fields_box.setVisible(bool(lt.get("fields")))
        with self.S() as s:
            party_names = [p.name for p in s.scalars(select(Party).where(Party.is_archived.is_(False)).order_by(Party.name))]
        for f in lt.get("fields", []):
            name, t = f["name"], f.get("type", "text")
            val = self.draft.fields.get(name, "")
            label = f.get("label", name) + (" *" if f.get("required") else "")
            if t == "money":
                w = MoneyEdit("rial")
                w.setValue(int(val) if str(val).isdigit() else 0, "rial")
                w.valueChanged.connect(lambda v, n=name: self._set_field(n, str(v) if v else ""))
            elif t == "date":
                w = JalaliDateEdit(jalali.parse(val) if val else None, allow_empty=True)
                w.dateChanged.connect(lambda dd, n=name: self._set_field(n, jalali.fmt(dd) if dd else ""))
            elif t == "longtext":
                w = QPlainTextEdit(str(val))
                w.setFixedHeight(110)
                w.textChanged.connect(lambda n=name, ww=w: self._set_field(n, ww.toPlainText()))
            elif t in ("choice", "party"):
                w = QComboBox()
                w.setEditable(True)
                w.addItems(party_names if t == "party" else _choice_options(f, self.settings_refs))
                w.setCurrentText(str(val))
                if not val and w.count():
                    self.draft.fields[name] = w.currentText()
                w.currentTextChanged.connect(lambda v, n=name: self._set_field(n, v))
            else:
                w = QLineEdit(str(val))
                if t in ("int", "percent"):
                    w.setMaximumWidth(120)
                w.textEdited.connect(lambda v, n=name: self._set_field(n, v.strip()))
            self.fields_form.addRow(label + ":", w)
            self.field_widgets[name] = w

    def _set_field(self, name, value):
        if self.draft is None:
            return
        from app.core.normalize import normalize_text
        self.draft.fields[name] = normalize_text(value) if isinstance(value, str) else value
        self._refresh_letter()

    def _letter_changed(self):
        if self._loading or not self.draft or self.draft.kind != "letter":
            return
        self.draft.salutation = self.salutation.currentText()
        self.draft.closing = self.closing.currentText()
        self.draft.subject = self.free_subject.text()
        self._refresh_letter()

    def _toggle_manual(self, on):
        if not self.draft:
            return
        self.body_edit.setReadOnly(not on)
        self.manual_tag.setVisible(on)
        if on:
            if self.draft.body_override is None:
                self.draft.body_override = letters.build_body(self.draft)
        else:
            if not self._loading and self.draft.body_override is not None:
                if not confirm(self, "متن دستی کنار گذاشته شود و متن دوباره از روی فیلدها ساخته شود؟"):
                    self.edit_text_btn.blockSignals(True)
                    self.edit_text_btn.setChecked(True)
                    self.edit_text_btn.blockSignals(False)
                    self.body_edit.setReadOnly(False)
                    self.manual_tag.show()
                    return
            self.draft.body_override = None
        self._refresh_letter()

    def _on_body_typed(self):
        if self._loading or not self.draft or self.body_edit.isReadOnly():
            return
        self.draft.body_override = [p.strip() for p in self.body_edit.toPlainText().split("\n") if p.strip()]
        self._update_summary()

    def _refresh_letter(self):
        d = self.draft
        if not d or d.kind != "letter":
            return
        self._loading = True
        try:
            if d.body_override is not None:
                if self.body_edit.isReadOnly():
                    self.body_edit.setPlainText("\n".join(d.body_override))
            else:
                self.body_edit.setPlainText("\n".join(letters.build_body(d)))
        finally:
            self._loading = False
        self._update_summary()

    def _collect_content(self):
        d = self.draft
        if not d:
            return
        if d.is_money_doc:
            d.title = self.title_edit.currentText().strip() or TITLE_BY_KIND[d.kind]
            d.lines = self.lines_money.lines()
            d.input_currency = self.lines_money.input_unit()
            d.vat_enabled = self.vat_check.isChecked()
            d.vat_percent = Decimal(str(self.vat_spin.value()))
        elif d.kind == "letter":
            d.salutation = self.salutation.currentText()
            d.closing = self.closing.currentText()
            d.header_line = self.header_line.currentText()
            d.attachment_text = self.attach_text.text()
            d.subject = self.free_subject.text() if not d.letter_type else d.subject
            if (d.letter_type or {}).get("with_items_table"):
                d.lines = self.letter_lines.lines()
                d.input_currency = self.letter_lines.input_unit()
            if not self.body_edit.isReadOnly():
                d.body_override = [p.strip() for p in self.body_edit.toPlainText().split("\n") if p.strip()]
        else:
            d.list_title = self.list_title.text().strip()
            d.list_subtitle = self.list_subtitle.text().strip()
            d.lines = self.list_lines.lines()

    # ================================================================ step 5: clauses & accounts
    def _build_clauses(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.clauses_note = QLabel(styleSheet="color:#666")
        lay.addWidget(self.clauses_note)
        self.picker = ClausePicker()
        self.picker.changed.connect(self._update_summary)
        self.picker.changed.connect(self._refresh_letter)
        lay.addWidget(self.picker, 1)
        lay.addWidget(QLabel("<b>حساب‌ها</b> (حساب اول در بند «واریز به شبا» می‌آید)"))
        self.acc_list = QListWidget()
        self.acc_list.setMaximumHeight(130)
        self.acc_list.itemChanged.connect(lambda _: self._on_accounts())
        self.acc_checks = {}
        lay.addWidget(self.acc_list)
        opts = QHBoxLayout()
        self.stamp_check = QCheckBox("مهر")
        self.sign_check = QCheckBox("امضا")
        self.tax_serial = QLineEdit(placeholderText="شماره‌ی منحصربه‌فرد مالیاتی (اختیاری)")
        self.tax_serial.setMaximumWidth(320)
        for wdg in (self.stamp_check, self.sign_check, self.tax_serial):
            opts.addWidget(wdg)
        opts.addStretch(1)
        lay.addLayout(opts)
        return w

    def _load_clauses(self):
        d = self.draft
        with self.S() as s:
            avail = [clause_sel(c) for c in docs.available_clauses(s, d.kind)]
            rank = {c.code: c.usage_count or 0 for c in s.scalars(select(Clause))}
            accounts = s.scalars(select(Account).where(Account.is_archived.is_(False), Account.active.is_(True))
                                 .order_by(Account.id)).all()
            acc_rows = [(a.id, f"{a.bank} – {a.holder} – {a.iban}", account_info(a)) for a in accounts]
        lt = d.letter_type or {}
        if d.kind == "letter":
            if lt.get("with_clauses"):
                self.clauses_note.setText("بندهای انتخاب‌شده در انتهای متن نامه می‌آیند.")
            else:
                avail = [c for c in avail if c.code == "PAY_TO_ACCOUNT"]
                self.clauses_note.setText("این موضوع نامه بند انتخابی ندارد؛ فقط حساب، مهر و امضا را تعیین کنید.")
        else:
            self.clauses_note.setText("بندهای پیش‌فرض این سربرگ و این مشتری از قبل تیک خورده‌اند.")
        self.picker.load(d, avail, rank)
        self.acc_list.blockSignals(True)
        self.acc_list.clear()
        self.acc_checks = {}
        selected = [a.id for a in d.accounts]
        for aid, label, ainfo in acc_rows:
            it = QListWidgetItem(label)
            it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            it.setCheckState(Qt.Checked if aid in selected else Qt.Unchecked)
            self.acc_list.addItem(it)
            self.acc_checks[aid] = (it, ainfo)
        self.acc_list.blockSignals(False)
        self.stamp_check.setChecked(d.show_stamp)
        self.sign_check.setChecked(d.show_signature)
        self.stamp_check.setVisible(d.issuer.get("kind") == "company")
        self.tax_serial.setVisible(d.issuer.get("kind") == "company" and d.kind != "letter")
        self.tax_serial.setText(d.tax_serial)

    def _on_accounts(self):
        d = self.draft
        current = [a.id for a in d.accounts]
        chosen = [aid for aid, (it, _) in self.acc_checks.items() if it.checkState() == Qt.Checked]
        order = [a for a in current if a in chosen] + [a for a in chosen if a not in current]
        d.accounts = [self.acc_checks[a][1] for a in order]
        self.picker.refresh()
        self._refresh_letter()
        self._update_summary()

    def _collect_clauses(self):
        d = self.draft
        if not d:
            return
        d.clauses = list(self.picker.order)
        d.show_stamp = self.stamp_check.isChecked()
        d.show_signature = self.sign_check.isChecked()
        d.tax_serial = self.tax_serial.text().strip()
        if self.picker.add_to_library:
            with self.S() as s:
                from sqlalchemy import func
                for sel in self.picker.add_to_library:
                    n = (s.scalar(select(func.count(Clause.id))) or 0) + 1
                    c = Clause(code=f"USER_{n:03d}", group=sel.group, text=sel.template,
                               applies_to=["proforma", "invoice"] if d.kind != "letter" else ["letter"],
                               sort_order=(s.scalar(select(func.max(Clause.sort_order))) or 0) + 1)
                    while s.scalar(select(Clause.id).where(Clause.code == c.code)):
                        n += 1
                        c.code = f"USER_{n:03d}"
                    s.add(c)
                    s.flush()
                    sel.code, sel.clause_id = c.code, c.id
                s.commit()
            self.picker.add_to_library = []

    # ================================================================ step 6: attachments & output
    def _build_output(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("صفحات PDF کامل (ترتیب با کشیدن)")
        bl = QVBoxLayout(box)
        self.att_list = QListWidget()
        self.att_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.att_list.model().rowsMoved.connect(lambda *_: self._attachments_from_list())
        self.att_list.setMaximumHeight(170)
        bl.addWidget(self.att_list)
        ab = QHBoxLayout()
        b1 = QPushButton("+ لیست اقلام از همین سند")
        b1.clicked.connect(self._add_items_list)
        b2 = QPushButton("+ نقشه / PDF / تصویر…")
        b2.clicked.connect(self._add_file)
        self.erase_btn = QPushButton("پاک کردن ناحیه…")
        self.erase_btn.clicked.connect(self._erase)
        b4 = QPushButton("حذف از فهرست")
        b4.clicked.connect(self._remove_attachment)
        for b in (b1, b2, self.erase_btn, b4):
            ab.addWidget(b)
        ab.addStretch(1)
        bl.addLayout(ab)
        lay.addWidget(box)
        self.output_issues = IssuesBox()
        lay.addWidget(self.output_issues)
        btns = QHBoxLayout()
        self.word_btn = QPushButton("ساخت فایل Word")
        self.word_btn.setObjectName("primary")
        self.word_btn.setMinimumHeight(52)
        self.word_btn.clicked.connect(self._make_word)
        self.pdf_btn = QPushButton("ساخت PDF کامل")
        self.pdf_btn.setMinimumHeight(52)
        self.pdf_btn.clicked.connect(self._make_pdf)
        self.folder_btn = QPushButton("باز کردن پوشه")
        self.folder_btn.setMinimumHeight(52)
        self.folder_btn.clicked.connect(self._open_folder)
        for b in (self.word_btn, self.pdf_btn, self.folder_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        self.result_label = QLabel(wordWrap=True)
        self.result_label.setTextFormat(Qt.RichText)
        self.result_label.setOpenExternalLinks(False)
        self.result_label.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl.fromLocalFile(url)))
        lay.addWidget(self.result_label)
        lay.addStretch(1)
        return w

    def _att_label(self, a):
        t = a.get("type")
        if t == "document":
            return "📄 خود سند"
        if t == "items_list":
            return f"📋 {a.get('title') or 'لیست اقلام'}"
        er = " (ناحیه پاک می‌شود)" if a.get("erase") else ""
        return f"📎 {a.get('name') or Path(a.get('path', '')).name}{er}"

    def _load_output(self):
        if not any(a.get("type") == "document" for a in self.attachments):
            self.attachments.insert(0, {"type": "document"})
        self.att_list.clear()
        for i, a in enumerate(self.attachments):
            it = QListWidgetItem(self._att_label(a))
            it.setData(Qt.UserRole, i)
            self.att_list.addItem(it)
        self._attachments_snapshot = list(self.attachments)
        self._refresh_issues()
        self._update_output_buttons()

    def _attachments_from_list(self):
        snap = self._attachments_snapshot
        self.attachments = [snap[self.att_list.item(i).data(Qt.UserRole)] for i in range(self.att_list.count())]
        self._load_output()

    def _add_items_list(self):
        if not self.draft.lines:
            warn(self, "جدول اقلام خالی است.")
            return
        title = self.draft.list_title or f"لیست اقلام {(self.draft.project or {}).get('title', '')}".strip()
        self.attachments.append({"type": "items_list", "title": title, "subtitle": self.draft.list_subtitle})
        self._load_output()

    def _add_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "انتخاب نقشه یا پیوست", "",
                                           "PDF یا تصویر (*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.bmp)")
        if not f:
            return
        self.save()
        src = Path(f)
        if src.suffix.lower() != ".pdf":
            from app.core import pdf_tools
            from app.core.files import versioned_path
            dest, _ = versioned_path(docs.attachments_dir(self.doc_id), src.stem, ".pdf")
            stored = pdf_tools.image_to_pdf(src, dest)   # images become one A4 page (18pt margin)
        else:
            stored = docs.store_attachment(self.doc_id, src)
        self.attachments.append({"type": "file", "path": str(stored), "name": src.name, "erase": {}})
        self._load_output()

    def _erase(self):
        it = self.att_list.currentItem()
        if not it:
            return
        a = self.attachments[it.data(Qt.UserRole)]
        if a.get("type") != "file":
            info(self, "این ابزار برای پیوست‌های PDF یا تصویر است.")
            return
        dlg = EraseDialog(a["path"], a.get("erase"), self)
        if dlg.exec():
            a["erase"] = dlg.result_regions()
            self._load_output()

    def _remove_attachment(self):
        it = self.att_list.currentItem()
        if not it:
            return
        a = self.attachments[it.data(Qt.UserRole)]
        if a.get("type") == "document":
            return
        self.attachments.remove(a)
        self._load_output()

    def _refresh_issues(self):
        issues = self.issues()
        self.output_issues.set_issues(issues)
        return issues

    def _update_output_buttons(self):
        self.word_btn.setEnabled(not self.issued)
        self.pdf_btn.setEnabled(self.issued)
        self.folder_btn.setEnabled(self.issued)

    def _make_word(self):
        self.collect()
        issues = self._refresh_issues()
        if any(i.blocking for i in issues):
            warn(self, "پیش از ساخت فایل، خطاهای قرمز را برطرف کنید.")
            return
        self.save()
        with self.S() as s:
            try:
                r = docs.issue(s, self.doc_id)
            except docs.IssueBlocked as e:
                self.output_issues.set_issues(e.issues)
                return
            except Exception as e:  # a template or disk problem: tell plainly
                warn(self, f"فایل ساخته نشد:\n{e}")
                return
        self.issued = True
        self.draft.number = r.number
        self.result_label.setText(f"✓ سند با شماره‌ی <b>{r.number}</b> صادر شد.<br>"
                                  f"<a href='{r.docx}'>{r.docx.name}</a> در پوشه‌ی {r.docx.parent}")
        self.output_issues.set_issues(r.warnings)
        self._update_output_buttons()
        self._lock()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(r.docx)))
        self._update_summary()

    def _make_pdf(self):
        doc_id = self.doc_id
        S = self.S
        self.save_attachments_only()

        def job():
            with S() as s:
                return docs.make_full_pdf(s, doc_id)

        def done(path, error):
            if error:
                from app.core.pdf_tools import PdfUnavailable
                if isinstance(error[0], PdfUnavailable):
                    warn(self, "PDF ساخته نشد: Word یا LibreOffice پیدا نشد.\n"
                               "برای PDF، فایل را در Word باز کنید و Save as PDF بزنید.")
                else:
                    warn(self, f"PDF ساخته نشد:\n{error[0]}")
                return
            self.result_label.setText(self.result_label.text() + f"<br>✓ PDF کامل: <a href='{path}'>{Path(path).name}</a>")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

        run_busy(self, "در حال ساخت PDF با Word…", job, done)

    def _open_folder(self):
        with self.S() as s:
            folder = docs.doc_folder(s, s.get(Document, self.doc_id))
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _lock(self):
        for i in range(0, 5):
            self.pages.widget(i).setEnabled(False)
        self.save_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.setWindowTitle(self.windowTitle() + " – صادر شد")

    # ================================================================ navigation
    def collect(self):
        if self.draft is None or self.issued:
            return
        if self.current == 2:
            self._collect_party()
        elif self.current == 3:
            self._collect_content()
        elif self.current == 4:
            self._collect_clauses()

    def go(self, i: int):
        if i < 0 or i >= len(STEPS):
            return
        if i >= 2 and (not self.kind or not self.issuer_id):
            warn(self, "اول نوع سند و سربرگ را انتخاب کنید.")
            return
        self.collect()
        if i >= 2:
            self._ensure_draft()
            if not self.issued:
                self.save()
        self._enter(i)

    def _enter(self, i: int):
        self.current = i
        if i == 0:
            self._fill_copy_sources()
            for k, c in self.kind_cards.items():
                c.setChecked(k == self.kind)
        elif i == 1:
            for k, c in self.issuer_cards.items():
                c.setChecked(k == self.issuer_id)
        elif i == 2:
            self._load_party_step()
        elif i == 3:
            self._load_content()
        elif i == 4:
            if self.draft.kind == "attachment_list":
                self._enter(5)
                return
            self._load_clauses()
        elif i == 5:
            self._load_output()
        self.pages.setCurrentIndex(i)
        for k, b in enumerate(self.step_buttons):
            b.setChecked(k == i)
            b.setEnabled(k <= 1 or self.draft is not None)
        self.prev_btn.setEnabled(i > 0 and not self.issued)
        self.next_btn.setVisible(i < 5)
        self._update_summary()

    # ================================================================ persistence
    def save(self):
        if self.draft is None or self.issued:
            return
        with self.S() as s:
            doc = docs.save_draft(s, self.draft, self.doc_id, attachments=self.attachments,
                                  party_override=self.party_override)
            s.commit()
            self.doc_id = doc.id

    def save_attachments_only(self):
        with self.S() as s:
            doc = s.get(Document, self.doc_id)
            doc.attachments = self.attachments
            s.commit()

    def _load_existing(self, doc_id):
        with self.S() as s:
            doc = s.get(Document, doc_id)
            self.doc_id = doc.id
            self.kind, self.issuer_id = doc.kind, doc.issuer_id
            self.draft = docs.draft_from_document(s, doc)
            self.attachments = list(doc.attachments or [{"type": "document"}])
            ov = (doc.fields_json or {}).get("_party_override")
            self.party_override = ov or None
            self.issued = doc.status != "draft"
        self.setWindowTitle(f"{KIND_FA[self.kind]} – {self.draft.issuer.get('title', '')}")
        if self.issued:
            self._enter(5)
            self.result_label.setText("این سند صادر شده است. برای تغییر از صفحه‌ی سند «نسخه‌ی جدید» بزنید.")
            self._lock()
            self._update_output_buttons()
        else:
            self._enter(2)

    def issues(self) -> list[Issue]:
        if not self.draft:
            return []
        with self.S() as s:
            try:
                return docs.check_draft(s, self.draft)
            except Exception as e:
                return [Issue("error", str(e))]

    def _update_summary(self):
        d = self.draft
        if not d:
            self.summary.setText("نوع سند و سربرگ را انتخاب کنید.")
            self.summary_issues.set_issues([])
            return
        parts = [f"<b>{KIND_FA[d.kind]}</b> – {d.issuer.get('title', '')}"]
        if d.party:
            parts.append(f"مشتری: {d.party.get('name', '')}")
        if d.contact:
            parts.append(f"مخاطب: {letters.contact_full(d.contact)}")
        if d.project:
            parts.append(f"پروژه: {d.project.get('title', '')}")
        parts.append(f"تاریخ: {jalali.fmt(d.date)} &nbsp; شماره: {d.number or self.number_edit.placeholderText() or '—'}")
        if d.kind == "letter" and d.letter_type:
            parts.append(f"موضوع: {letters.build_subject(d)}")
        if d.is_money_doc or (d.kind == "letter" and d.lines):
            t = d.totals
            parts.append(f"ردیف‌ها: {len(d.lines)}<br><b>{'قابل پرداخت' if t.vat_enabled else 'جمع کل'}: "
                         f"{money.fmt_int(t.payable)} ریال</b><br><small>{rial_words(t.payable)}</small>")
        if d.kind != "attachment_list":
            parts.append(f"بندها: {len(d.clauses)} &nbsp; حساب: {', '.join(a.bank for a in d.accounts) or '—'}")
        if d.kind == "letter" and d.body_override is not None:
            parts.append("<span style='background:#ffca28'>متن دستی</span>")
        self.summary.setText("<br>".join(parts))
        if self.current >= 3:
            self.summary_issues.set_issues(self.issues())
        else:
            self.summary_issues.set_issues([])

    def reject(self):
        """Close (X, Esc or «بستن»): the draft is saved, so nothing is lost and no question is needed."""
        if not self.issued and self.draft is not None:
            try:
                self.collect()
                self.save()
            except Exception:  # never block closing; the last autosave is still there
                import logging
                logging.getLogger(__name__).exception("saving draft on close failed")
        super().reject()
