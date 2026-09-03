"""Main window shell: init, menus, tabs layout, toolbar, placeholders."""
from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiShellMixin:
    def __init__(self) -> None:
        super().__init__()
        self._signal_relay = MainWindowSignalRelay(self)
        self.setWindowTitle(f"BSOD Analyzer v{core.VERSION}")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(DEFAULT_WINDOW_MIN_WIDTH, DEFAULT_WINDOW_MIN_HEIGHT)
        self._full_report = ""
        self._last_model = None
        self._show_all_devices = False
        self._all_devices_loaded = False
        self._culprit_tip = ""
        self._thread: QtCore.QThread | None = None
        self._worker: AnalysisWorker | None = None
        self._cdb_thread: QtCore.QThread | None = None
        self._cdb_worker: CdbWorker | None = None
        self._drv_thread: QtCore.QThread | None = None
        self._drv_thread_starting = False
        self._drv_worker: DriverCatalogWorker | None = None
        self._driver_comparison: dict | None = None
        self._driver_batch_comparison: dict | None = None
        self._hardware_profile: dict | None = None
        self._hw_thread: QtCore.QThread | None = None
        self._hw_worker: HardwareScanWorker | None = None
        self._compare_target: str = "summary"  # summary | drivers
        self._firmware_comparison: dict | None = None
        self._fw_check_keys: set[str] = set()
        self._drv_check_names: set[str] = set()
        self._drv_unified_cache: list[dict] = []
        self._drv_all_load_thread: QtCore.QThread | None = None
        self._drv_all_load_worker: LoadAllDriversWorker | None = None
        self._hw_save_thread: QtCore.QThread | None = None
        self._hw_save_worker: SaveHardwareProfileWorker | None = None
        self._drv_table_sync_gen = 0
        self._drv_table_sync_pos = 0
        self._drv_table_sync_active = False
        self._drv_table_sync_on_ready: Callable[[], None] | None = None
        self._drv_table_display: list[dict] = []
        self._drv_tab_ui_stale = True
        self._vendor_health_prompted = False
        self._session_all_drivers: list[dict] = []
        self._drv_load_apply_quiet = False
        self._drv_all_load_quiet = False
        self._ssd_firmware_loaded = False
        self._ssd_fw_thread: QtCore.QThread | None = None
        self._ssd_fw_worker: SsdFirmwareWorker | None = None
        self._ssd_fw_on_ready: Callable[[], None] | None = None
        self._fw_thread: QtCore.QThread | None = None
        self._fw_worker: FirmwareCatalogWorker | None = None
        self._fw_unified_cache: list[dict] = []
        self._install_thread: QtCore.QThread | None = None
        self._install_worker: InstallDriverWorker | None = None
        self._restore_thread: QtCore.QThread | None = None
        self._restore_worker: RestoreDriverWorker | None = None
        self._catalog_refresh_job = gui_workers.BackgroundJob()
        self._catalog_export_job = gui_workers.BackgroundJob()
        self._unified_export_dest_dir: str | None = None
        self._unified_export_choices = None
        self._catalog_stale_prompt_shown = False
        self._catalog_mismatch_toast_shown = False
        self._last_install_context: dict | None = None
        self._post_install_recheck_ctx: dict | None = None
        self._pending_driver_restore_path: str | None = None
        self._force_refresh_device_cache = False
        self._settings = app_set.load_settings()
        self._migrate_catalog_layout_settings()
        self._ignored_devices = app_set.load_ignored_devices()
        # Unchecked Include boxes (excluded from driver/firmware catalog search only).
        self._drv_check_excluded: set[str] = set()
        self._drv_include_user_customized = False
        self._fw_check_excluded: set[str] = set()
        self._fw_include_user_customized = False
        self._pending_auto_crash_linked_catalog: list[str] | None = None
        self._drv_auto_culprit_scan = False
        self._after_hw_driver_search: str | None = None
        self._pending_load_all_drivers_after_hw: tuple[bool, bool] | None = None
        self._pending_driver_search_after_tab_ready = False
        self._pending_firmware_load_after_hw = False
        self._session_hw_inventory_ready = False
        self._drv_manual_queue: list[dict] = []
        self._pending_crash_module_check: dict | None = None
        self._task_progress_depth = 0
        self._analysis_run_active = False
        self._drv_list_build_owns_progress = False
        self._last_fmt_args: tuple | None = None
        self._drv_filter_debounce = QtCore.QTimer(self)
        self._drv_filter_debounce.setSingleShot(True)
        self._drv_filter_debounce.setInterval(200)
        self._drv_filter_debounce.timeout.connect(self._apply_drv_filter)
        self._drv_filter_pending = False
        self._fw_filter_debounce = QtCore.QTimer(self)
        self._fw_filter_debounce.setSingleShot(True)
        self._fw_filter_debounce.setInterval(200)
        self._fw_filter_debounce.timeout.connect(self._apply_fw_filter)
        self._drv_workflow_phase: str = ""
        self._drv_workflow_meta: dict = {}
        # True once the catalog scan reaches the determinate per-device counting
        # phase; keeps the progress bar indeterminate during preparation/warm.
        self._drv_scan_determinate: bool = False
        self._fw_workflow_phase: str = ""
        self._fw_workflow_meta: dict = {}
        self._summary_refresh_timer = QtCore.QTimer(self)
        self._summary_refresh_timer.setSingleShot(True)
        self._summary_refresh_timer.timeout.connect(
            self._start_offthread_summary_refresh
        )
        self._summary_refresh_thread: QtCore.QThread | None = None
        self._summary_refresh_worker: SummaryRefreshWorker | None = None
        self._summary_refresh_generation = 0
        self._summary_refresh_pending = False
        self._analysis_generation = 0
        self._pending_needs_config = False
        self._drv_catalog_generation = 0
        self._drv_catalog_job_generation = 0
        self._drv_list_build_thread: QtCore.QThread | None = None
        self._drv_list_build_worker: BuildDriverListWorker | None = None
        self._drv_list_build_generation = 0
        self._drv_list_build_pending = False
        self._drv_list_build_on_ready: Callable[[], None] | None = None
        self._drv_list_build_pending_full: bool | None = None
        self._fw_catalog_generation = 0
        self._fw_catalog_job_generation = 0
        self._ctx_thread: QtCore.QThread | None = None
        self._ctx_worker: CatalogContextWorker | None = None
        self._ps_thread: QtCore.QThread | None = None
        self._ps_worker: PsMaintenanceWorker | None = None
        self._ps_retry_restore_after_enable = False
        self._system_restore_drive = "C:\\"
        self._shutting_down = False
        self._window_centered = False
        self._last_snapshot_path: str | None = None
        self._apply_catalog_from_settings()

        self._build_menu_bar()

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(16, 8, 16, 10)
        root.setSpacing(8)

        root.addWidget(self._build_admin_notice())
        self._main_tab_host = MainTabHost()
        self.tabs = self._main_tab_host
        tab_header = self._main_tab_host.header_layout()
        self._severity_banner = self._build_banner()
        tab_header.addWidget(self._severity_banner)
        tab_header.addWidget(self._build_task_progress_bar())
        self._build_tabs()
        self._apply_startup_catalog_layout()
        self._sync_driver_workflow_buttons()
        self._sync_fw_workflow_buttons()
        root.addWidget(self._main_tab_host, 1)
        root.addLayout(self._build_toolbar())

        self._sync_global_toolbar_for_tab(self.tabs.currentIndex())
        self.statusBar().showMessage(self._initial_status())
        import gui_theme as theme

        theme.activate_theme(self._settings.get(theme.UI_THEME_KEY, theme.UI_THEME_DEFAULT))
        self._apply_ui_theme()
        self._show_placeholder()
        if app_set.is_full_install_mode(self._settings):
            if self._restore_cached_hardware_profile():
                self.statusBar().showMessage(
                    f"Loaded saved device list ({hwcache.cache_age_summary()}).",
                    8000,
                )
            QtCore.QTimer.singleShot(200, self._preload_driver_index)
            self._update_drivers_tab_cache_status()
        QtCore.QTimer.singleShot(1200, self._maybe_show_onedrive_sync_warning)
        QtCore.QTimer.singleShot(500, self._show_startup_catalog_notices)
        if not self._settings.get("first_run_complete"):
            QtCore.QTimer.singleShot(900, self._show_first_run_tips)
        self._sync_admin_gated_controls()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._window_centered:
            return
        self._window_centered = True
        import gui_theme as theme

        theme.center_window_on_screen(self)

    _ADMIN_GATED_CONTROLS = (
        "btn_dump",
        "btn_restore_point",
        "btn_backup_driver",
        "drv_btn_restore",
        "drv_btn_backup",
        "drv_act_restore_point",
        "drv_act_backup_driver",
    )
    _ADMIN_GATED_TOOLTIP = (
        "Run BSOD Analyzer as administrator to use this action."
    )

    def _sync_admin_gated_controls(self) -> None:
        admin = log_cleanup.is_user_admin()
        for attr in self._ADMIN_GATED_CONTROLS:
            ctrl = getattr(self, attr, None)
            if ctrl is None:
                continue
            ctrl.setEnabled(admin)
            if isinstance(ctrl, QtWidgets.QPushButton):
                ctrl.setToolTip("" if admin else self._ADMIN_GATED_TOOLTIP)
            elif isinstance(ctrl, QtGui.QAction):
                ctrl.setToolTip("" if admin else self._ADMIN_GATED_TOOLTIP)
        for attr in ("btn_enable_restore", "drv_btn_enable_restore", "drv_act_enable_restore"):
            btn = getattr(self, attr, None)
            if btn is None or not btn.isVisible():
                continue
            btn.setEnabled(admin)
            if isinstance(btn, QtWidgets.QPushButton):
                btn.setToolTip("" if admin else self._ADMIN_GATED_TOOLTIP)
            elif isinstance(btn, QtGui.QAction):
                btn.setToolTip("" if admin else self._ADMIN_GATED_TOOLTIP)
        if hasattr(self, "_update_driver_restore_button"):
            self._update_driver_restore_button()
        if hasattr(self, "_sync_action_plan_health_buttons"):
            self._sync_action_plan_health_buttons()


    def _preload_driver_index(self) -> None:
        if drvidx.is_index_enabled(self._settings):
            drvidx.index_stats()

    def _maybe_show_onedrive_sync_warning(self) -> None:
        if self._shutting_down or self._settings.get("onedrive_sync_warn_seen"):
            return
        warn = app_set.data_sync_warning(self._settings)
        if not warn:
            return
        self._settings["onedrive_sync_warn_seen"] = True
        self._save_app_settings()
        QtWidgets.QMessageBox.warning(
            self,
            "OneDrive sync folder",
            f"{warn}\n\n"
            "You can relocate the data folder under Settings → Preferences.",
        )

    def _show_startup_catalog_notices(self) -> None:
        if self._shutting_down:
            return
        msg = drvcat.consume_mscatalog_startup_notice()
        if not msg:
            return
        QtWidgets.QMessageBox.warning(
            self,
            "Microsoft Update Catalog",
            "MSCatalogLTS could not be prepared at startup:\n\n"
            f"{msg}\n\n"
            "Some Microsoft catalog lookups may be unavailable until this is resolved "
            "(try Tools → Repair lookup addresses, or restart as administrator).",
        )

    def _run_powershell7_install_wait(self) -> tuple[bool, str]:
        """Launch elevated installer and poll until pwsh is detected (no app restart)."""
        ok, msg = rt.launch_powershell7_install_elevated()
        if not ok:
            return False, msg

        progress = QtWidgets.QProgressDialog(
            "Installing PowerShell 7…",
            "Cancel wait",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Installing PowerShell 7")
        progress.setMinimumDuration(0)
        progress.setModal(True)
        progress.show()

        thread = QtCore.QThread(self)
        worker = PowerShell7InstallWorker()
        worker.moveToThread(thread)
        loop = QtCore.QEventLoop(self)
        outcome = {"ok": False, "msg": "Install wait cancelled."}

        def _finish(success: bool, detail: str) -> None:
            outcome["ok"] = success
            outcome["msg"] = detail
            if loop.isRunning():
                loop.quit()

        worker.finished.connect(_finish)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        progress.canceled.connect(lambda: _finish(False, "Install wait cancelled."))
        thread.start()
        loop.exec()
        progress.close()
        return outcome["ok"], outcome["msg"]

    def _prompt_powershell7_before_online_scan(self) -> bool:
        """Offer PowerShell 7 install before driver/firmware Search (needs internet anyway).

        Returns True to proceed with Search; False if install was started but not detected yet.
        """
        if self._shutting_down:
            return True
        if not rt.should_prompt_powershell7_upgrade(self._settings):
            return True
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("Install PowerShell 7?")
        box.setText(
            f"Driver Search is {rt.PWSH7_DRIVER_SEARCH_SPEEDUP_LABEL} with PowerShell 7 "
            "than on Windows PowerShell 5.1.\n\nInstall now?"
        )
        box.setTextFormat(QtCore.Qt.TextFormat.RichText)
        box.setInformativeText(
            "Uses the official Microsoft installer. Search can continue when install finishes."
        )
        btn_install = box.addButton("Install now", QtWidgets.QMessageBox.ActionRole)
        btn_continue = box.addButton("Search anyway (slower)", QtWidgets.QMessageBox.AcceptRole)
        btn_dismiss = box.addButton("Don't show again", QtWidgets.QMessageBox.DestructiveRole)
        box.setDefaultButton(btn_install)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_dismiss:
            self._settings["powershell7_upgrade_dismissed"] = True
            self._save_app_settings()
            return True
        if clicked == btn_install:
            ok, detail = self._run_powershell7_install_wait()
            if ok:
                self.statusBar().showMessage(
                    f"PowerShell {detail} ready — catalog Search will use parallel lookups.",
                    12000,
                )
                return True
            QtWidgets.QMessageBox.warning(
                self,
                "PowerShell 7",
                rt.powershell7_install_failure_message(detail),
            )
            return False
        return True

    def _run_cdb_install_wait(self) -> tuple[bool, str]:
        """Install WinDbg/CDB on a worker thread and wait for completion."""
        if self._cdb_thread is not None and self._cdb_thread.isRunning():
            return False, "Debugging Tools install already in progress."

        progress = QtWidgets.QProgressDialog(
            "Installing WinDbg…",
            "Cancel wait",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Installing Debugging Tools")
        progress.setMinimumDuration(0)
        progress.setModal(True)
        progress.show()

        thread = QtCore.QThread(self)
        worker = CdbWorker("install")
        worker.moveToThread(thread)
        loop = QtCore.QEventLoop(self)
        outcome = {"ok": False, "msg": "Install wait cancelled."}

        def _finish(success: bool, detail: str) -> None:
            outcome["ok"] = success
            outcome["msg"] = detail
            if loop.isRunning():
                loop.quit()

        worker.finished.connect(_finish)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        progress.canceled.connect(lambda: _finish(False, "Install wait cancelled."))
        thread.start()
        loop.exec()
        progress.close()
        if outcome["ok"]:
            core.clear_cdb_path_cache()
            if hasattr(self, "_refresh_cdb_status"):
                self._refresh_cdb_status()
        return outcome["ok"], outcome["msg"]

    def _prompt_cdb_before_analysis(self) -> bool:
        """Offer WinDbg install before Run Analysis when online and only bundled CDB exists.

        Returns True to proceed with analysis; False if install was started but failed/waited out.
        """
        if self._shutting_down:
            return True
        if not core.should_prompt_cdb_online_install(self._settings):
            return True
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setWindowTitle("Install latest WinDbg?")
        box.setText(
            "You're online, but this PC does not have Microsoft's WinDbg app yet.\n\n"
            "Install the latest WinDbg now for best minidump analysis?"
        )
        btn_install = box.addButton("Install now", QtWidgets.QMessageBox.ActionRole)
        btn_continue = box.addButton("Run Analysis anyway", QtWidgets.QMessageBox.AcceptRole)
        btn_dismiss = box.addButton("Don't show again", QtWidgets.QMessageBox.DestructiveRole)
        box.setDefaultButton(btn_install)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_dismiss:
            self._settings["cdb_online_install_dismissed"] = True
            self._save_app_settings()
            return True
        if clicked == btn_install:
            ok, detail = self._run_cdb_install_wait()
            if ok:
                self.statusBar().showMessage("WinDbg installed — Run Analysis will use it.", 12000)
                return True
            fail_box = QtWidgets.QMessageBox(self)
            fail_box.setIcon(QtWidgets.QMessageBox.Warning)
            fail_box.setWindowTitle("Debugging Tools (CDB)")
            fail_box.setText(rt.windbg_install_failure_message(detail))
            btn_retry = fail_box.addButton("Try again", QtWidgets.QMessageBox.ActionRole)
            btn_continue = fail_box.addButton(
                "Continue with bundled CDB", QtWidgets.QMessageBox.AcceptRole
            )
            fail_box.setDefaultButton(btn_continue)
            fail_box.exec()
            if fail_box.clickedButton() == btn_continue:
                return True
            return False
        return True

    def _prompt_seven_zip_before_driver_install(
        self,
        *,
        offer: dict | None = None,
        path: str = "",
    ) -> bool:
        """Offer 7-Zip install when a .7z driver package needs it. True = proceed."""
        if self._shutting_down:
            return True
        import driver_install as drvinst

        if not drvinst.needs_seven_zip_but_missing(offer, path=path):
            return True
        if not rt.should_prompt_seven_zip_install(self._settings):
            QtWidgets.QMessageBox.warning(
                self,
                "7-Zip required",
                drvinst.seven_zip_required_message(),
            )
            return False
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setWindowTitle("Install 7-Zip for .7z driver packages")
        box.setText(
            "This driver package uses the <b>.7z</b> archive format.\n\n"
            "<b>Why we ask:</b> BSOD Analyzer needs a standard tool to open .7z "
            "files — the same way Windows opens .zip. Some AMD, Intel, and OEM "
            "drivers ship as .7z. We use <b>7-Zip</b> from 7-zip.org because it is "
            "free, widely trusted, and we do <b>not</b> bundle or modify it "
            "(same approach as PowerShell 7 for faster catalog Search).\n\n"
            "Install 7-Zip once from the official site, restart BSOD Analyzer, "
            "then run Install driver again."
        )
        box.setTextFormat(QtCore.Qt.TextFormat.RichText)
        box.setInformativeText(
            "We never install 7-Zip silently — you download it yourself from 7-zip.org."
        )
        btn_open = box.addButton("Open 7-zip.org download page", QtWidgets.QMessageBox.ActionRole)
        btn_later = box.addButton("Cancel install for now", QtWidgets.QMessageBox.RejectRole)
        btn_dismiss = box.addButton("Don't show again", QtWidgets.QMessageBox.DestructiveRole)
        box.setDefaultButton(btn_open)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_dismiss:
            self._settings["seven_zip_install_dismissed"] = True
            self._save_app_settings()
            return False
        if clicked == btn_open:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(rt.SEVEN_ZIP_INSTALL_URL))
            self.statusBar().showMessage(
                "Opened 7-Zip download page — restart this app after installing.",
                10000,
            )
            return False
        return False

    def _show_seven_zip_optional_tool_info(self) -> None:
        """Tools menu: explain optional 7-Zip dependency for .7z driver archives."""
        installed = rt.seven_zip_available()
        exe = rt.seven_zip_exe() or ""
        status = f"Detected: {exe}" if installed else "Not installed on this PC."
        box = QtWidgets.QMessageBox(self)
        box.setIcon(
            QtWidgets.QMessageBox.Information
            if installed
            else QtWidgets.QMessageBox.Warning
        )
        box.setWindowTitle("Optional tool — 7-Zip")
        box.setText(
            "7-Zip (free, from 7-zip.org) lets BSOD Analyzer open <b>.7z</b> driver "
            "archives. Some vendor packages use .7z instead of .zip or .cab.\n\n"
            f"<b>Status:</b> {status}\n\n"
            "<b>Why optional:</b> Most drivers we find are .cab, .exe, or .zip and "
            "work without 7-Zip. We only need it when you install or download a .7z "
            "package.\n\n"
            "<b>Trust:</b> We do not bundle 7-Zip or run its installer — you install "
            "from the official site, same as our PowerShell 7 suggestion for Search."
        )
        box.setTextFormat(QtCore.Qt.TextFormat.RichText)
        if installed:
            box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        else:
            btn_open = box.addButton(
                "Open official download page",
                QtWidgets.QMessageBox.ActionRole,
            )
            box.addButton(QtWidgets.QMessageBox.Close)
            box.setDefaultButton(btn_open)
            box.exec()
            if box.clickedButton() == btn_open:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(rt.SEVEN_ZIP_INSTALL_URL))
            return
        box.exec()

    def _show_actionable_error(
        self,
        title: str,
        summary: str,
        detail: str,
        *,
        status_ms: int = 10000,
    ) -> None:
        short = summary if len(summary) <= 120 else summary[:117] + "…"
        self.statusBar().showMessage(short, status_ms)
        body = (detail or summary).strip()
        if not body or body == summary.strip():
            QtWidgets.QMessageBox.warning(self, title, summary)
            return
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(summary)
        box.setDetailedText(body)
        box.exec()






    # ---- Tabs ----


