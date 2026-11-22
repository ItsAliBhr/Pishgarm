"""Main window: navigation on the right (RTL), one page per section (doc 04 §4.1)."""
from __future__ import annotations

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget
from sqlalchemy import select

from app import APP_TITLE_FA
from app.db.models import Issuer, LetterType
from app.services import tasks as task_service
from app.ui.pages.documents import DocumentsPage
from app.ui.pages.master_data import MasterDataPage
from app.ui.pages.projects import ProjectsPage
from app.ui.pages.simple import HomePage, SettingsPage
from app.ui.pages.tasks import TasksPage

STYLE = """
QListWidget#nav { background: #f3f5f8; border: none; padding: 8px; outline: 0; }
QListWidget#nav::item { padding: 10px 14px; border-radius: 6px; }
QListWidget#nav::item:selected { background: #1f6feb; color: white; }
QLabel#pageTitle { font-size: 16pt; font-weight: bold; padding: 4px 0 10px 0; }
QPushButton#primary { background: #1f6feb; color: white; font-weight: bold;
                      border-radius: 6px; padding: 8px 22px; border: none; }
QPushButton#primary:hover { background: #1a5fd0; }
QPushButton#primary:disabled { background: #9db8e6; }
QPushButton#card { background: white; border: 1px solid #cfd8e3; border-radius: 10px; padding: 12px;
                   font-size: 12pt; text-align: center; }
QPushButton#card:hover { border-color: #1f6feb; }
QPushButton#card:checked { background: #e8f0fe; border: 2px solid #1f6feb; }
QPushButton#step { border: none; border-bottom: 3px solid #dde3ea; padding: 8px; background: transparent; }
QPushButton#step:checked { border-bottom: 3px solid #1f6feb; font-weight: bold; color: #1f6feb; }
QPushButton#step:disabled { color: #aaa; }
QFrame#summary { background: #f7f9fc; border: 1px solid #e1e6ee; border-radius: 8px; }
"""


class MainWindow(QMainWindow):
    SECTIONS = ["خانه", "اسناد", "پروژه‌ها", "کارها", "اطلاعات پایه", "تنظیمات"]

    def __init__(self, SessionLocal):
        super().__init__()
        self.SessionLocal = SessionLocal
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(STYLE)   # app-wide, so dialogs get it too
        self.resize(1280, 800)

        self.nav = QListWidget(objectName="nav")
        self.nav.setFixedWidth(190)
        self.nav.setIconSize(QSize(20, 20))
        self.nav.addItems(self.SECTIONS)

        self.home = HomePage(SessionLocal)
        self.documents = DocumentsPage(SessionLocal)
        self.projects = ProjectsPage(SessionLocal)
        self.tasks = TasksPage(SessionLocal)
        self.master_data = MasterDataPage(SessionLocal)
        self.settings = SettingsPage(SessionLocal)
        self.pages = QStackedWidget()
        for page in (self.home, self.documents, self.projects, self.tasks, self.master_data, self.settings):
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(0)

        self.home.newDocument.connect(self.new_document)
        self.home.openDocument.connect(self.documents.open_document)
        self.home.goTasks.connect(lambda: self.go_to("کارها"))
        self.documents.openWizard.connect(self.open_wizard)
        self.documents.changed.connect(self.refresh_all)
        self.projects.openDocument.connect(self.documents.open_document)
        self.projects.newDocument.connect(self.new_document)
        self.projects.changed.connect(self.refresh_all)
        self.tasks.changed.connect(self.refresh_all)
        self.tasks.runAction.connect(self.run_task_action)
        self.settings.changed.connect(self.refresh_all)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.nav)   # first widget sits on the right in RTL
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.update_title()
        # re-check overdue tasks once an hour (the app may stay open for days)
        self._timer = QTimer(self, interval=3600 * 1000, timeout=self.refresh_all)
        self._timer.start()

    def _on_nav(self, row):
        self.pages.setCurrentIndex(row)
        page = self.pages.widget(row)
        if hasattr(page, "refresh"):
            page.refresh()

    def go_to(self, section: str) -> None:
        self.nav.setCurrentRow(self.SECTIONS.index(section))

    @property
    def master(self):
        return self.master_data

    def overdue_count(self) -> int:
        with self.SessionLocal() as s:
            return task_service.overdue_count(s)

    def update_title(self) -> None:
        n = self.overdue_count()
        self.setWindowTitle(f"{APP_TITLE_FA} — {n} کار عقب‌افتاده" if n else APP_TITLE_FA)

    def refresh_all(self):
        for page in (self.home, self.documents, self.projects, self.tasks):
            page.refresh()
        self.update_title()

    # ------------------------------------------------------------------ wizard entry points
    def new_document(self, preset: dict | None = None):
        from app.ui.wizard import DocumentWizard
        dlg = DocumentWizard(self.SessionLocal, preset={k: v for k, v in (preset or {}).items() if v}, parent=self)
        dlg.exec()
        self.refresh_all()

    def open_wizard(self, doc_id: int):
        from app.ui.wizard import DocumentWizard
        dlg = DocumentWizard(self.SessionLocal, doc_id=doc_id, parent=self)
        dlg.exec()
        self.refresh_all()

    def run_task_action(self, action: dict):
        """A finished automatic task opens the wizard prefilled (e.g. retention release letter)."""
        if action.get("open") != "letter_wizard":
            return
        with self.SessionLocal() as s:
            company = s.scalar(select(Issuer).where(Issuer.code == "COMPANY", Issuer.is_archived.is_(False)))
            issuer_id = company.id if company else None
        self.new_document({"kind": "letter", "issuer_id": issuer_id, "party_id": action.get("party_id"),
                           "project_id": action.get("project_id"), "letter_type": action.get("letter_type")})
