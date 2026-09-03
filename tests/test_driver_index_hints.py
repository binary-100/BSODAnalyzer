"""Driver index: hints vs verified scan (item #6)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import driver_index as drvidx


def _patch_db(tmp: str):
    drvidx._reset_session_flags()
    return mock.patch.object(drvidx, "_db_path", return_value=Path(tmp) / "idx.sqlite")


def test_apply_index_hints_does_not_set_check_status() -> None:
    devices = [{"name": "Test GPU", "_check_status": "pending", "_scan_verified": False}]
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result(
                "Test GPU",
                "newer",
                installed_version="1.0",
                detail=json.dumps({"offers": [{"version": "2.0"}]}),
            )
            drvidx.apply_index_hints_to_devices(devices, {"use_driver_index": True})
        drvidx._reset_session_flags()
    assert devices[0].get("_index_last_status") == "newer"
    assert devices[0].get("_check_status") == "pending"
    assert not devices[0].get("_scan_verified")


def test_apply_index_hints_skips_verified_devices() -> None:
    devices = [
        {
            "name": "Verified GPU",
            "_check_status": "same",
            "_scan_verified": True,
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result("Verified GPU", "newer", detail="{}")
            drvidx.apply_index_hints_to_devices(devices, {"use_driver_index": True})
        drvidx._reset_session_flags()
    assert "_index_last_status" not in devices[0]


def test_catalog_entry_from_index_restores_offers() -> None:
    offers = [{"source": "microsoft", "version": "9.9", "vs_installed": "newer"}]
    detail = json.dumps({"offers": offers})
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result(
                "My Device",
                "newer",
                installed_version="1.0",
                detail=detail,
            )
            entry = drvidx.catalog_entry_from_index("My Device")
        drvidx._reset_session_flags()
    assert entry is not None
    assert entry.get("_from_index") is True
    assert len(entry.get("offers") or []) == 1


def test_entry_with_index_firmware_packages_fills_empty_offers() -> None:
    offers = [{"kind": "bios", "version": "F20", "vs_installed": "newer"}]
    detail = json.dumps({"offers": offers})
    session = {
        "target_key": "bios",
        "installed_version": "F10",
        "offers": [],
        "status": "newer",
    }
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_firmware_check(
                "bios",
                "newer",
                installed_version="F10",
                detail=detail,
            )
            merged = drvidx.entry_with_index_firmware_packages(session, "bios")
        drvidx._reset_session_flags()
    assert merged is not None
    assert len(merged.get("offers") or []) == 1


def test_entry_with_index_packages_fills_empty_offers() -> None:
    offers = [{"source": "microsoft", "version": "2.0", "vs_installed": "newer"}]
    detail = json.dumps({"offers": offers})
    session = {
        "device_name": "My Device",
        "installed_version": "1.0",
        "offers": [],
        "status": "newer",
    }
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result(
                "My Device",
                "newer",
                installed_version="1.0",
                detail=detail,
            )
            merged = drvidx.entry_with_index_packages(session, "My Device")
        drvidx._reset_session_flags()
    assert merged is not None
    assert len(merged.get("offers") or []) == 1


def test_apply_index_hints_alias_equivalent() -> None:
    devices = [{"name": "Alias Dev", "_check_status": "pending"}]
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result("Alias Dev", "newer", detail="{}")
            drvidx.apply_index_hints_to_devices(devices, {"use_driver_index": True})
        drvidx._reset_session_flags()
    assert devices[0].get("_index_last_status") == "newer"
    assert devices[0]["_check_status"] == "pending"


if __name__ == "__main__":
    test_apply_index_hints_does_not_set_check_status()
    test_apply_index_hints_skips_verified_devices()
    test_catalog_entry_from_index_restores_offers()
    test_entry_with_index_firmware_packages_fills_empty_offers()
    test_entry_with_index_packages_fills_empty_offers()
    test_apply_index_hints_alias_equivalent()
    print("driver index hints tests OK")
