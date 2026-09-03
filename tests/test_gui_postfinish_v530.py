"""Batch 3 hotfix (v5.2.30): GUI post-finish deferral and pipeline reset."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from gui_test_harness import isolated_settings, minimal_analysis_model, offscreen_application


def test_reset_post_analysis_pipeline_bumps_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                before = win._analysis_generation
                win._reset_post_analysis_pipeline()
                assert win._analysis_generation == before + 1
                assert win._drv_catalog_generation >= 1


def test_populate_deferred_skips_stale_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                win._analysis_generation = 2
                m = minimal_analysis_model()
                called: list[str] = []

                def fake_schedule(_m: dict) -> None:
                    called.append("schedule")

                with mock.patch.object(
                    win, "_schedule_crash_report_update_checks", fake_schedule
                ), mock.patch.object(win, "_populate_firmware_tab"), mock.patch.object(
                    win, "_apply_hardware_profile"
                ), mock.patch.object(
                    win, "_refresh_model_culprit_driver_info"
                ), mock.patch.object(
                    win, "_schedule_refresh_summary_from_inventory"
                ):
                    win._populate_deferred(1, {}, m)
                assert called == []


def test_catalog_ctx_complete_detects_enriched_ctx() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                incomplete = {"system_model": "X"}
                complete = {
                    "video_controllers": [{"name": "GPU"}],
                    "service_tag": "ABC",
                    "baseboard_product": "Board",
                    "system_model": "X",
                }
                assert win._catalog_ctx_is_complete(incomplete) is False
                assert win._catalog_ctx_is_complete(complete) is True


if __name__ == "__main__":
    test_reset_post_analysis_pipeline_bumps_generation()
    test_populate_deferred_skips_stale_generation()
    test_catalog_ctx_complete_detects_enriched_ctx()
    print("GUI post-finish (v5.2.30) tests OK")
