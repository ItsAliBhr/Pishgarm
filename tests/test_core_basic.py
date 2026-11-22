from app.core.normalize import normalize_text
from app.core.validators import (company_id_error, format_iban, iban_error, national_code_error,
                                 postal_code_error)


def test_normalize():
    assert normalize_text(" علي كاظمي ۱۲۳٤ ") == "علی کاظمی 1234"


def test_iban_valid_and_formatted():
    assert iban_error("IR740190000000118420332008") is None
    assert format_iban("IR740190000000118420332008") == "IR74 0190 0000 0011 8420 3320 08"
    assert iban_error("۷۴۰۱۹۰۰۰۰۰۰۰۱۱۸۴۲۰۳۳۲۰۰۸") is None  # Persian digits, no IR


def test_iban_missing_digit_message():
    # the archive's most common mistake (doc 08, phase 1 acceptance 4)
    assert iban_error("IR80180000000344646318580") == "این شبا 23 رقم دارد؛ باید ۲۴ رقم باشد."


def test_iban_bad_checksum():
    assert "رقم کنترل" in iban_error("IR740190000000118420332009")


def test_national_codes():
    assert national_code_error("5419551322") is None  # from seed/issuers.json
    assert national_code_error("5419551323") is not None
    assert company_id_error("14012128802") is None    # company national id
    assert company_id_error("14012128803") is not None
    assert postal_code_error("8177787156") is None
    assert postal_code_error("81777") is not None
