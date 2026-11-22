"""اسناد: all documents with filters, the document page, and the open-receivables report."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)
from sqlalchemy import select

from app.core import jalali, money
from app.core.draft import KIND_FA, STATUS_FA
from app.db.models import Document, Party, Task
from app.services import documents as docs
from app.services import projects as proj
from app.ui.widgets import SearchCombo, SearchTable, confirm, info, warn
from app.ui.worker import run_busy

STATUS_COLORS = {"draft": "#8a6d00", "void": "#999", "rejected": "#c62828", "paid": "#2e7d32"}
ROLE_FA = {"docx": "Word", "pdf": "PDF", "merged_pdf": "PDF کامل", "final": "نسخه‌ی نهایی ارسالی"}


class DocumentDialog(QDialog):
    """صفحه‌ی سند: summary, files and versions, status buttons, tasks and derived documents."""
    openWizard = Signal(int)

    def __init__(self, SessionLocal, doc_id: int, parent=None):
        super().__init__(parent)
        self.S, self.doc_id = SessionLocal, doc_id
        self.setWindowTitle("سند")
        self.resize(820, 640)
        self.lay = QVBoxLayout(self)
        self.reload()

    def reload(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        with self.S() as s:
            d = s.get(Document, self.doc_id)
            who = d.party.name if d.party else "—"
            head = QLabel(f"<h2>{KIND_FA[d.kind]} {d.number or '(پیش‌نویس)'}</h2>"
                          f"{who}{' – ' + d.project.title if d.project else ''}<br>"
                          f"تاریخ {d.date_jalali} &nbsp; وضعیت: <b>{STATUS_FA.get(d.status, d.status)}</b>"
                          + (f" &nbsp; نسخه {d.version}" if (d.version or 1) > 1 else ""))
            head.setTextFormat(Qt.RichText)
            self.lay.addWidget(head)
            info_form = QFormLayout()
            if d.subject:
                info_form.addRow("موضوع:", QLabel(d.subject, wordWrap=True))
            if d.payable:
                info_form.addRow("مبلغ:", QLabel(f"{money.fmt_int(d.payable)} ریال"))
            if d.parent_document_id:
                parent = s.get(Document, d.parent_document_id)
                info_form.addRow("ساخته‌شده از:", QLabel(f"{KIND_FA[parent.kind]} {parent.number}"))
            self.lay.addLayout(info_form)

            # files
            fbox = QGroupBox("فایل‌ها و نسخه‌ها")
            fl = QVBoxLayout(fbox)
            self.files = QListWidget()
            for f in sorted(d.files, key=lambda f: (f.version, f.id)):
                exists = Path(f.path).exists()
                it = QListWidgetItem(f"v{f.version} – {ROLE_FA.get(f.role, f.role)} – {Path(f.path).name}"
                                     + ("" if exists else " (پیدا نشد)"))
                it.setData(Qt.UserRole, f.path)
                self.files.addItem(it)
            self.files.itemDoubleClicked.connect(lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole))))
            fl.addWidget(self.files)
            fb = QHBoxLayout()
            for text, fn in (("باز کردن", self._open_file), ("باز کردن پوشه", self._open_folder),
                             ("ساخت PDF کامل", self._pdf), ("بارگذاری نسخه‌ی نهایی…", self._final)):
                b = QPushButton(text)
                b.clicked.connect(fn)
                b.setEnabled(d.status != "draft" or text == "باز کردن پوشه")
                fb.addWidget(b)
            fb.addStretch(1)
            fl.addLayout(fb)
            self.lay.addWidget(fbox)

            # status
            sbox = QGroupBox("وضعیت")
            sl = QHBoxLayout(sbox)
            for st in ("sent", "accepted", "rejected", "paid", "void"):
                if st == "paid" and d.kind not in ("invoice", "statement"):
                    continue
                if st in ("accepted", "rejected") and d.kind not in ("proforma",):
                    continue
                b = QPushButton(STATUS_FA[st])
                b.setEnabled(st in docs.ALLOWED.get(d.status, set()))
                b.clicked.connect(lambda _=False, x=st: self._status(x))
                sl.addWidget(b)
            sl.addStretch(1)
            self.lay.addWidget(sbox)

            # actions
            abox = QGroupBox("کارها روی این سند")
            al = QHBoxLayout(abox)
            if d.status == "draft":
                b = QPushButton("ادامه‌ی ویرایش")
                b.setObjectName("primary")
                b.clicked.connect(lambda: self._wizard(self.doc_id))
                al.addWidget(b)
                b = QPushButton("حذف پیش‌نویس")
                b.clicked.connect(self._delete)
                al.addWidget(b)
            else:
                if d.kind == "proforma":
                    for kind, label in (("invoice", "ساخت فاکتور از این پیش‌فاکتور"),
                                        ("statement", "ساخت صورت‌وضعیت")):
                        b = QPushButton(label)
                        b.clicked.connect(lambda _=False, k=kind: self._derive(k))
                        al.addWidget(b)
                b = QPushButton("نسخه‌ی جدید")
                b.setToolTip("همان سند با همان شماره ویرایش می‌شود و فایل -v2 ساخته می‌شود؛ نسخه‌ی قبل حفظ می‌شود.")
                b.clicked.connect(self._new_version)
                b.setEnabled(d.status != "void")
                al.addWidget(b)
            b = QPushButton("کپی (سند جدید)")
            b.clicked.connect(lambda: self._copy(None))
            al.addWidget(b)
            self.other_party = SearchCombo(placeholder="ساخت برای مشتری دیگر…")
            self.other_party.set_items([(p.name, p.id) for p in s.scalars(select(Party).where(Party.is_archived.is_(False))
                                                                          .order_by(Party.name))], keep=False)
            self.other_party.activated.connect(lambda _: self._copy(self.other_party.current_id()))
            al.addWidget(self.other_party)
            al.addStretch(1)
            self.lay.addWidget(abox)

            tasks = s.scalars(select(Task).where(Task.document_id == d.id)).all()
            if tasks:
                tl = QLabel("<b>کارهای مرتبط:</b><br>" + "<br>".join(
                    f"{'✓' if t.status == 'done' else '○'} {t.title} – سررسید {jalali.fmt(t.due_date)}" for t in tasks))
                tl.setTextFormat(Qt.RichText)
                self.lay.addWidget(tl)
        self.lay.addStretch(1)
        close = QPushButton("بستن")
        close.clicked.connect(self.accept)
        self.lay.addWidget(close, 0, Qt.AlignLeading)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _open_file(self):
        it = self.files.currentItem() or (self.files.item(self.files.count() - 1) if self.files.count() else None)
        if it:
            QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole)))

    def _open_folder(self):
        with self.S() as s:
            folder = docs.doc_folder(s, s.get(Document, self.doc_id))
            s.commit()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _pdf(self):
        S, doc_id = self.S, self.doc_id

        def job():
            with S() as s:
                return docs.make_full_pdf(s, doc_id)

        def done(path, error):
            if error:
                warn(self, f"PDF ساخته نشد:\n{error[0]}\n\nاگر Word نصب نیست، فایل را در Word باز کنید و Save as PDF بزنید.")
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self.reload()
        run_busy(self, "در حال ساخت PDF با Word…", job, done)

    def _final(self):
        f, _ = QFileDialog.getOpenFileName(self, "فایل نهایی ارسال‌شده", "", "Word یا PDF (*.docx *.pdf)")
        if f:
            with self.S() as s:
                docs.register_final(s, self.doc_id, Path(f))
            self.reload()

    def _status(self, st):
        with self.S() as s:
            try:
                docs.set_status(s, self.doc_id, st)
            except ValueError as e:
                warn(self, str(e))
        self.reload()

    def _derive(self, kind):
        with self.S() as s:
            new = docs.make_invoice_from(s, self.doc_id, kind)
            nid = new.id
        self._wizard(nid)

    def _new_version(self):
        if not confirm(self, "سند برای ویرایش باز شود؟ با ساخت دوباره، فایل نسخه‌ی جدید (-v2) ساخته می‌شود و نسخه‌ی قبلی حفظ می‌شود."):
            return
        with self.S() as s:
            docs.new_version(s, self.doc_id)
        self._wizard(self.doc_id)

    def _copy(self, party_id):
        with self.S() as s:
            new = docs.copy_document(s, self.doc_id, party_id)
            nid = new.id
        self._wizard(nid)

    def _delete(self):
        if confirm(self, "این پیش‌نویس حذف شود؟"):
            with self.S() as s:
                try:
                    docs.delete_draft(s, self.doc_id)
                except ValueError as e:
                    warn(self, str(e))
                    return
            self.accept()

    def _wizard(self, doc_id):
        self.accept()
        self.openWizard.emit(doc_id)


class DocumentsPage(QWidget):
    openWizard = Signal(int)
    changed = Signal()

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.S = SessionLocal
        lay = QVBoxLayout(self)
        t = QLabel("اسناد")
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # all documents
        w = QWidget()
        wl = QVBoxLayout(w)
        filters = QHBoxLayout()
        self.kind_f = QComboBox()
        self.kind_f.addItem("همه‌ی انواع", None)
        for k, v in KIND_FA.items():
            self.kind_f.addItem(v, k)
        self.status_f = QComboBox()
        self.status_f.addItem("همه‌ی وضعیت‌ها", None)
        for k, v in STATUS_FA.items():
            self.status_f.addItem(v, k)
        self.year_f = QComboBox()
        self.party_f = SearchCombo(placeholder="همه‌ی مشتریان")
        for c in (self.kind_f, self.status_f, self.year_f):
            c.currentIndexChanged.connect(lambda _: self.refresh())
        self.party_f.idChanged.connect(lambda _: self.refresh())
        self.party_f.lineEdit().editingFinished.connect(
            lambda: self.refresh() if not self.party_f.currentText().strip() else None)
        for wdg in (self.kind_f, self.status_f, self.year_f, self.party_f):
            filters.addWidget(wdg)
        filters.addStretch(1)
        open_b = QPushButton("باز کردن سند")
        open_b.clicked.connect(self.open_selected)
        filters.addWidget(open_b)
        wl.addLayout(filters)
        self.table = SearchTable(["تاریخ", "نوع", "شماره", "مشتری", "پروژه", "موضوع / عنوان", "مبلغ (ریال)", "وضعیت"])
        self.table.view.doubleClicked.connect(lambda _: self.open_selected())
        wl.addWidget(self.table)
        self.tabs.addTab(w, "همه‌ی اسناد")

        # receivables
        r = QWidget()
        rl = QVBoxLayout(r)
        rl.addWidget(QLabel("فاکتورها و صورت‌وضعیت‌های پرداخت‌نشده، و سپرده‌های آزادنشده، به تفکیک مشتری."))
        self.rec_table = SearchTable(["مشتری", "نوع", "شرح", "مبلغ (ریال)", "تاریخ"])
        self.rec_table.view.doubleClicked.connect(self._open_receivable)
        rl.addWidget(self.rec_table)
        self.rec_total = QLabel(styleSheet="font-weight:bold")
        rl.addWidget(self.rec_total)
        self.tabs.addTab(r, "مطالبات باز")
        self._years_loaded = False
        self.refresh()

    def refresh(self):
        if getattr(self, "_refreshing", False):
            return
        self._refreshing = True
        try:
            self._refresh()
        finally:
            self._refreshing = False

    def _refresh(self):
        with self.S() as s:
            if not self._years_loaded:
                years = sorted({int(d.date_jalali[:4]) for d in s.scalars(select(Document)) if d.date_jalali}, reverse=True)
                self.year_f.blockSignals(True)
                self.year_f.addItem("همه‌ی سال‌ها", None)
                for y in years:
                    self.year_f.addItem(str(y), y)
                self.year_f.blockSignals(False)
                self.party_f.blockSignals(True)
                self.party_f.set_items([(p.name, p.id) for p in s.scalars(select(Party).where(Party.is_archived.is_(False))
                                                                          .order_by(Party.name))], keep=False)
                self.party_f.blockSignals(False)
                self._years_loaded = True
            q = select(Document).where(Document.is_archived.is_(False)).order_by(Document.date_greg.desc(), Document.id.desc())
            if self.kind_f.currentData():
                q = q.where(Document.kind == self.kind_f.currentData())
            if self.status_f.currentData():
                q = q.where(Document.status == self.status_f.currentData())
            if self.year_f.currentData():
                q = q.where(Document.date_jalali.like(f"{self.year_f.currentData()}/%"))
            if self.party_f.current_id():
                q = q.where(Document.party_id == self.party_f.current_id())
            rows = s.scalars(q).all()
            self.table.set_rows(
                [[d.date_jalali, KIND_FA[d.kind], d.number or "—", d.party.short_name or d.party.name if d.party else "",
                  d.project.title if d.project else "", d.subject or d.title,
                  money.fmt_int(d.payable) if d.payable else "", STATUS_FA.get(d.status, d.status)] for d in rows],
                [d.id for d in rows], [STATUS_COLORS.get(d.status, "") for d in rows])
            rec = proj.receivables(s)
            self.rec_table.set_rows([[r.party, "فاکتور" if r.kind == "invoice" else "سپرده", r.title,
                                      money.fmt_int(r.amount), jalali.fmt(r.date) if r.date else ""] for r in rec],
                                    [(r.document_id, r.project_id) for r in rec])
            self.rec_total.setText(f"جمع مطالبات باز: {money.fmt_int(sum(r.amount for r in rec))} ریال")

    def open_selected(self):
        ident = self.table.selected_id()
        if ident:
            self.open_document(ident)

    def open_document(self, doc_id):
        dlg = DocumentDialog(self.S, doc_id, self)
        dlg.openWizard.connect(self.openWizard.emit)
        dlg.exec()
        self.refresh()
        self.changed.emit()

    def _open_receivable(self, _):
        ident = self.rec_table.selected_id()
        if ident and ident[0]:
            self.open_document(ident[0])
