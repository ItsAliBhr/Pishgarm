"""Reusable widgets."""
from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QTableView, QVBoxLayout, QWidget)

from app.core.normalize import normalize_text


class NormalizingFilterProxy(QSortFilterProxyModel):
    """Search across all columns; ي/ك and Persian digits in the query are normalised first,
    matching how data is stored."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_needle(self, text: str) -> None:
        if hasattr(self, "beginFilterChange"):  # Qt >= 6.10
            self.beginFilterChange()
            self._needle = normalize_text(text or "").lower()
            self.endFilterChange()
        else:
            self._needle = normalize_text(text or "").lower()
            self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if not self._needle:
            return True
        m = self.sourceModel()
        for col in range(m.columnCount()):
            val = m.index(row, col, parent).data()
            if val and self._needle in normalize_text(str(val)).lower():
                return True
        return False


class SearchTable(QWidget):
    """A read-only table with a search box above it and a row counter."""

    MAX_COL_WIDTH = 320

    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        self.model = QStandardItemModel(0, len(headers), self)
        self.model.setHorizontalHeaderLabels(headers)
        self.proxy = NormalizingFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.search = QLineEdit(placeholderText="جست‌وجو…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        self.count_label = QLabel()

        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(True)
        self.view.setWordWrap(False)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.count_label)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.view)

    def set_rows(self, rows: list[list], ids: list | None = None, colors: list | None = None) -> None:
        self.model.removeRows(0, self.model.rowCount())
        for n, r in enumerate(rows):
            items = []
            for v in r:
                it = QStandardItem("" if v is None else str(v))
                it.setEditable(False)
                if ids is not None:
                    it.setData(ids[n], Qt.UserRole)
                if colors and colors[n]:
                    from PySide6.QtGui import QColor
                    it.setForeground(QColor(colors[n]))
                items.append(it)
            self.model.appendRow(items)
        self.view.resizeColumnsToContents()
        for col in range(self.model.columnCount()):
            if self.view.columnWidth(col) > self.MAX_COL_WIDTH:
                self.view.setColumnWidth(col, self.MAX_COL_WIDTH)
        self._update_count()

    def row_count(self) -> int:
        return self.proxy.rowCount()

    def selected_id(self):
        idx = self.view.currentIndex()
        if not idx.isValid():
            return None
        return self.proxy.index(idx.row(), 0).data(Qt.UserRole)

    def selected_ids(self) -> list:
        rows = {i.row() for i in self.view.selectionModel().selectedRows()}
        return [self.proxy.index(r, 0).data(Qt.UserRole) for r in sorted(rows)]

    def _on_search(self, text):
        self.proxy.set_needle(text)
        self._update_count()

    def _update_count(self):
        self.count_label.setText(f"{self.proxy.rowCount()} ردیف")


# ====================================================================== form widgets

from datetime import date as _date  # noqa: E402

from PySide6.QtCore import Signal  # noqa: E402
from PySide6.QtWidgets import (QComboBox, QCompleter, QDialog, QFrame, QGridLayout,  # noqa: E402
                               QMessageBox, QPushButton, QToolButton)

from app.core import jalali, money  # noqa: E402
from app.core.num2words_fa import rial_words  # noqa: E402


def info(parent, text: str, title: str = "دفتر اسناد پیشگرم") -> None:
    QMessageBox.information(parent, title, text)


def warn(parent, text: str, title: str = "دفتر اسناد پیشگرم") -> None:
    QMessageBox.warning(parent, title, text)


def confirm(parent, text: str, title: str = "تأیید") -> bool:
    box = QMessageBox(QMessageBox.Question, title, text, parent=parent)
    yes = box.addButton("بله", QMessageBox.YesRole)
    box.addButton("خیر", QMessageBox.NoRole)
    box.exec()
    return box.clickedButton() is yes


class JalaliCalendar(QDialog):
    """Small monthly Jalali calendar popup (Saturday first, Friday in red)."""

    def __init__(self, current: _date | None, parent=None):
        super().__init__(parent, Qt.Popup)
        self.selected: _date | None = None
        j = jalali.to_jalali(current or _date.today())
        self.year, self.month = j.year, j.month
        self.current = current
        lay = QVBoxLayout(self)
        nav = QHBoxLayout()
        prev_b, next_b = QToolButton(text="›"), QToolButton(text="‹")
        prev_b.clicked.connect(lambda: self._shift(-1))
        next_b.clicked.connect(lambda: self._shift(1))
        self.title = QLabel(alignment=Qt.AlignCenter)
        today_b = QPushButton("امروز")
        today_b.clicked.connect(lambda: self._pick(_date.today()))
        nav.addWidget(prev_b)
        nav.addWidget(self.title, 1)
        nav.addWidget(next_b)
        lay.addLayout(nav)
        self.grid = QGridLayout()
        lay.addLayout(self.grid)
        lay.addWidget(today_b)
        self._build()

    def _shift(self, d: int) -> None:
        total = self.year * 12 + self.month - 1 + d
        self.year, self.month = divmod(total, 12)
        self.month += 1
        self._build()

    def _build(self) -> None:
        import jdatetime
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.title.setText(f"{jalali.MONTHS[self.month - 1]} {self.year}")
        for i, name in enumerate(["ش", "ی", "د", "س", "چ", "پ", "ج"]):
            l = QLabel(name, alignment=Qt.AlignCenter)
            if i == 6:
                l.setStyleSheet("color:#c62828")
            self.grid.addWidget(l, 0, i)
        first = jdatetime.date(self.year, self.month, 1)
        col = first.weekday()  # 0 = Saturday
        row = 1
        today = _date.today()
        for day in range(1, jalali.month_length(self.year, self.month) + 1):
            g = jdatetime.date(self.year, self.month, day).togregorian()
            b = QToolButton(text=str(day))
            b.setAutoRaise(True)
            b.setMinimumWidth(32)
            style = []
            if col == 6:
                style.append("color:#c62828")
            if g == today:
                style.append("font-weight:bold; border:1px solid #1f6feb; border-radius:4px")
            if g == self.current:
                style.append("background:#1f6feb; color:white; border-radius:4px")
            b.setStyleSheet(";".join(style))
            b.clicked.connect(lambda _=False, gd=g: self._pick(gd))
            self.grid.addWidget(b, row, col)
            col += 1
            if col == 7:
                col, row = 0, row + 1

    def _pick(self, d: _date) -> None:
        self.selected = d
        self.accept()


class JalaliDateEdit(QWidget):
    dateChanged = Signal(object)

    def __init__(self, value: _date | None = None, allow_empty: bool = False, parent=None):
        super().__init__(parent)
        self.allow_empty = allow_empty
        self.edit = QLineEdit(placeholderText="1405/09/01")
        self.edit.setLayoutDirection(Qt.LeftToRight)
        self.edit.setMaximumWidth(120)
        self.edit.editingFinished.connect(self._on_edit)
        btn = QToolButton(text="▦")
        btn.setToolTip("تقویم")
        btn.clicked.connect(self._popup)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)
        lay.addWidget(btn)
        lay.addStretch(1)
        self._value: _date | None = None
        self.setDate(value if value is not None or allow_empty else _date.today())

    def date(self) -> _date | None:
        return self._value

    def text(self) -> str:
        return jalali.fmt(self._value) if self._value else ""

    def setDate(self, d: _date | None) -> None:
        self._value = d
        self.edit.setText(jalali.fmt(d) if d else "")
        self.edit.setStyleSheet("")

    def _on_edit(self) -> None:
        txt = self.edit.text().strip()
        if not txt and self.allow_empty:
            self._value = None
            self.dateChanged.emit(None)
            return
        d = jalali.parse(txt)
        if d is None:
            self.edit.setStyleSheet("background:#fff3cd")
            return
        changed = d != self._value
        self.setDate(d)
        if changed:
            self.dateChanged.emit(d)

    def _popup(self) -> None:
        cal = JalaliCalendar(self._value, self)
        cal.move(self.mapToGlobal(self.rect().bottomLeft()))
        if cal.exec() and cal.selected:
            self.setDate(cal.selected)
            self.dateChanged.emit(cal.selected)


class MoneyEdit(QWidget):
    """Amount input with unit (ریال / تومان / میلیون تومان) and a live line
    «= 21,000,000,000 ریال – بیست و یک میلیارد ریال»."""
    valueChanged = Signal(int)

    def __init__(self, unit: str = "million_toman", show_words: bool = True, parent=None):
        super().__init__(parent)
        self.edit = QLineEdit()
        self.edit.setLayoutDirection(Qt.LeftToRight)
        self.edit.setAlignment(Qt.AlignLeft)
        self.edit.textEdited.connect(self._on_text)
        self.unit = QComboBox()
        for k, label in money.UNIT_LABELS.items():
            self.unit.addItem(label, k)
        self.unit.setCurrentIndex(list(money.UNIT_LABELS).index(unit))
        self.unit.currentIndexChanged.connect(lambda _: self._on_text(self.edit.text()))
        self.words = QLabel()
        self.words.setStyleSheet("color:#555")
        self.words.setWordWrap(True)
        self.words.setVisible(show_words)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.edit, 1)
        top.addWidget(self.unit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(top)
        lay.addWidget(self.words)
        self._value = 0

    def current_unit(self) -> str:
        return self.unit.currentData()

    def value(self) -> int:
        return self._value

    def setValue(self, rial: int | None, unit: str | None = None) -> None:
        if unit:
            self.unit.blockSignals(True)
            self.unit.setCurrentIndex(list(money.UNIT_LABELS).index(unit))
            self.unit.blockSignals(False)
        self._value = int(rial or 0)
        v = money.from_rial(self._value, self.current_unit())
        self.edit.setText(self._group(format(v, "f")) if self._value else "")
        self._update_words()

    @staticmethod
    def _group(text: str) -> str:
        if "." in text:
            a, b = text.split(".", 1)
            return f"{int(a or 0):,}.{b}"
        return f"{int(text):,}" if text else ""

    def _on_text(self, text: str) -> None:
        try:
            v = money.parse_decimal(text)
            self._value = money.to_rial(v, self.current_unit())
            clean = money._clean_number(text)
            if clean and not clean.endswith(".") and clean.replace(".", "", 1).isdigit():
                pos = len(self.edit.text()) - self.edit.cursorPosition()
                self.edit.setText(self._group(clean))
                self.edit.setCursorPosition(max(0, len(self.edit.text()) - pos))
            self.edit.setStyleSheet("")
        except money.MoneyError:
            self.edit.setStyleSheet("background:#fff3cd")
            return
        self._update_words()
        self.valueChanged.emit(self._value)

    def _update_words(self) -> None:
        self.words.setText(f"= {money.fmt_int(self._value)} ریال – {rial_words(self._value)}"
                           if self._value else "")


class SearchCombo(QComboBox):
    """Editable combo; typing a few letters anywhere in the name finds the row."""
    idChanged = Signal(object)

    def __init__(self, parent=None, placeholder: str = "جست‌وجو…"):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.lineEdit().setPlaceholderText(placeholder)
        comp = self.completer()
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.currentIndexChanged.connect(lambda _: self.idChanged.emit(self.current_id()))
        self.setMinimumWidth(280)

    def set_items(self, items: list[tuple[str, object]], keep: bool = True) -> None:
        cur = self.current_id() if keep else None
        self.blockSignals(True)
        self.clear()
        for label, ident in items:
            self.addItem(label, ident)
        self.setCurrentIndex(-1)
        self.blockSignals(False)
        if cur is not None:
            self.set_current_id(cur)

    def current_id(self):
        i = self.currentIndex()
        if i < 0 or self.itemText(i) != self.currentText():
            return None
        return self.itemData(i)

    def set_current_id(self, ident) -> None:
        i = self.findData(ident)
        self.setCurrentIndex(i)
        if i < 0:
            self.setEditText("")


class IssuesBox(QFrame):
    """Yellow box for warnings, red for blocking errors (doc 04: «هشدار، نه مانع»)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel(wordWrap=True)
        self.label.setTextFormat(Qt.RichText)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.addWidget(self.label)
        self.set_issues([])

    def set_issues(self, issues) -> None:
        if not issues:
            self.hide()
            return
        errors = [i for i in issues if i.blocking]
        color, border = ("#fdecea", "#e57373") if errors else ("#fff8e1", "#ffca28")
        self.setStyleSheet(f"IssuesBox {{ background:{color}; border:1px solid {border}; border-radius:6px; }}")
        rows = [f"{'⛔' if i.blocking else '⚠'} {i.message}" for i in issues]
        self.label.setText("<br>".join(rows))
        self.show()
