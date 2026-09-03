"""Incident timeline builder and Qt HTML safety."""

from __future__ import annotations

import bsod_analyzer as core
import gui_html_safe as html_safe


def test_incident_timeline_shutdown_without_matching_dump() -> None:
    events = [
        {
            "time": "2026-08-09 20:59:35",
            "type": "KernelPower",
            "code": "0x0000000A",
            "code_source": "event41_bugcheck",
            "note": "Unexpected shutdown",
        },
    ]
    boot = [
        {
            "time": "2026-08-09 21:00:10",
            "type": "BootRecovery",
            "subtype": "KernelBoot",
            "message": "Boot failure",
        },
    ]
    windbg = {
        "dump_time": "2026-08-04 12:00:00",
        "dump_file": "080426-12345-01.dmp",
        "faulting_driver": "storport.sys",
    }
    dumps = [{"time": "2026-08-04 12:00:00", "name": "080426-12345-01.dmp", "size_mb": 0.3}]
    tl = core.build_incident_timeline(
        events,
        reliability_ctx={"boot_recovery": boot},
        windbg_analysis=windbg,
        kernel_dumps=dumps,
    )
    assert tl["newest_dump_mismatch"]
    assert not tl["dump_matches_latest"]
    kinds = {e["kind"] for e in tl["entries"]}
    assert "shutdown" in kinds
    assert "boot_recovery" in kinds
    assert "minidump" in kinds
    shutdown = next(e for e in tl["entries"] if e["kind"] == "shutdown")
    assert shutdown.get("verified_stop") is False


def test_incident_timeline_verified_bugcheck() -> None:
    events = [
        {"time": "2026-08-04 12:00:00", "type": "BugCheck", "code": "0x0000000A"},
    ]
    windbg = {
        "dump_time": "2026-08-04 12:00:00",
        "faulting_driver": "nvlddmkm.sys",
    }
    tl = core.build_incident_timeline(events, windbg_analysis=windbg, kernel_dumps=[])
    assert tl["dump_matches_latest"]
    row = next(e for e in tl["entries"] if e["kind"] == "bugcheck")
    assert row.get("verified_stop") is True


def test_safe_set_html_truncates_and_blocks_reentry() -> None:
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    browser = QtWidgets.QTextBrowser()
    huge = "<p>" + ("x" * (html_safe.MAX_HTML_CHARS + 50)) + "</p>"
    html_safe.safe_set_html(browser, huge)
    assert "truncated" in browser.toPlainText().lower()
    html_safe.safe_set_html(browser, "<p>one</p>")
    html_safe.safe_set_html(browser, "<p>two</p>")
    assert "two" in browser.toPlainText()


if __name__ == "__main__":
    test_incident_timeline_shutdown_without_matching_dump()
    test_incident_timeline_verified_bugcheck()
    test_safe_set_html_truncates_and_blocks_reentry()
    print("incident timeline + html safe tests OK")
