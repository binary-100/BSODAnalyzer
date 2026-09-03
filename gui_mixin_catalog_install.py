"""Driver install, backup, restore, and System Restore actions."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiCatalogInstallMixin:
    def _device_context_for_install(self, device_name: str) -> dict | None:
        """Build catalog device context for component-targeted install."""
        name = (device_name or "").strip()
        if not name:
            return None
        prof = self._hardware_profile_data() or {}
        pnp_list = prof.get("pnp_list") or []
        inv = self._full_driver_rows(prof) or prof.get("bios_driver_info", {}).get(
            "device_inventory"
        ) or []
        system_ctx = dict(prof.get("system_ctx") or {})
        system_ctx.setdefault("system_manufacturer", prof.get("manufacturer") or "")
        system_ctx.setdefault("system_model", prof.get("model") or "")
        system_ctx.setdefault("service_tag", prof.get("service_tag") or "")
        system_ctx.setdefault("video_controllers", prof.get("video_controllers") or [])
        system_ctx.setdefault("pnp_enrichment", prof.get("pnp_enrichment") or {})
        try:
            return drvcat.get_device_context_for_name(
                name, pnp_list, inv, system_ctx
            )
        except Exception:
            return None

    def _offer_from_compare_row(
        self, table: QtWidgets.QTableWidget, row: int | None = None
    ) -> tuple[dict, QtWidgets.QTableWidgetItem | None]:
        if row is None:
            row = table.currentRow()
        if row < 0:
            return {}, None
        for col in (1, 2, 0):
            item = table.item(row, col)
            if not item:
                continue
            offer = item.data(QtCore.Qt.UserRole)
            if offer:
                return dict(offer), item
        return {}, None

    def _selected_driver_device_name(self, *, for_drivers_tab: bool = True) -> str:
        if for_drivers_tab:
            names = self._drv_selected_device_names()
            return names[0] if names else ""
        ctx = (self._driver_comparison or {}).get("context") or {}
        return (ctx.get("device_label") or ctx.get("target_device_name") or "").strip()

    def _offer_persist_key(self, offer: dict) -> tuple[str, str, str, str, str]:
        return (
            (offer.get("title") or "").strip(),
            (offer.get("version") or "").strip(),
            (offer.get("source") or "").strip(),
            (offer.get("update_id") or "").strip(),
            (offer.get("url") or "").strip()[:240],
        )

    def _merge_downloaded_path_into_offer(self, target: dict, source: dict) -> dict:
        path = (source.get("downloaded_path") or source.get("local_package_path") or "").strip()
        if not path:
            return target
        merged = dict(target)
        merged["downloaded_path"] = path
        if source.get("update_id") and not (merged.get("update_id") or "").strip():
            merged["update_id"] = source["update_id"]
        return merged

    def _persist_downloaded_offer(self, offer: dict) -> None:
        """Write downloaded_path back to the package table and in-memory comparisons."""
        path = (offer.get("downloaded_path") or offer.get("local_package_path") or "").strip()
        if not path or not os.path.isfile(path):
            return
        key = self._offer_persist_key(offer)

        def _match(o: dict) -> bool:
            return self._offer_persist_key(o) == key

        table = getattr(self, "drv_compare_table", None)
        if table is not None:
            for row in range(table.rowCount()):
                for col in (1, 2, 0):
                    item = table.item(row, col)
                    if not item:
                        continue
                    stored = item.data(QtCore.Qt.UserRole)
                    if not isinstance(stored, dict) or not _match(stored):
                        continue
                    updated = self._merge_downloaded_path_into_offer(stored, offer)
                    item.setData(QtCore.Qt.UserRole, updated)

        comp = self._driver_comparison or {}
        offers = comp.get("offers")
        if isinstance(offers, list):
            comp["offers"] = [
                self._merge_downloaded_path_into_offer(o, offer) if _match(o) else o
                for o in offers
            ]
            self._driver_comparison = comp

        batch = self._driver_batch_comparison or {}
        devices = batch.get("devices")
        if isinstance(devices, list):
            for entry in devices:
                if not isinstance(entry, dict):
                    continue
                entry_offers = entry.get("offers")
                if not isinstance(entry_offers, list):
                    continue
                entry["offers"] = [
                    self._merge_downloaded_path_into_offer(o, offer) if _match(o) else o
                    for o in entry_offers
                ]
            self._driver_batch_comparison = batch

        self._on_drv_compare_selection_changed()

    def _update_driver_install_buttons(self, *, for_drivers_tab: bool = False) -> None:
        if not for_drivers_tab:
            return
        table = self.drv_compare_table
        row = table.currentRow()
        offer, _item = self._offer_from_compare_row(table, row)
        can, reason = drvinst.offer_install_capability(offer)
        self.drv_btn_install.setEnabled(row >= 0 and can)
        cat_url = drvcat.microsoft_catalog_view_url(offer) if isinstance(offer, dict) else None
        open_btn = getattr(self, "drv_btn_open_catalog", None)
        if open_btn is not None:
            open_btn.setEnabled(bool(row >= 0 and cat_url))
            if cat_url:
                open_btn.setToolTip(
                    "Open this Microsoft Update Catalog package in your browser "
                    f"(Package Details / hardware IDs).\n\n{cat_url}"
                )
            else:
                open_btn.setToolTip(
                    "Select a Microsoft Update Catalog package row to open its catalog page."
                )
        tip = (
            reason
            if row >= 0
            else "Select a package below after checking for updates."
        )
        self.drv_btn_install.setToolTip(
            f"{tip}\n\nInstall runs only when you click — never automatic. "
            "Downloads the package first when needed. Administrator required."
        )

    def _on_open_catalog_for_selected_offer(self, *, for_drivers_tab: bool = False) -> None:
        if not for_drivers_tab:
            return
        table = self.drv_compare_table
        row = table.currentRow()
        offer, _item = self._offer_from_compare_row(table, row)
        if not isinstance(offer, dict):
            return
        url = drvcat.microsoft_catalog_view_url(offer)
        if not url:
            QtWidgets.QMessageBox.information(
                self,
                "Update Catalog",
                "This package is not from the Microsoft Update Catalog.",
            )
            return
        import webbrowser

        webbrowser.open(url)
        self.statusBar().showMessage(f"Opened Update Catalog — {url}", 12000)

    def _on_drv_compare_selection_changed(self) -> None:
        self._update_driver_install_buttons(for_drivers_tab=True)

    def _on_fw_compare_selection_changed(self) -> None:
        self.fw_btn_download.setEnabled(self.fw_compare_table.currentRow() >= 0)

    def _driver_backup_root(self) -> str:
        import driver_backup as drvbackup

        return drvbackup.default_backup_root(self._settings)

    def _driver_backup_keep_count(self) -> int:
        import driver_backup as drvbackup

        return drvbackup.backup_keep_count(self._settings)

    def _maybe_show_driver_install_checklist(self) -> None:
        if self._settings.get("driver_install_checklist_seen"):
            return
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setWindowTitle("Before you install a driver")
        box.setText(
            "A few safeguards before changing drivers:\n\n"
            "• Back up the current driver (recommended, on by default)\n"
            "• Optional system restore point on the install confirm dialog\n"
            "• If a new driver causes trouble later, select the device and click "
            "Restore previous driver on the Drivers toolbar\n"
            "• Manage backups anytime from Tools → Driver backups…"
        )
        box.addButton(QtWidgets.QMessageBox.Ok)
        box.exec()
        self._settings["driver_install_checklist_seen"] = True
        app_set.save_settings(self._settings)

    def _cleanup_install_thread(self) -> None:
        self._install_thread = None
        self._install_worker = None
        self.drv_btn_install.setEnabled(True)
        self.drv_btn_install_file.setEnabled(True)
        self._on_drv_compare_selection_changed()

    def _start_driver_install(
        self,
        offer: dict,
        *,
        device_name: str = "",
        backup_before: bool = False,
        create_restore_point: bool = False,
    ) -> None:
        if self._install_thread and self._install_thread.isRunning():
            QtWidgets.QMessageBox.information(
                self,
                "Install driver",
                "An install is already in progress.",
            )
            return
        self.drv_btn_install.setEnabled(False)
        self.drv_btn_install_file.setEnabled(False)
        self._last_install_context = {
            "device_name": device_name,
            "package_title": (offer.get("title") or "")[:120],
            "offer_key": self._offer_persist_key(offer),
            "installed_version_before": self._installed_version_for_device(device_name),
        }
        self._begin_task_progress("Preparing driver install…", maximum=0)
        self.statusBar().showMessage("Preparing driver install…")
        self._install_thread = QtCore.QThread()
        self._install_worker = InstallDriverWorker(
            offer,
            device_name=device_name,
            device_ctx=self._device_context_for_install(device_name),
            backup_before=backup_before,
            backup_root=self._driver_backup_root(),
            backup_keep_count=self._driver_backup_keep_count(),
            create_restore_point=create_restore_point,
        )
        self._install_worker.moveToThread(self._install_thread)
        self._install_thread.started.connect(self._install_worker.run)
        self._install_worker.progress.connect(self._signal_relay.driver_install_progress)
        self._install_worker.finished.connect(self._signal_relay.driver_install_finished)
        self._install_worker.failed.connect(self._signal_relay.driver_install_failed)
        self._install_worker.finished.connect(self._install_thread.quit)
        self._install_worker.failed.connect(self._install_thread.quit)
        self._install_thread.finished.connect(self._cleanup_install_thread)
        self._install_thread.start()

    @QtCore.Slot(str)
    def _on_driver_install_progress(self, msg: str) -> None:
        self._set_task_progress(label=msg)

    @QtCore.Slot(bool, str, object, object)
    def _on_driver_install_finished(
        self, ok: bool, msg: str, offer: object, backup_record: object = None,
    ) -> None:
        self._end_task_progress()
        ctx = self._last_install_context or {}
        device = (ctx.get("device_name") or "").strip()
        version_before = (ctx.get("installed_version_before") or "").strip()
        if isinstance(offer, dict):
            self._persist_downloaded_offer(offer)
        rec = backup_record if isinstance(backup_record, dict) else None
        vendor_launch = self._finish_driver_install_feedback(
            msg, backup_record=rec, device_name=device,
        )
        if device:
            self._post_install_recheck_ctx = {
                "device_name": device,
                "installed_version_before": version_before,
                "vendor_launch": vendor_launch,
                "install_msg": (msg or "").strip(),
                "install_ok": bool(ok),
            }
        self._update_driver_restore_button()
        if device and not vendor_launch:
            QtCore.QTimer.singleShot(
                500,
                lambda d=device: self._recheck_driver_devices([d], quiet=True),
            )

    @QtCore.Slot(str, object)
    def _on_driver_install_failed(self, err: str, offer: object) -> None:
        self._end_task_progress()
        self._last_install_context = None
        if isinstance(offer, dict):
            self._persist_downloaded_offer(offer)
        QtWidgets.QMessageBox.warning(self, "Install driver", err)
        self.statusBar().showMessage("Driver install failed.", 15000)

    def _select_driver_devices(self, names: list[str]) -> None:
        table = self.drv_unified_table
        if not names:
            return
        sm = table.selectionModel()
        sm.clearSelection()
        flags = (
            QtCore.QItemSelectionModel.Select
            | QtCore.QItemSelectionModel.Rows
        )
        for name in names:
            _tbl, row = self._drv_row_for_name(name)
            if row >= 0:
                sm.select(table.model().index(row, 0), flags)

    def _recheck_driver_devices(
        self, names: list[str], *, quiet: bool = False,
    ) -> None:
        if not names:
            return
        self._focus_drivers_tab_for_device(names[0])
        self._select_driver_devices(names)
        if self._drv_catalog_thread_busy():
            if quiet:
                self.statusBar().showMessage(
                    "Install finished — a scan is already running; "
                    "installed version will refresh when it completes.",
                    15000,
                )
                return
            QtWidgets.QMessageBox.information(
                self,
                "Driver check",
                "A driver check is already running — wait for it to finish, then try again.",
            )
            return
        if quiet:
            self.statusBar().showMessage(
                f"Refreshing installed driver version for {names[0]}…",
                12000,
            )
        self._on_check_driver_catalog(for_drivers_tab=True)

    def _latest_backup_for_device(self, device_name: str) -> dict | None:
        import driver_backup as drvbackup

        key = (device_name or "").strip().lower()
        if not key:
            return None
        for rec in drvbackup.list_driver_backups(self._driver_backup_root()):
            if (rec.get("device_name") or "").strip().lower() == key:
                return rec
        return None

    def _update_driver_restore_button(self) -> None:
        btn = getattr(self, "drv_btn_restore_driver", None)
        if btn is None:
            return
        device = self._selected_driver_device_name()
        rec = self._latest_backup_for_device(device) if device else None
        path = (rec.get("path") or "").strip() if rec else ""
        self._pending_driver_restore_path = path or None
        admin = log_cleanup.is_user_admin()
        btn.setEnabled(bool(path) and admin)
        if not admin:
            btn.setToolTip(self._ADMIN_GATED_TOOLTIP)
            return
        if path and rec:
            ver = (rec.get("driver_version") or "").strip() or "unknown version"
            when = (rec.get("backed_up_at_local") or rec.get("backed_up_at") or "").strip()
            tip = f"Restore pre-change backup ({ver}"
            if when:
                tip += f", {when}"
            tip += "). Use if the new driver misbehaves — usually not needed immediately after install."
            btn.setToolTip(tip)
        else:
            btn.setToolTip(
                "Roll back to the most recent saved backup for the selected device. "
                "Use this if a new driver causes problems — not needed right after install."
            )

    def _finish_driver_install_feedback(
        self,
        install_msg: str,
        *,
        backup_record: dict | None = None,
        device_name: str = "",
    ) -> bool:
        """Update status bar after install. Returns True if a vendor wizard was opened."""
        ctx = self._last_install_context or {}
        self._last_install_context = None
        device = (device_name or ctx.get("device_name") or "").strip()
        low = (install_msg or "").lower()
        vendor_launch = (
            "vendor installer" in low
            or "opened the vendor installer" in low
            or "setup.exe from extracted" in low
        )
        if vendor_launch:
            status = (
                "Vendor installer opened — complete that wizard (Device Manager will not "
                "change until it finishes). Reboot if the installer asks, then use "
                "Search for updates or re-select this device to refresh the version. "
                "Dell/Realtek installers can report success even when Windows keeps the "
                "current driver (not a better match)."
            )
        elif "pnputil" in low:
            status = (
                "Driver package applied via Windows (pnputil) — there is no separate "
                "installer window. Refreshing installed version… If Device Manager still "
                "shows the old driver, reboot or use Update driver on that device."
            )
        elif "installed" in low:
            status = "Driver install command finished. Refreshing installed version…"
        else:
            status = (install_msg or "Driver install finished.").split("\n", 1)[0].strip()
        if backup_record and backup_record.get("path"):
            status += (
                " Pre-install backup saved — Restore previous driver on the "
                "Drivers toolbar if you need to roll back."
            )
        elif device:
            status += f" ({device})"
        self.statusBar().showMessage(status[:280], 25000)
        return vendor_launch

    def _on_restore_previous_driver(self) -> None:
        device = self._selected_driver_device_name()
        rec = self._latest_backup_for_device(device) if device else None
        path = (rec.get("path") or self._pending_driver_restore_path or "").strip()
        if not path:
            QtWidgets.QMessageBox.information(
                self,
                "Restore previous driver",
                "Select a device in the list that has a saved backup, then try again.\n\n"
                "Backups are created automatically before install when that option is enabled, "
                "or use Tools → Driver backups…",
            )
            return
        self._confirm_and_restore_backup(path)

    def _confirm_install_driver(
        self,
        *,
        summary: str,
        device_name: str,
        offer: dict,
    ) -> None:
        self._maybe_show_driver_install_checklist()
        dlg = gui_prefs.InstallDriverConfirmDialog(
            self,
            summary=summary,
            settings=self._settings,
            allow_backup=not core.is_platform_chipset_device_key(device_name),
        )
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if not self._prompt_seven_zip_before_driver_install(offer=offer):
            return
        choices = dlg.choices()
        self._start_driver_install(
            offer,
            device_name=device_name,
            backup_before=bool(choices.get("backup_before")) and bool(device_name),
            create_restore_point=bool(choices.get("create_restore_point")),
        )

    def _on_install_selected_driver(self, *, for_drivers_tab: bool = False) -> None:
        if not for_drivers_tab:
            return
        table = self.drv_compare_table
        offer, _item = self._offer_from_compare_row(table)
        if not offer:
            return
        can, reason = drvinst.offer_install_capability(offer)
        if not can:
            QtWidgets.QMessageBox.information(self, "Install driver", reason)
            return
        device_name = self._selected_driver_device_name(for_drivers_tab=True)
        src = offer.get("source_label") or offer.get("source") or "driver"
        ver = offer.get("version") or "—"
        device_ctx = self._device_context_for_install(device_name) if device_name else None
        component_note = drvinst.component_install_confirm_note(offer, device_ctx)
        summary = (
            f"Install this driver now?\n\n"
            f"Source: {src}\n"
            f"Package: {offer.get('title', '')}\n"
            f"Version: {ver}\n"
            f"Device: {device_name or '(see package)'}\n\n"
            f"{reason}"
            f"{component_note}\n\n"
            "The app will download the package when needed, then install it or open "
            "the vendor setup program."
        )
        self._confirm_install_driver(
            summary=summary,
            device_name=device_name,
            offer=offer,
        )

    def _pick_driver_install_path(self) -> tuple[str, str] | tuple[None, None]:
        """Return (path, kind) where kind is file or folder."""
        choice = QtWidgets.QMessageBox(self)
        choice.setWindowTitle("Install driver")
        choice.setText("Install from a driver package file or a backed-up driver folder?")
        btn_file = choice.addButton("File…", QtWidgets.QMessageBox.ActionRole)
        btn_folder = choice.addButton("Backup folder…", QtWidgets.QMessageBox.ActionRole)
        choice.addButton(QtWidgets.QMessageBox.Cancel)
        choice.exec()
        clicked = choice.clickedButton()
        if clicked == btn_file:
            path, _flt = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Install driver from file",
                "",
                "Driver packages (*.cab *.inf *.zip *.7z *.msu *.exe *.msi);;All files (*.*)",
            )
            return (path, "file") if path else (None, None)
        if clicked == btn_folder:
            path = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Install driver from backup folder",
                self._driver_backup_root(),
            )
            return (path, "folder") if path else (None, None)
        return None, None

    def _on_install_driver_from_file(self, *, for_drivers_tab: bool = False) -> None:
        if not for_drivers_tab:
            return
        path, kind = self._pick_driver_install_path()
        if not path:
            return
        low = path.lower()
        if kind == "folder" or os.path.isdir(path):
            import driver_backup as drvbackup

            manifest = os.path.join(path, drvbackup.MANIFEST_NAME)
            title = os.path.basename(path)
            if os.path.isfile(manifest):
                title = f"Backup: {title}"
            offer = {"downloaded_path": path, "source": "local", "title": title}
            can, reason = drvinst.offer_install_capability(offer)
            if not can:
                QtWidgets.QMessageBox.warning(self, "Install driver", reason)
                return
            device_name = self._selected_driver_device_name(for_drivers_tab=True)
            summary = (
                f"Install driver files from backup folder:\n\n{path}\n\n"
                f"{reason}\n\n"
                "Only runs because you clicked Install — never automatic. "
                "Administrator required."
            )
            self._confirm_install_driver(
                summary=summary,
                device_name=device_name,
                offer=offer,
            )
            return
        if low.endswith((".exe", ".msi")):
            offer = {"downloaded_path": path, "source": "local", "title": os.path.basename(path)}
            can, reason = drvinst.offer_install_capability(offer)
            if not can:
                QtWidgets.QMessageBox.warning(self, "Install driver", reason)
                return
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Install driver",
                f"Open the vendor installer?\n\n{path}\n\n{reason}\n\nContinue?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
            self._start_driver_install(offer, device_name="")
            return
        offer = {"downloaded_path": path, "source": "local", "title": os.path.basename(path)}
        can, reason = drvinst.offer_install_capability(offer)
        if not can:
            QtWidgets.QMessageBox.warning(self, "Install driver", reason)
            return
        device_name = self._selected_driver_device_name(for_drivers_tab=True)
        if not self._prompt_seven_zip_before_driver_install(path=path):
            return
        summary = (
            f"Install driver files from:\n\n{path}\n\n"
            f"{reason}\n\n"
            "Only runs because you clicked Install — never automatic. "
            "Administrator required."
        )
        self._confirm_install_driver(
            summary=summary,
            device_name=device_name,
            offer=offer,
        )

    def _on_create_restore_point(self) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Create restore point",
            "Create a system restore point now?\n\n"
            "Requires System Restore to be enabled and administrator rights.\n"
            "Do this before you install a new driver manually if you want a rollback option.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._start_ps_maintenance("create_restore")

    def _prompt_enable_system_restore(self, reason: str) -> None:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("System Restore disabled")
        box.setText(
            f"{reason}\n\n"
            "You can enable System Restore on your system drive, or open System Protection "
            "to turn it on manually."
        )
        btn_enable = box.addButton("Enable System Restore", QtWidgets.QMessageBox.ActionRole)
        btn_settings = box.addButton("Open System Protection", QtWidgets.QMessageBox.ActionRole)
        box.addButton(QtWidgets.QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == btn_enable:
            self._on_enable_system_restore(retry_restore_point=True)
        elif clicked == btn_settings:
            ok, msg = drvcat.open_system_protection_settings()
            if ok:
                QtWidgets.QMessageBox.information(self, "System Protection", msg)
            else:
                QtWidgets.QMessageBox.warning(self, "System Protection", msg)

    def _on_enable_system_restore(self, retry_restore_point: bool = False) -> None:
        self._start_ps_maintenance(
            "enable_restore",
            drive=self._system_restore_drive,
            retry_restore_point=retry_restore_point,
        )

    def _on_backup_driver(self) -> None:
        ctx = (self._driver_comparison or {}).get("context") or {}
        name = ctx.get("device_label") or ctx.get("target_device_name") or ""
        if not name:
            primary = self._drv_primary_table()
            if primary is not None and primary.currentRow() >= 0:
                item = primary.item(primary.currentRow(), DRV_COL_DEVICE)
                if item:
                    name = str(item.data(QtCore.Qt.UserRole) or item.text())
        if not name and self._last_model:
            info = (self._last_model.get("culprit_driver_info") or [])
            if info:
                name = info[0].get("name") or ""
        if not name:
            QtWidgets.QMessageBox.warning(
                self,
                "Back up driver",
                "No device selected. Use the Drivers tab or run crash analysis first.",
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Back up driver",
            f"Export the current driver package for:\n\n{name}\n\n"
            f"Requires administrator rights. Files are saved under:\n"
            f"{self._driver_backup_root()}\n\nContinue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._start_ps_maintenance(
            "backup_driver",
            device_name=name,
            backup_root=self._driver_backup_root(),
            keep_count=self._driver_backup_keep_count(),
        )

    def _on_driver_backups_dialog(self) -> None:
        dlg = gui_prefs.DriverBackupsDialog(
            self,
            settings=self._settings,
            on_restore=self._start_driver_restore,
        )
        dlg.exec()

    def _confirm_and_restore_backup(self, backup_path: str) -> None:
        path = (backup_path or "").strip()
        if not path:
            return
        if self._restore_thread and self._restore_thread.isRunning():
            QtWidgets.QMessageBox.information(
                self,
                "Restore driver",
                "A restore is already in progress.",
            )
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Restore driver",
            f"Reinstall the backed-up driver from:\n\n{path}\n\nContinue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._start_driver_restore(path)

    def _cleanup_restore_thread(self) -> None:
        self._restore_thread = None
        self._restore_worker = None

    def _start_driver_restore(self, backup_path: str) -> None:
        self._begin_task_progress("Restoring driver backup…", maximum=0)
        self.statusBar().showMessage("Restoring driver backup…")
        self._restore_thread = QtCore.QThread()
        self._restore_worker = RestoreDriverWorker(backup_path)
        self._restore_worker.moveToThread(self._restore_thread)
        self._restore_thread.started.connect(self._restore_worker.run)
        self._restore_worker.progress.connect(self._signal_relay.driver_restore_progress)
        self._restore_worker.finished.connect(self._signal_relay.driver_restore_finished)
        self._restore_worker.failed.connect(self._signal_relay.driver_restore_failed)
        self._restore_worker.finished.connect(self._restore_thread.quit)
        self._restore_worker.failed.connect(self._restore_thread.quit)
        self._restore_thread.finished.connect(self._cleanup_restore_thread)
        self._restore_thread.start()

    @QtCore.Slot(str)
    def _on_driver_restore_progress(self, msg: str) -> None:
        self._set_task_progress(label=msg)

    @QtCore.Slot(bool, str)
    def _on_driver_restore_finished(self, ok: bool, msg: str) -> None:
        self._end_task_progress()
        QtWidgets.QMessageBox.information(self, "Restore driver", msg)
        self.statusBar().showMessage(msg[:120])
        self._update_driver_restore_button()

    @QtCore.Slot(str)
    def _on_driver_restore_failed(self, err: str) -> None:
        self._end_task_progress()
        QtWidgets.QMessageBox.warning(self, "Restore driver", err)
        self.statusBar().showMessage("Driver restore failed.")
