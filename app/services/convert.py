"""Rows ↔ plain dicts used by the pure core."""
from __future__ import annotations

from app.core import jalali
from app.core.draft import AccountInfo, ClauseSel
from app.db.models import Account, Clause, Contact, Issuer, LetterType, Party, Project


def issuer_dict(i: Issuer) -> dict:
    return {c.key: getattr(i, c.key) for c in Issuer.__table__.columns}


def party_dict(p: Party | None) -> dict:
    if p is None:
        return {}
    return {c.key: getattr(p, c.key) for c in Party.__table__.columns}


def contact_dict(c: Contact | None) -> dict | None:
    if c is None:
        return None
    return {k: getattr(c, k) for k in ("id", "title_prefix", "honorific", "name", "position", "phone")}


def project_dict(p: Project | None) -> dict | None:
    if p is None:
        return None
    d = {c.key: getattr(p, c.key) for c in Project.__table__.columns}
    d["contract_date_jalali"] = jalali.fmt(p.contract_date) if p.contract_date else ""
    return d


def letter_type_dict(t: LetterType | None) -> dict | None:
    if t is None:
        return None
    return {c.key: getattr(t, c.key) for c in LetterType.__table__.columns}


def account_info(a: Account) -> AccountInfo:
    return AccountInfo(a.id, a.iban, a.bank, a.holder, a.code)


def clause_sel(c: Clause, values: dict | None = None) -> ClauseSel:
    return ClauseSel(group=c.group, template=c.text, values=dict(values or {}), code=c.code,
                     clause_id=c.id, variables=dict(c.variables or {}), requires=dict(c.requires or {}),
                     excludes=list(c.excludes or []), applies_to=list(c.applies_to or []))
