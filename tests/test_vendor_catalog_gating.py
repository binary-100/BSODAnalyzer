"""Tests for PC-level manufacturer lookup gating during catalog Search."""

from __future__ import annotations

import bsod_hardware_wmi as hw
import driver_catalog as dc


_AMD_ALIENWARE = {
    "cpu_vendor": "amd",
    "has_amd_chipset": True,
    "has_intel_chipset": False,
    "gpu_vendor": "amd",
    "gpu_vendors_present": {"amd"},
    "hardware_vendors": {
        "network": {"realtek"},
        "audio": {"realtek", "amd"},
        "display": {"amd"},
    },
}


def test_intel_usb_companion_still_allows_intel_lookup() -> None:
    ctx = {
        "cpu_vendor": "amd",
        "has_amd_chipset": True,
        "hardware_vendors": {"usb_controller": {"intel"}},
    }
    assert hw.intel_driver_lookup_applicable(ctx)


def test_pure_amd_system_blocks_intel_manufacturer_tasks() -> None:
    dev_ctx = {
        "vendor_key": "intel",
        "pnp_class": "system",
        "device_label": "intel(r) management engine interface",
    }
    tasks = dc._manufacturer_catalog_tasks_for_ctx(dev_ctx, _AMD_ALIENWARE)
    assert "intel" not in tasks


def test_amd_gpu_row_still_gets_amd_task() -> None:
    dev_ctx = {
        "vendor_key": "amd",
        "pnp_class": "display",
        "device_label": "amd radeon rx 6800m",
    }
    tasks = dc._manufacturer_catalog_tasks_for_ctx(dev_ctx, _AMD_ALIENWARE)
    assert "amd" in tasks
    assert "intel" not in tasks


def test_fetch_intel_returns_empty_when_intel_absent_from_pc() -> None:
    ctx = {
        "vendor_key": "intel",
        "pnp_class": "net",
        "device_label": "intel wi-fi 6 ax201",
        "_catalog_system_ctx": _AMD_ALIENWARE,
    }
    assert dc.fetch_intel_driver_offers(ctx) == []


def test_realtek_row_allowed_on_amd_alienware() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "net",
        "device_label": "realtek gaming 2.5gbe family controller",
        "_catalog_system_ctx": _AMD_ALIENWARE,
    }
    assert dc._manufacturer_vendor_lookup_applicable("realtek", _AMD_ALIENWARE)
    tasks = dc._manufacturer_catalog_tasks_for_ctx(ctx, _AMD_ALIENWARE)
    assert "realtek" in tasks


def test_uncertain_hardware_profile_fails_open() -> None:
    sparse_ctx: dict = {}
    assert dc._manufacturer_vendor_lookup_applicable("intel", sparse_ctx) is True


if __name__ == "__main__":
    test_intel_usb_companion_still_allows_intel_lookup()
    test_pure_amd_system_blocks_intel_manufacturer_tasks()
    test_amd_gpu_row_still_gets_amd_task()
    test_fetch_intel_returns_empty_when_intel_absent_from_pc()
    test_realtek_row_allowed_on_amd_alienware()
    test_uncertain_hardware_profile_fails_open()
    print("vendor catalog gating tests OK")
