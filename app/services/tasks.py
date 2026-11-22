"""Task storage + automatic tasks from document/project events (doc 06 §6.5)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import tasks as rules
from app.core.clauses import render_clause
from app.db.models import Document, Project, Task
from app.db.repo import get_setting


def _rules(s: Session) -> dict:
    return {k: int(get_setting(s, f"task_{k}", v)) for k, v in rules.DEFAULT_RULES.items()}


def add_auto(s: Session, spec: rules.TaskSpec, key: str, document: Document | None = None,
             project: Project | None = None, party_id: int | None = None, action: dict | None = None) -> Task | None:
    """Create an automatic task unless one with the same (rule, object) key already exists."""
    auto_key = f"{spec.rule}:{key}"
    if s.scalar(select(Task.id).where(Task.auto_key == auto_key)):
        return None
    t = Task(title=spec.title, due_date=spec.due, source=f"auto:{spec.rule}", auto_key=auto_key,
             document_id=document.id if document else None,
             project_id=(project.id if project else (document.project_id if document else None)),
             party_id=party_id or (document.party_id if document else (project.party_id if project else None)),
             action=action)
    s.add(t)
    return t


def _customer(doc: Document) -> str:
    return (doc.party.short_name or doc.party.name) if doc.party else ""


def after_issue(s: Session, doc: Document, draft) -> None:
    validity = None
    for c in draft.clauses:
        if c.code == "OTH_VALIDITY":
            v = (c.values or {}).get("validity_days") or (c.variables or {}).get("validity_days", {}).get("default")
            try:
                validity = int(v)
            except (TypeError, ValueError):
                validity = None
    code = doc.letter_type.code if doc.letter_type else None
    for spec in rules.on_issue(doc.kind, doc.date_greg, _customer(doc), code, doc.fields_json or {},
                               validity, _rules(s)):
        add_auto(s, spec, f"doc{doc.id}", document=doc)


def after_status(s: Session, doc: Document, status: str) -> None:
    today = date.today()
    if status in ("accepted", "rejected", "void"):
        close_auto(s, doc.id, "proforma_followup")
    if status == "accepted":
        from app.services.documents import draft_from_document
        d = draft_from_document(s, doc)
        adv = ""
        for c in d.clauses:
            if c.code in ("PAY_ADV", "PAY_SPLIT_CARDS_INSTALL"):
                from app.core.clauses import clause_values
                adv = clause_values(d, c).get("advance_amount", "")
        for spec in rules.on_accepted(doc.kind, today, _customer(doc), adv, _rules(s)):
            add_auto(s, spec, f"doc{doc.id}", document=doc)
    if status == "paid":
        close_auto(s, doc.id, "payment_followup")
        for spec in rules.on_paid(doc.kind, today, _customer(doc)):
            add_auto(s, spec, f"doc{doc.id}", document=doc)


def close_auto(s: Session, doc_id: int, rule: str) -> None:
    t = s.scalar(select(Task).where(Task.auto_key == f"{rule}:doc{doc_id}", Task.status == "open"))
    if t:
        t.status = "done"
        t.done_at = datetime.now()


def after_handover(s: Session, project: Project) -> Task | None:
    if not project.handover_date:
        return None
    specs = rules.on_handover(project.handover_date, project.retention_percent, project.retention_months,
                              (project.party.short_name or project.party.name), project.title)
    for spec in specs:
        existing = s.scalar(select(Task).where(Task.auto_key == f"{spec.rule}:project{project.id}"))
        if existing and existing.status == "open":
            existing.due_date = spec.due   # handover date edited → move the due date
            existing.title = spec.title
            return existing
        return add_auto(s, spec, f"project{project.id}", project=project,
                        action={"open": "letter_wizard", "letter_type": "PAY_RETENTION_RELEASE",
                                "project_id": project.id, "party_id": project.party_id})
    return None


def complete(s: Session, task_id: int, done: bool = True) -> Task:
    t = s.get(Task, task_id)
    t.status = "done" if done else "open"
    t.done_at = datetime.now() if done else None
    s.commit()
    return t


def overdue_count(s: Session) -> int:
    from sqlalchemy import func
    return s.scalar(select(func.count(Task.id)).where(Task.status == "open", Task.due_date < date.today(),
                                                      Task.is_archived.is_(False))) or 0
