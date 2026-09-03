"""Shared imports and symbols for MainWindow mixin modules."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
import urllib.parse
from typing import Callable

import gui_qt_bootstrap as _qt_boot

_qt_boot.register_qt_plugins_for_import()

from PySide6 import QtCore, QtGui, QtWidgets

import app_settings as app_set
import bsod_analyzer as core
import bsod_runtime as rt
import bsod_gui_log_cleanup as gui_cleanup
import bsod_gui_preferences as gui_prefs
import catalog_cache as ccat
import catalog_export as cexp
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
import maintenance_log as mlog

from gui_theme import (
    ACCENT,
    BG,
    BORDER,
    BTN_DRV_LOAD,
    BTN_DRV_LOADING,
    BTN_DRV_SEARCH,
    BTN_FW_LOAD,
    BTN_FW_LOADING,
    BTN_FW_SEARCH,
    CARD,
    CARD_ALT,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_MIN_HEIGHT,
    DEFAULT_WINDOW_MIN_WIDTH,
    DEFAULT_WINDOW_WIDTH,
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
    TABLE_SELECTION,
    TEXT,
    UPDATE_STATUS_COLORS,
    UPDATE_STATUS_LABELS,
    UNIFIED_TABLE_CHECK_COL_WIDTH,
    UNIFIED_TABLE_DEVICE_COL_MIN_WIDTH,
    UNIFIED_TABLE_HEADER_HEIGHT,
    UNIFIED_TABLE_ICON_COL_WIDTH,
    UNIFIED_TABLE_INSTALLED_COL_WIDTH,
    UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
    UNIFIED_TABLE_INSTALLED_COL_MIN_WIDTH,
    UNIFIED_TABLE_PACKAGE_COL_MIN_WIDTH,
    UNIFIED_TABLE_PACKAGE_SOURCE_COL_MIN_WIDTH,
    UNIFIED_TABLE_STATUS_COL_WIDTH,
    UNIFIED_TABLE_STATUS_COL_MIN_WIDTH,
    UNIFIED_TABLE_ICON_SIZE,
    UNIFIED_TABLE_INSP_ICON_SIZE,
    UNIFIED_TABLE_MIN_COMPARE_HEIGHT,
    UNIFIED_TABLE_MIN_LIST_HEIGHT,
    UNIFIED_TABLE_PACKAGE_ROW_HEIGHT,
    UNIFIED_TABLE_HINT_MAX_HEIGHT,
    UNIFIED_TABLE_SUBTITLE_MAX_HEIGHT,
    UNIFIED_TABLE_ROW_HEIGHT,
    UNIFIED_TABLE_ROW_HEIGHT_DUAL_VERSION,
    UNIFIED_TAB_INSPECTOR_MIN_HEIGHT,
    UNIFIED_TAB_INSPECTOR_COMPACT_HEIGHT,
    UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT,
    UNIFIED_TAB_PACKAGES_PANEL_MIN_HEIGHT,
    UNIFIED_TAB_SECTION_MIN_HEIGHT,
    UNIFIED_TAB_SPLITTER_SIZES,
    UNIFIED_SPLITTER_HANDLE_WIDTH,
    TASK_PROGRESS_BAR_HEIGHT,
    TASK_PROGRESS_FRAME_HEIGHT,
    TASK_PROGRESS_BANNER_FRAME_HEIGHT,
    TASK_PROGRESS_LABEL_LINE_HEIGHT,
    CATALOG_TAB_PROGRESS_FRAME_HEIGHT,
    CATALOG_CHROME_H_INSET,
    TAB_BODY_MARGINS,
    TAB_BODY_MARGIN_TOP,
    CATALOG_TAB_BODY_MARGINS,
    CATALOG_TAB_BODY_MARGIN_TOP,
    CATALOG_FILTER_COMBO_PAD_LEFT,
    CATALOG_VIEW_FILTER_MIN_WIDTH,
    CATALOG_LOAD_BTN_MIN_WIDTH,
    CATALOG_SEARCH_BTN_MIN_WIDTH,
    CATALOG_SPLITTER_SETTINGS_KEY,
    CATALOG_UNIFIED_COL_WIDTHS_KEY,
    CATALOG_PACKAGE_COL_WIDTHS_KEY,
    CATALOG_NAME_COLUMNS,
    CATALOG_ROW_CURRENT_BG,
    CATALOG_ROW_CURRENT_BG_ALPHA,
    TASK_PROGRESS_LABEL_MAX_WIDTH,
    _DRV_INDEX_HINTS_MAX,
    _DRV_TABLE_DISPLAY_CAP,
    _DRV_TABLE_SYNC_BATCH,
    _DRV_TABLE_SYNC_DELAY_MS,
    _DRV_TABLE_SYNC_INLINE_MAX,
    _LARGE_DRIVER_SCAN_HINT_THRESHOLD,
)
import gui_widgets
from gui_widgets import (
    CatalogTableNeutralDelegate,
    MainTabHost,
    SeverityMeter,
    _MenuFriendlyStyle,
    _fix_menu_popup_width,
    _plain_menu_text,
    apply_styled_control,
    apply_catalog_filter_control,
    apply_catalog_table_style,
    apply_styled_frame,
)
from bsod_gui_workers import (
    AnalysisWorker,
    BuildDriverListWorker,
    CatalogContextWorker,
    CatalogExportWorker,
    CdbWorker,
    DriverCatalogWorker,
    FirmwareCatalogWorker,
    HardwareScanWorker,
    InstallDriverWorker,
    LoadAllDriversWorker,
    PsMaintenanceWorker,
    PowerShell7InstallWorker,
    RestoreDriverWorker,
    SaveHardwareProfileWorker,
    SsdFirmwareWorker,
    SummaryRefreshWorker,
)
from gui_signal_relay import MainWindowSignalRelay

__all__ = [n for n in globals() if not n.startswith("__")]
