"""Catalog tab chrome bridge: include columns, summary lines, stale refresh prompts."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogShellMixin:
    def _apply_catalog_tab_accessibility(self) -> None:
        pairs = (
            ("drv_view_filter", "Driver list view filter"),
            ("drv_filter", "Driver list text search"),
            ("drv_btn_scan_devices", "Load devices"),
            ("drv_btn_check", "Search for updates"),
            ("drv_unified_table", "Driver device list"),
            ("fw_view_filter", "Firmware component view filter"),
            ("fw_btn_scan_components", "Load components"),
            ("fw_btn_check", "Search for firmware updates"),
            ("fw_unified_table", "Firmware component list"),
        )
        for attr, name in pairs:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setAccessibleName(name)

    def _sync_full_install_driver_tools(self) -> None:
        full = app_set.is_full_install_mode(self._settings)
        act = getattr(self, "drv_act_refresh_database", None)
        if act is not None:
            act.setVisible(full)

    def _repolish_widget_style(self, widget: QtWidgets.QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _apply_catalog_workflow_highlight(
        self,
        load_btn: QtWidgets.QPushButton,
        search_btn: QtWidgets.QPushButton,
        *,
        search_enabled: bool,
        load_enabled: bool,
    ) -> None:
        """Accent the obvious next workflow step (① load vs ② search)."""
        if search_enabled:
            load_btn.setObjectName("")
            search_btn.setObjectName("Primary")
        elif load_enabled:
            load_btn.setObjectName("Primary")
            search_btn.setObjectName("")
        else:
            load_btn.setObjectName("")
            search_btn.setObjectName("")
        for btn in (load_btn, search_btn):
            self._repolish_widget_style(btn)

    def _set_refresh_component_list_ui(
        self, *, enabled: bool, label: str | None = None
    ) -> None:
        label = label or BTN_FW_LOAD
        if hasattr(self, "fw_act_refresh_inventory"):
            self.fw_act_refresh_inventory.setEnabled(enabled)
            self.fw_act_refresh_inventory.setText(label)
        if hasattr(self, "fw_btn_scan_components"):
            self.fw_btn_scan_components.setEnabled(enabled)
            self.fw_btn_scan_components.setText(label)
        self._sync_fw_workflow_buttons()

    def _set_refresh_device_list_ui(
        self, *, enabled: bool, label: str | None = None
    ) -> None:
        import gui_theme as theme

        label = label or BTN_DRV_LOAD
        if hasattr(self, "drv_act_refresh_list"):
            self.drv_act_refresh_list.setEnabled(enabled)
            self.drv_act_refresh_list.setText(label)
        if hasattr(self, "drv_btn_scan_devices"):
            self.drv_btn_scan_devices.setEnabled(enabled)
            self.drv_btn_scan_devices.setText(label)
        self._sync_driver_workflow_buttons()

    def _update_drivers_tab_cache_status(self) -> None:
        self._update_drv_tab_summary_line()

    def _drv_include_column_hidden(self) -> bool:
        if not hasattr(self, "drv_view_filter"):
            return False
        mode = self.drv_view_filter.currentData() or "log_attention"
        return mode == "log_attention"

    def _apply_drv_include_column_visibility(self) -> None:
        if not hasattr(self, "drv_unified_table"):
            return
        hidden = self._drv_include_column_hidden()
        self.drv_unified_table.setColumnHidden(DRV_COL_CHECK, hidden)
        if hasattr(self, "_drv_include_header"):
            self._drv_include_header.refresh()

    def _apply_fw_include_column_visibility(self) -> None:
        if not hasattr(self, "fw_unified_table"):
            return
        hidden = self._fw_include_column_hidden()
        self.fw_unified_table.setColumnHidden(FW_COL_CHECK, hidden)
        if hasattr(self, "_fw_include_header"):
            self._fw_include_header.refresh()

    def _sync_drv_include_header(self) -> None:
        if not hasattr(self, "_drv_include_header"):
            return
        names = self._drv_visible_device_names()
        included = sum(1 for n in names if self._drv_include_checked(n))
        self._drv_include_header.sync_from_rows(included, len(names))
        self._drv_include_header.refresh()

    def _sync_fw_include_header(self) -> None:
        if not hasattr(self, "_fw_include_header"):
            return
        keys = self._fw_visible_keys()
        included = sum(1 for k in keys if k not in self._fw_check_excluded)
        self._fw_include_header.sync_from_rows(included, len(keys))
        self._fw_include_header.refresh()

    def _on_drv_include_header_changed(self, checked: bool) -> None:
        if checked:
            self._drv_select_all_visible()
        else:
            self._drv_clear_all_visible()

    def _on_fw_include_header_changed(self, checked: bool) -> None:
        if checked:
            self._fw_select_all_visible()
        else:
            self._fw_clear_all_visible()
        self._sync_fw_workflow_buttons()

    def _fw_include_column_hidden(self) -> bool:
        if not hasattr(self, "fw_view_filter"):
            return False
        mode = self.fw_view_filter.currentData() or "log_attention"
        return mode == "log_attention"

    def _sync_global_toolbar_for_tab(self, index: int) -> None:
        drv_idx = self._drivers_tab_index() if hasattr(self, "_drivers_tab_widget") else -1
        fw_idx = self._firmware_tab_index() if hasattr(self, "_firmware_tab_widget") else -1
        on_catalog_tab = index in (drv_idx, fw_idx)
        show_banner = not on_catalog_tab
        prog_vis = hasattr(self, "_header_progress_shown") and self._header_progress_shown()
        if hasattr(self, "_main_tab_host"):
            self._main_tab_host.set_header_visible(show_banner or prog_vis)
        if hasattr(self, "_severity_banner"):
            self._severity_banner.setVisible(show_banner)
        if hasattr(self, "_sync_task_progress_layout_for_tab"):
            self._sync_task_progress_layout_for_tab(index)
        self._mirror_task_progress_to_catalog_tabs()
        if hasattr(self, "_mirror_task_progress_to_catalog_status"):
            self._mirror_task_progress_to_catalog_status()
        on_drv = index == drv_idx
        on_fw = index == fw_idx
        if hasattr(self, "btn_search_driver_updates"):
            self.btn_search_driver_updates.setVisible(not on_catalog_tab)
        if hasattr(self, "drv_btn_install"):
            self.drv_btn_install.setVisible(on_drv)
        if hasattr(self, "drv_btn_open_catalog"):
            self.drv_btn_open_catalog.setVisible(on_drv)
        if hasattr(self, "drv_btn_restore_driver"):
            self.drv_btn_restore_driver.setVisible(on_drv)
            if on_drv:
                self._update_driver_restore_button()
        if hasattr(self, "fw_btn_download"):
            self.fw_btn_download.setVisible(on_fw)
        if hasattr(self, "fw_btn_set_installed"):
            self.fw_btn_set_installed.setVisible(on_fw)

    def _sync_tab_header_visibility(self) -> None:
        if not hasattr(self, "_main_tab_host"):
            return
        drv_idx = self._drivers_tab_index() if hasattr(self, "_drivers_tab_widget") else -1
        fw_idx = self._firmware_tab_index() if hasattr(self, "_firmware_tab_widget") else -1
        on_catalog_tab = self.tabs.currentIndex() in (drv_idx, fw_idx)
        show_banner = not on_catalog_tab
        prog_vis = hasattr(self, "_header_progress_shown") and self._header_progress_shown()
        self._main_tab_host.set_header_visible(show_banner or prog_vis)
        if hasattr(self, "_severity_banner"):
            self._severity_banner.setVisible(show_banner)
        if hasattr(self, "_sync_task_progress_layout_for_tab"):
            self._sync_task_progress_layout_for_tab()
        self._mirror_task_progress_to_catalog_tabs()

    def _compact_portable_drv_hint(self) -> str:
        if app_set.is_full_install_mode(self._settings):
            idx = drvidx.index_stats()
            total = idx.get("total", 0)
            return f"full install · index {total} cached" if total else "full install"
        if self._session_hw_inventory_ready and self._hardware_profile:
            return "portable · session list loaded"
        return "portable · search to check"

    def _update_drv_tab_summary_line(self, prof: dict | None = None) -> None:
        if not hasattr(self, "drv_scan_status"):
            return
        if prof is None:
            prof = self._hardware_profile or {}
        shown_n = len(self._drv_table_display)
        cache_n = len(self._drv_unified_cache)
        culprit_n = sum(
            1 for d in self._drv_unified_cache if self._dev_needs_analysis_attention(d)
        )
        outdated_n = sum(
            1
            for d in self._drv_unified_cache
            if d.get("_scan_verified") and d.get("_check_status") == "newer"
        )
        parts: list[str] = []
        if culprit_n and self._has_crash_analysis_context():
            parts.append(
                f"{culprit_n} need attention"
                if culprit_n != 1
                else "1 needs attention"
            )
        elif shown_n:
            parts.append(f"{shown_n} device(s)")
        if shown_n and cache_n and shown_n != cache_n:
            parts.append(f"showing {shown_n} of {cache_n}")
        if outdated_n:
            parts.append(f"{outdated_n} update(s)")
        parts.append(self._compact_portable_drv_hint())
        phase = self._drv_workflow_phase
        meta = self._drv_workflow_meta
        if phase == "scanning":
            checked = int(meta.get("checked") or 0)
            total = int(meta.get("total") or 0)
            detail = (meta.get("batch_note") or "").strip()
            if total > 0:
                line = f"Searching driver catalogs… {checked}/{total} device(s)"
                if detail:
                    line = f"{line} — {detail}"
                self.drv_scan_status.setText(line)
            else:
                self.drv_scan_status.setText(
                    f"Searching driver catalogs… {shown_n or cache_n} device(s) in list"
                )
            return
        elif phase == "finalizing":
            detail = (meta.get("batch_note") or "").strip()
            self.drv_scan_status.setText(
                detail or "Finalizing driver catalog…"
            )
            return
        elif phase == "done":
            checked = meta.get("checked", 0)
            updates = meta.get("updates", 0)
            if checked:
                parts.append(f"checked {checked}")
            if updates:
                parts.append(f"{updates} update(s) found")
        elif phase == "failed":
            parts.append("search failed")
        elif not prof and not self._last_model:
            parts.append("use Search or Scan driver devices")
        elif (
            not self._all_devices_loaded
            and not self._full_driver_rows(prof)
            and (self.drv_view_filter.currentData() or "") in ("all", "common", "uncommon")
        ):
            parts.append("refresh list in Tools for full inventory")
        scan_sm = drvcat.catalog_scan_mode_summary(
            full_install=app_set.is_full_install_mode(self._settings),
            quick_check=bool(self._settings.get("quick_check_mode")),
            gui_mode=True,
        )
        parts.append(scan_sm.get("mode") or "")
        line = " · ".join(p for p in parts if p)
        self.drv_scan_status.setText(line or "Select devices and search for updates")
        tip_parts: list[str] = []
        if prof:
            tip_parts.append(
                f"Scanned {len(prof.get('pnp_list') or [])} PnP devices · "
                f"{cache_n} indexed in memory"
            )
            gen = prof.get("devices_with_generic_driver") or []
            probs = prof.get("devices_with_driver_problems") or []
            if gen:
                tip_parts.append(f"{len(gen)} generic driver(s)")
            if probs:
                tip_parts.append(f"{len(probs)} driver problem(s)")
        if app_set.is_full_install_mode(self._settings):
            payload = hwcache.load_cache_payload()
            hw_line = (
                hwcache.cache_age_summary(payload)
                if payload
                else "Device list: not saved yet"
            )
            tip_parts.append(app_set.last_maintenance_summary(self._settings))
            tip_parts.append(f"Device list: {hw_line}")
            tip_parts.append(ccat.catalog_age_summary())
        else:
            tip_parts.append(
                "Portable mode: device list and catalog results are session-only."
            )
        tip_parts.append(
            "Red = crash suspect · Yellow = update available · "
            "Include column appears outside Needs attention filter."
        )
        tip_parts.append(scan_sm.get("detail") or "")
        wf.drv_workflow_banner_text(
            full_install=app_set.is_full_install_mode(self._settings),
            crash_context=self._has_crash_analysis_context(),
            hardware_ready=bool(prof),
            phase=phase or "idle",
            updates=meta.get("updates", 0),
            checked=meta.get("checked", 0),
            batch_note=meta.get("batch_note", ""),
            crash_driver=(self._last_model or {}).get("driver") or "",
        )
        if phase:
            tip_parts.insert(
                0,
                wf.drv_workflow_banner_text(
                    full_install=app_set.is_full_install_mode(self._settings),
                    crash_context=self._has_crash_analysis_context(),
                    hardware_ready=bool(prof),
                    phase=phase,
                    updates=meta.get("updates", 0),
                    checked=meta.get("checked", 0),
                    batch_note=meta.get("batch_note", ""),
                    crash_driver=(self._last_model or {}).get("driver") or "",
                ),
            )
        self.drv_scan_status.setToolTip("\n".join(t for t in tip_parts if t))

    def _update_fw_tab_summary_line(self) -> None:
        if not hasattr(self, "fw_scan_status"):
            return
        row_n = self.fw_unified_table.rowCount() if hasattr(self, "fw_unified_table") else 0
        total_n = len(self._fw_unified_cache)
        culprit_n = sum(1 for d in self._fw_unified_cache if d.get("_tier") == "culprit")
        outdated_n = sum(1 for d in self._fw_unified_cache if d.get("_tier") == "outdated")
        parts: list[str] = []
        if culprit_n:
            parts.append(f"{culprit_n} crash-related")
        elif row_n:
            parts.append(f"{row_n} component(s)")
        if row_n and total_n and row_n != total_n:
            parts.append(f"showing {row_n} of {total_n}")
        if outdated_n:
            parts.append(f"{outdated_n} update(s)")
        if not self._ssd_firmware_loaded:
            parts.append("Scan firmware components to load SSD rows")
        phase = self._fw_workflow_phase
        meta = self._fw_workflow_meta
        if phase == "scanning":
            parts.append("searching…")
        elif phase == "done" and meta.get("updates"):
            parts.append(f"{meta['updates']} update(s) found")
        elif phase == "failed":
            parts.append("search failed")
        scan_sm = drvcat.catalog_scan_mode_summary(
            full_install=app_set.is_full_install_mode(self._settings),
            quick_check=bool(self._settings.get("quick_check_mode")),
            gui_mode=True,
        )
        parts.append(scan_sm.get("mode") or "")
        line = " · ".join(p for p in parts if p)
        self.fw_scan_status.setText(
            line or "Download-only — never auto-flashes BIOS or SSD firmware"
        )
        fw_tip = [
            "Check Include on components (visible outside Needs attention), "
            "then Search for firmware updates. Scan firmware components loads SSD rows.",
            scan_sm.get("detail") or "",
        ]
        self.fw_scan_status.setToolTip("\n".join(t for t in fw_tip if t))

    def _catalog_system_ctx_from_profile(self) -> dict:
        """Return profile system_ctx without blocking WMI/PowerShell on the UI thread."""
        prof = self._hardware_profile or {}
        return dict(prof.get("system_ctx") or {})

    def _catalog_background_busy(self) -> bool:
        """True while driver catalog, hardware scan, or deep DB refresh is running."""
        return bool(
            self._drv_catalog_thread_busy()
            or self._catalog_refresh_job.is_running()
            or (self._hw_thread and self._hw_thread.isRunning())
        )

    def _bind_catalog_from_profile(self) -> None:
        ctx = self._catalog_system_ctx_from_profile()
        if ctx:
            ccat.bind_catalog_system_ctx(ctx)

    def _catalog_ctx_is_complete(self, ctx: dict) -> bool:
        return bool(
            ctx.get("video_controllers")
            and ctx.get("service_tag")
            and ctx.get("baseboard_product")
            and ctx.get("system_model")
        )

    def _schedule_catalog_context_enrichment(self, *, quiet: bool = False) -> None:
        """Enrich system_ctx off the UI thread (service tag, baseboard, GPU list)."""
        if self._shutting_down:
            return
        if self._catalog_background_busy():
            QtCore.QTimer.singleShot(
                500, lambda q=quiet: self._schedule_catalog_context_enrichment(quiet=q)
            )
            return
        prof = self._hardware_profile
        if not prof:
            return
        ctx = dict(prof.get("system_ctx") or {})
        if self._catalog_ctx_is_complete(ctx):
            return
        if self._ctx_thread and self._ctx_thread.isRunning():
            return
        if not quiet and hasattr(self, "fw_support_links"):
            self.fw_support_links.setText("Support: loading vendor links…")
            self.fw_support_links.setVisible(True)
        self._ctx_thread = QtCore.QThread()
        self._ctx_worker = CatalogContextWorker(ctx)
        self._ctx_worker.moveToThread(self._ctx_thread)
        self._ctx_thread.started.connect(self._ctx_worker.run)
        self._ctx_worker.finished.connect(self._signal_relay.catalog_context_ready)
        self._ctx_worker.failed.connect(self._signal_relay.catalog_context_failed)
        self._ctx_worker.finished.connect(self._ctx_thread.quit)
        self._ctx_worker.failed.connect(self._ctx_thread.quit)
        self._ctx_thread.finished.connect(self._cleanup_catalog_context_thread)
        self._ctx_thread.start()

    def _maybe_notify_portable_cache_mismatch(self) -> None:
        if (
            self._catalog_mismatch_toast_shown
            or self._shutting_down
            or self._catalog_background_busy()
        ):
            return
        ctx = self._catalog_system_ctx_from_profile()
        if not ccat.system_ctx_has_catalog_identity(ctx):
            return
        try:
            msg = ccat.portable_cache_mismatch_message(ctx)
            if not msg:
                return
        except Exception:
            return
        self._catalog_mismatch_toast_shown = True
        self.statusBar().showMessage(msg, 15000)

    def _defer_stale_catalog_refresh_prompt(self) -> None:
        """Defer stale-cache dialog so tab switches never block the UI thread."""
        if self._catalog_stale_prompt_shown or self._shutting_down:
            return
        QtCore.QTimer.singleShot(0, self._maybe_prompt_stale_catalog_refresh)

    def _maybe_prompt_stale_catalog_refresh(self) -> None:
        """Once per session: offer Refresh driver database when disk cache is stale (B9)."""
        if self._catalog_stale_prompt_shown or self._shutting_down:
            return
        if not self._hardware_profile:
            return
        if self._catalog_background_busy():
            return
        try:
            ctx = self._catalog_system_ctx_from_profile()
            if not ccat.system_ctx_has_catalog_identity(ctx):
                return
            if not ccat.should_prompt_catalog_refresh(self._settings, system_ctx=ctx):
                return
        except Exception:
            return
        self._catalog_stale_prompt_shown = True
        age_line = ccat.catalog_age_summary(system_ctx=ctx)
        reply = QtWidgets.QMessageBox.question(
            self,
            "Driver database",
            f"The on-disk driver database looks stale.\n\n{age_line}\n\n"
            "Refresh now? This queries Windows Update and OEM sources in the "
            "background (several minutes, internet required). Nothing installs "
            "automatically.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self._refresh_driver_database()

    def _refresh_driver_database(self) -> None:
        if self._drv_catalog_thread_busy():
            QtWidgets.QMessageBox.warning(
                self,
                "Refresh driver database",
                "A driver catalog search is still running.\n\n"
                "Wait for it to finish (or close and restart the app) before "
                "refreshing the on-disk driver database.",
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Refresh driver database",
            "This performs a full Windows Update query and OEM vendor scan. "
            "It can take several minutes and uses the internet.\n\n"
            "Nothing installs automatically. Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        if self._drv_catalog_thread_busy():
            QtWidgets.QMessageBox.warning(
                self,
                "Refresh driver database",
                "A driver catalog search started while this dialog was open.\n\n"
                "Wait for it to finish before refreshing the driver database.",
            )
            return
        prof = self._hardware_profile or {}
        ctx = dict(prof.get("system_ctx") or {})
        self._begin_task_progress("Refreshing driver database…", maximum=0)
        self.statusBar().showMessage("Refreshing driver database…")
        if hasattr(self, "drv_btn_check"):
            self.drv_btn_check.setEnabled(False)
        if hasattr(self, "btn_search_driver_updates"):
            self.btn_search_driver_updates.setEnabled(False)

        class _DbWorker(QtCore.QObject):
            finished = QtCore.Signal(bool, str)
            progress = QtCore.Signal(str)

            def __init__(self, system_ctx: dict) -> None:
                super().__init__()
                self._system_ctx = dict(system_ctx)

            @QtCore.Slot()
            def run(self) -> None:
                work_ctx = dict(self._system_ctx)
                if not work_ctx.get("system_manufacturer"):
                    work_ctx = drvcat.extend_system_ctx_for_catalog(work_ctx)
                ok, msg = ccat.refresh_driver_database(
                    work_ctx,
                    progress=lambda m: self.progress.emit(m),
                )
                self.finished.emit(ok, msg)

        def _done(ok: bool, msg: str) -> None:
            self._end_task_progress()
            if hasattr(self, "drv_btn_check"):
                self.drv_btn_check.setEnabled(True)
            if hasattr(self, "btn_search_driver_updates"):
                self.btn_search_driver_updates.setEnabled(True)
            if self._shutting_down:
                return
            mlog.append_event("catalog_refresh", "Manual driver database refresh", detail=msg)
            if ok:
                self._catalog_stale_prompt_shown = False
                self._record_maintenance_activity("Driver database refresh", detail=msg)
                QtWidgets.QMessageBox.information(self, "Driver database", msg)
            else:
                QtWidgets.QMessageBox.warning(self, "Driver database", msg)
                self._update_drivers_tab_cache_status()

        if self._catalog_refresh_job.is_running():
            return
        worker = _DbWorker(ctx)
        self._catalog_refresh_job.start(
            worker,
            connections=[
                (worker.progress, lambda m: self.statusBar().showMessage(m[:120])),
                (worker.finished, _done),
            ],
        )
