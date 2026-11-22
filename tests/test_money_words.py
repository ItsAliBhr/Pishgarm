import json
from decimal import Decimal

import pytest

from app import paths
from app.core import money
from app.core.num2words_fa import num_to_words, rial_words


@pytest.mark.parametrize("n,words", [
    (7_700_000_000, "هفت میلیارد و هفتصد میلیون"),
    (22_700_000_000, "بیست و دو میلیارد و هفتصد میلیون"),
    (1000, "هزار"),
    (1_000_000, "یک میلیون"),
    (1_001_000, "یک میلیون و هزار"),
    (18_500_000_000, "هجده میلیارد و پانصد میلیون"),
    (25_025_000_000, "بیست و پنج میلیارد و بیست و پنج میلیون"),
    (81_700, "هشتاد و یک هزار و هفتصد"),
    (0, "صفر"),
    (115, "صد و پانزده"),
])
def test_words(n, words):
    assert num_to_words(n) == words


def test_words_match_all_test_contexts():
    for f in (paths.bundled_templates_dir() / "test_contexts").glob("proforma_*.json"):
        t = json.loads(f.read_text(encoding="utf-8"))["totals"]
        for key in ("subtotal", "payable"):
            n = int(t[key].replace(",", ""))
            assert rial_words(n) == t[f"{key}_words"], f.name


def test_input_units():
    assert money.to_rial("2020", "million_toman") == 20_200_000_000
    assert money.to_rial("۱٫۵", "million_toman") == 15_000_000
    assert money.to_rial("350,000", "toman") == 3_500_000
    assert money.to_rial("81،700", "rial") == 81_700


def test_line_and_totals():
    assert money.line_total(Decimal("45000"), 81_700) == 3_676_500_000
    assert money.line_total(Decimal("2.5"), 3) == 8  # half-up on the line only
    t = money.compute_totals([7_000_000_000], True, 10)
    assert (t.subtotal, t.vat, t.payable) == (7_000_000_000, 700_000_000, 7_700_000_000)


def test_markup():
    assert money.markup_price(1_000_000, 25) == 1_250_000
    assert money.markup_price(1_000_001, 25, step=100_000) == 1_300_000
    assert money.fmt_decimal(Decimal("2.50")) == "2.5" and money.fmt_decimal(Decimal("40655")) == "40,655"
