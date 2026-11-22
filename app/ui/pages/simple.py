"""Home (today) and Settings."""
from __future__ import annotations

import shutil
from datetime import date

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)
from sqlalchemy import select

from app import __version__, paths
from app.core import money, pdf_tools
from app.core.draft import KIND_FA, STATUS_FA
from app.db import backup
from app.db.models import Document, Task
from app.db.repo import get_setting, output_root, set_setting
from app.ui.widgets import SearchTable, confirm, info


def primary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("primary")
    b.setMinimumHeight(48)
    return b


class HomePage(QWidget):
    newDocument = Signal(dict)
    openDocument = Signal(int)
    goTasks = Signal()

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.S = SessionLocal
        lay = QVBoxLayout(self)
        title = QLabel("امروز")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        row = QHBoxLayout()
        self.new_doc = primary_button("+ سند جدید")
        self.new_doc.setMinimumWidth(220)
        self.new_doc.clicked.connect(lambda: self.newDocument.emit({}))
        row.addWidget(self.new_doc)
        for kind in ("proforma", "letter", "invoice"):
            b = QPushButton(f"{KIND_FA[kind]} جدید")
            b.setMinimumHeight(48)
            b.clicked.connect(lambda _=False, k=kind: self.newDocument.emit({"kind": k}))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.tasks_label = QLabel()
        self.tasks_label.setTextFormat(Qt.RichText)
        self.tasks_label.linkActivated.connect(lambda _: self.goTasks.emit())
        lay.addWidget(self.tasks_label)
        self.tasks = SearchTable(["عنوان کار", "سررسید", "مشتری"])
        self.tasks.search.hide()
        self.tasks.setMaximumHeight(240)
        self.tasks.view.doubleClicked.connect(lambda _: self.goTasks.emit())
        lay.addWidget(self.tasks)
        lay.addWidget(QLabel("<b>آخرین اسناد</b>"))
        self.recent = SearchTable(["تاریخ", "نوع", "شماره", "مشتری", "موضوع / عنوان", "مبلغ", "وضعیت"])
        self.recent.search.hide()
        self.recent.view.doubleClicked.connect(lambda _: self.openDocument.emit(self.recent.selected_id())
                                               if self.recent.selected_id() else None)
        lay.addWidget(self.recent, 1)
        self.refresh()

    def refresh(self):
        from app.core import jalali
        with self.S() as s:
            today = date.today()
            tasks = s.scalars(select(Task).where(Task.status == "open", Task.is_archived.is_(False),
                                                 Task.due_date <= today).order_by(Task.due_date)).all()
            overdue = sum(1 for t in tasks if t.due_date < today)
            self.tasks_label.setText(f"<b>کارهای امروز و عقب‌افتاده: {len(tasks)}</b>"
                                     + (f" <span style='color:#c62828'>({overdue} عقب‌افتاده)</span>" if overdue else "")
                                     + " &nbsp; <a href='tasks'>همه‌ی کارها</a>")
            self.tasks.set_rows([[t.title, jalali.fmt(t.due_date),
                                  (t.party.short_name or t.party.name) if t.party else ""] for t in tasks],
                                [t.id for t in tasks], ["#c62828" if t.due_date < today else "" for t in tasks])
            docs = s.scalars(select(Document).where(Document.is_archived.is_(False))
                             .order_by(Document.id.desc()).limit(15)).all()
            self.recent.set_rows([[d.date_jalali, KIND_FA[d.kind], d.number or "—",
                                   (d.party.short_name or d.party.name) if d.party else "", d.subject or d.title,
                                   money.fmt_int(d.payable) if d.payable else "", STATUS_FA.get(d.status)]
                                  for d in docs], [d.id for d in docs])


