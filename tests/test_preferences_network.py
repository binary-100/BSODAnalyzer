"""Preferences dialog — network adapter power section."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

import bsod_gui_preferences as gui_prefs  # noqa: E402


def test_preferences_shows_active_adapter_label() -> None:
    payload = {
        "Name": "Wi-Fi",
        "InterfaceDescription": "Intel Wi-Fi 6 AX201",
        "MediaType": "802.11",
        "AllowComputerToTurnOffDevice": 1,
        "PowerSavingOn": True,
        "PowerManagementSupported": True,
    }
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with mock.patch(
        "system_network_power.query_active_network_adapter",
        return_value=payload,
    ):
        dlg = gui_prefs.PreferencesDialog(None, {})
        text = dlg._pref_network_adapter_label.text()
        assert "Intel Wi-Fi 6 AX201" in text
        assert "Wi" in text
        assert dlg._pref_network_keep_awake.isEnabled()
        dlg.close()
