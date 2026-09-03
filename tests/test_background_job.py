"""BackgroundJob thread lifecycle (export/refresh workers)."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from gui_test_harness import offscreen_application


def test_background_job_clears_after_worker_finishes() -> None:
    with offscreen_application():
        from PySide6 import QtCore, QtWidgets

        import bsod_gui_workers as gw

        class _Worker(QtCore.QObject):
            finished = QtCore.Signal(str)

            @QtCore.Slot()
            def run(self) -> None:
                self.finished.emit("ok")

        job = gw.BackgroundJob()
        worker = _Worker()
        seen: list[str] = []
        job.start(worker, connections=[(worker.finished, seen.append)])

        app = QtWidgets.QApplication.instance()
        assert app is not None
        for _ in range(500):
            app.processEvents()
            if not job.is_running():
                break
            QtCore.QThread.msleep(10)
        else:
            raise AssertionError("BackgroundJob still running after worker finished")

        assert seen == ["ok"]
        assert not job.is_running()
        for _ in range(100):
            app.processEvents()
            if job.thread is None:
                break
            QtCore.QThread.msleep(10)
        assert job.thread is None
        assert job.worker is None


if __name__ == "__main__":
    test_background_job_clears_after_worker_finishes()
    print("BackgroundJob tests OK")
