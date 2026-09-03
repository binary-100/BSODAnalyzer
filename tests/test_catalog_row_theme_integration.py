"""Catalog row styling under each View theme — offscreen integration."""

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

from gui_test_harness import offscreen_main_window, process_events_until  # noqa: E402

import gui_theme as theme  # noqa: E402
from PySide6 import QtGui, QtWidgets  # noqa: E402


def _hex_rgb(color: QtGui.QColor) -> str:
    return color.name(QtGui.QColor.NameFormat.HexRgb).lower()


def _seed_row(table: QtWidgets.QTableWidget, row: int) -> None:
    from gui_theme import DRV_COL_CHECK, DRV_COL_DEVICE, DRV_COL_ICON, DRV_COL_INSTALLED

    for col, flags in (
        (DRV_COL_ICON, QtWidgets.QTableWidgetItem()),
        (DRV_COL_CHECK, QtWidgets.QTableWidgetItem()),
        (DRV_COL_DEVICE, QtWidgets.QTableWidgetItem("Test Device")),
        (DRV_COL_INSTALLED, QtWidgets.QTableWidgetItem("1.0.0")),
    ):
        item = flags
        item.setFlags(QtGui.Qt.ItemIsEnabled | QtGui.Qt.ItemIsSelectable)
        table.setItem(row, col, item)


def _device_bg(table: QtWidgets.QTableWidget, row: int) -> QtGui.QColor:
    from gui_theme import DRV_COL_DEVICE

    item = table.item(row, DRV_COL_DEVICE)
    assert item is not None
    return item.background().color()


def _status_fg(table: QtWidgets.QTableWidget, row: int) -> QtGui.QColor:
    from gui_theme import DRV_COL_STATUS

    item = table.item(row, DRV_COL_STATUS)
    assert item is not None
    return item.foreground().color()


def test_catalog_row_style_survives_night_day_and_manly_themes() -> None:
    """Regression: driver scan finish tints rows using live gui_theme tokens."""
    cases = {
        "night": {
            "update_bg": "#3a3420",
            "culprit_bg": "#3a2228",
            "current_solid": "#243d30",
            "status_same": "#3fb950",
        },
        "day": {
            "update_bg": "#fef3c7",
            "culprit_bg": "#fee2e2",
            "current_solid": "#dcfce7",
            "status_same": "#15803d",
        },
        "manly": {
            "update_bg": "#f5d9a8",
            "culprit_bg": "#f5c0cc",
            "current_solid": "#b8e6cc",
            "status_same": "#2a7a50",
        },
    }

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            table = win.drv_unified_table
            table.setRowCount(1)
            _seed_row(table, 0)
            process_events_until(lambda: table.rowCount() == 1, timeout_ms=500)

            for theme_id, expected in cases.items():
                theme.activate_theme(theme_id)
                win._apply_ui_theme()

                win._set_device_row_status(0, "newer", table=table)
                win._apply_catalog_row_style(
                    table, 0, tier="normal", status="newer"
                )
                assert _hex_rgb(_device_bg(table, 0)) == expected["update_bg"]

                win._set_device_row_status(0, "same", table=table)
                win._apply_catalog_row_style(
                    table, 0, tier="normal", status="same"
                )
                current = _device_bg(table, 0)
                assert _hex_rgb(current) == expected["current_solid"]
                assert _hex_rgb(_status_fg(table, 0)) == expected["status_same"]
                name_item = table.item(0, theme.DRV_COL_DEVICE)
                assert name_item is not None
                assert _hex_rgb(name_item.foreground().color()) == theme.TEXT.lower()

                win._apply_catalog_row_style(
                    table, 0, tier="normal", status="newer"
                )
                name_item = table.item(0, theme.DRV_COL_DEVICE)
                assert name_item is not None
                assert _hex_rgb(name_item.foreground().color()) == theme.TEXT.lower()

                win._apply_catalog_row_style(
                    table, 0, tier="culprit", status="newer"
                )
                assert _hex_rgb(_device_bg(table, 0)) == expected["culprit_bg"]

            theme.activate_theme("night")


def test_catalog_pending_rows_use_theme_zebra_on_day_and_manly() -> None:
    """Normal/pending rows must not leave NoBrush (black unreadable stripes on light themes)."""
    zebra_cases = {
        "day": {0: "#f4f5f8", 1: "#ffffff"},
        "manly": {0: "#e6d6f4", 1: "#f0e6fa"},
    }

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            table = win.drv_unified_table
            table.setRowCount(2)
            for row in (0, 1):
                _seed_row(table, row)
            process_events_until(lambda: table.rowCount() == 2, timeout_ms=500)

            for theme_id, expected in zebra_cases.items():
                theme.activate_theme(theme_id)
                win._apply_ui_theme()
                for row in (0, 1):
                    win._apply_catalog_row_style(
                        table, row, tier="normal", status="pending"
                    )
                    bg = _hex_rgb(_device_bg(table, row))
                    assert bg == expected[row], f"{theme_id} row {row}: {bg}"
                    item = table.item(row, theme.DRV_COL_DEVICE)
                    assert item is not None
                    fg = _hex_rgb(item.foreground().color())
                    assert fg == theme.TEXT.lower()

            theme.activate_theme("night")


if __name__ == "__main__":
    test_catalog_row_style_survives_night_day_and_manly_themes()
    test_catalog_pending_rows_use_theme_zebra_on_day_and_manly()
    print("OK")
