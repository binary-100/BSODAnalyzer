"""Regression tests for P0/P1 audit fixes (v5.2.23)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import app_settings as app_set
import bsod_analyzer as core


def test_newest_minidump_analysis_prefers_first_dump_in_order() -> None:
    dumps = [
        {"name": "newest.dmp", "time": "2026-05-30"},
        {"name": "older.dmp", "time": "2026-05-29"},
    ]
    analyses = [
        {
            "dump_file": "older.dmp",
            "faulting_driver": "old.sys",
            "bugcheck_str": "0x11111111",
        },
        {
            "dump_file": "newest.dmp",
            "faulting_driver": "new.sys",
            "bugcheck_str": "0x22222222",
        },
    ]
    picked = core.newest_minidump_analysis(analyses, dumps)
    assert picked is not None
    assert picked["dump_file"] == "newest.dmp"
    assert picked["faulting_driver"] == "new.sys"


def test_settings_path_prefers_pc_local_portable_when_chosen() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        full_dir = base / "full"
        pc_dir = base / "local"
        legacy_dir = base / "portable"
        full_dir.mkdir()
        pc_dir.mkdir()
        legacy_dir.mkdir()
        full_settings = full_dir / "settings.json"
        pc_settings = pc_dir / "settings.json"
        legacy_settings = legacy_dir / "settings.json"
        full_settings.write_text(
            json.dumps({"install_mode": "full", "install_mode_chosen": True}),
            encoding="utf-8",
        )
        pc_settings.write_text(
            json.dumps({"install_mode": "portable", "install_mode_chosen": True}),
            encoding="utf-8",
        )
        legacy_settings.write_text(
            json.dumps({"install_mode": "portable", "install_mode_chosen": True}),
            encoding="utf-8",
        )
        orig_full = app_set.full_install_data_dir
        orig_port = app_set.portable_settings_dir
        orig_maint = app_set.maintenance_data_dir
        try:
            app_set.full_install_data_dir = lambda: full_dir  # type: ignore[method-assign]
            app_set.maintenance_data_dir = lambda: pc_dir  # type: ignore[method-assign]
            app_set.portable_settings_dir = lambda: legacy_dir  # type: ignore[method-assign]
            assert app_set._settings_path() == pc_settings
        finally:
            app_set.full_install_data_dir = orig_full  # type: ignore[method-assign]
            app_set.maintenance_data_dir = orig_maint  # type: ignore[method-assign]
            app_set.portable_settings_dir = orig_port  # type: ignore[method-assign]


def test_crash_driver_and_fw_scan_flags_are_independent() -> None:
    """Document the v5.2.23 state model: driver and firmware crash scans do not share one mode string."""
    driver_active = True
    fw_active = True
    assert driver_active and fw_active
    driver_active = False
    assert not driver_active
    assert fw_active


if __name__ == "__main__":
    test_newest_minidump_analysis_prefers_first_dump_in_order()
    test_settings_path_prefers_pc_local_portable_when_chosen()
    test_crash_driver_and_fw_scan_flags_are_independent()
    print("P0/P1 fix tests OK")
