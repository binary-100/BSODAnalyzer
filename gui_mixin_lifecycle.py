"""File-menu snapshots, shutdown, closeEvent, background task teardown."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiLifecycleMixin:
    def _copy_diagnosis(self) -> None:
        if not self._last_model:
            QtWidgets.QMessageBox.information(
                self, "Copy diagnosis", "Run Analysis first to build a diagnosis summary."
            )
            return
        text = app_set.format_diagnosis_clipboard(self._last_model)
        QtWidgets.QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Diagnosis copied to clipboard.")

    def _save_snapshot(self) -> None:
        if not self._last_model:
            QtWidgets.QMessageBox.information(
                self,
                "Save analysis baseline",
                "Run Analysis first, then save a baseline.\n\n"
                "Baselines store a compact summary (likely driver, crashes, severity)—"
                "use Compare to saved baseline after driver updates or new crashes.",
            )
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save analysis baseline (summary for later comparison)",
            "BSODAnalyzer_baseline.json",
            "Baseline JSON (*.json);;All files (*.*)",
        )
        if path:
            app_set.save_snapshot(self._last_model, path)
            self._last_snapshot_path = path
            self.statusBar().showMessage(f"Analysis baseline saved: {path}")

    def _compare_snapshot(self) -> None:
        if not self._last_model:
            QtWidgets.QMessageBox.information(
                self,
                "Compare to saved baseline",
                "Run Analysis first so there is a current result to compare against a "
                "baseline you saved earlier.",
            )
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open saved baseline to compare with current analysis",
            self._last_snapshot_path or "",
            "Baseline JSON (*.json);;All files (*.*)",
        )
        if not path:
            return
        old = app_set.load_snapshot(path)
        if not old:
            QtWidgets.QMessageBox.warning(
                self, "Compare to saved baseline", "Could not read that baseline file."
            )
            return
        new = app_set.snapshot_from_model(self._last_model)
        lines = app_set.compare_snapshots(old, new)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Baseline comparison")
        dlg.resize(520, 360)
        lay = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setReadOnly(True)
        te.setPlainText("\n".join(lines))
        lay.addWidget(te)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def _compare_catalog_exports(self) -> None:
        """Diff two catalog scan JSON exports (Tools menu)."""
        import json

        import catalog_export as cexp

        path_a, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "First catalog export (A)",
            "",
            "Catalog JSON (*.json);;All files (*.*)",
        )
        if not path_a:
            return
        path_b, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Second catalog export (B)",
            path_a,
            "Catalog JSON (*.json);;All files (*.*)",
        )
        if not path_b:
            return
        try:
            payload_a = json.loads(Path(path_a).read_text(encoding="utf-8"))
            payload_b = json.loads(Path(path_b).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Compare catalog exports",
                f"Could not read one of the export files:\n{exc}",
            )
            return
        text = cexp.compare_catalog_exports(payload_a, payload_b)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Catalog export comparison")
        dlg.resize(640, 420)
        lay = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        lay.addWidget(te)
        btn_row = QtWidgets.QHBoxLayout()
        copy_btn = QtWidgets.QPushButton("Copy to clipboard")
        copy_btn.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(te.toPlainText())
        )
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        ok_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        ok_box.accepted.connect(dlg.accept)
        btn_row.addWidget(ok_box)
        lay.addLayout(btn_row)
        dlg.exec()

    def _clear_check_history(self) -> None:
        app_set.clear_check_cache()
        self.statusBar().showMessage(
            "Cleared remembered driver/firmware check results (driver_index.sqlite)."
        )

    def _running_background_tasks(self) -> list[str]:
        active: list[str] = []
        for attr, label in self._BACKGROUND_THREAD_LABELS:
            th = getattr(self, attr, None)
            if th is not None and th.isRunning():
                active.append(label)
        if self._catalog_refresh_job.is_running():
            active.append("catalog database refresh")
        if self._catalog_export_job.is_running():
            active.append("catalog export")
        return active

    def _stop_deferred_timers(self) -> None:
        self._summary_refresh_timer.stop()
        self._drv_filter_debounce.stop()
        self._fw_filter_debounce.stop()

    def _disconnect_analysis_worker(self) -> None:
        worker = self._worker
        if worker is None:
            return
        relay = getattr(self, "_signal_relay", None)
        if relay is not None:
            for sig, slot in (
                (worker.progress, relay.analysis_progress),
                (worker.finished, relay.analysis_finished),
                (worker.failed, relay.analysis_failed),
            ):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        for sig, slot in (
            (worker.progress, self._on_progress),
            (worker.finished, self._on_finished),
            (worker.failed, self._on_failed),
        ):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        active = self._running_background_tasks()
        if active:
            label = ", ".join(active)
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle("Close while tasks are running?")
            box.setText(
                f"The following task(s) are still running:\n{label}\n\n"
                "Wait up to 15 seconds for them to finish, or close anyway "
                "(in-progress checks may stop)."
            )
            btn_wait = box.addButton("Wait and close", QtWidgets.QMessageBox.AcceptRole)
            btn_now = box.addButton("Close now", QtWidgets.QMessageBox.DestructiveRole)
            btn_cancel = box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(btn_wait)
            box.exec()
            clicked = box.clickedButton()
            if clicked is None or clicked == btn_cancel:
                event.ignore()
                return
            wait_long = clicked == btn_wait
        else:
            wait_long = False
        export_wait_ms = 15000 if wait_long else 12000
        if self._catalog_export_job.is_running() or self._unified_export_dest_dir:
            self._drain_pending_catalog_export(timeout_ms=export_wait_ms)
        self._shutting_down = True
        self._pending_needs_config = False
        self._pending_crash_module_check = None
        self._drv_manual_queue.clear()
        self._stop_deferred_timers()
        if hasattr(self, "_cancel_drv_table_sync"):
            self._cancel_drv_table_sync()
        self._task_progress_depth = 0
        self._task_progress_frame.setVisible(False)
        self._disconnect_analysis_worker()
        gui_workers.stop_jobs(
            self._catalog_refresh_job,
            self._catalog_export_job,
        )
        wait_ms = 15000 if wait_long else 4000
        for attr, _label in self._BACKGROUND_THREAD_LABELS:
            th = getattr(self, attr, None)
            if th is not None and th.isRunning():
                if wait_long:
                    self.statusBar().showMessage("Waiting for background tasks…")
                th.quit()
                th.wait(wait_ms)
        super().closeEvent(event)
