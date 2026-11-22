"""Simple schema versioning with PRAGMA user_version (doc 07 §7.2)."""
from __future__ import annotations

import logging

from sqlalchemy import Engine, text

from app.db.models import Base

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# Tables v0.1.0 created but never wrote to (it only showed master data).
_V1_UNUSED_TABLES = ["document_file", "document_account", "document_clause", "document_line",
                     "task", "party_clause_default", "document", "project", "number_counter",
                     "audit_log", "archive_file"]


def _v1_to_v2(conn) -> None:
    """Recreate the transactional tables with their v2 shape. Refuses if any holds data."""
    for t in _V1_UNUSED_TABLES:
        exists = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                              {"n": t}).first()
        if exists and conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar():
            raise RuntimeError(f"migration v1→v2: table {t} is not empty")
    for t in _V1_UNUSED_TABLES:
        conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))
    Base.metadata.create_all(conn)
    # personal numbering: month without zero padding (archive 401100 = 401 | 1 | 00)
    conn.execute(text("UPDATE issuer SET number_pattern='{yyy}{m}{seq:02}' "
                      "WHERE code='PERSONAL' AND number_pattern='{yyy}{mm}{seq:02}'"))


# _MIGRATIONS[i] upgrades version i+1 → i+2
_MIGRATIONS = [_v1_to_v2]


def get_version(engine: Engine) -> int:
    with engine.connect() as c:
        return int(c.execute(text("PRAGMA user_version")).scalar() or 0)


def migrate(engine: Engine) -> int:
    version = get_version(engine)
    if version == 0:
        Base.metadata.create_all(engine)
        version = SCHEMA_VERSION
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS[version - 1]
        log.info("migrating schema %s → %s", version, version + 1)
        with engine.begin() as c:
            step(c)
        version += 1
    with engine.begin() as c:
        c.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
    return version
