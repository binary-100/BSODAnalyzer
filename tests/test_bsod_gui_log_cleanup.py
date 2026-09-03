"""GUI tests — log cleanup wizard pages."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

import bsod_gui_log_cleanup as gui_log_cleanup  # noqa: E402


def test_prepare_page_incomplete_until_all_checks() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    page = gui_log_cleanup.PreparePage()
    assert page.isComplete() is False
    for cb in page._checks:
        cb.setChecked(True)
    assert page.isComplete() is True


def test_prepare_page_exports_wizard_pages() -> None:
    assert gui_log_cleanup.PreparePage.__name__ == "PreparePage"
    assert gui_log_cleanup.InventoryPage.__name__ == "InventoryPage"
