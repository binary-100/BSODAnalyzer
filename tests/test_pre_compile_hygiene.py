"""Pre-compile hygiene — export guard, row a11y, themed warnings."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui_test_harness import offscreen_main_window, process_events_until  # noqa: E402

import gui_theme as theme  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402
from gui_theme import DRV_COL_CHECK, DRV_COL_DEVICE, DRV_COL_ICON, DRV_COL_STATUS  # noqa: E402


def test_export_blocked_while_driver_catalog_running() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._full_report = "crash report body"
            fake_drv = mock.MagicMock()
            fake_drv.isRunning.return_value = True
            win._drv_thread = fake_drv
            with mock.patch.object(
                QtWidgets.QMessageBox, "information"
            ) as info_box, mock.patch.object(
                win, "_resolve_export_file_choices"
            ) as resolve:
                win._export_available_data()
            info_box.assert_called_once()
            assert "search" in info_box.call_args[0][2].lower()
            resolve.assert_not_called()


def test_export_blocked_while_firmware_catalog_running() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._full_report = "crash report body"
            win._drv_thread = None
            fake_fw = mock.MagicMock()
            fake_fw.isRunning.return_value = True
            win._fw_thread = fake_fw
            with mock.patch.object(
                QtWidgets.QMessageBox, "information"
            ) as info_box, mock.patch.object(
                win, "_resolve_export_file_choices"
            ) as resolve:
                win._export_available_data()
            info_box.assert_called_once()
            resolve.assert_not_called()


def test_catalog_row_sets_accessible_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            table = win.drv_unified_table
            table.setRowCount(1)
            device = QtWidgets.QTableWidgetItem("Realtek Audio")
            device.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            table.setItem(0, DRV_COL_DEVICE, device)
            check = QtWidgets.QTableWidgetItem("")
            check.setFlags(
                check.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsEnabled
            )
            check.setCheckState(QtCore.Qt.CheckState.Checked)
            table.setItem(0, DRV_COL_CHECK, check)
            icon = QtWidgets.QTableWidgetItem("")
            table.setItem(0, DRV_COL_ICON, icon)
            win._set_catalog_row_status(
                table, 0, "newer", tier="culprit", version_hint="2.0"
            )
            role = QtCore.Qt.ItemDataRole.AccessibleTextRole
            summary = device.data(role)
            assert summary
            assert "Realtek Audio" in str(summary)
            assert "Crash-related" in str(summary)
            assert "Update available" in str(summary) or "newer" in str(summary).lower()
            status_item = table.item(0, DRV_COL_STATUS)
            assert status_item is not None
            assert status_item.data(role) == summary
            icon_item = table.item(0, DRV_COL_ICON)
            assert icon_item is not None
            assert "Device icon" in str(icon_item.data(role))
            check_item = table.item(0, DRV_COL_CHECK)
            assert check_item is not None
            assert "Include in catalog search" in str(check_item.data(role))


def test_warning_fg_theme_token() -> None:
    theme.activate_theme("night")
    assert theme.WARNING_FG == "#e6a23c"
    theme.activate_theme("day")
    assert theme.WARNING_FG == "#b45309"
    theme.activate_theme("manly")
    assert theme.WARNING_FG == "#9a5a10"
    theme.activate_theme("night")


def test_data_gaps_html_uses_live_warning_color() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            theme.activate_theme("day")
            html = win._plain_english_html(
                {"plain_english": "Summary.", "data_gaps": ["Minidump unreadable"]}
            )
            assert theme.WARNING_FG in html
            assert "#e6a23c" not in html
            theme.activate_theme("night")


if __name__ == "__main__":
    test_export_blocked_while_driver_catalog_running()
    test_export_blocked_while_firmware_catalog_running()
    test_catalog_row_sets_accessible_summary()
    test_warning_fg_theme_token()
    test_data_gaps_html_uses_live_warning_color()
    print("OK")
