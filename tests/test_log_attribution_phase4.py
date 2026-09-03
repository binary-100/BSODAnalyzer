"""Tests for Phase 4 extended log attribution (WER, setupapi, CBS)."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_analyzer as core
import driver_verification as dv
import log_attribution as la


def _write_wer_report(base: str, folder_name: str, text: str) -> str:
    folder = os.path.join(base, folder_name)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "Report.wer")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def test_scan_wer_folder_extracts_module() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _write_wer_report(
            tmp,
            "Report001",
            "EventType=BlueScreen\n"
            "EventTime=2026-08-09 20:59:46\n"
            "BucketId=DRIVER_IRQL_NOT_LESS_OR_EQUAL_storport.sys_abc\n",
        )
        hints = la._scan_wer_folder(tmp, source_label="ReportArchive")
        assert len(hints) == 1
        assert hints[0]["module"] == "storport.sys"
        assert hints[0]["event_time"].startswith("2026-08-09")


def test_classify_wer_hints_marks_historical() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35"}]
    wer_hints = [
        {"module": "storport.sys", "event_time": "2026-08-04 12:00:00", "wer_source": "ReportArchive"},
        {"module": "amdkmdag.sys", "event_time": "2026-08-09 20:59:40", "wer_source": "ReportArchive"},
    ]
    enriched, latest = la.classify_wer_hints_for_incidents(wer_hints, events)
    hist = [h for h in enriched if h["module"] == "storport.sys"][0]
    assert hist["historical"] is True
    assert hist["matches_latest_incident"] is False
    assert any(h["module"] == "amdkmdag.sys" for h in latest)


def test_setupapi_scan_finds_near_incident_change() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_path = os.path.join(tmp, "setupapi.dev.log")
        content = (
            ">>>  [Device Install]\n"
            ">>>  Section start 2026/08/09 18:30:15.123\n"
            "     inf: Installing driver package C:\\Windows\\System32\\drivers\\amdkmdag.sys\n"
        )
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        old = la.SETUPAPI_DEV_LOG
        la.SETUPAPI_DEV_LOG = log_path
        try:
            rows = la.scan_setupapi_dev_log("2026-08-09 20:59:35")
            assert rows
            assert "amdkmdag.sys" in (rows[0].get("driver_ref") or "")
        finally:
            la.SETUPAPI_DEV_LOG = old


def test_cbs_scan_finds_pending_restart() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_path = os.path.join(tmp, "CBS.log")
        content = (
            "2026-08-09 19:00:01, Info CBS Package pending restart is set.\n"
            "2026-08-09 19:00:02, Info CBS Failed to execute advanced installer phase.\n"
        )
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        old = la.CBS_LOG
        la.CBS_LOG = log_path
        try:
            hints = la.scan_cbs_hints("2026-08-09 20:59:35")
            assert hints
            categories = {h["category"] for h in hints}
            assert any("pending restart" in c.lower() for c in categories)
        finally:
            la.CBS_LOG = old


def test_collect_extended_log_attribution_shape() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35"}]
    windbg = {"faulting_driver": "ntoskrnl.exe", "dump_time": "2026-08-04 12:00:00"}
    bundle = la.collect_extended_log_attribution(events, windbg_analysis=windbg)
    assert "wer_module_hints" in bundle
    assert "latest_incident_wer_hints" in bundle
    assert "setupapi_changes" in bundle
    assert "cbs_hints" in bundle
    assert "sources_scanned" in bundle
    assert bundle["dump_matches_latest"] is False


def test_suspect_list_includes_extended_wer_hint() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35"}]
    system_ctx = {
        "extended_log_attribution": {
            "latest_incident_wer_hints": [
                {
                    "module": "storport.sys",
                    "event_time": "2026-08-09 20:59:40",
                    "historical": False,
                    "wer_source": "ReportArchive",
                }
            ]
        }
    }
    suspects = dv.build_crash_suspect_list(events, None, system_ctx=system_ctx)
    modules = [s["module"] for s in suspects]
    assert "storport" in modules


def test_narrative_wer_hint_when_no_dump() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35"}]
    system_ctx = {
        "extended_log_attribution": {
            "latest_incident_wer_hints": [
                {
                    "module": "storport.sys",
                    "event_time": "2026-08-09 20:59:40",
                    "historical": False,
                    "wer_source": "ReportArchive",
                }
            ],
            "context_lines": ["WER archived report(s) near the latest incident suggest: storport.sys"],
            "action_steps": [],
        }
    }
    n = dv.build_crash_repair_narrative(events, None, system_ctx=system_ctx)
    summary = (n.get("what_failed") or {}).get("summary") or ""
    assert "storport.sys" in summary
    assert "Windows Error Reporting" in summary or "Directed" in summary.lower()
    assert n.get("context_notes")


def test_timeline_includes_wer_attribution_rows() -> None:
    events = [{"type": "KernelPower", "time": "2026-08-09 20:59:35", "code": "N/A"}]
    ext = {
        "wer_module_hints": [
            {
                "module": "storport.sys",
                "event_time": "2026-08-04 12:00:00",
                "historical": True,
                "matches_latest_incident": False,
                "wer_source": "ReportArchive",
                "bucket": "test",
            }
        ],
        "setupapi_changes": [],
        "cbs_hints": [],
    }
    tl = core.build_incident_timeline(events, extended_log_attribution=ext)
    kinds = {e.get("kind") for e in tl.get("entries") or []}
    assert "wer_attribution" in kinds


if __name__ == "__main__":
    tests = [
        test_scan_wer_folder_extracts_module,
        test_classify_wer_hints_marks_historical,
        test_setupapi_scan_finds_near_incident_change,
        test_cbs_scan_finds_pending_restart,
        test_collect_extended_log_attribution_shape,
        test_suspect_list_includes_extended_wer_hint,
        test_narrative_wer_hint_when_no_dump,
        test_timeline_includes_wer_attribution_rows,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    raise SystemExit(1 if failed else 0)
