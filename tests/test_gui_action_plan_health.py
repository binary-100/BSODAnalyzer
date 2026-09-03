"""GUI tests — Action Plan inline health buttons."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui_test_harness import offscreen_main_window, process_events_until  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402


def _model_with_steps(steps: list[str]) -> dict:
    return {
        "severity_level": 1,
        "severity_name": "Moderate",
        "cause_title": "Test",
        "confidence": "Test",
        "fix_plan": {"headline": "Fix plan", "steps": steps},
        "recommendations": steps,
        "plain_english": "Summary.",
        "incidents": [],
        "dumps_analyzed": 0,
        "crash_count": 0,
    }


def test_action_plan_shows_sfc_and_dism_buttons_for_combined_step() -> None:
    step = (
        "Optional: run sfc /scannow; use DISM /Online /Cleanup-Image "
        "/RestoreHealth if the system feels corrupted."
    )
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._populate_action_plan_ui(_model_with_steps([step]))
            labels = [
                b.text()
                for b in win.findChildren(QtWidgets.QPushButton)
                if "SFC" in b.text() or "DISM" in b.text()
            ]
            assert any("SFC" in t for t in labels)
            assert any("DISM" in t for t in labels)


def test_action_plan_memory_button_for_mdsched_step() -> None:
    step = "Run Windows Memory Diagnostic (mdsched.exe) to test RAM"
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._populate_action_plan_ui(_model_with_steps([step]))
            btns = [b.text() for b in win.findChildren(QtWidgets.QPushButton)]
            assert any("memory test" in t.lower() for t in btns)


def test_action_plan_admin_gates_sfc_when_not_elevated() -> None:
    step = "Optional: run sfc /scannow only if problems persist."
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            with mock.patch("log_cleanup.is_user_admin", return_value=False):
                win._populate_action_plan_ui(_model_with_steps([step]))
                sfc_btns = [
                    b
                    for b in win.findChildren(QtWidgets.QPushButton)
                    if "SFC" in b.text()
                ]
                assert sfc_btns
                assert not sfc_btns[0].isEnabled()


def test_action_plan_chipset_step_gets_inline_link_button() -> None:
    steps = ["Install the latest AMD chipset drivers for this PC."]
    options = [
        {
            "id": "amd_chipset",
            "label": "AMD chipset drivers (for this PC's AMD platform)",
            "kind": "url",
            "url": "https://www.amd.com/en/support/chipsets/amd-socket-am4/b550",
        },
        {
            "id": "wu_optional_platform",
            "label": "Open Windows Update (optional updates)",
            "kind": "uri",
            "uri": "ms-settings:windowsupdate-optionalupdates",
        },
    ]
    model = _model_with_steps(steps)
    model["driver_update_options"] = options
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._populate_action_plan_ui(model)
            labels = [b.text() for b in win.findChildren(QtWidgets.QPushButton)]
            assert any("AMD chipset" in t for t in labels)
            assert any("Windows Update" in t for t in labels)
            assert not getattr(win, "action_driver_links_frame", None)
