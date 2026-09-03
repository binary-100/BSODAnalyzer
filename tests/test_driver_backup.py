"""Driver backup library — manifest, list, prune, zip export."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import driver_backup as drvbackup


def test_default_backup_root_uses_localappdata() -> None:
    root = drvbackup.default_backup_root()
    assert "BSODAnalyzer" in root
    assert root.endswith("driver_backups")


def test_default_backup_root_custom_setting() -> None:
    custom = r"D:\Backups\Drivers"
    root = drvbackup.default_backup_root({"driver_backup_folder": custom})
    assert os.path.normcase(root) == os.path.normcase(os.path.abspath(custom))


def test_backup_keep_count_defaults_to_three() -> None:
    assert drvbackup.backup_keep_count({}) == 3
    assert drvbackup.backup_keep_count({"driver_backup_keep_count": 5}) == 5
    assert drvbackup.backup_keep_count({"driver_backup_keep_count": -1}) == 0


def test_backup_before_install_default_on() -> None:
    assert drvbackup.backup_before_install_default({}) is True
    assert drvbackup.backup_before_install_default({"driver_backup_before_install": False}) is False


def test_list_driver_backups_reads_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        device_dir = Path(tmp) / "Realtek_Audio"
        stamp_dir = device_dir / "20260726_120000"
        stamp_dir.mkdir(parents=True)
        manifest = {
            "device_name": "Realtek Audio",
            "driver_version": "6.0.1.1",
            "backed_up_at": "2026-07-26T12:00:00Z",
            "backed_up_at_local": "2026-07-26 12:00",
            "path": str(stamp_dir),
        }
        (stamp_dir / drvbackup.MANIFEST_NAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        records = drvbackup.list_driver_backups(tmp)
        assert len(records) == 1
        assert records[0]["device_name"] == "Realtek Audio"
        assert records[0]["driver_version"] == "6.0.1.1"


def test_prune_driver_backups_keeps_newest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        device_dir = Path(tmp) / "GPU"
        for name in ("20260101_000000", "20260201_000000", "20260301_000000", "20260401_000000"):
            (device_dir / name).mkdir(parents=True)
        removed, _msg = drvbackup.prune_driver_backups(tmp, keep_per_device=3)
        assert removed == 1
        remaining = [p.name for p in device_dir.iterdir() if p.is_dir()]
        assert len(remaining) == 3
        assert "20260101_000000" not in remaining


def test_export_backup_zip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "dev" / "stamp"
        backup.mkdir(parents=True)
        (backup / "driver.inf").write_text("[Version]\n", encoding="utf-8")
        zip_path = str(Path(tmp) / "out.zip")
        ok, msg = drvbackup.export_backup_zip(str(backup), zip_path)
        assert ok
        assert os.path.isfile(zip_path)
        assert "Exported" in msg


def test_remove_driver_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "dev" / "stamp"
        backup.mkdir(parents=True)
        (backup / "x.txt").write_text("x", encoding="utf-8")
        ok, _msg = drvbackup.remove_driver_backup(str(backup))
        assert ok
        assert not backup.exists()


def test_backup_device_driver_writes_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(
            drvbackup,
            "_query_signed_driver",
            return_value={"InfName": "oem42.inf", "DriverVersion": "1.2.3", "DriverDate": "2026-01-01"},
        ), mock.patch("driver_backup.run_powershell", return_value=(True, "ok")):
            ok, msg, record = drvbackup.backup_device_driver("Test Device", tmp)
        assert ok
        assert record is not None
        assert record["driver_version"] == "1.2.3"
        manifest_path = Path(record["path"]) / drvbackup.MANIFEST_NAME
        assert manifest_path.is_file()
        assert "Backed up" in msg


if __name__ == "__main__":
    test_default_backup_root_uses_localappdata()
    test_default_backup_root_custom_setting()
    test_backup_keep_count_defaults_to_three()
    test_backup_before_install_default_on()
    test_list_driver_backups_reads_manifest()
    test_prune_driver_backups_keeps_newest()
    test_export_backup_zip()
    test_remove_driver_backup()
    test_backup_device_driver_writes_manifest()
    print("driver backup tests OK")
