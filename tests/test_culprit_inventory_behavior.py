"""Culprit inventory refresh and scan queue helper regression tests."""

from __future__ import annotations

import bsod_analyzer as core
from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL


def test_culprit_info_improves_with_full_inventory() -> None:
    driver = "nvlddmkm.sys"
    thin = [
        {
            "name": "USB Root Hub",
            "driver": "usbhub.sys",
            "device_class": "USB",
            "version": "10.0.0.0",
        },
    ]
    full = thin + [
        {
            "name": "NVIDIA GeForce RTX 4070",
            "driver": "nvlddmkm.sys",
            "device_class": "DISPLAY",
            "version": "31.0.15.4601",
            "date": "2024-01-01",
        },
    ]
    thin_info = core.get_culprit_device_driver_info(driver, thin)
    full_info = core.get_culprit_device_driver_info(driver, full)
    assert thin_info[0]["name"].startswith("Device for module")
    assert full_info[0]["name"] == "NVIDIA GeForce RTX 4070"
    assert full_info[0]["version"] == "31.0.15.4601"


def test_platform_chipset_keys_excluded_from_bulk_scan_helpers() -> None:
    assert core.is_platform_chipset_device_key(CHIPSET_DEVICE_AMD)
    assert core.is_platform_chipset_device_key(CHIPSET_DEVICE_INTEL)
    assert not core.is_platform_chipset_device_key("NVIDIA GeForce RTX 4070")
    assert not core.is_crash_synthetic_device_key(CHIPSET_DEVICE_AMD)


def test_crash_report_names_use_inventory_before_cache() -> None:
    driver = "nvlddmkm.sys"
    bio = {
        "drivers": [
            {
                "name": "NVIDIA GeForce RTX 3080",
                "driver": "nvlddmkm.sys",
                "device_class": "DISPLAY",
            },
        ],
    }
    names = core.find_culprit_devices(
        core.device_inventory_for_matching(bio), driver
    )
    assert "NVIDIA GeForce RTX 3080" in names


if __name__ == "__main__":
    test_culprit_info_improves_with_full_inventory()
    test_platform_chipset_keys_excluded_from_bulk_scan_helpers()
    test_crash_report_names_use_inventory_before_cache()
    print("Culprit inventory behavior tests OK")
