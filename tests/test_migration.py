import sqlite3

from sqlalchemy import select

from app.db.models import Issuer


def test_v1_database_upgrades(tmp_path):
    """A database made by v0.1.0 (schema 1) opens and gains the v2 columns."""
    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.executescript("""
        CREATE TABLE document (id INTEGER PRIMARY KEY, kind VARCHAR);
        CREATE TABLE task (id INTEGER PRIMARY KEY, title VARCHAR);
        CREATE TABLE issuer (id INTEGER PRIMARY KEY, created_at DATETIME, updated_at DATETIME,
            is_archived BOOLEAN NOT NULL DEFAULT 0, code VARCHAR UNIQUE, kind VARCHAR, title VARCHAR,
            name VARCHAR, signer_name VARCHAR, signer_title VARCHAR, national_id VARCHAR,
            economic_code VARCHAR, registration_no VARCHAR, phone VARCHAR, mobile VARCHAR, fax VARCHAR,
            address TEXT, postal_code VARCHAR, vat_enabled_by_default BOOLEAN,
            default_vat_percent NUMERIC(5,2), show_stamp_by_default BOOLEAN, stamp_image VARCHAR,
            signature_image VARCHAR, letter_template VARCHAR, proforma_template VARCHAR,
            invoice_template VARCHAR, statement_template VARCHAR, number_pattern VARCHAR,
            number_scope VARCHAR, default_account_codes JSON, notes TEXT);
        INSERT INTO issuer (code, kind, number_pattern, is_archived) VALUES ('PERSONAL','personal','{yyy}{mm}{seq:02}',0);
        PRAGMA user_version = 1;
    """)
    con.close()
    from app.db.session import open_database
    engine, S = open_database(db_file)
    with S() as s:
        p = s.scalar(select(Issuer).where(Issuer.code == "PERSONAL"))
        assert p.number_pattern == "{yyy}{m}{seq:02}"
    cols = {r[1] for r in sqlite3.connect(db_file).execute("PRAGMA table_info(document)")}
    assert {"version", "attachments", "issued_at"} <= cols
    engine.dispose()
