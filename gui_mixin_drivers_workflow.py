"""Drivers tab search workflow, crash-linked catalog, summary/reliability UI."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversWorkflowMixin:
    def _prepare_full_driver_catalog_search(self) -> None:
        """② Search for updates always scans every catalog-eligible device."""
        if hasattr(self, "drv_view_filter"):
            idx = self.drv_view_filter.findData("all")
            if idx >= 0 and self.drv_view_filter.currentIndex() != idx:
                self.drv_view_filter.blockSignals(True)
                self.drv_view_filter.setCurrentIndex(idx)
                self.drv_view_filter.blockSignals(False)
        self._drv_include_user_customized = False
        prof = self._hardware_profile
        if prof and self._drv_unified_cache:
            self._apply_all_devices_include_defaults(prof)
            self._drv_apply_include_column_states()

    def _apply_driver_only_view_defaults(self) -> None:
        """Default to All devices unless crash analysis named a faulting driver module."""
        if not hasattr(self, "drv_view_filter"):
            return
        if self._has_crash_faulting_driver():
            idx = self.drv_view_filter.findData("log_attention")
        else:
            idx = self.drv_view_filter.findData("all")
        if idx >= 0 and self.drv_view_filter.currentIndex() != idx:
            self.drv_view_filter.blockSignals(True)
            self.drv_view_filter.setCurrentIndex(idx)
            self.drv_view_filter.blockSignals(False)

    def _ensure_drivers_tab_visible_rows(self, prof: dict) -> bool:
        """When the active view filter hides every cached row, fall back to All devices."""
        if not self._drv_unified_cache or self._drv_table_display:
            return False
        if not hasattr(self, "drv_view_filter"):
            return False
        mode = self.drv_view_filter.currentData() or "log_attention"
        if mode == "all":
            return False
        idx = self.drv_view_filter.findData("all")
        if idx < 0 or self.drv_view_filter.currentIndex() == idx:
            return False
        self.drv_view_filter.blockSignals(True)
        self.drv_view_filter.setCurrentIndex(idx)
        self.drv_view_filter.blockSignals(False)
        self._rebuild_drv_table_display()
        if hasattr(self, "drv_scan_status"):
            self.drv_scan_status.setText(
                f"No rows matched the current view — showing all "
                f"{len(self._drv_unified_cache)} device(s)."
            )
        return True

    def _drv_device_list_ready_for_search(self) -> bool:
        """True after device list is built and safe to run catalog search."""
        if self._drv_list_build_thread and self._drv_list_build_thread.isRunning():
            return False
        if self._drv_table_sync_active:
            return False
        if not self._drv_unified_cache:
            return False
        if self._all_devices_loaded:
            return True
        prof = self._hardware_profile
        if prof and self._session_hw_inventory_ready and self._hardware_inventory_ready():
            if len(self._drv_unified_cache) >= 1:
                return True
            rows = self._full_driver_rows(prof)
            if rows and self._driver_list_looks_full(rows, prof):
                return True
        return False

    def _driver_catalog_search_busy(self) -> bool:
        return self._drv_catalog_thread_busy()

    def _drv_search_button_enabled(self) -> bool:
        return (
            self._drv_device_list_ready_for_search()
            and not self._driver_catalog_search_busy()
        )

    def _sync_driver_workflow_buttons(self) -> None:
        if not hasattr(self, "drv_btn_scan_devices"):
            return
        import gui_theme as theme

        load_running = (
            self._drv_all_load_thread is not None
            and self._drv_all_load_thread.isRunning()
        )
        hw_scan_running = (
            self._hw_thread is not None and self._hw_thread.isRunning()
        )
        catalog_search_busy = self._drv_catalog_thread_busy()
        load_blocked = load_running or hw_scan_running or catalog_search_busy
        if load_blocked:
            self.drv_btn_scan_devices.setEnabled(False)
        else:
            self.drv_btn_scan_devices.setEnabled(True)
            if self.drv_btn_scan_devices.isEnabled():
                self.drv_btn_scan_devices.setText(theme.BTN_DRV_LOAD)
        search_ok = self._drv_search_button_enabled()
        if hasattr(self, "drv_btn_check"):
            self.drv_btn_check.setEnabled(search_ok)
        if hasattr(self, "btn_search_driver_updates"):
            self.btn_search_driver_updates.setEnabled(search_ok)
        if hasattr(self, "drv_btn_scan_devices") and hasattr(self, "drv_btn_check"):
            self._apply_catalog_workflow_highlight(
                self.drv_btn_scan_devices,
                self.drv_btn_check,
                search_enabled=search_ok,
                load_enabled=self.drv_btn_scan_devices.isEnabled(),
            )

    def _apply_all_devices_include_defaults(self, prof: dict) -> None:
        """When filter is All devices, include every catalog-eligible row for Search."""
        if getattr(self, "_drv_include_user_customized", False):
            return
        for dev in self._drv_unified_cache:
            name = (dev.get("name") or "").strip()
            if not name:
                continue
            if self._drv_device_excluded_from_catalog(dev):
                self._drv_check_excluded.add(name)
            else:
                self._drv_check_excluded.discard(name)

    def _apply_search_include_defaults(self, prof: dict) -> None:
        mode = (
            self.drv_view_filter.currentData()
            if hasattr(self, "drv_view_filter")
            else "all"
        )
        if mode == "all":
            self._apply_all_devices_include_defaults(prof)
        else:
            self._apply_common_device_include_defaults(prof)

    def _continue_driver_search_after_tab_ready(self) -> None:
        prof = self._hardware_profile
        if prof:
            self._prepare_full_driver_catalog_search()
        names = self._drv_checked_device_names()
        if not names:
            self._end_task_progress()
            self.drv_btn_check.setEnabled(self._drv_search_button_enabled())
            QtWidgets.QMessageBox.information(
                self,
                "Driver check",
                "No devices are included for search. Switch the filter to All devices "
                "or check Include on one or more rows, then try again.",
            )
            return
        self._on_check_driver_catalog(for_drivers_tab=True)

    def _driver_search_workflow_busy(self) -> bool:
        return (
            (self._hw_thread is not None and self._hw_thread.isRunning())
            or (
                self._drv_all_load_thread is not None
                and self._drv_all_load_thread.isRunning()
            )
            or (
                self._drv_list_build_thread is not None
                and self._drv_list_build_thread.isRunning()
            )
            or self._drv_catalog_thread_busy()
        )

    def _driver_inventory_available(self) -> bool:
        prof = self._hardware_profile
        if not prof:
            return False
        if self._full_driver_rows(prof):
            return True
        bio = prof.get("bios_driver_info") or {}
        return bool(core.device_inventory_for_matching(bio))

    def _cancel_chained_driver_search_workflow(self, *, re_enable_buttons: bool = True) -> bool:
        """Clear one-click search state; return True if a chained search was in progress."""
        chaining = self._after_hw_driver_search == "checked"
        self._after_hw_driver_search = None
        self._pending_load_all_drivers_after_hw = None
        self._pending_driver_search_after_tab_ready = False
        if re_enable_buttons:
            self._sync_driver_workflow_buttons()
        return chaining

    def _on_scan_for_devices(self) -> None:
        """WMI load for the full Drivers tab device list (step 1 — not catalog search)."""
        idx = self._drivers_tab_index()
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        if self._driver_search_workflow_busy():
            self.statusBar().showMessage("Device list load already in progress…", 5000)
            return
        self._sync_driver_workflow_buttons()
        self._start_load_all_driver_devices(force_refresh=True, quiet=False)

    def _on_begin_driver_update_workflow(self) -> None:
        """Hardware inventory (if needed), then driver catalog search on Include devices."""
        idx = self._drivers_tab_index()
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        if self._driver_search_workflow_busy():
            self.statusBar().showMessage(
                "Driver update search already in progress…", 5000
            )
            return
        if self._block_if_other_catalog_busy("driver"):
            return
        if not self._drv_device_list_ready_for_search():
            import gui_theme as theme

            self.statusBar().showMessage(
                f"Complete {theme.BTN_DRV_LOAD} before searching for updates.",
                10000,
            )
            QtWidgets.QMessageBox.information(
                self,
                "Load device list first",
                f"Run {theme.BTN_DRV_LOAD} on the Drivers tab and wait for the list "
                f"to finish loading, then use {theme.BTN_DRV_SEARCH}.",
            )
            return
        if not self._prompt_powershell7_before_online_scan():
            return
        import driver_catalog as drvcat

        drvcat.clear_installed_package_versions_cache()
        self.drv_btn_check.setEnabled(False)
        if hasattr(self, "btn_search_driver_updates"):
            self.btn_search_driver_updates.setEnabled(False)
        self._sync_driver_workflow_buttons()
        self._begin_task_progress("Starting driver update search…", maximum=0)
        self.statusBar().showMessage("Starting driver update search…")
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )
        self._after_hw_driver_search = "checked"
        need_hw, reason = self._needs_hardware_profile_scan()
        if need_hw:
            if reason:
                self._set_task_progress(label=f"{reason}…")
                self.statusBar().showMessage(f"Driver search — {reason}…", 6000)
            self._start_hardware_scan()
            return
        if not self._drv_device_list_ready_for_search():
            self._after_hw_driver_search = None
            self._end_task_progress()
            self._sync_driver_workflow_buttons()
            import gui_theme as theme

            self.statusBar().showMessage(
                f"Complete {theme.BTN_DRV_LOAD} before searching for updates.",
                10000,
            )
            QtWidgets.QMessageBox.information(
                self,
                "Load device list first",
                f"Run {theme.BTN_DRV_LOAD} on the Drivers tab and wait for the list "
                f"to finish loading, then use {theme.BTN_DRV_SEARCH}.",
            )
            return
        if not self._driver_inventory_available():
            self._after_hw_driver_search = None
            self._end_task_progress()
            self._sync_driver_workflow_buttons()
            self.statusBar().showMessage(
                "No device inventory yet — run ① Load devices first.",
                10000,
            )
            QtWidgets.QMessageBox.information(
                self,
                "Device inventory required",
                "No driver devices are loaded yet.\n\n"
                "Click ① Load devices on the Drivers tab, then run "
                "② Search for updates.",
            )
            return
        if not self._drv_unified_cache and self._ensure_hardware_profile():
            self._set_task_progress(label="Building device list…", maximum=0)
            self._drv_tab_ui_stale = True
            self._pending_driver_search_after_tab_ready = True
            self._populate_drivers_tab()
            return
        self._finish_hw_then_continue_driver_search()

    def _finish_hw_then_continue_driver_search(self) -> None:
        """Run catalog checks after inventory is ready (hardware step already done)."""
        self._session_hw_inventory_ready = True
        self._refresh_model_culprit_driver_info()
        self._schedule_refresh_summary_from_inventory()
        mode = self._after_hw_driver_search
        self._after_hw_driver_search = None
        self._sync_driver_workflow_buttons()
        if mode != "checked":
            return
        if not self._has_crash_analysis_context():
            self._apply_driver_only_view_defaults()
            self._pending_driver_search_after_tab_ready = True
            self._drv_tab_ui_stale = True
            self._populate_drivers_tab()
            return
        prof = self._hardware_profile
        if prof and (not self._drv_unified_cache or self._drv_tab_ui_stale):
            self._pending_driver_search_after_tab_ready = True
            self._populate_drivers_tab()
            return
        if prof:
            self._prepare_full_driver_catalog_search()
        self._continue_driver_search_after_tab_ready()

    def _update_drv_workflow_banner(
        self,
        phase: str,
        *,
        updates: int = 0,
        checked: int = 0,
        total: int = 0,
        batch_note: str = "",
    ) -> None:
        self._drv_workflow_phase = (phase or "").strip()
        self._drv_workflow_meta = {
            "updates": updates,
            "checked": checked,
            "total": total,
            "batch_note": batch_note,
        }
        self._update_drv_tab_summary_line()

    def _crash_report_driver_names(self, m: dict | None = None) -> list[str]:
        """Device names tied to the crash report (faulting module or platform chipset focus)."""
        model = m or self._last_model or {}
        driver = model.get("driver")
        drv_ver = model.get("driver_verification") or {}
        platform_focus = bool((drv_ver.get("attribution") or {}).get("platform_chipset_focus"))
        if not core.has_crash_faulting_driver(driver) and not platform_focus:
            return []
        prof = self._hardware_profile or self._profile_from_model(model)
        bio = (prof or {}).get("bios_driver_info") or model.get("bios_driver_info") or {}
        ctx = (prof or {}).get("system_ctx") or model.get("system_ctx") or {}
        resolved = core.resolve_crash_culprit_context(
            driver,
            bio,
            code_val=model.get("stop_code_val"),
            system_ctx=ctx,
            cause_type=model.get("cause_type"),
            fix_plan=model.get("fix_plan"),
            has_crash_context=self._has_crash_analysis_context(),
        )
        if platform_focus and not core.has_crash_faulting_driver(driver):
            import driver_verification as drvver

            return drvver.crash_linked_catalog_device_names(
                drv_ver, resolved.get("culprit_device_names")
            )
        names: list[str] = []
        seen: set[str] = set()
        for info in resolved["culprit_driver_info"]:
            n = (info.get("name") or "").strip()
            if core._culprit_info_row_is_placeholder(info):
                continue
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(n)
        for key in sorted(resolved["culprit_device_names"]):
            if core.is_crash_synthetic_device_key(key):
                if not names and driver:
                    names.append(core.crash_synthetic_device_key(driver))
                continue
            if key in seen:
                continue
            for dev in self._drv_unified_cache:
                n = (dev.get("name") or "").strip()
                if n and n.lower() == key:
                    seen.add(key)
                    names.append(n)
                    break
            else:
                seen.add(key)
                names.append(key)
        if not names and driver:
            names.append(core.crash_synthetic_device_key(driver))
        return names

    def _schedule_crash_report_update_checks(self, m: dict) -> None:
        """After crash analysis: mark Drivers tab stale; manual scan only (no auto catalog)."""
        if self._shutting_down:
            return
        prof = self._hardware_profile or self._profile_from_model(m)
        if prof:
            self._drv_tab_ui_stale = True
            drv_ver = m.get("driver_verification") or {}
            platform_focus = bool((drv_ver.get("attribution") or {}).get("platform_chipset_focus"))
            if self._has_crash_faulting_driver() or platform_focus:
                idx = self.drv_view_filter.findData("log_attention")
                if idx >= 0:
                    self.drv_view_filter.blockSignals(True)
                    self.drv_view_filter.setCurrentIndex(idx)
                    self.drv_view_filter.blockSignals(False)
            else:
                self._apply_driver_only_view_defaults()
            self._update_drivers_tab_status_only(prof)
            if self._drivers_tab_is_active():
                self._populate_drivers_tab()
                self._drv_tab_ui_stale = False
        driver = (m.get("driver") or "").strip()
        drv_ver = m.get("driver_verification") or {}
        gated = int(drv_ver.get("catalog_gated_count") or 0)
        if core.has_crash_faulting_driver(driver):
            self._update_drv_workflow_banner("")
            ver_note = ""
            if drv_ver.get("has_suspects"):
                ver_note = f" Driver verification: {len(drv_ver.get('suspects') or [])} suspect(s)"
                if gated:
                    ver_note += f", {gated} ready for catalog Check."
                ver_note += " See crash report section 3b."
            if self._all_devices_loaded:
                self.statusBar().showMessage(
                    f"Analysis complete. Drivers tab lists your devices — "
                    f"check Include, then ② Search for updates. "
                    f"Needs attention shows crash-flagged rows ({driver}).{ver_note}",
                    15000,
                )
            else:
                self.statusBar().showMessage(
                    f"Analysis complete. Drivers tab: run ① Load devices, then "
                    f"② Search for updates. Needs attention shows crash-flagged rows ({driver}).{ver_note}",
                    15000,
                )
        elif self._firmware_bios_crash_priority() or self._firmware_ssd_crash_priority():
            self.statusBar().showMessage(
                "Analysis complete. Open the Firmware tab and click "
                "Search for firmware updates when ready.",
                15000,
            )
            self._update_fw_workflow_banner("")

    def _maybe_start_auto_crash_linked_catalog(self, m: dict | None = None) -> None:
        """Gap-closing Phase 6: small catalog scan for crash-linked rows after analysis."""
        if self._shutting_down:
            return
        if not self._settings.get("auto_crash_linked_catalog", True):
            return
        if self._drv_catalog_thread_busy() or self._driver_search_workflow_busy():
            return
        model = m or self._last_model or {}
        if not model.get("events") and not model.get("driver_verification"):
            return
        import driver_verification as drvver

        bio = (self._hardware_profile or {}).get("bios_driver_info") or model.get("bios_driver_info") or {}
        ctx = (self._hardware_profile or {}).get("system_ctx") or model.get("system_ctx") or {}
        resolved = core.resolve_crash_culprit_context(
            model.get("driver"),
            bio,
            code_val=model.get("code_val"),
            system_ctx=ctx,
            cause_type=model.get("cause_type"),
            fix_plan=model.get("fix_plan"),
            has_crash_context=bool(model.get("events")),
        )
        names = drvver.crash_linked_catalog_device_names(
            model.get("driver_verification"),
            resolved.get("culprit_device_names"),
        )
        if not names:
            return
        if not self._prompt_powershell7_before_online_scan():
            return
        if not self._drv_device_list_ready_for_search():
            self._pending_auto_crash_linked_catalog = names
            return
        self._pending_auto_crash_linked_catalog = None
        self.statusBar().showMessage(
            f"Checking {len(names)} crash-linked driver(s) in the background…",
            12000,
        )
        self._start_drivers_tab_catalog_check(
            names,
            auto_culprit=True,
            catalog_source=model,
        )

    def _flush_pending_auto_crash_linked_catalog(self) -> None:
        pending = getattr(self, "_pending_auto_crash_linked_catalog", None)
        if not pending or self._shutting_down:
            return
        self._pending_auto_crash_linked_catalog = None
        m = self._last_model or {}
        self._maybe_start_auto_crash_linked_catalog(m)

    def _refresh_model_culprit_driver_info(self) -> None:
        """Re-match faulting module to PnP rows after full hardware inventory loads."""
        m = self._last_model
        if not m:
            return
        prof = self._hardware_profile
        bio = (prof or {}).get("bios_driver_info") or m.get("bios_driver_info") or {}
        system_ctx = dict(m.get("system_ctx") or {})
        if prof:
            system_ctx = system_ctx or dict(prof.get("system_ctx") or {})
        changed = core.refresh_model_culprit_fields(m, bio, system_ctx=system_ctx)
        if changed and hasattr(self, "driver_update_frame"):
            self._populate_driver_update_options(m)

    def _update_fw_workflow_banner(self, phase: str, *, updates: int = 0) -> None:
        self._fw_workflow_phase = (phase or "").strip()
        self._fw_workflow_meta = {"updates": updates}
        self._update_fw_tab_summary_line()

    def _update_crash_timeline_ui(self, m: dict) -> None:
        import gui_html_safe as html_safe
        import gui_theme as theme

        view = getattr(self, "crash_timeline_view", None) or getattr(
            self, "crash_timeline_label", None
        )
        if view is None:
            return
        if not self._settings.get("show_crash_timeline", True):
            html_safe.safe_set_html(
                view,
                f"<p style='color:{theme.MUTED}; margin:0'>"
                "Incident timeline is off — enable it in Settings → Preferences.</p>",
            )
            return
        itl = m.get("incident_timeline") or {}
        entries = itl.get("entries") or []
        if not entries:
            tl = m.get("crash_timeline") or {}
            if not tl.get("count_30d") and not m.get("crash_count"):
                html_safe.safe_set_html(
                    view,
                    f"<p style='color:{theme.MUTED}; margin:0'>"
                    "No crash events in the recent log window.</p>",
                )
                return
            parts = [
                f"{tl.get('count_7d', 0)} BSOD(s) in the last 7 days",
                f"{tl.get('count_30d', 0)} in the last 30 days",
            ]
            if tl.get("last_crash"):
                parts.append(f"Most recent: {tl['last_crash']}")
            hint = tl.get("last_clean_hint") or ""
            if hint:
                parts.append(hint)
            html_safe.safe_set_html(
                view,
                "".join(
                    f"<p style='color:{theme.MUTED}; margin:0 0 4px 0'>{self._esc(p)}</p>"
                    for p in parts
                ),
            )
            return

        kind_colors = {
            "bugcheck": theme.SEVERITY_COLORS.get(3, theme.ACCENT),
            "shutdown": "#e8a030",
            "boot_recovery": "#c9a227",
            "minidump": theme.MUTED,
            "event": theme.MUTED,
        }
        rows: list[str] = []
        for ent in entries[:10]:
            kind = ent.get("kind") or "event"
            color = kind_colors.get(kind, theme.MUTED)
            badge = {
                "bugcheck": "BSOD",
                "shutdown": "Shutdown",
                "boot_recovery": "Boot/recovery",
                "minidump": "Minidump",
                "event": "Event",
            }.get(kind, kind)
            time_s = self._esc(ent.get("time") or "?")
            label = self._esc(ent.get("label") or "")
            detail = self._esc(ent.get("detail") or "")
            flags: list[str] = []
            if ent.get("verified_stop") is True:
                flags.append("verified stop")
            elif ent.get("verified_stop") is False:
                flags.append("unverified stop")
            if ent.get("dump_match") is True:
                flags.append("dump matches")
            elif ent.get("dump_match") is False:
                flags.append("dump mismatch")
            if ent.get("historical"):
                flags.append("historical")
            flag_bit = (
                f" <span style='color:{theme.MUTED}; font-size:11px'>"
                f"({' · '.join(flags)})</span>"
                if flags
                else ""
            )
            detail_html = (
                f"<br><span style='color:{theme.MUTED}; font-size:12px'>{detail}</span>"
                if detail
                else ""
            )
            rows.append(
                f"<div style='margin:0 0 10px 0; line-height:140%'>"
                f"<span style='color:{color}; font-weight:600'>{badge}</span> "
                f"<span style='color:{theme.MUTED}'>{time_s}</span><br>"
                f"<span>{label}</span>{flag_bit}{detail_html}</div>"
            )
        summary = itl.get("summary_lines") or []
        foot = ""
        if summary:
            foot = (
                f"<p style='color:{theme.MUTED}; margin:8px 0 0 0; font-size:12px'>"
                f"{self._esc(summary[-1])}</p>"
            )
        html_safe.safe_set_html(
            view,
            f"<div style='line-height:140%'>{''.join(rows)}{foot}</div>",
        )

    def _update_reliability_ui(self, m: dict) -> None:
        if not self._settings.get("show_reliability_events", True):
            self.reliability_label.setText(
                "Reliability / Live Kernel is off — enable in Settings → Preferences."
            )
            return
        rel = m.get("reliability_ctx") or {}
        stab = rel.get("stability_index")
        lk = rel.get("livekernel") or []
        wer = rel.get("wer_errors") or []
        crash_times = [m.get("last_crash")] if m.get("last_crash") else []
        for inc in m.get("incidents") or []:
            if inc.get("time"):
                crash_times.append(inc["time"])
        near = sum(
            1 for e in lk
            if core._match_event_to_crash(e.get("time", ""), crash_times, 15)
        )
        parts = []
        if stab is not None:
            parts.append(f"Stability index: {stab} (10 = most stable)")
        if lk:
            line = f"{len(lk)} Live Kernel event(s) in recent logs"
            if near:
                line += f" — {near} near last crash"
            parts.append(line)
        elif not stab:
            parts.append("No Live Kernel events in recent logs")
        if wer:
            parts.append(f"{len(wer)} WER system error(s) logged")
        if not parts:
            parts.append("No reliability data returned (try Run as Administrator)")
        parts.append("Open Reliability Monitor: Win+R → perfmon /rel")
        self.reliability_label.setText("\n".join(parts))

    def _reliability_details_html(self, m: dict) -> str:
        if not self._settings.get("show_reliability_events", True):
            return ""
        rel = m.get("reliability_ctx") or {}
        lk = rel.get("livekernel") or []
        wer = rel.get("wer_errors") or []
        stab = rel.get("stability_index")
        if stab is None and not lk and not wer:
            return ""
        import gui_theme as theme

        parts = ["<div style='line-height:150%; margin-top:16px'>"]
        parts.append("<h3>Reliability &amp; Live Kernel</h3>")
        if stab is not None:
            parts.append(
                f"<p style='color:{theme.MUTED}; margin-top:0'>"
                f"System Stability Index: <b>{self._esc(str(stab))}</b> (10 = most stable)</p>"
            )
        if lk:
            parts.append(f"<p style='color:{theme.MUTED}; margin-top:0'>Live Kernel events:</p>")
            for e in lk[:10]:
                parts.append(
                    f"<div>• <span style='color:{theme.MUTED}'>{self._esc(e.get('time', '?'))}</span> "
                    f"ID {self._esc(str(e.get('id', '?')))} — "
                    f"{self._esc(e.get('summary') or e.get('message', '')[:100])}</div>"
                )
        if wer:
            parts.append(f"<p style='color:{theme.MUTED}'>Windows Error Reporting (system):</p>")
            for e in wer[:6]:
                parts.append(
                    f"<div>• <span style='color:{theme.MUTED}'>{self._esc(e.get('time', '?'))}</span> "
                    f"{self._esc((e.get('message') or '')[:100])}</div>"
                )
        parts.append("</div>")
        return "".join(parts)

