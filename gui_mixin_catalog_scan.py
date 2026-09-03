"""Driver catalog scan workers, batch merge, and progress handlers."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogScanMixin:
    def _fw_catalog_thread_busy(self) -> bool:
        return bool(getattr(self, "_fw_thread", None) and self._fw_thread.isRunning())

    def _catalog_search_busy(self) -> bool:
        """True while any catalog search or DB refresh worker is active."""
        return (
            self._drv_catalog_thread_busy()
            or self._fw_catalog_thread_busy()
            or self._catalog_db_refresh_busy()
        )

    def _other_catalog_search_busy(self, kind: str) -> bool:
        if kind == "driver":
            return self._fw_catalog_thread_busy()
        return self._drv_catalog_thread_busy()

    def _catalog_db_refresh_busy(self) -> bool:
        return bool(
            getattr(self, "_catalog_refresh_job", None)
            and self._catalog_refresh_job.is_running()
        )

    def _block_if_other_catalog_busy(self, kind: str) -> bool:
        if self._catalog_db_refresh_busy():
            self.statusBar().showMessage(
                "Driver database refresh is running — wait for it to finish before searching.",
                8000,
            )
            return True
        if not self._other_catalog_search_busy(kind):
            return False
        if kind == "driver":
            self.statusBar().showMessage(
                "Firmware update search is still running — wait for it to finish.",
                6000,
            )
        else:
            self.statusBar().showMessage(
                "Driver update search is still running — wait for it to finish.",
                6000,
            )
        return True

    def _drv_catalog_thread_busy(self) -> bool:
        """True while a driver catalog worker is starting or running."""
        if getattr(self, "_drv_thread_starting", False):
            return True
        return bool(self._drv_thread and self._drv_thread.isRunning())

    def _catalog_scannable_device_names(self, names: list[str]) -> list[str]:
        """Names that actually enter the catalog worker (firmware rows are skipped)."""
        import driver_catalog as dc

        prof = self._hardware_profile_data() or {}
        pnp_list = prof.get("pnp_list") or []
        inventory = prof.get("bios_driver_info") or {}
        system_ctx = dc.extend_system_ctx_for_catalog(
            dict(prof.get("system_ctx") or {})
        )
        out: list[str] = []
        seen: set[str] = set()
        for raw in names:
            name = (raw or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ctx = dc.get_device_context_for_name(
                name, pnp_list, inventory, system_ctx
            )
            if dc.is_driver_scan_excluded_ctx(ctx):
                continue
            out.append(name)
        return out

    def _clear_drv_thread_starting(self) -> None:
        self._drv_thread_starting = False

    def _launch_drv_catalog_worker(self, worker: DriverCatalogWorker) -> bool:
        """Wire and start a driver catalog worker; False if one is already active."""
        if self._catalog_db_refresh_busy():
            self.statusBar().showMessage(
                "Driver database refresh is running — wait for it to finish before searching.",
                8000,
            )
            return False
        if self._drv_catalog_thread_busy():
            return False
        self._drv_thread_starting = True
        self._drv_thread = QtCore.QThread()
        self._drv_worker = worker
        self._drv_worker.moveToThread(self._drv_thread)
        self._drv_thread.started.connect(self._drv_worker.run)
        self._drv_worker.progress.connect(self._signal_relay.drv_catalog_progress)
        self._drv_worker.finished.connect(self._signal_relay.driver_catalog_ready)
        self._drv_worker.failed.connect(self._signal_relay.driver_catalog_failed)
        self._drv_worker.finished.connect(self._drv_thread.quit)
        self._drv_worker.failed.connect(self._drv_thread.quit)
        self._drv_thread.started.connect(self._clear_drv_thread_starting)
        self._drv_thread.finished.connect(self._cleanup_driver_catalog_thread)
        self._session_log_begin(
            "driver_catalog",
            "Driver update catalog search",
            "_session_log_catalog_token",
        )
        self._drv_thread.start()
        return True

    def _focus_drivers_tab_for_device(self, device_name: str) -> None:
        if hasattr(self, "_drivers_tab_widget"):
            idx = self.tabs.indexOf(self._drivers_tab_widget)
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)
        name = (device_name or "").strip()
        if not name:
            return
        for table in self._drv_tables():
            for row in range(table.rowCount()):
                item = table.item(row, DRV_COL_DEVICE)
                if not item:
                    continue
                key = str(item.data(QtCore.Qt.UserRole) or item.text())
                if key == name or item.text() == name:
                    for other in self._drv_tables():
                        other.clearSelection()
                    table.selectRow(row)
                    self._on_drv_device_row_selected(table)
                    return

    def _batch_entry_for_device_name(self, name: str) -> dict | None:
        key = (name or "").strip().lower()
        if not key:
            return None
        batch = self._driver_batch_comparison or {}
        for entry in batch.get("devices") or []:
            dn = (entry.get("device_name") or "").strip().lower()
            if dn == key:
                return entry
        return None

    def _catalog_entry_from_verified_device(self, dev: dict, name: str) -> dict | None:
        """Fallback Packages payload when batch dict lost but row shows a verified scan."""
        if not dev.get("_scan_verified"):
            return None
        batch_entry = self._batch_entry_for_device_name(name)
        if (
            batch_entry
            and not (batch_entry.get("offers") or [])
            and dev.get("_index_package_offers")
        ):
            batch_entry = dict(batch_entry)
            batch_entry["offers"] = list(dev["_index_package_offers"])
        if drvidx.is_index_enabled(self._settings):
            merged = drvidx.entry_with_index_packages(batch_entry, name)
            if merged:
                merged = dict(merged)
                merged.pop("_from_index", None)
                return merged
        if batch_entry:
            return batch_entry
        status = (dev.get("_check_status") or "none").strip() or "none"
        if status == "pending":
            return None
        offers = list(dev.get("_index_package_offers") or [])
        return {
            "device_name": name,
            "installed_version": (
                dev.get("_installed_at_scan") or dev.get("version") or "?"
            ),
            "offers": offers,
            "status": status,
            "_from_session_row": True,
        }

    def _drv_result_for_name(self, name: str) -> dict | None:
        entry = self._batch_entry_for_device_name(name)
        dev = next(
            (d for d in self._drv_unified_cache if (d.get("name") or "") == name),
            None,
        )
        if dev:
            verified = self._catalog_entry_from_verified_device(dev, name)
            if verified:
                return verified
        if drvidx.is_index_enabled(self._settings):
            merged = drvidx.entry_with_index_packages(entry, name)
            if merged:
                merged = dict(merged)
                merged.pop("_from_index", None)
                return merged
        return entry

    def _on_drv_device_row_selected(
        self, table: QtWidgets.QTableWidget | None = None,
    ) -> None:
        table = table or self._drv_primary_table()
        if not table:
            return
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if self._drv_is_section_row(table, row):
            return
        selected = self._drv_selected_device_names()
        item = table.item(row, DRV_COL_DEVICE)
        if not item:
            return
        name = str(item.data(QtCore.Qt.UserRole) or item.text())
        label = item.text() or name
        dev = self._device_dict_by_name(name)
        result = self._drv_result_for_name(name)
        self._update_drv_inspector_header(dev, result)
        if result:
            self._driver_comparison = result
            offers = result.get("offers") or []
            self._fill_driver_compare_table(self.drv_compare_table, offers)
            status = result.get("status") or "none"
            if offers or status not in ("none", "pending"):
                self._set_drv_packages_section_visible(True)
                if hasattr(self, "drv_packages_heading"):
                    self.drv_packages_heading.setText("Available packages")
            if status in ("unknown", "uncertain"):
                summary = drvcat.build_uncertain_inspector_summary(
                    offers,
                    (result.get("installed_version") or dev.get("version") or "?"),
                    status=status,
                )
                brief = self._brief_package_compare_hint(status, offers)
                self._set_catalog_hint(
                    self.drv_hint,
                    brief,
                    tooltip=summary or drvcat.catalog_scan_mode_summary(gui_mode=True).get("detail") or "",
                )
            else:
                brief = self._brief_package_compare_hint(status, offers)
                if brief:
                    self._set_catalog_hint(self.drv_hint, brief)
                else:
                    self._set_catalog_hint(self.drv_hint, "")
        else:
            self._driver_comparison = None
            self._fill_driver_compare_table(self.drv_compare_table, [])
            self._set_drv_packages_section_visible(False)
            self._set_catalog_hint(self.drv_hint, "")
        self._on_drv_compare_selection_changed()

    def _driver_scan_progress_label(self, msg: str) -> str:
        return msg[:120]

    def _on_driver_row_selected(self) -> None:
        pass

    def _merge_crash_module_into_batch(
        self, comparison: dict, device_key: str
    ) -> None:
        offers = comparison.get("offers") or []
        entry = {
            "device_name": device_key,
            "installed_version": comparison.get("installed_version") or "?",
            "offers": offers,
            "status": drvcat.summarize_offer_status(offers),
        }
        comp = {
            "devices": [entry],
            "fetched_at": comparison.get("fetched_at") or "",
        }
        self._driver_batch_comparison = self._merge_driver_batch_comparison(comp)
        self._apply_driver_batch_results(comp, only_names={device_key})
        for dev in self._drv_unified_cache:
            if (dev.get("name") or "").strip() == device_key:
                self._sync_device_from_catalog_entry(dev, entry)

    def _start_crash_module_catalog_check(
        self,
        synth_device_key: str,
        *,
        catalog_source: dict | None = None,
    ) -> None:
        """Catalog check keyed to faulting .sys when no PnP device row matched."""
        if self._drv_catalog_thread_busy():
            self._pending_crash_module_check = {
                "synth_device_key": synth_device_key,
                "catalog_source": catalog_source,
            }
            driver = (catalog_source or self._last_model or {}).get("driver") or "module"
            self.statusBar().showMessage(
                f"Crash module check for {driver} queued — waiting for current search…",
                8000,
            )
            return
        src = catalog_source or self._last_model or {}
        driver = src.get("driver")
        if not driver:
            return
        prof = self._hardware_profile_data()
        if catalog_source or not prof:
            pnp_list = ((src.get("system_ctx") or {}).get("pnp_list")) or []
            system_ctx = dict(src.get("system_ctx") or {})
            bios = src.get("bios_driver_info")
        else:
            pnp_list = prof.get("pnp_list") or []
            system_ctx = dict(prof.get("system_ctx") or {})
            bios = prof.get("bios_driver_info")
        self._compare_target = "drivers"
        self._drv_crash_synth_key = synth_device_key
        self._drv_check_names = {synth_device_key}
        tbl, row = self._drv_row_for_name(synth_device_key)
        if row >= 0:
            self._set_device_row_status(row, "checking", table=tbl)
        self.drv_btn_check.setEnabled(False)
        self._drv_scan_determinate = False
        self._begin_task_progress(
            f"Checking packages for crash module {driver}…",
            maximum=0,
        )
        self._drv_catalog_job_generation = self._drv_catalog_generation
        worker = DriverCatalogWorker(
            pnp_list,
            system_ctx,
            bios,
            driver=driver,
        )
        if not self._launch_drv_catalog_worker(worker):
            self._pending_crash_module_check = {
                "synth_device_key": synth_device_key,
                "catalog_source": catalog_source,
            }
            if row >= 0:
                self._set_device_row_status(row, "none", table=tbl)
            self.drv_btn_check.setEnabled(self._drv_search_button_enabled())
            self._end_task_progress()
            self.statusBar().showMessage(
                f"Crash module check for {driver} queued — driver search is starting…",
                8000,
            )
            return

    def _drv_manual_queue_summary(self) -> tuple[int, int]:
        jobs = self._drv_manual_queue or []
        devices = sum(len(j.get("device_names") or []) for j in jobs)
        return devices, len(jobs)

    def _refresh_drv_manual_queue_status(self) -> None:
        devices, jobs = self._drv_manual_queue_summary()
        if devices <= 0:
            return
        block = wf.drv_manual_queue_block_reason()
        text = wf.drv_manual_queue_status_text(
            queued_devices=devices,
            queued_jobs=jobs,
            block_reason=block,
            generic_driver_busy=self._drv_catalog_thread_busy(),
        )
        self.statusBar().showMessage(text, 10000)
        self._set_catalog_hint(self.drv_hint, text)

    def _enqueue_drivers_tab_catalog_check(
        self,
        device_names: list[str],
        *,
        auto_culprit: bool = False,
        catalog_source: dict | None = None,
    ) -> bool:
        """Queue a manual Search if a catalog check is already running."""
        names = [(n or "").strip() for n in device_names if (n or "").strip()]
        if not names:
            return False
        if not self._drv_catalog_thread_busy():
            return False
        self._drv_manual_queue.append(
            {
                "device_names": names,
                "auto_culprit": auto_culprit,
                "catalog_source": catalog_source,
            }
        )
        self._refresh_drv_manual_queue_status()
        return True

    def _flush_drv_manual_queue(self) -> None:
        if self._shutting_down or not self._drv_manual_queue:
            return
        if self._drv_catalog_thread_busy():
            return
        job = self._drv_manual_queue.pop(0)
        n = len(job.get("device_names") or [])
        if n:
            self.statusBar().showMessage(
                f"Starting your queued driver search ({n} device(s))…",
                6000,
            )
        QtCore.QTimer.singleShot(
            0,
            lambda j=job: self._start_drivers_tab_catalog_check(
                j["device_names"],
                auto_culprit=j.get("auto_culprit", False),
                catalog_source=j.get("catalog_source"),
            ),
        )

    def _start_drivers_tab_catalog_check(
        self,
        device_names: list[str],
        *,
        auto_culprit: bool = False,
        catalog_source: dict | None = None,
    ) -> None:
        names = [(n or "").strip() for n in device_names if (n or "").strip()]
        if not names:
            return
        if hasattr(self, "_maybe_warn_network_power_before_catalog_scan"):
            self._maybe_warn_network_power_before_catalog_scan()
        import driver_list_build as drvlist

        names = drvlist.expand_primary_catalog_device_names(
            names,
            getattr(self, "_drv_unified_cache", []),
        )
        if self._block_if_other_catalog_busy("driver"):
            self.drv_btn_check.setEnabled(True)
            if hasattr(self, "btn_search_driver_updates"):
                self.btn_search_driver_updates.setEnabled(True)
            return
        if not drvcat.catalog_powershell_available():
            self.statusBar().showMessage(
                "PowerShell is unavailable — some installed driver versions may be incomplete.",
                10000,
            )
        if self._enqueue_drivers_tab_catalog_check(
            names,
            auto_culprit=auto_culprit,
            catalog_source=catalog_source,
        ):
            return
        if catalog_source:
            pnp_list = ((catalog_source.get("system_ctx") or {}).get("pnp_list")) or []
            system_ctx = dict(catalog_source.get("system_ctx") or {})
            bios = catalog_source.get("bios_driver_info")
        else:
            prof = self._hardware_profile_data()
            if not prof:
                if not auto_culprit:
                    QtWidgets.QMessageBox.information(
                        self,
                        "Driver check",
                        "Hardware scan is still running. Try again in a moment.",
                    )
                return
            pnp_list = prof.get("pnp_list") or []
            system_ctx = dict(prof.get("system_ctx") or {})
            bios = prof.get("bios_driver_info")
        self._compare_target = "drivers"
        self._drv_auto_culprit_scan = auto_culprit
        self._drv_check_names = set(names)
        for name in names:
            tbl, row = self._drv_row_for_name(name)
            if row >= 0:
                self._set_device_row_status(row, "checking", table=tbl)
        self.drv_btn_check.setEnabled(False)
        scannable = self._catalog_scannable_device_names(names)
        count = len(scannable) if scannable else len(names)
        self._drv_scan_expected_total = count
        user_include_scan = catalog_source is None and not auto_culprit
        progress_msg = (
            f"Checking {count} crash-related driver(s)…"
            if auto_culprit
            else f"Checking {count} included device(s)…"
        )
        self._drv_scan_progress_total = count
        # Start indeterminate: the scan opens with WU/OEM/online-store/Update Catalog
        # preparation before per-device counting begins, so a determinate bar here
        # would sit at 0% (or fill and reset) and look stuck. The bar switches to a
        # determinate 0→100% span once per-device checks start ("Checking N device(s)").
        self._drv_scan_determinate = False
        if getattr(self, "_task_progress_depth", 0) > 0:
            self._set_task_progress(0, progress_msg, maximum=0)
        else:
            self._begin_task_progress(progress_msg, maximum=0)
        if (
            user_include_scan
            and count > _LARGE_DRIVER_SCAN_HINT_THRESHOLD
        ):
            mode = (
                self.drv_view_filter.currentData()
                if hasattr(self, "drv_view_filter")
                else ""
            )
            if mode == "all":
                self.statusBar().showMessage(
                    f"Checking {count} devices — many may show Unknown (version format mismatch). "
                    "Use Needs attention for crash drivers.",
                    12000,
                )
            status_msg = (
                f"Checking {count} included devices — this may take a while. "
                "Querying Microsoft, OEM, and vendor catalogs…"
            )
            if hasattr(self, "drv_hint"):
                self._set_catalog_hint(
                    self.drv_hint,
                    f"Scanning {count} devices with Include checked. "
                    "Large scans run in the background — watch the progress bar below.",
                )
        else:
            status_msg = (
                f"{progress_msg} Querying Microsoft, OEM, and vendor catalogs…"
            )
        scan_sm = drvcat.catalog_scan_mode_summary(
            full_install=app_set.is_full_install_mode(self._settings),
            quick_check=bool(self._settings.get("quick_check_mode")),
            gui_mode=True,
        )
        if hasattr(self, "drv_hint"):
            self._set_catalog_hint(
                self.drv_hint,
                f"Scanning {count} device(s) — {scan_sm.get('mode', 'scan')}. "
                f"{scan_sm.get('active_sources', '')}. "
                "Results appear below as each finishes.",
                tooltip=scan_sm.get("detail") or "",
            )
        self.statusBar().showMessage(status_msg)
        self._catalog_status_line(status_msg)
        self._update_drv_workflow_banner("scanning", total=count)
        self._drv_catalog_job_generation = self._drv_catalog_generation
        worker = DriverCatalogWorker(
            pnp_list,
            system_ctx,
            bios,
            device_names=names,
        )
        if not self._launch_drv_catalog_worker(worker):
            self._enqueue_drivers_tab_catalog_check(
                names,
                auto_culprit=auto_culprit,
                catalog_source=catalog_source,
            )

    def _on_check_driver_catalog(self, *, for_drivers_tab: bool = False) -> None:
        if self._shutting_down:
            return
        driver: str | None = None
        device_name: str | None = None
        pnp_list: list = []
        system_ctx: dict = {}
        bios: dict | None = None

        device_names: list[str] | None = None
        if for_drivers_tab:
            device_names = self._drv_checked_device_names()
            if not device_names:
                QtWidgets.QMessageBox.information(
                    self,
                    "Driver check",
                    "Check Include on one or more devices (use the Include column header, then uncheck any to skip).",
                )
                return
            self._start_drivers_tab_catalog_check(device_names)
            return
        else:
            if self._drv_catalog_thread_busy():
                self.statusBar().showMessage(
                    "Driver check already running — wait for it to finish.", 5000
                )
                return
            self._compare_target = "summary"
            m = self._last_model
            if not m or not m.get("driver"):
                return
            driver = m.get("driver")
            pnp_list = ((m.get("system_ctx") or {}).get("pnp_list")) or []
            system_ctx = dict(m.get("system_ctx") or {})
            bios = m.get("bios_driver_info")
            self.btn_check_drivers.setEnabled(False)

        self.statusBar().showMessage("Checking driver sources (Microsoft, OEM, vendor)…")
        self._drv_catalog_job_generation = self._drv_catalog_generation
        worker = DriverCatalogWorker(
            pnp_list,
            system_ctx,
            bios,
            driver=driver,
            device_names=device_names,
        )
        if not self._launch_drv_catalog_worker(worker):
            self.btn_check_drivers.setEnabled(True)
            self.statusBar().showMessage(
                "Driver check already running — wait for it to finish.", 5000
            )

    def _cleanup_driver_catalog_thread(self) -> None:
        self._drv_thread_starting = False
        self._drv_thread = None
        self._drv_worker = None
        self.btn_check_drivers.setEnabled(True)
        self.drv_btn_check.setEnabled(self._drv_search_button_enabled())
        if self._drv_workflow_phase in ("scanning", "finalizing"):
            verified = sum(
                1 for d in self._drv_unified_cache if d.get("_scan_verified")
            )
            expected = int(getattr(self, "_drv_scan_expected_total", 0) or 0)
            total = verified or expected
            if total:
                updates = sum(
                    1
                    for d in self._drv_unified_cache
                    if d.get("_scan_verified")
                    and d.get("_check_status") == "newer"
                )
                self._update_drv_workflow_banner(
                    "done",
                    checked=verified or total,
                    total=total,
                    updates=updates,
                )
        self._flush_drv_manual_queue()
        pending = getattr(self, "_pending_crash_module_check", None)
        if pending and not self._shutting_down:
            self._pending_crash_module_check = None
            QtCore.QTimer.singleShot(
                0,
                lambda p=pending: self._start_crash_module_catalog_check(
                    p["synth_device_key"],
                    catalog_source=p.get("catalog_source"),
                ),
            )

    def _merge_driver_batch_comparison(self, new_comp: dict) -> dict:
        old = self._driver_batch_comparison or {}
        by_name = {
            (e.get("device_name") or ""): e for e in (old.get("devices") or [])
        }
        for e in new_comp.get("devices") or []:
            by_name[e.get("device_name") or ""] = e
        devices = sorted(
            by_name.values(),
            key=lambda r: (
                drvcat._STATUS_RANK.get(r.get("status") or "none", 99),
                (r.get("device_name") or "").lower(),
            ),
        )
        return {
            "devices": devices,
            "fetched_at": new_comp.get("fetched_at") or old.get("fetched_at"),
            "elapsed_ms": new_comp.get("elapsed_ms") if new_comp.get("elapsed_ms") is not None else old.get("elapsed_ms"),
            "checked_count": len(devices),
            "update_count": sum(1 for d in devices if d.get("status") == "newer"),
        }

    def _apply_driver_batch_results(
        self, comparison: dict, only_names: set[str] | None = None
    ) -> None:
        by_name = {
            (e.get("device_name") or ""): e for e in (comparison.get("devices") or [])
        }
        cache_by_name = {
            (d.get("name") or "").strip(): d for d in self._drv_unified_cache
        }
        for table in self._drv_tables():
            for row in range(table.rowCount()):
                if self._drv_is_section_row(table, row):
                    continue
                item = table.item(row, DRV_COL_DEVICE)
                if not item:
                    continue
                name = str(item.data(QtCore.Qt.UserRole) or item.text())
                if only_names is not None and name not in only_names:
                    continue
                entry = by_name.get(name)
                dev = cache_by_name.get(name.strip())
                if entry:
                    meta = drvlist._scan_metadata_from_entry(entry)
                    hint = meta.get("_available_version") or ""
                    if not hint and meta.get("_installed_at_scan"):
                        hint = meta["_installed_at_scan"]
                    if dev:
                        self._sync_device_from_catalog_entry(dev, entry)
                        if dev.get("_check_status") == "newer":
                            dev["_tier"] = "outdated"
                    status = (
                        (dev or {}).get("_check_status") or meta["_check_status"]
                    )
                    tier = (dev or {}).get("_tier") or "normal"
                    self._set_catalog_row_status(
                        table,
                        row,
                        status,
                        tier=tier,
                        version_hint=hint,
                        none_reason=meta.get("_none_reason") or "",
                        dev=dev,
                    )
                    if dev:
                        label_item = table.item(row, DRV_COL_DEVICE)
                        if label_item:
                            self._apply_device_crash_info_tooltip(label_item, dev)
                        icon_item = table.item(row, DRV_COL_ICON)
                        if icon_item:
                            icon_item.setIcon(
                                vicons.icon_for_device(
                                    dev, size=UNIFIED_TABLE_ICON_SIZE
                                )
                            )
                elif only_names is not None and name in only_names:
                    self._set_device_row_status(row, "error", table=table)
        for dname, dev in cache_by_name.items():
            if only_names is not None and dname not in only_names:
                continue
            entry = by_name.get(dname)
            self._sync_device_from_catalog_entry(dev, entry)
        cur = self.drv_unified_table.currentRow()
        if cur >= 0:
            self._on_drv_device_row_selected(self.drv_unified_table)

    def _catalog_status_line(self, msg: str) -> None:
        from gui_catalog_parallel import catalog_status_message

        drv = self._drv_catalog_thread_busy()
        fw = bool(self._fw_thread and self._fw_thread.isRunning())
        text = catalog_status_message(msg, drv_running=drv, fw_running=fw)
        if text:
            self.statusBar().showMessage(text)

    def _on_drv_catalog_progress(self, msg: str) -> None:
        if self._shutting_down or self._drv_catalog_job_stale():
            return
        label = self._driver_scan_progress_label(msg)
        self._session_log_progress("driver_catalog", label)
        self._catalog_status_line(label)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )
        if msg.startswith("Checked ") and hasattr(self, "drv_hint"):
            self._set_catalog_hint(self.drv_hint, label)
        m = re.search(r"Checked (\d+)/(\d+)", msg)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            self._drv_scan_progress_total = tot
            self._drv_scan_determinate = True
            if cur >= tot and "finalizing" in msg.lower():
                self._update_drv_workflow_banner(
                    "finalizing",
                    checked=cur,
                    total=tot,
                    batch_note=label,
                )
            else:
                self._update_drv_workflow_banner("scanning", checked=cur, total=tot)
            self._set_task_progress(cur, label, maximum=max(tot, 1))
            return
        if msg.startswith("Coverage check"):
            total = int(getattr(self, "_drv_scan_progress_total", 0) or 0)
            self._update_drv_workflow_banner(
                "finalizing",
                checked=total,
                total=total,
                batch_note=label,
            )
            if getattr(self, "_task_progress_depth", 0) > 0:
                bar = getattr(self, "_task_progress", None)
                if bar is not None and bar.maximum() > 0:
                    self._set_task_progress(label=label)
            return
        batch = re.search(r"Checking (\d+) device\(s\)", msg)
        if batch:
            # Transition into the single determinate 0→100% span for the per-device
            # catalog phase. Everything before this (WU/OEM warm, online store, HWID
            # batch, parallel Update Catalog search) is an indeterminate preparation
            # phase — never a determinate bar that fills to 100% and resets.
            tot = int(batch.group(1))
            self._drv_scan_progress_total = tot
            self._drv_scan_determinate = True
            self._update_drv_workflow_banner("scanning", checked=0, total=tot)
            if getattr(self, "_task_progress_depth", 0) <= 0:
                self._begin_task_progress(label, maximum=max(tot, 1), value=0)
            else:
                self._set_task_progress(0, label, maximum=max(tot, 1))
            return
        # Preparation / warm phases (Windows Update, OEM, online store, HWID batch,
        # parallel Update Catalog search) run before per-device counting and have no
        # single reliable unit total. Show ONE indeterminate (marquee) bar with the
        # live label instead of a determinate bar that fills to 100% and resets each
        # phase (which reads as "done… then hung… then restarted").
        if not getattr(self, "_drv_scan_determinate", False):
            if getattr(self, "_task_progress_depth", 0) <= 0:
                self._begin_task_progress(label, maximum=0)
            else:
                self._set_task_progress(label=label, maximum=0)
            return
        # Per-device substeps (OEM, MSCatalog, "Checking Foo…") that arrive during the
        # determinate phase — update the label only and keep the accumulated fill.
        if getattr(self, "_task_progress_depth", 0) > 0:
            bar = getattr(self, "_task_progress", None)
            if bar is not None and bar.maximum() > 0:
                self._set_task_progress(label=label)
                return

    def _driver_scan_status_breakdown(self, names: set[str]) -> dict[str, int]:
        counts = {
            "newer": 0,
            "same": 0,
            "uncertain": 0,
            "unknown": 0,
            "none": 0,
            "error": 0,
        }
        for dev in self._drv_unified_cache:
            n = (dev.get("name") or "").strip()
            if names and n not in names:
                continue
            if not dev.get("_scan_verified"):
                continue
            st = (dev.get("_check_status") or "none").strip().lower()
            if st not in counts:
                st = "unknown"
            counts[st] += 1
        return counts

    @staticmethod
    def _format_driver_scan_breakdown(counts: dict[str, int]) -> str:
        parts: list[str] = []
        if counts.get("newer"):
            parts.append(f"{counts['newer']} update(s) available")
        if counts.get("same"):
            parts.append(f"{counts['same']} up to date")
        if counts.get("uncertain"):
            parts.append(f"{counts['uncertain']} verify manually (uncertain)")
        if counts.get("unknown"):
            parts.append(f"{counts['unknown']} check manually (unknown version compare)")
        if counts.get("none"):
            parts.append(f"{counts['none']} no catalog match")
        if counts.get("error"):
            parts.append(f"{counts['error']} check failed")
        return " · ".join(parts) if parts else "no verified results"

    def _driver_scan_summary_lines(self, names: set[str]) -> list[str]:
        lines: list[str] = []
        status_labels = {
            "same": "up to date",
            "unknown": "check manually — version strings not comparable",
            "uncertain": "verify manually — conflicting signals",
            "none": "no catalog match",
            "error": "check failed",
        }
        for dev in self._drv_unified_cache:
            n = (dev.get("name") or "").strip()
            if names and n not in names:
                continue
            if not dev.get("_scan_verified"):
                continue
            inst = (dev.get("_installed_at_scan") or dev.get("version") or "?").strip()
            st = (dev.get("_check_status") or "none").strip().lower()
            label = dev.get("display_name") or n
            if st == "newer":
                new_v = (dev.get("_available_version") or "?").strip()
                src = (dev.get("_available_source") or "").strip()
                extra = f" via {src}" if src else ""
                lines.append(f"• {label}: {inst} → {new_v}{extra}")
            elif n in names:
                avail = (dev.get("_available_version") or "").strip()
                src = (dev.get("_available_source") or "").strip()
                if st == "same" and avail:
                    extra = f" via {src}" if src else ""
                    lines.append(f"• {label}: {inst} — catalog {avail}{extra} (same)")
                elif st == "same":
                    lines.append(f"• {label}: {inst} — up to date")
                elif st in status_labels:
                    tail = status_labels[st]
                    if avail:
                        extra = f" via {src}" if src else ""
                        lines.append(
                            f"• {label}: {inst} — catalog {avail}{extra} ({tail})"
                        )
                    else:
                        lines.append(f"• {label}: {inst} — {tail}")
        return lines

    def _drv_catalog_job_stale(self) -> bool:
        return (
            self._shutting_down
            or self._drv_catalog_job_generation != self._drv_catalog_generation
        )

    def _on_driver_catalog_ready(self, comparison: dict) -> None:
        if self._drv_catalog_job_stale():
            self._session_log_end(
                "driver_catalog",
                "Driver catalog search cancelled (superseded)",
                "_session_log_catalog_token",
                status="cancelled",
            )
            self._end_task_progress()
            return
        try:
            self._on_driver_catalog_ready_impl(comparison)
        except Exception as e:  # noqa: BLE001 — keep GUI alive after catalog work
            import traceback

            self._end_task_progress()
            detail = traceback.format_exc()
            if not self._shutting_down:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Driver check — display error",
                    f"{e}\n\nCatalog data was retrieved but updating the window failed.\n\n"
                    f"{detail[-1200:]}",
                )
                self.statusBar().showMessage(
                    f"Driver check finished but display failed: {str(e)[:80]}", 8000
                )

    def _on_driver_catalog_ready_impl(self, comparison: dict) -> None:
        self._end_task_progress()
        fetched = comparison.get("fetched_at") or ""
        devices = comparison.get("devices") or []
        offers = comparison.get("offers") or []
        if devices:
            checked = len(devices)
            updates = sum(1 for d in devices if (d.get("status") or "") == "newer")
            summary = f"Checked {checked} device(s); {updates} update(s) available"
        elif offers:
            summary = f"Single-device check — {len(offers)} offer(s)"
        else:
            summary = "Driver catalog search complete"
        elapsed_ms = self._session_log_end(
            "driver_catalog",
            summary,
            "_session_log_catalog_token",
            extra={"fetched_at": fetched} if fetched else None,
        )
        if elapsed_ms is not None:
            comparison = dict(comparison)
            comparison["elapsed_ms"] = elapsed_ms
        if self._compare_target == "drivers":
            checked = getattr(self, "_drv_check_names", set())
            auto_culprit = getattr(self, "_drv_auto_culprit_scan", False)
            self._drv_auto_culprit_scan = False
            synth_key = getattr(self, "_drv_crash_synth_key", None)
            if synth_key:
                self._drv_crash_synth_key = None
                self._merge_crash_module_into_batch(comparison, synth_key)
            else:
                self._driver_batch_comparison = self._merge_driver_batch_comparison(
                    comparison
                )
                self._apply_driver_batch_results(
                    comparison, only_names=checked if checked else None
                )
            QtCore.QTimer.singleShot(0, self._apply_drv_filter)
            self._maybe_report_post_install_recheck(comparison)
            if self._settings.get("remember_driver_firmware_checks"):
                if synth_key:
                    devices = (self._driver_batch_comparison or {}).get(
                        "devices"
                    ) or []
                    synth_dev = next(
                        (
                            d
                            for d in devices
                            if (d.get("device_name") or "").strip() == synth_key
                        ),
                        None,
                    )
                    if synth_dev:
                        QtCore.QTimer.singleShot(
                            0,
                            lambda d=synth_dev, ts=fetched: drvidx.record_batch_results(
                                [d], fetched_at=ts
                            ),
                        )
                else:
                    batch_devices = list(comparison.get("devices") or [])
                    QtCore.QTimer.singleShot(
                        0,
                        lambda rows=batch_devices, ts=fetched: drvidx.record_batch_results(
                            rows, fetched_at=ts
                        ),
                    )
                idx_err = drvidx.peek_index_error()
                if idx_err:
                    self.statusBar().showMessage(
                        f"Could not save check results: {idx_err[:60]}", 8000
                    )
            crash_names = set(self._crash_report_driver_names(self._last_model or {}))
            checked_crash = bool(checked & crash_names)
            if synth_key and core.is_crash_synthetic_device_key(synth_key):
                checked_crash = True
            batch_updates = sum(
                1
                for n in checked
                if (self._drv_result_for_name(n) or {}).get("status") == "newer"
            )
            breakdown = self._driver_scan_status_breakdown(checked)
            breakdown_text = self._format_driver_scan_breakdown(breakdown)
            summary = self._driver_scan_summary_lines(checked)
            brief = (
                f"Scan finished — checked {len(checked)} device(s). {breakdown_text}. "
                "Select a device to see packages."
            )
            detail_lines = [
                f"Scan finished at {fetched}.",
                f"Results: {breakdown_text}.",
            ]
            if breakdown.get("unknown") or breakdown.get("uncertain"):
                detail_lines.append(
                    "Unknown / Uncertain: a package was found but versions could not be "
                    "compared — not the same as up to date."
                )
            eligible = [
                d
                for d in (self._drv_unified_cache or [])
                if not self._drv_device_excluded_from_catalog(d)
            ]
            pending_after = sum(
                1 for d in eligible if not d.get("_scan_verified")
            )
            if pending_after > max(10, len(eligible) // 4):
                incomplete = (
                    f"{pending_after} of {len(eligible)} device(s) were not scanned — "
                    "run ② Search for updates with All devices (plugged into AC power)."
                )
                detail_lines.insert(1, incomplete)
                brief = f"{brief} {incomplete}"
            if summary:
                detail_lines.extend(summary[:20])
            self._set_catalog_hint(self.drv_hint, brief, tooltip="\n".join(detail_lines))
            if batch_updates:
                idx = self.drv_view_filter.findData("updates")
                if idx >= 0:
                    self.drv_view_filter.setCurrentIndex(idx)
            elif auto_culprit and self._has_crash_faulting_driver():
                idx = self.drv_view_filter.findData("log_attention")
                if idx >= 0:
                    self.drv_view_filter.setCurrentIndex(idx)
            self._drv_check_names = set()
            primary = self._drv_primary_table()
            if primary is None or primary.currentRow() < 0:
                pick = self._drv_first_selectable_row()
                if pick >= 0:
                    self.drv_unified_table.selectRow(pick)
                    primary = self.drv_unified_table
            if primary is not None:
                self._on_drv_device_row_selected(primary)
            self.drv_btn_install.setEnabled(False)
            trunc, orig = drvcat.peek_session_rows_truncated()
            status_msg = f"Driver check complete — {breakdown_text}."
            if trunc and orig:
                status_msg += f" Catalog capped at 8000 of {orig} rows."
            self.statusBar().showMessage(status_msg, 12000)
            self._refresh_system_restore_button()
            if checked_crash:
                self._apply_crash_driver_scan_to_summary()
            self._record_maintenance_activity(
                "Driver update search",
                detail=(
                    f"Checked {len(checked)} device(s); "
                    f"{batch_updates} with a newer package."
                ),
            )
            self._update_drv_workflow_banner(
                "done",
                checked=len(checked),
                updates=batch_updates,
                total=len(checked),
            )
            QtCore.QTimer.singleShot(0, self._maybe_warn_vendor_health_after_scan)
            return

        self._driver_comparison = comparison
        offers = comparison.get("offers") or []
        suffix = (
            f"\n\nCompared at {fetched}. Select a row and use Install driver on the Drivers tab. "
            "Use Install only when you choose — never automatic."
        )
        self._fill_driver_compare_table(self.driver_compare_table, offers)
        self.driver_update_hint.setText(
            self.driver_update_hint.text().split("\n\n")[0] + suffix
        )
        self._refresh_system_restore_button()
        self.statusBar().showMessage(f"Found {len(offers)} driver offer(s).")

    def _on_driver_catalog_failed(self, err: str) -> None:
        if self._drv_catalog_job_stale():
            self._session_log_end(
                "driver_catalog",
                "Driver catalog search cancelled (superseded)",
                "_session_log_catalog_token",
                status="cancelled",
            )
            self._end_task_progress()
            return
        self._session_log_end(
            "driver_catalog",
            f"Driver catalog search failed: {err[:200]}",
            "_session_log_catalog_token",
            status="error",
        )
        self._end_task_progress()
        self._update_drv_workflow_banner("failed")
        try:
            QtWidgets.QMessageBox.warning(self, "Driver check", err)
            self.statusBar().showMessage("Driver check failed.")
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(
                f"Driver check failed: {err[:60]} ({str(e)[:40]})", 8000
            )
