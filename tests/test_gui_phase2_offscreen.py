"""Phase 2 — offscreen Qt smoke tests for MainWindow internals."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from gui_test_harness import (
    minimal_analysis_model,
    minimal_fmt_args,
    offscreen_main_window,
    process_events_until,
)


def _sample_devices() -> list[dict]:
    return [
        {
            "name": "Alpha Device",
            "display_name": "Alpha Device",
            "driver": "alpha.sys",
            "version": "1.0",
            "_tier": "normal",
            "_check_status": "pending",
            "_reasons": [],
        },
        {
            "name": "Beta Device",
            "display_name": "Beta Device",
            "driver": "beta.sys",
            "version": "2.0",
            "_tier": "normal",
            "_check_status": "pending",
            "_reasons": [],
        },
    ]


def _refreshed_model() -> dict:
    return {
        "plain_english": "Refreshed plain english.",
        "fix_plan": [],
        "recommendations": [],
        "culprit_driver_info": [],
        "driver_update_options": [],
        "action_plan_link_basis": "",
        "cause_title": "Test cause",
        "hardware_findings": [],
    }


def test_drv_filter_hides_rows_incrementally() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._drv_unified_cache = _sample_devices()
            win._rebuild_drv_table_display()
            win._sync_drv_unified_table()
            process_events_until(
                lambda: not getattr(win, "_drv_table_sync_active", False),
                timeout_ms=2000,
            )
            assert win.drv_unified_table.rowCount() == 2
            idx = win.drv_view_filter.findData("uncommon")
            if idx >= 0:
                win.drv_view_filter.setCurrentIndex(idx)
            win.drv_filter.setText("alpha")
            win._apply_drv_filter()
            process_events_until(
                lambda: not getattr(win, "_drv_table_sync_active", False),
                timeout_ms=2000,
            )
            visible = win._drv_visible_device_names()
            assert win.drv_unified_table.rowCount() == len(visible)
            assert "Alpha Device" in visible
            assert "Beta Device" not in visible


def test_manual_queue_status_mentions_current_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._drv_manual_queue.append({"device_names": ["GPU One"]})
            fake_thread = mock.MagicMock()
            fake_thread.isRunning.return_value = True
            win._drv_thread = fake_thread
            win._refresh_drv_manual_queue_status()
            hint = win.drv_hint.toPlainText().lower()
            assert "queued" in hint
            assert "current catalog check" in hint
            win._drv_thread = None


def test_summary_refresh_progress_indicator() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._set_summary_refresh_progress(True)
            assert win._summary_refresh_frame.isVisible()
            win._set_summary_refresh_progress(False)
            assert not win._summary_refresh_frame.isVisible()


def test_summary_refresh_apply_on_main_thread() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._last_model = minimal_analysis_model()
            win._summary_refresh_generation = 3
            win._on_summary_refresh_finished(3, _refreshed_model())
            assert "Refreshed" in (win._last_model.get("plain_english") or "")


def test_summary_refresh_ignores_stale_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._last_model = minimal_analysis_model()
            win._summary_refresh_generation = 5
            before = win._last_model.get("plain_english")
            win._on_summary_refresh_finished(
                4,
                {"plain_english": "STALE SHOULD NOT APPLY"},
            )
            assert win._last_model.get("plain_english") == before


def test_summary_refresh_worker_thread_completes() -> None:
    import bsod_gui_qt as gui

    def _fast_run(self) -> None:
        self.finished.emit(self._generation, _refreshed_model())

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._last_model = minimal_analysis_model()
            win._last_fmt_args = minimal_fmt_args()
            win._hardware_profile = {
                "bios_driver_info": {"drivers": []},
                "system_ctx": {"pnp_list": []},
            }
            with mock.patch.object(gui.SummaryRefreshWorker, "run", _fast_run):
                win._start_offthread_summary_refresh()
            done = process_events_until(
                lambda: win._summary_refresh_thread is None
                or not win._summary_refresh_thread.isRunning(),
                timeout_ms=3000,
            )
            assert done
            assert "Refreshed" in (win._last_model.get("plain_english") or "")


if __name__ == "__main__":
    test_drv_filter_hides_rows_incrementally()
    test_manual_queue_status_mentions_current_check()
    test_summary_refresh_progress_indicator()
    test_summary_refresh_apply_on_main_thread()
    test_summary_refresh_ignores_stale_generation()
    test_summary_refresh_worker_thread_completes()
    print("Phase 2 offscreen GUI tests OK")
