"""پروژه‌ها: customer → project tree, project page, contract info, legacy archive files."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                               QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
from sqlalchemy import select

from app.core import jalali, money
from app.core.draft import KIND_FA, STATUS_FA
from app.db.models import ArchiveFile, Document, Party, Project, Task
from app.db.repo import get_setting
from app.services import documents as docs
from app.services import projects as proj
from app.ui.widgets import JalaliDateEdit, MoneyEdit, SearchCombo, SearchTable, confirm


class ProjectForm(QDialog):
    def __init__(self, s, project: Project | None, party_id: int | None = None, parent=None):
        super().__init__(parent)
        self.s, self.project = s, project
        self.setWindowTitle("پروژه")
        self.setMinimumWidth(560)
        p = project or Project(party_id=party_id or 0, title="",
                               retention_percent=Decimal(str(get_setting(s, "retention_percent_default", 10))),
                               retention_months=int(get_setting(s, "retention_months_default", 3)))
        f = QFormLayout(self)
        self.party = SearchCombo()
        self.party.set_items([(x.name, x.id) for x in s.scalars(select(Party).where(Party.is_archived.is_(False))
                                                                .order_by(Party.name))], keep=False)
        self.party.set_current_id(p.party_id)
        f.addRow("مشتری:", self.party)
        self.title = QLineEdit(p.title)
        f.addRow("عنوان پروژه:", self.title)
        self.status = QComboBox()
        for k, v in proj.PROJECT_STATUS_FA.items():
            self.status.addItem(v, k)
        self.status.setCurrentIndex(max(self.status.findData(p.status or "open"), 0))
        f.addRow("وضعیت:", self.status)
        self.contract_no = QLineEdit(p.contract_no)
        self.contract_no.setLayoutDirection(Qt.LeftToRight)
        f.addRow("شماره‌ی قرارداد:", self.contract_no)
        self.contract_date = JalaliDateEdit(p.contract_date, allow_empty=True)
        f.addRow("تاریخ قرارداد:", self.contract_date)
        self.amount = MoneyEdit("million_toman")
        self.amount.setValue(p.contract_amount or 0)
        f.addRow("مبلغ قرارداد:", self.amount)
        self.ret_pct = QDoubleSpinBox(decimals=2, maximum=100)
        self.ret_pct.setSuffix(" ٪")
        self.ret_pct.setValue(float(p.retention_percent or 0))
        self.ret_months = QSpinBox(maximum=60)
        self.ret_months.setSuffix(" ماه")
        self.ret_months.setValue(int(p.retention_months or 0))
        row = QHBoxLayout()
        row.addWidget(self.ret_pct)
        row.addWidget(self.ret_months)
        f.addRow("سپرده‌ی حسن انجام کار:", row)
        self.handover = JalaliDateEdit(p.handover_date, allow_empty=True)
        f.addRow("تاریخ تحویل موقت:", self.handover)
        f.addRow("", QLabel("با ثبت تاریخ تحویل موقت، کار «نامه‌ی آزادسازی سپرده» در تاریخ درست ساخته می‌شود.",
                            styleSheet="color:#666", wordWrap=True))
        self.supplier = QLineEdit(p.supplier_name)
        f.addRow("تأمین‌کننده (فقط داخلی):", self.supplier)
        self.supplier_notes = QPlainTextEdit(p.supplier_notes)
        self.supplier_notes.setFixedHeight(60)
        f.addRow("یادداشت داخلی:", self.supplier_notes)
        self.err = QLabel(styleSheet="color:#c62828")
        f.addRow(self.err)
        bb = QDialogButtonBox()
        bb.addButton("ذخیره", QDialogButtonBox.AcceptRole)
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self):
        if not self.party.current_id() or not self.title.text().strip():
            self.err.setText("مشتری و عنوان لازم است.")
            return
        self.accept()

    def save(self) -> Project:
        p = self.project or Project(party_id=0, title="")
        p.party_id = self.party.current_id()
        p.title = self.title.text().strip()
        p.status = self.status.currentData()
        p.contract_no = self.contract_no.text().strip()
        p.contract_date = self.contract_date.date()
        p.contract_amount = self.amount.value() or None
        p.retention_percent = Decimal(str(self.ret_pct.value()))
        p.retention_months = self.ret_months.value()
        p.handover_date = self.handover.date()
        if p.handover_date and p.status in ("open", "waiting_payment") and p.retention_percent > 0:
            p.status = "retention"
        p.supplier_name = self.supplier.text().strip()
        p.supplier_notes = self.supplier_notes.toPlainText().strip()
        return proj.save_project(self.s, p)


class ProjectsPage(QWidget):
    openDocument = Signal(int)
    newDocument = Signal(dict)
    changed = Signal()

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.S = SessionLocal
        lay = QVBoxLayout(self)
        t = QLabel("پروژه‌ها")
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        bar = QHBoxLayout()
        b = QPushButton("+ پروژه‌ی جدید")
        b.clicked.connect(lambda: self._edit(None))
        self.search = QLineEdit(placeholderText="جست‌وجوی مشتری یا پروژه…")
        self.search.textChanged.connect(lambda _: self.refresh())
        self.show_closed = QComboBox()
        self.show_closed.addItems(["پروژه‌های باز", "همه‌ی پروژه‌ها"])
        self.show_closed.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(b)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_closed)
        lay.addLayout(bar)
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["مشتری / پروژه", "وضعیت"])
        self.tree.setColumnWidth(0, 280)
        self.tree.currentItemChanged.connect(lambda *_: self._show_selected())
        split.addWidget(self.tree)
        self.detail = QWidget()
        self.dl = QVBoxLayout(self.detail)
        split.addWidget(self.detail)
        split.setSizes([360, 700])
        lay.addWidget(split, 1)
        self.refresh()

    def refresh(self):
        needle = self.search.text().strip()
        cur = self.tree.currentItem()
        cur_key = cur.data(0, Qt.UserRole) if cur else None
        self.tree.clear()
        with self.S() as s:
            parties = s.scalars(select(Party).where(Party.is_archived.is_(False)).order_by(Party.name)).all()
            q = select(Project).where(Project.is_archived.is_(False))
            if self.show_closed.currentIndex() == 0:
                q = q.where(Project.status.not_in(["closed", "cancelled"]))
            projects = s.scalars(q.order_by(Project.id.desc())).all()
            by_party = {}
            for p in projects:
                by_party.setdefault(p.party_id, []).append(p)
            has_docs = set(s.scalars(select(Document.party_id).where(Document.is_archived.is_(False))))
            has_archive = set(s.scalars(select(ArchiveFile.party_id)))
            for party in parties:
                prs = by_party.get(party.id, [])
                if not prs and party.id not in has_docs and party.id not in has_archive and not needle:
                    continue
                text = f"{party.short_name or party.name}"
                if needle and needle not in party.name and needle not in (party.short_name or "") and \
                        not any(needle in p.title for p in prs):
                    continue
                top = QTreeWidgetItem([text, ""])
                top.setData(0, Qt.UserRole, ("party", party.id))
                self.tree.addTopLevelItem(top)
                general = QTreeWidgetItem(["عمومی (بدون پروژه)", ""])
                general.setData(0, Qt.UserRole, ("general", party.id))
                top.addChild(general)
                for p in prs:
                    it = QTreeWidgetItem([p.title, proj.PROJECT_STATUS_FA.get(p.status, p.status)])
                    it.setData(0, Qt.UserRole, ("project", p.id))
                    top.addChild(it)
                top.setExpanded(bool(prs) or bool(needle))
                if cur_key and cur_key == ("party", party.id):
                    self.tree.setCurrentItem(top)
        if cur_key:
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                for j in range(top.childCount()):
                    if top.child(j).data(0, Qt.UserRole) == cur_key:
                        self.tree.setCurrentItem(top.child(j))

    def _clear_detail(self):
        while self.dl.count():
            item = self.dl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                lay = item.layout()
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()

    def _show_selected(self):
        it = self.tree.currentItem()
        self._clear_detail()
        if not it:
            return
        kind, ident = it.data(0, Qt.UserRole)
        with self.S() as s:
            if kind == "project":
                p = s.get(Project, ident)
                party_id = p.party_id
                head = (f"<h3>{p.title}</h3>{p.party.name}<br>وضعیت: {proj.PROJECT_STATUS_FA.get(p.status)}"
                        + (f"<br>قرارداد {p.contract_no}" if p.contract_no else "")
                        + (f" مورخ {jalali.fmt(p.contract_date)}" if p.contract_date else "")
                        + (f"<br>مبلغ قرارداد: {money.fmt_int(p.contract_amount)} ریال" if p.contract_amount else "")
                        + (f"<br>سپرده: {money.fmt_percent(p.retention_percent)}٪ به مدت {p.retention_months} ماه" if p.retention_percent else "")
                        + (f"<br>تحویل موقت: {jalali.fmt(p.handover_date)}" if p.handover_date else ""))
                sums = proj.project_sums(s, p.id)
                head += (f"<br><br>جمع پیش‌فاکتورها: {money.fmt_int(sums['proforma'])} &nbsp; "
                         f"جمع فاکتورها: {money.fmt_int(sums['invoice'])} &nbsp; پرداخت‌شده: {money.fmt_int(sums['paid'])} ریال")
                q = select(Document).where(Document.project_id == p.id)
                tq = select(Task).where(Task.project_id == p.id)
            else:
                party = s.get(Party, ident)
                party_id = party.id
                head = f"<h3>{party.name}</h3>" + (party.address or "") + (f"<br>{party.phone}" if party.phone else "")
                q = select(Document).where(Document.party_id == party.id)
                if kind == "general":
                    q = q.where(Document.project_id.is_(None))
                tq = select(Task).where(Task.party_id == party.id)
            lbl = QLabel(head)
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            self.dl.addWidget(lbl)
            bar = QHBoxLayout()
            nb = QPushButton("+ سند جدید در این " + ("پروژه" if kind == "project" else "پوشه"))
            nb.setObjectName("primary")
            preset = {"party_id": party_id, "project_id": ident if kind == "project" else None}
            nb.clicked.connect(lambda: self.newDocument.emit(preset))
            bar.addWidget(nb)
            if kind == "project":
                eb = QPushButton("ویرایش پروژه / تحویل موقت")
                eb.clicked.connect(lambda: self._edit(ident))
                bar.addWidget(eb)
            fb = QPushButton("باز کردن پوشه")
            fb.clicked.connect(lambda: self._open_folder(party_id, ident if kind == "project" else None))
            bar.addWidget(fb)
            bar.addStretch(1)
            self.dl.addLayout(bar)
            rows = s.scalars(q.where(Document.is_archived.is_(False)).order_by(Document.date_greg)).all()
            table = SearchTable(["تاریخ", "نوع", "شماره", "موضوع / عنوان", "مبلغ", "وضعیت"])
            table.set_rows([[d.date_jalali, KIND_FA[d.kind], d.number, d.subject or d.title,
                             money.fmt_int(d.payable) if d.payable else "", STATUS_FA.get(d.status)] for d in rows],
                           [d.id for d in rows])
            table.view.doubleClicked.connect(lambda _, t=table: self.openDocument.emit(t.selected_id()) if t.selected_id() else None)
            self.dl.addWidget(QLabel("<b>اسناد</b>"))
            self.dl.addWidget(table, 2)
            tasks = s.scalars(tq.where(Task.is_archived.is_(False)).order_by(Task.due_date)).all()
            if tasks:
                tl = QLabel("<b>کارها</b><br>" + "<br>".join(
                    f"{'✓' if t.status == 'done' else '○'} {t.title} – {jalali.fmt(t.due_date)}" for t in tasks))
                tl.setTextFormat(Qt.RichText)
                self.dl.addWidget(tl)
            arch = s.scalars(select(ArchiveFile).where(ArchiveFile.party_id == party_id)
                             .order_by(ArchiveFile.date_guess.desc(), ArchiveFile.title)).all() if kind != "project" else []
            if arch:
                self.dl.addWidget(QLabel("<b>بایگانی قدیمی</b> (فقط برای باز کردن؛ دوبار کلیک)"))
                at = SearchTable(["عنوان فایل", "نوع حدسی", "تاریخ حدسی", "مسیر"])
                at.set_rows([[a.title, KIND_FA.get(a.kind_guess, ""), a.date_guess, a.path] for a in arch],
                            [a.path for a in arch])
                at.view.doubleClicked.connect(lambda _, t=at: QDesktopServices.openUrl(QUrl.fromLocalFile(t.selected_id())))
                self.dl.addWidget(at, 2)

    def _edit(self, project_id):
        it = self.tree.currentItem()
        party_id = None
        if it and it.data(0, Qt.UserRole)[0] in ("party", "general"):
            party_id = it.data(0, Qt.UserRole)[1]
        with self.S() as s:
            dlg = ProjectForm(s, s.get(Project, project_id) if project_id else None, party_id, self)
            if dlg.exec():
                dlg.save()
        self.refresh()
        self._show_selected()
        self.changed.emit()

    def _open_folder(self, party_id, project_id):
        from app.core.files import document_folder
        from app.db.repo import output_root
        with self.S() as s:
            party = s.get(Party, party_id)
            pr = s.get(Project, project_id) if project_id else None
            folder = document_folder(output_root(s), party.short_name or party.name, pr.title if pr else None)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
