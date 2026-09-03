"""Guided wizard to clean crash logs and dumps safely."""

from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

import log_cleanup as lc


class PreparePage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Before you clean up")
        self.setSubTitle("Follow this order so you do not lose data you still need.")
        lay = QtWidgets.QVBoxLayout(self)
        self._checks: list[QtWidgets.QCheckBox] = []
        for title, body in lc.GUIDANCE_STEPS[:3]:
            box = QtWidgets.QGroupBox(title)
            bl = QtWidgets.QVBoxLayout(box)
            cb = QtWidgets.QCheckBox("I understand")
            bl.addWidget(cb)
            desc = QtWidgets.QLabel(body)
            desc.setWordWrap(True)
            bl.addWidget(desc)
            lay.addWidget(box)
            self._checks.append(cb)
            cb.toggled.connect(self.completeChanged)
        note = QtWidgets.QLabel(
            "Optional: use File → Export report or Save analysis baseline so you have a record "
            "after dumps are removed."
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        self._cb_export = QtWidgets.QCheckBox(
            "I exported a report or saved an analysis baseline (optional)"
        )
        lay.addWidget(self._cb_export)
        lay.addStretch(1)

    def isComplete(self) -> bool:
        return all(c.isChecked() for c in self._checks)


class InventoryPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("What is on this PC")
        self.setSubTitle("Crash-related files and logs found during scan.")
        lay = QtWidgets.QVBoxLayout(self)
        self._summary = QtWidgets.QLabel("Scanning…")
        self._summary.setWordWrap(True)
        lay.addWidget(self._summary)
        self._table = QtWidgets.QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Category", "Count / size", "Location", "Notes"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self._table)
        self._admin = QtWidgets.QLabel()
        self._admin.setWordWrap(True)
        lay.addWidget(self._admin)

    def set_inventory(self, inv: dict) -> None:
        k = inv.get("kernel_minidumps") or []
        a = inv.get("app_dumps") or []
        fd = inv.get("full_dump")
        wa = inv.get("wer_report_archive") or {}
        wq = inv.get("wer_report_queue") or {}
        logs = inv.get("event_logs") or []

        parts = [
            f"Kernel minidumps: {len(k)} file(s), {inv.get('kernel_total_mb', 0)} MB total",
            f"Application crash dumps: {len(a)} file(s), {inv.get('app_total_mb', 0)} MB total",
        ]
        if fd:
            parts.append(f"Full memory dump: {fd.get('size_mb', 0)} MB")
        self._summary.setText("\n".join(parts))

        rows: list[tuple[str, str, str, str]] = []
        rows.append((
            "Kernel minidumps",
            f"{len(k)} files, {inv.get('kernel_total_mb', 0)} MB",
            inv.get("kernel_dir", ""),
            "Keep newest 1–2 unless disk space is critical" if k else "None found",
        ))
        rows.append((
            "App crash dumps",
            f"{len(a)} files, {inv.get('app_total_mb', 0)} MB",
            "; ".join(inv.get("app_dirs") or [])[:120] or "—",
            "Safe to remove old .dmp after analysis",
        ))
        if fd:
            rows.append((
                "Full memory dump",
                f"{fd.get('size_mb', 0)} MB",
                fd.get("path", ""),
                "Large — delete only if you no longer need deep analysis",
            ))
        if wa.get("exists"):
            rows.append((
                "WER ReportArchive",
                f"{wa.get('file_count', 0)} files, {wa.get('size_mb', 0)} MB",
                wa.get("path", ""),
                "Old Windows Error Reporting payloads",
            ))
        if wq.get("exists"):
            rows.append((
                "WER ReportQueue",
                f"{wq.get('file_count', 0)} files, {wq.get('size_mb', 0)} MB",
                wq.get("path", ""),
                "Pending WER reports — usually safe to clear",
            ))
        for log in logs:
            rows.append((
                f"Event log: {log.get('log_name', '?')}",
                f"{log.get('record_count', 0)} records, {log.get('size_mb', 0)} MB",
                "Windows Event Viewer",
                "Clear only if you exported a backup (advanced)",
            ))

        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self._table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))

        if inv.get("is_admin"):
            self._admin.setText(
                "Running as Administrator — kernel minidumps and event log actions are available."
            )
        elif not inv.get("can_delete_kernel"):
            self._admin.setText(
                "Not running as Administrator — you can clean app crash dumps and some WER "
                "folders. For C:\\Windows\\Minidump, close the app and use "
                "Run as administrator."
            )
        else:
            self._admin.setText("")


class OptionsPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Choose what to remove")
        self.setSubTitle("Recommended defaults keep recent dumps and avoid touching event logs.")
        lay = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        il = QtWidgets.QVBoxLayout(inner)

        dump_box = QtWidgets.QGroupBox("Crash dump files (recommended)")
        dl = QtWidgets.QVBoxLayout(dump_box)
        self._cb_kernel = QtWidgets.QCheckBox("Delete older kernel minidumps")
        self._cb_kernel.setChecked(True)
        dl.addWidget(self._cb_kernel)
        krow = QtWidgets.QHBoxLayout()
        krow.addWidget(QtWidgets.QLabel("Keep newest:"))
        self._kernel_keep = QtWidgets.QSpinBox()
        self._kernel_keep.setRange(0, 20)
        self._kernel_keep.setValue(2)
        krow.addWidget(self._kernel_keep)
        krow.addWidget(QtWidgets.QLabel("file(s)"))
        krow.addStretch(1)
        dl.addLayout(krow)
        self._cb_app = QtWidgets.QCheckBox("Delete older application crash dumps (.dmp in CrashDumps)")
        self._cb_app.setChecked(True)
        dl.addWidget(self._cb_app)
        arow = QtWidgets.QHBoxLayout()
        arow.addWidget(QtWidgets.QLabel("Keep newest:"))
        self._app_keep = QtWidgets.QSpinBox()
        self._app_keep.setRange(0, 20)
        self._app_keep.setValue(1)
        arow.addWidget(self._app_keep)
        arow.addStretch(1)
        dl.addLayout(arow)
        self._cb_full = QtWidgets.QCheckBox("Delete full memory dump (C:\\Windows\\MEMORY.DMP)")
        self._cb_full.setChecked(False)
        dl.addWidget(self._cb_full)
        il.addWidget(dump_box)

        wer_box = QtWidgets.QGroupBox("Windows Error Reporting folders (optional)")
        wl = QtWidgets.QVBoxLayout(wer_box)
        self._cb_wer_arch = QtWidgets.QCheckBox("Clear WER ReportArchive (old report files)")
        self._cb_wer_queue = QtWidgets.QCheckBox("Clear WER ReportQueue (pending queue)")
        self._cb_wer_temp = QtWidgets.QCheckBox("Clear WER Temp")
        wl.addWidget(self._cb_wer_arch)
        wl.addWidget(self._cb_wer_queue)
        wl.addWidget(self._cb_wer_temp)
        il.addWidget(wer_box)

        log_box = QtWidgets.QGroupBox("Event logs (advanced — destructive)")
        ll = QtWidgets.QVBoxLayout(log_box)
        warn = QtWidgets.QLabel(
            "Clearing logs removes BSOD and app crash history from Event Viewer. "
            "Export a backup .evtx first if you might need it later."
        )
        warn.setWordWrap(True)
        ll.addWidget(warn)
        self._cb_sys_log = QtWidgets.QCheckBox("Clear System log (after export below)")
        self._cb_app_log = QtWidgets.QCheckBox("Clear Application log (after export below)")
        ll.addWidget(self._cb_sys_log)
        self._sys_export = QtWidgets.QLineEdit()
        self._sys_export.setPlaceholderText("Optional: path for System log backup .evtx")
        ll.addWidget(self._sys_export)
        btn_sys = QtWidgets.QPushButton("Browse…")
        btn_sys.clicked.connect(lambda: self._browse_export(self._sys_export))
        ll.addWidget(btn_sys)
        ll.addWidget(self._cb_app_log)
        self._app_export = QtWidgets.QLineEdit()
        self._app_export.setPlaceholderText("Optional: path for Application log backup .evtx")
        ll.addWidget(self._app_export)
        btn_app = QtWidgets.QPushButton("Browse…")
        btn_app.clicked.connect(lambda: self._browse_export(self._app_export))
        ll.addWidget(btn_app)
        il.addWidget(log_box)

        il.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll)
        self._inv: dict | None = None

    def apply_inventory(self, inv: dict) -> None:
        self._inv = inv
        can_k = bool(inv.get("can_delete_kernel"))
        self._cb_kernel.setEnabled(can_k and bool(inv.get("kernel_minidumps")))
        if not can_k and inv.get("kernel_minidumps"):
            self._cb_kernel.setChecked(False)
            self._cb_kernel.setToolTip("Run the app as Administrator to delete kernel minidumps.")
        has_full = bool(inv.get("full_dump"))
        self._cb_full.setEnabled(has_full and bool(inv.get("can_delete_full_dump")))
        if not has_full:
            self._cb_full.setChecked(False)
        wa = inv.get("wer_report_archive") or {}
        wq = inv.get("wer_report_queue") or {}
        wt = inv.get("wer_temp") or {}
        self._cb_wer_arch.setEnabled(wa.get("exists", False))
        self._cb_wer_queue.setEnabled(wq.get("exists", False))
        self._cb_wer_temp.setEnabled(wt.get("exists", False))

    def _browse_export(self, line: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save event log export",
            "System_backup.evtx",
            "Event log (*.evtx);;All files (*.*)",
        )
        if path:
            line.setText(path)

    def options_dict(self) -> dict:
        return {
            "delete_older_kernel": self._cb_kernel.isChecked(),
            "kernel_keep": self._kernel_keep.value(),
            "delete_older_app": self._cb_app.isChecked(),
            "app_keep": self._app_keep.value(),
            "delete_full_dump": self._cb_full.isChecked(),
            "delete_wer_archive": self._cb_wer_arch.isChecked(),
            "delete_wer_queue": self._cb_wer_queue.isChecked(),
            "delete_wer_temp": self._cb_wer_temp.isChecked(),
            "clear_system_log": self._cb_sys_log.isChecked(),
            "clear_application_log": self._cb_app_log.isChecked(),
            "export_system_log_path": self._sys_export.text().strip(),
            "export_application_log_path": self._app_export.text().strip(),
        }


