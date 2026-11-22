"""Projects, open-receivables report and the legacy archive index."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.normalize import normalize_text
from app.db.models import ArchiveFile, Document, Party, Project
from app.services import tasks as task_service

PROJECT_STATUS_FA = {"open": "باز", "waiting_payment": "در انتظار پرداخت", "retention": "سپرده",
                     "closed": "بسته", "cancelled": "لغو شده"}


def save_project(s: Session, project: Project) -> Project:
    if project.id is None:
        s.add(project)
    s.flush()
    if project.handover_date:
        task_service.after_handover(s, project)
        if project.status in ("open", "waiting_payment") and (project.retention_percent or 0) > 0:
            pass
    s.commit()
    return project


def project_sums(s: Session, project_id: int) -> dict:
    docs = s.scalars(select(Document).where(Document.project_id == project_id, Document.is_archived.is_(False),
                                            Document.status.not_in(["draft", "void"]))).all()
    out = {"proforma": 0, "invoice": 0, "paid": 0}
    for d in docs:
        if d.kind == "proforma":
            out["proforma"] += d.payable or 0
        elif d.kind in ("invoice", "statement"):
            out["invoice"] += d.payable or 0
            if d.status == "paid":
                out["paid"] += d.payable or 0
    return out


@dataclass
class Receivable:
    party: str
    kind: str        # "invoice" / "retention"
    title: str
    amount: int
    document_id: int | None
    project_id: int | None
    date: object


def receivables(s: Session) -> list[Receivable]:
    """Unpaid invoices/statements + unreleased retention deposits, grouped by customer."""
    out = []
    docs = s.scalars(select(Document).where(Document.kind.in_(["invoice", "statement"]),
                                            Document.status.in_(["issued", "sent", "accepted"]),
                                            Document.is_archived.is_(False))).all()
    for d in docs:
        out.append(Receivable(d.party.short_name or d.party.name if d.party else "",
                              "invoice", f"{'فاکتور' if d.kind == 'invoice' else 'صورت‌وضعیت'} {d.number}",
                              d.payable or 0, d.id, d.project_id, d.date_greg))
    for p in s.scalars(select(Project).where(Project.status == "retention", Project.is_archived.is_(False))):
        sums = project_sums(s, p.id)
        base = p.contract_amount or sums["invoice"]
        amount = int(base * float(p.retention_percent or 0) / 100)
        out.append(Receivable(p.party.short_name or p.party.name, "retention",
                              f"سپرده‌ی {p.retention_percent:g}٪ {p.title}", amount, None, p.id, p.handover_date))
    out.sort(key=lambda r: (r.party, r.kind))
    return out


# ------------------------------------------------------------------ legacy archive (phase 2)

KIND_GUESS = [("پیش", "proforma"), ("پيش", "proforma"), ("فاکتور", "invoice"), ("صورت وضعیت", "statement"),
              ("صورت‌وضعیت", "statement"), ("نامه", "letter")]


def _guess_kind(name: str) -> str:
    n = normalize_text(name)
    for word, kind in KIND_GUESS:
        if word in n:
            return kind
    return ""


def _guess_date(name: str) -> str:
    m = re.search(r"(14\d{2})[/\-_.]?(\d{2})[/\-_.]?(\d{2})", normalize_text(name))
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else ""


def _match_party(folder_name: str, parties: list[Party]) -> Party | None:
    f = normalize_text(folder_name)
    for p in parties:
        if p.archive_folder and normalize_text(p.archive_folder) == f:
            return p
    for p in parties:
        for cand in (p.archive_folder, p.short_name):
            if cand and (normalize_text(cand) in f or f in normalize_text(cand)):
                return p
    return None


def scan_legacy_archive(s: Session, root: Path) -> int:
    """Index the old «بابا» folder: files under each customer folder (by folder name). Read-only."""
    root = Path(root)
    parties = s.scalars(select(Party).where(Party.is_archived.is_(False))).all()
    for row in s.scalars(select(ArchiveFile)).all():
        s.delete(row)
    n = 0
    for dirpath, _dirs, files in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        top = rel.parts[0] if rel.parts else ""
        party = _match_party(top, parties) if top else None
        for fn in files:
            if fn.startswith("~$") or Path(fn).suffix.lower() not in (".docx", ".doc", ".pdf", ".xlsx", ".xls",
                                                                     ".jpg", ".jpeg", ".png"):
                continue
            s.add(ArchiveFile(party_id=party.id if party else None, path=str(Path(dirpath) / fn),
                              kind_guess=_guess_kind(fn), date_guess=_guess_date(fn), title=Path(fn).stem))
            n += 1
    s.commit()
    return n
