"""GUI tests — Advanced tab minidump panel (`gui_mixin_minidump.py`)."""

from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui_test_harness import offscreen_main_window  # noqa: E402


def test_minidump_panel_empty_shows_guidance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._refresh_minidump_panel({"kernel_dumps": [], "windbg_analysis": {}})
            assert win.minidump_combo.count() == 1
            assert "No kernel minidumps" in win.minidump_combo.itemText(0)
            assert not win.minidump_combo.isEnabled()
            html = win.minidump_stack_browser.toHtml()
            assert "Run Analysis" in html or "memory dumps" in html


def test_minidump_panel_lists_dumps_from_model() -> None:
    dumps = [
        {"path": r"C:\Windows\Minidump\081524.dmp", "time": "2025-08-15 12:00:00"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._refresh_minidump_panel({"kernel_dumps": dumps, "windbg_analysis": {}})
            assert win.minidump_combo.isEnabled()
            assert win.minidump_combo.count() >= 1
            assert win.minidump_combo.itemData(0) == dumps[0]["path"]
