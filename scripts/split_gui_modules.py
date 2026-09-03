"""One-shot extractor: split bsod_gui_qt.py into theme/widgets/workers/mixins."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bsod_gui_qt.py"
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)

# 1-indexed inclusive line ranges from original file
THEME = (41, 374)
WIDGETS = (377, 475)
WORKERS = (478, 906)

MIXINS = [
    (
        "gui_mixin_shell.py",
        "GuiShellMixin",
        931,
        2923,
        "Main window shell: init, menus, tabs layout, toolbar, placeholders.",
    ),
    (
        "gui_mixin_analysis.py",
        "GuiAnalysisMixin",
        2925,
        3693,
        "Run analysis, populate summary/action/crash views, summary refresh.",
    ),
    (
        "gui_mixin_drivers.py",
        "GuiDriversMixin",
        3694,
        5764,
        "Hardware profile, driver list/table, drivers tab population.",
    ),
    (
        "gui_mixin_firmware.py",
        "GuiFirmwareMixin",
        5765,
        6871,
        "Firmware tab, SSD inventory, firmware catalog checks.",
    ),
    (
        "gui_mixin_catalog.py",
        "GuiCatalogMixin",
        6872,
        8150,
        "Driver catalog batching, install/download, restore/backup.",
    ),
    (
        "gui_mixin_system.py",
        "GuiSystemMixin",
        8151,
        8413,
        "System HTML, CDB tasks, export, event filter.",
    ),
]

MODULE_HEADER = '''\
"""{doc}"""
from __future__ import annotations

import gui_app_context as ctx

'''


def slice_lines(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def write_theme() -> None:
    body = slice_lines(*THEME)
    path = ROOT / "gui_theme.py"
    path.write_text(
        '"""Qt GUI palette, stylesheet, and table column constants."""\n\n' + body,
        encoding="utf-8",
    )


def write_widgets() -> None:
    body = slice_lines(*WIDGETS)
    path = ROOT / "gui_widgets.py"
    path.write_text(
        '"""Custom Qt widgets and menu helpers for the BSOD Analyzer GUI."""\n'
        "from __future__ import annotations\n\n"
        "from PySide6 import QtCore, QtGui, QtWidgets\n\n"
        "from gui_theme import MUTED, SEVERITY_COLORS, SEVERITY_SEGMENTS, TEXT\n\n"
        + body,
        encoding="utf-8",
    )


def write_workers() -> None:
    body = slice_lines(*WORKERS)
    existing = (ROOT / "bsod_gui_workers.py").read_text(encoding="utf-8")
    header = existing.split("class BackgroundJob")[0].rstrip() + "\n\n"
    extra_imports = (
        "import json\n"
        "import os\n\n"
        "import bsod_analyzer as core\n"
        "import bsod_workflow as wf\n"
        "import driver_catalog as drvcat\n"
        "import driver_list_build as drvlist\n"
        "import driver_install as drvinst\n"
        "import firmware_catalog as fwcat\n"
        "import hardware_cache as hwcache\n"
    )
    # Insert extra imports after PySide6 import block
    header = header.replace(
        "from PySide6 import QtCore\n\n",
        "from PySide6 import QtCore\n\n" + extra_imports + "\n",
    )
    path = ROOT / "bsod_gui_workers.py"
    path.write_text(header + body + "\n", encoding="utf-8")


def write_app_context() -> None:
    """Shared imports/constants for MainWindow mixins."""
    text = '''\
"""Shared imports and symbols for MainWindow mixin modules."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
import urllib.parse
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

import app_settings as app_set
import bsod_analyzer as core
import bsod_gui_log_cleanup as gui_cleanup
import bsod_gui_preferences as gui_prefs
import catalog_cache as ccat
import driver_catalog as drvcat
import bsod_gui_workers as gui_workers
import driver_index as drvidx
import driver_list_build as drvlist
import driver_install as drvinst
import firmware_catalog as fwcat
import hardware_cache as hwcache
import bsod_hardware_wmi as hw_wmi
import bsod_workflow as wf
import gui_vendor_icons as vicons
import gui_include_header as inc_hdr
import log_cleanup as log_cleanup

