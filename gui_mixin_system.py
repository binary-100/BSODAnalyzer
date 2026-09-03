"""System HTML, CDB tasks, export, event filter."""
from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiSystemMixin:
    def _culprit_banner_html(self, callout: dict) -> str:
        import gui_theme as theme

        crash_red = theme.SEVERITY_COLORS[3]
        driver = self._esc(callout.get("driver", ""))
        devices = callout.get("devices") or []
        dev_lines = "".join(
            f"<div style='margin:4px 0 0 12px'>• <b style='color:{crash_red}'>"
            f"{self._esc(name)}</b></div>"
            for name in devices
        )
        summary = callout.get("summary", "")
        summary_html = (
            f"<div style='color:{theme.MUTED}; margin-top:6px'>{self._esc(summary)}</div>"
            if summary else "")
        return (
            f"<div style='background:{theme.CARD_ALT}; border:1px solid {crash_red}; border-radius:8px; "
            f"padding:12px; margin-bottom:16px'>"
            f"<div style='color:{crash_red}; font-weight:600; font-size:14px'>"
            f"Crash-related device (not listed under Common devices)</div>"
            f"<div style='margin-top:6px'>Driver from crash logs: <b>{driver}</b></div>"
            f"{dev_lines}{summary_html}"
            f"<div style='color:{theme.MUTED}; margin-top:8px; font-size:12px'>"
            f"These are platform/chipset or other devices — expand <b>All devices</b> below "
            f"to see the full list.</div></div>"
        )

    def _system_html(self, m: dict) -> str:
        import gui_theme as theme

        parts = ["<div style='line-height:150%'>"]
        callout = m.get("culprit_callout")
        if callout:
            parts.append(self._culprit_banner_html(callout))
        probs = m.get("devices_with_driver_problems", [])
        if probs:
            parts.append("<h3 style='margin-top:0'>Devices with missing or problematic drivers</h3>")
            for d in probs[:20]:
                shown = d.get("display_name") or d.get("name", "?")
                parts.append(f"<div>• <b>{self._esc(shown)}</b> "
                             f"<span style='color:{theme.MUTED}'>{self._esc(d.get('error_meaning', ''))} (Code {self._esc(str(d.get('error_code', '')))})</span></div>")
            parts.append(f"<p style='color:{theme.MUTED}'>Fix: Device Manager &gt; right-click device &gt; Update driver.</p>")
        bios = (m.get("bios_driver_info") or {}).get("bios") or {}
        if bios and (bios.get("manufacturer") or bios.get("version")):
            parts.append("<h3>BIOS / Firmware</h3>")
            parts.append(
                f"<p style='color:{theme.MUTED}; margin-top:0'>"
                f"<a href='firmware-tab' style='color:{theme.ACCENT}; text-decoration:none'>"
                f"Open Firmware tab</a> to check for BIOS/UEFI updates (OEM laptops and DIY boards).</p>"
            )
            parts.append(f"<div>Manufacturer: <b>{self._esc(bios.get('manufacturer', ''))}</b></div>")
            parts.append(f"<div>Version: <b>{self._esc(bios.get('version', ''))}</b></div>")
            parts.append(f"<div>Date: {self._esc(core._parse_json_date(bios.get('date', '')))}</div>")
        info = m.get("bios_driver_info") or {}
        drivers = info.get("drivers") or []
        all_drivers = self._full_driver_rows()
        if not all_drivers:
            all_drivers = info.get("all_drivers") or []
        inventory = core.device_inventory_for_matching(info)
        driver = m.get("driver")
        culprit_keys = m.get("culprit_device_names")
        if culprit_keys is None and driver:
            resolved = core.resolve_crash_culprit_context(
                driver,
                info,
                code_val=m.get("stop_code_val"),
                system_ctx=m.get("system_ctx"),
                cause_type=m.get("cause_type"),
                fix_plan=m.get("fix_plan"),
                has_crash_context=True,
            )
            culprit_keys = sorted(resolved["culprit_device_names"])
        culprits = {
            str(n).strip()
            for n in (culprit_keys or [])
            if n and not core.is_crash_synthetic_device_key(str(n))
        }
        if driver and culprits:
            names = ", ".join(sorted(culprits)[:4])
            extra = f" (+{len(culprits) - 4} more)" if len(culprits) > 4 else ""
            self._culprit_tip = (
                f"Crash logs point to driver {driver}. Related device(s): {names}{extra}.")
        elif driver:
            self._culprit_tip = (
                f"Crash logs point to driver {driver} as the likely cause of your crashes.")
        else:
            self._culprit_tip = ""
        if drivers:
            parts.append(f"<h3>Common devices ({len(drivers)})</h3>")
            parts.append(f"<p style='color:{theme.MUTED}; margin-top:0'>Recognizable hardware — graphics, "
                         f"storage, network, audio, input and similar devices on this system.</p>")
            for d in drivers:
                parts.append(self._driver_row_html(d, show_class=True,
                                                   culprit=d.get("name", "") in culprits))
        if inventory or all_drivers:
            list_for_all = all_drivers if all_drivers else inventory
            count = len(list_for_all)
            parts.append("<h3>All devices</h3>")
            if self._show_all_devices and all_drivers:
                parts.append(f"<div><a href='toggle:devices' style='color:{theme.ACCENT}; text-decoration:none'>"
                             f"▼ Hide full device list ({count})</a></div>")
                for d in all_drivers:
                    parts.append(self._driver_row_html(d, show_class=True,
                                                       culprit=d.get("name", "") in culprits))
            elif self._show_all_devices and not all_drivers:
                parts.append(f"<div style='color:{theme.MUTED}'>Loading full device list…</div>")
            else:
                label = f"all {count} installed devices" if all_drivers else "all installed devices"
                parts.append(f"<div><a href='toggle:devices' style='color:{theme.ACCENT}; text-decoration:none'>"
                             f"▶ Show {label}</a></div>")
        gen = m.get("devices_with_generic_driver", [])
        if gen:
            parts.append("<h3>Devices using a generic driver</h3>")
            parts.append(
                f"<p style='color:{theme.MUTED}; margin-top:0'>Click a device to open the "
                f"<a href='drivers-tab' style='color:{theme.ACCENT}; text-decoration:none'>Drivers</a> "
                f"tab and check for manufacturer-specific packages.</p>"
            )
            for d in gen[:15]:
                dn = d.get("name", "?")
                shown = d.get("display_name") or dn
                qn = urllib.parse.quote(dn, safe="")
                parts.append(
                    f"<div>• <a href='device-driver:{qn}' style='color:{theme.ACCENT}; "
                    f"text-decoration:none'>{self._esc(shown)}</a></div>"
                )
            if len(gen) > 15:
                parts.append(
                    f"<div style='color:{theme.MUTED}'>… and {len(gen) - 15} more (see Drivers tab).</div>"
                )
        if len(parts) == 1:
            parts.append(f"<p style='color:{theme.MUTED}'>No BIOS or driver data gathered.</p>")
        parts.append("</div>")
        return "".join(parts)

    def _driver_row_html(self, d: dict, show_class: bool = False, culprit: bool = False) -> str:
        import gui_theme as theme

        cls = d.get("device_class", "")
        cls_html = (f" <span style='color:{theme.MUTED}'>[{self._esc(cls)}]</span>"
                    if show_class and cls else "")
        ver = self._esc(d.get("version", "")) or "?"
        date = self._esc(core._parse_json_date(d.get("date", "")))
        name = self._esc(d.get("display_name") or d.get("name", ""))
        if culprit:
            crash_red = theme.SEVERITY_COLORS[3]
            # Wrap in an anchor (href 'culprit') so the ToolTip event filter can detect hover.
            name_html = (f"<a href='culprit' style='color:{crash_red}; font-weight:600; "
                         f"text-decoration:none'>{name}</a>"
                         f" <span style='color:{crash_red}; font-weight:600'>— likely crash cause</span>")
            return (f"<div>• {name_html}{cls_html} "
                    f"<span style='color:{theme.MUTED}'>v{ver} ({date})</span></div>")
        return (f"<div>• {name}{cls_html} "
                f"<span style='color:{theme.MUTED}'>v{ver} ({date})</span></div>")

    def eventFilter(self, obj, event) -> bool:
        if obj is self.system_text.viewport() and event.type() == QtCore.QEvent.ToolTip:
            href = self.system_text.anchorAt(event.pos())
            if href == "culprit" and self._culprit_tip:
                QtWidgets.QToolTip.showText(event.globalPos(), self._culprit_tip, self.system_text)
            else:
                QtWidgets.QToolTip.hideText()
            return True
        return super().eventFilter(obj, event)

    def _on_system_anchor(self, url) -> None:
        href = url.toString()
        if href == "firmware-tab":
            self._focus_firmware_tab()
            return
        if href == "drivers-tab":
            self._focus_drivers_tab_for_device("")
            return
        if href.startswith("device-driver:"):
            name = urllib.parse.unquote(href.split(":", 1)[1])
            self._focus_drivers_tab_for_device(name)
            return
        if href == "toggle:devices":
            expanding = not self._show_all_devices
            if expanding:
                rows = self._full_driver_rows()
                if not rows:
                    self.statusBar().showMessage(
                        "Use Drivers → Scan driver devices to load the full inventory.",
                        8000,
                    )
                    return
            self._show_all_devices = expanding
            if self._last_model is not None:
                pos = self.system_text.verticalScrollBar().value()
                self.system_text.setHtml(self._system_html(self._last_model))
                self.system_text.verticalScrollBar().setValue(pos)
                self.statusBar().showMessage(self._initial_status())

    def on_enable_dump(self) -> None:
        msg, changed = core.enable_memory_dumps_or_report_status(1)
        QtWidgets.QMessageBox.information(self, "Enable Memory Dump", msg)
        self.statusBar().showMessage(msg[:120])
        dump_val, dump_config = core.get_dump_config()
        if dump_val and dump_val != 0:
            self.dump_status.setText(f"Memory dumps are enabled in the Windows registry ({dump_config}).")

    def on_export(self) -> None:
        self._export_available_data()

    def on_windbg(self) -> None:
        ok, msg = core.launch_latest_dump_in_windbg()
        if ok:
            QtWidgets.QMessageBox.information(self, "WinDbg", msg)
        else:
            QtWidgets.QMessageBox.information(self, "WinDbg", msg)

    # ---- CDB install / update ----
    def on_install_cdb(self) -> None:
        self._run_cdb_task("install")

    def on_update_cdb(self) -> None:
        self._run_cdb_task("update")

    def _run_cdb_task(self, kind: str) -> None:
        if self._cdb_thread is not None and self._cdb_thread.isRunning():
            return
        self.btn_cdb_install.setEnabled(False)
        self.btn_cdb_update.setEnabled(False)
        verb = "Updating" if kind == "update" else "Installing"
        self.cdb_status_label.setText(f"{verb} Debugging Tools… this can take several minutes.")
        self.statusBar().showMessage(f"{verb} CDB…")

        self._cdb_thread = QtCore.QThread()
        self._cdb_worker = CdbWorker(kind)
        self._cdb_worker.moveToThread(self._cdb_thread)
        self._cdb_thread.started.connect(self._cdb_worker.run)
        self._cdb_worker.progress.connect(self._signal_relay.cdb_progress)
        self._cdb_worker.finished.connect(self._signal_relay.cdb_finished)
        self._cdb_worker.finished.connect(self._cdb_thread.quit)
        self._cdb_thread.start()

    @QtCore.Slot(str)
    def _on_cdb_progress(self, msg: str) -> None:
        self.cdb_status_label.setText(msg)
        self.statusBar().showMessage(msg[:120])

    @QtCore.Slot(bool, str)
    def _on_cdb_finished(self, ok: bool, msg: str) -> None:
        if self._cdb_thread:
            if self._cdb_thread.isRunning():
                self._cdb_thread.quit()
                self._cdb_thread.wait(self._CDB_THREAD_WAIT_MS)
        self._cdb_thread = None
        self._cdb_worker = None
        if self._shutting_down:
            return
        self._refresh_cdb_status()
        self.statusBar().showMessage(self._initial_status())
        box = QtWidgets.QMessageBox.information if ok else QtWidgets.QMessageBox.warning
        box(self, "Debugging Tools (CDB)", msg)


