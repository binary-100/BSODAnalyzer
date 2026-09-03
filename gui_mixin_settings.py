"""App settings, menu bar, theme, preferences, install mode."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiSettingsMixin:
    def _apply_catalog_from_settings(self) -> None:
        quick = bool(self._settings.get("quick_check_mode"))
        if app_set.is_full_install_mode(self._settings):
            quick = False
        drvcat.configure_catalog(
            quick_check=quick,
            oem_session_cache=self._settings.get("oem_session_cache"),
            catalog_include_preview=self._settings.get("catalog_include_preview"),
        )

    def _save_app_settings(self, *, saved_message: str | None = None) -> bool:
        if app_set.save_settings(self._settings):
            if saved_message:
                self.statusBar().showMessage(saved_message, 4000)
            return True
        err = app_set.peek_settings_save_error()
        if err:
            self.statusBar().showMessage(err[:120], 10000)
        return False

    def _apply_settings(self, new_settings: dict | None = None) -> None:
        if new_settings is not None:
            old_common = self._settings.get("default_include_common_devices", True)
            new_common = new_settings.get("default_include_common_devices", True)
            if old_common != new_common:
                self._drv_include_user_customized = False
            self._settings = new_settings
        ok = self._save_app_settings()
        self._apply_catalog_from_settings()
        self._sync_full_install_driver_tools()
        mode = "full install" if app_set.is_full_install_mode(self._settings) else "portable"
        if ok:
            self.statusBar().showMessage(f"Settings saved ({mode} mode).", 4000)
        self._update_idle_workflow_banners()
        self._update_drivers_tab_cache_status()

    def _build_menu_bar(self) -> None:
        mb = self.menuBar()
        mb.setNativeMenuBar(False)
        mb.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        file_m = mb.addMenu("&File")
        file_m.addAction("Copy diagnosis to clipboard", self._copy_diagnosis)
        file_m.addSeparator()
        _baseline_tip = (
            "A baseline is a small JSON summary of your last analysis (likely driver, "
            "severity, crash timeline, driver-health counts)—not a full report. "
            "Save one after a run, then compare later to see what changed."
        )
        act_baseline_save = QtGui.QAction("Save analysis baseline…", self)
        act_baseline_save.setStatusTip(_baseline_tip)
        act_baseline_save.setToolTip(_baseline_tip)
        act_baseline_save.triggered.connect(self._save_snapshot)
        file_m.addAction(act_baseline_save)
        act_baseline_cmp = QtGui.QAction("Compare to saved baseline…", self)
        act_baseline_cmp.setStatusTip(
            "Open a baseline you saved earlier and show differences versus the current analysis."
        )
        act_baseline_cmp.setToolTip(act_baseline_cmp.statusTip())
        act_baseline_cmp.triggered.connect(self._compare_snapshot)
        file_m.addAction(act_baseline_cmp)
        file_m.addSeparator()
        file_m.addAction("Export report", self.on_export)

        settings_m = mb.addMenu("&Settings")
        settings_m.addAction("Preferences", self._show_preferences)
        settings_m.addAction("Change install mode", self._show_change_install_mode)
        settings_m.addSeparator()
        settings_m.addAction(
            "Enable full install mode",
            self._enable_full_install_mode,
        )
        settings_m.addAction(
            "Enable portable (crash diagnosis)",
            self._enable_portable_mode,
        )

        view_m = mb.addMenu("&View")
        self._theme_action_group = QtGui.QActionGroup(self)
        self._theme_action_group.setExclusive(True)
        self._theme_menu_actions: dict[str, QtGui.QAction] = {}
        import gui_theme as theme

        for theme_id, preset in theme.THEME_PRESETS.items():
            act = QtGui.QAction(str(preset.get("label") or theme_id), self)
            act.setCheckable(True)
            act.setData(theme_id)
            act.triggered.connect(
                lambda checked, tid=theme_id: self._set_ui_theme(tid) if checked else None
            )
            self._theme_action_group.addAction(act)
            view_m.addAction(act)
            self._theme_menu_actions[theme_id] = act
        self._sync_theme_menu_checks()

        tools_m = mb.addMenu("&Tools")
        self._tools_menu = tools_m
        self.drv_act_refresh_list = QtGui.QAction("Drivers — load device list", self)
        self.drv_act_refresh_list.setToolTip(
            "Drivers tab: ① Load devices — full WMI inventory before Search."
        )
        self.drv_act_refresh_list.triggered.connect(self._on_scan_for_devices)
        tools_m.addAction(self.drv_act_refresh_list)
        self.fw_act_refresh_inventory = QtGui.QAction("Firmware — load component list", self)
        self.fw_act_refresh_inventory.setToolTip(
            "Firmware tab: ① Load components — BIOS and SSD inventory before Search."
        )
        self.fw_act_refresh_inventory.triggered.connect(self._on_scan_for_components)
        tools_m.addAction(self.fw_act_refresh_inventory)
        self.drv_act_refresh_database = QtGui.QAction(
            "Refresh driver database", self
        )
        self.drv_act_refresh_database.triggered.connect(self._refresh_driver_database)
        tools_m.addAction(self.drv_act_refresh_database)
        self.act_export_catalog = QtGui.QAction("Export scan results…", self)
        self.act_export_catalog.setToolTip(
            "Save everything compiled this session — crash analysis and/or driver/firmware "
            "scan results — into one folder."
        )
        self.act_export_catalog.triggered.connect(self.export_catalog_scan_results)
        tools_m.addAction(self.act_export_catalog)
        act_cmp_exports = QtGui.QAction("Compare catalog exports…", self)
        act_cmp_exports.setToolTip(
            "Open two saved catalog scan JSON files and show driver status/version "
            "differences (before/after updates or across machines)."
        )
        act_cmp_exports.triggered.connect(self._compare_catalog_exports)
        tools_m.addAction(act_cmp_exports)
        tools_m.addAction("Export full install report", self.export_maintenance_report)
        tools_m.addAction("Activity history", self._show_maintenance_history)
        tools_m.addSeparator()
        tools_m.addAction(
            "Check manufacturer lookup health…",
            self._show_vendor_health_report,
        )
        tools_m.addAction(
            "Audit manufacturer lookup pages…",
            self._run_vendor_lookup_audit,
        )
        tools_m.addAction(
            "Repair manufacturer lookups…",
            self._run_vendor_endpoint_repair,
        )
        tools_m.addSeparator()
        tools_m.addAction(
            "Optional tools — 7-Zip (.7z driver archives)…",
            self._show_seven_zip_optional_tool_info,
        )
        tools_m.addSeparator()
        tools_m.addAction("Clear Windows Update cache", drvcat.clear_wu_driver_cache)
        tools_m.addAction("Clear OEM catalog cache", drvcat.clear_oem_cache)
        tools_m.addAction("Clear check result index", self._clear_check_history)
        tools_m.addSeparator()
        tools_m.addAction("Clean up logs and dumps", self._show_log_cleanup_wizard)

        help_m = mb.addMenu("&Help")
        help_m.addAction("Release notes", self._show_release_notes)
        help_m.addAction("First-run tips", self._show_first_run_tips)
        help_m.addAction("About", self._show_about)

        for menu in (file_m, settings_m, view_m, tools_m, help_m):
            menu.aboutToShow.connect(lambda m=menu: _fix_menu_popup_width(m))

    def _sync_theme_menu_checks(self) -> None:
        import gui_theme as theme

        active = theme.current_theme_id()
        for theme_id, act in getattr(self, "_theme_menu_actions", {}).items():
            act.setChecked(theme_id == active)

    def _set_ui_theme(self, theme_id: str) -> None:
        import gui_theme as theme

        if theme_id not in theme.THEME_PRESETS:
            return
        if theme.current_theme_id() == theme_id:
            self._sync_theme_menu_checks()
            return
        theme.activate_theme(theme_id)
        self._settings[theme.UI_THEME_KEY] = theme_id
        self._save_app_settings()
        self._apply_ui_theme()
        label = theme.THEME_PRESETS[theme_id].get("label") or theme_id
        self.statusBar().showMessage(f"Appearance: {label}.", 4000)

    def _apply_ui_theme(self) -> None:
        import gui_theme as theme

        self.setStyleSheet(theme.STYLESHEET)
        for tbl in (
            getattr(self, "drv_unified_table", None),
            getattr(self, "fw_unified_table", None),
        ):
            if tbl is not None:
                self._apply_unified_catalog_table_style(tbl)
                tbl.viewport().update()
        for hdr in (
            getattr(self, "_drv_include_header", None),
            getattr(self, "_fw_include_header", None),
        ):
            if hdr is not None:
                hdr.refresh()
        if hasattr(self, "_refresh_catalog_row_styles"):
            self._refresh_catalog_row_styles()
        if hasattr(self, "_configure_catalog_filter_controls"):
            self._configure_catalog_filter_controls()
        if hasattr(self, "_refresh_compare_tables_theme"):
            self._refresh_compare_tables_theme()
        for tbl in (
            getattr(self, "drv_compare_table", None),
            getattr(self, "fw_compare_table", None),
        ):
            if tbl is not None:
                self._apply_compare_table_style(tbl)
                tbl.viewport().update()
        if hasattr(self, "_refresh_theme_chrome_from_model"):
            self._refresh_theme_chrome_from_model()
        self._sync_theme_menu_checks()
        if hasattr(self, "_refresh_action_link_button_styles"):
            self._refresh_action_link_button_styles()
        self._apply_catalog_chrome_widgets()
        import gui_app_icon as app_icon

        app_icon.apply_window_icon(self)

    def _show_release_notes(self) -> None:
        path = app_set.release_notes_path()
        if not path:
            QtWidgets.QMessageBox.information(
                self,
                "Release notes",
                "VERSION.txt was not found next to BSODAnalyzer.exe or in the app folder.",
            )
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Release notes",
                f"Could not read {path}:\n{e}",
            )
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Release notes — {path.name}")
        dlg.resize(560, 480)
        lay = QtWidgets.QVBoxLayout(dlg)
        hint = QtWidgets.QLabel(str(path))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        te = QtWidgets.QPlainTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        te.setStyleSheet(f"font-family: {MONO}; font-size: 12px;")
        lay.addWidget(te, 1)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def _show_about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            "BSOD Analyzer",
            f"<b>BSOD Analyzer v{core.VERSION}</b><br><br>"
            "Crash analysis, driver checks, and firmware guidance.<br>"
            "Drivers: optional install when <i>you</i> confirm — never automatic.<br>"
            "Firmware: download-only (no flashing from this app).<br><br>"
            "<b>New in 5.4.12</b><ul>"
            "<li>AMD emblem geometry fix; Drivers/Firmware panel sizing to reduce scroll bars</li>"
            "</ul>"
            "<b>New in 5.4.11</b><ul>"
            "<li>Portable build: onedir layout fixes OneDrive launch crash (Permission denied)</li>"
            "</ul>"
            "<b>New in 5.4.10</b><ul>"
            "<li>AMD vendor icon: official block-arrow emblem in brand red</li>"
            "</ul>"
            "<b>New in 5.4.9</b><ul>"
            "<li>Driver catalog: faster batch checks (parallel devices/sources, batch WU/OEM warm-up)</li>"
            "<li>Drivers/Firmware: table-style Include header checkbox; larger icons/rows; AMD arrow logo</li>"
            "</ul>"
            "<b>New in 5.4.8</b><ul>"
            "<li>Include header checkbox aligns with rows; header no longer clipped</li>"
            "</ul>"
            "<b>New in 5.4.6</b><ul>"
            "<li>Data-folder migration/OneDrive safeguards; frozen CDB probe smoke test</li>"
            "<li>Driver/firmware filter polish; faster analysis (combined WMI pass)</li>"
            "<li>Admin-gated restore/dump actions; ARM64 CDB path search</li>"
            "<li>Severity indicator accessible names for screen readers</li>"
            "</ul>"
            "<b>Also in 5.4.x</b><ul>"
            "<li>Unified crash culprit matching across Summary, System, and Drivers tabs</li>"
            "<li>Manual-only driver/firmware scans after Run Analysis "
            "(Scan driver devices → Include → Search)</li>"
            "<li>Driver index hardening; off-thread device list build</li>"
            "<li>Catalog User-Agent synced to app version; safer download validation</li>"
            "<li>Unified WHEA/thermal crash correlation windows</li>"
            "<li>Limited-access banner when not running as Administrator</li>"
            "</ul>"
            "<b>Also in 5.3.x</b><ul>"
            "<li>GUI/export report parity via shared derivations</li>"
            "<li>Shutdown guards and analysis correctness (newest dump wins)</li>"
            "</ul>"
            "<b>Also in 5.2.x</b><ul>"
            "<li>Unified Drivers &amp; Firmware tabs; reliability events</li>"
            "<li>Full install mode with saved driver database</li>"
            "</ul>"
            "See Help → Release notes for the full changelog.",
        )

    def _show_preferences(self) -> None:
        dlg = gui_prefs.PreferencesDialog(self, self._settings)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._apply_settings(dlg.result_settings())

    def _enable_full_install_mode(self) -> None:
        r = QtWidgets.QMessageBox.question(
            self,
            "Full install mode",
            "Full install saves your device list and driver-check results under "
            "%LOCALAPPDATA%\\BSODAnalyzer, so reboots between update sessions do not "
            "start from scratch.\n\n"
            "Enable full install mode?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self._apply_settings(app_set.apply_full_install_defaults(self._settings))
            if not self._hardware_profile:
                self._restore_cached_hardware_profile()
    def _enable_portable_mode(self) -> None:
        r = QtWidgets.QMessageBox.question(
            self,
            "Portable mode",
            "Portable mode is for diagnosing BSODs and crashes. It clears saved driver "
            "lists and check caches on this PC; use Search for driver updates on the Drivers tab.\n\n"
            "Switch to portable mode?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            app_set.clear_full_install_caches()
            app_set.remove_full_install_settings_file(self._settings)
            self._apply_settings(app_set.apply_portable_defaults(self._settings))
            self._hardware_profile = None
            self._all_devices_loaded = False
            self._session_hw_inventory_ready = False
            if hasattr(self, "drv_unified_table"):
                self.drv_unified_table.setRowCount(0)
                self.drv_scan_status.setText(
                    "Portable (crash troubleshooting) — use Search for driver updates "
                    "on the Drivers tab (inventory stays for this session only)."
                )

    def _show_change_install_mode(self) -> None:
        dlg = gui_prefs.InstallModeChoiceDialog(self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if dlg.choice_is_full():
            self._apply_settings(app_set.apply_full_install_defaults(self._settings))
            self._restore_cached_hardware_profile()
        else:
            app_set.clear_full_install_caches()
            app_set.remove_full_install_settings_file(self._settings)
            self._apply_settings(app_set.apply_portable_defaults(self._settings))
            self._hardware_profile = None
            self._all_devices_loaded = False
            self._session_hw_inventory_ready = False
            if hasattr(self, "drv_unified_table"):
                self.drv_unified_table.setRowCount(0)
                self.drv_scan_status.setText(
                    "Portable (crash troubleshooting) — use Search for driver updates "
                    "on the Drivers tab (inventory stays for this session only)."
                )

    def _restore_cached_hardware_profile(self) -> bool:
        if not app_set.is_full_install_mode(self._settings):
            return False
        prof = hwcache.load_cached_profile()
        if not prof:
            return False
        self._hardware_profile = prof
        self._all_devices_loaded = hwcache.has_full_device_list(prof)
        self._session_hw_inventory_ready = self._all_devices_loaded
        bio = prof.get("bios_driver_info") or {}
        cached_rows = bio.get("all_drivers") or []
        if cached_rows:
            self._set_session_all_drivers(cached_rows)
            bio = dict(bio)
            bio.pop("all_drivers", None)
            bio["all_drivers_count"] = len(cached_rows)
            prof["bios_driver_info"] = bio
        self._update_drivers_tab_status_only(prof)
        self._update_idle_workflow_banners()
        if hasattr(self, "_sync_driver_workflow_buttons"):
            self._sync_driver_workflow_buttons()
        return True

    def _show_log_cleanup_wizard(self) -> None:
        dlg = gui_cleanup.LogCleanupWizard(self)
        dlg.finished_cleanup.connect(self._on_log_cleanup_done)
        dlg.exec()

    @QtCore.Slot(dict)
    def _on_log_cleanup_done(self, result: dict) -> None:
        freed = result.get("freed_mb", 0)
        errs = len(result.get("errors") or [])
        msg = f"Cleanup done — about {freed} MB from dumps/WER."
        if errs:
            msg += f" {errs} error(s); see the dialog for details."
        self.statusBar().showMessage(msg)

    def _show_first_run_tips(self) -> None:
        dlg = gui_prefs.FirstRunTipsDialog(self)
        dlg.exec()
        if dlg.dont_show_again():
            self._settings["first_run_complete"] = True
            self._apply_settings()
