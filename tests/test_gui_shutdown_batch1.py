"""Batch 1: GUI shutdown guards and analysis thread lifecycle."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from gui_test_harness import isolated_settings, minimal_analysis_model, offscreen_application


def test_on_finished_skips_populate_when_shutting_down() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                win._shutting_down = True
                m = minimal_analysis_model()
                with mock.patch.object(win, "_populate") as populate, mock.patch.object(
                    win, "_teardown_thread"
                ) as teardown:
                    win._on_finished(m, (), "report", False)
                populate.assert_not_called()
                teardown.assert_called_once()


def test_populate_skips_when_shutting_down() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                win._shutting_down = True
                with mock.patch.object(win, "_set_dot_color") as dot:
                    win._populate(minimal_analysis_model())
                dot.assert_not_called()


def test_on_failed_skips_ui_when_shutting_down() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                win._shutting_down = True
                win.btn_run.setEnabled(False)
                with mock.patch.object(win, "_teardown_thread") as teardown:
                    win._on_failed("boom")
                teardown.assert_called_once()
                assert win.btn_run.isEnabled() is False


def test_on_run_blocks_when_thread_running() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                running = mock.MagicMock()
                running.isRunning.return_value = True
                win._thread = running
                with mock.patch.object(win, "_reset_post_analysis_pipeline") as reset:
                    win.on_run()
                reset.assert_not_called()


def test_on_run_teardowns_stale_non_running_thread() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui
                from PySide6 import QtCore

                win = gui.MainWindow()
                win._thread = QtCore.QThread()
                assert not win._thread.isRunning()
                worker = mock.MagicMock()
                with mock.patch.object(
                    gui, "AnalysisWorker", return_value=worker
                ), mock.patch.object(
                    win, "_reset_post_analysis_pipeline"
                ), mock.patch.object(
                    win, "_set_summary_refresh_progress"
                ), mock.patch.object(
                    win, "_begin_task_progress"
                ), mock.patch.object(
                    QtCore.QThread, "start"
                ):
                    win.on_run()
                assert win._thread is not None
                assert win._worker is worker


def test_running_background_tasks_includes_catalog_refresh() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                with mock.patch.object(
                    win._catalog_refresh_job, "is_running", return_value=True
                ):
                    active = win._running_background_tasks()
                assert "catalog database refresh" in active


def test_cdb_finished_skips_dialog_when_shutting_down() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with isolated_settings(tmp):
            with offscreen_application():
                import bsod_gui_qt as gui

                win = gui.MainWindow()
                win._shutting_down = True
                win._cdb_thread = mock.MagicMock()
                win._cdb_thread.isRunning.return_value = False
                with mock.patch.object(
                    gui.QtWidgets.QMessageBox, "information"
                ) as info, mock.patch.object(gui.QtWidgets.QMessageBox, "warning") as warn:
                    win._on_cdb_finished(True, "done")
                info.assert_not_called()
                warn.assert_not_called()


if __name__ == "__main__":
    test_on_finished_skips_populate_when_shutting_down()
    test_populate_skips_when_shutting_down()
    test_on_failed_skips_ui_when_shutting_down()
    test_on_run_blocks_when_thread_running()
    test_on_run_teardowns_stale_non_running_thread()
    test_running_background_tasks_includes_catalog_refresh()
    test_cdb_finished_skips_dialog_when_shutting_down()
    print("GUI shutdown batch 1 tests OK")
