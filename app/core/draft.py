"""In-memory document being edited (pure data, no DB / Qt). The service layer converts it
to and from the database; context.py turns it into a template context."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.core import money

KIND_FA = {"letter": "نامه", "proforma": "پیش‌فاکتور", "invoice": "فاکتور",
           "statement": "صورت‌وضعیت", "attachment_list": "لیست اقلام"}
TITLE_BY_KIND = {"proforma": "پیش‌فاکتور فروش و خدمات", "invoice": "فاکتور فروش و خدمات",
                 "statement": "صورت وضعیت", "attachment_list": "لیست اقلام", "letter": ""}
STATUS_FA = {"draft": "پیش‌نویس", "issued": "صادر شد", "sent": "ارسال شد", "accepted": "تأیید شد",
             "rejected": "رد شد", "paid": "پرداخت شد", "void": "باطل"}
CLAUSE_GROUPS = ["payment", "delivery", "tax", "site", "other", "note"]
GROUP_FA = {"payment": "شرایط پرداخت", "delivery": "شرایط حمل و زمان", "tax": "مالیات و بیمه",
            "site": "تعهدات کارفرما", "other": "سایر", "note": "توضیحات"}


@dataclass
class Line:
    description: str = ""
    unit: str = "عدد"
    qty: Decimal = Decimal(1)
    unit_price: int = 0
    purchase_price: int | None = None
    markup_percent: Decimal | None = None
    buyer_supplied: bool = False
    emphasis: bool = False
    is_service: bool = False      # installation / service row (split-payment clause, «نصب» rule)
    item_id: int | None = None
    category: str = ""
    note: str = ""

    @property
    def total(self) -> int:
        return money.line_total(self.qty, self.unit_price)


@dataclass
class ClauseSel:
    group: str
    template: str
    values: dict = field(default_factory=dict)
    code: str | None = None          # None = ad-hoc clause
    clause_id: int | None = None
    variables: dict = field(default_factory=dict)   # {name: {"type":..., "default":...}}
    requires: dict = field(default_factory=dict)
    excludes: list = field(default_factory=list)
    applies_to: list = field(default_factory=list)


@dataclass
class AccountInfo:
    id: int | None
    iban: str
    bank: str
    holder: str
    code: str = ""


@dataclass
class Draft:
    kind: str
    issuer: dict                      # issuer row as dict
    party: dict = field(default_factory=dict)     # buyer / addressee party (editable copy)
    contact: dict | None = None
    project: dict | None = None
    date: date = field(default_factory=date.today)
    number: str = ""
    title: str = ""
    # letter
    letter_type: dict | None = None
    fields: dict = field(default_factory=dict)
    subject: str = ""
    salutation: str = "با سلام و احترام؛"
    closing: str = ""
    attachment_text: str = "ندارد"
    header_line: str = "باسمه تعالی"
    addressee_lines: list[str] | None = None      # None = built automatically
    addressee_format: int = 0
    body_override: list[str] | None = None
    # money
    lines: list[Line] = field(default_factory=list)
    vat_enabled: bool = False
    vat_percent: Decimal = Decimal(10)
    input_currency: str = "million_toman"
    # clauses / accounts
    clauses: list[ClauseSel] = field(default_factory=list)
    accounts: list[AccountInfo] = field(default_factory=list)
    show_stamp: bool = False
    show_signature: bool = True
    tax_serial: str = ""
    # attachment list
    list_title: str = ""
    list_subtitle: str = ""
    # misc
    parent_number: str = ""
    show_seller_national_id: bool = False

    @property
    def totals(self) -> money.Totals:
        return money.compute_totals((l.total for l in self.lines),
                                    self.vat_enabled, self.vat_percent)

    @property
    def is_money_doc(self) -> bool:
        return self.kind in ("proforma", "invoice", "statement")

    @property
    def doc_kind_for_clauses(self) -> str:
        return "invoice" if self.kind == "statement" else self.kind
