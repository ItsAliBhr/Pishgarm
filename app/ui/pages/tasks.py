"""کارها: light task manager (doc 04 §4.5)."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)
from sqlalchemy import select

from app.core import jalali
from app.db.models import Party, Project, Task
from app.services import tasks as task_service
from app.ui.widgets import JalaliDateEdit, SearchCombo


class TaskForm(QDialog):
    def __init__(self, s, task: Task | None = None, parent=None):
        super().__init__(parent)
        self.s, self.task = s, task
        self.setWindowTitle("کار")
        self.setMinimumWidth(480)
        f = QFormLayout(self)
        self.title = QLineEdit(task.title if task else "")
        f.addRow("عنوان:", self.title)
        self.due = JalaliDateEdit(task.due_date if task else date.today())
        f.addRow("سررسید:", self.due)
        self.project = SearchCombo(placeholder="(اختیاری)")
        self.project.set_items([(f"{p.party.short_name or p.party.name} – {p.title}", p.id)
                                for p in s.scalars(select(Project).where(Project.is_archived.is_(False)))], keep=False)
        if task and task.project_id:
            self.project.set_current_id(task.project_id)
        f.addRow("پروژه:", self.project)
        self.notes = QLineEdit(task.notes if task else "")
        f.addRow("یادداشت:", self.notes)
        bb = QDialogButtonBox()
        bb.addButton("ذخیره", QDialogButtonBox.AcceptRole)
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(lambda: self.accept() if self.title.text().strip() else None)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def save(self):
        t = self.task or Task(title="", source="manual")
        t.title = self.title.text().strip()
        t.due_date = self.due.date()
        t.project_id = self.project.current_id()
        if t.project_id:
            t.party_id = self.s.get(Project, t.project_id).party_id
        t.notes = self.notes.text().strip()
        if t.id is None:
            self.s.add(t)
        self.s.commit()


class TaskTable(QTableWidget):
    """Tasks with a one-click «انجام شد» checkbox."""
    toggled = Signal(int, bool)
    activated_task = Signal(int)

    def __init__(self):
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(["انجام شد", "عنوان", "سررسید", "مشتری / پروژه", "منبع"])
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.itemChanged.connect(self._changed)
        self.cellDoubleClicked.connect(lambda r, c: self.activated_task.emit(self.item(r, 0).data(Qt.UserRole)))
        self._loading = False

    def set_tasks(self, tasks):
        self._loading = True
        self.setRowCount(0)
        today = date.today()
        for t in tasks:
            r = self.rowCount()
            self.insertRow(r)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if t.status == "done" else Qt.Unchecked)
            chk.setData(Qt.UserRole, t.id)
            self.setItem(r, 0, chk)
            where = ""
            if t.project:
                where = f"{t.project.party.short_name or t.project.party.name} – {t.project.title}"
            elif t.party:
                where = t.party.short_name or t.party.name
            src = "خودکار" if (t.source or "").startswith("auto") else "دستی"
            if t.action:
                src += " – دوبار کلیک: ساخت نامه"
            for c, v in enumerate([t.title, jalali.fmt(t.due_date), where, src], 1):
                it = QTableWidgetItem(v)
                if t.status == "open" and t.due_date and t.due_date < today:
                    it.setForeground(QColor("#c62828"))
                elif t.status == "done":
                    it.setForeground(QColor("#999"))
                self.setItem(r, c, it)
        self.resizeColumnToContents(2)
        self._loading = False

    def _changed(self, item):
        if self._loading or item.column() != 0:
            return
        self.toggled.emit(item.data(Qt.UserRole), item.checkState() == Qt.Checked)


class TasksPage(QWidget):
    changed = Signal()
    runAction = Signal(dict)

    def __init__(self, SessionLocal, parent=None):
        super().__init__(parent)
        self.S = SessionLocal
        lay = QVBoxLayout(self)
        t = QLabel("کارها")
        t.setObjectName("pageTitle")
        lay.addWidget(t)
        bar = QHBoxLayout()
        nb = QPushButton("+ کار جدید")
        nb.setObjectName("primary")
        nb.clicked.connect(self._new)
        eb = QPushButton("ویرایش")
        eb.clicked.connect(self._edit)
        bar.addWidget(nb)
        bar.addWidget(eb)
        bar.addStretch(1)
        self.status_f = QComboBox()
        self.status_f.addItems(["باز", "انجام‌شده", "همه"])
        self.status_f.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(QLabel("در نمای «همه»:"))
        bar.addWidget(self.status_f)
        lay.addLayout(bar)
        self.tabs = QTabWidget()
        self.today_table = TaskTable()
        self.all_table = TaskTable()
        for tbl in (self.today_table, self.all_table):
            tbl.toggled.connect(self._toggle)
            tbl.activated_task.connect(self._activate)
        self.tabs.addTab(self.today_table, "امروز و عقب‌افتاده")
        self.tabs.addTab(self.all_table, "همه")
        lay.addWidget(self.tabs)
        self.refresh()

    def refresh(self):
        with self.S() as s:
            base = select(Task).where(Task.is_archived.is_(False))
            today = s.scalars(base.where(Task.status == "open", Task.due_date <= date.today()).order_by(Task.due_date)).all()
            self.today_table.set_tasks(today)
            q = base
            if self.status_f.currentIndex() == 0:
                q = q.where(Task.status == "open")
            elif self.status_f.currentIndex() == 1:
                q = q.where(Task.status == "done")
            self.all_table.set_tasks(s.scalars(q.order_by(Task.due_date)).all())
            self.tabs.setTabText(0, f"امروز و عقب‌افتاده ({len(today)})")

    def _toggle(self, task_id, done):
        with self.S() as s:
            t = task_service.complete(s, task_id, done)
            action = dict(t.action) if (done and t.action) else None
        self.refresh()
        self.changed.emit()
        if action:
            self.runAction.emit(action)

    def _activate(self, task_id):
        with self.S() as s:
            t = s.get(Task, task_id)
            action = dict(t.action) if t.action else None
        if action:
            self.runAction.emit(action)
        else:
            self._edit()

    def _current_table(self):
        return self.today_table if self.tabs.currentIndex() == 0 else self.all_table

    def _new(self):
        with self.S() as s:
            dlg = TaskForm(s, None, self)
            if dlg.exec():
                dlg.save()
        self.refresh()
        self.changed.emit()

    def _edit(self):
        tbl = self._current_table()
        r = tbl.currentRow()
        if r < 0:
            return
        with self.S() as s:
            dlg = TaskForm(s, s.get(Task, tbl.item(r, 0).data(Qt.UserRole)), self)
            if dlg.exec():
                dlg.save()
        self.refresh()
        self.changed.emit()
