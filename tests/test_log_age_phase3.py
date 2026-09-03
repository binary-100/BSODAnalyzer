"""Phase 3 — log age, historical timeline labels, stale dump separation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_analyzer as core
import log_read_windows as lrw


def test_read_windows_constants() -> None:
    w = lrw.read_windows_as_dict()
    assert w["primary_incident_days"] == 30
    assert w["crash_events"]["wer1001_max"] == 30
    assert w["minidumps"]["analyze_max"] == 3


def test_is_outside_primary_window() -> None:
    assert lrw.is_outside_primary_window(
        "2026-07-01 12:00:00",
        "2026-08-09 20:59:35",
    )
    assert not lrw.is_outside_primary_window(
        "2026-08-08 00:05:27",
        "2026-08-09 20:59:35",
    )


def test_stale_dump_note_includes_file_and_latest() -> None:
    note = lrw.build_stale_dump_note(
        {
            "dump_time": "2026-08-04 17:49:12",
            "dump_file": "080426-18703-01.dmp",
            "faulting_driver": "ntoskrnl.exe",
        },
        latest_incident_date="2026-08-09",
    )
    assert "080426" in note
    assert "ntoskrnl" in note
    assert "2026-08-09" in note
    assert "does not explain" in note


def test_timeline_marks_historical_minidump() -> None:
    events = [{"time": "2026-08-09 20:59:35", "type": "KernelPower", "code_source": "event41_bugcheck"}]
    windbg = {
        "dump_time": "2026-08-04 12:00:00",
        "dump_file": "080426-01.dmp",
        "faulting_driver": "storport.sys",
    }
    dumps = [{"time": "2026-08-04 12:00:00", "name": "080426-01.dmp", "size_mb": 0.3}]
    tl = core.build_incident_timeline(events, windbg_analysis=windbg, kernel_dumps=dumps)
    md = next(e for e in tl["entries"] if e["kind"] == "minidump")
    assert md.get("historical") is True
    assert md.get("relevance") == "historical"
    assert "Historical" in md.get("label", "")
    assert tl.get("stale_dump_note")


def test_log_coverage_includes_read_windows() -> None:
    cov = core.build_event_log_coverage_summary([], [], [], [], {}, [], None)
    assert cov.get("read_window_lines")
    assert cov.get("read_windows")


if __name__ == "__main__":
    test_read_windows_constants()
    test_is_outside_primary_window()
    test_stale_dump_note_includes_file_and_latest()
    test_timeline_marks_historical_minidump()
    test_log_coverage_includes_read_windows()
    print("log age phase 3 tests OK")
