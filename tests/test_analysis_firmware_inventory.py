"""Run Analysis should populate firmware inventory like the Drivers tab."""

from __future__ import annotations

from unittest import mock

import bsod_analyzer as core


def test_gather_firmware_inventory_for_gui() -> None:
    pnp = [{"device_id": "PCI\\VEN_1"}]
    drivers = [{"name": "GPU", "version": "1.0"}]
    with mock.patch(
        "bsod_analyzer.get_ssd_firmware_inventory",
        return_value=[{"model": "Samsung SSD", "firmware_revision": "5B2Q"}],
    ), mock.patch(
        "firmware_peripheral_discovery.discover_secondary_firmware_devices",
        return_value=[{"key": "usb:foo", "display_name": "USB Device"}],
    ):
        ssd, secondary = core.gather_firmware_inventory_for_gui(pnp, drivers)
    assert len(ssd) == 1
    assert len(secondary) == 1


def test_build_display_model_includes_firmware_from_system_ctx() -> None:
    fmt_args = (
        [], [], None, [],
        None, [], [],
        "ok", 1, False,
        "user", r"C:\CrashDumps",
        [], {"bios": {"manufacturer": "Dell", "version": "1.0"}},
        {
            "pnp_list": [],
            "ssd_firmware": [{"model": "NVMe", "firmware_revision": "1.1"}],
            "secondary_firmware": [{"key": "x", "display_name": "Y"}],
        },
        [], [],
        {"livekernel": [], "wer_errors": [], "stability_index": None},
    )
    model = core.build_display_model(fmt_args)
    assert len(model["ssd_firmware"]) == 1
    assert len(model["secondary_firmware"]) == 1


if __name__ == "__main__":
    test_gather_firmware_inventory_for_gui()
    test_build_display_model_includes_firmware_from_system_ctx()
    print("OK")
