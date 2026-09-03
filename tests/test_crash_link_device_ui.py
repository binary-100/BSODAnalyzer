"""Crash-linked driver row UI — highlight rules and info tooltip copy."""

from __future__ import annotations

import bsod_gui_qt as gui


def test_crash_linked_up_to_date_uses_current_highlight() -> None:
    assert (
        gui.MainWindow._catalog_row_highlight_kind(
            "culprit", "same", crash_linked=True, scan_verified=True
        )
        == "current"
    )
    assert (
        gui.MainWindow._catalog_row_highlight_kind(
            "normal", "same", crash_linked=True, scan_verified=True
        )
        == "current"
    )


def test_crash_linked_needs_update_stays_culprit() -> None:
    assert (
        gui.MainWindow._catalog_row_highlight_kind(
            "culprit", "newer", crash_linked=True, scan_verified=True
        )
        == "culprit"
    )
    assert (
        gui.MainWindow._catalog_row_highlight_kind(
            "culprit", "same", crash_linked=True, scan_verified=False
        )
        == "culprit"
    )


def test_crash_link_info_tooltip_plain_language() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._last_model = {"last_crash": "2026-08-04 17:49 UTC"}
    dev = {
        "name": "__chipset_amd_platform__",
        "display_name": "AMD Chipset / Platform drivers",
        "_crash_linked": True,
        "_tier": "culprit",
        "_check_status": "same",
        "_scan_verified": True,
        "version": "8.05.04.516",
        "date": "2025-01-01",
    }
    tip = win._crash_link_info_tooltip(dev)
    assert "Crash analysis flagged this device for attention" in tip
    assert "Why is this row highlighted?" not in tip
    assert "WinDbg" not in tip
    assert "crash driver" not in tip.lower()


def test_updated_since_crash_status_when_driver_dated_after_bsod() -> None:
    win = gui.MainWindow.__new__(gui.MainWindow)
    win._last_model = {"last_crash": "2026-08-04 17:49 UTC"}
    win._fix_progress_last_crash_cache = None
    dev = {
        "_crash_linked": True,
        "_check_status": "same",
        "version": "8.05.04.516",
        "date": "2026-08-05",
    }
    assert win._crash_linked_same_status_label(dev) == "Updated since crash"


if __name__ == "__main__":
    test_crash_linked_up_to_date_uses_current_highlight()
    test_crash_linked_needs_update_stays_culprit()
    test_crash_link_info_tooltip_plain_language()
    test_updated_since_crash_status_when_driver_dated_after_bsod()
    print("OK")
