"""Reusable QThread worker wiring for the Qt GUI."""

from __future__ import annotations

from typing import Callable

from PySide6 import QtCore

import json
import os

import bsod_analyzer as core
import bsod_workflow as wf
import driver_catalog as drvcat
import driver_list_build as drvlist
import driver_install as drvinst
import firmware_catalog as fwcat
import hardware_cache as hwcache

class SummaryRefreshWorker(QtCore.QObject):
    """Rebuild display model with merged hardware inventory off the UI thread."""

    finished = QtCore.Signal(int, object)  # generation, new_model dict
    failed = QtCore.Signal(int, str)  # generation, error message

    def __init__(
        self,
        fmt_args: tuple,
        hardware_profile: dict | None,
        generation: int,
    ) -> None:
        super().__init__()
        self._fmt_args = fmt_args
        self._hardware_profile = hardware_profile
        self._generation = generation

    @QtCore.Slot()
    def run(self) -> None:
        try:
            merged = wf.merge_hardware_into_fmt_args(
                self._fmt_args, self._hardware_profile
            )
            new_m = core.build_display_model(merged)
            self.finished.emit(self._generation, new_m)
        except Exception as e:  # noqa: BLE001 - surface to UI
            self.failed.emit(self._generation, str(e))


class AnalysisWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)  # percent 0–100, status message
    finished = QtCore.Signal(object, object, str, bool)  # model, fmt_args, report, needs_config
    failed = QtCore.Signal(str)

    def __init__(self, include_reliability: bool = True) -> None:
        super().__init__()
        self._include_reliability = include_reliability

    @QtCore.Slot()
    def run(self) -> None:
        token = ""
        elapsed_ms: int | None = None
        try:
            import session_log as slog

            token = slog.begin("run_analysis", "Run Analysis")
        except Exception:
            pass  # optional session_log; must not break worker startup
        try:
            fmt_args, needs_config = core.gather_report_data(
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                include_reliability=self._include_reliability,
            )
            self.progress.emit(98, "Building results…")
            model = core.build_display_model(fmt_args)
            if token:
                try:
                    import session_log as slog

                    elapsed_ms = slog.end(token, "run_analysis", "Analysis complete")
                except Exception:
                    elapsed_ms = None
            if elapsed_ms is not None:
                model["analysis_elapsed_ms"] = elapsed_ms
            full = core.format_output(
                *fmt_args,
                include_technical_details=True,
                analysis_elapsed_ms=elapsed_ms,
            )
            self.finished.emit(model, fmt_args, full, needs_config)
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            if token:
                try:
                    import session_log as slog

                    slog.end(
                        token,
                        "run_analysis",
                        f"Analysis failed: {str(e)[:120]}",
                        status="error",
                    )
                except Exception:
                    pass  # optional session_log; must not mask worker error
            self.failed.emit(str(e))


