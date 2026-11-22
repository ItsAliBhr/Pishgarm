import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data folder and output root; nothing touches the real profile."""
    monkeypatch.setenv("PISHGARM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profile"))
    return tmp_path


@pytest.fixture
def db(tmp_path):
    from app.db.session import open_database
    engine, SessionLocal = open_database(tmp_path / "data" / "data.db")
    yield SessionLocal
    engine.dispose()


_APP = None


@pytest.fixture(scope="session")
def _qt_app():
    """One QApplication for the whole run, kept referenced until the very end (a QApplication
    destroyed while widgets still exist crashes at interpreter exit)."""
    global _APP
    from app.ui.app import create_app, load_fonts
    _APP = create_app(["test"])
    load_fonts(_APP)
    yield _APP
    _APP.closeAllWindows()
    _APP.processEvents()


@pytest.fixture
def qapp(_qt_app, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: True))
    yield _qt_app
    for w in QApplication.topLevelWidgets():
        w.close()
        w.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    _qt_app.processEvents()
