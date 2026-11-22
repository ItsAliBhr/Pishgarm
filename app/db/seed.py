"""Load seed/*.json on first run (doc 03 §3.5). Idempotent: records are keyed by `code`;
existing rows are never overwritten, so the owner's edits survive re-runs and upgrades."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import paths
from app.core.normalize import normalize_text
from app.core.validators import clean_iban, iban_error
from app.db.models import (Account, Clause, Contact, Issuer, Item, LetterType, Party, Setting,
                           Unit)

log = logging.getLogger(__name__)

STAMP_FILE = "stamp_company.jpg"
SIGNATURE_FILE = "signature_bahrami.png"


def _read(seed_dir: Path, name: str):
    with open(seed_dir / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _n(value):
    """Normalise strings recursively (ي/ك, digits) as doc 03 requires before storing."""
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [_n(v) for v in value]
    if isinstance(value, dict):
        return {k: _n(v) for k, v in value.items()}
    return value


def _existing_codes(s: Session, model) -> set[str]:
    return set(s.scalars(select(model.code)))


def _pick(row: dict, model, skip=()) -> dict:
    cols = {c.key for c in model.__table__.columns} - {"id", "created_at", "updated_at"}
    return {k: _n(v) for k, v in row.items() if k in cols and k not in skip}


def _copy_assets() -> dict[str, str]:
    """Copy stamp/signature images to the writable data folder; return their paths."""
    out = {}
    for name in (STAMP_FILE, SIGNATURE_FILE):
        src = paths.bundled_assets_dir() / name
        dst = paths.user_assets_dir() / name
        if src.exists():
            if not dst.exists():
                shutil.copy2(src, dst)
            out[name] = str(dst)
    return out


def load_seed(s: Session, seed_dir: Path | None = None) -> dict[str, int]:
    """Insert every seed record whose code is not yet in the database. Returns counts inserted."""
    seed_dir = seed_dir or paths.seed_dir()
    added: dict[str, int] = {}

    # units
    have = set(s.scalars(select(Unit.name)))
    units = [u for u in _read(seed_dir, "units") if normalize_text(u) not in have]
    for i, u in enumerate(_read(seed_dir, "units")):
        if normalize_text(u) not in have:
            s.add(Unit(name=normalize_text(u), sort_order=i))
    added["units"] = len(units)

    # issuers (+ stamp / signature)
    assets = _copy_assets()
    have = _existing_codes(s, Issuer)
    n = 0
    for row in _read(seed_dir, "issuers"):
        if row["code"] in have:
            continue
        issuer = Issuer(**_pick(row, Issuer))
        issuer.signature_image = assets.get(SIGNATURE_FILE)
        if row["kind"] == "company":
            issuer.stamp_image = assets.get(STAMP_FILE)
        s.add(issuer)
        n += 1
    added["issuers"] = n
    s.flush()
    issuers = {i.code: i for i in s.scalars(select(Issuer))}

    # accounts
    have = _existing_codes(s, Account)
    n = 0
    for row in _read(seed_dir, "accounts"):
        if row["code"] in have:
            continue
        acc = Account(**_pick(row, Account, skip=("iban",)))
        acc.iban = clean_iban(row.get("iban", ""))
        err = iban_error(acc.iban)
        if err:
            log.warning("seed account %s has invalid IBAN: %s", row["code"], err)
            acc.active = False
        acc.issuer = issuers.get(row.get("issuer_code"))
        s.add(acc)
        n += 1
    added["accounts"] = n

    # parties + contacts
    have = _existing_codes(s, Party)
    n = 0
    for row in _read(seed_dir, "parties"):
        if row["code"] in have:
            continue
        party = Party(**_pick(row, Party))
        for i, c in enumerate(row.get("contacts", [])):
            party.contacts.append(Contact(
                title_prefix=normalize_text(c.get("title_prefix", "جناب آقای")),
                honorific=normalize_text(c.get("title", "")),
                name=normalize_text(c.get("name", "")),
                position=normalize_text(c.get("position", "")),
                is_default=(i == 0),
            ))
        s.add(party)
        n += 1
    added["parties"] = n

    # letter types, clauses
    for name, model in (("letter_types", LetterType), ("clauses", Clause)):
        have = _existing_codes(s, model)
        n = 0
        for i, row in enumerate(_read(seed_dir, name)):
            if row["code"] in have:
                continue
            obj = model(**_pick(row, model))
            if model is Clause:
                obj.sort_order = i
            s.add(obj)
            n += 1
        added[name] = n

    # items
    have = _existing_codes(s, Item)
    n = 0
    for row in _read(seed_dir, "items"):
        if row["code"] in have:
            continue
        item = Item(**_pick(row, Item))
        item.last_unit_price = row.get("last_unit_price_rial")
        s.add(item)
        n += 1
    added["items"] = n

    # settings
    have = set(s.scalars(select(Setting.key)))
    settings = _read(seed_dir, "settings")
    n = 0
    for key, value in settings.items():
        if key not in have:
            s.add(Setting(key=key, value_json=value))
            n += 1
    for key, value in DEFAULT_SETTINGS.items():
        if key not in have and key not in settings:
            s.add(Setting(key=key, value_json=value))
            n += 1
    added["settings"] = n

    s.commit()
    if any(added.values()):
        log.info("seed loaded: %s", added)
    return added


# Settings for the open questions in docs/08 — documented defaults, changeable in Settings.
DEFAULT_SETTINGS: dict[str, object] = {
    "numbering_shared_letter_invoice": False,      # شماره‌گذاری نامه و فاکتور مشترک؟ پیش‌فرض: جدا
    "numbering_separate_per_issuer": True,         # شخصی و شرکتی جدا؟ پیش‌فرض: بله
    "retention_months_default": 3,                 # مدت نگهداری سپرده‌ی حسن انجام کار
    "retention_percent_default": 10,
    "personal_invoice_show_national_id": False,    # کد ملی فروشنده در فاکتور شخصی؟ پیش‌فرض: خیر
    "markup_round_step_rial": 1,
    "output_digits_persian": False,
    "ui_font_size_pt": 11,
    "backup_keep_count": 30,
    "proforma_validity_workdays": 3,
}
