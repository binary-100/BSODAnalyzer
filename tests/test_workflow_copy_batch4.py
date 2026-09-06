"""Batch 4: workflow copy matches manual-only driver scan after Run Analysis."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

# offscreen_main_window owns teardown (worker threads, then close). Building MainWindow
# by hand left a live top-level window until interpreter exit, which aborted the process
# with 0xC0000409 during Qt shutdown.
from gui_test_harness import drain_qt_top_levels, minimal_analysis_model, offscreen_main_window


@pytest.fixture(autouse=True)
def _drain_qt_after_test() -> None:
    yield
    drain_qt_top_levels()


def test_driver_comparison_hint_is_manual_not_automatic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            m = minimal_analysis_model()
            m["cause_type"] = {"driver_actionable": True, "label": "Driver"}
            m["driver"] = "nvlddmkm.sys"
            m["culprit_driver_info"] = [
                {"name": "NVIDIA GPU", "version": "1.0", "date": "2024-01-01"}
            ]
            win._populate_driver_update_options(m)
            hint = win.driver_update_hint.text().lower()
            assert "checked automatically" not in hint
            assert "load devices" in hint
            assert "search for updates" in hint


def test_populate_deferred_does_not_start_crash_driver_scan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            m = minimal_analysis_model()
            m["driver"] = "nvlddmkm.sys"
            m["cause_type"] = {"driver_actionable": True}
            prof = win._profile_from_model(m)
            win._analysis_generation = 1
            win._populate_deferred(1, prof, m)
            assert not (
                win._drv_thread and win._drv_thread.isRunning()
            )


if __name__ == "__main__":
    test_driver_comparison_hint_is_manual_not_automatic()
    test_populate_deferred_does_not_start_crash_driver_scan()
    drain_qt_top_levels()
    print("Workflow copy batch 4 tests OK")
