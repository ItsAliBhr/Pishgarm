"""Main window: navigation on the right (RTL), one page per section (doc 04 §4.1)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from app import APP_TITLE_FA
from app.db.models import Task
from app.ui.pages.master_data import MasterDataPage
from app.ui.pages.simple import HomePage, PlaceholderPage, SettingsPage

STYLE = """
QListWidget#nav { background: #f3f5f8; border: none; padding: 8px; outline: 0; }
QListWidget#nav::item { padding: 10px 14px; border-radius: 6px; }
QListWidget#nav::item:selected { background: #1f6feb; color: white; }
QLabel#pageTitle { font-size: 16pt; font-weight: bold; padding: 4px 0 10px 0; }
QPushButton#primary { background: #1f6feb; color: white; font-weight: bold;
                      border-radius: 6px; padding: 8px 28px; }
QPushButton#primary:disabled { background: #9db8e6; }
"""


class MainWindow(QMainWindow):
    SECTIONS = ["خانه", "اسناد", "پروژه‌ها", "کارها", "اطلاعات پایه", "تنظیمات"]

    def __init__(self, SessionLocal):
        super().__init__()
        self.SessionLocal = SessionLocal
        self.setStyleSheet(STYLE)
        self.resize(1200, 760)

        self.nav = QListWidget(objectName="nav")
        self.nav.setFixedWidth(190)
        self.nav.setIconSize(QSize(20, 20))
        self.nav.addItems(self.SECTIONS)

        self.master_data = MasterDataPage(SessionLocal)
        self.pages = QStackedWidget()
        for page in (
            HomePage(),
            PlaceholderPage("اسناد", "فهرست اسناد صادرشده در فاز ۱ اضافه می‌شود."),
            PlaceholderPage("پروژه‌ها", "پوشه‌بندی شرکت ← پروژه در فاز ۲ اضافه می‌شود."),
            PlaceholderPage("کارها", "تسک منیجر در فاز ۳ اضافه می‌شود."),
            self.master_data,
            SettingsPage(SessionLocal),
        ):
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.nav)   # first widget sits on the right in RTL
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.update_title()

    def go_to(self, section: str) -> None:
        self.nav.setCurrentRow(self.SECTIONS.index(section))

    def overdue_count(self) -> int:
        with self.SessionLocal() as s:
            return s.scalar(select(func.count(Task.id)).where(
                Task.status == "open", Task.due_date < date.today(), Task.is_archived.is_(False))) or 0

    def update_title(self) -> None:
        n = self.overdue_count()
        self.setWindowTitle(f"{APP_TITLE_FA} — {n} کار عقب‌افتاده" if n else APP_TITLE_FA)
