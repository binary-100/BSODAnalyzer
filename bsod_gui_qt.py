"""
Modern Qt (PySide6) GUI for BSOD Analyzer — "Diagnostic Console" (Option B).

Dark, tabbed layout: a status banner with a traffic-light severity indicator, tabs for
Summary / Action Plan / Crash Details / System / Advanced, a severity meter, and a bottom
toolbar. All analysis logic lives in bsod_analyzer; this module only renders results.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import gui_qt_bootstrap as _qt_boot

_qt_boot.normalize_qt_env()
if __name__ == "__main__":
    _qt_boot.prepare_interactive_gui()
elif not _qt_boot.is_offscreen_test_mode():
    _qt_boot.prepare_interactive_gui(probe=False)

from PySide6 import QtCore, QtWidgets

import app_settings as app_set
import bsod_analyzer as core
import bsod_gui_preferences as gui_prefs
import driver_catalog as drvcat

from gui_mixin_analysis import GuiAnalysisMixin
from gui_mixin_action_plan import GuiActionPlanMixin
from gui_mixin_minidump import GuiMinidumpMixin
from gui_mixin_catalog import GuiCatalogMixin
from gui_mixin_catalog_scan import GuiCatalogScanMixin
from gui_mixin_catalog_export import GuiCatalogExportMixin
from gui_mixin_catalog_install import GuiCatalogInstallMixin
from gui_mixin_catalog_packages import GuiCatalogPackagesMixin
from gui_mixin_drivers import GuiDriversMixin
from gui_mixin_drivers_table import GuiDriversTableMixin
from gui_mixin_drivers_inventory import GuiDriversInventoryMixin
from gui_mixin_drivers_workflow import GuiDriversWorkflowMixin
from gui_mixin_vendor_health import GuiVendorHealthMixin
from gui_mixin_firmware import GuiFirmwareMixin
from gui_mixin_firmware_inventory import GuiFirmwareInventoryMixin
from gui_mixin_firmware_scan import GuiFirmwareScanMixin
from gui_mixin_firmware_table import GuiFirmwareTableMixin
from gui_mixin_firmware_workflow import GuiFirmwareWorkflowMixin
from gui_mixin_shell import GuiShellMixin
from gui_mixin_catalog_layout import GuiCatalogLayoutMixin
from gui_mixin_settings import GuiSettingsMixin
from gui_mixin_task_progress import GuiTaskProgressMixin
from gui_mixin_lifecycle import GuiLifecycleMixin
from gui_mixin_maintenance import GuiMaintenanceMixin
from gui_mixin_tabs import GuiTabsMixin
from gui_mixin_catalog_shell import GuiCatalogShellMixin
from gui_mixin_window_chrome import GuiWindowChromeMixin
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
    MinidumpAnalyzeWorker,
    PsMaintenanceWorker,
    RestoreDriverWorker,
    SaveHardwareProfileWorker,
    SsdFirmwareWorker,
    SummaryRefreshWorker,
    SystemHealthWorker,
    stop_jobs,
)
from gui_theme import STYLESHEET  # noqa: F401
from gui_widgets import SeverityMeter  # noqa: F401


class MainWindow(
    GuiShellMixin,
    GuiSettingsMixin,
    GuiCatalogLayoutMixin,
    GuiTaskProgressMixin,
    GuiMaintenanceMixin,
    GuiLifecycleMixin,
    GuiWindowChromeMixin,
    GuiTabsMixin,
    GuiCatalogShellMixin,
    GuiVendorHealthMixin,
    GuiActionPlanMixin,
    GuiMinidumpMixin,
    GuiAnalysisMixin,
    GuiDriversTableMixin,
    GuiDriversInventoryMixin,
    GuiDriversWorkflowMixin,
    GuiDriversMixin,
    GuiFirmwareWorkflowMixin,
    GuiFirmwareInventoryMixin,
    GuiFirmwareTableMixin,
    GuiFirmwareScanMixin,
    GuiFirmwareMixin,
    GuiCatalogScanMixin,
    GuiCatalogPackagesMixin,
    GuiCatalogInstallMixin,
    GuiCatalogExportMixin,
    GuiCatalogMixin,
    GuiSystemMixin,
    QtWidgets.QMainWindow,
):
    """Diagnostic console main window (composed from tab/feature mixins)."""

    _FW_BIOS_PRIORITY_CODES = frozenset({0x124, 0x7F, 0x9C})
    _FW_DISK_STOP_CODES = frozenset({0x7A, 0x7B, 0xED, 0x50, 0x133})
    _ANALYSIS_THREAD_WAIT_MS = 5000
    _CDB_THREAD_WAIT_MS = 5000
    _BACKGROUND_THREAD_LABELS: tuple[tuple[str, str], ...] = (
        ("_thread", "crash analysis"),
        ("_cdb_thread", "CDB install/update"),
        ("_drv_thread", "driver update check"),
        ("_fw_thread", "firmware check"),
        ("_hw_thread", "hardware scan"),
        ("_summary_refresh_thread", "summary refresh"),
        ("_drv_all_load_thread", "full device list load"),
        ("_hw_save_thread", "hardware profile save"),
        ("_ssd_fw_thread", "SSD firmware lookup"),
        ("_install_thread", "driver install"),
        ("_restore_thread", "driver restore"),
        ("_ps_thread", "system maintenance"),
        ("_ctx_thread", "support link lookup"),
        ("_drv_list_build_thread", "device list build"),
    )


def _ensure_install_mode_chosen() -> None:
    """First launch: default to portable without prompting (portable-first product).

    Set ``prompt_install_mode_on_first_launch`` in settings to re-enable the
    full-install vs portable choice dialog (e.g. if a future feature needs it).
    """
    settings = app_set.load_settings()
    if settings.get("install_mode_chosen"):
        return
    if settings.get("prompt_install_mode_on_first_launch"):
        dlg = gui_prefs.InstallModeChoiceDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            settings = app_set.apply_portable_defaults(settings)
            app_set.save_settings(settings)
            return
        if dlg.choice_is_full():
            settings = app_set.apply_full_install_defaults(settings)
        else:
            settings = app_set.apply_portable_defaults(settings)
        app_set.save_settings(settings)
        return
    settings = app_set.apply_portable_defaults(settings)
    app_set.save_settings(settings)


def _install_gui_exception_hook() -> None:
    """Surface uncaught main-thread errors instead of closing with no dialog."""
    _prev = sys.excepthook

    def _crash_log_path() -> Path | None:
        try:
            import app_settings as app_set

            if app_set.allows_persistent_driver_data():
                d = app_set.full_install_data_dir()
            else:
                d = app_set.portable_exports_dir()
                if not d:
                    d = Path(os.environ.get("TEMP", ".")) / "BSODAnalyzer"
            d.mkdir(parents=True, exist_ok=True)
            return d / "BSODAnalyzer_self_crash.txt"
        except Exception:
            try:
                d = Path(os.environ.get("TEMP", ".")) / "BSODAnalyzer"
                d.mkdir(parents=True, exist_ok=True)
                return d / "BSODAnalyzer_self_crash.txt"
            except Exception:
                return None

    def _write_crash_artifact(detail: str) -> None:
        path = _crash_log_path()
        if not path:
            return
        try:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"\n=== {stamp} ===\n{detail}\n")
        except OSError:
            pass

    def _hook(exc_type, exc, tb) -> None:
        import traceback

        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        _write_crash_artifact(detail)
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                QtWidgets.QMessageBox.critical(
                    None,
                    "BSOD Analyzer — unexpected error",
                    detail[-2000:],
                )
        except Exception:
            pass  # excepthook fallback; avoid recursive GUI failure
        _prev(exc_type, exc, tb)

    sys.excepthook = _hook


def run_gui_qt() -> None:
    """Launch the PySide6 (Option B) GUI."""
    _qt_boot.prepare_interactive_gui()
    if sys.platform != "win32":
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(
            None,
            "BSOD Analyzer",
            "BSOD Analyzer requires Windows (WMI, event logs, and crash dumps).",
        )
        sys.exit(1)
    import faulthandler

    drvcat.set_gui_application_mode(True)
    try:
        if drvcat._v6_catalog_enabled():
            ok, detail = drvcat.ensure_mscatalog_module_ready(check_online=True)
            if not ok:
                drvcat.set_mscatalog_startup_notice(detail or "MSCatalogLTS module not ready")
    except Exception as exc:
        drvcat.set_mscatalog_startup_notice(str(exc))
    _install_gui_exception_hook()
    try:
        if app_set.allows_persistent_driver_data():
            log_dir = app_set.full_install_data_dir()
        else:
            log_dir = Path(os.environ.get("TEMP", ".")) / "BSODAnalyzer"
        log_dir.mkdir(parents=True, exist_ok=True)
        from timestamped_log_io import TimestampPrefixTextIO

        fh = TimestampPrefixTextIO(
            open(log_dir / "gui_crash.log", "a", encoding="utf-8")
        )
        faulthandler.enable(file=fh, all_threads=True)
    except OSError:
        faulthandler.enable()
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setAttribute(QtCore.Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    base_style = app.style()
    app.setStyle(_MenuFriendlyStyle(base_style))
    app.setApplicationName("BSOD Analyzer")
    _ensure_install_mode_chosen()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui_qt()
