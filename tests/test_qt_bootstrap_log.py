"""Qt platform bootstrap writes an agent-readable diagnostic log."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import gui_qt_bootstrap as qt


def test_pyside6_import_guard_registers_plugins_before_qt() -> None:
    """Guard must set QT_PLUGIN_PATH before gui modules import PySide6."""
    import os

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    qt.install_pyside6_import_guard()
    qt.register_qt_plugins_for_import()
    import gui_signal_relay  # noqa: F401 — imports PySide6

    plugin_path = os.environ.get("QT_PLUGIN_PATH", "")
    assert "PySide6" in plugin_path and plugin_path.rstrip("/\\").endswith("plugins")


def test_offscreen_probe_writes_log() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    assert qt.probe_qt_platform(mode="test_offscreen")
    text = qt.read_qt_platform_log()
    assert "event=probe_ok" in text
    assert "platform: offscreen" in text


def test_offscreen_probe_tolerates_cmd_trailing_space() -> None:
    """cmd ``set QT_QPA_PLATFORM=offscreen &&`` leaves a trailing space — must not break Qt."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen "
    qt.normalize_qt_env()
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    assert qt.probe_qt_platform(mode="test_offscreen_trailing_space")


if __name__ == "__main__":
    test_offscreen_probe_writes_log()
    test_offscreen_probe_tolerates_cmd_trailing_space()
    print("qt bootstrap log tests OK")
