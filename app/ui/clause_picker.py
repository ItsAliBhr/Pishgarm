"""Step 5: clauses in collapsible groups, inline variables, ad-hoc clauses, drag ordering."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from app.core.clauses import render_clause
from app.core.draft import CLAUSE_GROUPS, GROUP_FA, ClauseSel

VAR_LABELS = {"advance_percent": "درصد پیش‌پرداخت", "retention_percent": "درصد سپرده",
              "retention_months": "ماه", "install_advance_percent": "درصد نصب", "delivery_days": "روز",
              "days_from": "از روز", "days_to": "تا روز", "insurance_percent": "درصد بیمه",
              "validity_days": "روز اعتبار", "warranty_months": "ماه گارانتی", "cheque_percent": "درصد چک",
              "guarantee_months": "ماه تضمین", "origin_country": "کشور"}


class AdHocDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("بند آزاد")
        f = QFormLayout(self)
        self.text = QPlainTextEdit()
        self.text.setFixedHeight(90)
        self.group = QComboBox()
        for g in CLAUSE_GROUPS:
            self.group.addItem(GROUP_FA[g], g)
        self.group.setCurrentIndex(CLAUSE_GROUPS.index("other"))
        self.to_library = QCheckBox("افزودن به کتابخانه‌ی بندها")
        f.addRow("متن:", self.text)
        f.addRow("گروه:", self.group)
        f.addRow("", self.to_library)
        bb = QDialogButtonBox()
        bb.addButton("افزودن", QDialogButtonBox.AcceptRole)
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class ClauseRow(QWidget):
    toggled = Signal()

    def __init__(self, sel: ClauseSel, checked: bool, picker):
        super().__init__()
        self.sel, self.picker = sel, picker
        self.check = QCheckBox()
        self.check.setChecked(checked)
        self.check.toggled.connect(lambda _: self.toggled.emit())
        self.text = QLabel(wordWrap=True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text.mousePressEvent = lambda e: self.check.toggle()
        self.vars: dict[str, QLineEdit] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.check, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        for name, spec in (sel.variables or {}).items():
            e = QLineEdit(str((sel.values or {}).get(name, (spec or {}).get("default", ""))))
            e.setMaximumWidth(80)
            e.setToolTip(VAR_LABELS.get(name, name))
            e.setPlaceholderText(VAR_LABELS.get(name, name))
            e.textEdited.connect(lambda t, n=name: self._var(n, t))
            lay.addWidget(QLabel(VAR_LABELS.get(name, name) + ":", styleSheet="color:#666"))
            lay.addWidget(e)
            self.vars[name] = e

    def _var(self, name, text):
        self.sel.values[name] = text.strip()
        self.toggled.emit()

    def refresh(self, draft):
        try:
            self.text.setText(render_clause(draft, self.sel))
        except Exception:
            self.text.setText(self.sel.template)


class ClausePicker(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[ClauseRow] = []
        self.order: list[ClauseSel] = []   # selected, in user order
        self.draft = None
        self.add_to_library = []           # ad-hoc clauses to save into the library

        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.container)

        adhoc = QPushButton("+ بند آزاد")
        adhoc.clicked.connect(self._add_adhoc)
        self.order_list = QListWidget()
        self.order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.order_list.model().rowsMoved.connect(lambda *_: self._order_from_list())
        self.order_list.setWordWrap(True)
        side = QVBoxLayout()
        side.addWidget(QLabel("ترتیب بندهای انتخاب‌شده (با کشیدن جابه‌جا کنید):"))
        side.addWidget(self.order_list)
        rm = QPushButton("برداشتن بند انتخاب‌شده")
        rm.clicked.connect(self._remove_from_order)
        side.addWidget(rm)
        sidew = QWidget()
        sidew.setLayout(side)
        sidew.setMaximumWidth(380)

        top = QHBoxLayout()
        top.addWidget(adhoc)
        top.addStretch(1)
        main = QHBoxLayout()
        main.addWidget(scroll, 3)
        main.addWidget(sidew, 2)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addLayout(main)

    def load(self, draft, available: list[ClauseSel], usage_rank: dict | None = None):
        """`available`: all library clauses for this kind (fresh ClauseSel objects)."""
        self.draft = draft
        while self.vbox.count():
            w = self.vbox.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.rows = []
        selected = {c.code: c for c in draft.clauses if c.code}
        self.order = list(draft.clauses)
        usage_rank = usage_rank or {}
        for g in CLAUSE_GROUPS:
            group_items = [c for c in available if c.group == g]
            group_items.sort(key=lambda c: -usage_rank.get(c.code, 0))
            adhoc = [c for c in draft.clauses if not c.code and c.group == g]
            if not group_items and not adhoc:
                continue
            box = QGroupBox(GROUP_FA[g])
            box.setCheckable(False)
            bl = QVBoxLayout(box)
            toggle = QToolButton(text="▾ نمایش/پنهان")
            toggle.setAutoRaise(True)
            inner = QWidget()
            il = QVBoxLayout(inner)
            il.setContentsMargins(0, 0, 0, 0)
            toggle.clicked.connect(lambda _=False, w=inner: w.setVisible(not w.isVisible()))
            bl.addWidget(toggle, 0, Qt.AlignLeading)
            bl.addWidget(inner)
            for c in group_items + adhoc:
                sel = selected.get(c.code, c) if c.code else c
                row = ClauseRow(sel, (c.code in selected) if c.code else True, self)
                row.toggled.connect(lambda r=row: self._on_toggle(r))
                il.addWidget(row)
                self.rows.append(row)
            has_selected = any(r.check.isChecked() for r in self.rows if r.sel.group == g)
            inner.setVisible(has_selected or g in ("payment", "tax"))
            self.vbox.addWidget(box)
        self.vbox.addStretch(1)
        self.refresh()

    def _on_toggle(self, row: ClauseRow):
        if row.check.isChecked() and row.sel not in self.order:
            self.order.append(row.sel)
        elif not row.check.isChecked() and row.sel in self.order:
            self.order.remove(row.sel)
        self._sync()

    def _sync(self):
        if self.draft is not None:
            self.draft.clauses = list(self.order)
        self.refresh()
        self.changed.emit()

    def refresh(self):
        if self.draft is None:
            return
        for r in self.rows:
            r.refresh(self.draft)
        self.order_list.blockSignals(True)
        self.order_list.clear()
        for c in self.order:
            it = QListWidgetItem(f"[{GROUP_FA.get(c.group, c.group)}] {render_clause(self.draft, c)}")
            it.setData(Qt.UserRole, id(c))
            self.order_list.addItem(it)
        self.order_list.blockSignals(False)

    def _order_from_list(self):
        by_id = {id(c): c for c in self.order}
        self.order = [by_id[self.order_list.item(i).data(Qt.UserRole)] for i in range(self.order_list.count())]
        self._sync()

    def _remove_from_order(self):
        it = self.order_list.currentItem()
        if not it:
            return
        target = next((c for c in self.order if id(c) == it.data(Qt.UserRole)), None)
        for r in self.rows:
            if r.sel is target:
                r.check.setChecked(False)
                return
        if target:
            self.order.remove(target)
            self._sync()

    def _add_adhoc(self):
        dlg = AdHocDialog(self)
        if not dlg.exec() or not dlg.text.toPlainText().strip():
            return
        sel = ClauseSel(group=dlg.group.currentData(), template=dlg.text.toPlainText().strip())
        if dlg.to_library.isChecked():
            self.add_to_library.append(sel)
        self.order.append(sel)
        self._sync()
        if self.draft is not None:
            # rebuild to show the new row inside its group
            avail = [r.sel for r in self.rows if r.sel.code]
            self.load(self.draft, avail)