class CdbWorker(QtCore.QObject):
    """Runs a long CDB install/update task off the UI thread."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)

    def __init__(self, kind: str) -> None:
        super().__init__()
        self._kind = kind  # "install" or "update"

    @QtCore.Slot()
    def run(self) -> None:
        try:
            fn = core.update_cdb if self._kind == "update" else core.install_cdb
            ok, msg = fn(progress=lambda m: self.progress.emit(m))
            self.finished.emit(ok, msg)
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            self.finished.emit(False, str(e))


class HardwareScanWorker(QtCore.QObject):
    """PnP + driver inventory scan without crash log analysis."""

    progress = QtCore.Signal(int, int, str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            profile = core.gather_hardware_profile(
                progress_cb=lambda c, t, m: self.progress.emit(c, t, m),
            )
            self.finished.emit(profile)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class PsMaintenanceWorker(QtCore.QObject):
    """System Restore status / restore point / driver backup off the UI thread."""

    finished = QtCore.Signal(str, object)  # op, payload
    failed = QtCore.Signal(str, str)  # op, error

    def __init__(self, op: str, **params: object) -> None:
        super().__init__()
        self._op = op
        self._params = params

    @QtCore.Slot()
    def run(self) -> None:
        try:
            if self._op == "restore_status":
                self.finished.emit(self._op, drvcat.get_system_restore_status())
            elif self._op == "create_restore":
                desc = str(
                    self._params.get("description")
                    or "BSOD Analyzer before driver change"
                )
                self.finished.emit(self._op, drvcat.create_system_restore_point(desc))
            elif self._op == "enable_restore":
                drive = self._params.get("drive")
                self.finished.emit(self._op, drvcat.enable_system_restore(drive))
            elif self._op == "backup_driver":
                import driver_backup as drvbackup

                name = str(self._params.get("device_name") or "")
                root = self._params.get("backup_root")
                keep = int(self._params.get("keep_count") or 3)
                ok, msg, record = drvbackup.backup_device_driver(name, root)
                if ok and keep > 0:
                    drvbackup.prune_driver_backups(root, keep_per_device=keep)
                self.finished.emit(self._op, (ok, msg, record))
            elif self._op == "restore_driver":
                import driver_backup as drvbackup

                path = str(self._params.get("backup_path") or "")
                self.finished.emit(self._op, drvbackup.restore_driver_backup(path))
            else:
                self.failed.emit(self._op, f"Unknown operation: {self._op}")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(self._op, str(e))


class MinidumpAnalyzeWorker(QtCore.QObject):
    """Run CDB !analyze on one minidump off the UI thread."""

    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, dump_path: str, cdb_path: str) -> None:
        super().__init__()
        self._dump_path = dump_path
        self._cdb_path = cdb_path

    @QtCore.Slot()
    def run(self) -> None:
        try:
            import bsod_minidump as mdump

            analysis = mdump.analyze_minidump_with_cdb(self._dump_path, self._cdb_path)
            if analysis:
                self.finished.emit(analysis)
            else:
                self.failed.emit("CDB returned no analysis for this dump.")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class SystemHealthWorker(QtCore.QObject):
    """Run SFC or DISM off the UI thread."""

    finished = QtCore.Signal(bool, str)
    failed = QtCore.Signal(str)

    def __init__(self, kind: str) -> None:
        super().__init__()
        self._kind = kind

    @QtCore.Slot()
    def run(self) -> None:
        try:
            import system_health_actions as shealth

            if self._kind == "sfc":
                ok, detail = shealth.run_sfc_scannow()
            elif self._kind == "dism":
                ok, detail = shealth.run_dism_restore_health()
            elif self._kind == "chkdsk":
                ok, detail = shealth.schedule_chkdsk_system_drive()
            else:
                self.failed.emit(f"Unknown health check: {self._kind}")
                return
            self.finished.emit(ok, detail)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class LoadAllDriversWorker(QtCore.QObject):
    """Loads every signed driver device row (slower than the default hardware scan)."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(int)  # row count; payload in result_path or rows_result
    failed = QtCore.Signal(str)

    def __init__(self, pnp_index: dict) -> None:
        super().__init__()
        self._pnp_index = pnp_index
        self.rows_result: list = []
        self.result_path: str = ""

    @QtCore.Slot()
    def run(self) -> None:
        import tempfile

        import device_enrichment as de

        path = ""
        try:
            rows = core.get_all_installed_driver_devices(
                progress_cb=lambda m: self.progress.emit(m),
                sequential=True,
            )
            self.progress.emit("Enriching device names…")
            if self._pnp_index:
                rows = de.enrich_driver_inventory_rows(
                    rows,
                    self._pnp_index,
                    known_vendor_fn=core._extract_vendor_from_string,
                    parallel=False,
                )
            self.rows_result = rows
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                delete=False,
            ) as tmp:
                json.dump(rows, tmp, ensure_ascii=False)
                path = tmp.name
            self.result_path = path
            self.finished.emit(len(rows))
        except Exception as e:  # noqa: BLE001
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self.failed.emit(str(e))


