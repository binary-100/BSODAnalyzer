"""S1: unified WHEA/thermal/reliability near-crash time windows."""

from __future__ import annotations

import bsod_analyzer as core


def test_near_crash_window_constants() -> None:
    assert core._WHEA_NEAR_CRASH_WINDOW_MIN == 10
    assert core._THERMAL_NEAR_CRASH_WINDOW_MIN == 10
    assert core._RELIABILITY_NEAR_CRASH_WINDOW_MIN == 15
    assert core._INCIDENT_WHEA_WINDOW_MIN == 2


def test_whea_window_includes_nine_minute_gap() -> None:
    evt = "2026-05-30 12:00:00"
    crash = ["2026-05-30 12:09:00"]
    assert core._match_event_to_crash(evt, crash, core._WHEA_NEAR_CRASH_WINDOW_MIN)
    assert not core._match_event_to_crash(evt, crash, 8)


def test_incident_window_tighter_than_batch_window() -> None:
    evt = "2026-05-30 12:00:00"
    crash = ["2026-05-30 12:03:00"]
    assert not core._match_event_to_crash(evt, crash, core._INCIDENT_WHEA_WINDOW_MIN)
    assert core._match_event_to_crash(evt, crash, core._WHEA_NEAR_CRASH_WINDOW_MIN)


if __name__ == "__main__":
    test_near_crash_window_constants()
    test_whea_window_includes_nine_minute_gap()
    test_incident_window_tighter_than_batch_window()
    print("S1 time window tests OK")
