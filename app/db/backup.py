"""Automatic backup of data.db (doc 07 §7.3): on close and once a day, keep the last 30."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import jdatetime

from app import paths

log = logging.getLogger(__name__)

BACKUP_FOLDER = "_پشتیبان"


def backup_dir(output_root: Path) -> Path:
    d = Path(output_root) / BACKUP_FOLDER
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp(today: jdatetime.date | None = None) -> str:
    today = today or jdatetime.date.today()
    return f"{today.year:04d}-{today.month:02d}-{today.day:02d}"


def backup_now(target_dir: Path, db_file: Path | None = None, keep: int = 30,
               today: jdatetime.date | None = None) -> Path:
    """Copy the database with SQLite's online backup API (safe while the app has it open).
    One file per Jalali day (data-1405-09-01.db); a later backup the same day replaces it."""
    db_file = Path(db_file) if db_file else paths.db_path()
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"data-{_stamp(today)}.db"
    tmp = dest.with_suffix(".db.tmp")
    src = sqlite3.connect(db_file)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    tmp.replace(dest)
    prune(target_dir, keep)
    log.info("backup written: %s", dest)
    return dest


def prune(target_dir: Path, keep: int) -> None:
    files = sorted(Path(target_dir).glob("data-*.db"))
    for old in files[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)


def backup_if_due(target_dir: Path, db_file: Path | None = None, keep: int = 30) -> Path | None:
    """Daily backup: only if today's file does not exist yet."""
    if (Path(target_dir) / f"data-{_stamp()}.db").exists():
        return None
    return backup_now(target_dir, db_file, keep)


PENDING_RESTORE = "restore-pending.db"


def schedule_restore(source) -> None:
    """Copy a backup next to data.db; it replaces data.db at the next start (DB is closed then)."""
    import shutil
    shutil.copy2(source, paths.data_dir() / PENDING_RESTORE)


def apply_pending_restore() -> bool:
    pending = paths.data_dir() / PENDING_RESTORE
    if not pending.exists():
        return False
    db = paths.db_path()
    for suffix in ("-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    pending.replace(db)
    log.info("restored database from backup")
    return True
