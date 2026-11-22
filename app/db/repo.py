"""Small query helpers shared by the UI."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import paths
from app.db.models import Setting

DEFAULT_OUTPUT_ROOT = r"%USERPROFILE%\Documents\اسناد پیشگرم"


def get_setting(s: Session, key: str, default=None):
    row = s.get(Setting, key)
    return default if row is None else row.value_json


def set_setting(s: Session, key: str, value) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value_json=value))
    else:
        row.value_json = value
    s.commit()


def output_root(s: Session) -> Path:
    return paths.expand_user_path(get_setting(s, "output_root", DEFAULT_OUTPUT_ROOT))
