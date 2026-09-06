"""Firmware catalog workers, user-installed MCU version, download."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiFirmwareScanMixin:
    def _on_fw_set_user_installed(self) -> None:
        """Phase B — save user-confirmed MCU firmware for a USB peripheral."""
        row = self.fw_unified_table.currentRow()
        if row < 0:
            return
        key = self._fw_key_from_row(row)
        cache_row = self._fw_cache_row_for_key(key) or {}
        device_id = (cache_row.get("device_id") or "").strip()
        if not device_id or not key.startswith("peripheral:"):
            return
        try:
            import firmware_peripheral_installed as fpinst
        except ImportError:
            return
        current = (cache_row.get("installed") or "").strip()
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Set installed firmware",
            f"Enter the firmware version confirmed in the vendor tool for:\n"
            f"{cache_row.get('component') or key}\n\n"
            f"(Current display: {current})",
            text=current if current not in ("—", "?", "Loading…") else "",
        )
        if not ok or not (text or "").strip():
            return
        ver = text.strip()
        if fpinst.save_user_confirmed(device_id, ver):
            cache_row["installed"] = ver
            cache_row["installed_source"] = "user_confirmed"
            prof = self._hardware_profile
            if prof:
                for dev in prof.get("secondary_firmware") or []:
                    if (dev.get("key") or "") == key:
                        dev["installed"] = ver
                        dev["installed_source"] = "user_confirmed"
            self._refresh_unified_firmware_table(prof or {})
            self.statusBar().showMessage(
                f"Saved installed firmware {ver} for {cache_row.get('component') or key}.",
                8000,
            )
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "Firmware",
                "Could not save the confirmed firmware version.",
            )

    def _on_check_firmware_catalog(self) -> None:
        if self._shutting_down:
            return
        if self._fw_thread and self._fw_thread.isRunning():
            self.statusBar().showMessage(
                "Firmware update search already in progress…", 5000
            )
            return
        if self._block_if_other_catalog_busy("firmware"):
            return
        prof = self._hardware_profile_data()
        if not prof:
            QtWidgets.QMessageBox.information(
                self,
                "Firmware check",
                "Hardware scan is still running. Try again shortly.",
            )
            return
        target_keys = self._fw_checked_target_keys()
        if not target_keys:
            QtWidgets.QMessageBox.information(
                self,
                "Firmware check",
                "Check Include on one or more components (use the Include column header, then uncheck any to skip).",
            )
            return
        if not self._ssd_firmware_loaded:
            import gui_theme as theme

            self.statusBar().showMessage(
                f"Complete {theme.BTN_FW_LOAD} before searching for updates.",
                6000,
            )
            QtWidgets.QMessageBox.information(
                self,
                "Load component list first",
                f"Run {theme.BTN_FW_LOAD} on the Firmware tab and wait for it to finish, "
                f"then use {theme.BTN_FW_SEARCH}.",
            )
            return
        if not self._prompt_powershell7_before_online_scan():
            return
        self._start_firmware_catalog_check(target_keys)

    def _start_firmware_catalog_check(
        self, target_keys: list[str], *, pipeline: bool = False
    ) -> None:
        if self._shutting_down:
            return
        prof = self._hardware_profile_data()
        if not prof:
            return
        bios = (prof.get("bios_driver_info") or {}).get("bios") or {}
        system_ctx = dict(prof.get("system_ctx") or {})
        pnp_list = prof.get("pnp_list") or []
        self.fw_btn_check.setEnabled(False)
        for key in target_keys:
            row = self._fw_row_for_key(key)
            if row >= 0:
                self._set_fw_row_status(row, "checking")
        self._fw_check_keys = set(target_keys)
        self._fw_pipeline_step = pipeline
        self._fw_catalog_job_generation = self._fw_catalog_generation
        self._fw_scan_determinate = False
        self._fw_scan_progress_total = len(target_keys)
        start_label = f"Checking {len(target_keys)} firmware target(s)…"
        self._begin_task_progress(start_label, maximum=0)
        self._catalog_status_line(start_label)
        if hasattr(self, "fw_scan_status"):
            self.fw_scan_status.setText(start_label)
        scan_sm = drvcat.catalog_scan_mode_summary(
            full_install=app_set.is_full_install_mode(self._settings),
            quick_check=bool(self._settings.get("quick_check_mode")),
            gui_mode=True,
        )
        self._set_catalog_hint(
            self.fw_hint,
            f"Checking {len(target_keys)} component(s) — {scan_sm.get('mode', 'scan')}. "
            f"{scan_sm.get('active_sources', '')}",
            tooltip=scan_sm.get("detail") or "",
        )
        self._fw_thread = QtCore.QThread()
        self._fw_worker = FirmwareCatalogWorker(
            bios,
            system_ctx,
            pnp_list,
            prof.get("ssd_firmware") or [],
            target_keys=target_keys,
            secondary_firmware=(
                list(prof.get("secondary_firmware") or [])
                if self._ssd_firmware_loaded
                else None
            ),
        )
        self._fw_worker.moveToThread(self._fw_thread)
        self._fw_thread.started.connect(self._fw_worker.run)
        self._fw_worker.progress.connect(self._signal_relay.fw_catalog_progress)
        self._fw_worker.finished.connect(self._signal_relay.firmware_catalog_ready)
        self._fw_worker.failed.connect(self._signal_relay.firmware_catalog_failed)
        self._fw_worker.finished.connect(self._fw_thread.quit)
        self._fw_worker.failed.connect(self._fw_thread.quit)
        self._fw_thread.finished.connect(self._cleanup_firmware_catalog_thread)
        self._session_log_begin(
            "firmware_catalog",
            f"Firmware catalog search ({len(target_keys)} target(s))",
            "_session_log_firmware_token",
        )
        self._fw_thread.start()

    @QtCore.Slot(str)
    def _on_fw_catalog_progress(self, msg: str) -> None:
        import re

        if self._shutting_down or self._fw_catalog_job_stale():
            return
        label = (msg or "").strip() or "Searching firmware catalog…"
        self._session_log_progress("firmware_catalog", label)
        self._catalog_status_line(label)
        if hasattr(self, "fw_scan_status"):
            self.fw_scan_status.setText(label)
        # Do not call processEvents here — same re-entrant stack overflow as driver catalog.
        if msg.startswith("Checked ") and hasattr(self, "fw_hint"):
            self._set_catalog_hint(self.fw_hint, label)
        m = re.search(r"Checked (\d+)/(\d+)", msg)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            self._fw_scan_progress_total = tot
            self._fw_scan_determinate = True
            self._set_task_progress(cur, label, maximum=max(tot, 1))
            return
        batch = re.search(r"Checking (\d+) firmware component\(s\)", msg)
        if batch:
            tot = int(batch.group(1))
            self._fw_scan_progress_total = tot
            self._fw_scan_determinate = True
            if getattr(self, "_task_progress_depth", 0) <= 0:
                self._begin_task_progress(label, maximum=max(tot, 1), value=0)
            else:
                self._set_task_progress(0, label, maximum=max(tot, 1))
            return
        # Warm/prep phases before per-component counting — indeterminate marquee.
        if not getattr(self, "_fw_scan_determinate", False):
            if getattr(self, "_task_progress_depth", 0) <= 0:
                self._begin_task_progress(label, maximum=0)
            else:
                self._set_task_progress(label=label, maximum=0)
            return
        # Determinate phase substeps — update label, keep accumulated fill.
        if getattr(self, "_task_progress_depth", 0) > 0:
            bar = getattr(self, "_task_progress", None)
            if bar is not None and bar.maximum() > 0:
                self._set_task_progress(label=label)

    def _cleanup_firmware_catalog_thread(self) -> None:
        self._fw_thread = None
        self._fw_worker = None
        self._sync_fw_workflow_buttons()

    def _persist_firmware_check_results(
        self, checked: set[str], fetched: str
    ) -> None:
        if not self._settings.get("remember_driver_firmware_checks"):
            return
        batch: list[dict] = []
        for key in checked:
            target_offers = self._fw_offers_for_target(key)
            ent = self._fw_cache_row_for_key(key)
            batch.append(
                {
                    "target_key": key,
                    "status": self._firmware_status_from_offers(target_offers),
                    "installed_version": (ent.get("installed") or "?") if ent else "?",
                    "offers": target_offers,
                    "target_label": (ent.get("component") or key) if ent else key,
                }
            )
        if batch:
            drvidx.record_firmware_checks_batch(batch, fetched_at=fetched)
        idx_err = drvidx.peek_index_error()
        if idx_err:
            self.statusBar().showMessage(
                f"Could not save firmware check results: {idx_err[:60]}", 8000
            )

    def _fw_catalog_job_stale(self) -> bool:
        return (
            self._shutting_down
            or self._fw_catalog_job_generation != self._fw_catalog_generation
        )

    def _on_firmware_catalog_ready(self, comparison: dict) -> None:
        if self._fw_catalog_job_stale():
            self._session_log_end(
                "firmware_catalog",
                "Firmware catalog search cancelled (superseded)",
                "_session_log_firmware_token",
                status="cancelled",
            )
            self._end_task_progress()
            return
        try:
            self._on_firmware_catalog_ready_impl(comparison)
        except Exception as e:  # noqa: BLE001
            import traceback

            self._end_task_progress()
            detail = traceback.format_exc()
            if not self._shutting_down:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Firmware check — display error",
                    f"{e}\n\n{traceback.format_exc()[-1200:]}",
                )
                self.statusBar().showMessage(
                    f"Firmware check finished but display failed: {str(e)[:80]}", 8000
                )

    def _on_firmware_catalog_ready_impl(self, comparison: dict) -> None:
        self._end_task_progress()
        checked = getattr(self, "_fw_check_keys", set())
        pipeline_step = getattr(self, "_fw_pipeline_step", False)
        self._fw_pipeline_step = False
        fetched = comparison.get("fetched_at") or ""
        offers = comparison.get("offers") or []
        if offers:
            batch_updates = sum(
                1 for o in offers if (o.get("vs_installed") or "") == "newer"
            )
            summary = (
                f"Checked {len(checked)} component(s); {batch_updates} update(s) available"
                if checked
                else f"Firmware catalog search complete — {len(offers)} offer(s)"
            )
        else:
            summary = (
                f"Checked {len(checked)} component(s); no offers"
                if checked
                else "Firmware catalog search complete"
            )
        elapsed_ms = self._session_log_end(
            "firmware_catalog",
            summary,
            "_session_log_firmware_token",
            extra={"fetched_at": fetched} if fetched else None,
        )
        if elapsed_ms is not None:
            comparison = dict(comparison)
            comparison["elapsed_ms"] = elapsed_ms
        self._firmware_comparison = self._merge_firmware_comparison(comparison)
        self._update_fw_targets_from_comparison(
            self._firmware_comparison,
            only_keys=checked if checked else None,
        )
        self._apply_fw_filter()
        offers = self._firmware_comparison.get("offers") or []
        if pipeline_step:
            batch_updates = sum(
                1
                for d in self._fw_unified_cache
                if d.get("_scan_verified") and d.get("_check_status") == "newer"
            )
            self._update_fw_workflow_banner("done", updates=batch_updates)
            if batch_updates:
                idx = self.fw_view_filter.findData("updates")
                if idx >= 0:
                    self.fw_view_filter.setCurrentIndex(idx)
            elif self._firmware_bios_crash_priority() or self._firmware_ssd_crash_priority():
                idx = self.fw_view_filter.findData("log_attention")
                if idx >= 0:
                    self.fw_view_filter.setCurrentIndex(idx)
            msg = f"Firmware check complete — {batch_updates} update(s) found."
            self._persist_firmware_check_results(checked, fetched)
            self.statusBar().showMessage(msg)
            self._fw_check_keys = set()
            QtCore.QTimer.singleShot(
                0, lambda: self._maybe_warn_vendor_health_after_scan(firmware_scan=True)
            )
            return
        self._persist_firmware_check_results(checked, fetched)
        self._on_fw_unified_selection()
        inst = self._firmware_comparison.get("installed") or {}
        batch_updates = sum(
            1 for d in self._fw_unified_cache if d.get("_check_status") == "newer"
        )
        brief = (
            f"Compared at {fetched}. Checked {len(checked)} component(s); "
            f"{batch_updates} may have an update. "
            f"Installed BIOS: {inst.get('version', '?')}."
        )
        detail = brief
        if comparison.get("scan_mode"):
            detail += f"\n\nScan mode: {comparison.get('scan_mode')}"
        mode_detail = (comparison.get("scan_mode_detail") or "").strip()
        if mode_detail:
            detail += f"\n\n{mode_detail}"
        self._set_catalog_hint(self.fw_hint, brief, tooltip=detail)
        self.fw_btn_download.setEnabled(False)
        self.statusBar().showMessage(f"Found {len(offers)} firmware-related offer(s).")
        self._fw_check_keys = set()
        QtCore.QTimer.singleShot(
            0, lambda: self._maybe_warn_vendor_health_after_scan(firmware_scan=True)
        )

    def _on_firmware_catalog_failed(self, err: str) -> None:
        if self._fw_catalog_job_stale():
            self._session_log_end(
                "firmware_catalog",
                "Firmware catalog search cancelled (superseded)",
                "_session_log_firmware_token",
                status="cancelled",
            )
            self._end_task_progress()
            return
        self._session_log_end(
            "firmware_catalog",
            f"Firmware catalog search failed: {err[:200]}",
            "_session_log_firmware_token",
            status="error",
        )
        self._end_task_progress()
        QtWidgets.QMessageBox.warning(self, "Firmware check", err)
        self.statusBar().showMessage("Firmware check failed.")

    def _on_download_selected_firmware(self) -> None:
        row = self.fw_compare_table.currentRow()
        if row < 0:
            return
        offer, _item = self._offer_from_compare_row(self.fw_compare_table, row)
        if not offer:
            return
        if offer.get("kind") == "bios":
            extra = (
                "\n\nOnly install BIOS using the manufacturer's instructions. "
                "Use AC power; do not power off during the update."
            )
        else:
            extra = ""
        src = offer.get("source_label") or "firmware"
        ver = offer.get("version") or "—"
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Open firmware download",
            f"Open the page for {src}?\n\n"
            f"Package: {offer.get('title', '')}\n"
            f"Version: {ver}\n"
            f"vs installed: {offer.get('vs_installed', 'unknown')}\n\n"
            f"{offer.get('notes', '')}{extra}\n\n"
            "BSOD Analyzer will not install or flash firmware. Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self.fw_btn_download.setEnabled(False)
        # Third value is the saved package path; msg already names it when present.
        ok, msg, _saved_path = fwcat.open_firmware_offer(offer)
        self.fw_btn_download.setEnabled(True)
        if ok:
            QtWidgets.QMessageBox.information(self, "Firmware", msg)
        else:
            QtWidgets.QMessageBox.warning(self, "Firmware", msg)
        self.statusBar().showMessage(msg[:120])
