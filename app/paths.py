"""Filesystem locations: bundled resources (read-only) and per-user data (writable)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from app import APP_NAME


def bundle_root() -> Path:
    """Root holding templates/, seed/, assets/ and app/resources/.

    In a PyInstaller build this is sys._MEIPASS; in development it is the repo root.
    """
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent.parent


def seed_dir() -> Path:
    return bundle_root() / "seed"


def bundled_templates_dir() -> Path:
    return bundle_root() / "templates"


def bundled_assets_dir() -> Path:
    return bundle_root() / "assets"


def resources_dir() -> Path:
    return bundle_root() / "app" / "resources"


def data_dir() -> Path:
    """Writable per-user data folder: %LOCALAPPDATA%\\PishgarmDocs on Windows.

    PISHGARM_DATA_DIR overrides it (used by tests and portable runs).
    """
    override = os.environ.get("PISHGARM_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "data.db"


def user_assets_dir() -> Path:
    p = data_dir() / "assets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_templates_dir() -> Path:
    p = data_dir() / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def template_path(name: str) -> Path:
    """A user-edited copy in the data folder wins over the bundled template (doc 07 §7.3)."""
    user = user_templates_dir() / name
    if user.exists():
        return user
    return bundled_templates_dir() / name


def expand_user_path(value: str) -> Path:
    """Expand %USERPROFILE% / %VAR% and ~ in a settings path, portable across OSes."""
    def _var(m):
        name = m.group(1)
        if name.upper() == "USERPROFILE":
            return os.environ.get("USERPROFILE", str(Path.home()))
        return os.environ.get(name, m.group(0))

    value = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", _var, value)
    value = os.path.expandvars(value)
    if sys.platform != "win32":
        value = value.replace("\\", "/")
    return Path(value).expanduser()