class BuildDriverListWorker(QtCore.QObject):
    """Build unified driver/device list off the UI thread."""

    finished = QtCore.Signal(int, object)  # generation, devices list
    failed = QtCore.Signal(int, str)

    def __init__(
        self,
        prof: dict,
        *,
        full: bool,
        settings: dict,
        session_batch: dict | None,
        crash_driver: str | None,
        last_model: dict | None,
        last_fmt_args: tuple | None,
        generation: int,
    ) -> None:
        super().__init__()
        self._prof = prof
        self._full = full
        self._settings = dict(settings)
        self._session_batch = session_batch
        self._crash_driver = crash_driver
        self._last_model = last_model
        self._last_fmt_args = last_fmt_args
        self._generation = generation

    @QtCore.Slot()
    def run(self) -> None:
        try:
            devices = drvlist.build_unified_driver_list(
                self._prof,
                full=self._full,
                settings=self._settings,
                session_batch=self._session_batch,
                crash_driver=self._crash_driver,
                last_model=self._last_model,
                last_fmt_args=self._last_fmt_args,
            )
            self.finished.emit(self._generation, devices)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(self._generation, str(e))


class SaveHardwareProfileWorker(QtCore.QObject):
    """Persist hardware profile off the UI thread (large all_drivers gzip)."""

    finished = QtCore.Signal(bool)

    def __init__(self, profile: dict, all_drivers: list | None = None) -> None:
        super().__init__()
        self._profile = profile
        self._all_drivers = list(all_drivers or [])

    @QtCore.Slot()
    def run(self) -> None:
        try:
            snap = dict(self._profile)
            bio = dict(snap.get("bios_driver_info") or {})
            if self._all_drivers:
                bio["all_drivers"] = self._all_drivers
            bio.pop("all_drivers_count", None)
            snap["bios_driver_info"] = bio
            if "system_ctx" in snap and isinstance(snap["system_ctx"], dict):
                snap["system_ctx"] = dict(snap["system_ctx"])
            for key in (
                "pnp_list",
                "devices_with_generic_driver",
                "devices_with_driver_problems",
                "ssd_firmware",
            ):
                if key in snap and isinstance(snap[key], list):
                    snap[key] = list(snap[key])
            ok = hwcache.save_profile(snap)
            self.finished.emit(bool(ok))
        except Exception:  # noqa: BLE001
            self.finished.emit(False)


class SsdFirmwareWorker(QtCore.QObject):
    """Reads SSD/NVMe firmware revisions and secondary peripheral inventory."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        pnp_list: list | None = None,
        driver_rows: list | None = None,
    ) -> None:
        super().__init__()
        self._pnp_list = list(pnp_list or [])
        self._driver_rows = list(driver_rows or [])

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.progress.emit("Reading storage firmware…")
            rows = core.get_ssd_firmware_inventory()
            secondary: list[dict] = []
            try:
                import firmware_peripheral_discovery as fpdisc

                self.progress.emit("Discovering USB / system firmware devices…")
                secondary = fpdisc.discover_secondary_firmware_devices(
                    self._pnp_list,
                    self._driver_rows,
                    query_pnp_firmware=True,
                    has_bios=True,
                )
            except Exception:
                secondary = []
            self.finished.emit({"ssd": rows, "secondary": secondary})
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class CatalogContextWorker(QtCore.QObject):
    """Enrich system_ctx for OEM/vendor links without blocking the UI thread."""

    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, system_ctx: dict) -> None:
        super().__init__()
        self._system_ctx = system_ctx

    @QtCore.Slot()
    def run(self) -> None:
        try:
            ctx = drvcat.extend_system_ctx_for_catalog(dict(self._system_ctx))
            self.finished.emit(ctx)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class FirmwareCatalogWorker(QtCore.QObject):
    """Fetches BIOS/UEFI and firmware catalog entries off the UI thread."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        bios_info: dict | None,
        system_ctx: dict,
        pnp_list: list,
        ssd_firmware: list | None = None,
        target_keys: list[str] | None = None,
        secondary_firmware: list | None = None,
    ) -> None:
        super().__init__()
        self._bios = bios_info
        self._system_ctx = system_ctx
        self._pnp_list = pnp_list
        self._ssd_firmware = ssd_firmware or []
        self._target_keys = target_keys
        self._secondary_firmware = secondary_firmware

    @QtCore.Slot()
    def run(self) -> None:
        drvcat.set_gui_catalog_session(True)
        try:
            system_ctx = dict(self._system_ctx)
            system_ctx["_gui_driver_catalog"] = True
            result = fwcat.build_firmware_comparison(
                self._bios,
                system_ctx,
                self._pnp_list,
                self._ssd_firmware,
                progress=lambda m: self.progress.emit(m),
                target_keys=self._target_keys,
                secondary_firmware=self._secondary_firmware,
            )
            self.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
        finally:
            drvcat.set_gui_catalog_session(False)


