"""Acceptance (phase 0, item 2): master data → parties shows the 42 seed rows; RTL; font."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture
def qapp():
    from app.ui.app import create_app, load_fonts
    app = create_app(["test"])
    load_fonts(app)
    return app


def test_main_window_rtl_and_parties(qapp, db):
    from app.ui.main_window import MainWindow
    win = MainWindow(db)
    assert qapp.layoutDirection() == Qt.RightToLeft
    assert qapp.font().family() == "Vazirmatn"
    win.go_to("اطلاعات پایه")
    parties = win.master_data.tables["parties"]
    assert parties.row_count() == 42
    parties.search.setText("ناب")
    assert 1 <= parties.row_count() < 42
    parties.search.setText("")
    assert win.master_data.tables["clauses"].row_count() == 45
    assert win.windowTitle() == "دفتر اسناد پیشگرم"
    win.close()