from gui_theme import (
    ACCENT,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    DRV_COL_CHECK,
    DRV_COL_DEVICE,
    DRV_COL_ICON,
    DRV_COL_INSTALLED,
    DRV_COL_STATUS,
    DRV_SECTION_HEADER_ROLE,
    DRV_TIER_CULPRIT_BG,
    DRV_TIER_CULPRIT_FG,
    DRV_TIER_OUTDATED_BG,
    DRV_TIER_OUTDATED_FG,
    FW_COL_CHECK,
    FW_COL_COMPONENT,
    FW_COL_ICON,
    FW_COL_INSTALLED,
    FW_COL_STATUS,
    MONO,
    MUTED,
    SEVERITY_COLORS,
    SEVERITY_SEGMENTS,
    STYLESHEET,
    TEXT,
    UPDATE_STATUS_COLORS,
    UPDATE_STATUS_LABELS,
    _DRV_INDEX_HINTS_MAX,
    _DRV_TABLE_DISPLAY_CAP,
    _DRV_TABLE_SYNC_BATCH,
    _DRV_TABLE_SYNC_DELAY_MS,
    _DRV_TABLE_SYNC_INLINE_MAX,
    _LARGE_DRIVER_SCAN_HINT_THRESHOLD,
)
from gui_widgets import (
    SeverityMeter,
    _MenuFriendlyStyle,
    _fix_menu_popup_width,
    _plain_menu_text,
)
from bsod_gui_workers import (
    AnalysisWorker,
    BuildDriverListWorker,
    CatalogContextWorker,
    CdbWorker,
    DriverCatalogWorker,
    FirmwareCatalogWorker,
    HardwareScanWorker,
    InstallDriverWorker,
    LoadAllDriversWorker,
    PsMaintenanceWorker,
    SaveHardwareProfileWorker,
    SsdFirmwareWorker,
    SummaryRefreshWorker,
)
'''
    (ROOT / "gui_app_context.py").write_text(text, encoding="utf-8")


def write_mixins() -> None:
    for filename, classname, start, end, doc in MIXINS:
        body = slice_lines(start, end)
        content = (
            f'"""{doc}"""\n'
            "from __future__ import annotations\n\n"
            "from gui_app_context import *  # noqa: F403\n\n\n"
            f"class {classname}:\n"
            + body
        )
        (ROOT / filename).write_text(content, encoding="utf-8")


def write_main_bsod_gui_qt() -> None:
    module_funcs = slice_lines(8414, len(lines))
    text = f'''\
"""
Modern Qt (PySide6) GUI for BSOD Analyzer — "Diagnostic Console" (Option B).

Dark, tabbed layout: a status banner with a traffic-light severity indicator, tabs for
Summary / Action Plan / Crash Details / System / Advanced, a severity meter, and a bottom
toolbar. All analysis logic lives in bsod_analyzer; this module only renders results.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets

import app_settings as app_set
import bsod_analyzer as core
import driver_catalog as drvcat

from gui_mixin_analysis import GuiAnalysisMixin
from gui_mixin_catalog import GuiCatalogMixin
from gui_mixin_drivers import GuiDriversMixin
from gui_mixin_firmware import GuiFirmwareMixin
from gui_mixin_shell import GuiShellMixin
from gui_mixin_system import GuiSystemMixin
from gui_widgets import _MenuFriendlyStyle

# Re-export for tests and backward compatibility
from bsod_gui_workers import (  # noqa: F401
    AnalysisWorker,
    BackgroundJob,
    BuildDriverListWorker,
    CatalogContextWorker,
    CdbWorker,
    DriverCatalogWorker,
    FirmwareCatalogWorker,
    HardwareScanWorker,
    InstallDriverWorker,
    LoadAllDriversWorker,
    PsMaintenanceWorker,
    SaveHardwareProfileWorker,
    SsdFirmwareWorker,
    SummaryRefreshWorker,
    stop_jobs,
)
from gui_theme import STYLESHEET  # noqa: F401
from gui_widgets import SeverityMeter  # noqa: F401


class MainWindow(
    GuiShellMixin,
    GuiAnalysisMixin,
    GuiDriversMixin,
    GuiFirmwareMixin,
    GuiCatalogMixin,
    GuiSystemMixin,
    QtWidgets.QMainWindow,
):
    """Diagnostic console main window (composed from tab/feature mixins)."""


{module_funcs}'''
    SRC.write_text(text, encoding="utf-8")


def main() -> None:
    write_theme()
    write_widgets()
    write_workers()
    write_app_context()
    write_mixins()
    write_main_bsod_gui_qt()
    print("GUI split complete.")


if __name__ == "__main__":
    main()
