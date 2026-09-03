"""SSD inventory workers and unified firmware list build."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiFirmwareInventoryMixin:
    def _ensure_ssd_firmware_inventory(
        self,
        *,
        force_refresh: bool = False,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Load SSD firmware rows on demand (Firmware tab scan button or explicit refresh)."""
        if force_refresh:
            self._ssd_firmware_loaded = False
        if self._ssd_firmware_loaded:
            if on_ready:
                on_ready()
            return
        if self._ssd_fw_thread and self._ssd_fw_thread.isRunning():
            if on_ready:
                self._ssd_fw_on_ready = on_ready
            return
        prof = self._hardware_profile or self._ensure_hardware_profile()
        if not prof:
            if on_ready:
                self._ssd_fw_on_ready = on_ready
            if self._hw_thread and self._hw_thread.isRunning():
                self._pending_firmware_load_after_hw = True
                self.statusBar().showMessage(
                    "Hardware scan in progress — firmware inventory will load when it finishes.",
                    6000,
                )
                return
            self._pending_firmware_load_after_hw = True
            self.statusBar().showMessage(
                "Scanning hardware for firmware inventory…", 6000
            )
            self._start_hardware_scan()
            return
        if on_ready:
            self._ssd_fw_on_ready = on_ready
        import gui_theme as theme

        self._set_refresh_component_list_ui(enabled=False, label=theme.BTN_FW_LOADING)
        self._begin_task_progress("Loading SSD firmware info…", maximum=0)
        self.statusBar().showMessage("Loading SSD firmware info…")
        if self.tabs.currentIndex() == self._firmware_tab_index():
            self._populate_firmware_tab()
        prof = self._hardware_profile
        pnp_list = list((prof or {}).get("pnp_list") or [])
        driver_rows = self._full_driver_rows(prof) if prof else []
        self._ssd_fw_thread = QtCore.QThread()
        self._ssd_fw_worker = SsdFirmwareWorker(pnp_list, driver_rows)
        self._ssd_fw_worker.moveToThread(self._ssd_fw_thread)
        self._ssd_fw_thread.started.connect(self._ssd_fw_worker.run)
        self._ssd_fw_worker.progress.connect(self._signal_relay.status_message)
        self._ssd_fw_worker.finished.connect(self._signal_relay.ssd_firmware_loaded)
        self._ssd_fw_worker.failed.connect(self._signal_relay.ssd_firmware_load_failed)
        self._ssd_fw_worker.finished.connect(self._ssd_fw_thread.quit)
        self._ssd_fw_worker.failed.connect(self._ssd_fw_thread.quit)
        self._ssd_fw_thread.finished.connect(self._cleanup_ssd_firmware_thread)
        self._ssd_fw_thread.start()

    def _cleanup_ssd_firmware_thread(self) -> None:
        self._ssd_fw_thread = None
        self._ssd_fw_worker = None
        self._sync_fw_workflow_buttons()

    @QtCore.Slot(object)
    def _on_ssd_firmware_loaded(self, payload: object) -> None:
        if self._shutting_down:
            self._ssd_fw_on_ready = None
            return
        if isinstance(payload, dict):
            rows = payload.get("ssd") or []
            secondary = payload.get("secondary") or []
        else:
            rows = list(payload or [])
            secondary = []
        if self._hardware_profile is not None:
            self._hardware_profile["ssd_firmware"] = rows
            self._hardware_profile["secondary_firmware"] = secondary
        if self._last_model is not None:
            self._last_model["ssd_firmware"] = rows
            self._last_model["secondary_firmware"] = secondary

        self._ssd_firmware_loaded = True
        self._fw_include_user_customized = False
        self._end_task_progress()
        self._set_refresh_component_list_ui(enabled=True)

        n = len(rows or [])
        n2 = len(secondary or [])
        loaded_msg = (
            f"Firmware inventory loaded — {n} SSD, {n2} secondary device(s)."
            if n2
            else (
                f"SSD inventory loaded ({n} drive(s))."
                if n
                else "SSD inventory loaded (no SSD rows found)."
            )
        )
        on_fw_tab = self.tabs.currentIndex() == self._firmware_tab_index()
        if on_fw_tab:
            self.statusBar().showMessage("Updating component list…", 0)
            self._populate_firmware_tab()
            self._sync_fw_workflow_buttons()
            self.statusBar().showMessage(loaded_msg, 8000)
        else:
            self.statusBar().showMessage(loaded_msg, 8000)

        cb = self._ssd_fw_on_ready
        self._ssd_fw_on_ready = None
        if cb and not on_fw_tab:
            cb()

    @QtCore.Slot(str)
    def _on_ssd_firmware_load_failed(self, err: str) -> None:
        if self._shutting_down:
            return
        self._end_task_progress()
        self._set_refresh_component_list_ui(enabled=True)
        cb = self._ssd_fw_on_ready
        self._ssd_fw_on_ready = None
        self._show_actionable_error(
            "Firmware scan",
            "SSD firmware read failed.",
            err,
        )
        if self.tabs.currentIndex() == self._firmware_tab_index():
            self._set_catalog_hint(
                self.fw_hint,
                f"Could not read SSD firmware info: {err[:80]}… "
                "Click ① Load components to retry.",
            )
        if cb:
            cb()

    def _firmware_stop_code(self) -> int | None:
        m = self._last_model or {}
        val = m.get("stop_code_val")
        return val if isinstance(val, int) else None

    def _firmware_bios_crash_priority(self) -> bool:
        code = self._firmware_stop_code()
        return code is not None and code in self._FW_BIOS_PRIORITY_CODES

    def _firmware_ssd_crash_priority(self) -> bool:
        code = self._firmware_stop_code()
        return code is not None and code in self._FW_DISK_STOP_CODES

    def _fw_status_column(self) -> int:
        return FW_COL_STATUS

    def _apply_fw_include_defaults(self) -> None:
        """Include every catalog-eligible component (matches Drivers → All devices)."""
        if getattr(self, "_fw_include_user_customized", False):
            return
        for ent in self._fw_unified_cache:
            key = ent.get("key") or ""
            if not key or key in ("ssd:loading", "ssd:none"):
                continue
            self._fw_check_excluded.discard(key)

    def _fw_component_visible(self, ent: dict, needle: str) -> bool:
        if not self._fw_passes_view_filter(ent):
            return False
        if needle:
            label = (ent.get("component") or "").lower()
            if needle not in label:
                return False
        return True

    def _sync_firmware_inventory_from_model(self, m: dict, prof: dict) -> None:
        """Apply firmware rows gathered during Run Analysis (Drivers tab parity)."""
        ctx = m.get("system_ctx") or {}
        has_fw = (
            "ssd_firmware" in m
            or "secondary_firmware" in m
            or "ssd_firmware" in ctx
            or "secondary_firmware" in ctx
        )
        if not has_fw:
            return
        ssd = m.get("ssd_firmware")
        if ssd is None:
            ssd = ctx.get("ssd_firmware")
        secondary = m.get("secondary_firmware")
        if secondary is None:
            secondary = ctx.get("secondary_firmware")
        prof["ssd_firmware"] = list(ssd or [])
        prof["secondary_firmware"] = list(secondary or [])
        self._ssd_firmware_loaded = True
        if self._hardware_profile is not None:
            self._hardware_profile["ssd_firmware"] = prof["ssd_firmware"]
            self._hardware_profile["secondary_firmware"] = prof["secondary_firmware"]
        if self._last_model is not None:
            self._last_model["ssd_firmware"] = prof["ssd_firmware"]
            self._last_model["secondary_firmware"] = prof["secondary_firmware"]

    def _build_unified_firmware_list(self, prof: dict) -> list[dict]:
        bios = (prof.get("bios_driver_info") or {}).get("bios") or {}
        mfr = (bios.get("manufacturer") or "").strip()
        ver = (bios.get("version") or "?").strip()
        bios_label = "Motherboard BIOS"
        if mfr:
            bios_label += f" ({mfr})"
        rows: list[dict] = [
            {
                "key": "bios",
                "component": bios_label,
                "installed": ver,
                "manufacturer": mfr,
                "_check_status": "pending",
                "_reasons": [],
            }
        ]
        ssd_list = prof.get("ssd_firmware") or []
        ssd_loading = (
            not self._ssd_firmware_loaded
            and not ssd_list
            and self._ssd_fw_thread is not None
            and self._ssd_fw_thread.isRunning()
        )
        if ssd_loading:
            rows.append(
                {
                    "key": "ssd:loading",
                    "component": "SSD drives",
                    "installed": "Loading…",
                    "_check_status": "pending",
                    "_reasons": [],
                }
            )
        elif ssd_list:
            for d in ssd_list:
                model = (d.get("model") or "SSD").strip()
                fw = (d.get("firmware_revision") or "?").strip()
                rows.append(
                    {
                        "key": f"ssd:{model}",
                        "component": f"SSD — {model}",
                        "installed": fw,
                        "model": model,
                        "_check_status": "pending",
                        "_reasons": [],
                    }
                )
        elif self._ssd_firmware_loaded:
            rows.append(
                {
                    "key": "ssd:none",
                    "component": "Storage",
                    "installed": "—",
                    "_check_status": "pending",
                    "_reasons": [],
                }
            )

        secondary_list = prof.get("secondary_firmware") or []
        if not secondary_list and self._ssd_firmware_loaded:
            try:
                import firmware_peripheral_discovery as fpdisc

                pnp = prof.get("pnp_list") or []
                drivers = self._full_driver_rows(prof)
                secondary_list = fpdisc.discover_secondary_firmware_devices(
                    pnp,
                    drivers,
                    query_pnp_firmware=False,
                    has_bios=True,
                )
            except ImportError:
                secondary_list = []
        else:
            try:
                import firmware_peripheral_discovery as fpdisc

                secondary_list = fpdisc.finalize_secondary_firmware_devices(
                    secondary_list,
                    has_bios=True,
                )
            except ImportError:
                pass
        for dev in secondary_list:
            key = (dev.get("key") or "").strip()
            if not key:
                continue
            installed = (dev.get("installed") or dev.get("driver_version") or "—").strip()
            src = (dev.get("installed_source") or "").strip()
            component = (dev.get("component") or dev.get("resolved_name") or "?").strip()
            row = {
                "key": key,
                "component": component,
                "installed": installed,
                "vendor_key": dev.get("vendor_key") or "",
                "device_id": dev.get("device_id") or "",
                "installed_source": src,
                "_tier": "secondary",
                "_check_status": "pending",
                "_reasons": ["Secondary — USB / PnP firmware"],
                "_scan_verified": False,
            }
            if src == "hid_driver":
                row["_reasons"].append("MCU version not reported by Windows")
            rows.append(row)

        bios_priority = self._firmware_bios_crash_priority()
        ssd_priority = self._firmware_ssd_crash_priority()

        def tier(row: dict) -> int:
            key = row.get("key") or ""
            status = row.get("_check_status") or "pending"
            if key == "bios" and bios_priority:
                return 0
            if key.startswith("ssd:") and key not in ("ssd:loading", "ssd:none") and ssd_priority:
                return 0
            if row.get("_scan_verified") and status == "newer":
                return 1
            if key == "ssd:loading":
                return 2
            return 3

        for row in rows:
            if row.get("_tier") == "secondary":
                if "_scan_verified" not in row:
                    row["_scan_verified"] = False
                continue
            if "_scan_verified" not in row:
                row["_scan_verified"] = False
            t = tier(row)
            row["_tier"] = ("culprit", "outdated", "attention", "normal")[t]
            if row["_tier"] == "culprit":
                code = self._firmware_stop_code()
                if row.get("key") == "bios":
                    row["_reasons"] = [
                        f"Crash-related (stop 0x{code:08X})" if code else "Crash-related"
                    ]
                else:
                    row["_reasons"] = [
                        f"Storage-related crash (0x{code:08X})" if code else "Storage-related crash"
                    ]
            elif row["_tier"] == "outdated":
                row["_reasons"] = ["Update available"]

        rows.sort(
            key=lambda x: (
                tier(x),
                (x.get("component") or "").lower(),
            )
        )
        drvidx.apply_index_hints_to_firmware_rows(rows, self._settings)
        drvidx.apply_index_packages_to_verified_firmware_rows(rows, self._settings)
        return rows
