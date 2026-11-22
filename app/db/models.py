"""SQLAlchemy models — the full schema of docs/03. Money columns are integer Rial."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Common:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(),
                                                 onupdate=func.current_timestamp())
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------- master data (§3.1)

class Issuer(Common, Base):
    __tablename__ = "issuer"
    code: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)  # personal / company
    title: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, default="")
    signer_name: Mapped[str] = mapped_column(String, default="")
    signer_title: Mapped[str] = mapped_column(String, default="")
    national_id: Mapped[str] = mapped_column(String, default="")
    economic_code: Mapped[str] = mapped_column(String, default="")
    registration_no: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    mobile: Mapped[str] = mapped_column(String, default="")
    fax: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    postal_code: Mapped[str] = mapped_column(String, default="")
    vat_enabled_by_default: Mapped[bool] = mapped_column(Boolean, default=False)
    default_vat_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    show_stamp_by_default: Mapped[bool] = mapped_column(Boolean, default=False)
    stamp_image: Mapped[str | None] = mapped_column(String, nullable=True)
    signature_image: Mapped[str | None] = mapped_column(String, nullable=True)
    letter_template: Mapped[str] = mapped_column(String, default="")
    proforma_template: Mapped[str] = mapped_column(String, default="")
    invoice_template: Mapped[str] = mapped_column(String, default="")
    statement_template: Mapped[str] = mapped_column(String, default="")
    number_pattern: Mapped[str] = mapped_column(String, default="")
    number_scope: Mapped[str] = mapped_column(String, default="per_year")
    default_account_codes: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")

    accounts: Mapped[list["Account"]] = relationship(back_populates="issuer")


class Account(Common, Base):
    __tablename__ = "account"
    code: Mapped[str] = mapped_column(String, unique=True)
    issuer_id: Mapped[int | None] = mapped_column(ForeignKey("issuer.id"), nullable=True)
    bank: Mapped[str] = mapped_column(String, default="")
    branch: Mapped[str] = mapped_column(String, default="")
    holder: Mapped[str] = mapped_column(String, default="")
    iban: Mapped[str] = mapped_column(String(26), default="")
    account_no: Mapped[str] = mapped_column(String, default="")
    card_no: Mapped[str] = mapped_column(String, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    issuer: Mapped[Issuer | None] = relationship(back_populates="accounts")


class Party(Common, Base):
    __tablename__ = "party"
    code: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String, default="company")  # company/person/bank/government
    name: Mapped[str] = mapped_column(String)
    short_name: Mapped[str] = mapped_column(String, default="")
    archive_folder: Mapped[str] = mapped_column(String, default="")
    national_id: Mapped[str] = mapped_column(String, default="")
    economic_code: Mapped[str] = mapped_column(String, default="")
    registration_no: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    postal_code: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    fax: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    contacts: Mapped[list["Contact"]] = relationship(back_populates="party", cascade="all, delete-orphan",
                                                     order_by="Contact.id")


class Contact(Common, Base):
    __tablename__ = "contact"
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    title_prefix: Mapped[str] = mapped_column(String, default="جناب آقای")
    honorific: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, default="")
    position: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    party: Mapped[Party] = relationship(back_populates="contacts")


class LetterType(Common, Base):
    __tablename__ = "letter_type"
    code: Mapped[str] = mapped_column(String, unique=True)
    category: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String)
    subject_line: Mapped[str] = mapped_column(String, default="")
    body: Mapped[list] = mapped_column(JSON, default=list)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    closing: Mapped[str] = mapped_column(String, default="")
    with_items_table: Mapped[bool] = mapped_column(Boolean, default=False)
    with_clauses: Mapped[bool] = mapped_column(Boolean, default=False)
    with_account: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(Text, default="")


class Clause(Common, Base):
    __tablename__ = "clause"
    code: Mapped[str] = mapped_column(String, unique=True)
    group: Mapped[str] = mapped_column(String)  # payment/delivery/tax/site/other/note
    text: Mapped[str] = mapped_column(Text)
    variables: Mapped[dict] = mapped_column(JSON, default=dict)
    applies_to: Mapped[list] = mapped_column(JSON, default=list)
    default_for_issuers: Mapped[list] = mapped_column(JSON, default=list)
    requires: Mapped[dict] = mapped_column(JSON, default=dict)
    excludes: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(Text, default="")


class PartyClauseDefault(Common, Base):
    __tablename__ = "party_clause_default"
    __table_args__ = (UniqueConstraint("party_id", "clause_id", "doc_kind"),)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    clause_id: Mapped[int] = mapped_column(ForeignKey("clause.id"))
    doc_kind: Mapped[str] = mapped_column(String)
    use_count: Mapped[int] = mapped_column(Integer, default=0)


class Item(Common, Base):
    __tablename__ = "item"
    code: Mapped[str] = mapped_column(String, unique=True)
    category: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String, default="")
    last_unit_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_price_source: Mapped[str] = mapped_column(String, default="")
    last_purchase_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # hidden
    buyer_supplied_by_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Unit(Common, Base):
    __tablename__ = "unit"
    name: Mapped[str] = mapped_column(String, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- projects & documents (§3.2)

class Project(Common, Base):
    __tablename__ = "project"
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"))
    title: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="open")
    contract_no: Mapped[str] = mapped_column(String, default="")
    contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=10)
    retention_months: Mapped[int] = mapped_column(Integer, default=3)
    handover_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_name: Mapped[str] = mapped_column(String, default="")  # internal only
    supplier_notes: Mapped[str] = mapped_column(Text, default="")   # internal only
    folder_path: Mapped[str] = mapped_column(String, default="")

    party: Mapped[Party] = relationship()


class Document(Common, Base):
    __tablename__ = "document"
    kind: Mapped[str] = mapped_column(String)  # letter/proforma/invoice/statement/attachment_list
    issuer_id: Mapped[int] = mapped_column(ForeignKey("issuer.id"))
    party_id: Mapped[int | None] = mapped_column(ForeignKey("party.id"), nullable=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contact.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    letter_type_id: Mapped[int | None] = mapped_column(ForeignKey("letter_type.id"), nullable=True)
    number: Mapped[str] = mapped_column(String, default="")
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seq_group: Mapped[str] = mapped_column(String, default="")
    seq_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seq_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_greg: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_jalali: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    subject: Mapped[str] = mapped_column(String, default="")
    salutation: Mapped[str] = mapped_column(String, default="")
    closing: Mapped[str] = mapped_column(String, default="")
    attachment_text: Mapped[str] = mapped_column(String, default="")
    fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    body_override: Mapped[list | None] = mapped_column(JSON, nullable=True)
    vat_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    vat_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    insurance_note: Mapped[str] = mapped_column(String, default="")
    input_currency: Mapped[str] = mapped_column(String, default="million_toman")
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    vat_amount: Mapped[int] = mapped_column(Integer, default=0)
    payable: Mapped[int] = mapped_column(Integer, default=0)
    show_stamp: Mapped[bool] = mapped_column(Boolean, default=False)
    show_signature: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String, default="draft")
    parent_document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"), nullable=True)
    tax_serial: Mapped[str] = mapped_column(String, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    header_line: Mapped[str] = mapped_column(String, default="")
    addressee_lines: Mapped[list | None] = mapped_column(JSON, nullable=True)
    addressee_format: Mapped[int] = mapped_column(Integer, default=0)
    list_title: Mapped[str] = mapped_column(String, default="")
    list_subtitle: Mapped[str] = mapped_column(String, default="")
    attachments: Mapped[list] = mapped_column(JSON, default=list)   # wizard step 6 config
    notes: Mapped[str] = mapped_column(Text, default="")

    issuer: Mapped["Issuer"] = relationship(foreign_keys=[issuer_id])
    party: Mapped["Party | None"] = relationship(foreign_keys=[party_id])
    contact: Mapped["Contact | None"] = relationship(foreign_keys=[contact_id])
    project: Mapped["Project | None"] = relationship(foreign_keys=[project_id])
    letter_type: Mapped["LetterType | None"] = relationship(foreign_keys=[letter_type_id])

    lines: Mapped[list["DocumentLine"]] = relationship(cascade="all, delete-orphan",
                                                       order_by="DocumentLine.idx")
    clauses: Mapped[list["DocumentClause"]] = relationship(cascade="all, delete-orphan",
                                                           order_by="DocumentClause.sort_order")
    accounts: Mapped[list["DocumentAccount"]] = relationship(cascade="all, delete-orphan",
                                                             order_by="DocumentAccount.sort_order")
    files: Mapped[list["DocumentFile"]] = relationship(cascade="all, delete-orphan")


class DocumentLine(Common, Base):
    __tablename__ = "document_line"
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    idx: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("item.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String, default="")
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=1)
    unit_price: Mapped[int] = mapped_column(Integer, default=0)
    purchase_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # hidden
    markup_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    buyer_supplied: Mapped[bool] = mapped_column(Boolean, default=False)
    emphasis: Mapped[bool] = mapped_column(Boolean, default=False)
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(Text, default="")


class DocumentClause(Common, Base):
    __tablename__ = "document_clause"
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    clause_id: Mapped[int | None] = mapped_column(ForeignKey("clause.id"), nullable=True)
    group: Mapped[str] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    rendered_text: Mapped[str] = mapped_column(Text, default="")
    variables_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DocumentAccount(Common, Base):
    __tablename__ = "document_account"
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class DocumentFile(Common, Base):
    __tablename__ = "document_file"
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    role: Mapped[str] = mapped_column(String)  # docx/pdf/merged_pdf/final/attachment_*
    path: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sha256: Mapped[str] = mapped_column(String, default="")


# ---------------------------------------------------------------- tasks (§3.3)

class Task(Common, Base):
    __tablename__ = "task"
    title: Mapped[str] = mapped_column(String)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"), nullable=True)
    party_id: Mapped[int | None] = mapped_column(ForeignKey("party.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    source: Mapped[str] = mapped_column(String, default="manual")
    notes: Mapped[str] = mapped_column(Text, default="")
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # (rule_code, document/project id) of an automatic task — never created twice (doc 06 §6.5)
    auto_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    action: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # e.g. open the letter wizard

    project: Mapped["Project | None"] = relationship()
    document: Mapped["Document | None"] = relationship()
    party: Mapped["Party | None"] = relationship()


# ---------------------------------------------------------------- settings & system (§3.4)

class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[object] = mapped_column(JSON)


class NumberCounter(Base):
    __tablename__ = "number_counter"
    __table_args__ = (UniqueConstraint("issuer_id", "group", "period_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issuer_id: Mapped[int | None] = mapped_column(ForeignKey("issuer.id"), nullable=True)  # None = shared
    group: Mapped[str] = mapped_column(String)  # letter / invoice_family / all
    period_key: Mapped[str] = mapped_column(String)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    action: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")


class ArchiveFile(Common, Base):
    __tablename__ = "archive_file"
    party_id: Mapped[int | None] = mapped_column(ForeignKey("party.id"), nullable=True)
    path: Mapped[str] = mapped_column(String)
    kind_guess: Mapped[str] = mapped_column(String, default="")
    date_guess: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