class SettingsPage(QWidget):
    changed = Signal()

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.S = SessionLocal
        outer = QVBoxLayout(self)
        t = QLabel("تنظیمات")
        t.setObjectName("pageTitle")
        outer.addWidget(t)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        with SessionLocal() as s:
            self.out_root = output_root(s)
            self.keep = int(get_setting(s, "backup_keep_count", 30))
            g = lambda k, d=None: get_setting(s, k, d)  # noqa: E731
            vals = {k: g(k) for k in ("numbering_shared_letter_invoice", "numbering_separate_per_issuer",
                                      "personal_invoice_show_national_id", "output_digits_persian",
                                      "markup_round_step_rial", "ui_font_size_pt", "retention_months_default",
                                      "retention_percent_default", "task_invoice_payment_days",
                                      "task_payment_letter_reply_days", "task_proforma_followup_workdays",
                                      "task_advance_followup_days")}
            self.legacy = g("legacy_archive_root", "")

        # paths
        box = QGroupBox("مسیرها")
        form = QFormLayout(box)
        row = QHBoxLayout()
        self.root_label = self._path_label(self.out_root)
        ch = QPushButton("تغییر…")
        ch.clicked.connect(self._change_root)
        op = QPushButton("باز کردن")
        op.clicked.connect(lambda: self._open(self.out_root))
        row.addWidget(self.root_label, 1)
        row.addWidget(ch)
        row.addWidget(op)
        form.addRow("پوشه‌ی اسناد:", row)
        form.addRow("پایگاه داده:", self._path_label(paths.db_path()))
        form.addRow("نسخه‌ی برنامه:", QLabel(__version__))
        pdf = "Word یا LibreOffice پیدا شد ✓" if pdf_tools.pdf_available() else "Word پیدا نشد؛ PDF ساخته نمی‌شود"
        form.addRow("ساخت PDF:", QLabel(pdf))
        lay.addWidget(box)

        # backup
        bbox = QGroupBox("پشتیبان")
        bl = QVBoxLayout(bbox)
        bl.addWidget(QLabel(f"هنگام بستن برنامه و روزی یک بار، پشتیبان خودکار در پوشه‌ی «{backup.BACKUP_FOLDER}» "
                            f"ساخته می‌شود و {self.keep} نسخه‌ی آخر نگه داشته می‌شود.", wordWrap=True))
        brow = QHBoxLayout()
        for text, fn in (("پشتیبان‌گیری همین حالا", self.backup_now), ("پشتیبان‌گیری روی فلش…", self.backup_to_folder),
                         ("باز کردن پوشه‌ی پشتیبان", lambda: self._open(backup.backup_dir(self.out_root))),
                         ("بازگردانی از پشتیبان…", self.restore)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            brow.addWidget(b)
        brow.addStretch(1)
        bl.addLayout(brow)
        lay.addWidget(bbox)

        # numbering & defaults
        nbox = QGroupBox("شماره‌گذاری و پیش‌فرض‌ها")
        nf = QFormLayout(nbox)
        self.checks = {}
        for key, label in (("numbering_shared_letter_invoice", "شماره‌گذاری نامه و فاکتور مشترک باشد"),
                           ("numbering_separate_per_issuer", "شماره‌گذاری شخصی و شرکتی جدا باشد"),
                           ("personal_invoice_show_national_id", "کد ملی فروشنده در فاکتور شخصی چاپ شود"),
                           ("output_digits_persian", "مبالغ جدول با ارقام فارسی چاپ شود")):
            cb = QCheckBox(label)
            cb.setChecked(bool(vals[key]))
            cb.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
            nf.addRow("", cb)
            self.checks[key] = cb
        self.spins = {}
        for key, label, lo, hi, suffix in (
                ("retention_percent_default", "درصد پیش‌فرض سپرده:", 0, 100, " ٪"),
                ("retention_months_default", "مدت پیش‌فرض سپرده:", 0, 60, " ماه"),
                ("task_proforma_followup_workdays", "پیگیری تأیید پیش‌فاکتور (اگر اعتبار نداشت):", 1, 60, " روز کاری"),
                ("task_advance_followup_days", "پیگیری پیش‌پرداخت پس از تأیید:", 1, 60, " روز"),
                ("task_invoice_payment_days", "پیگیری پرداخت فاکتور:", 1, 120, " روز"),
                ("task_payment_letter_reply_days", "پیگیری پاسخ نامه‌ی درخواست پرداخت:", 1, 60, " روز"),
                ("ui_font_size_pt", "اندازه‌ی فونت برنامه (پس از اجرای دوباره):", 9, 16, " pt")):
            sp = QSpinBox(minimum=lo, maximum=hi)
            sp.setSuffix(suffix)
            default = {"task_proforma_followup_workdays": 3, "task_advance_followup_days": 3,
                       "task_invoice_payment_days": 14, "task_payment_letter_reply_days": 10}.get(key, 0)
            sp.setValue(int(float(vals[key])) if vals[key] is not None else default)
            sp.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
            nf.addRow(label, sp)
            self.spins[key] = sp
        self.step = QComboBox()
        for v, label in ((1, "۱ ریال (بدون گرد کردن)"), (10_000, "۱۰٬۰۰۰ ریال"), (100_000, "۱۰۰٬۰۰۰ ریال"),
                         (1_000_000, "۱٬۰۰۰٬۰۰۰ ریال")):
            self.step.addItem(label, v)
        self.step.setCurrentIndex(max(self.step.findData(int(vals["markup_round_step_rial"] or 1)), 0))
        self.step.currentIndexChanged.connect(lambda _: self._set("markup_round_step_rial", self.step.currentData()))
        nf.addRow("گرد کردن قیمت مارک‌آپ (رو به بالا):", self.step)
        lay.addWidget(nbox)

        # templates
        tbox = QGroupBox("قالب‌های Word")
        tl = QVBoxLayout(tbox)
        tl.addWidget(QLabel("برای تغییر ظاهر، قالب را در Word ویرایش کنید و برچسب‌های {{ }} و {% %} را دست نزنید. "
                            "نسخه‌ی ویرایش‌شده‌ی شما بر نسخه‌ی پیش‌فرض اولویت دارد.", wordWrap=True))
        trow = QHBoxLayout()
        self.tpl_combo = QComboBox()
        for f in sorted(paths.bundled_templates_dir().glob("*.docx")):
            self.tpl_combo.addItem(f.name)
        e = QPushButton("ویرایش در Word")
        e.clicked.connect(self._edit_template)
        r = QPushButton("بازگردانی قالب پیش‌فرض")
        r.clicked.connect(self._restore_template)
        trow.addWidget(self.tpl_combo)
        trow.addWidget(e)
        trow.addWidget(r)
        trow.addStretch(1)
        tl.addLayout(trow)
        lay.addWidget(tbox)

        # legacy archive
        abox = QGroupBox("بایگانی قدیمی")
        al = QVBoxLayout(abox)
        al.addWidget(QLabel("پوشه‌ی قدیمی اسناد را انتخاب کنید تا فایل‌ها زیر هر مشتری (از روی نام پوشه) "
                            "در صفحه‌ی «پروژه‌ها» دیده شوند. فایل‌ها جابه‌جا نمی‌شوند.", wordWrap=True))
        arow = QHBoxLayout()
        self.legacy_label = QLabel(self.legacy or "انتخاب نشده")
        a = QPushButton("انتخاب پوشه و فهرست‌برداری…")
        a.clicked.connect(self._scan_legacy)
        arow.addWidget(self.legacy_label, 1)
        arow.addWidget(a)
        al.addLayout(arow)
        lay.addWidget(abox)

        # logs
        lbox = QGroupBox("عیب‌یابی")
        ll = QHBoxLayout(lbox)
        b = QPushButton("باز کردن پوشه‌ی گزارش خطا")
        b.clicked.connect(lambda: self._open(paths.logs_dir()))
        ll.addWidget(b)
        ll.addStretch(1)
        lay.addWidget(lbox)
        lay.addStretch(1)

    @staticmethod
    def _path_label(p) -> QLabel:
        l = QLabel(str(p))
        l.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return l

    def _open(self, p):
        from pathlib import Path
        Path(p).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _set(self, key, value):
        with self.S() as s:
            set_setting(s, key, value)
        self.changed.emit()

    def _change_root(self):
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی اسناد", str(self.out_root))
        if folder:
            self._set("output_root", folder)
            with self.S() as s:
                self.out_root = output_root(s)
            self.root_label.setText(str(self.out_root))

    def backup_now(self):
        dest = backup.backup_now(backup.backup_dir(self.out_root), keep=self.keep)
        info(self, f"پشتیبان ساخته شد:\n{dest}")

    def backup_to_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی فلش را انتخاب کنید")
        if not folder:
            return
        dest = backup.backup_now(backup.backup_dir(self.out_root), keep=self.keep)
        target = shutil.copy2(dest, folder)
        info(self, f"پشتیبان روی فلش کپی شد:\n{target}")

    def restore(self):
        f, _ = QFileDialog.getOpenFileName(self, "فایل پشتیبان", str(backup.backup_dir(self.out_root)), "پشتیبان (*.db)")
        if not f:
            return
        if not confirm(self, "اطلاعات فعلی با این پشتیبان جایگزین شود؟ (از وضعیت فعلی هم یک پشتیبان گرفته می‌شود.) "
                             "برنامه پس از بازگردانی بسته می‌شود."):
            return
        backup.backup_now(backup.backup_dir(self.out_root), keep=self.keep)
        backup.schedule_restore(f)
        QMessageBox.information(self, "بازگردانی", "برنامه بسته می‌شود؛ دوباره باز کنید.")
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _edit_template(self):
        name = self.tpl_combo.currentText()
        user = paths.user_templates_dir() / name
        if not user.exists():
            shutil.copy2(paths.bundled_templates_dir() / name, user)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(user)))

    def _restore_template(self):
        name = self.tpl_combo.currentText()
        user = paths.user_templates_dir() / name
        if user.exists() and confirm(self, f"نسخه‌ی ویرایش‌شده‌ی {name} کنار گذاشته شود؟"):
            user.rename(user.with_suffix(".docx.old"))
            info(self, "قالب پیش‌فرض برگشت.")

    def _scan_legacy(self):
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی قدیمی اسناد", self.legacy or "")
        if not folder:
            return
        from app.services.projects import scan_legacy_archive
        with self.S() as s:
            n = scan_legacy_archive(s, folder)
            set_setting(s, "legacy_archive_root", folder)
        self.legacy_label.setText(folder)
        info(self, f"{n} فایل فهرست شد. در صفحه‌ی «پروژه‌ها» زیر هر مشتری دیده می‌شوند.")
        self.changed.emit()
