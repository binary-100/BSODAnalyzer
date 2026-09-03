"""Unified catalog row styling — Drivers and Firmware use the same rules."""

from __future__ import annotations

import bsod_gui_qt as gui


def test_catalog_row_highlight_unifies_newer_and_outdated() -> None:
    assert gui.MainWindow._catalog_row_highlight_kind("normal", "newer") == "update"
    assert gui.MainWindow._catalog_row_highlight_kind("outdated", "same") == "update"
    assert gui.MainWindow._catalog_row_highlight_kind("normal", "same") == "current"
    assert gui.MainWindow._catalog_row_highlight_kind("culprit", "newer") == "culprit"
    assert (
        gui.MainWindow._catalog_row_highlight_kind(
            "culprit", "same", crash_linked=True, scan_verified=True
        )
        == "current"
    )
    assert gui.MainWindow._catalog_row_highlight_kind("normal", "pending") == "none"


if __name__ == "__main__":
    test_catalog_row_highlight_unifies_newer_and_outdated()
    print("OK")