class InstallDriverWorker(QtCore.QObject):
    """Download (if needed) and install a driver after explicit user confirmation."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str, object, object)  # ok, msg, offer, backup_record
    failed = QtCore.Signal(str, object)

    @staticmethod
    def _is_platform_chipset_device(device_name: str) -> bool:
        try:
            return core.is_platform_chipset_device_key(device_name)
        except AttributeError:
            return device_name.strip() in (
                "__chipset_amd_platform__",
                "__chipset_intel_platform__",
            )

    def __init__(
        self,
        offer: dict,
        device_name: str = "",
        *,
        device_ctx: dict | None = None,
        backup_before: bool = False,
        backup_root: str | None = None,
        backup_keep_count: int = 3,
        create_restore_point: bool = False,
    ) -> None:
        super().__init__()
        self._offer = dict(offer)
        self._device_name = device_name
        self._device_ctx = dict(device_ctx) if device_ctx else None
        self._backup_before = backup_before
        self._backup_root = backup_root
        self._backup_keep_count = backup_keep_count
        self._create_restore_point = create_restore_point

    @QtCore.Slot()
    def run(self) -> None:
        backup_record: dict | None = None
        try:
            if self._create_restore_point:
                self.progress.emit("Creating system restore point…")
                ok_rp, msg_rp, code_rp = drvcat.create_system_restore_point(
                    "BSOD Analyzer before driver install"
                )
                if not ok_rp:
                    if code_rp == "disabled":
                        self.failed.emit(
                            f"{msg_rp}\n\nEnable System Restore or uncheck "
                            "“Create a system restore point” and try again.",
                            self._offer,
                        )
                    else:
                        self.failed.emit(msg_rp, self._offer)
                    return

            if (
                self._backup_before
                and self._device_name.strip()
                and not self._is_platform_chipset_device(self._device_name)
            ):
                import driver_backup as drvbackup

                self.progress.emit("Backing up current driver…")
                ok_b, msg_b, record = drvbackup.backup_device_driver(
                    self._device_name,
                    self._backup_root,
                    progress_cb=lambda m: self.progress.emit(m),
                )
                if not ok_b:
                    self.failed.emit(msg_b, self._offer)
                    return
                backup_record = record
                if self._backup_keep_count > 0:
                    removed, prune_msg = drvbackup.prune_driver_backups(
                        self._backup_root,
                        keep_per_device=self._backup_keep_count,
                    )
                    if removed and prune_msg:
                        self.progress.emit(prune_msg)

            ok, msg, offer = drvinst.install_driver_offer(
                self._offer,
                device_name=self._device_name,
                device_ctx=self._device_ctx,
                progress_cb=lambda m: self.progress.emit(m),
            )
            self._offer = dict(offer)
            if ok:
                self.finished.emit(True, msg, offer, backup_record)
            else:
                self.failed.emit(msg, offer)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e), self._offer)


class PowerShell7InstallWorker(QtCore.QObject):
    """Wait for PowerShell 7 to appear after the user runs the elevated installer."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)  # ok, version or error message

    @QtCore.Slot()
    def run(self) -> None:
        import bsod_runtime as rt

        self.progress.emit("Waiting for PowerShell 7 install to finish…")
        ok, ver = rt.wait_for_powershell7_installed(timeout_sec=180.0, poll_sec=2.0)
        if ok and ver:
            self.finished.emit(True, ver)
        else:
            self.finished.emit(
                False,
                "PowerShell 7 was not detected yet. If the installer showed an error, "
                f"see {rt.powershell7_install_log_path()}.",
            )


