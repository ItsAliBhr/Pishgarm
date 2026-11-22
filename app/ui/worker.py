"""Run slow work (Word → PDF, merging) off the UI thread with a busy dialog (doc 07 §7.3)."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QProgressDialog


class _Job(QObject):
    finished = Signal(object, object)   # result, error-text

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished.emit(self.fn(), None)
        except Exception as e:  # reported to the UI thread
            self.finished.emit(None, (e, traceback.format_exc()))


def run_busy(parent, text: str, fn, on_done) -> None:
    """Call fn() in a thread; then on_done(result, error) on the UI thread.
    `error` is None or (exception, traceback-text)."""
    dlg = QProgressDialog(text, None, 0, 0, parent)
    dlg.setWindowTitle("لطفاً صبر کنید")
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)
    dlg.setCancelButton(None)
    thread = QThread(parent)
    job = _Job(fn)
    job.moveToThread(thread)
    thread.started.connect(job.run)

    def done(result, error):
        dlg.close()
        thread.quit()
        thread.wait()
        job.deleteLater()
        thread.deleteLater()
        on_done(result, error)

    job.finished.connect(done, Qt.QueuedConnection)
    parent._busy_refs = getattr(parent, "_busy_refs", []) + [(thread, job)]
    thread.start()
    dlg.show()
