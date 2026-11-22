"""Core rules: golden documents of phase 1 (doc 08) at the pure-logic level."""
from datetime import date
from decimal import Decimal

from app.core import jalali, numbering, tasks
from app.core.clauses import check, render_clause
from app.core.context import build_context
from app.core.draft import AccountInfo, ClauseSel, Draft, Line
from app.core.files import base_file_name, versioned_path
from app.core.letters import build_addressee, build_body, build_subject

COMPANY = {"code": "COMPANY", "kind": "company", "name": "شرکت پیشگرم سازان فولاد ایرانیان",
           "signer_name": "بهرامی", "national_id": "14012128802"}
PERSONAL = {"code": "PERSONAL", "kind": "personal", "name": "قربانعلی بهرامی", "signer_name": "بهرامی",
            "national_id": "5419551322"}
SADERAT = AccountInfo(1, "IR740190000000118420332008", "صادرات", "شرکت پیشگرم سازان فولاد ایرانیان")


def sel(code, group, template, **kw):
    return ClauseSel(group=group, template=template, code=code, **kw)


def test_golden_personal_fuel_system():
    d = Draft("proforma", PERSONAL, party={"name": "شرکت فولاد ناب تبریز"})
    d.lines = [Line("اقلام سیستم سوخت‌رسانی گازوئیل (۱۷ مشعل)", "مجموعه", Decimal(1), 20_200_000_000),
               Line("حضور کارشناس", "روز", Decimal(1), 2_500_000_000)]
    ctx = build_context(d)
    assert ctx["totals"]["payable"] == "22,700,000,000"
    assert ctx["totals"]["payable_words"] == "بیست و دو میلیارد و هفتصد میلیون ریال"
    assert ctx["totals"]["payable_label"] == "جمع کل"
    assert ctx["seller"]["national_id"] == ""   # personal invoice hides national id by default


def test_golden_company_tikmeh_dash():
    d = Draft("proforma", COMPANY, party={"name": "شرکت صنایع فولاد کاوه تیکمه داش"},
              vat_enabled=True, vat_percent=Decimal(10), show_stamp=True, accounts=[SADERAT])
    d.lines = [Line("مشعل 2000 کیلووات", "عدد", Decimal(2), 3_500_000_000)]
    d.clauses = [sel("PAY_TO_ACCOUNT", "payment",
                     "خواهشمند است مبلغ فوق به شماره شبای {iban} نزد بانک {bank} به نام {holder} واریز گردد."),
                 sel("TAX_NET_PLUS_VAT", "tax", "مبالغ به صورت خالص می‌باشد و مبلغ {vat_percent}% ارزش افزوده به مبلغ فوق اضافه می‌گردد.",
                     requires={"vat_enabled": True})]
    ctx = build_context(d)
    t = ctx["totals"]
    assert (t["subtotal"], t["vat"], t["payable"]) == ("7,000,000,000", "700,000,000", "7,700,000,000")
    assert ctx["show_stamp"] is True
    assert ctx["clauses"][-1].startswith("خواهشمند است") and "IR740190000000118420332008" in ctx["clauses"][-1]
    assert "10%" in ctx["clauses"][0]
    assert not check(d)


def test_golden_markup_hidden():
    d = Draft("proforma", COMPANY, vat_enabled=True, vat_percent=Decimal(10))
    purchases = [4_100_000_000, 3_300_000_000, 2_900_000_000, 2_700_000_000, 2_300_000_000,
                 1_700_000_000, 1_200_000_000]  # 7 Siemens cards = 18.2 B
    from app.core.money import markup_price
    d.lines = [Line(f"کارت زیمنس {i}", "عدد", Decimal(1), markup_price(p, 25), purchase_price=p,
                    markup_percent=Decimal(25)) for i, p in enumerate(purchases, 1)]
    ctx = build_context(d)
    assert ctx["totals"]["payable"] == "25,025,000,000"
    from app.core.context import all_output_text
    text = all_output_text(ctx)
    shown = {v for it in ctx["items"] for v in (it["unit_price"], it["total"])}
    assert not shown & {f"{p:,}" for p in purchases}
    assert "25%" not in text and "purchase" not in str(ctx)


def test_golden_warnings():
    d = Draft("proforma", PERSONAL, vat_enabled=True)
    d.lines = [Line("نصب و راه‌اندازی کارت‌ها", "سرویس", Decimal(1), 100)]
    d.clauses = [sel("OTH_NO_INSTALL", "other", "نصب و راه‌اندازی بر عهده‌ی فروشنده نمی‌باشد.",
                     excludes=["category:installation"]),
                 sel("TAX_NOT_CALCULATED", "tax", "مالیات … محاسبه نشده است.", requires={"vat_enabled": False})]
    msgs = [i.message for i in check(d)]
    assert any("نصب" in m for m in msgs)
    assert any("ارزش افزوده" in m for m in msgs)


def test_validity_in_invoice_and_account_missing():
    d = Draft("invoice", COMPANY)
    d.clauses = [sel("OTH_VALIDITY", "other", "مدت اعتبار این پیش‌فاکتور {validity_days} روز",
                     variables={"validity_days": {"default": 3}}),
                 sel("PAY_TO_ACCOUNT", "payment", "شبای {iban}")]
    issues = check(d)
    assert any(i.level == "warning" and "اعتبار" in i.message for i in issues)
    assert any(i.level == "error" and "حساب" in i.message for i in issues)