class ConfirmPage(QtWidgets.QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Confirm")
        self.setSubTitle("Review what will be deleted or cleared.")
        lay = QtWidgets.QVBoxLayout(self)
        self._text = QtWidgets.QLabel()
        self._text.setWordWrap(True)
        lay.addWidget(self._text)
        self._list = QtWidgets.QListWidget()
        lay.addWidget(self._list)

    def set_plan(self, plan: list[dict], summary: dict) -> None:
        self._text.setText(
            f"{summary.get('item_count', 0)} action(s); "
            f"approximately {summary.get('freed_mb', 0)} MB from dump/WER files."
        )
        self._list.clear()
        for item in plan:
            if item.get("event_log"):
                extra = ""
                if item.get("export_path"):
                    extra = f" → export to {item['export_path']}"
                self._list.addItem(
                    f"{item['category']}: {item['detail']}{extra}"
                )
            elif item.get("is_tree"):
                self._list.addItem(
                    f"{item['category']}: {item['path']} (~{item.get('size_mb', 0)} MB)"
                )
            else:
                self._list.addItem(
                    f"{item['category']}: {item.get('detail', '')} "
                    f"({item.get('size_mb', 0)} MB)"
                )


class LogCleanupWizard(QtWidgets.QWizard):
    finished_cleanup = QtCore.Signal(dict)

    def __init__(self, parent: QtWidgets.QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Clean up crash logs and dumps")
        self.setMinimumSize(640, 480)
        self._inventory: dict = {}
        self._plan: list[dict] = []

        self._prep = PreparePage()
        self._inv = InventoryPage()
        self._opt = OptionsPage()
        self._confirm = ConfirmPage()

        self.addPage(self._prep)
        self.addPage(self._inv)
        self.addPage(self._opt)
        self.addPage(self._confirm)

        self.setPage(1, self._inv)
        self.setPage(2, self._opt)
        self.setPage(3, self._confirm)
        self.setOption(QtWidgets.QWizard.WizardOption.NoCancelButtonOnLastPage, False)
        self.setButtonText(QtWidgets.QWizard.WizardButton.FinishButton, "Run cleanup")

        self.currentIdChanged.connect(self._on_page)

    def _on_page(self, page_id: int) -> None:
        if page_id == 1 and not self._inventory:
            self._inventory = lc.gather_cleanup_inventory()
            self._inv.set_inventory(self._inventory)
        elif page_id == 2:
            if self._inventory:
                self._opt.apply_inventory(self._inventory)
        elif page_id == 3:
            opts = self._opt.options_dict()
            if opts.get("clear_system_log") or opts.get("clear_application_log"):
                if not lc.is_user_admin():
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Administrator required",
                        "Clearing event logs requires running BSOD Analyzer as Administrator.",
                    )
            self._plan = lc.build_cleanup_plan(self._inventory, opts)
            if not self._plan:
                self._confirm.set_plan([], {"item_count": 0, "freed_mb": 0})
                return
            if opts.get("clear_system_log") and not opts.get("export_system_log_path"):
                r = QtWidgets.QMessageBox.question(
                    self,
                    "No System log backup",
                    "You chose to clear the System log without exporting a backup. "
                    "BSOD history in Event Viewer will be lost. Continue?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                )
                if r != QtWidgets.QMessageBox.StandardButton.Yes:
                    self._opt._cb_sys_log.setChecked(False)
                    self._plan = lc.build_cleanup_plan(self._inventory, self._opt.options_dict())
            self._confirm.set_plan(self._plan, lc.plan_summary(self._plan))

    def accept(self) -> None:
        if not self._plan:
            QtWidgets.QMessageBox.information(
                self, "Nothing selected", "Choose at least one cleanup action on the previous page."
            )
            return
        r = QtWidgets.QMessageBox.warning(
            self,
            "Final confirmation",
            "Delete/clear the selected items now? This cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if r != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        result = lc.execute_cleanup_plan(self._plan)
        msg_lines = [
            f"Removed or cleared {result.get('deleted_files', 0)} file(s)/folder(s).",
            f"Approximately {result.get('freed_mb', 0)} MB from dumps/WER.",
        ]
        for act in result.get("actions") or []:
            msg_lines.append(f"• {act}")
        if result.get("errors"):
            msg_lines.append("")
            msg_lines.append("Errors:")
            for err in result["errors"][:8]:
                msg_lines.append(f"• {err}")
        QtWidgets.QMessageBox.information(self, "Cleanup finished", "\n".join(msg_lines))
        self.finished_cleanup.emit(result)
        super().accept()
