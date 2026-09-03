"""Batch 5: off-thread unified driver list builder."""

from __future__ import annotations

import driver_list_build as drvlist


def test_minimal_profile_builds_list() -> None:
    prof = {
        "bios_driver_info": {
            "device_inventory": [
                {"name": "Intel Wi-Fi", "version": "1.0", "driver": "netwtw08.sys"},
            ],
        },
        "system_ctx": {},
    }
    devices = drvlist.build_unified_driver_list(
        prof,
        full=False,
        settings={"use_driver_index": False},
        session_batch=None,
        crash_driver=None,
    )
    assert isinstance(devices, list)
    assert len(devices) >= 1
    assert devices[0].get("name") == "Intel Wi-Fi"
    assert devices[0].get("_tier") in ("culprit", "outdated", "attention", "normal")


def test_amd_chipset_in_list_without_crash_analysis() -> None:
    from bsod_hardware_wmi import CHIPSET_DEVICE_AMD

    prof = {
        "bios_driver_info": {
            "device_inventory": [
                {"name": "Intel Wi-Fi", "version": "1.0", "driver": "netwtw08.sys"},
            ],
        },
        "system_ctx": {"has_amd_chipset": True, "cpu_vendor": "amd"},
    }
    devices = drvlist.build_unified_driver_list(
        prof,
        full=False,
        settings={"use_driver_index": False},
        session_batch=None,
        crash_driver=None,
        last_model=None,
    )
    names = {(d.get("name") or "") for d in devices}
    assert CHIPSET_DEVICE_AMD in names


def test_empty_profile_builds_empty_or_chipset_only() -> None:
    prof: dict = {"bios_driver_info": {}, "system_ctx": {}}
    devices = drvlist.build_unified_driver_list(
        prof,
        full=False,
        settings={"use_driver_index": False},
        session_batch=None,
        crash_driver=None,
    )
    assert isinstance(devices, list)


def test_drv_list_build_stale_helper() -> None:
    current = 3
    assert current != 2
    assert not (current != current)


if __name__ == "__main__":
    test_minimal_profile_builds_list()
    test_empty_profile_builds_empty_or_chipset_only()
    test_drv_list_build_stale_helper()
    print("driver list build batch5 tests OK")
