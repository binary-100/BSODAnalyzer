"""Heuristic for distinguishing full WMI driver inventory from analysis subset."""

from __future__ import annotations


def driver_list_looks_full(rows: list, prof: dict | None) -> bool:
    """Mirror MainWindow._driver_list_looks_full (no Qt)."""
    if len(rows) < 5:
        return False
    bio = (prof or {}).get("bios_driver_info") or {}
    inv = bio.get("device_inventory") or bio.get("drivers") or []
    if inv and len(rows) <= max(len(inv), 12):
        return False
    return True


def test_subset_inventory_not_full() -> None:
    inv = [{"name": f"dev{i}"} for i in range(20)]
    prof = {"bios_driver_info": {"device_inventory": inv}}
    assert not driver_list_looks_full(inv, prof)


def test_large_list_is_full() -> None:
    inv = [{"name": f"dev{i}"} for i in range(20)]
    all_rows = [{"name": f"dev{i}"} for i in range(120)]
    prof = {"bios_driver_info": {"device_inventory": inv, "all_drivers": all_rows}}
    assert driver_list_looks_full(all_rows, prof)


def test_tiny_list_never_full() -> None:
    prof = {"bios_driver_info": {"device_inventory": [{"name": "GPU"}]}}
    assert not driver_list_looks_full([{"name": "GPU"}], prof)


def test_build_unified_driver_list_excludes_firmware_class() -> None:
    import driver_list_build as dl

    prof = {
        "bios_driver_info": {
            "all_drivers": [
                {
                    "name": "Realtek(R) Audio",
                    "version": "6.0.9929.1",
                    "device_class": "MEDIA",
                },
                {
                    "name": "Device Firmware",
                    "version": "0.1.16",
                    "device_class": "FIRMWARE",
                },
            ],
        },
        "system_ctx": {},
    }
    devices = dl.build_unified_driver_list(
        prof,
        full=True,
        settings={},
        session_batch=None,
        crash_driver=None,
    )
    names = {(d.get("name") or "").lower() for d in devices}
    assert "realtek(r) audio" in names
    assert "device firmware" not in names


if __name__ == "__main__":
    test_subset_inventory_not_full()
    test_large_list_is_full()
    test_tiny_list_never_full()
    test_build_unified_driver_list_excludes_firmware_class()
    print("OK")
