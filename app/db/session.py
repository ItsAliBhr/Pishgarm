"""Engine / session factory for the single SQLite file."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app import paths
from app.db.migrations import migrate


def make_engine(db_file: Path | None = None):
    db_file = Path(db_file) if db_file else paths.db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA journal_mode = WAL")
        cur.close()

    return engine


def open_database(db_file: Path | None = None) -> tuple:
    """Create/migrate the database and load seed data on first run. Returns (engine, Session)."""
    from app.db.seed import load_seed

    engine = make_engine(db_file)
    migrate(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)
    with SessionLocal() as s:
        load_seed(s)
    return engine, SessionLocal


def new_session(SessionLocal) -> Session:
    return SessionLocal()
