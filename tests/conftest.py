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
