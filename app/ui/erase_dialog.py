"""«پاک کردن ناحیه»: draw white rectangles over a PDF page (e.g. a drawing's title block)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QRubberBand, QScrollArea, QSpinBox, QVBoxLayout)

from app.core import pdf_tools


def _to_pixmap(img) -> QPixmap:
    img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    q = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


class _Canvas(QLabel):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = None
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, e):
        self.origin = e.position().toPoint()
        self.band.setGeometry(QRect(self.origin, QSize()))
        self.band.show()

    def mouseMoveEvent(self, e):
        if self.origin is not None:
            self.band.setGeometry(QRect(self.origin, e.position().toPoint()).normalized())

    def mouseReleaseEvent(self, e):
        if self.origin is None:
            return
        r = QRect(self.origin, e.position().toPoint()).normalized()
        self.band.hide()
        self.origin = None
        pm = self.pixmap()
        if pm and r.width() > 4 and r.height() > 4:
            w, h = pm.width(), pm.height()
            self.dialog.add_rect((r.left() / w, r.top() / h, r.right() / w, r.bottom() / h))


class EraseDialog(QDialog):
    def __init__(self, pdf_path, regions: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("پاک کردن ناحیه")
        self.resize(1000, 760)
        self.pdf = pdf_path
        self.regions: dict[int, list] = {int(k): [tuple(r) for r in v] for k, v in (regions or {}).items()}
        self.pages = pdf_tools.page_count(pdf_path)
        self.page = QSpinBox(minimum=1, maximum=max(self.pages, 1))
        self.page.valueChanged.connect(lambda _: self._show())
        clear = QPushButton("پاک کردن مستطیل‌های این صفحه")
        clear.clicked.connect(self._clear)
        top = QHBoxLayout()
        top.addWidget(QLabel("با ماوس روی ناحیه‌ای که باید سفید شود (مثل شناسنامه‌ی نقشه) مستطیل بکشید. صفحه:"))
        top.addWidget(self.page)
        top.addWidget(clear)
        top.addStretch(1)
        self.canvas = _Canvas(self)
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        scroll.setLayoutDirection(Qt.LeftToRight)
        bb = QDialogButtonBox()
        bb.addButton("تأیید", QDialogButtonBox.AcceptRole)
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(scroll, 1)
        lay.addWidget(bb)
        self._show()

    def _show(self):
        i = self.page.value() - 1
        img = pdf_tools.render_page(self.pdf, i, dpi=90)
        pm = _to_pixmap(img)
        painter = QPainter(pm)
        painter.setPen(QColor("#c62828"))
        painter.setBrush(QColor(255, 255, 255, 220))
        for x0, y0, x1, y1 in self.regions.get(i, []):
            painter.drawRect(QRect(QPoint(int(x0 * pm.width()), int(y0 * pm.height())),
                                   QPoint(int(x1 * pm.width()), int(y1 * pm.height()))))
        painter.end()
        self.canvas.setPixmap(pm)
        self.canvas.resize(pm.size())

    def add_rect(self, rect):
        self.regions.setdefault(self.page.value() - 1, []).append(rect)
        self._show()

    def _clear(self):
        self.regions.pop(self.page.value() - 1, None)
        self._show()

    def result_regions(self) -> dict:
        return {str(k): [list(r) for r in v] for k, v in self.regions.items() if v}
