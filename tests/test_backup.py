import sqlite3

import jdatetime

from app import paths
from app.db import backup


def test_backup_and_prune(db, tmp_path):
    target = tmp_path / "backups"
    for d in range(1, 6):
        backup.backup_now(target, keep=3, today=jdatetime.date(1405, 9, d))
    files = sorted(p.name for p in target.glob("data-*.db"))
    assert files == ["data-1405-09-03.db", "data-1405-09-04.db", "data-1405-09-05.db"]
    con = sqlite3.connect(target / files[-1])
    assert con.execute("select count(*) from party").fetchone()[0] == 42
    con.close()


def test_backup_if_due_once_per_day(db, tmp_path):
    target = tmp_path / "b"
    assert backup.backup_if_due(target) is not None
    assert backup.backup_if_due(target) is None


def test_output_root_expands_userprofile(db, isolated_data_dir):
    from app.db.repo import output_root
    with db() as s:
        root = output_root(s)
    assert str(root).startswith(str(isolated_data_dir / "profile"))
    assert root.name == "اسناد پیشگرم"
