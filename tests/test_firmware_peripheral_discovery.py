"""Tests for peripheral discovery and installed-version resolution."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import device_enrichment as de
import firmware_peripheral_discovery as fpdisc
import firmware_peripheral_installed as fpinst


def test_resolve_peripheral_display_name_uses_parent() -> None:
    pnp = [
        {
            "Name": "Razer Pro Type Ultra",
            "PNPClass": "USB",
            "DeviceID": r"USB\VID_1532&PID_0277\0001",
        },
        {
            "Name": "HID Keyboard Device",
            "PNPClass": "Keyboard",
            "DeviceID": r"HID\VID_1532&PID_0277&MI_00\9&1",
            "Parent": r"USB\VID_1532&PID_0277\0001",
        },
    ]
    id_map = de.build_pnp_id_to_name_map(pnp)
    hid = dict(pnp[1])
    hid.update(de.pnp_parent_fields_from_row(hid, id_map))
    name = fpdisc.resolve_peripheral_display_name(hid, id_to_name=id_map)
    assert "Pro Type Ultra" in name or "Razer" in name


def test_discover_secondary_usb_peripheral() -> None:
    pnp = [
        {
            "Name": "HID Keyboard Device",
            "PNPClass": "Keyboard",
            "DeviceID": r"HID\VID_1532&PID_0277&MI_00\9&2CE64270&0&0000",
            "Parent": r"USB\VID_1532&PID_0277\0001",
        },
        {
            "Name": "Razer Pro Type Ultra",
            "PNPClass": "USB",
            "DeviceID": r"USB\VID_1532&PID_0277\0001",
        },
    ]
    rows = fpdisc.discover_secondary_firmware_devices(pnp, query_pnp_firmware=False)
    keys = {r["key"] for r in rows}
    assert "peripheral:1532:0277" in keys
    razer = next(r for r in rows if r["key"] == "peripheral:1532:0277")
    assert razer.get("vendor_key") == "razer"


def test_user_confirmed_cache_roundtrip(tmp_path, monkeypatch) -> None:
    path = tmp_path / "firmware_user_confirmed.json"
    monkeypatch.setattr(fpinst, "user_confirmed_path", lambda: path)
    dev = r"HID\VID_1532&PID_0277&MI_00\9&1"
    assert fpinst.save_user_confirmed(dev, "1.03.00_r3")
    cache = fpinst.load_user_confirmed()
    assert cache.get("1532:0277") == "1.03.00_r3"


def test_filter_redundant_winfw_when_bios_present() -> None:
    rows = [
        {
            "key": "winfw:uefi0",
            "category": "windows_firmware",
            "resolved_name": "Microsoft UEFI-Compliant System",
            "installed": "0",
            "installed_source": "pnp_firmware_property",
        },
        {
            "key": "peripheral:046d:c081",
            "category": "usb_peripheral",
            "vid": "046D",
            "pid": "C081",
            "component": "Logitech G900 Gaming Mouse",
        },
    ]
    out = fpdisc.filter_redundant_winfw_devices(rows, has_bios=True)
    assert len(out) == 1
    assert out[0]["key"] == "peripheral:046d:c081"


def test_merge_logitech_g900_and_virtual_keyboard() -> None:
    rows = [
        {
            "key": "peripheral:046d:c081",
            "category": "usb_peripheral",
            "vid": "046D",
            "pid": "C081",
            "component": "Logitech G900 Gaming Mouse",
            "installed": "—",
            "installed_source": "hid_driver",
        },
        {
            "key": "peripheral:046d:c232",
            "category": "usb_peripheral",
            "vid": "046D",
            "pid": "C232",
            "installed": "12.01.13",
            "installed_source": "vendor_app_cache",
        },
    ]
    out = fpdisc.finalize_secondary_firmware_devices(rows, has_bios=False)
    keys = {r["key"] for r in out}
    assert "peripheral:046d:c232" not in keys
    g900 = next(r for r in out if r["key"] == "peripheral:046d:c081")
    assert g900["installed"] == "12.01.13"
    assert g900["installed_source"] == "vendor_app_cache"


if __name__ == "__main__":
    test_resolve_peripheral_display_name_uses_parent()
    test_discover_secondary_usb_peripheral()
    print("ok")
