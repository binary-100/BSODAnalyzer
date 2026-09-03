"""Run analysis, populate summary/action/crash views, summary refresh."""
from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiAnalysisMixin:
    def _safe_set_html(self, browser, html: str) -> None:
        import gui_html_safe as html_safe

        html_safe.safe_set_html(browser, html)

    def _reset_post_analysis_pipeline(self) -> None:
        """Bump analysis/catalog generations before a new Run Analysis."""
        self._analysis_generation += 1
        self._pending_needs_config = False
        self._drv_catalog_generation += 1
        self._fw_catalog_generation += 1
        self._drv_list_build_generation += 1
        self._drv_manual_queue.clear()
        self._pending_crash_module_check = None
        # Do not forcibly quit catalog threads mid-PowerShell — handlers ignore stale jobs.

    def on_run(self) -> None:
        if self._thread is not None:
            if self._thread.isRunning():
                return
            self._teardown_thread()
        if self._hw_thread is not None and self._hw_thread.isRunning():
            QtWidgets.QMessageBox.information(
                self,
                "Run Analysis",
                "A hardware scan is still running. Wait for it to finish, then run analysis again.",
            )
            return
        if not self._prompt_cdb_before_analysis():
            return
        self._reset_post_analysis_pipeline()
        self._summary_refresh_generation += 1
        self._set_summary_refresh_progress(False)
        self._analysis_run_active = True
        self.btn_run.setEnabled(False)
        self._begin_task_progress("Running log analysis…", maximum=100, value=0)
        self.statusBar().showMessage("Analyzing event logs and dump files...")
        self.cause_title.setText("Analyzing…")
        self.cause_sub.setText("Scanning event logs, minidumps, and drivers.")
        import gui_theme as theme

        self._set_dot_color(theme.BORDER, label="Unknown")

        import bsod_gui_qt as _gui

        self._thread = QtCore.QThread()
        self._worker = _gui.AnalysisWorker(
            include_reliability=self._settings.get("show_reliability_events", True),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._signal_relay.analysis_progress)
        self._worker.finished.connect(self._signal_relay.analysis_finished)
        self._worker.failed.connect(self._signal_relay.analysis_failed)
        self._thread.start()

    @QtCore.Slot(int, str)
    def _on_progress(self, pct: int, msg: str) -> None:
        if self._shutting_down:
            return
        self.statusBar().showMessage(msg)
        # Cap at 95% until the worker finishes formatting so the bar is not full while work continues.
        self._set_task_progress(min(max(pct, 0), 95), msg, maximum=100)

    @QtCore.Slot(object, object, str, bool)
    def _on_finished(
        self, model: dict, fmt_args: tuple, full_report: str, needs_config: bool,
    ) -> None:
        if self._shutting_down:
            self._teardown_thread()
            return
        self._set_task_progress(100, "Log analysis complete.", maximum=100)
        self._analysis_run_active = False
        self._end_task_progress()
        self._full_report = full_report
        self._last_fmt_args = fmt_args
        try:
            self._populate(model)
            self.statusBar().showMessage(
                "Log analysis complete. Driver and firmware tabs may still be loading."
            )
        except Exception as e:  # noqa: BLE001 — keep GUI alive; show actionable error
            import traceback

            detail = traceback.format_exc()
            if not self._shutting_down:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Could not display analysis results",
                    f"{e}\n\nThe scan finished but updating the window failed.\n\n{detail[-1800:]}",
                )
                self.cause_title.setText("Analysis finished — display error")
                self.cause_sub.setText(str(e)[:240])
                self.statusBar().showMessage(
                    "Analysis complete, but displaying results failed."
                )
        finally:
            self._teardown_thread()
            if not self._shutting_down:
                self.btn_run.setEnabled(True)
        if self._shutting_down:
            return
        self._pending_needs_config = bool(needs_config)
        if needs_config:
            QtCore.QTimer.singleShot(250, self._prompt_enable_memory_dump_if_needed)

    def _prompt_enable_memory_dump_if_needed(self) -> None:
        if self._shutting_down or not self._pending_needs_config:
            return
        self._pending_needs_config = False
        ret = QtWidgets.QMessageBox.question(
            self, "Enable Memory Dump",
            "Windows memory dumps are not enabled. Enabling them helps find the root "
            "cause of future crashes.\n\nEnable now? (requires Administrator)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if ret == QtWidgets.QMessageBox.Yes:
            self.on_enable_dump()

    @QtCore.Slot(str)
    def _on_failed(self, err: str) -> None:
        if self._shutting_down:
            self._teardown_thread()
            return
        self._analysis_run_active = False
        self._end_task_progress()
        self._teardown_thread()
        self.btn_run.setEnabled(True)
        self.cause_title.setText("Analysis failed")
        self.cause_sub.setText(err)
        self.statusBar().showMessage("Analysis failed.")

    def _teardown_thread(self) -> None:
        self._disconnect_analysis_worker()
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(self._ANALYSIS_THREAD_WAIT_MS)
        self._thread = None
        self._worker = None

    def _merge_hardware_into_fmt_args(self, fmt_args: tuple) -> tuple:
        return wf.merge_hardware_into_fmt_args(fmt_args, self._hardware_profile)

    def _repair_narrative_html(self, narrative: dict, m: dict | None = None) -> str:
        import gui_theme as theme

        n = narrative or {}
        m = m or {}
        if not n.get("what_happened"):
            return ""
        blocks: list[str] = []

        digest: list[tuple[str, str]] = []
        if m.get("last_crash"):
            digest.append(("Latest incident", str(m["last_crash"])))
        stop = m.get("stop_name_friendly") or m.get("stop_name")
        if stop:
            digest.append(("Stop code", str(stop).replace("_", " ")))
        driver = m.get("driver")
        if driver:
            if core.is_kernel_shim_fault_module(driver):
                digest.append(
                    (
                        "Minidump module",
                        f"{driver} (kernel — look for underlying driver)",
                    )
                )
            else:
                digest.append(("Faulting module", driver))
        dumps_n = m.get("dumps_analyzed")
        if dumps_n:
            digest.append(("Minidumps analyzed", str(dumps_n)))
        timeline = m.get("incident_timeline") or {}
        for entry in (timeline.get("entries") or [])[:4]:
            if entry.get("historical"):
                continue
            label = (entry.get("label") or entry.get("kind") or "").strip()
            if not label:
                continue
            t = (entry.get("time") or "").strip()
            digest.append(("Log signal", f"{label}" + (f" · {t}" if t else "")))
            if len([d for d in digest if d[0] == "Log signal"]) >= 2:
                break
        if digest:
            rows = "".join(
                f"<tr>"
                f"<td style='padding:3px 10px 3px 0; color:{theme.MUTED}; vertical-align:top; white-space:nowrap'>{self._esc(k)}</td>"
                f"<td style='padding:3px 0; vertical-align:top'>{self._esc(v)}</td>"
                f"</tr>"
                for k, v in digest[:8]
            )
            blocks.append(
                f"<p style='margin:0 0 6px 0'><b>Log summary</b></p>"
                f"<table style='width:100%; border-collapse:collapse; font-size:13px; line-height:140%; margin:0 0 12px 0'>"
                f"{rows}</table>"
            )

        blocks.append(
            f"<p style='margin:0 0 10px 0; line-height:150%'>{self._esc(n['what_happened'])}</p>"
        )
        wf = n.get("what_failed") or {}
        if wf.get("summary"):
            blocks.append(
                f"<p style='margin:0 0 10px 0; line-height:150%; color:{theme.MUTED}'>"
                f"{self._esc(wf['summary'])}</p>"
            )
        targets = n.get("repair_targets") or []
        if targets:
            rows = []
            for t in targets[:5]:
                ver = self._esc(t.get("version") or "—")
                rows.append(
                    "<tr>"
                    f"<td style='padding:3px 8px 3px 0; vertical-align:top'>{self._esc(t.get('label') or '?')}</td>"
                    f"<td style='padding:3px 0; vertical-align:top'>{ver}</td>"
                    "</tr>"
                )
            more = len(targets) - 5
            extra = (
                f"<p style='margin:4px 0 0 0; color:{theme.MUTED}; font-size:12px'>"
                f"+ {more} more on Drivers → Needs attention</p>"
                if more > 0
                else ""
            )
            blocks.append(
                f"<p style='margin:0 0 4px 0'><b>Check first on this PC</b></p>"
                f"<table style='width:100%; border-collapse:collapse; font-size:13px; line-height:140%'>"
                f"<tr style='color:{theme.MUTED}'><th align='left'>Device</th>"
                f"<th align='left'>Installed</th></tr>"
                + "".join(rows)
                + "</table>"
                + extra
            )
        why = n.get("why_this_order") or n.get("how_sure")
        if why:
            blocks.append(
                f"<p style='margin:10px 0 0 0; color:{theme.MUTED}; line-height:150%; font-size:13px'>"
                f"{self._esc(why)}</p>"
            )
        if n.get("older_incident_note"):
            blocks.append(
                f"<p style='margin:8px 0 0 0; color:{theme.MUTED}; line-height:150%; font-size:13px'>"
                f"{self._esc(n['older_incident_note'])}</p>"
            )
        blocks.append(
            f"<p style='margin:10px 0 0 0; line-height:150%; font-size:13px; color:{theme.MUTED}'>"
            "Numbered steps and download links are on <b>Action Plan</b>.</p>"
        )
        return "".join(blocks)

    def _capture_readiness_html(self, readiness: dict) -> str:
        import gui_theme as theme

        checks = readiness.get("checks") or []
        if not checks:
            return ""
        rows = []
        for c in checks:
            ok = c.get("ok")
            color = theme.MUTED if ok else theme.WARNING_FG
            mark = "✓" if ok else "!"
            detail = self._esc(c.get("detail") or "")
            label = self._esc(c.get("label") or "?")
            rows.append(
                f"<tr>"
                f"<td style='color:{color}; padding:2px 8px 2px 0; vertical-align:top'>{mark}</td>"
                f"<td style='padding:2px 8px 2px 0; vertical-align:top'>{label}</td>"
                f"<td style='padding:2px 0; color:{theme.MUTED}; vertical-align:top'>{detail}</td>"
                f"</tr>"
            )
        headline = "Crash capture ready" if readiness.get("capture_ready") else "Crash capture needs attention"
        return (
            f"<p style='margin:14px 0 6px 0'><b>{self._esc(headline)}</b></p>"
            f"<table style='width:100%; border-collapse:collapse; font-size:13px; line-height:140%'>"
            + "".join(rows)
            + "</table>"
        )

    def _plain_english_html(self, m: dict) -> str:
        import gui_theme as theme

        narrative = m.get("crash_repair_narrative") or (m.get("driver_verification") or {}).get(
            "repair_narrative"
        )
        if narrative and narrative.get("what_happened"):
            pe_html = self._repair_narrative_html(narrative, m)
            cap = m.get("capture_readiness") or {}
            if cap.get("checks") and not cap.get("capture_ready"):
                pe_html += self._capture_readiness_html(cap)
            gaps = m.get("data_gaps") or []
            if m.get("driver_verification", {}).get("has_suspects"):
                pe_html += (
                    f"<p style='margin:12px 0 0 0; color:{theme.MUTED}; line-height:150%'>"
                    "Tip: on the Drivers tab, start with <b>Needs attention</b> rows, then "
                    "Search for updates.</p>"
                )
            if gaps:
                gap_items = "".join(f"<li>{self._esc(g)}</li>" for g in gaps)
                warn = theme.WARNING_FG
                pe_html = (
                    f"<p style='color:{warn}; margin:0 0 10px 0'><b>Data gaps</b> "
                    f"(parts of the scan failed):</p>"
                    f"<ul style='margin:0 0 12px 0; padding-left:1.15em; color:{warn}'>"
                    f"{gap_items}</ul>"
                ) + pe_html
            return pe_html

        driver = m.get("driver")
        gaps = m.get("data_gaps") or []
        pe_raw = (m.get("plain_english") or "").strip()
        pe_parts = [p.strip() for p in pe_raw.split("\n\n") if p.strip()]
        drv_hi = ""
        if driver:
            drv_esc = self._esc(driver)
            drv_hi = f"<span style='font-family:{MONO}; color:{theme.ACCENT}'>{drv_esc}</span>"
        blocks: list[str] = []
        for p in pe_parts:
            if p.startswith("What the logs show:\n") or p.startswith("Logs reviewed"):
                lines = p.split("\n")
                head = self._esc(lines[0])
                blocks.append(
                    f"<p style='margin:12px 0 4px 0; line-height:150%'><b>{head}</b></p>"
                )
                blocks.append(
                    "<ul style='margin:0 0 10px 0; padding-left:1.15em; line-height:150%'>"
                )
                for line in lines[1:]:
                    text = line[2:].strip() if line.startswith("• ") else line.strip()
                    if text:
                        blocks.append(f"<li>{self._esc(text)}</li>")
                blocks.append("</ul>")
            elif p.startswith("• "):
                blocks.append(
                    f"<p style='margin:0 0 6px 0; padding-left:1.15em; text-indent:-1em; "
                    f"line-height:150%'>{self._esc(p)}</p>"
                )
            else:
                body = self._esc(p)
                if driver:
                    body = body.replace(self._esc(driver), drv_hi)
                blocks.append(
                    f"<p style='margin:0 0 12px 0; line-height:150%'>{body}</p>"
                )
        pe_html = "".join(blocks) or f"<p style='color:{theme.MUTED}'>No summary available.</p>"
        conf = m.get("crash_confidence") or {}
        if conf.get("headline"):
            warn = theme.WARNING_FG if conf.get("level") in ("focus", "unknown") else theme.ACCENT
            conf_html = (
                f"<p style='margin:0 0 8px 0; color:{warn}; font-weight:600'>"
                f"{self._esc(conf.get('headline') or '')}</p>"
                f"<p style='margin:0 0 8px 0; line-height:150%'>{self._esc(conf.get('detail') or '')}</p>"
            )
            changes = conf.get("what_would_change") or []
            if changes:
                conf_html += (
                    f"<p style='margin:8px 0 4px 0; color:{theme.MUTED}'><b>What would change this</b></p><ul>"
                )
                conf_html += "".join(
                    f"<li>{self._esc(c)}</li>" for c in changes
                )
                conf_html += "</ul>"
            pe_html = conf_html + pe_html
        if m.get("driver_verification", {}).get("has_suspects"):
            pe_html += (
                f"<p style='margin:12px 0 0 0; color:{theme.MUTED}; line-height:150%'>"
                "Tip: full driver scans list many inbox Microsoft devices as "
                "<i>none</i> — that is normal. Start with crash-linked / Needs attention rows.</p>"
            )
        if gaps:
            gap_items = "".join(f"<li>{self._esc(g)}</li>" for g in gaps)
            warn = theme.WARNING_FG
            pe_html = (
                f"<p style='color:{warn}; margin:0 0 10px 0'><b>Data gaps</b> "
                f"(parts of the scan failed — results may be incomplete):</p>"
                f"<ul style='margin:0 0 12px 0; padding-left:1.15em; color:{warn}'>"
                f"{gap_items}</ul>"
            ) + pe_html
        return pe_html

    def _action_plan_html(self, m: dict) -> str:
        import gui_theme as theme

        fix_plan = m.get("fix_plan") or {}
        recs = fix_plan.get("steps") or m.get("recommendations", [])
        items = []
        n = 0
        for r in recs:
            r = r.strip()
            if not r:
                continue
            if r.startswith(("1)", "2)", "3)", "4)")):
                items.append(
                    f"<div style='margin:2px 0 2px 12px; color:{theme.MUTED}'>{self._esc(r)}</div>"
                )
            else:
                n += 1
                items.append(
                    f"<div style='margin:8px 0'><b style='color:{theme.ACCENT}'>{n}.</b> {self._esc(r)}</div>"
                )
        headline = (fix_plan.get("headline") or "").strip()
        intro = ""
        if headline:
            intro = f"<p style='color:{theme.MUTED}; margin:0 0 12px 0'>{self._esc(headline)}</p>"
        return (
            "<div style='line-height:150%'>"
            "<h3 style='margin-top:0'>Troubleshooting steps determined by your crash logs</h3>"
            + intro
            + ("".join(items) or "<p>No specific actions found.</p>")
            + "</div>"
        )

    def _has_crash_analysis_context(self) -> bool:
        return wf.has_crash_analysis_context(self._last_model, self._last_fmt_args)

    def _should_refresh_crash_details_from_hardware(self) -> bool:
        return wf.should_refresh_crash_details_after_hardware(
            full_install=app_set.is_full_install_mode(self._settings),
            model=self._last_model,
            fmt_args=self._last_fmt_args,
            hardware_ready=self._hardware_inventory_ready(),
        )

    def _workflow_banner_flags(self) -> tuple[bool, bool, bool]:
        full = app_set.is_full_install_mode(self._settings)
        return full, self._has_crash_analysis_context(), self._hardware_inventory_ready()

    def _update_idle_workflow_banners(self) -> None:
        self._update_drv_workflow_banner("")
        self._update_fw_workflow_banner("")

    def _crash_details_html(self, m: dict) -> str:
        import gui_theme as theme

        incidents = m.get("incidents", [])
        if incidents:
            rows = []
            for i, inc in enumerate(incidents, 1):
                rows.append(
                    f"<div style='margin-bottom:12px'><b>Incident {i}</b> "
                    f"<span style='color:{theme.MUTED}'>({self._esc(inc['time'])})</span><br>"
                    f"<span style='color:{theme.MUTED}'>Events:</span> {self._esc(inc['types'])}<br>"
                    + (
                        f"<span style='color:{theme.MUTED}'>Stop code:</span> "
                        f"{self._esc(inc['stop_code'])}<br>"
                        if inc.get("stop_code")
                        else ""
                    )
                    + (
                        f"<span style='color:{theme.MUTED}'>Cause:</span> "
                        f"{self._esc(inc['cause'])}"
                        if inc.get("cause")
                        else ""
                    )
                    + "</div>"
                )
            details_html = (
                "<div style='line-height:150%'>" + "".join(rows) + "</div>"
            )
        else:
            details_html = (
                f"<p style='color:{theme.MUTED}'>No crash incidents found in the event log.</p>"
            )
        rel_block = self._reliability_details_html(m)
        return details_html + (rel_block or "")

    def _populate_at_a_glance_from_model(self, m: dict) -> None:
        self._clear_glance()
        self._add_glance("Dumps analyzed", str(m.get("dumps_analyzed", 0)))
        if m.get("recurring_count"):
            self._add_glance(
                "Crashes attributed",
                f"{m['recurring_count']} ({m.get('attributed_pct', 0)}%)",
            )
        if m.get("last_crash"):
            self._add_glance("Last crash", m["last_crash"])
        stop_display = m.get("stop_name_friendly") or m.get("stop_name")
        if stop_display:
            self._add_glance("Stop code", stop_display)
        ct = m.get("cause_type") or {}
        cause_label = ct.get("label", "")
        if cause_label:
            self._add_glance("Cause type", cause_label)
        driver = m.get("driver")
        if driver:
            glance_driver = (
                "Kernel fault (platform drivers)"
                if core.is_kernel_shim_fault_module(driver)
                else driver
            )
            self._add_glance("Top suspect", glance_driver)
        self._add_glance("Crash events found", str(m.get("crash_count", 0)))
        rel = m.get("reliability_ctx") or {}
        lk = rel.get("livekernel") or []
        if lk:
            self._add_glance("Live Kernel events", str(len(lk)))
        if rel.get("stability_index") is not None:
            self._add_glance("Stability index", str(rel["stability_index"]))

    def _refresh_crash_views_from_model(self, m: dict, new_m: dict) -> None:
        wf.merge_display_keys(m, new_m, wf.INVENTORY_CRASH_VIEW_KEYS)
        if self._hardware_profile:
            fw = self._hardware_profile.get("ssd_firmware")
            if fw:
                m["ssd_firmware"] = fw
        self._update_crash_timeline_ui(m)
        self._update_reliability_ui(m)
        self._populate_at_a_glance_from_model(m)
        self._safe_set_html(self.details_text, self._crash_details_html(m))
        self._safe_set_html(self.system_text, self._system_html(m))

    def _schedule_refresh_summary_from_inventory(self) -> None:
        """Coalesce multiple hardware-path callers into one summary rebuild."""
        if self._shutting_down:
            return
        self._summary_refresh_timer.start(80)

    def _set_summary_refresh_progress(self, visible: bool) -> None:
        if hasattr(self, "_summary_refresh_frame"):
            self._summary_refresh_frame.setVisible(visible)
        if visible:
            self.statusBar().showMessage(
                "Refreshing summary with full device list…", 5000
            )

    def _start_offthread_summary_refresh(self) -> None:
        """Run build_display_model on a worker thread; apply on main thread."""
        if self._shutting_down:
            return
        m = self._last_model
        fmt = self._last_fmt_args
        if not m or not fmt:
            return
        if self._summary_refresh_thread and self._summary_refresh_thread.isRunning():
            self._summary_refresh_pending = True
            return
        self._summary_refresh_generation += 1
        gen = self._summary_refresh_generation
        prof = wf.hardware_profile_for_summary_refresh(self._hardware_profile)
        self._set_summary_refresh_progress(True)
        self._summary_refresh_thread = QtCore.QThread()
        self._summary_refresh_worker = SummaryRefreshWorker(fmt, prof, gen)
        self._summary_refresh_worker.moveToThread(self._summary_refresh_thread)
        self._summary_refresh_thread.started.connect(self._summary_refresh_worker.run)
        self._summary_refresh_worker.finished.connect(
            self._signal_relay.summary_refresh_finished
        )
        self._summary_refresh_worker.failed.connect(
            self._signal_relay.summary_refresh_failed
        )
        self._summary_refresh_worker.finished.connect(
            self._summary_refresh_thread.quit
        )
        self._summary_refresh_worker.failed.connect(self._summary_refresh_thread.quit)
        self._summary_refresh_thread.finished.connect(
            self._cleanup_summary_refresh_thread
        )
        self._summary_refresh_thread.start()

    def _apply_summary_refresh_from_model(self, new_m: dict) -> None:
        """Apply worker-built model to Summary / Action Plan (main thread only)."""
        m = self._last_model
        if not m:
            return
        if self._last_fmt_args and self._hardware_profile:
            merged = wf.merge_hardware_into_fmt_args(
                self._last_fmt_args, self._hardware_profile
            )
            self._last_fmt_args = merged
            try:
                self._full_report = core.format_output_from_fmt_args(
                    merged, include_technical_details=True
                )
            except Exception as exc:
                try:
                    import session_log

                    session_log.progress(
                        "gui",
                        f"report refresh: {type(exc).__name__}",
                        extra={"status": "skip"},
                    )
                except Exception:
                    pass  # optional session_log
        wf.merge_display_keys(m, new_m, wf.INVENTORY_SUMMARY_KEYS)
        if self._hardware_profile:
            fw = self._hardware_profile.get("ssd_firmware")
            if fw:
                m["ssd_firmware"] = fw
        driver = m.get("driver")
        if driver:
            self.cause_title.setText(f"Likely cause: {m['cause_title']}")
        self._safe_set_html(self.plain_text, f"<div>{self._plain_english_html(m)}</div>")
        self._populate_action_plan_ui(m)
        self._refresh_minidump_panel(m)
        self._populate_driver_update_options(m)
        self._populate_action_plan_ui(m)
        if self._should_refresh_crash_details_from_hardware():
            self._refresh_crash_views_from_model(m, new_m)
        self._update_idle_workflow_banners()

    @QtCore.Slot(int, object)
    def _on_summary_refresh_finished(self, generation: int, new_m: object) -> None:
        if generation != self._summary_refresh_generation or self._shutting_down:
            return
        self._set_summary_refresh_progress(False)
        if isinstance(new_m, dict):
            self._apply_summary_refresh_from_model(new_m)
            self.statusBar().showMessage("Summary updated with device list.", 4000)

    @QtCore.Slot(int, str)
    def _on_summary_refresh_failed(self, generation: int, err: str) -> None:
        if generation != self._summary_refresh_generation or self._shutting_down:
            return
        self._set_summary_refresh_progress(False)
        self.statusBar().showMessage(
            f"Summary refresh failed: {err[:80]}", 8000
        )

    def _cleanup_summary_refresh_thread(self) -> None:
        pending = bool(self._summary_refresh_pending)
        self._summary_refresh_pending = False
        self._summary_refresh_thread = None
        self._summary_refresh_worker = None
        if pending and not self._shutting_down:
            QtCore.QTimer.singleShot(0, self._start_offthread_summary_refresh)

    def _populate(self, m: dict) -> None:
        if self._shutting_down:
            return
        self._last_model = m
        self._fix_progress_last_crash_cache = None
        self._show_all_devices = False
        if not self._session_all_drivers:
            self._all_devices_loaded = False
        import gui_theme as theme

        level = m["severity_level"]
        color = theme.SEVERITY_COLORS[level]
        self._set_dot_color(color, label=m["severity_name"])
        driver = m.get("driver")
        if driver:
            self.cause_title.setText(f"Likely cause: {m['cause_title']}")
        else:
            self.cause_title.setText(m["cause_title"])
        sub = (m.get("cause_subtitle") or "").strip()
        ct = m.get("cause_type") or {}
        cause_label = ct.get("label", "")
        conf = m.get("confidence", "")
        if sub:
            self.cause_sub.setText(sub)
        elif cause_label:
            self.cause_sub.setText(f"Likely cause type: {cause_label}. {ct.get('detail', '')}")
        else:
            self.cause_sub.setText(conf)
        # Data gaps are listed under Plain English (see _plain_english_html).

        # Severity card
        self.sev_label.setText(m["severity_name"])
        self.sev_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {color};")
        self.meter.set_level(level)
        self._update_crash_timeline_ui(m)
        self._update_reliability_ui(m)

        self._safe_set_html(self.plain_text, f"<div>{self._plain_english_html(m)}</div>")
        self._populate_driver_update_options(m)

        self._populate_at_a_glance_from_model(m)

        self._populate_action_plan_ui(m)
        self._populate_action_plan_ui(m)
        self._refresh_minidump_panel(m)

        self._safe_set_html(self.details_text, self._crash_details_html(m))

        # System (summary tabs first; driver/firmware tab work is deferred)
        self._safe_set_html(self.system_text, self._system_html(m))
        prof = self._profile_from_model(m)

        # Advanced
        raw = m.get("raw_windbg", [])
        kernel_dumps = m.get("kernel_dumps", [])
        lines = []
        if raw:
            dump_label = (m.get("windbg_dump_file") or "").strip()
            if m.get("newest_dump_mismatch") and dump_label:
                lines.append(
                    f"=== WinDbg !analyze -v ({dump_label}; newest dump unavailable) ==="
                )
            else:
                lines.append("=== WinDbg !analyze -v (most recent dump) ===")
            lines.extend(raw)
            lines.append("")
        if kernel_dumps:
            lines.append(f"Kernel minidumps ({core.MINIDUMP_DIR}):")
            for d in kernel_dumps[:8]:
                lines.append("  " + core.format_minidump_summary_line(d))
        self.raw_text.setPlainText("\n".join(lines) if lines else "No WinDbg output (no minidumps analyzed).")
        if m.get("needs_config"):
            self.dump_status.setText("Windows memory dumps are not enabled. Use 'Enable Memory Dump' so future crashes are captured.")
        else:
            self.dump_status.setText(f"Memory dumps are enabled in the Windows registry ({m.get('dump_config', '')}).")

        gen = self._analysis_generation
        QtCore.QTimer.singleShot(0, lambda g=gen, p=prof, model=m: self._populate_deferred(g, p, model))

    def _populate_deferred(self, generation: int, prof: dict, m: dict) -> None:
        """Drivers/firmware tabs and post-analysis checks — off the critical path."""
        if self._shutting_down or generation != self._analysis_generation:
            return
        try:
            if prof:
                if self._hardware_inventory_ready():
                    self._session_hw_inventory_ready = True
                self._apply_hardware_profile(prof, update_drivers_tab=False)
                self._sync_full_driver_inventory_flags(prof)
                self._sync_firmware_inventory_from_model(m, prof)
                self._drv_tab_ui_stale = True
                self._refresh_model_culprit_driver_info()
                self._schedule_refresh_summary_from_inventory()
                if self._drivers_tab_is_active():
                    QtCore.QTimer.singleShot(0, self._populate_drivers_tab)
                self._sync_driver_workflow_buttons()
                # Run Analysis already gathers the full driver list in parallel inside
                # gather_report_data (see analyzer_gather.py group-2 pool). Reuse that
                # inventory when present; only start Load devices if analysis did not.
                if self._all_devices_loaded:
                    if self._drivers_tab_is_active():
                        QtCore.QTimer.singleShot(0, self._populate_drivers_tab)
                elif self._settings.get("auto_load_all_drivers_on_scan", True):
                    QtCore.QTimer.singleShot(
                        0, lambda: self._ensure_full_driver_device_list(quiet=True)
                    )
            self._populate_firmware_tab(load_support_links=False)
            self._schedule_crash_report_update_checks(m)
            QtCore.QTimer.singleShot(100, lambda: self._maybe_start_auto_crash_linked_catalog(m))
            QtCore.QTimer.singleShot(500, self._schedule_firmware_support_links_when_idle)
        except Exception as e:  # noqa: BLE001 — keep window open after summary is shown
            import traceback

            detail = traceback.format_exc()
            QtWidgets.QMessageBox.warning(
                self,
                "Could not finish loading driver/firmware tabs",
                f"{e}\n\nSummary results are still shown.\n\n{detail[-1200:]}",
            )
            self.statusBar().showMessage(
                "Analysis complete — driver/firmware tab update failed.", 8000
            )

    def _action_link_btn_style(self) -> str:
        import gui_theme as theme

        return (
            f"QPushButton {{ text-align: left; color: {theme.ACCENT}; background: transparent; "
            f"border: none; padding: 6px 2px; font-weight: 500; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
            f"QPushButton:disabled {{ color: {theme.MUTED}; }}"
        )

    def _refresh_theme_chrome_from_model(self) -> None:
        """Re-apply summary chrome and HTML panels after a theme switch."""
        import gui_theme as theme

        if hasattr(self, "meter"):
            self.meter.update()
        m = getattr(self, "_last_model", None)
        if not m:
            return
        level = int(m.get("severity_level", 0))
        color = theme.SEVERITY_COLORS.get(level, theme.BORDER)
        self._set_dot_color(color, label=m.get("severity_name", ""))
        if hasattr(self, "sev_label"):
            self.sev_label.setStyleSheet(
                f"font-size: 20px; font-weight: 700; color: {color};"
            )
        self._safe_set_html(self.plain_text, f"<div>{self._plain_english_html(m)}</div>")
        self._populate_action_plan_ui(m)
        self._refresh_minidump_panel(m)
        self._safe_set_html(self.details_text, self._crash_details_html(m))
        self._safe_set_html(self.system_text, self._system_html(m))
    def _on_action_driver_link(self, option: dict) -> None:
        ok, msg = core.run_driver_update_option(option)
        self.statusBar().showMessage(msg[:200])
        if not ok:
            QtWidgets.QMessageBox.warning(
                self,
                "Driver link",
                msg or "Could not open that link.",
            )

    def _refresh_driver_verification_from_catalog(self) -> None:
        """Merge crash-linked catalog results into driver verification + Action Plan."""
        m = self._last_model
        batch = self._driver_batch_comparison or {}
        if not m or not batch.get("devices"):
            return
        rows: dict[str, dict] = {}
        for d in batch.get("devices") or []:
            name = (d.get("device_name") or "").strip()
            if name:
                rows[name.lower()] = d
        if not rows:
            return
        import driver_verification as drvver

        drv_ver = dict(m.get("driver_verification") or {})
        merged = drvver.apply_catalog_results_from_gui(drv_ver, rows)
        if not merged:
            return
        rebuilt = drvver.rebuild_verification_report_lines(merged)
        if rebuilt:
            merged = rebuilt
        m["driver_verification"] = merged
        fix_plan = dict(m.get("fix_plan") or {})
        recs = core.merge_verification_action_steps(
            merged, m.get("recommendations") or [], faulting_driver=m.get("driver")
        )
        m["recommendations"] = recs
        fix_plan["steps"] = recs
        m["fix_plan"] = fix_plan
        fmt = self._last_fmt_args
        if fmt and len(fmt) > 14:
            fa = list(fmt)
            sc = dict(fa[14] or {})
            sc["driver_verification"] = merged
            fa[14] = sc
            self._last_fmt_args = tuple(fa)
            try:
                self._full_report = core.format_output_from_fmt_args(
                    self._last_fmt_args,
                    include_technical_details=True,
                    analysis_elapsed_ms=m.get("analysis_elapsed_ms"),
                )
            except Exception as exc:
                try:
                    import session_log

                    session_log.progress(
                        "gui",
                        f"verification report refresh: {type(exc).__name__}",
                        extra={"status": "skip"},
                    )
                except Exception:
                    pass  # optional session_log
        if hasattr(self, "plain_text"):
            self._safe_set_html(self.plain_text, f"<div>{self._plain_english_html(m)}</div>")
        if hasattr(self, "action_plan_steps_layout"):
            self._populate_action_plan_ui(m)
            self._refresh_minidump_panel(m)
        elif hasattr(self, "action_text"):
            self._safe_set_html(self.action_text, f"<div>{self._action_plan_html(m)}</div>")

    def _apply_crash_driver_scan_to_summary(self) -> None:
        """Push crash-report driver scan results onto the Summary comparison card."""
        m = self._last_model
        if not m:
            return
        self._refresh_driver_verification_from_catalog()
        ct = m.get("cause_type") or {}
        drv_ver = m.get("driver_verification") or {}
        platform_focus = bool((drv_ver.get("attribution") or {}).get("platform_chipset_focus"))
        if not ct.get("driver_actionable") and not platform_focus:
            if not drv_ver.get("has_suspects"):
                return
        if not m.get("driver") and not platform_focus:
            return
        crash_names = set(self._crash_report_driver_names(m))
        if platform_focus:
            import driver_verification as drvver

            bio = (self._hardware_profile or {}).get("bios_driver_info") or m.get("bios_driver_info") or {}
            ctx = (self._hardware_profile or {}).get("system_ctx") or m.get("system_ctx") or {}
            resolved = core.resolve_crash_culprit_context(
                m.get("driver"),
                bio,
                code_val=m.get("code_val"),
                system_ctx=ctx,
                cause_type=ct,
                fix_plan=m.get("fix_plan"),
                has_crash_context=self._has_crash_analysis_context(),
            )
            for n in drvver.crash_linked_catalog_device_names(
                drv_ver, resolved.get("culprit_device_names")
            ):
                crash_names.add(n)
        batch = self._driver_batch_comparison or {}
        entries = [
            e
            for e in (batch.get("devices") or [])
            if (e.get("device_name") or "").strip() in crash_names
            or core.is_crash_synthetic_device_key(e.get("device_name") or "")
        ]
        if not entries:
            return
        comp = drvcat.build_summary_comparison_from_device_entries(
            entries,
            faulting_driver=m.get("driver"),
        )
        comp["fetched_at"] = batch.get("fetched_at") or comp.get("fetched_at")
        self._driver_comparison = comp
        offers = comp.get("offers") or []
        fetched = comp.get("fetched_at") or ""
        self._fill_driver_compare_table(self.driver_compare_table, offers)
        self.driver_compare_table.setVisible(True)
        suffix = (
            f"\n\nCompared at {fetched} (crash-related devices). "
            "Installed vs Microsoft/OEM/vendor catalog — select a row below. "
            "Nothing installs automatically."
        )
        base = self.driver_update_hint.text().split("\n\nCompared at")[0].strip()
        self.driver_update_hint.setText(base + suffix)
        self._refresh_system_restore_button()

    def _populate_driver_update_options(self, m: dict) -> None:
        """Driver comparison card when cause type is driver/software."""
        prior = (
            self._driver_comparison
            if (self._driver_comparison or {}).get("offers")
            else None
        )
        self.driver_compare_table.setRowCount(0)
        self.driver_compare_table.setVisible(False)
        self.btn_enable_restore.setVisible(False)
        ct = m.get("cause_type") or {}
        if not ct.get("driver_actionable") or not m.get("driver"):
            self.driver_update_frame.setVisible(False)
            return
        self.driver_update_frame.setVisible(True)
        driver = m.get("driver") or "driver"
        self.driver_update_title.setText(f"Driver comparison for {driver}")
        lines = ["Installed on this PC (Windows driver inventory):"]
        for d in m.get("culprit_driver_info") or []:
            cls = f" [{d['device_class']}]" if d.get("device_class") else ""
            lines.append(
                f"  • {d['name']}{cls} — {d.get('version', '?')} ({d.get('date', '')})"
            )
        lines.append("")
        lines.append(
            "Use the Drivers tab to install updates: run ① Load devices when ready, "
            "check Include on crash-flagged rows, then ② Search for updates. "
            "Select a package and click Install driver — nothing installs unless you confirm."
        )
        lines.append(
            "Comparison uses version numbers plus driver dates (ignoring Microsoft placeholder dates), "
            "and trusts Windows Update optional-driver offers. “Uncertain” means version/date disagree — verify manually."
        )
        self.driver_update_hint.setText("\n".join(lines))
        if prior and (prior.get("offers") or []):
            self._driver_comparison = prior
            self._fill_driver_compare_table(
                self.driver_compare_table, prior.get("offers") or []
            )
            self.driver_compare_table.setVisible(True)
        self._refresh_system_restore_button()

    def _refresh_system_restore_button(self) -> None:
        self._start_ps_maintenance("restore_status")

    def _set_ps_maintenance_busy(self, busy: bool, message: str = "") -> None:
        for attr in ("btn_restore_point", "drv_btn_restore", "btn_enable_restore", "drv_btn_enable_restore", "btn_backup_driver", "drv_btn_backup", "drv_act_restore_point", "drv_act_backup_driver", "drv_act_enable_restore"):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setEnabled(not busy)
        if message:
            self.statusBar().showMessage(message[:120])

    def _start_ps_maintenance(self, op: str, **params: object) -> None:
        if self._ps_thread is not None and self._ps_thread.isRunning():
            return
        self._ps_op = op
        if op == "restore_status":
            pass
        elif op == "create_restore":
            self._set_ps_maintenance_busy(True, "Creating restore point…")
        elif op == "enable_restore":
            self._ps_retry_restore_after_enable = bool(params.pop("retry_restore_point", False))
            self._set_ps_maintenance_busy(True, "Enabling System Restore…")
        elif op == "backup_driver":
            self._set_ps_maintenance_busy(True, "Backing up driver package…")
        elif op == "restore_driver":
            self._set_ps_maintenance_busy(True, "Restoring driver backup…")
        self._ps_thread = QtCore.QThread()
        self._ps_worker = PsMaintenanceWorker(op, **params)
        self._ps_worker.moveToThread(self._ps_thread)
        self._ps_thread.started.connect(self._ps_worker.run)
        self._ps_worker.finished.connect(self._signal_relay.ps_maintenance_finished)
        self._ps_worker.failed.connect(self._signal_relay.ps_maintenance_failed)
        self._ps_worker.finished.connect(self._ps_thread.quit)
        self._ps_worker.failed.connect(self._ps_thread.quit)
        self._ps_thread.finished.connect(self._cleanup_ps_maintenance_thread)
        self._ps_thread.start()

    def _cleanup_ps_maintenance_thread(self) -> None:
        self._ps_thread = None
        self._ps_worker = None

    def _apply_system_restore_visibility(self, st: dict) -> None:
        self._system_restore_drive = (st.get("drive") or "C:\\")
        enabled = st.get("enabled")
        show = enabled is False
        self.btn_enable_restore.setVisible(show)
        if hasattr(self, "drv_btn_enable_restore"):
            self.drv_btn_enable_restore.setVisible(show)
        if hasattr(self, "drv_act_enable_restore"):
            self.drv_act_enable_restore.setVisible(show)

    @QtCore.Slot(str, object)
    def _on_ps_maintenance_finished(self, op: str, payload: object) -> None:
        if op == "restore_status":
            if isinstance(payload, dict):
                self._apply_system_restore_visibility(payload)
            return
        if self._shutting_down:
            return
        self._set_ps_maintenance_busy(False)
        if op == "create_restore":
            ok, msg, code = payload  # type: ignore[misc]
            if ok:
                QtWidgets.QMessageBox.information(self, "Restore point", msg)
                self.statusBar().showMessage(msg[:120])
                return
            if code == "disabled":
                self._prompt_enable_system_restore(msg)
                return
            QtWidgets.QMessageBox.warning(self, "Restore point", msg)
            self.statusBar().showMessage(msg[:120])
        elif op == "enable_restore":
            ok, msg, code = payload  # type: ignore[misc]
            if ok:
                QtWidgets.QMessageBox.information(self, "System Restore", msg)
                self._refresh_system_restore_button()
                if self._ps_retry_restore_after_enable:
                    self._ps_retry_restore_after_enable = False
                    self._start_ps_maintenance("create_restore")
                else:
                    self.statusBar().showMessage(msg[:120])
                return
            self._ps_retry_restore_after_enable = False
            if code == "denied":
                drvcat.open_system_protection_settings()
                QtWidgets.QMessageBox.warning(
                    self,
                    "System Restore",
                    f"{msg}\n\nRun BSOD Analyzer as Administrator, or use System Protection to enable it.",
                )
                return
            open_ok, open_msg = drvcat.open_system_protection_settings()
            QtWidgets.QMessageBox.warning(
                self,
                "System Restore",
                f"{msg}\n\n{open_msg if open_ok else 'Could not open System Protection.'}",
            )
        elif op == "backup_driver":
            if isinstance(payload, tuple) and len(payload) >= 2:
                ok, msg = payload[0], payload[1]
            else:
                ok, msg = payload  # type: ignore[misc]
            if ok:
                QtWidgets.QMessageBox.information(self, "Back up driver", msg)
            else:
                QtWidgets.QMessageBox.warning(self, "Back up driver", msg)
            self.statusBar().showMessage(msg[:120])
        elif op == "restore_driver":
            ok, msg = payload  # type: ignore[misc]
            if ok:
                QtWidgets.QMessageBox.information(self, "Restore driver", msg)
            else:
                QtWidgets.QMessageBox.warning(self, "Restore driver", msg)
            self.statusBar().showMessage(msg[:120])

    @QtCore.Slot(str, str)
    def _on_ps_maintenance_failed(self, op: str, err: str) -> None:
        if op == "restore_status":
            if not self._shutting_down:
                self.statusBar().showMessage(
                    f"Could not read System Restore status: {err[:100]}", 8000
                )
            return
        if self._shutting_down:
            return
        self._set_ps_maintenance_busy(False)
        self._ps_retry_restore_after_enable = False
        titles = {
            "create_restore": "Restore point",
            "enable_restore": "System Restore",
            "backup_driver": "Back up driver",
            "restore_driver": "Restore driver",
        }
        QtWidgets.QMessageBox.warning(self, titles.get(op, "Maintenance"), err)
        self.statusBar().showMessage(err[:120])

