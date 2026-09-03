"""Action Plan tab — step rows with inline repair buttons."""

from __future__ import annotations

import action_plan_ui as apui
import gui_theme as theme
import log_cleanup

from gui_app_context import *  # noqa: F403

_ACTION_BTN_MIN_WIDTH = 196
_ACTION_BTN_MIN_HEIGHT = 34


class GuiActionPlanMixin:
    _ADMIN_HEALTH_KINDS = frozenset({"sfc", "dism", "chkdsk"})

    def _build_action_plan_step_host(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        self.action_plan_headline = QtWidgets.QLabel("")
        self.action_plan_headline.setWordWrap(True)
        self.action_plan_headline.setObjectName("SectionHeading")
        self.action_plan_headline.hide()
        parent_layout.addWidget(self.action_plan_headline)

        self.action_plan_context = QtWidgets.QLabel("")
        self.action_plan_context.setWordWrap(True)
        self.action_plan_context.setObjectName("Muted")
        parent_layout.addWidget(self.action_plan_context)

        self.action_plan_scroll = QtWidgets.QScrollArea()
        self.action_plan_scroll.setWidgetResizable(True)
        self.action_plan_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.action_plan_steps_host = QtWidgets.QWidget()
        self.action_plan_steps_layout = QtWidgets.QVBoxLayout(self.action_plan_steps_host)
        self.action_plan_steps_layout.setContentsMargins(0, 0, 0, 0)
        self.action_plan_steps_layout.setSpacing(6)
        self.action_plan_steps_layout.addStretch(1)
        self.action_plan_scroll.setWidget(self.action_plan_steps_host)
        parent_layout.addWidget(self.action_plan_scroll, 1)

        self._action_plan_row_widgets: list[QtWidgets.QWidget] = []
        self._action_plan_health_buttons: list[QtWidgets.QPushButton] = []
        self._action_plan_link_buttons: list[QtWidgets.QPushButton] = []
        self._network_power_adapter: dict | None = None
        self._health_thread: QtCore.QThread | None = None
        self._health_worker: object | None = None

    def _clear_action_plan_step_rows(self) -> None:
        for w in self._action_plan_row_widgets:
            self.action_plan_steps_layout.removeWidget(w)
            w.deleteLater()
        self._action_plan_row_widgets.clear()
        self._action_plan_health_buttons.clear()
        self._action_plan_link_buttons.clear()
        while self.action_plan_steps_layout.count() > 1:
            item = self.action_plan_steps_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _action_plan_source_steps(self, m: dict) -> list[str]:
        fix_plan = m.get("fix_plan") or {}
        recs = fix_plan.get("steps") or m.get("recommendations", [])
        recs = core.sanitize_action_plan_steps(
            list(recs or []), m.get("driver")
        )
        rows: list[str] = []
        for r in recs:
            r = (r or "").strip()
            if not r:
                continue
            if r.startswith(("1)", "2)", "3)", "4)")):
                continue
            rows.append(r)
        return rows

    def _sync_action_plan_health_buttons(self) -> None:
        admin = log_cleanup.is_user_admin()
        tip = getattr(self, "_ADMIN_GATED_TOOLTIP", "Run BSOD Analyzer as administrator.")
        for btn in self._action_plan_health_buttons:
            kind = btn.property("health_kind")
            needs_admin = kind in self._ADMIN_HEALTH_KINDS
            btn.setEnabled(admin or not needs_admin)
            if needs_admin:
                btn.setToolTip("" if admin else tip)

    def _action_plan_button_size(self) -> tuple[int, int]:
        labels = apui.iter_action_button_labels()
        longest = max(labels, key=lambda t: len(t))
        probe = QtWidgets.QPushButton(longest, self)
        probe.ensurePolished()
        hint = probe.sizeHint()
        probe.deleteLater()
        width = max(_ACTION_BTN_MIN_WIDTH, hint.width() + 4)
        height = max(_ACTION_BTN_MIN_HEIGHT, hint.height())
        return width, height

    def _make_action_plan_button_column(
        self,
        *,
        health_kinds: list[str],
        driver_options: list[dict],
        btn_width: int,
        btn_height: int,
    ) -> QtWidgets.QWidget:
        import system_health_actions as shealth

        host = QtWidgets.QWidget()
        host.setFixedWidth(btn_width)
        host.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        col = QtWidgets.QVBoxLayout(host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        def _style_button(btn: QtWidgets.QPushButton) -> None:
            btn.setFixedSize(btn_width, btn_height)
            btn.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

        if not health_kinds and not driver_options:
            gap = QtWidgets.QWidget()
            gap.setFixedSize(btn_width, btn_height)
            gap.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            col.addWidget(gap)
            return host

        for kind in health_kinds:
            btn = QtWidgets.QPushButton(shealth.action_button_label(kind))  # type: ignore[arg-type]
            btn.setProperty("health_kind", kind)
            _style_button(btn)
            btn.clicked.connect(
                lambda _checked=False, k=kind: self._run_action_plan_health_action(k)
            )
            col.addWidget(btn)
            self._action_plan_health_buttons.append(btn)
        for opt in driver_options:
            btn = QtWidgets.QPushButton(apui.driver_action_button_label(opt))
            btn.setProperty("driver_option", opt)
            btn.setToolTip((opt.get("reason") or opt.get("label") or "").strip())
            _style_button(btn)
            btn.clicked.connect(
                lambda _checked=False, o=opt: self._on_action_driver_link(o)
            )
            col.addWidget(btn)
            self._action_plan_link_buttons.append(btn)
        return host

    def _populate_action_plan_ui(self, m: dict) -> None:
        if not hasattr(self, "action_plan_steps_layout"):
            return
        self._clear_action_plan_step_rows()
        fix_plan = m.get("fix_plan") or {}
        cause_title = (m.get("cause_title") or "").strip()
        headline = (fix_plan.get("headline") or "").strip()
        if headline and headline.lower() not in cause_title.lower():
            self.action_plan_headline.setText(headline)
            self.action_plan_headline.show()
        else:
            self.action_plan_headline.hide()

        context = apui.action_plan_context_line(
            fix_plan, m, skip_headline=cause_title or headline
        )
        if context:
            self.action_plan_context.setText(context)
            self.action_plan_context.show()
        else:
            self.action_plan_context.hide()

        steps = self._action_plan_source_steps(m)
        options = list(m.get("driver_update_options") or [])
        plan_rows = apui.build_action_plan_rows(steps, options)
        if not plan_rows:
            empty = QtWidgets.QLabel("No specific actions found.")
            empty.setObjectName("Muted")
            self.action_plan_steps_layout.insertWidget(0, empty)
            self._action_plan_row_widgets.append(empty)
            return

        btn_width, btn_height = self._action_plan_button_size()
        for i, entry in enumerate(plan_rows, 1):
            row = QtWidgets.QWidget()
            row_lay = QtWidgets.QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(10)

            num = QtWidgets.QLabel(f"{i}.")
            num.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
            num.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight
            )
            num.setFixedWidth(24)

            btn_host = self._make_action_plan_button_column(
                health_kinds=entry["health_kinds"],
                driver_options=entry["driver_options"],
                btn_width=btn_width,
                btn_height=btn_height,
            )

            text = QtWidgets.QLabel(entry["text"])
            text.setWordWrap(True)
            text.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )

            row_lay.addWidget(num, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            row_lay.addWidget(btn_host, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            row_lay.addWidget(text, 1)

            insert_at = max(0, self.action_plan_steps_layout.count() - 1)
            self.action_plan_steps_layout.insertWidget(insert_at, row)
            self._action_plan_row_widgets.append(row)
        self._sync_action_plan_health_buttons()

    def _run_action_plan_health_action(self, kind: str) -> None:
        import system_health_actions as shealth

        if kind not in ("memory_test", "sfc", "dism", "chkdsk"):
            return
        if kind in self._ADMIN_HEALTH_KINDS and not log_cleanup.is_user_admin():
            QtWidgets.QMessageBox.warning(
                self,
                "Administrator required",
                "Restart BSOD Analyzer as administrator to run this check.",
            )
            return
        msg = shealth.action_confirm_message(kind)  # type: ignore[arg-type]
        title = {
            "memory_test": "Memory test",
            "sfc": "System File Checker",
            "dism": "DISM repair",
            "chkdsk": "Check Disk",
        }.get(kind, "System check")
        reply = QtWidgets.QMessageBox.question(
            self,
            title,
            msg,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if kind == "memory_test":
            ok, detail = shealth.launch_memory_diagnostic()
            if ok:
                QtWidgets.QMessageBox.information(self, title, detail)
            else:
                QtWidgets.QMessageBox.warning(self, title, detail)
            return
        if kind == "chkdsk":
            ok, detail = shealth.schedule_chkdsk_system_drive()
            if ok:
                QtWidgets.QMessageBox.information(self, title, detail[-2000:])
            else:
                QtWidgets.QMessageBox.warning(self, title, detail[-2000:])
            return
        self._start_system_health_job(kind)

    def _start_system_health_job(self, kind: str) -> None:
        if getattr(self, "_health_thread", None) and self._health_thread.isRunning():
            QtWidgets.QMessageBox.information(
                self,
                "System check",
                "A system check is already running — wait for it to finish.",
            )
            return
        label = {
            "sfc": "Running SFC /scannow…",
            "dism": "Running DISM RestoreHealth…",
        }.get(kind, "Running system check…")
        self._begin_task_progress(label, maximum=0)
        self.statusBar().showMessage(label)
        from bsod_gui_workers import SystemHealthWorker

        self._health_thread = QtCore.QThread()
        self._health_worker = SystemHealthWorker(kind)
        self._health_worker.moveToThread(self._health_thread)
        self._health_thread.started.connect(self._health_worker.run)
        self._health_worker.finished.connect(self._on_system_health_finished)
        self._health_worker.failed.connect(self._on_system_health_failed)
        self._health_worker.finished.connect(self._health_thread.quit)
        self._health_worker.failed.connect(self._health_thread.quit)
        self._health_thread.finished.connect(self._cleanup_system_health_thread)
        self._health_thread.start()

    @QtCore.Slot(bool, str)
    def _on_system_health_finished(self, ok: bool, detail: str) -> None:
        self._end_task_progress()
        title = "System check complete" if ok else "System check finished with issues"
        if ok:
            QtWidgets.QMessageBox.information(
                self, title, detail[-3500:] if detail else title
            )
        else:
            QtWidgets.QMessageBox.warning(
                self, title, detail[-3500:] if detail else title
            )
        self.statusBar().showMessage(title, 8000)

    @QtCore.Slot(str)
    def _on_system_health_failed(self, err: str) -> None:
        self._end_task_progress()
        QtWidgets.QMessageBox.warning(self, "System check failed", err[:2000])
        self.statusBar().showMessage(f"System check failed: {err[:80]}", 8000)

    def _cleanup_system_health_thread(self) -> None:
        self._health_thread = None
        self._health_worker = None

    def _maybe_warn_network_power_before_catalog_scan(self) -> None:
        import system_network_power as snp

        adapter = snp.query_active_network_adapter()
        self._network_power_adapter = adapter
        if not adapter or not adapter.get("PowerSavingOn"):
            return
        if not hasattr(self, "drv_hint"):
            return
        summary = snp.adapter_power_summary(adapter)
        self._set_catalog_hint(
            self.drv_hint,
            f"{summary} Use Settings → Preferences → “Keep adapter awake”.",
        )
