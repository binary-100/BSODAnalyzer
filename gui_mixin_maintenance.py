"""Session log hooks and full-install maintenance report/history."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiMaintenanceMixin:
    def _record_maintenance_activity(self, label: str, detail: str = "") -> None:
        """Update last-maintenance timestamp after a user-initiated driver cache refresh."""
        if not app_set.is_full_install_mode(self._settings):
            return
        app_set.touch_last_maintenance()
        self._settings = app_set.load_settings()
        mlog.append_event("maintenance_run", label, detail=detail or label)
        self._update_drivers_tab_cache_status()

    def _session_log_begin(self, kind: str, summary: str, token_attr: str) -> None:
        try:
            import session_log as slog

            token = slog.begin(kind, summary)
            setattr(self, token_attr, token)
        except Exception:
            pass  # optional session_log; telemetry only

    def _session_log_end(
        self,
        kind: str,
        summary: str,
        token_attr: str,
        *,
        status: str = "ok",
        extra: dict | None = None,
    ) -> int | None:
        try:
            import session_log as slog

            token = getattr(self, token_attr, None)
            elapsed_ms = slog.end(token, kind, summary, status=status, extra=extra)
            setattr(self, token_attr, None)
            return elapsed_ms
        except Exception:
            return None

    def _session_log_progress(self, kind: str, message: str, **extra) -> None:
        try:
            import session_log as slog

            slog.progress(kind, message, **extra)
        except Exception:
            pass  # optional session_log; telemetry only

    def export_maintenance_report(self) -> None:
        if not app_set.is_full_install_mode(self._settings):
            QtWidgets.QMessageBox.information(
                self,
                "Full install report",
                "Full install reports are available only in full install mode.",
            )
            return
        lines = self._build_maintenance_report_lines()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export full install report",
            "BSODAnalyzer_full_install_report.txt",
            "Text files (*.txt);;All files (*.*)",
        )
        if not path:
            return
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            QtWidgets.QMessageBox.information(
                self, "Full install report", f"Report saved to:\n{path}"
            )
        except OSError as e:
            QtWidgets.QMessageBox.warning(self, "Full install report", str(e))

    def _build_maintenance_report_lines(self) -> list[str]:
        lines = [
            "BSOD Analyzer — Full install report",
            "=" * 50,
            "",
            app_set.last_maintenance_summary(self._settings),
            ccat.catalog_age_summary(),
        ]
        payload = hwcache.load_cache_payload()
        lines.append(hwcache.cache_age_summary(payload) if payload else "Device list: not cached")
        stor = hwcache.cache_storage_summary()
        if stor.get("bytes"):
            lines.append(f"Device list cache file: {stor['bytes']:,} bytes (gzip in SQLite)")
        lines.append("")
        prof = self._hardware_profile or {}
        bio = prof.get("bios_driver_info") or {}
        lines.append(f"Devices in saved list: {len(bio.get('all_drivers') or [])}")
        outdated = sum(
            1 for d in self._drv_unified_cache if d.get("_check_status") == "newer"
        )
        lines.append(f"Known driver updates in cache: {outdated}")
        rel = (self._last_model or {}).get("reliability_ctx") or {}
        stab = rel.get("stability_index")
        if stab is not None:
            lines.append(f"Stability index (last analysis): {stab} / 10")
        lines.append("")
        lines.append("Recent activity")
        lines.append("-" * 50)
        lines.append(mlog.format_events_plain(mlog.read_events(30)))
        lines.append("")
        try:
            import session_log as slog

            lines.append("Session timing log")
            lines.append("-" * 50)
            lines.append(f"File: {slog.log_path()}")
            lines.append(slog.format_events_plain(slog.read_events(40)))
        except Exception:
            pass  # optional session_log in maintenance export

        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return lines

    def _show_maintenance_history(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Activity history")
        dlg.resize(640, 480)
        lay = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setReadOnly(True)
        parts = [
            "Maintenance events (full install)",
            "=" * 50,
            mlog.format_events_plain(mlog.read_events(80)),
            "",
        ]
        try:
            import session_log as slog

            parts.extend([
                "Session timing log (progress + elapsed times)",
                "=" * 50,
                f"File: {slog.log_path()}",
                "",
                slog.format_events_plain(slog.read_events(120)),
            ])
        except Exception:
            pass  # optional session_log in activity history dialog

        te.setPlainText("\n".join(parts))
        lay.addWidget(te)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()
