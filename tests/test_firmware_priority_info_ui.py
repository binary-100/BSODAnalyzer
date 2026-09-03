"""Firmware tab — stop-code priority row ⓘ tooltip (Drivers tab parity)."""

from __future__ import annotations

import bsod_gui_qt as gui
from gui_theme import DRV_CRASH_INFO_TOOLTIP_ROLE
from PySide6 import QtWidgets


def test_ssd_culprit_row_gets_priority_info_tooltip() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._last_model = {"stop_code_val": 0x7A}
    ent = {
        "key": "ssd:Samsung SSD 990 PRO 4TB",
        "component": "SSD — Samsung SSD 990 PRO 4TB",
        "_tier": "culprit",
        "_check_status": "pending",
    }
    tip = win._firmware_priority_info_tooltip(ent)
    assert "storage-related" in tip
    assert "does not mean the drive caused the crash" in tip
    assert "0x0000007A" in tip
    assert "Not checked" in tip

    item = QtWidgets.QTableWidgetItem(ent["component"])
    win._apply_firmware_priority_info_tooltip(item, ent)
    assert item.data(DRV_CRASH_INFO_TOOLTIP_ROLE) == tip


def test_non_culprit_firmware_row_clears_info_tooltip() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._last_model = {"stop_code_val": 0x7A}
    ent = {
        "key": "ssd:Samsung SSD 990 PRO 4TB",
        "_tier": "normal",
        "_check_status": "pending",
    }
    item = QtWidgets.QTableWidgetItem("SSD")
    win._apply_firmware_priority_info_tooltip(item, ent)
    assert item.data(DRV_CRASH_INFO_TOOLTIP_ROLE) is None


def test_bios_culprit_tooltip_mentions_bios_not_fault() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._last_model = {"stop_code_val": 0x124}
    ent = {"key": "bios", "_tier": "culprit", "_check_status": "pending"}
    tip = win._firmware_priority_info_tooltip(ent)
    assert "BIOS" in tip
    assert "not because BIOS is known to be faulty" in tip


if __name__ == "__main__":
    test_ssd_culprit_row_gets_priority_info_tooltip()
    test_non_culprit_firmware_row_clears_info_tooltip()
    test_bios_culprit_tooltip_mentions_bios_not_fault()
    print("OK")
