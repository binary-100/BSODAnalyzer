"""Phase 2 GUI harness — offscreen Qt, isolated settings (no dialogs)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest import mock

# Must be set before PySide6 import.
import gui_qt_bootstrap as _qt_boot

_qt_boot.ensure_offscreen_for_tests(probe=False)


def report_contains(report: str, text: str) -> bool:
    """
    Whether the report contains `text`, ignoring line wrapping.

    format_output() wraps to the configured report width, so any assertion on a phrase
    longer than a few words fails on a literal `in` check even when the wording is right.
    """
    return " ".join(text.split()) in " ".join(report.split())


def minimal_fmt_args() -> tuple:
    """Minimal tuple accepted by build_display_model / merge_hardware_into_fmt_args."""
    return (
        [],
        [],
        None,
        [],
        None,
        [],
        [],
        "",
        None,
        False,
        "",
        "",
        [],
        {},
        {},
        [],
        [],
        {"livekernel": [], "wer_errors": [], "stability_index": None},
    )


def minimal_analysis_model() -> dict:
    return {
        "cause_title": "Test cause",
        "severity_level": 1,
        "severity_name": "Low",
        "plain_english": "Test plain english.",
        "driver": "test.sys",
        "cause_type": {"label": "Driver", "driver_actionable": True},
        "confidence": "Test confidence",
        "data_gaps": [],
        "incidents": [],
        "recommendations": [],
        "fix_plan": [],
        "culprit_driver_info": [],
        "driver_update_options": [],
        "hardware_findings": [],
        "log_coverage": {},
        "crash_timeline": {},
        "system_ctx": {},
        "bios_driver_info": {},
    }


def _write_portable_settings(base: Path | str) -> None:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    settings = {
        "version": 2,
        "install_mode": "portable",
        "install_mode_chosen": True,
        "first_run_complete": True,
        "use_driver_index": False,
        "remember_driver_firmware_checks": False,
        "auto_load_all_drivers_on_scan": False,
    }
    (base / "settings.json").write_text(
        json.dumps(settings, indent=2),
        encoding="utf-8",
    )


@contextmanager
def isolated_settings(tmp: Path | str) -> Iterator[Path]:
    tmp = Path(tmp)
    """Point portable/full settings at a temp directory."""
    import app_settings as app_set

    _write_portable_settings(tmp)

    def _portable_dir() -> Path:
        return tmp

    def _settings_path() -> Path:
        return tmp / "settings.json"

    def _full_data_dir() -> Path:
        return tmp / "appdata"

    with (
        mock.patch.object(app_set, "portable_settings_dir", _portable_dir),
        mock.patch.object(app_set, "_settings_path", _settings_path),
        mock.patch.object(app_set, "full_install_data_dir", _full_data_dir),
    ):
        yield tmp


@contextmanager
def offscreen_application() -> Iterator[object]:
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app


@contextmanager
def offscreen_widget(factory) -> Iterator[object]:
    """Build a parentless widget and guarantee it is destroyed inside the test.

    Qt keeps top-level widgets alive independently of the Python reference, so a widget
    created and dropped by a test survives until interpreter shutdown and is then torn
    down while QApplication is going away — aborting the process with 0xC0000409.
    """
    with offscreen_application() as app:
        widget = factory()
        try:
            yield widget
        finally:
            widget.close()
            widget.deleteLater()
            app.processEvents()


@contextmanager
def offscreen_main_window(tmp: Path | str) -> Iterator[object]:
    tmp = Path(tmp)
    """Construct MainWindow with isolated settings (no install-mode dialog)."""
    with isolated_settings(tmp):
        with offscreen_application():
            import bsod_gui_qt as gui

            win = gui.MainWindow()
            win.show()
            try:
                yield win
            finally:
                teardown_main_window(win)
                drain_qt_top_levels()


def process_events_until(
    predicate,
    *,
    timeout_ms: int = 8000,
) -> bool:
    """Pump Qt events until predicate() is true or timeout. Returns predicate result."""
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        return bool(predicate())
    deadline = QtCore.QTime.currentTime().addMSecs(timeout_ms)
    while QtCore.QTime.currentTime() < deadline:
        if predicate():
            return True
        app.processEvents()
        QtCore.QThread.msleep(20)
    return bool(predicate())


def teardown_main_window(win: object) -> None:
    """Stop background work before destroying the window."""
    win._shutting_down = True  # type: ignore[attr-defined]
    for attr in (
        "_thread",
        "_cdb_thread",
        "_drv_thread",
        "_fw_thread",
        "_hw_thread",
        "_summary_refresh_thread",
        "_ps_thread",
        "_ctx_thread",
        "_ssd_fw_thread",
        "_install_thread",
        "_drv_all_load_thread",
        "_hw_save_thread",
        "_drv_list_build_thread",
    ):
        th = getattr(win, attr, None)
        if th is not None and th.isRunning():
            th.quit()
            th.wait(2000)
        setattr(win, attr, None)
    win._summary_refresh_worker = None  # type: ignore[attr-defined]
    win._ps_worker = None  # type: ignore[attr-defined]
    win.close()  # type: ignore[attr-defined]
    win.deleteLater()  # type: ignore[attr-defined]
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.processEvents()
        app.processEvents()


def drain_qt_top_levels() -> None:
    """Close stray top-level widgets so interpreter exit does not hit 0xC0000409."""
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass
    app.processEvents()
    app.processEvents()
