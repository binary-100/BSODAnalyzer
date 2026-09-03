"""Settings and first-run dialogs for BSOD Analyzer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PySide6 import QtCore, QtWidgets

import app_settings as settings
import bsod_runtime as rt

import driver_backup as drvbackup


class PreferencesDialog(QtWidgets.QDialog):
    """Application preferences with plain-language trade-off descriptions."""

    def __init__(self, parent: QtWidgets.QWidget | None, current: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(520)
        self._data = dict(current)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(12)

        intro = QtWidgets.QLabel(
            "These options change how driver checks and startup behave. "
            "They are saved for this Windows user account."
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        def _opt(title: str, body: str, key: str, default: bool = False) -> QtWidgets.QCheckBox:
            box = QtWidgets.QGroupBox(title)
            bl = QtWidgets.QVBoxLayout(box)
            cb = QtWidgets.QCheckBox("Enabled")
            cb.setChecked(bool(self._data.get(key, default)))
            cb.setProperty("settings_key", key)
            bl.addWidget(cb)
            desc = QtWidgets.QLabel(body)
            desc.setWordWrap(True)
            desc.setObjectName("Muted")
            bl.addWidget(desc)
            lay.addWidget(box)
            return cb

        self._cb_full_install = _opt(
            "Full install mode",
            "Designed for ongoing driver and firmware checks on your own PC: saved device "
            "list and results that survive reboots. Data is stored under "
            "%LOCALAPPDATA%\\BSODAnalyzer (not next to the .exe). Avoid placing that folder "
            "on OneDrive-synced paths if you see lock or corruption errors.\n\n"
            "Watch the cache age on the Drivers tab and use "
            "Tools → Refresh driver database when the on-disk catalog is stale.\n\n"
            "Choose portable mode instead if you mainly need to diagnose crashes.",
            "install_mode",
            False,
        )
        self._cb_full_install.setChecked(
            (self._data.get("install_mode") or "portable") == "full"
        )

        self._cb_quick = _opt(
            "Quick driver check (portable)",
            "For portable / crash-troubleshooting mode only: skips the saved OEM database "
            "and opens your PC maker's support page instead of using a full OEM scrape.\n\n"
            "Full install mode uses a saved driver database — use Tools → Refresh "
            "driver database for a full OEM update.",
            "quick_check_mode",
        )
        self._sync_quick_check_for_install_mode()

        def _on_mode_toggle() -> None:
            self._sync_quick_check_for_install_mode()

        self._cb_full_install.toggled.connect(_on_mode_toggle)

        data_box = QtWidgets.QGroupBox("Full install data folder")
        data_lay = QtWidgets.QVBoxLayout(data_box)
        self._data_dir_label = QtWidgets.QLabel()
        self._data_dir_label.setWordWrap(True)
        self._data_dir_label.setObjectName("Muted")
        data_lay.addWidget(self._data_dir_label)
        self._data_dir_warning = QtWidgets.QLabel()
        self._data_dir_warning.setWordWrap(True)
        self._data_dir_warning.setStyleSheet("color: #f0c040;")
        self._data_dir_warning.hide()
        data_lay.addWidget(self._data_dir_warning)
        data_row = QtWidgets.QHBoxLayout()
        self._btn_choose_data_dir = QtWidgets.QPushButton("Choose folder…")
        self._btn_choose_data_dir.clicked.connect(self._choose_data_dir)
        self._btn_recommended_data_dir = QtWidgets.QPushButton("Use recommended location")
        self._btn_recommended_data_dir.clicked.connect(self._use_recommended_data_dir)
        data_row.addWidget(self._btn_choose_data_dir)
        data_row.addWidget(self._btn_recommended_data_dir)
        data_row.addStretch(1)
        data_lay.addLayout(data_row)
        lay.addWidget(data_box)
        self._pending_custom_data_dir = (self._data.get("custom_data_dir") or "").strip()
        if not self._pending_custom_data_dir and self._cb_full_install.isChecked():
            self._pending_custom_data_dir = str(settings.default_full_install_data_dir())
        self._refresh_data_dir_ui()

        self._cb_oem_cache = _opt(
            "Remember OEM catalog results (this session)",
            "While the app is open, reuses Dell/Lenovo/HP/ASUS/etc. driver lists already "
            "downloaded instead of hitting those sites again for each device.\n\nTrade-off: "
            "results can be up to ~10 minutes old if you just installed a driver — use "
            "Tools → Clear OEM catalog cache after installing.",
            "oem_session_cache",
            True,
        )
        self._cb_catalog_preview = _opt(
            "Include preview / non-WHQL Microsoft Catalog packages",
            "When searching Microsoft Update Catalog (MSCatalogLTS), also show preview "
            "packages. Default is WHQL/stable only.",
            "catalog_include_preview",
            False,
        )
        self._cb_catalog_refresh_prompt = _opt(
            "Prompt when driver database is stale (full install)",
            "Full install only: when you open the Drivers tab and the on-disk WU/OEM "
            "database is older than the cache age in settings, offer Tools → Refresh "
            "driver database once per session. Portable mode uses Search to build cache; "
            "this prompt is off by default there.",
            "catalog_auto_refresh_prompt",
            False,
        )
        self._cb_include_common = _opt(
            "Default Include: common devices (Drivers tab)",
            "When the device list is shown, common hardware (GPU, network, storage, etc.) "
            "is checked for driver search; uncommon devices stay unchecked. Crash-linked "
            "suspects stay checked. Changing any Include box keeps your choices until the "
            "list is force-refreshed.",
            "default_include_common_devices",
            True,
        )
        self._cb_remember = _opt(
            "Remember last driver/firmware check results (Packages only; Updates list needs a new scan)",
            "Keeps update status (e.g. “May have update”) for devices you already checked, "
            "even after closing the app.\n\nTrade-off: status may be stale until you check "
            "again after installing drivers.",
            "remember_driver_firmware_checks",
            True,
        )
        self._cb_timeline = _opt(
            "Show crash timeline on Summary",
            "After Run Analysis, shows how many BSODs occurred in the last 7 and 30 days.",
            "show_crash_timeline",
            True,
        )
        self._cb_reliability = _opt(
            "Include Reliability / Live Kernel events in analysis",
            "During Run Analysis only, reads Live Kernel and WER system events plus the "
            "stability index (same data Reliability Monitor uses). No background service.\n\n"
            "Trade-off: one extra PowerShell query (~1–3 seconds).",
            "show_reliability_events",
            True,
        )
        self._cb_ps7_prompt = _opt(
            "Suggest PowerShell 7 before driver/firmware Search",
            "When Search is clicked and this PC only has Windows PowerShell 5.1, offer "
            f"a short prompt to install PowerShell 7 (Driver Search is {rt.PWSH7_DRIVER_SEARCH_SPEEDUP_LABEL} with pwsh). "
            "The app works without it.",
            "powershell7_upgrade_prompt",
            True,
        )
        self._cb_cdb_prompt = _opt(
            "Suggest WinDbg before Run Analysis when online",
            "When Run Analysis is clicked, this PC is online, and Microsoft's WinDbg app "
            "is not installed, offer to install the latest WinDbg. Offline runs use the bundled debugger.",
            "cdb_online_install_prompt",
            True,
        )
        self._cb_7z_prompt = _opt(
            "Suggest 7-Zip before installing .7z driver packages",
            "Some AMD, Intel, and OEM drivers download as .7z archives. BSOD Analyzer "
            "uses the free 7-Zip program from 7-zip.org to open them (we do not bundle "
            "7-Zip). Offer the official download page when a .7z install is attempted.",
            "seven_zip_install_prompt",
            True,
        )

        backup_box = QtWidgets.QGroupBox("Driver backups")
        backup_lay = QtWidgets.QVBoxLayout(backup_box)
        self._cb_backup_before = QtWidgets.QCheckBox(
            "Back up current driver before install (recommended)"
        )
        self._cb_backup_before.setChecked(
            bool(self._data.get("driver_backup_before_install", True))
        )
        backup_lay.addWidget(self._cb_backup_before)
        keep_row = QtWidgets.QHBoxLayout()
        keep_row.addWidget(QtWidgets.QLabel("Keep last backups per device:"))
        self._backup_keep_spin = QtWidgets.QSpinBox()
        self._backup_keep_spin.setRange(0, 99)
        self._backup_keep_spin.setValue(int(self._data.get("driver_backup_keep_count", 3)))
        self._backup_keep_spin.setToolTip("0 disables auto-prune. Default is 3.")
        keep_row.addWidget(self._backup_keep_spin)
        keep_row.addStretch(1)
        backup_lay.addLayout(keep_row)
        self._backup_folder_label = QtWidgets.QLabel()
        self._backup_folder_label.setWordWrap(True)
        self._backup_folder_label.setObjectName("Muted")
        backup_lay.addWidget(self._backup_folder_label)
        backup_btn_row = QtWidgets.QHBoxLayout()
        self._btn_choose_backup_folder = QtWidgets.QPushButton("Choose backup folder…")
        self._btn_choose_backup_folder.clicked.connect(self._choose_backup_folder)
        self._btn_default_backup_folder = QtWidgets.QPushButton("Use default location")
        self._btn_default_backup_folder.clicked.connect(self._use_default_backup_folder)
        backup_btn_row.addWidget(self._btn_choose_backup_folder)
        backup_btn_row.addWidget(self._btn_default_backup_folder)
        backup_btn_row.addStretch(1)
        backup_lay.addLayout(backup_btn_row)
        backup_hint = QtWidgets.QLabel(
            "Backups are pnputil export folders with a manifest. Manage them from "
            "Tools → Driver backups…"
        )
        backup_hint.setWordWrap(True)
        backup_hint.setObjectName("Muted")
        backup_lay.addWidget(backup_hint)
        lay.addWidget(backup_box)
        self._pending_backup_folder = (self._data.get("driver_backup_folder") or "").strip()
        self._refresh_backup_folder_ui()

        net_box = QtWidgets.QGroupBox("Network adapter (driver scan performance)")
        net_lay = QtWidgets.QVBoxLayout(net_box)
        self._pref_network_adapter_label = QtWidgets.QLabel("")
        self._pref_network_adapter_label.setWordWrap(True)
        net_lay.addWidget(self._pref_network_adapter_label)
        self._pref_network_power_hint = QtWidgets.QLabel("")
        self._pref_network_power_hint.setWordWrap(True)
        self._pref_network_power_hint.setObjectName("Muted")
        net_lay.addWidget(self._pref_network_power_hint)
        self._pref_network_keep_awake = QtWidgets.QCheckBox("Keep active adapter awake")
        self._pref_network_keep_awake.setToolTip(
            "Disables “Allow the computer to turn off this device to save power” on the "
            "adapter carrying your current internet connection. Helps long Microsoft "
            "Catalog searches stay online; only this adapter is changed."
        )
        self._pref_network_keep_awake.toggled.connect(self._on_pref_network_keep_awake_toggled)
        net_lay.addWidget(self._pref_network_keep_awake)
        net_note = QtWidgets.QLabel(
            "This is a permanent Windows power setting for the active Wi‑Fi or Ethernet "
            "adapter only — not a temporary scan boost."
        )
        net_note.setWordWrap(True)
        net_note.setObjectName("Muted")
        net_lay.addWidget(net_note)
        lay.addWidget(net_box)
        self._pref_network_adapter: dict | None = None
        self._refresh_pref_network_power_ui()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _sync_quick_check_for_install_mode(self) -> None:
        full = self._cb_full_install.isChecked()
        self._cb_quick.setEnabled(not full)
        if hasattr(self, "_btn_choose_data_dir"):
            for w in (
                self._btn_choose_data_dir,
                self._btn_recommended_data_dir,
                self._data_dir_label,
                self._data_dir_warning,
            ):
                w.setEnabled(full)
            if full:
                self._refresh_data_dir_ui()
        if full:
            self._cb_quick.setChecked(False)
            self._cb_quick.setToolTip(
                "Disabled in full install mode. Use Tools → Refresh driver database."
            )
        else:
            self._cb_quick.setToolTip("")

    def _effective_data_dir(self) -> Path:
        preview = dict(self._data)
        preview["install_mode"] = (
            "full" if self._cb_full_install.isChecked() else "portable"
        )
        preview["custom_data_dir"] = self._pending_custom_data_dir
        return settings.full_install_data_dir(preview)

    def _refresh_data_dir_ui(self) -> None:
        path = self._effective_data_dir()
        self._data_dir_label.setText(
            f"Driver index, hardware profile, and check cache:\n{path}"
        )
        warn = settings.onedrive_data_dir_warning(
            {
                **self._data,
                "install_mode": (
                    "full" if self._cb_full_install.isChecked() else "portable"
                ),
                "custom_data_dir": self._pending_custom_data_dir,
            }
        )
        if warn:
            self._data_dir_warning.setText(warn)
            self._data_dir_warning.show()
        else:
            self._data_dir_warning.hide()

    def _confirm_onedrive_data_folder(self, folder: Path) -> bool:
        reply = QtWidgets.QMessageBox.question(
            self,
            "OneDrive-synced folder",
            (
                f"This folder is under OneDrive sync:\n{folder}\n\n"
                "SQLite caches and settings can lock or corrupt when synced. "
                "Use a local folder (for example D:\\BSODAnalyzer) when you can.\n\n"
                "Use this folder anyway?"
            ),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes

    def _choose_data_dir(self) -> None:
        start = str(self._effective_data_dir())
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose full-install data folder",
            start,
        )
        if not chosen:
            return
        resolved, err = settings.resolve_custom_data_dir(chosen)
        if err or resolved is None:
            QtWidgets.QMessageBox.warning(self, "Data folder", err or "Invalid folder.")
            return
        if settings.is_onedrive_synced_path(resolved):
            if not self._confirm_onedrive_data_folder(resolved):
                return
        self._pending_custom_data_dir = str(resolved)
        self._refresh_data_dir_ui()

    def _use_recommended_data_dir(self) -> None:
        self._pending_custom_data_dir = str(settings.default_full_install_data_dir())
        self._refresh_data_dir_ui()

    def _refresh_backup_folder_ui(self) -> None:
        effective = drvbackup.default_backup_root(self._data)
        if self._pending_backup_folder:
            effective = os.path.abspath(self._pending_backup_folder)
        self._backup_folder_label.setText(f"Backup folder: {effective}")

    def _choose_backup_folder(self) -> None:
        start = drvbackup.default_backup_root(self._data)
        if self._pending_backup_folder:
            start = self._pending_backup_folder
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose driver backup folder",
            start,
        )
        if chosen:
            self._pending_backup_folder = chosen
            self._refresh_backup_folder_ui()

    def _use_default_backup_folder(self) -> None:
        self._pending_backup_folder = ""
        self._refresh_backup_folder_ui()

    def _refresh_pref_network_power_ui(self) -> None:
        import system_network_power as snp

        self._pref_network_adapter = snp.query_active_network_adapter()
        adapter = self._pref_network_adapter
        cb = self._pref_network_keep_awake
        cb.blockSignals(True)
        if adapter and adapter.get("PowerManagementSupported"):
            cb.setEnabled(True)
            cb.setChecked(not adapter.get("PowerSavingOn"))
        else:
            cb.setEnabled(False)
            cb.setChecked(False)
        cb.blockSignals(False)
        if adapter:
            media = (adapter.get("MediaType") or "").strip()
            kind = "Wi‑Fi" if "802.11" in media else "Ethernet"
            self._pref_network_adapter_label.setText(
                f"Active connection: {adapter.get('InterfaceDescription') or adapter.get('Name')} ({kind})"
            )
        else:
            self._pref_network_adapter_label.setText(
                "Active connection: none detected (connect Wi‑Fi or Ethernet)."
            )
        self._pref_network_power_hint.setText(snp.adapter_power_summary(adapter))

    def _on_pref_network_keep_awake_toggled(self, checked: bool) -> None:
        adapter = self._pref_network_adapter or {}
        name = (adapter.get("Name") or "").strip()
        if not name:
            return
        import system_network_power as snp

        ok, msg = snp.set_active_adapter_allow_turn_off(
            name,
            allow_turn_off=not checked,
        )
        if not ok:
            QtWidgets.QMessageBox.warning(self, "Network adapter power", msg)
        self._refresh_pref_network_power_ui()

    def result_settings(self) -> dict:
        out = dict(self._data)
        out["quick_check_mode"] = self._cb_quick.isChecked()
        out["oem_session_cache"] = self._cb_oem_cache.isChecked()
        out["catalog_include_preview"] = self._cb_catalog_preview.isChecked()
        out["catalog_auto_refresh_prompt"] = self._cb_catalog_refresh_prompt.isChecked()
        out["default_include_common_devices"] = self._cb_include_common.isChecked()
        out["remember_driver_firmware_checks"] = self._cb_remember.isChecked()
        out["show_crash_timeline"] = self._cb_timeline.isChecked()
        out["show_reliability_events"] = self._cb_reliability.isChecked()
        out["powershell7_upgrade_prompt"] = self._cb_ps7_prompt.isChecked()
        out["cdb_online_install_prompt"] = self._cb_cdb_prompt.isChecked()
        out["seven_zip_install_prompt"] = self._cb_7z_prompt.isChecked()
        out["driver_backup_before_install"] = self._cb_backup_before.isChecked()
        out["driver_backup_keep_count"] = int(self._backup_keep_spin.value())
        out["driver_backup_folder"] = self._pending_backup_folder.strip()
        prev_custom = settings.normalize_custom_data_dir(self._data.get("custom_data_dir") or "")
        pending = settings.normalize_custom_data_dir(self._pending_custom_data_dir or "")
        if self._cb_full_install.isChecked():
            out = settings.apply_full_install_defaults(out)
            out["custom_data_dir"] = pending
            if pending != prev_custom:
                new_resolved, new_err = settings.resolve_custom_data_dir(pending or "")
                if (
                    new_resolved is not None
                    and settings.is_onedrive_synced_path(new_resolved)
                    and not self._confirm_onedrive_data_folder(new_resolved)
                ):
                    out["custom_data_dir"] = prev_custom
                else:
                    old_dir = settings.full_install_data_dir(self._data)
                    new_dir = settings.full_install_data_dir(out)
                    ok, msg = settings.migrate_full_install_data(old_dir, new_dir)
                    if not ok:
                        QtWidgets.QMessageBox.warning(
                            self,
                            "Data folder",
                            f"Could not relocate data:\n{msg}",
                        )
                        out["custom_data_dir"] = prev_custom
                    elif msg and ("Relocated" in msg or "Skipped" in msg):
                        QtWidgets.QMessageBox.information(
                            self,
                            "Data folder",
                            msg,
                        )
        else:
            out = settings.apply_portable_defaults(out)
            out["custom_data_dir"] = ""
            settings.remove_full_install_settings_file(dict(self._data))
            settings.clear_full_install_caches()
        return out


class InstallModeChoiceDialog(QtWidgets.QDialog):
    """First-launch choice: full install (cached) vs portable (no driver cache)."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("How will you use BSOD Analyzer?")
        self.setMinimumWidth(540)
        self._choice: str = "portable"
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(12)

        title = QtWidgets.QLabel("What are you using this tool for?")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        lay.addWidget(title)

        intro = QtWidgets.QLabel(
            "This is the same program either way (one .exe, crash debugger built in). "
            "Pick the workflow that matches your goal — you can change it later in Settings."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(intro)

        self._btn_full = QtWidgets.QRadioButton(
            "Full install mode — ongoing driver checks on this PC"
        )
        self._btn_portable = QtWidgets.QRadioButton(
            "Portable mode — find what is causing BSODs and crashes"
        )
        self._btn_full.setChecked(True)
        self._choice = "full"
        self._btn_full.toggled.connect(self._on_full_toggled)
        lay.addWidget(self._btn_full)

        full_body = QtWidgets.QLabel(
            "<b>Designed for:</b> checking drivers and firmware over several sessions and "
            "keeping the PC in good shape.<br><br>"
            "• Saves your device list and check results (survives reboots)<br>"
            "• Drivers tab stays ready without rescanning every time<br>"
            "• Cache age on the Drivers tab — refresh the list or driver database when stale<br>"
            "• Data lives in your Windows user folder (not inside the .exe folder)"
        )
        full_body.setWordWrap(True)
        full_body.setTextFormat(QtCore.Qt.RichText)
        full_body.setObjectName("Muted")
        full_body.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(full_body)

        lay.addSpacing(8)
        lay.addWidget(self._btn_portable)

        port_body = QtWidgets.QLabel(
            "<b>Designed for:</b> troubleshooting — figuring out <i>why</i> the system "
            "blue-screens or crashes, then fixing the cause (often one focused visit).<br><br>"
            "• Run Analysis and read crash details first<br>"
            "• Does <b>not</b> save driver lists between runs — fresh scan when you check drivers<br>"
            "• Leaves almost nothing on the PC (good for a USB stick or someone else's PC)"
        )
        port_body.setWordWrap(True)
        port_body.setTextFormat(QtCore.Qt.RichText)
        port_body.setObjectName("Muted")
        port_body.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(port_body)

        note = QtWidgets.QLabel(
            "You can change this later under Settings → Change install mode…"
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _on_full_toggled(self, checked: bool) -> None:
        self._choice = "full" if checked else "portable"

    def choice_is_full(self) -> bool:
        return self._btn_full.isChecked()


class FirstRunTipsDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to BSOD Analyzer")
        self.setMinimumWidth(480)
        lay = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Quick start")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        lay.addWidget(title)
        tips = QtWidgets.QLabel(
            "<ul>"
            "<li><b>Run as Administrator</b> when possible — needed for full event logs, "
            "memory dump settings, and some driver checks.</li>"
            "<li><b>Run Analysis</b> after a crash to read minidumps and the event log.</li>"
            "<li><b>Drivers tab</b> — one sorted list (crash suspects red, known updates yellow); "
            "optional <i>Install</i> only when you click — never automatic.</li>"
            "<li><b>Firmware tab</b> — same layout; download-only (never flashes BIOS/SSD).</li>"
            "<li><b>Tools → Clean up crash logs and dumps</b> — guided cleanup when disk is full.</li>"
            "<li><b>Portable mode (default)</b> — USB or any PC: fresh hardware scan each "
            "session, driver/firmware Search when you need updates (~5 min full check).</li>"
            "<li><b>Full install</b> (optional, Settings → Change install mode) — saves "
            "device list and check history on this PC between sessions.</li>"
            "<li><b>Settings → Preferences</b> — Quick check, reliability events, and related options.</li>"
            "<li><b>File → Save analysis baseline</b> before driver work; use "
            "<b>Compare to saved baseline</b> after installing fixes.</li>"
            "<li><b>Help → Release notes</b> for version history.</li>"
            "</ul>"
        )
        tips.setWordWrap(True)
        tips.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(tips)
        self._dont_show = QtWidgets.QCheckBox("Don't show this again")
        self._dont_show.setChecked(True)
        lay.addWidget(self._dont_show)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn.accepted.connect(self.accept)
        lay.addWidget(btn)

    def dont_show_again(self) -> bool:
        return self._dont_show.isChecked()


class InstallDriverConfirmDialog(QtWidgets.QDialog):
    """Install confirmation with backup and restore-point options."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        *,
        summary: str,
        settings: dict,
        allow_backup: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Install driver")
        self.setMinimumWidth(480)
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(summary)
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self._cb_backup = QtWidgets.QCheckBox("Back up current driver before install")
        self._cb_backup.setChecked(
            allow_backup and drvbackup.backup_before_install_default(settings)
        )
        self._cb_backup.setEnabled(allow_backup)
        if not allow_backup:
            self._cb_backup.setToolTip(
                "Platform chipset packages install from the downloaded INF — "
                "there is no single Device Manager row to back up."
            )
        lay.addWidget(self._cb_backup)
        self._cb_restore = QtWidgets.QCheckBox("Create a system restore point first")
        self._cb_restore.setChecked(False)
        lay.addWidget(self._cb_restore)
        note = QtWidgets.QLabel(
            "Administrator rights are required. BSOD Analyzer never installs unless you confirm."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Yes | QtWidgets.QDialogButtonBox.No
        )
        buttons.button(QtWidgets.QDialogButtonBox.Yes).setText("Install")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def choices(self) -> dict:
        return {
            "backup_before": self._cb_backup.isChecked(),
            "create_restore_point": self._cb_restore.isChecked(),
        }


class DriverBackupsDialog(QtWidgets.QDialog):
    """Browse, restore, export, or remove saved driver backups."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        *,
        settings: dict,
        on_restore: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._settings = dict(settings)
        self._on_restore = on_restore
        self.setWindowTitle("Driver backups")
        self.setMinimumSize(720, 360)
        lay = QtWidgets.QVBoxLayout(self)
        root = drvbackup.default_backup_root(self._settings)
        hint = QtWidgets.QLabel(
            f"Saved under:\n{root}\n\nSelect a backup, then Restore, Open folder, Export zip, or Remove."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)
        self._table = QtWidgets.QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Device", "Driver version", "Backed up", "Folder"]
        )
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self._table, 1)
        btn_row = QtWidgets.QHBoxLayout()
        self._btn_restore = QtWidgets.QPushButton("Restore")
        self._btn_open = QtWidgets.QPushButton("Open folder")
        self._btn_export = QtWidgets.QPushButton("Export zip…")
        self._btn_remove = QtWidgets.QPushButton("Remove")
        self._btn_refresh = QtWidgets.QPushButton("Refresh")
        for btn in (
            self._btn_restore,
            self._btn_open,
            self._btn_export,
            self._btn_remove,
            self._btn_refresh,
        ):
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        close_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        btn_row.addWidget(close_box)
        lay.addLayout(btn_row)
        self._btn_restore.clicked.connect(self._restore_selected)
        self._btn_open.clicked.connect(self._open_selected)
        self._btn_export.clicked.connect(self._export_selected)
        self._btn_remove.clicked.connect(self._remove_selected)
        self._btn_refresh.clicked.connect(self._reload)
        self._table.itemSelectionChanged.connect(self._sync_buttons)
        self._records: list[dict] = []
        self._reload()
        self._sync_buttons()

    def _reload(self) -> None:
        self._records = drvbackup.list_driver_backups(
            drvbackup.default_backup_root(self._settings)
        )
        self._table.setRowCount(len(self._records))
        for row, rec in enumerate(self._records):
            device = rec.get("device_name") or "—"
            version = rec.get("driver_version") or "—"
            when = rec.get("backed_up_at_local") or rec.get("backed_up_at") or "—"
            path = rec.get("path") or ""
            for col, text in enumerate((device, version, when, path)):
                self._table.setItem(row, col, QtWidgets.QTableWidgetItem(str(text)))
        self._sync_buttons()

    def _selected_record(self) -> dict | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def _sync_buttons(self) -> None:
        has = self._selected_record() is not None
        for btn in (
            self._btn_restore,
            self._btn_open,
            self._btn_export,
            self._btn_remove,
        ):
            btn.setEnabled(has)

    def _restore_selected(self) -> None:
        rec = self._selected_record()
        if not rec:
            return
        path = rec.get("path") or ""
        device = rec.get("device_name") or "device"
        reply = QtWidgets.QMessageBox.question(
            self,
            "Restore driver",
            f"Reinstall the backed-up driver for:\n\n{device}\n\n{path}\n\nContinue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._on_restore(path)
        self.accept()

    def _open_selected(self) -> None:
        rec = self._selected_record()
        if not rec:
            return
        path = rec.get("path") or ""
        if path and os.path.isdir(path):
            os.startfile(path)

    def _export_selected(self) -> None:
        rec = self._selected_record()
        if not rec:
            return
        path = rec.get("path") or ""
        device = (rec.get("device_name") or "driver").replace(" ", "_")[:40]
        stamp = (rec.get("backed_up_at_local") or "backup").replace(":", "").replace(" ", "_")
        default = f"{device}_{stamp}.zip"
        dest, _flt = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export backup as zip",
            default,
            "Zip archives (*.zip)",
        )
        if not dest:
            return
        ok, msg = drvbackup.export_backup_zip(path, dest)
        if ok:
            QtWidgets.QMessageBox.information(self, "Export backup", msg)
        else:
            QtWidgets.QMessageBox.warning(self, "Export backup", msg)

    def _remove_selected(self) -> None:
        rec = self._selected_record()
        if not rec:
            return
        path = rec.get("path") or ""
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Remove backup",
            f"Delete this backup folder permanently?\n\n{path}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        ok, msg = drvbackup.remove_driver_backup(path)
        if ok:
            self._reload()
            QtWidgets.QMessageBox.information(self, "Remove backup", msg)
        else:
            QtWidgets.QMessageBox.warning(self, "Remove backup", msg)
