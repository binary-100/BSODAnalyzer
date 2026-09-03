"""Tests for analysis data-gap reporting."""

from __future__ import annotations

import bsod_analyzer as core


def test_analysis_gap_message_includes_task_label() -> None:
    msg = core._analysis_gap_message("events", RuntimeError("access denied"))
    assert "Windows crash event log" in msg
    assert "access denied" in msg


def test_analysis_task_labels_cover_gather_keys() -> None:
    for key in (
        "events",
        "windbg_analysis",
        "pnp_list",
        "storage_context",
    ):
        assert key in core._ANALYSIS_TASK_LABELS


def test_minidump_gap_when_dumps_without_bugcheck() -> None:
    msg = core.minidump_without_bugcheck_gap(
        [{"name": "dump.dmp"}],
        [{"type": "KernelPower", "time": "2026-01-01"}],
    )
    assert msg is not None
    assert "1001" in msg
    assert "minidump" in msg.lower()


def test_minidump_gap_suppressed_when_bugcheck_present() -> None:
    msg = core.minidump_without_bugcheck_gap(
        [{"name": "dump.dmp"}],
        [{"type": "BugCheck", "time": "2026-01-01", "code": "0x124"}],
    )
    assert msg is None


def test_minidump_gap_suppressed_when_events_query_failed() -> None:
    msg = core.minidump_without_bugcheck_gap(
        [{"name": "dump.dmp"}],
        [],
        events_query_failed=True,
    )
    assert msg is None


if __name__ == "__main__":
    test_analysis_gap_message_includes_task_label()
    test_analysis_task_labels_cover_gather_keys()
    test_minidump_gap_when_dumps_without_bugcheck()
    test_minidump_gap_suppressed_when_bugcheck_present()
    test_minidump_gap_suppressed_when_events_query_failed()
    print("analysis gaps tests OK")
