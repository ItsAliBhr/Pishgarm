"""Simple schema versioning with PRAGMA user_version (doc 07 §7.2)."""
from __future__ import annotations

from sqlalchemy import Engine, text

from app.db.models import Base

SCHEMA_VERSION = 1

# Each entry upgrades from version (index) to version (index + 1). Version 0 → 1 is create_all.
_MIGRATIONS: list = []


def get_version(engine: Engine) -> int:
    with engine.connect() as c:
        return int(c.execute(text("PRAGMA user_version")).scalar() or 0)


def migrate(engine: Engine) -> int:
    version = get_version(engine)
    if version == 0:
        Base.metadata.create_all(engine)
        version = 1
    for step in _MIGRATIONS[version - 1:]:
        with engine.begin() as c:
            step(c)
        version += 1
    with engine.begin() as c:
        c.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
    return version
