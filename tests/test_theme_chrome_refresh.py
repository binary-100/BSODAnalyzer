"""Theme chrome refresh — severity meter, compare table, action links."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui_test_harness import (  # noqa: E402
    offscreen_main_window,
    offscreen_widget,
    process_events_until,
)

import gui_theme as theme  # noqa: E402
from PySide6 import QtGui, QtWidgets  # noqa: E402
from gui_widgets import SeverityMeter  # noqa: E402


def _hex_rgb(color: QtGui.QColor) -> str:
    return color.name(QtGui.QColor.NameFormat.HexRgb).lower()


def test_severity_meter_reads_live_theme_tokens() -> None:
    with offscreen_widget(SeverityMeter) as meter:
        meter.set_level(2)
        theme.activate_theme("night")
        meter.update()
        assert theme.SEVERITY_COLORS[2] == "#f5731f"

        theme.activate_theme("manly")
        meter.update()
        assert theme.SEVERITY_COLORS[2] == "#c86848"
        theme.activate_theme("night")


def test_action_link_style_follows_theme() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            theme.activate_theme("night")
            night = win._action_link_btn_style()
            assert theme.ACCENT in night

            theme.activate_theme("manly")
            win._apply_ui_theme()
            manly = win._action_link_btn_style()
            assert theme.ACCENT in manly
            assert manly != night

            theme.activate_theme("night")


def test_compare_table_vs_colors_follow_theme() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            table = win.drv_compare_table
            offers = [
                {
                    "vs_installed": "newer",
                    "version": "2.0.0",
                    "source_label": "Test",
                    "display_title": "Package A",
                }
            ]
            theme.activate_theme("night")
            win._fill_driver_compare_table(table, offers)
            item = table.item(0, 0)
            assert item is not None
            night_fg = _hex_rgb(item.foreground().color())

            theme.activate_theme("manly")
            win._fill_driver_compare_table(table, offers)
            item = table.item(0, 0)
            assert item is not None
            manly_fg = _hex_rgb(item.foreground().color())
            assert night_fg != manly_fg

            theme.activate_theme("night")


def test_refresh_theme_chrome_reapplies_summary_html() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            model = {
                "severity_level": 1,
                "severity_name": "Moderate",
                "cause_title": "Test cause",
                "confidence": "Test",
                "cause_type": {"driver_actionable": True},
                "driver": "sample.sys",
                "plain_english": "Sample summary text for sample.sys.",
                "fix_plan": {"steps": ["Do something useful."]},
                "recommendations": [],
                "incidents": [],
                "dumps_analyzed": 0,
                "crash_count": 0,
            }
            win._last_model = model
            theme.activate_theme("night")
            win._refresh_theme_chrome_from_model()
            night_html = win._plain_english_html(model)
            assert theme.ACCENT.lower() in night_html.lower()

            theme.activate_theme("manly")
            win._refresh_theme_chrome_from_model()
            manly_html = win._plain_english_html(model)
            assert theme.ACCENT.lower() in manly_html.lower()
            assert manly_html != night_html

            theme.activate_theme("night")


if __name__ == "__main__":
    test_severity_meter_reads_live_theme_tokens()
    test_action_link_style_follows_theme()
    test_compare_table_vs_colors_follow_theme()
    test_refresh_theme_chrome_reapplies_summary_html()
    print("OK")
