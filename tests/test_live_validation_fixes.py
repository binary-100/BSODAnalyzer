"""Tests for live-validation fixes: CDB engine detection and boot/crash correlation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_analyzer as core


def test_boot_events_near_crash_searches_full_list() -> None:
    boot = [{"time": f"2026-08-12 02:3{i}:00", "message": "recent"} for i in range(8)]
    boot.append({"time": "2026-08-09 20:59:44", "message": "wininit near crash"})
    near = core.boot_events_near_crash(
        boot,
        ["2026-08-09 20:59:46", "2026-08-09 20:59:35"],
        window_minutes=15,
    )
    assert len(near) == 1
    assert near[0]["time"].startswith("2026-08-09")


def test_cdb_engine_usable_requires_ext_dll() -> None:
    local = core._get_local_cdb_path()
    if os.path.isfile(local):
        has_ext = os.path.isfile(os.path.join(os.path.dirname(local), "winext", "ext.dll"))
        assert core._cdb_engine_usable(local) is has_ext
    assert core._cdb_engine_usable(None) is False


def test_find_cdb_skips_incomplete_local_engine() -> None:
    core.clear_cdb_path_cache()
    path = core.find_cdb()
    if path:
        assert core._cdb_engine_usable(path)


def test_capture_readiness_shape() -> None:
    r = core.build_capture_readiness(
        needs_config=False,
        dump_config="Small memory dump (minidump)",
        kernel_dumps=[{"time": "2026-08-04 17:49:12", "name": "x.dmp"}],
        events=[{"time": "2026-08-09 20:59:46", "type": "KernelPower"}],
        windbg_analysis={"dump_time": "2026-08-04 17:49:12"},
        cdb_path=core.find_cdb(),
    )
    assert len(r.get("checks") or []) >= 4
    assert r.get("dump_matches_latest") is False
    keys = {c["key"] for c in r["checks"]}
    assert "admin" in keys and "dumps" in keys and "cdb" in keys


def test_repair_local_cdb_skips_when_usable() -> None:
    local = core._get_local_cdb_path()
    if os.path.isfile(local) and core._cdb_engine_usable(local):
        ok, msg = core.repair_local_cdb_engine_if_needed()
        assert ok is False
        assert "already" in msg.lower()


def test_repair_local_cdb_integration() -> None:
    """When local copy lacks ext.dll and WinDbg app exists, repair succeeds."""
    local = core._get_local_cdb_path()
    if not os.path.isfile(local):
        return
    if core._cdb_engine_usable(local):
        return
    if not core._find_windbg_app_engine_dir():
        return
    core.clear_cdb_path_cache()
    ok, msg = core.repair_local_cdb_engine_if_needed()
    assert ok is True, msg
    assert core._cdb_engine_usable(core._get_local_cdb_path())
    assert core.find_cdb() and "DebuggingTools" in (core.find_cdb() or "")


if __name__ == "__main__":
    test_boot_events_near_crash_searches_full_list()
    test_cdb_engine_usable_requires_ext_dll()
    test_find_cdb_skips_incomplete_local_engine()
    test_capture_readiness_shape()
    test_repair_local_cdb_skips_when_usable()
    test_repair_local_cdb_integration()
    print("live validation fix tests OK")
