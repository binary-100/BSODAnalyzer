"""Admin banner, severity dot, bottom toolbar, placeholder glance panel."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiWindowChromeMixin:
    def _build_admin_notice(self) -> QtWidgets.QFrame:
        frame = apply_styled_frame(QtWidgets.QFrame(), "AdminNotice")
        lay = QtWidgets.QHBoxLayout(frame)
        lay.setContentsMargins(12, 8, 12, 8)
        icon = QtWidgets.QLabel("⚠")
        icon.setObjectName("AdminNoticeIcon")
        text = QtWidgets.QLabel(
            "Running without Administrator rights — event logs, minidumps, and some "
            "driver checks may be incomplete. Right-click BSODAnalyzer.exe → Run as administrator."
        )
        text.setWordWrap(True)
        text.setObjectName("AdminNoticeText")
        lay.addWidget(icon, 0, QtCore.Qt.AlignTop)
        lay.addWidget(text, 1)
        frame.setVisible(not log_cleanup.is_user_admin())
        return frame

    # ---- Banner ----
    def _build_banner(self) -> QtWidgets.QFrame:
        banner = apply_styled_frame(QtWidgets.QFrame(), "Banner")
        lay = QtWidgets.QHBoxLayout(banner)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(16)

        self.dot = QtWidgets.QLabel()
        self.dot.setFixedSize(28, 28)
        self.dot.setAccessibleName("Severity indicator")
        import gui_theme as theme

        self._set_dot_color(theme.BORDER, label="Unknown")
        lay.addWidget(self.dot, 0, QtCore.Qt.AlignTop)

        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(2)
        self.cause_title = QtWidgets.QLabel("Ready to scan")
        self.cause_title.setObjectName("CauseTitle")
        self.cause_title.setWordWrap(True)
        self.cause_sub = QtWidgets.QLabel("Click Run Analysis to inspect crash dumps and event logs.")
        self.cause_sub.setObjectName("CauseSub")
        self.cause_sub.setWordWrap(True)
        text_col.addWidget(self.cause_title)
        text_col.addWidget(self.cause_sub)
        lay.addLayout(text_col, 1)
        return banner

    def _set_dot_color(self, color: str, *, label: str = "") -> None:
        self.dot.setStyleSheet(
            f"background-color: {color}; border-radius: 14px; border: 3px solid {color};"
        )
        if label:
            self.dot.setAccessibleName(f"Severity: {label}")
            self.dot.setAccessibleDescription(
                f"Crash severity indicator — {label}"
            )

    def _build_toolbar(self) -> QtWidgets.QHBoxLayout:
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(8)
        self.btn_run = QtWidgets.QPushButton("Run Analysis")
        self.btn_run.setObjectName("Primary")
        self.btn_run.clicked.connect(self.on_run)
        self.btn_dump = QtWidgets.QPushButton("Enable Memory Dump")
        self.btn_dump.clicked.connect(self.on_enable_dump)
        self.btn_export = QtWidgets.QPushButton("Export Report")
        self.btn_export.setToolTip(
            "Save session results to a folder. Choose crash report, driver summary, "
            "and/or detailed JSON — all available options are selected by default."
        )
        self.btn_export.clicked.connect(self.on_export)
        self.btn_search_driver_updates = QtWidgets.QPushButton(BTN_DRV_SEARCH)
        self.btn_search_driver_updates.setToolTip(
            "Step 2 — check devices with Include checked (Microsoft, OEM, vendor catalogs). "
            "Available after ① Load devices finishes on the Drivers tab."
        )
        self.btn_search_driver_updates.setEnabled(False)
        self.btn_search_driver_updates.clicked.connect(
            self._on_begin_driver_update_workflow
        )
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_search_driver_updates)
        bar.addWidget(self.btn_dump)
        bar.addWidget(self.btn_export)
        if hasattr(self, "drv_btn_install"):
            self.drv_btn_install.setVisible(False)
            bar.addWidget(self.drv_btn_install)
        if hasattr(self, "drv_btn_open_catalog"):
            self.drv_btn_open_catalog.setVisible(False)
            bar.addWidget(self.drv_btn_open_catalog)
        if hasattr(self, "drv_btn_restore_driver"):
            self.drv_btn_restore_driver.setVisible(False)
            bar.addWidget(self.drv_btn_restore_driver)
        if hasattr(self, "fw_btn_download"):
            self.fw_btn_download.setVisible(False)
            bar.addWidget(self.fw_btn_download)
        if hasattr(self, "fw_btn_set_installed"):
            self.fw_btn_set_installed.setVisible(False)
            bar.addWidget(self.fw_btn_set_installed)
        bar.addStretch(1)
        self.btn_windbg_link = QtWidgets.QPushButton("Open in WinDbg (advanced)")
        self.btn_windbg_link.setObjectName("Link")
        self.btn_windbg_link.clicked.connect(self.on_windbg)
        bar.addWidget(self.btn_windbg_link)
        return bar

    # ---- Helpers ----
    def _initial_status(self) -> str:
        cdb = core.find_cdb()
        if cdb:
            ver = core.get_cdb_version(cdb)
            ver_txt = f" (CDB v{ver})" if ver else ""
            if (
                app_set.is_full_install_mode(self._settings)
                and self._hardware_inventory_ready()
            ):
                return (
                    f"CDB found{ver_txt}. Run Analysis for crashes; "
                    "Search for driver updates when you want catalog checks."
                )
            return f"CDB found{ver_txt}. Click Run Analysis to analyze minidumps."
        return "CDB not found — install Debugging Tools (Advanced tab) for full minidump analysis."

    def _refresh_cdb_status(self) -> None:
        """Update the Debugger (CDB) card text and which buttons are enabled."""
        if self._cdb_thread is not None:
            return  # a task is running; leave the in-progress text alone
        st = core.cdb_status()
        if st["installed"]:
            if st.get("is_bundled"):
                loc = "bundled with this app — portable"
            elif st["is_local"]:
                loc = "local offline copy"
            else:
                loc = "system install"
            ver = f" v{st['version']}" if st.get("version") else ""
            txt = f"CDB found ({loc}){ver}."
            if not st["is_local"] and not st.get("is_bundled"):
                txt += " A local offline copy will be saved on the next install/update."
            if st["online"]:
                txt += " You can check Microsoft for a newer build."
            else:
                txt += " Offline — connect to the internet to check for updates."
            self.cdb_status_label.setText(txt)
            self.btn_cdb_install.setVisible(False)
            self.btn_cdb_update.setEnabled(st["online"])
        else:
            if st["online"]:
                txt = ("CDB is not installed. Click Install CDB to download the latest Debugging "
                       "Tools from Microsoft (a local offline copy is saved for future use).")
            elif st["bundled_installer"]:
                txt = ("CDB is not installed. You're offline, but a bundled installer is available — "
                       "click Install CDB to install from it.")
            else:
                txt = ("CDB is not installed and you're offline with no bundled installer. "
                       "Connect to the internet to install, or place winsdksetup.exe in the "
                       "DebuggingTools/Installers folder.")
            self.cdb_status_label.setText(txt)
            self.btn_cdb_install.setVisible(True)
            self.btn_cdb_install.setEnabled(st["online"] or st["bundled_installer"])
            self.btn_cdb_update.setEnabled(False)

    def _show_placeholder(self) -> None:
        msg = ("<p style='color:%s'>Run an analysis to populate this view.</p>" % MUTED)
        self.driver_update_frame.setVisible(False)
        for tb in (self.plain_text, self.action_text, self.system_text):
            tb.setHtml(msg)
        self.details_text.setHtml(msg)
        prof = self._hardware_profile
        if prof and app_set.is_full_install_mode(self._settings):
            self.system_text.setHtml(
                self._system_html(self._display_model_from_profile(prof))
            )
        self.raw_text.setPlainText("Run an analysis to see raw WinDbg output.")
        self._refresh_cdb_status()
        dump_val, dump_config = core.get_dump_config()
        if dump_val is None or dump_val == 0:
            self.dump_status.setText("Windows memory dumps are not enabled. Use 'Enable Memory Dump' so future crashes are captured.")
        else:
            self.dump_status.setText(f"Memory dumps are enabled in the Windows registry ({dump_config}).")

    def _clear_glance(self) -> None:
        while self.glance.count():
            item = self.glance.takeAt(0)
            wgt = item.widget()
            if wgt:
                wgt.deleteLater()

    def _add_glance(self, key: str, value: str) -> None:
        row = self.glance.rowCount()
        k = QtWidgets.QLabel(key)
        k.setObjectName("Muted")
        v = QtWidgets.QLabel(value)
        v.setObjectName("SectionValue")
        v.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        v.setWordWrap(True)
        self.glance.addWidget(k, row, 0)
        self.glance.addWidget(v, row, 1)

    @staticmethod
    def _esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
