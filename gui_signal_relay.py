"""Qt signal relay — worker threads must connect to slots on this QObject, not mixins."""
from __future__ import annotations

from PySide6 import QtCore


class MainWindowSignalRelay(QtCore.QObject):
    """Forwards worker signals to MainWindow mixin handlers on the GUI thread."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window

    @QtCore.Slot(int, str)
    def analysis_progress(self, pct: int, msg: str) -> None:
        self._window._on_progress(pct, msg)

    @QtCore.Slot(object, object, str, bool)
    def analysis_finished(
        self, model: object, fmt_args: object, full_report: str, needs_config: bool,
    ) -> None:
        self._window._on_finished(model, fmt_args, full_report, needs_config)

    @QtCore.Slot(str)
    def analysis_failed(self, err: str) -> None:
        self._window._on_failed(err)

    @QtCore.Slot(int, object)
    def summary_refresh_finished(self, generation: int, new_m: object) -> None:
        self._window._on_summary_refresh_finished(generation, new_m)

    @QtCore.Slot(int, str)
    def summary_refresh_failed(self, generation: int, err: str) -> None:
        self._window._on_summary_refresh_failed(generation, err)

    @QtCore.Slot(str, object)
    def ps_maintenance_finished(self, op: str, payload: object) -> None:
        self._window._on_ps_maintenance_finished(op, payload)

    @QtCore.Slot(str, str)
    def ps_maintenance_failed(self, op: str, err: str) -> None:
        self._window._on_ps_maintenance_failed(op, err)

    @QtCore.Slot(str)
    def cdb_progress(self, msg: str) -> None:
        self._window._on_cdb_progress(msg)

    @QtCore.Slot(bool, str)
    def cdb_finished(self, ok: bool, msg: str) -> None:
        self._window._on_cdb_finished(ok, msg)

    @QtCore.Slot(str)
    def drv_catalog_progress(self, msg: str) -> None:
        self._window._on_drv_catalog_progress(msg)

    @QtCore.Slot(str)
    def fw_catalog_progress(self, msg: str) -> None:
        self._window._on_fw_catalog_progress(msg)

    @QtCore.Slot(object)
    def driver_catalog_ready(self, comparison: object) -> None:
        self._window._on_driver_catalog_ready(comparison)

    @QtCore.Slot(str)
    def driver_catalog_failed(self, err: str) -> None:
        self._window._on_driver_catalog_failed(err)

    @QtCore.Slot(str)
    def driver_install_progress(self, msg: str) -> None:
        self._window._on_driver_install_progress(msg)

    @QtCore.Slot(bool, str, object, object)
    def driver_install_finished(
        self, ok: bool, msg: str, offer: object, backup_record: object,
    ) -> None:
        self._window._on_driver_install_finished(ok, msg, offer, backup_record)

    @QtCore.Slot(str, object)
    def driver_install_failed(self, err: str, offer: object) -> None:
        self._window._on_driver_install_failed(err, offer)

    @QtCore.Slot(str)
    def driver_restore_progress(self, msg: str) -> None:
        self._window._on_driver_restore_progress(msg)

    @QtCore.Slot(bool, str)
    def driver_restore_finished(self, ok: bool, msg: str) -> None:
        self._window._on_driver_restore_finished(ok, msg)

    @QtCore.Slot(str)
    def driver_restore_failed(self, err: str) -> None:
        self._window._on_driver_restore_failed(err)

    @QtCore.Slot(object)
    def ssd_firmware_loaded(self, rows: object) -> None:
        self._window._on_ssd_firmware_loaded(rows)

    @QtCore.Slot(str)
    def ssd_firmware_load_failed(self, err: str) -> None:
        self._window._on_ssd_firmware_load_failed(err)

    @QtCore.Slot(object)
    def catalog_context_ready(self, ctx: object) -> None:
        self._window._on_catalog_context_ready(ctx)

    @QtCore.Slot(str)
    def catalog_context_failed(self, err: str) -> None:
        self._window._on_catalog_context_failed(err)

    @QtCore.Slot(object)
    def firmware_catalog_ready(self, comparison: object) -> None:
        self._window._on_firmware_catalog_ready(comparison)

    @QtCore.Slot(str)
    def firmware_catalog_failed(self, err: str) -> None:
        self._window._on_firmware_catalog_failed(err)

    @QtCore.Slot(int, int, str)
    def hw_scan_progress(self, step: int, total: int, msg: str) -> None:
        self._window._on_hw_scan_progress(step, total, msg)

    @QtCore.Slot(object)
    def hardware_ready(self, profile: object) -> None:
        self._window._on_hardware_ready(profile)

    @QtCore.Slot(str)
    def hardware_scan_failed(self, err: str) -> None:
        self._window._on_hardware_scan_failed(err)

    @QtCore.Slot(int, object)
    def drv_list_build_finished(self, generation: int, devices: object) -> None:
        self._window._on_drv_list_build_finished(generation, devices)

    @QtCore.Slot(int, str)
    def drv_list_build_failed(self, generation: int, err: str) -> None:
        self._window._on_drv_list_build_failed(generation, err)

    @QtCore.Slot(int)
    def drv_all_devices_loaded(self, count: int) -> None:
        self._window._on_drv_all_devices_loaded(count)

    @QtCore.Slot(str)
    def drv_all_devices_load_failed(self, err: str) -> None:
        self._window._on_drv_all_devices_load_failed(err)

    @QtCore.Slot(str)
    def drv_all_load_progress(self, msg: str) -> None:
        self._window._on_drv_all_load_progress(msg)

    @QtCore.Slot(str)
    def status_message(self, msg: str) -> None:
        self._window._catalog_status_line(msg)

    @QtCore.Slot(str)
    def catalog_status(self, msg: str) -> None:
        self._window._catalog_status_line(msg)

    @QtCore.Slot(object)
    def catalog_export_ready(self, payload: object) -> None:
        self._window._on_catalog_export_ready(payload)

    @QtCore.Slot(str)
    def catalog_export_failed(self, err: str) -> None:
        self._window._on_catalog_export_failed(err)
