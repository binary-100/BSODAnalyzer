"""Tests for Phase 2e minidump prerequisites and Phase 2f WER dump recovery."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_analyzer as core


def test_expand_windows_path() -> None:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    assert core._expand_windows_path("%SystemRoot%\\Minidump") == os.path.join(root, "Minidump")


def test_get_minidump_search_directories_includes_default() -> None:
    settings = {"minidump_dir": core.MINIDUMP_DIR, "minidump_dir_registry": None}
    dirs = core.get_minidump_search_directories(settings)
    assert core.MINIDUMP_DIR in dirs


def test_assess_minidump_prerequisites_shape() -> None:
    settings = {
        "minidump_dir": core.MINIDUMP_DIR,
        "minidump_dir_registry": None,
        "crash_dump_enabled": 1,
        "dump_type_label": "Small memory dump (minidump)",
        "registry_read_ok": True,
    }
    prereqs = core.assess_minidump_prerequisites(settings)
    assert "folder_writable" in prereqs
    assert "free_space_mb" in prereqs
    assert "directories" in prereqs


def test_reconcile_relocates_missing_dump_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dump_name = "082609-12345-01.dmp"
        dump_path = os.path.join(tmp, dump_name)
        with open(dump_path, "wb") as handle:
            handle.write(b"MDMP")
        cited = os.path.join(r"C:\Windows\Minidump", dump_name)
        events = [
            {
                "type": "BugCheck",
                "code_source": "wer1001",
                "time": "2026-08-09 20:59:46",
                "dump": cited,
            }
        ]
        recovery = core.reconcile_wer_dumpfile_gaps(events, [], [tmp])
        assert recovery["recovered_count"] == 1
        merged = core.merge_recovered_kernel_dumps([], recovery)
        assert len(merged) == 1
        assert os.path.normcase(merged[0]["path"]) == os.path.normcase(dump_path)
        assert events[0]["dump_recovered"] == "relocated"


def test_module_from_wer_bucket() -> None:
    mod = core._module_from_wer_bucket("DRIVER_IRQL_NOT_LESS_OR_EQUAL_storport.sys_abc")
    assert mod == "storport.sys"


def test_parse_report_wer() -> None:
    text = "EventType=BlueScreen\nDumpFile=C:\\Windows\\Minidump\\test.dmp\nBucketId=foo_nvlddmkm.sys_bar"
    parsed = core.parse_report_wer(text)
    assert parsed["EventType"] == "BlueScreen"
    assert core._wer_report_module_hint(parsed) == "nvlddmkm.sys"


def test_capture_readiness_includes_disk_check_when_space_known() -> None:
    prereqs = {
        "effective_dir": core.MINIDUMP_DIR,
        "folder_writable": True,
        "dir_detail": core.MINIDUMP_DIR,
        "free_space_mb": 10000.0,
        "disk_ok": True,
        "disk_warn": False,
        "disk_detail": "10000 MB free",
        "action_steps": [],
    }
    r = core.build_capture_readiness(
        needs_config=False,
        dump_config="Small memory dump",
        kernel_dumps=[],
        events=[],
        windbg_analysis=None,
        minidump_prereqs=prereqs,
    )
    keys = {c["key"] for c in r["checks"]}
    assert "disk_space" in keys
    assert "minidump_dir" in keys


def test_live_validate_output_schema() -> None:
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "live_validate_analysis.py"
    spec = importlib.util.spec_from_file_location("live_validate_analysis", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    sample = {
        "version": core.VERSION,
        "admin": True,
        "needs_config": False,
        "dump_val": 1,
        "kernel_dump_count": 1,
        "windbg_summary": {"dumps_analyzed": 1},
        "repair_narrative": {"what_happened": "Test incident."},
        "capture_readiness": {
            "checks": [
                {"key": k, "ok": True}
                for k in ("admin", "dumps", "cdb", "minidump_dir", "disk_space", "dump_match")
            ],
            "minidump_prerequisites": {
                "effective_dir": core.MINIDUMP_DIR,
                "folder_writable": True,
                "free_space_mb": 1000.0,
                "directories": [core.MINIDUMP_DIR],
            },
        },
    }
    assert mod.validate_live_output(sample) == []
    bad = dict(sample)
    bad["capture_readiness"] = {"checks": [{"key": "admin", "ok": True}]}
    assert mod.validate_live_output(bad)


if __name__ == "__main__":
    test_expand_windows_path()
    test_get_minidump_search_directories_includes_default()
    test_assess_minidump_prerequisites_shape()
    test_reconcile_relocates_missing_dump_path()
    test_module_from_wer_bucket()
    test_parse_report_wer()
    test_capture_readiness_includes_disk_check_when_space_known()
    test_live_validate_output_schema()
    print("minidump prerequisite tests OK")
