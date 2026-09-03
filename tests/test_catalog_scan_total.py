"""Driver scan progress total aligns with catalog-scannable device count."""

from __future__ import annotations

import bsod_gui_qt as gui


def test_catalog_scannable_device_names_deduplicates() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._hardware_profile = {
        "pnp_list": [],
        "bios_driver_info": {},
        "system_ctx": {},
    }
    names = ["Realtek Audio", "Realtek Audio", "Intel Wi-Fi"]
    scannable = win._catalog_scannable_device_names(names)
    assert scannable == ["Realtek Audio", "Intel Wi-Fi"]


def test_catalog_scannable_count_never_exceeds_include_list() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._hardware_profile = {
        "pnp_list": [],
        "bios_driver_info": {},
        "system_ctx": {},
    }
    names = [f"Device {i}" for i in range(142)]
    scannable = win._catalog_scannable_device_names(names)
    assert len(scannable) <= len(names)


if __name__ == "__main__":
    test_catalog_scannable_device_names_deduplicates()
    test_catalog_scannable_count_never_exceeds_include_list()
    print("OK")