class RestoreDriverWorker(QtCore.QObject):
    """Reinstall a backed-up driver folder via pnputil."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)
    failed = QtCore.Signal(str)

    def __init__(self, backup_path: str) -> None:
        super().__init__()
        self._backup_path = backup_path

    @QtCore.Slot()
    def run(self) -> None:
        try:
            import driver_backup as drvbackup

            ok, msg = drvbackup.restore_driver_backup(
                self._backup_path,
                progress_cb=lambda m: self.progress.emit(m),
            )
            if ok:
                self.finished.emit(True, msg)
            else:
                self.failed.emit(msg)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class DriverCatalogWorker(QtCore.QObject):
    """Fetches Microsoft / OEM / vendor driver offers off the UI thread."""

    progress = QtCore.Signal(str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        pnp_list: list,
        system_ctx: dict,
        bios_driver_info: dict | None,
        *,
        driver: str | None = None,
        device_name: str | None = None,
        device_names: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._driver = driver
        self._device_name = device_name
        self._device_names = device_names
        self._pnp_list = pnp_list
        self._system_ctx = system_ctx
        self._bios_driver_info = bios_driver_info

    @QtCore.Slot()
    def run(self) -> None:
        drvcat.set_gui_catalog_session(True)
        try:
            system_ctx = dict(self._system_ctx)
            system_ctx["_gui_driver_catalog"] = True
            try:
                import catalog_cache as ccat
            except ImportError:
                ccat = None  # type: ignore[assignment]
            if ccat is not None and ccat.needs_catalog_refresh(system_ctx=system_ctx):
                self.progress.emit(
                    "Driver database missing or stale — querying live catalogs "
                    "(not blocking on a full refresh)…"
                )
            inventory = core.device_inventory_for_matching(self._bios_driver_info)
            if self._device_names:
                result = drvcat.build_multi_device_driver_comparison(
                    self._device_names,
                    self._pnp_list,
                    inventory,
                    system_ctx,
                    progress=lambda m: self.progress.emit(m),
                )
            elif self._device_name:
                result = drvcat.build_device_driver_comparison(
                    self._device_name,
                    self._pnp_list,
                    inventory,
                    system_ctx,
                    progress=lambda m: self.progress.emit(m),
                )
            else:
                extended = drvcat.extend_system_ctx_for_catalog(system_ctx)
                extended["_gui_driver_catalog"] = True
                dev_ctx = drvcat.get_device_context(
                    self._driver,
                    self._pnp_list,
                    inventory,
                    extended,
                )
                dev_ctx["_batch_driver_check"] = True
                result = drvcat._build_device_comparison_from_ctx(
                    dev_ctx,
                    extended,
                    progress=lambda m: self.progress.emit(m),
                )
            drvcat.persist_session_catalog_cache(system_ctx)
            self.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
        finally:
            drvcat.set_gui_catalog_session(False)


class CatalogExportWorker(QtCore.QObject):
    """Build catalog export payload and write files off the UI thread."""

    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, task_fn) -> None:
        super().__init__()
        self._task_fn = task_fn

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self._task_fn()
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class BackgroundJob:
    """Owns one QThread + worker; safe to stop on window close."""

    def __init__(self) -> None:
        self.thread: QtCore.QThread | None = None
        self.worker: QtCore.QObject | None = None

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def start(
        self,
        worker: QtCore.QObject,
        *,
        connections: list[tuple[object, Callable]] | None = None,
        on_thread_finished: Callable[[], None] | None = None,
    ) -> None:
        self.stop(wait=False)
        thread = QtCore.QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)  # type: ignore[attr-defined]
        for signal, slot in connections or []:
            signal.connect(slot)
        for signal_name in ("finished", "failed"):
            signal = getattr(worker, signal_name, None)
            if signal is not None and hasattr(signal, "connect"):
                signal.connect(thread.quit)
        thread.finished.connect(lambda t=thread: self._clear_thread_refs(t))
        if on_thread_finished:
            thread.finished.connect(on_thread_finished)
        self.thread = thread
        self.worker = worker
        thread.start()

    def _clear_thread_refs(self, thread: QtCore.QThread) -> None:
        if self.thread is thread:
            self.thread = None
            self.worker = None

    def stop(self, *, wait: bool = True, timeout_ms: int = 8000) -> None:
        thread = self.thread
        if thread is None:
            return
        if thread.isRunning():
            thread.quit()
            if wait:
                thread.wait(timeout_ms)
        self.thread = None
        self.worker = None


def stop_jobs(*jobs: BackgroundJob | None, timeout_ms: int = 8000) -> None:
    for job in jobs:
        if job is not None:
            job.stop(wait=True, timeout_ms=timeout_ms)

