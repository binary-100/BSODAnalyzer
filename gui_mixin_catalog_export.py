"""Catalog scan export payloads and session file writes."""

from __future__ import annotations

from dataclasses import dataclass

from gui_app_context import *  # noqa: F403


@dataclass
class ExportFileChoices:
    include_crash_report: bool = False
    include_catalog_summary: bool = False
    include_catalog_json: bool = False

    def any_selected(self) -> bool:
        return (
            self.include_crash_report
            or self.include_catalog_summary
            or self.include_catalog_json
        )

    def needs_catalog_payload(self) -> bool:
        return self.include_catalog_summary or self.include_catalog_json


class GuiCatalogExportMixin:
    def _bundle_fields_from_catalog_entry(self, entry: dict | None) -> dict:
        if not entry:
            return {}
        import bundle_verification as bv

        return {
            "chipset_bundle_components": list(
                entry.get("chipset_bundle_components") or []
            ),
            "chipset_suite_version": (entry.get("chipset_suite_version") or "").strip(),
            "bundle_offer_components": list(entry.get("bundle_offer_components") or []),
            "bundle_component_compare": bv.bundle_compare_rows_from_catalog_entry(entry),
            "bundle_compare_note": (entry.get("bundle_compare_note") or "").strip(),
            "bundle_status_rollup": (entry.get("bundle_status_rollup") or "").strip(),
        }

    def _build_export_index_health(self) -> dict:
        enabled = drvidx.is_index_enabled(self._settings)
        snap = drvidx.index_diagnostics_snapshot()
        health: dict = {"enabled": enabled}
        gaps = snap.get("skipped_devices") or []
        if gaps:
            health["skipped_devices"] = sorted(set(gaps))
        err = (snap.get("read_error") or "").strip()
        if err:
            health["read_error"] = err
        return health

    def _build_catalog_export_payload(self, *, redact_sensitive: bool = False) -> dict:
        sources: list[str] = []
        driver_rows = self._gather_driver_export_rows(sources)
        firmware_rows = self._gather_firmware_export_rows(sources)

        batch = self._driver_batch_comparison or {}
        fw_comp = self._firmware_comparison or {}
        prof = self._hardware_profile or {}
        bio = prof.get("bios_driver_info") or {}

        scan_sm = drvcat.catalog_scan_mode_summary(
            full_install=app_set.is_full_install_mode(self._settings),
            quick_check=bool(self._settings.get("quick_check_mode")),
            gui_mode=True,
        )
        import vendor_endpoint_health as veh

        lookup_health = veh.build_export_lookup_health(
            prof.get("system_ctx") or {},
            scan_sm,
            driver_rows=driver_rows,
            firmware_rows=firmware_rows,
        )
        export_options = {
            k: self._settings.get(k)
            for k in (
                "quick_check_mode",
                "remember_driver_firmware_checks",
                "catalog_include_preview",
                "oem_session_cache",
            )
        }
        export_options["redact_sensitive"] = redact_sensitive
        return cexp.build_payload(
            app_version=core.VERSION,
            export_options=export_options,
            install_mode=(
                "full_install"
                if app_set.is_full_install_mode(self._settings)
                else "portable"
            ),
            scan_mode=scan_sm,
            crash_context={
                "faulting_driver": ((self._last_model or {}).get("driver") or "").strip(),
                "stop_code": (self._last_model or {}).get("stop_code") or "",
                "stop_code_val": (self._last_model or {}).get("stop_code_val"),
                "culprit_device_names": list((self._last_model or {}).get("culprit_device_names") or []),
            },
            hardware_summary=cexp.build_hardware_summary(
                prof,
                bios_driver_info=bio,
                full_driver_count=len(self._full_driver_rows(prof)),
                device_counts=self._export_driver_device_counts(),
                system_ctx=prof.get("system_ctx") or {},
            ),
            driver_rows=driver_rows,
            firmware_rows=firmware_rows,
            driver_batch_fetched_at=(batch.get("fetched_at") or "").strip(),
            firmware_fetched_at=(fw_comp.get("fetched_at") or "").strip(),
            driver_batch_elapsed_ms=batch.get("elapsed_ms"),
            firmware_elapsed_ms=fw_comp.get("elapsed_ms"),
            data_sources=sources,
            lookup_health=lookup_health,
            export_index=self._build_export_index_health(),
            redact_sensitive=redact_sensitive,
        )

    def _confirm_catalog_export_privacy(self) -> tuple[bool, bool]:
        """Return (proceed, redact_sensitive)."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setWindowTitle("Export")
        box.setText(
            "The catalog export may include your service tag, device IDs, crash context, "
            "and manufacturer lookup URLs.\n\n"
            "Share only with people you trust."
        )
        redact_cb = QtWidgets.QCheckBox("Omit service tag & device IDs")
        box.setCheckBox(redact_cb)
        box.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        box.setDefaultButton(QtWidgets.QMessageBox.Yes)
        if box.exec() != QtWidgets.QMessageBox.Yes:
            return False, False
        return True, redact_cb.isChecked()

    def _export_file_options(
        self, *, has_crash: bool, has_catalog: bool
    ) -> list[tuple[str, str, str]]:
        """Return (key, title, description) for each export file available."""
        options: list[tuple[str, str, str]] = []
        if has_crash:
            options.append(
                (
                    "crash",
                    "Crash report (.txt)",
                    "What the tool found about crashes and what to try next. "
                    "Best for support tickets, email, or forums.",
                )
            )
        if has_catalog:
            options.append(
                (
                    "catalog_summary",
                    "Driver & firmware summary (.txt)",
                    "Devices checked, update status, and recommended packages "
                    "in plain language.",
                )
            )
            options.append(
                (
                    "catalog_json",
                    "Driver & firmware details (.json)",
                    "Complete scan data for deep troubleshooting — every catalog "
                    "offer and lookup flag. Use if advanced support asked for a "
                    "full export.",
                )
            )
        return options

    def _export_file_choices_all_on(
        self, options: list[tuple[str, str, str]]
    ) -> ExportFileChoices:
        keys = {key for key, _, _ in options}
        return ExportFileChoices(
            include_crash_report="crash" in keys,
            include_catalog_summary="catalog_summary" in keys,
            include_catalog_json="catalog_json" in keys,
        )

    def _prompt_export_file_choices(
        self, options: list[tuple[str, str, str]]
    ) -> ExportFileChoices | None:
        """Ask which files to save. All available options default to checked."""
        if not options:
            return None
        if len(options) == 1:
            return self._export_file_choices_all_on(options)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Export — choose files")
        dlg.setMinimumWidth(480)
        outer = QtWidgets.QVBoxLayout(dlg)
        intro = QtWidgets.QLabel(
            "Pick what to save. All options use data already collected this session."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        boxes: dict[str, inc_hdr.ItemViewStyleCheckBox] = {}
        for key, title, description in options:
            row = QtWidgets.QWidget()
            row_lay = QtWidgets.QVBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(2)
            cb = inc_hdr.ItemViewStyleCheckBox(title)
            cb.setChecked(True)
            boxes[key] = cb
            row_lay.addWidget(cb)
            desc = QtWidgets.QLabel(description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {MUTED}; margin-left: 22px;")
            row_lay.addWidget(desc)
            outer.addWidget(row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Export")

        def _sync_ok() -> None:
            ok_btn.setEnabled(any(cb.isChecked() for cb in boxes.values()))

        for cb in boxes.values():
            cb.toggled.connect(_sync_ok)
        _sync_ok()
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)

        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return ExportFileChoices(
            include_crash_report=boxes["crash"].isChecked()
            if "crash" in boxes
            else False,
            include_catalog_summary=boxes["catalog_summary"].isChecked()
            if "catalog_summary" in boxes
            else False,
            include_catalog_json=boxes["catalog_json"].isChecked()
            if "catalog_json" in boxes
            else False,
        )

    def _maybe_report_post_install_recheck(self, comparison: dict) -> None:
        ctx = getattr(self, "_post_install_recheck_ctx", None)
        if not ctx or self._compare_target != "drivers":
            return
        device = (ctx.get("device_name") or "").strip()
        before = (ctx.get("installed_version_before") or "").strip()
        vendor = bool(ctx.get("vendor_launch"))
        install_msg = (ctx.get("install_msg") or "").strip()
        install_ok = bool(ctx.get("install_ok"))
        outcome = drvinst.classify_driver_install_outcome(install_msg)
        self._post_install_recheck_ctx = None
        if not device:
            return
        after = ""
        for entry in comparison.get("devices") or []:
            if (entry.get("device_name") or "").strip() == device:
                after = (entry.get("installed_version") or "").strip()
                break
        if not after or not before:
            return
        if before == after:
            if outcome == "windows_kept_driver":
                detail = (
                    f"Install finished but {device} still reports {after}. "
                    "Windows kept the current driver (not a better match)."
                )
            elif vendor:
                detail = (
                    f"Install finished but {device} still reports {after}. "
                    "The vendor log may say success while Windows kept the current driver "
                    "(not a better match). Reboot, then check Device Manager."
                )
            elif install_ok:
                detail = (
                    f"Install command finished but {device} still reports {after}. "
                    "Windows may have kept the current driver — reboot, or check "
                    "Update Catalog → Package Details for a hardware ID mismatch."
                )
            else:
                detail = (
                    f"Install finished but {device} still reports {after}. "
                    "Reboot or use Update driver in Device Manager if you expected a change."
                )
            self.statusBar().showMessage(detail, 30000)
        else:
            self.statusBar().showMessage(
                f"{device} driver updated: {before} -> {after}.",
                20000,
            )

    def _confirm_onedrive_export_destination(self, dest_dir: str | Path) -> bool:
        if self._settings.get("onedrive_export_warn_seen"):
            return True
        warn = app_set.onedrive_export_destination_warning(dest_dir)
        if not warn:
            return True
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("OneDrive export folder")
        box.setText(warn)
        local = app_set.local_export_directory()
        box.setInformativeText(
            f"Continue saving to the selected folder, or cancel and pick a local path "
            f"such as:\n{local}"
        )
        btn_continue = box.addButton("Export here anyway", QtWidgets.QMessageBox.AcceptRole)
        btn_local = box.addButton("Use local exports folder", QtWidgets.QMessageBox.ActionRole)
        btn_dismiss = box.addButton("Don't show again", QtWidgets.QMessageBox.DestructiveRole)
        box.setDefaultButton(btn_local)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_dismiss:
            self._settings["onedrive_export_warn_seen"] = True
            app_set.save_settings(self._settings)
        if clicked is btn_local:
            return False
        return clicked is btn_continue

    def _resolve_export_file_choices(
        self, *, has_crash: bool, has_catalog: bool
    ) -> ExportFileChoices | None:
        options = self._export_file_options(
            has_crash=has_crash, has_catalog=has_catalog
        )
        return self._prompt_export_file_choices(options)

    def _write_session_export_files(
        self,
        dest_dir: str | Path,
        *,
        catalog_payload: dict | None,
        choices: ExportFileChoices,
    ) -> tuple[list[tuple[str, Path]], str]:
        """Write selected export artifacts into dest_dir."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        dest = Path(dest_dir)
        written: list[tuple[str, Path]] = []

        if choices.include_crash_report and (self._full_report or "").strip():
            crash_path = dest / f"BSODAnalyzer_crash_report_{stamp}.txt"
            ok, msg = core.export_report_to_file(str(crash_path), self._full_report)
            if not ok:
                raise OSError(msg)
            written.append(("Crash report (support/email)", crash_path))

        payload = catalog_payload if isinstance(catalog_payload, dict) else None
        if payload:
            drv_n = len(payload.get("drivers") or [])
            fw_n = len(payload.get("firmware") or [])
            if drv_n or fw_n:
                if choices.include_catalog_summary:
                    summary_path = (
                        dest / f"BSODAnalyzer_driver_firmware_summary_{stamp}.txt"
                    )
                    rt.write_text_file_sync(
                        summary_path,
                        cexp.format_text_summary(payload),
                    )
                    written.append(
                        ("Driver & firmware summary", summary_path)
                    )
                if choices.include_catalog_json:
                    catalog_path = dest / f"BSODAnalyzer_catalog_scan_{stamp}.json"
                    cexp.write_export_file(catalog_path, payload)
                    written.append(
                        (
                            f"Driver & firmware details ({drv_n} driver(s), "
                            f"{fw_n} firmware component(s))",
                            catalog_path,
                        )
                    )

        if not written:
            raise OSError("Nothing to write — session data may have changed.")

        for _label, path in written:
            rt.notify_shell_path_updated(path)
        rt.notify_shell_path_updated(dest)
        labels = [label for label, _ in written]
        summary = "Saved " + ", ".join(labels)
        return written, summary

    def _show_export_success(
        self,
        file_entries: list[tuple[str, Path]],
        summary: str,
        *,
        catalog_payload: dict | None = None,
        auto_open_folder: bool = True,
    ) -> None:
        extra = ""
        if catalog_payload and any(
            p.suffix.lower() == ".json" for _, p in file_entries
        ):
            lh = catalog_payload.get("lookup_health") or {}
            vendor_failed = lh.get("session_vendor_failures") or []
            if vendor_failed:
                extra = (
                    f" Vendor lookup failures this session: {', '.join(vendor_failed)}."
                )
            if catalog_payload.get("redacted_sensitive_fields"):
                extra += " Sensitive fields omitted from catalog export."
        folder = str(file_entries[0][1].parent)
        names = ", ".join(label for label, _ in file_entries)
        self.statusBar().showMessage(
            f"Export saved — {names} → {folder}{extra}",
            20000,
        )
        if auto_open_folder:
            rt.reveal_path_in_explorer(file_entries[0][1])
        self._record_maintenance_activity(
            "Exported session data",
            detail=f"{len(file_entries)} file(s) → {file_entries[0][1].parent.name}",
        )

    @QtCore.Slot(object)
    def _drain_pending_catalog_export(self, *, timeout_ms: int = 12000) -> None:
        """Process UI events until async export finishes writing on the main thread."""
        if getattr(self, "_export_drain_active", False):
            return
        if not self._catalog_export_job.is_running() and not self._unified_export_dest_dir:
            return
        self._export_drain_active = True
        try:
            app = QtWidgets.QApplication.instance()
            deadline = time.monotonic() + timeout_ms / 1000.0
            while time.monotonic() < deadline:
                if (
                    not self._catalog_export_job.is_running()
                    and not self._unified_export_dest_dir
                ):
                    return
                if app is not None:
                    app.processEvents(
                        QtCore.QEventLoop.ProcessEventsFlag.AllEvents,
                        100,
                    )
                th = self._catalog_export_job.thread
                if th is not None and th.isRunning():
                    th.wait(50)
        finally:
            self._export_drain_active = False

    def _on_catalog_export_ready(self, result: object) -> None:
        try:
            shutting_down = self._shutting_down
            self._end_task_progress()
            self._unified_export_dest_dir = None
            self._unified_export_choices = None
            if not isinstance(result, dict):
                return
            file_entries = list(result.get("file_entries") or [])
            summary = str(result.get("summary") or "")
            catalog_payload = result.get("catalog_payload")
            if not file_entries:
                return
            if shutting_down:
                self.statusBar().showMessage(
                    f"Export saved ({len(file_entries)} file(s)) before exit.",
                    8000,
                )
                return
            self._show_export_success(
                file_entries,
                summary,
                catalog_payload=catalog_payload if isinstance(catalog_payload, dict) else None,
            )
        finally:
            self._catalog_export_job.stop(wait=False)

    @QtCore.Slot(str)
    def _on_catalog_export_failed(self, err: str) -> None:
        try:
            if self._shutting_down:
                return
            self._end_task_progress()
            self._unified_export_dest_dir = None
            self._unified_export_choices = None
            self._show_actionable_error(
                "Export",
                "Could not build export.",
                err,
            )
        finally:
            self._catalog_export_job.stop(wait=False)

    def _export_driver_device_counts(self) -> dict[str, int | bool | str]:
        prof = self._hardware_profile or {}
        bio = prof.get("bios_driver_info") or {}
        inv = core.device_inventory_for_matching(bio)
        full_rows = self._full_driver_rows(prof)
        view_filter = ""
        if hasattr(self, "drv_view_filter"):
            view_filter = str(self.drv_view_filter.currentData() or "")
        return {
            "full_list_loaded": bool(self._all_devices_loaded and full_rows),
            "inventory_count": len(inv),
            "full_inventory_count": len(full_rows) if full_rows else len(inv),
            "drivers_tab_cache_count": len(self._drv_unified_cache),
            "view_filter": view_filter,
        }

    def _export_driver_device_universe(self) -> list[dict]:
        """Stable export device list — prefer full inventory when it has been loaded."""
        prof = self._hardware_profile or {}
        if not prof:
            return list(self._drv_unified_cache)
        full_rows = self._full_driver_rows(prof)
        if full_rows and self._all_devices_loaded:
            import driver_list_build as drvlist

            batch = self._driver_batch_comparison or {}
            session_batch = (
                {"devices": list((batch or {}).get("devices") or [])}
                if batch
                else None
            )
            return drvlist.build_unified_driver_list(
                self._profile_snapshot_for_driver_list(prof),
                full=True,
                settings=dict(self._settings),
                session_batch=session_batch,
                crash_driver=(self._last_model or {}).get("driver"),
                last_model=self._last_model,
                last_fmt_args=self._last_fmt_args,
            )
        return list(self._drv_unified_cache)

    def _export_device_diagnostics(
        self,
        entry: dict | None,
        dev: dict | None = None,
    ) -> dict:
        ctx = (entry or {}).get("context") if entry else None
        if not isinstance(ctx, dict):
            ctx = {}
        prof = self._hardware_profile or {}
        system_ctx = prof.get("system_ctx") or {}
        if not ctx and dev:
            ctx = {
                "vendor_key": dev.get("vendor_key") or "",
                "pnp_class": dev.get("pnp_class") or dev.get("device_class") or "",
                "device_label": dev.get("display_name") or dev.get("name") or "",
                "instance_id": dev.get("instance_id") or dev.get("device_name") or "",
            }
        return cexp.device_catalog_diagnostics(
            ctx,
            system_ctx=system_ctx,
            offers=list((entry or {}).get("offers") or []),
        )

    def _gather_driver_export_rows(self, sources: list[str]) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        export_devices = self._export_driver_device_universe()
        cache_by_name = {
            (d.get("name") or "").strip(): d
            for d in export_devices
            if (d.get("name") or "").strip()
        }

        def append_from_cache() -> None:
            for dev in export_devices:
                name = (dev.get("name") or "").strip()
                if not name or name in seen:
                    continue
                result = self._drv_result_for_name(name)
                status = (
                    (result or {}).get("status")
                    or dev.get("_check_status")
                    or "none"
                )
                seen.add(name)
                result = result or {}
                rows.append(
                    {
                        "device_name": name,
                        "display_name": (dev.get("display_name") or name).strip(),
                        "manufacturer": (dev.get("manufacturer") or "").strip(),
                        "device_class": (dev.get("device_class") or "").strip(),
                        "driver_file": (dev.get("driver") or "").strip(),
                        "parent_device_name": (dev.get("parent_device_name") or "").strip(),
                        "parent_device_id": (dev.get("parent_device_id") or "").strip(),
                        "installed_version": (
                            result.get("installed_version")
                            or dev.get("_installed_at_scan")
                            or dev.get("version")
                            or "?"
                        ),
                        "status": status,
                        "possible_coverage_gap": bool(
                            result.get("possible_coverage_gap")
                            or dev.get("_possible_coverage_gap")
                        ),
                        "none_reason": (
                            result.get("none_reason")
                            or dev.get("_none_reason")
                            or ""
                        ),
                        "crash_linked": bool(dev.get("_crash_linked")),
                        "tier": (dev.get("_tier") or "").strip(),
                        "offers": list(result.get("offers") or []),
                        "device_diagnostics": self._export_device_diagnostics(result, dev),
                        **self._bundle_fields_from_catalog_entry(result),
                    }
                )

        def append_from_batch() -> None:
            batch = self._driver_batch_comparison or {}
            for entry in batch.get("devices") or []:
                name = (entry.get("device_name") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                dev = cache_by_name.get(name) or next(
                    (d for d in self._drv_unified_cache if (d.get("name") or "") == name),
                    None,
                )
                rows.append(
                    {
                        "device_name": name,
                        "display_name": (
                            (dev or {}).get("display_name") or name
                        ).strip(),
                        "manufacturer": ((dev or {}).get("manufacturer") or "").strip(),
                        "device_class": ((dev or {}).get("device_class") or "").strip(),
                        "driver_file": ((dev or {}).get("driver") or "").strip(),
                        "parent_device_name": ((dev or {}).get("parent_device_name") or "").strip(),
                        "parent_device_id": ((dev or {}).get("parent_device_id") or "").strip(),
                        "installed_version": (
                            entry.get("installed_version")
                            or (dev or {}).get("version")
                            or "?"
                        ),
                        "status": entry.get("status") or "none",
                        "possible_coverage_gap": bool(
                            entry.get("possible_coverage_gap")
                        ),
                        "none_reason": (entry.get("none_reason") or "").strip(),
                        "crash_linked": bool((dev or {}).get("_crash_linked")),
                        "tier": ((dev or {}).get("_tier") or "").strip(),
                        "offers": list(entry.get("offers") or []),
                        "device_diagnostics": self._export_device_diagnostics(entry, dev),
                        **self._bundle_fields_from_catalog_entry(entry),
                    }
                )

        def append_from_index() -> None:
            for entry in drvidx.list_all_device_check_entries():
                name = (entry.get("device_name") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                dev = cache_by_name.get(name) or next(
                    (d for d in self._drv_unified_cache if (d.get("name") or "") == name),
                    None,
                )
                rows.append(
                    {
                        "device_name": name,
                        "display_name": (
                            (dev or {}).get("display_name") or name
                        ).strip(),
                        "manufacturer": ((dev or {}).get("manufacturer") or "").strip(),
                        "device_class": ((dev or {}).get("device_class") or "").strip(),
                        "driver_file": ((dev or {}).get("driver") or "").strip(),
                        "parent_device_name": ((dev or {}).get("parent_device_name") or "").strip(),
                        "parent_device_id": ((dev or {}).get("parent_device_id") or "").strip(),
                        "installed_version": entry.get("installed_version") or "?",
                        "status": entry.get("status") or "none",
                        "crash_linked": bool((dev or {}).get("_crash_linked")),
                        "tier": ((dev or {}).get("_tier") or "").strip(),
                        "offers": list(entry.get("offers") or []),
                        "from_index": True,
                        "device_diagnostics": self._export_device_diagnostics(entry, dev),
                    }
                )

        if self._driver_batch_comparison:
            sources.append("session_driver_batch")
        append_from_batch()
        append_from_cache()
        if drvidx.is_index_enabled(self._settings):
            before = len(rows)
            append_from_index()
            if len(rows) > before:
                sources.append("driver_index.sqlite")
        if not sources and rows:
            sources.append("session_driver_cache")
        return rows

    def _gather_firmware_export_rows(self, sources: list[str]) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()

        for ent in self._fw_unified_cache:
            key = (ent.get("key") or "").strip()
            if not key or key == "ssd:loading" or key in seen:
                continue
            catalog = self._fw_catalog_entry_for_key(key) or {}
            status = (
                catalog.get("status")
                or ent.get("_check_status")
                or "none"
            )
            offers = list(catalog.get("offers") or [])
            if status in ("pending", "none") and not offers and not ent.get("_scan_verified"):
                continue
            seen.add(key)
            rows.append(
                {
                    "target_key": key,
                    "component": (ent.get("component") or key).strip(),
                    "installed_version": (
                        catalog.get("installed_version")
                        or ent.get("installed")
                        or "?"
                    ),
                    "status": status,
                    "tier": (ent.get("_tier") or "").strip(),
                    "offers": offers,
                }
            )

        if self._firmware_comparison:
            sources.append("session_firmware_batch")

        if drvidx.is_index_enabled(self._settings):
            before = len(rows)
            for entry in drvidx.list_all_firmware_check_entries():
                key = (entry.get("target_key") or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                ent = self._fw_cache_row_for_key(key) or {}
                rows.append(
                    {
                        "target_key": key,
                        "component": (
                            entry.get("target_label")
                            or ent.get("component")
                            or key
                        ).strip(),
                        "installed_version": entry.get("installed_version") or "?",
                        "status": entry.get("status") or "none",
                        "tier": (ent.get("_tier") or "").strip(),
                        "offers": list(entry.get("offers") or []),
                        "from_index": True,
                    }
                )
            if len(rows) > before:
                sources.append("driver_index.sqlite")

        if rows and "session_firmware_batch" not in sources and not any(
            s == "driver_index.sqlite" for s in sources
        ):
            sources.append("session_firmware_cache")
        return rows

    def _has_catalog_export_data(self) -> bool:
        """True when driver/firmware scan results can be exported (no crash analysis required)."""
        sources: list[str] = []
        if self._gather_driver_export_rows(sources):
            return True
        sources.clear()
        return bool(self._gather_firmware_export_rows(sources))

    def _export_available_data(self) -> None:
        """Export crash report and/or catalog scan — user picks which files to save."""
        if self._catalog_export_job.is_running():
            self.statusBar().showMessage("Export already in progress…", 5000)
            return
        if self._catalog_search_busy():
            QtWidgets.QMessageBox.information(
                self,
                "Export",
                "A driver or firmware update search (or database refresh) is still "
                "running.\n\nWait for it to finish so export includes complete results.",
            )
            self.statusBar().showMessage(
                "Export blocked — catalog search in progress.", 6000
            )
            return

        has_crash = bool((self._full_report or "").strip())
        has_catalog = self._has_catalog_export_data()
        if not has_crash and not has_catalog:
            QtWidgets.QMessageBox.information(
                self,
                "Export",
                "Nothing to export yet.\n\n"
                "Run Analysis for crash diagnosis, and/or run a driver or firmware scan "
                "(Drivers tab → ① Load devices → ② Search for updates), then try again.",
            )
            return

        choices = self._resolve_export_file_choices(
            has_crash=has_crash, has_catalog=has_catalog
        )
        if choices is None or not choices.any_selected():
            return

        redact = False
        if has_catalog and choices.needs_catalog_payload():
            proceed, redact = self._confirm_catalog_export_privacy()
            if not proceed:
                return
            index_err = drvidx.index_diagnostics_snapshot().get("read_error")
            if index_err:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Export",
                    "The saved driver index could not be read completely — export will "
                    "use session results only.\n\n"
                    f"Detail: {str(index_err)[:240]}",
                )

        dest_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose folder for export",
            rt.default_export_directory(self._settings),
        )
        if not dest_dir:
            return

        dest_path = Path(dest_dir)
        if not self._confirm_onedrive_export_destination(dest_path):
            local = app_set.local_export_directory()
            try:
                local.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Export",
                    f"Could not create local export folder:\n{local}\n\n{exc}",
                )
                return
            dest_path = local
            dest_dir = str(local)
            self.statusBar().showMessage(
                f"Export folder switched to local path (OneDrive Desktop avoided): {local}",
                12000,
            )

        try:
            dest_path.mkdir(parents=True, exist_ok=True)
            probe = dest_path / ".bsod_export_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Export",
                f"Cannot write to the selected folder:\n{dest_dir}\n\n{exc}",
            )
            return

        self._unified_export_dest_dir = str(dest_path)
        self._unified_export_choices = choices

        if has_catalog and choices.needs_catalog_payload():
            self._begin_task_progress("Saving export…", maximum=0)
            dest_dir = str(dest_path)
            export_choices = choices
            redact_flag = redact

            def _export_task() -> dict:
                payload = self._build_catalog_export_payload(
                    redact_sensitive=redact_flag
                )
                file_entries, summary = self._write_session_export_files(
                    dest_dir,
                    catalog_payload=payload,
                    choices=export_choices,
                )
                return {
                    "file_entries": file_entries,
                    "summary": summary,
                    "catalog_payload": payload,
                }

            worker = CatalogExportWorker(_export_task)
            self._catalog_export_job.start(
                worker,
                connections=[
                    (worker.finished, self._signal_relay.catalog_export_ready),
                    (worker.failed, self._signal_relay.catalog_export_failed),
                ],
            )
            return

        try:
            file_entries, summary = self._write_session_export_files(
                dest_dir,
                catalog_payload=None,
                choices=choices,
            )
        except OSError as exc:
            self._unified_export_dest_dir = None
            self._unified_export_choices = None
            QtWidgets.QMessageBox.warning(
                self,
                "Export",
                f"Could not save export:\n{exc}",
            )
            return
        self._unified_export_dest_dir = None
        self._unified_export_choices = None
        self._show_export_success(file_entries, summary)

    def export_catalog_scan_results(self) -> None:
        """Save driver/firmware check results for offline review or sharing."""
        self._export_available_data()
