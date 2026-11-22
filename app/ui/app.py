"""Application bootstrap: logging, RTL + Vazirmatn, database, daily backup, main window."""
from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, APP_TITLE_FA, __version__, paths
from app.db import backup
from app.db.repo import get_setting, output_root
from app.db.session import open_database

log = logging.getLogger("app")


def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def load_fonts(app: QApplication, size_pt: int = 11) -> str:
    family = "Vazirmatn"
    for f in sorted((paths.resources_dir() / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            family = fams[0]
    app.setFont(QFont(family, size_pt))
    return family


def show_error(title: str, details: str) -> None:
    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(APP_TITLE_FA)
    box.setText(title)
    box.setDetailedText(details)
    copy = box.addButton("کپی جزئیات", QMessageBox.ActionRole)
    box.addButton("بستن", QMessageBox.AcceptRole)
    box.exec()
    if box.clickedButton() is copy:
        QApplication.clipboard().setText(details)


def _excepthook(exc_type, exc, tb):
    details = "".join(traceback.format_exception(exc_type, exc, tb))
    log.error("unhandled error:\n%s", details)
    if QApplication.instance():
        show_error("خطایی پیش آمد. کار شما ذخیره شده است؛ لطفاً جزئیات را برای پشتیبانی بفرستید.",
                   details)


def create_app(argv=None) -> QApplication:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE_FA)
    app.setApplicationVersion(__version__)
    app.setLayoutDirection(Qt.RightToLeft)
    return app


def main(argv=None) -> int:
    setup_logging()
    sys.excepthook = _excepthook
    app = create_app(argv)
    try:
        engine, SessionLocal = open_database()
    except Exception:
        show_error("پایگاه داده باز نشد.", traceback.format_exc())
        return 1

    with SessionLocal() as s:
        load_fonts(app, int(get_setting(s, "ui_font_size_pt", 11)))
        bdir = backup.backup_dir(output_root(s))
        keep = int(get_setting(s, "backup_keep_count", 30))
    try:
        backup.backup_if_due(bdir, keep=keep)
    except Exception:
        log.exception("daily backup failed")

    from app.ui.main_window import MainWindow

    win = MainWindow(SessionLocal)
    win.show()

    def _on_quit():
        try:
            backup.backup_now(bdir, keep=keep)
        except Exception:
            log.exception("backup on close failed")
        engine.dispose()

    app.aboutToQuit.connect(_on_quit)
    return app.exec()
