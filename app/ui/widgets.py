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

    def set_rows(self, rows: list[list]) -> None:
        self.model.removeRows(0, self.model.rowCount())
        for r in rows:
            items = []
            for v in r:
                it = QStandardItem("" if v is None else str(v))
                it.setEditable(False)
                items.append(it)
            self.model.appendRow(items)
        self.view.resizeColumnsToContents()
        for col in range(self.model.columnCount()):
            if self.view.columnWidth(col) > self.MAX_COL_WIDTH:
                self.view.setColumnWidth(col, self.MAX_COL_WIDTH)
        self._update_count()

    def row_count(self) -> int:
        return self.proxy.rowCount()

    def _on_search(self, text):
        self.proxy.set_needle(text)
        self._update_count()

    def _update_count(self):
        self.count_label.setText(f"{self.proxy.rowCount()} ردیف")
