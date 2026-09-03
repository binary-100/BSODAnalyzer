"""Driver index batch read/write (Track B v5.2.24)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import driver_index as drvidx


def _patch_db(tmp: str):
    drvidx._reset_session_flags()
    return mock.patch.object(drvidx, "_db_path", return_value=Path(tmp) / "idx.sqlite")


def test_record_batch_results_single_transaction() -> None:
    devices = [
        {
            "device_name": f"Device {i}",
            "status": "newer",
            "installed_version": "1.0",
            "offers": [{"version": f"{i}.0"}],
        }
        for i in range(5)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.record_batch_results(devices, fetched_at="2026-05-30T12:00:00Z")
            stats = drvidx.index_stats()
        drvidx._reset_session_flags()
    assert stats["total"] == 5
    assert stats["outdated"] == 5


def test_get_cached_status_batch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result(
                "Alpha GPU",
                "newer",
                detail=json.dumps({"offers": [{"version": "2.0"}]}),
            )
            drvidx.save_check_result("Beta NIC", "same", detail="{}")
            batch = drvidx.get_cached_status_batch(["Alpha GPU", "Beta NIC", "Missing"])
        drvidx._reset_session_flags()
    assert "alpha gpu" in batch
    assert batch["alpha gpu"]["status"] == "newer"
    assert "beta nic" in batch
    assert "missing" not in batch


def test_apply_index_hints_uses_batch() -> None:
    devices = [
        {"name": "Batch A", "_check_status": "pending"},
        {"name": "Batch B", "_check_status": "pending"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.save_check_result("Batch A", "newer", detail="{}")
            drvidx.save_check_result("Batch B", "same", detail="{}")
            drvidx.apply_index_hints_to_devices(devices, {"use_driver_index": True})
        drvidx._reset_session_flags()
    assert devices[0]["_index_last_status"] == "newer"
    assert devices[1]["_index_last_status"] == "same"


def test_record_firmware_checks_batch() -> None:
    checks = [
        {
            "target_key": "bios",
            "status": "newer",
            "installed_version": "F10",
            "offers": [{"version": "F20"}],
            "target_label": "BIOS",
        },
        {
            "target_key": "ssd:Samsung SSD",
            "status": "same",
            "installed_version": "1.0",
            "offers": [],
            "target_label": "SSD",
        },
    ]
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_db(tmp):
            drvidx.record_firmware_checks_batch(
                checks, fetched_at="2026-05-30T12:00:00Z"
            )
            stats = drvidx.index_stats()
            cached = drvidx.get_firmware_cached_batch(["bios", "ssd:Samsung SSD"])
        drvidx._reset_session_flags()
    assert stats["firmware"] == 2
    assert cached["bios"]["status"] == "newer"


def test_migrate_legacy_single_transaction() -> None:
    import json

    legacy_data = {
        "driver:Alpha GPU": {
            "kind": "driver",
            "status": "newer",
            "installed_version": "1.0",
            "fetched_at": "2026-05-30T12:00:00Z",
        },
        "driver:Beta NIC": {
            "kind": "driver",
            "status": "same",
            "installed_version": "2.0",
            "fetched_at": "2026-05-30T12:00:00Z",
        },
        "firmware:bios": {
            "kind": "firmware",
            "status": "newer",
            "installed_version": "F10",
            "fetched_at": "2026-05-30T12:00:00Z",
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "appdata"
        data_dir.mkdir()
        legacy = data_dir / "check_cache.json"
        legacy.write_text(json.dumps(legacy_data), encoding="utf-8")
        drvidx._reset_session_flags()
        with (
            mock.patch(
                "driver_index.app_set.full_install_data_dir", return_value=data_dir
            ),
            mock.patch(
                "driver_index.app_set.allows_persistent_driver_data",
                return_value=True,
            ),
        ):
            assert drvidx.migrate_legacy_check_cache() is True
            assert not legacy.is_file()
            stats = drvidx.index_stats()
            cached = drvidx.get_cached_status_batch(["Alpha GPU", "Beta NIC"])
            fw_cached = drvidx.get_firmware_cached_batch(["bios"])
        drvidx._reset_session_flags()
    assert stats["total"] == 2
    assert stats["firmware"] == 1
    assert cached["alpha gpu"]["status"] == "newer"
    assert cached["beta nic"]["status"] == "same"
    assert fw_cached["bios"]["status"] == "newer"


if __name__ == "__main__":
    test_record_batch_results_single_transaction()
    test_get_cached_status_batch()
    test_apply_index_hints_uses_batch()
    test_record_firmware_checks_batch()
    test_migrate_legacy_single_transaction()
    print("driver index batch tests OK")
