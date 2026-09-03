"""Advanced tab — minidump picker, stack summary, re-analyze selected dump."""

from __future__ import annotations

import os

import gui_theme as theme

from gui_app_context import *  # noqa: F403


class GuiMinidumpMixin:
    def _build_minidump_panel(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        card = apply_styled_frame(QtWidgets.QFrame(), "Card")
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)
        title = QtWidgets.QLabel("Minidump analysis")
        title.setObjectName("CardTitle")
        lay.addWidget(title)
        hint = QtWidgets.QLabel(
            "Pick a crash dump to inspect its call stack. The first non-kernel frame "
            "is highlighted when the faulting module is ntoskrnl or another kernel name."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        self.minidump_combo = QtWidgets.QComboBox()
        self.minidump_combo.setMinimumWidth(280)
        self.minidump_combo.currentIndexChanged.connect(self._on_minidump_combo_changed)
        row.addWidget(self.minidump_combo, 1)
        self.btn_analyze_dump = QtWidgets.QPushButton("Analyze selected dump")
        self.btn_analyze_dump.clicked.connect(self._on_analyze_selected_dump)
        row.addWidget(self.btn_analyze_dump)
        self.btn_open_dump_folder = QtWidgets.QPushButton("Open dump folder")
        self.btn_open_dump_folder.clicked.connect(self._on_open_minidump_folder)
        row.addWidget(self.btn_open_dump_folder)
        lay.addLayout(row)

        self.minidump_stack_browser = QtWidgets.QTextBrowser()
        self.minidump_stack_browser.setOpenExternalLinks(False)
        self.minidump_stack_browser.setMaximumHeight(180)
        lay.addWidget(self.minidump_stack_browser)

        parent_layout.addWidget(card)
        self._minidump_analyses: dict[str, dict] = {}
        self._minidump_thread: QtCore.QThread | None = None
        self._minidump_worker: object | None = None
        self._minidump_dump_paths: list[str] = []

    def _refresh_minidump_panel(self, m: dict) -> None:
        if not hasattr(self, "minidump_combo"):
            return
        dumps = list(m.get("kernel_dumps") or [])
        windbg = dict(m.get("windbg_analysis") or {})
        self._minidump_dump_paths = []
        self.minidump_combo.blockSignals(True)
        self.minidump_combo.clear()
        if not dumps:
            self.minidump_combo.addItem("No kernel minidumps found", "")
            self.minidump_combo.setEnabled(False)
            self.btn_analyze_dump.setEnabled(False)
            self.btn_open_dump_folder.setEnabled(bool(core.MINIDUMP_DIR))
            self.minidump_stack_browser.setHtml(
                f"<p style='color:{theme.MUTED}'>Run Analysis after a BSOD, or enable memory dumps "
                "and wait for the next crash.</p>"
            )
            self.minidump_combo.blockSignals(False)
            return

        self.minidump_combo.setEnabled(True)
        self.btn_analyze_dump.setEnabled(bool(core.find_cdb()))
        self.btn_open_dump_folder.setEnabled(True)
        primary_path = ""
        for i, d in enumerate(dumps[:12]):
            path = (d.get("path") or "").strip()
            label = core.format_minidump_summary_line(d)
            self.minidump_combo.addItem(label, path)
            self._minidump_dump_paths.append(path)
            if i == 0:
                primary_path = path

        analyzed_path = (windbg.get("dump_file") or "").strip()
        if analyzed_path:
            for idx in range(self.minidump_combo.count()):
                if (self.minidump_combo.itemData(idx) or "").lower() == analyzed_path.lower():
                    self.minidump_combo.setCurrentIndex(idx)
                    primary_path = self.minidump_combo.itemData(idx) or primary_path
                    break

        if windbg and primary_path:
            key = primary_path.lower()
            self._minidump_analyses[key] = windbg

        self.minidump_combo.blockSignals(False)
        self._show_minidump_stack_for_path(self.minidump_combo.currentData() or primary_path)

    def _on_minidump_combo_changed(self, _index: int) -> None:
        path = self.minidump_combo.currentData()
        if path:
            self._show_minidump_stack_for_path(path)

    def _show_minidump_stack_for_path(self, dump_path: str) -> None:
        if not dump_path:
            self.minidump_stack_browser.clear()
            return
        analysis = self._minidump_analyses.get(dump_path.lower())
        if not analysis:
            self.minidump_stack_browser.setHtml(
                f"<p style='color:{theme.MUTED}'>Not analyzed yet — click "
                "<b>Analyze selected dump</b> (requires CDB).</p>"
            )
            return
        self.minidump_stack_browser.setHtml(self._minidump_stack_html(analysis))

    @staticmethod
    def _minidump_stack_html(analysis: dict) -> str:
        import bsod_minidump as mdump

        frames = list(analysis.get("stack_frames") or [])
        fault = (analysis.get("faulting_driver") or "").strip()
        lead = (analysis.get("actionable_stack_frame") or "").strip()
        if not lead:
            lead = mdump.first_actionable_stack_frame(frames) or ""
        headline_parts = []
        if fault:
            headline_parts.append(f"Faulting module: <b>{fault}</b>")
        if lead:
            headline_parts.append(f"Best driver lead: <b>{lead}</b>")
        elif analysis.get("kernel_stack_top"):
            headline_parts.append(
                f"Stack top is kernel-only ({analysis.get('kernel_stack_top')}) — "
                "check drivers on the Action Plan tab."
            )
        head_html = ""
        if headline_parts:
            head_html = (
                f"<p style='margin:0 0 8px 0; line-height:140%'>{'<br/>'.join(headline_parts)}</p>"
            )

        if not frames:
            return head_html + f"<p style='color:{theme.MUTED}'>No stack frames captured.</p>"

        rows = []
        for i, frame in enumerate(frames, 1):
            esc = (
                frame.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            if lead and frame == lead:
                style = f"color:{theme.ACCENT}; font-weight:600"
                note = " ← first non-kernel frame"
            elif i == 1:
                style = f"color:{theme.TEXT}"
                note = ""
            else:
                style = f"color:{theme.MUTED}"
                note = ""
            rows.append(f"<li style='{style}; margin:2px 0'>{esc}{note}</li>")
        return (
            head_html
            + f"<ol style='margin:0; padding-left:1.2em; font-family:{MONO}; font-size:12px'>"
            + "".join(rows)
            + "</ol>"
        )

    def _on_analyze_selected_dump(self) -> None:
        path = self.minidump_combo.currentData()
        if not path or not os.path.isfile(path):
            QtWidgets.QMessageBox.information(
                self, "Minidump", "Select a valid dump file first."
            )
            return
        cdb = core.find_cdb()
        if not cdb:
            QtWidgets.QMessageBox.warning(
                self,
                "Minidump",
                "CDB is not installed — use Install CDB above, then try again.",
            )
            return
        if getattr(self, "_minidump_thread", None) and self._minidump_thread.isRunning():
            self.statusBar().showMessage("Minidump analysis already running…", 4000)
            return
        self._begin_task_progress("Analyzing minidump…", maximum=0)
        from bsod_gui_workers import MinidumpAnalyzeWorker

        self._minidump_thread = QtCore.QThread()
        self._minidump_worker = MinidumpAnalyzeWorker(path, cdb)
        self._minidump_worker.moveToThread(self._minidump_thread)
        self._minidump_thread.started.connect(self._minidump_worker.run)
        self._minidump_worker.finished.connect(self._on_minidump_analyze_finished)
        self._minidump_worker.failed.connect(self._on_minidump_analyze_failed)
        self._minidump_worker.finished.connect(self._minidump_thread.quit)
        self._minidump_worker.failed.connect(self._minidump_thread.quit)
        self._minidump_thread.finished.connect(self._cleanup_minidump_thread)
        self._minidump_pending_path = path
        self._minidump_thread.start()

    @QtCore.Slot(object)
    def _on_minidump_analyze_finished(self, analysis: object) -> None:
        self._end_task_progress()
        path = getattr(self, "_minidump_pending_path", "") or ""
        if isinstance(analysis, dict) and path:
            self._minidump_analyses[path.lower()] = analysis
            self._show_minidump_stack_for_path(path)
            raw = list(analysis.get("raw") or [])
            if analysis.get("stack_frames"):
                raw.append(
                    "Stack: "
                    + " -> ".join((analysis.get("stack_frames") or [])[:6])
                )
            self.raw_text.setPlainText("\n".join(raw) if raw else "Analysis complete.")
            self.statusBar().showMessage("Minidump analysis complete.", 5000)
        else:
            QtWidgets.QMessageBox.warning(self, "Minidump", "Analysis returned no data.")

    @QtCore.Slot(str)
    def _on_minidump_analyze_failed(self, err: str) -> None:
        self._end_task_progress()
        QtWidgets.QMessageBox.warning(self, "Minidump analysis failed", err[:2000])

    def _cleanup_minidump_thread(self) -> None:
        self._minidump_thread = None
        self._minidump_worker = None

    def _on_open_minidump_folder(self) -> None:
        folder = core.MINIDUMP_DIR
        m = getattr(self, "_last_model", None) or {}
        dumps = m.get("kernel_dumps") or []
        if dumps and dumps[0].get("path"):
            folder = os.path.dirname(dumps[0]["path"]) or folder
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.information(
                self,
                "Minidump folder",
                f"Folder not found: {folder or '(unknown)'}",
            )
            return
        try:
            import bsod_runtime as rt

            rt.reveal_path_in_explorer(folder)
            self.statusBar().showMessage(f"Opened {folder}", 5000)
        except OSError as e:
            QtWidgets.QMessageBox.warning(self, "Minidump folder", str(e))
