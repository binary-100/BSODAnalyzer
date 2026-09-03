"""Firmware tab Verify manually / filter rules (mirrors Drivers tab)."""

from __future__ import annotations


def fw_passes_uncertain(ent: dict) -> bool:
    """Mirror MainWindow._fw_passes_view_filter mode == 'uncertain'."""
    return bool(ent.get("_scan_verified")) and (ent.get("_check_status") or "") == "uncertain"


def fw_passes_updates(ent: dict) -> bool:
    return bool(ent.get("_scan_verified")) and (ent.get("_check_status") or "") == "newer"


def test_uncertain_filter_matches_verify_manually_components() -> None:
    assert fw_passes_uncertain({"_scan_verified": True, "_check_status": "uncertain"})
    assert not fw_passes_uncertain({"_scan_verified": True, "_check_status": "newer"})
    assert not fw_passes_uncertain({"_scan_verified": True, "_check_status": "same"})
    assert not fw_passes_uncertain({"_check_status": "uncertain"})


def test_updates_requires_verified_newer() -> None:
    assert fw_passes_updates({"_scan_verified": True, "_check_status": "newer"})
    assert not fw_passes_updates({"_scan_verified": True, "_check_status": "uncertain"})


if __name__ == "__main__":
    test_uncertain_filter_matches_verify_manually_components()
    test_updates_requires_verified_newer()
    print("OK")