def test_advance_clause_amounts():
    d = Draft("proforma", COMPANY, vat_enabled=True, vat_percent=Decimal(10))
    d.lines = [Line("x", "عدد", Decimal(1), 7_750_000_000)]
    c = sel("PAY_ADV", "payment", "{advance_percent}% مبلغ کل معادل {advance_amount} ریال",
            variables={"advance_percent": {"default": 60}})
    rest = sel("PAY_REST_BEFORE_SHIP", "payment", "{rest_percent}% الباقی معادل {rest_amount} ریال")
    d.clauses = [c, rest]
    assert render_clause(d, c) == "60% مبلغ کل معادل 5,115,000,000 ریال"
    assert render_clause(d, rest) == "40% الباقی معادل 3,410,000,000 ریال"
    c.values = {"advance_percent": "150"}
    assert any(i.blocking for i in check(d))


def test_letter_retention_release():
    lt = {"subject_line": "درخواست آزادسازی سپرده‌ی حسن انجام کار",
          "body": ["به استحضار می‌رساند ... قرارداد {contract_no} با موضوع {project_title} ... ({retention_percent}% باقیمانده) صورت پذیرد."],
          "fields": [{"name": "contract_no", "type": "text", "required": False},
                     {"name": "project_title", "type": "text", "required": True},
                     {"name": "retention_percent", "type": "percent", "required": False}],
          "with_account": True}
    d = Draft("letter", COMPANY, party={"name": "شرکت صنعت تجارت پردیس آذربایجان"},
              contact={"title_prefix": "جناب آقای", "honorific": "دکتر", "name": "مطلب‌زاده", "position": "مدیرعامل"},
              letter_type=lt, fields={"project_title": "نسوزکاری کوره", "retention_percent": 10},
              accounts=[SADERAT])
    assert build_subject(d) == "درخواست آزادسازی سپرده‌ی حسن انجام کار"
    body = build_body(d)
    assert "قرارداد  با" not in body[0] and "(10% باقیمانده)" in body[0]
    assert "IR740190000000118420332008" in body[-1]
    lines = build_addressee("{company}\n{title_prefix} {contact_title} {contact_name}\n{position} محترم",
                            d.party, d.contact)
    assert lines == ["شرکت صنعت تجارت پردیس آذربایجان", "جناب آقای دکتر مطلب‌زاده", "مدیرعامل محترم"]


def test_numbering():
    assert numbering.format_number("{seq:03}/{yyyy}", 1, 1405, 9) == "001/1405"
    assert numbering.format_number("{yyy}{m}{seq:02}", 1, 1405, 9) == "405901"
    # archive numbers 401100 / 401101 / 401202 = year 401, month 1/1/2, seq 00/01/02
    assert numbering.format_number("{yyy}{m}{seq:02}", 2, 1401, 2) == "401202"
    assert numbering.format_number("{yyy}{mm}{seq:02}", 1, 1405, 9) == "4050901"
    assert numbering.counter_group("proforma") == numbering.counter_group("invoice") == "invoice_family"
    assert numbering.period_key("per_month", 1405, 9) == "1405-09"


def test_jalali_and_tasks():
    d = jalali.parse("1405/09/01")
    assert jalali.fmt(d) == "1405/09/01" and jalali.parse("۱۴۰۵/۹/۱") == d
    # proforma valid 3 workdays → due date skips Fridays
    due = tasks.on_issue("proforma", d, "x", validity_days=3)[0].due
    assert due.weekday() != 4 and sum(1 for k in range(1, (due - d).days + 1)
                                      if jalali.add_days(d, k).weekday() != 4) == 3
    w = tasks.on_issue("letter", d, "گل‌گهر", "PAY_WARNING", {"deadline_days": 10})[0]
    assert (w.due - d).days == 10 and w.rule == "warning_deadline"
    h = tasks.on_handover(d, 10, 3, "x", "y")[0]
    assert jalali.fmt(h.due) == "1405/12/01"


def test_files(tmp_path):
    name = base_file_name("proforma", "فولاد ناب", "014/1405", jalali.parse("1405/09/01"))
    assert name == "پیش‌فاکتور فولاد ناب 014-1405 14050901"
    p1, v1 = versioned_path(tmp_path, name, ".docx")
    p1.write_text("x")
    p2, v2 = versioned_path(tmp_path, name, ".docx")
    assert v1 == 1 and v2 == 2 and p2.name.endswith(" -v2.docx")


def test_versioned_path_long_folder(tmp_path):
    """Deep folders used to make « -v2» be cut off → endless loop (seen on Windows)."""
    deep = tmp_path.joinpath(*(["پوشه‌ی بسیار طولانی مشتری"] * 6))
    deep.mkdir(parents=True)
    base = "پیش‌فاکتور فولاد ناب تبریز سیستم سوخت‌رسانی 014-1405 14050901"
    seen = set()
    for _ in range(4):
        p, v = versioned_path(deep, base, ".docx")
        assert p not in seen
        seen.add(p)
        p.write_text("x")
    assert v == 4 and p.name.endswith(" -v4.docx")
