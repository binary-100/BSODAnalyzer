"""Agent verification: interactive GUI starts (platform + MainWindow) then exits cleanly."""
from __future__ import annotations

import os
import sys

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

# Simulate polluted post-test terminal (cmd trailing-space bug).
os.environ["QT_QPA_PLATFORM"] = "offscreen "

import gui_qt_bootstrap as qt_boot

qt_boot.prepare_interactive_gui(probe=True)

from PySide6 import QtCore, QtWidgets

import bsod_gui_qt


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    platform = app.platformName()
    if platform != "windows":
        print(f"FAIL: expected platform windows, got {platform!r}")
        return 1

    win = bsod_gui_qt.MainWindow()
    win.show()
    app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 2000)

    title = win.windowTitle()
    if not win.isVisible():
        print("FAIL: MainWindow not visible after show()")
        return 1

    print(f"OK: platform={platform} title={title!r} visible={win.isVisible()}")
    win.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
