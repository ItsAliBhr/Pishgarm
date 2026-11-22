"""Home, placeholder pages and settings for phase 0."""
from __future__ import annotations

import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGroupBox, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from app import __version__, paths
from app.db import backup
from app.db.repo import get_setting, output_root


def primary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("primary")
    b.setMinimumHeight(48)
    return b


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        title = QLabel("امروز")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        self.new_doc = primary_button("+ سند جدید")
        self.new_doc.setToolTip("ویزارد صدور سند در فاز ۱ اضافه می‌شود.")
        self.new_doc.setEnabled(False)
        lay.addWidget(self.new_doc, 0, Qt.AlignLeading)
        lay.addWidget(QLabel("کارهای امروز و آخرین اسناد اینجا نمایش داده می‌شوند."))
        lay.addStretch(1)


class PlaceholderPage(QWidget):
    def __init__(self, title: str, note: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        lay.addWidget(QLabel(note))
        lay.addStretch(1)


class SettingsPage(QWidget):
    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.SessionLocal = SessionLocal
        lay = QVBoxLayout(self)
        t = QLabel("تنظیمات")
        t.setObjectName("pageTitle")
        lay.addWidget(t)

        with SessionLocal() as s:
            self.out_root = output_root(s)
            self.keep = int(get_setting(s, "backup_keep_count", 30))

        box = QGroupBox("مسیرها")
        form = QFormLayout(box)
        form.addRow("پوشه‌ی اسناد:", self._path_label(self.out_root))
        form.addRow("پایگاه داده:", self._path_label(paths.db_path()))
        form.addRow("نسخه‌ی برنامه:", QLabel(__version__))
        lay.addWidget(box)

        bbox = QGroupBox("پشتیبان")
        bl = QVBoxLayout(bbox)
        bl.addWidget(QLabel(f"هنگام بستن برنامه و روزی یک بار، پشتیبان خودکار در پوشه‌ی «{backup.BACKUP_FOLDER}» "
                            f"ساخته می‌شود و {self.keep} نسخه‌ی آخر نگه داشته می‌شود."))
        b1 = QPushButton("پشتیبان‌گیری همین حالا")
        b1.clicked.connect(self.backup_now)
        b2 = QPushButton("پشتیبان‌گیری روی فلش…")
        b2.clicked.connect(self.backup_to_folder)
        b3 = QPushButton("باز کردن پوشه‌ی پشتیبان")
        b3.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(backup.backup_dir(self.out_root)))))
        for b in (b1, b2, b3):
            bl.addWidget(b, 0, Qt.AlignLeading)
        lay.addWidget(bbox)
        lay.addStretch(1)

    @staticmethod
    def _path_label(p) -> QLabel:
        l = QLabel(str(p))
        l.setTextInteractionFlags(Qt.TextSelectableByMouse)
        l.setLayoutDirection(Qt.LeftToRight)
        return l

    def backup_now(self):
        dest = backup.backup_now(backup.backup_dir(self.out_root), keep=self.keep)
        QMessageBox.information(self, "پشتیبان", f"پشتیبان ساخته شد:\n{dest}")

    def backup_to_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی فلش را انتخاب کنید")
        if not folder:
            return
        dest = backup.backup_now(backup.backup_dir(self.out_root), keep=self.keep)
        target = shutil.copy2(dest, folder)
        QMessageBox.information(self, "پشتیبان", f"پشتیبان روی فلش کپی شد:\n{target}")
