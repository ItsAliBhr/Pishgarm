"""Items table of the wizard (doc 04 §4.2, step 4)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QStyledItemDelegate,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.core import money
from app.core.draft import Line
from app.ui.widgets import MoneyEdit, SearchCombo

COL_DESC, COL_QTY, COL_UNIT, COL_PRICE, COL_TOTAL, COL_BUYER, COL_EMPH, COL_SERVICE = range(8)
HEADERS = ["شرح کالا / خدمات", "تعداد", "واحد", "قیمت واحد", "جمع (ریال)", "تأمین خریدار", "پررنگ", "نصب/خدمات"]


class _DescDelegate(QStyledItemDelegate):
    """Free text with catalog suggestions while typing."""

    def __init__(self, editor_owner):
        super().__init__(editor_owner)
        self.owner = editor_owner

    def createEditor(self, parent, option, index):
        e = QLineEdit(parent)
        c = QCompleter(list(self.owner.catalog_by_desc), e)
        c.setFilterMode(Qt.MatchContains)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        e.setCompleter(c)
        return e


class MarkupDialog(QDialog):
    """Purchase price + markup % → selling price. Purchase price stays inside the program."""

    def __init__(self, line: Line, unit: str, step: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("مارک‌آپ")
        self.step = step
        f = QFormLayout(self)
        f.addRow(QLabel("قیمت خرید و درصد فقط در برنامه ذخیره می‌شوند و در سند چاپ نمی‌شوند.",
                        wordWrap=True, styleSheet="color:#666"))
        self.purchase = MoneyEdit(unit)
        self.purchase.setValue(line.purchase_price or 0, unit)
        self.pct = QDoubleSpinBox(decimals=2, maximum=1000)
        self.pct.setSuffix(" ٪")
        self.pct.setValue(float(line.markup_percent if line.markup_percent is not None else 25))
        self.result = QLabel(styleSheet="font-weight:bold")
        f.addRow("قیمت خرید واحد:", self.purchase)
        f.addRow("درصد سود:", self.pct)
        f.addRow("قیمت فروش واحد:", self.result)
        bb = QDialogButtonBox()
        bb.addButton("اعمال", QDialogButtonBox.AcceptRole)
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.purchase.valueChanged.connect(lambda _: self._update())
        self.pct.valueChanged.connect(lambda _: self._update())
        self._update()

    def price(self) -> int:
        return money.markup_price(self.purchase.value(), Decimal(str(self.pct.value())), self.step)

    def _update(self):
        self.result.setText(f"{money.fmt_int(self.price())} ریال")


class LinesEditor(QWidget):
    changed = Signal()

    def __init__(self, mode: str = "money", parent=None):
        """mode: money (proforma/invoice/statement) · letter (desc/qty/unit/amount) · list (attachment list)."""
        super().__init__(parent)
        self.mode = mode
        self.catalog: list = []           # [(id, description, unit, price, category, buyer_supplied, purchase)]
        self.catalog_by_desc: dict = {}
        self.units: list[str] = []
        self.markup_step = 1
        self._lines: list[Line] = []
        self._loading = False

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_DESC, QHeaderView.Stretch)
        for c in (COL_QTY, COL_UNIT, COL_PRICE, COL_TOTAL, COL_BUYER, COL_EMPH, COL_SERVICE):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setItemDelegateForColumn(COL_DESC, _DescDelegate(self))
        self.table.itemChanged.connect(self._on_item_changed)
        if mode == "list":
            for c in (COL_PRICE, COL_TOTAL, COL_SERVICE):
                self.table.setColumnHidden(c, True)
        if mode == "letter":
            for c in (COL_BUYER, COL_EMPH, COL_SERVICE):
                self.table.setColumnHidden(c, True)

        self.unit_combo = QComboBox()
        for k, label in money.UNIT_LABELS.items():
            self.unit_combo.addItem(f"قیمت به {label}", k)
        self.unit_combo.setCurrentIndex(2)
        self.unit_combo.currentIndexChanged.connect(lambda _: self._reload_prices())

        self.catalog_pick = SearchCombo(placeholder="افزودن از کاتالوگ اقلام…")
        self.catalog_pick.activated.connect(self._add_from_catalog)

        add = QPushButton("+ ردیف")
        add.clicked.connect(lambda: self.add_line(Line(unit=self.units[0] if self.units else "عدد")))
        rem = QPushButton("حذف ردیف")
        rem.clicked.connect(self.remove_selected)
        up = QPushButton("▲")
        up.setToolTip("بالا")
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("▼")
        down.setToolTip("پایین")
        down.clicked.connect(lambda: self._move(1))
        self.markup_btn = QPushButton("مارک‌آپ…")
        self.markup_btn.clicked.connect(self._markup)

        bar = QHBoxLayout()
        bar.addWidget(self.catalog_pick, 2)
        bar.addWidget(add)
        bar.addWidget(rem)
        bar.addWidget(up)
        bar.addWidget(down)
        if mode == "money":
            bar.addWidget(self.markup_btn)
        if mode != "list":
            bar.addWidget(self.unit_combo)
        bar.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.table)
        self.hint = QLabel("برای ردیف‌های «تأمین خریدار» قیمت نگذارید؛ در لیست اقلام قرمز چاپ می‌شوند.",
                           styleSheet="color:#666")
        lay.addWidget(self.hint)
        self.hint.setVisible(mode != "letter")

    # ------------------------------------------------------------------ data in/out
    def set_catalog(self, items, units: list[str]):
        self.catalog = items
        self.catalog_by_desc = {i[1]: i for i in items}
        self.units = units
        self.catalog_pick.set_items([(f"{i[1]} ({i[2]})", i[0]) for i in items], keep=False)

    def set_unit(self, unit: str):
        i = self.unit_combo.findData(unit)
        if i >= 0:
            self.unit_combo.setCurrentIndex(i)

    def input_unit(self) -> str:
        return self.unit_combo.currentData()

    def set_lines(self, lines: list[Line]):
        self._lines = [Line(**vars(l)) for l in lines]
        self._rebuild()

    def lines(self) -> list[Line]:
        return [Line(**vars(l)) for l in self._lines]

    # ------------------------------------------------------------------ table
    def _rebuild(self):
        self._loading = True
        self.table.setRowCount(0)
        for l in self._lines:
            self._append_row(l)
        self._loading = False

    def _check_item(self, value: bool) -> QTableWidgetItem:
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it.setCheckState(Qt.Checked if value else Qt.Unchecked)
        return it

    def _append_row(self, l: Line):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, COL_DESC, QTableWidgetItem(l.description))
        q = QTableWidgetItem(money.fmt_decimal(l.qty))
        self.table.setItem(r, COL_QTY, q)
        unit = QComboBox()
        unit.setEditable(True)
        unit.addItems(self.units or ["عدد"])
        unit.setCurrentText(l.unit)
        unit.currentTextChanged.connect(lambda t, row=r: self._set_unit(row, t))
        self.table.setCellWidget(r, COL_UNIT, unit)
        self.table.setItem(r, COL_PRICE, QTableWidgetItem(self._price_text(l.unit_price)))
        tot = QTableWidgetItem()
        tot.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(r, COL_TOTAL, tot)
        self.table.setItem(r, COL_BUYER, self._check_item(l.buyer_supplied))
        self.table.setItem(r, COL_EMPH, self._check_item(l.emphasis))
        self.table.setItem(r, COL_SERVICE, self._check_item(l.is_service))
        for c in (COL_QTY, COL_PRICE, COL_TOTAL):
            self.table.item(r, c).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._paint_row(r)

    def _price_text(self, rial: int) -> str:
        if not rial:
            return ""
        v = money.from_rial(rial, self.input_unit())
        s = format(v, "f")
        if "." in s:
            a, b = s.split(".")
            return f"{int(a):,}.{b}"
        return f"{int(s):,}"

    def _paint_row(self, r: int):
        l = self._lines[r]
        tot = self.table.item(r, COL_TOTAL)
        if tot:
            tot.setText(money.fmt_int(l.total) if l.unit_price else "-")
        desc = self.table.item(r, COL_DESC)
        if desc:
            f = desc.font()
            f.setBold(l.emphasis)
            desc.setFont(f)
            desc.setForeground(QColor("#c62828") if l.buyer_supplied else QColor("#000"))
            tip = []
            if l.purchase_price:
                tip.append(f"قیمت خرید: {money.fmt_int(l.purchase_price)} ریال، سود {money.fmt_percent(l.markup_percent or 0)}٪ (چاپ نمی‌شود)")
            desc.setToolTip("\n".join(tip))

    def _reload_prices(self):
        self._loading = True
        for r, l in enumerate(self._lines):
            self.table.item(r, COL_PRICE).setText(self._price_text(l.unit_price))
        self._loading = False

    def _set_unit(self, row, text):
        if 0 <= row < len(self._lines):
            self._lines[row].unit = text
            self.changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._loading:
            return
        r, c = item.row(), item.column()
        if r >= len(self._lines):
            return
        l = self._lines[r]
        try:
            if c == COL_DESC:
                l.description = item.text().strip()
                cat = self.catalog_by_desc.get(l.description)
                if cat and not l.unit_price and self.mode != "list":
                    self._apply_catalog(r, cat)
            elif c == COL_QTY:
                l.qty = money.parse_decimal(item.text() or "0")
            elif c == COL_PRICE:
                l.unit_price = money.to_rial(item.text() or "0", self.input_unit())
                l.purchase_price, l.markup_percent = None, None
                self._loading = True
                item.setText(self._price_text(l.unit_price))
                self._loading = False
            elif c == COL_BUYER:
                l.buyer_supplied = item.checkState() == Qt.Checked
            elif c == COL_EMPH:
                l.emphasis = item.checkState() == Qt.Checked
            elif c == COL_SERVICE:
                l.is_service = item.checkState() == Qt.Checked
            item.setBackground(QColor(0, 0, 0, 0))
        except money.MoneyError:
            item.setBackground(QColor("#fff3cd"))
            return
        self._loading = True
        self._paint_row(r)
        self._loading = False
        self.changed.emit()

    def _apply_catalog(self, r, cat):
        ident, desc, unit, price, category, buyer, purchase = cat
        l = self._lines[r]
        l.item_id, l.description, l.unit, l.category = ident, desc, unit, category or ""
        if self.mode != "list" and price:
            l.unit_price = price
        l.buyer_supplied = bool(buyer)
        l.is_service = category == "installation"
        self._loading = True
        self.table.item(r, COL_DESC).setText(desc)
        self.table.cellWidget(r, COL_UNIT).setCurrentText(unit)
        self.table.item(r, COL_PRICE).setText(self._price_text(l.unit_price))
        self.table.item(r, COL_BUYER).setCheckState(Qt.Checked if l.buyer_supplied else Qt.Unchecked)
        self.table.item(r, COL_SERVICE).setCheckState(Qt.Checked if l.is_service else Qt.Unchecked)
        self._paint_row(r)
        self._loading = False

    def add_line(self, l: Line):
        self._lines.append(l)
        self._loading = True
        self._append_row(l)
        self._loading = False
        self.table.setCurrentCell(len(self._lines) - 1, COL_DESC)
        self.changed.emit()

    def _add_from_catalog(self, _index=None):
        ident = self.catalog_pick.current_id()
        cat = next((c for c in self.catalog if c[0] == ident), None)
        if not cat:
            return
        self.add_line(Line(description=cat[1], unit=cat[2]))
        self._apply_catalog(len(self._lines) - 1, cat)
        self.catalog_pick.setCurrentIndex(-1)
        self.catalog_pick.setEditText("")
        self.changed.emit()

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._lines.pop(r)
        self._rebuild()
        self.changed.emit()

    def _move(self, delta):
        r = self.table.currentRow()
        t = r + delta
        if r < 0 or not (0 <= t < len(self._lines)):
            return
        self._lines[r], self._lines[t] = self._lines[t], self._lines[r]
        self._rebuild()
        self.table.setCurrentCell(t, COL_DESC)
        self.changed.emit()

    def _markup(self):
        r = self.table.currentRow()
        if r < 0:
            return
        l = self._lines[r]
        dlg = MarkupDialog(l, self.input_unit(), self.markup_step, self)
        if dlg.exec():
            l.purchase_price = dlg.purchase.value()
            l.markup_percent = Decimal(str(dlg.pct.value()))
            l.unit_price = dlg.price()
            self._loading = True
            self.table.item(r, COL_PRICE).setText(self._price_text(l.unit_price))
            self._paint_row(r)
            self._loading = False
            self.changed.emit()
