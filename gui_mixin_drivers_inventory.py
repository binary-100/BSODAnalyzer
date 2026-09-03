"""Hardware profile scan and full driver inventory loading."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiDriversInventoryMixin:
    def _ensure_hardware_profile(self) -> dict | None:
        """Return hardware profile, building from the last analysis model when needed."""
        if self._hardware_profile:
            return self._hardware_profile
        if self._last_model:
            prof = self._profile_from_model(self._last_model)
            self._hardware_profile = prof
            return prof
        return None

    def _profile_from_model(self, m: dict) -> dict:
        ctx = dict(m.get("system_ctx") or {})
        return {
            "pnp_list": ctx.get("pnp_list") or [],
            "system_ctx": ctx,
            "bios_driver_info": m.get("bios_driver_info") or {},
            "devices_with_generic_driver": m.get("devices_with_generic_driver") or [],
            "devices_with_driver_problems": m.get("devices_with_driver_problems") or [],
            "ssd_firmware": m.get("ssd_firmware") or [],
            "secondary_firmware": m.get("secondary_firmware") or [],
        }

    def _drivers_tab_is_active(self) -> bool:
        idx = self._drivers_tab_index()
        return idx >= 0 and self.tabs.currentIndex() == idx

    def _apply_hardware_profile(
        self, profile: dict, *, update_drivers_tab: bool = True
    ) -> None:
        incoming_bio = dict((profile or {}).get("bios_driver_info") or {})
        if incoming_bio.get("all_drivers"):
            self._set_session_all_drivers(incoming_bio["all_drivers"])
        if self._hardware_profile and profile:
            existing = self._hardware_profile
            merged_bio = dict(existing.get("bios_driver_info") or {})
            merged_bio.pop("all_drivers", None)
            if self._session_all_drivers:
                merged_bio["all_drivers_count"] = len(self._session_all_drivers)
            for key in ("device_inventory", "drivers", "bios"):
                if incoming_bio.get(key) and not merged_bio.get(key):
                    merged_bio[key] = incoming_bio[key]
            profile = {
                **existing,
                **profile,
                "bios_driver_info": merged_bio,
                "system_ctx": {
                    **dict(existing.get("system_ctx") or {}),
                    **dict(profile.get("system_ctx") or {}),
                },
            }
        elif profile and incoming_bio.get("all_drivers"):
            profile = dict(profile)
            bio = dict(incoming_bio)
            bio.pop("all_drivers", None)
            bio["all_drivers_count"] = len(self._session_all_drivers)
            profile["bios_driver_info"] = bio
        if incoming_bio.get("all_drivers"):
            self._sync_full_driver_inventory_flags(profile)
        self._hardware_profile = profile
        self._bind_catalog_from_profile()
        self._schedule_catalog_context_enrichment(quiet=True)
        if update_drivers_tab:
            self._populate_drivers_tab()
        self._update_idle_workflow_banners()

    def _hardware_profile_data(self) -> dict | None:
        return self._hardware_profile

    def _start_hardware_scan(
        self,
        *,
        force_refresh_cache: bool = False,
    ) -> None:
        if self._hw_thread and self._hw_thread.isRunning():
            self.statusBar().showMessage(
                "Hardware scan already in progress…", 4000
            )
            return
        self._force_refresh_device_cache = force_refresh_cache
        if force_refresh_cache:
            self._session_hw_inventory_ready = False
            self._drv_include_user_customized = False
        if hasattr(self, "btn_search_driver_updates"):
            self.btn_search_driver_updates.setEnabled(False)
        self._ssd_firmware_loaded = False
        if self._hardware_profile is not None:
            self._hardware_profile["ssd_firmware"] = []
        self.drv_scan_status.setText("Scanning hardware and drivers…")
        self.drv_btn_check.setEnabled(False)
        if getattr(self, "_task_progress_depth", 0) > 0:
            self._set_task_progress(label="Scanning hardware and drivers…", maximum=0)
        else:
            self._begin_task_progress("Scanning hardware and drivers…", maximum=100, value=0)
        self.statusBar().showMessage("Scanning hardware…")
        self._session_log_begin(
            "hardware_scan",
            "Hardware and driver inventory scan",
            "_session_log_hw_token",
        )
        self._hw_thread = QtCore.QThread()
        self._hw_worker = HardwareScanWorker()
        self._hw_worker.moveToThread(self._hw_thread)
        self._hw_thread.started.connect(self._hw_worker.run)
        self._hw_worker.progress.connect(self._signal_relay.hw_scan_progress)
        self._hw_worker.finished.connect(self._signal_relay.hardware_ready)
        self._hw_worker.failed.connect(self._signal_relay.hardware_scan_failed)
        self._hw_worker.finished.connect(self._hw_thread.quit)
        self._hw_worker.failed.connect(self._hw_thread.quit)
        self._hw_thread.finished.connect(self._cleanup_hardware_scan_thread)
        self._hw_thread.start()

    def _cleanup_hardware_scan_thread(self) -> None:
        self._hw_thread = None
        self._hw_worker = None
        self._sync_driver_workflow_buttons()

    @QtCore.Slot(int, int, str)
    def _on_hw_scan_progress(self, step: int, total: int, msg: str) -> None:
        if step <= 0:
            self.drv_scan_status.setText(msg)
            self._set_task_progress(label=msg, maximum=0)
        else:
            pct = int(100 * step / total) if total else 0
            self.drv_scan_status.setText(f"{msg} ({pct}%)")
            self._set_task_progress(pct, msg, maximum=100)
        self._session_log_progress(
            "hardware_scan",
            msg,
            step=step,
            total=total,
        )
        self.statusBar().showMessage(msg[:120])
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )

    @staticmethod
    def _driver_inventory_progress(msg: str) -> tuple[str, int | None, int | None]:
        """Parse shard progress from driver inventory messages."""
        import re

        m = re.search(r"Driver inventory\s+(\d+)/(\d+)", msg or "", re.I)
        if not m:
            return msg, None, None
        done, total = int(m.group(1)), int(m.group(2))
        if total <= 0:
            return msg, None, None
        pct = int(100 * done / total)
        return msg, pct, 100

    @QtCore.Slot(str)
    def _on_drv_all_load_progress(self, msg: str) -> None:
        if self._shutting_down:
            return
        label, pct, maximum = self._driver_inventory_progress(msg)
        if pct is not None and maximum:
            self.drv_scan_status.setText(f"{label} ({pct}%)")
            self._set_task_progress(pct, label, maximum=maximum)
        else:
            self.drv_scan_status.setText(label)
            self._set_task_progress(label=label, maximum=0)
        self._session_log_progress("load_devices", label)
        self._catalog_status_line(label)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )

    def _display_model_from_profile(self, prof: dict) -> dict:
        """Minimal display dict for System tab before crash analysis."""
        return {
            "culprit_callout": None,
            "devices_with_driver_problems": prof.get("devices_with_driver_problems") or [],
            "devices_with_generic_driver": prof.get("devices_with_generic_driver") or [],
            "bios_driver_info": prof.get("bios_driver_info") or {},
            "ssd_firmware": prof.get("ssd_firmware") or [],
            "driver": None,
            "system_ctx": prof.get("system_ctx") or {},
        }

    def _merge_cached_all_drivers(self, profile: dict) -> bool:
        """Reuse saved full device list when cache is still fresh."""
        if not app_set.is_full_install_mode(self._settings):
            return False
        if self._force_refresh_device_cache:
            return False
        cached = hwcache.load_cached_profile()
        if not cached or not hwcache.is_cache_fresh(settings=self._settings):
            return False
        rows = (cached.get("bios_driver_info") or {}).get("all_drivers") or []
        if not rows:
            return False
        self._set_session_all_drivers(rows)
        bio = dict(profile.get("bios_driver_info") or {})
        bio.pop("all_drivers", None)
        bio["all_drivers_count"] = len(rows)
        profile["bios_driver_info"] = bio
        return True

    @QtCore.Slot(object)
    def _on_hardware_ready(self, profile: dict) -> None:
        if self._shutting_down:
            return
        self._session_log_end(
            "hardware_scan",
            "Hardware scan complete",
            "_session_log_hw_token",
        )
        chaining_search = self._after_hw_driver_search == "checked"
        if chaining_search:
            self._set_task_progress(label="Preparing device list…", maximum=0)
        else:
            self._end_task_progress()
        self._force_refresh_device_cache = False
        merged = self._merge_cached_all_drivers(profile)
        if merged:
            self._all_devices_loaded = True
            if self._last_model is not None:
                bio = profile.get("bios_driver_info") or {}
                if bio:
                    self._last_model["bios_driver_info"] = dict(bio)
        self._apply_hardware_profile(profile)
        pending_load = getattr(self, "_pending_load_all_drivers_after_hw", None)
        had_pending_load = pending_load is not None
        if pending_load is not None:
            self._pending_load_all_drivers_after_hw = None
            force_refresh, quiet = pending_load
            QtCore.QTimer.singleShot(
                100,
                lambda fr=force_refresh, q=quiet: self._start_load_all_driver_devices(
                    force_refresh=fr, quiet=q
                ),
            )
        if app_set.is_full_install_mode(self._settings):
            QtCore.QTimer.singleShot(
                500, lambda p=profile: self._start_save_hardware_profile(p)
            )
            hwcache.invalidate_live_fingerprint_cache()
        n_gen = len(profile.get("devices_with_generic_driver") or [])
        if not self._last_model:
            self.system_text.setHtml(
                self._system_html(self._display_model_from_profile(profile))
            )
        self._populate_firmware_tab()
        self._update_idle_workflow_banners()
        if getattr(self, "_pending_firmware_load_after_hw", False):
            self._pending_firmware_load_after_hw = False
            cb = self._ssd_fw_on_ready
            QtCore.QTimer.singleShot(
                100,
                lambda: self._ensure_ssd_firmware_inventory(
                    force_refresh=True,
                    on_ready=cb,
                ),
            )
        if merged:
            self.statusBar().showMessage(
                f"Hardware scan complete (reused saved device list). "
                f"{n_gen} generic driver(s)."
            )
            if self._after_hw_driver_search and not had_pending_load:
                self._finish_hw_then_continue_driver_search()
            return
        if had_pending_load:
            return
        if self._settings.get("auto_load_all_drivers_on_scan", True):
            self._start_load_all_driver_devices()
            if not app_set.is_full_install_mode(self._settings):
                self.statusBar().showMessage(
                    f"Hardware scan complete. Loading full device list… "
                    f"({n_gen} generic driver(s) flagged)."
                )
        else:
            self.statusBar().showMessage(
                f"Hardware scan complete. Use Drivers → Scan driver devices "
                f"for the full inventory ({n_gen} generic driver(s) flagged).",
                12000,
            )
            if self._after_hw_driver_search:
                self._finish_hw_then_continue_driver_search()

    @QtCore.Slot(str)
    def _on_hardware_scan_failed(self, err: str) -> None:
        if self._shutting_down:
            return
        self._session_log_end(
            "hardware_scan",
            f"Hardware scan failed: {err[:200]}",
            "_session_log_hw_token",
            status="error",
        )
        self._end_task_progress()
        self._cancel_chained_driver_search_workflow()
        self._pending_firmware_load_after_hw = False
        self._ssd_fw_on_ready = None
        self.drv_scan_status.setText(f"Hardware scan failed: {err}")
        self._show_actionable_error(
            "Hardware scan",
            "Hardware scan failed.",
            err,
        )

    @staticmethod
    def _update_status_label(status: str) -> str:
        return UPDATE_STATUS_LABELS.get(status, status)

    def _driver_rows_for_cache(self, prof: dict, *, full: bool) -> list[dict]:
        """Source rows for unified cache — lite mode skips full WMI list on the UI thread."""
        bio = prof.get("bios_driver_info") or {}
        all_rows = self._full_driver_rows(prof)
        if full or not all_rows:
            if all_rows:
                return list(all_rows)
            return self._driver_other_devices_from_profile(prof)
        keep: set[str] = set()
        for d in self._driver_watchlist_from_profile(prof):
            n = (d.get("name") or "").strip().lower()
            if n:
                keep.add(n)
        for n in self._culprit_device_names(prof):
            if n:
                keep.add(n.lower())
        inv = core.device_inventory_for_matching(bio)
        lite_inv = list(
            bio.get("device_inventory") or bio.get("drivers") or inv
        )
        if not keep:
            return lite_inv
        out: list[dict] = []
        seen: set[str] = set()
        for rows in (inv, all_rows):
            for d in rows:
                name = (d.get("name") or "").strip()
                key = name.lower()
                if not key or key not in keep or key in seen:
                    continue
                seen.add(key)
                out.append(d)
        return out or list(inv)

    def _build_unified_driver_list(self, prof: dict, *, full: bool = False) -> list[dict]:
        """Merge devices with sort tier. Use full=False for fast crash-only views."""
        return drvlist.build_unified_driver_list(
            self._profile_snapshot_for_driver_list(prof),
            full=full,
            settings=self._settings,
            session_batch=self._driver_batch_comparison,
            crash_driver=(self._last_model or {}).get("driver"),
            last_model=self._last_model,
            last_fmt_args=self._last_fmt_args,
        )

    def _profile_snapshot_for_driver_list(self, prof: dict) -> dict:
        """Shallow profile copy with session all_drivers embedded for off-thread build."""
        snap = dict(prof)
        bio = dict(snap.get("bios_driver_info") or {})
        all_rows = self._full_driver_rows(prof)
        if all_rows:
            bio["all_drivers"] = list(all_rows)
        snap["bios_driver_info"] = bio
        if "system_ctx" in snap and isinstance(snap["system_ctx"], dict):
            snap["system_ctx"] = dict(snap["system_ctx"])
        for key in (
            "devices_with_generic_driver",
            "devices_with_driver_problems",
            "pnp_list",
        ):
            if key in snap and isinstance(snap[key], list):
                snap[key] = list(snap[key])
        return snap

    def _drv_list_build_stale(self, generation: int) -> bool:
        return (
            self._shutting_down
            or generation != self._drv_list_build_generation
        )

    def _cleanup_drv_list_build_thread(self) -> None:
        self._drv_list_build_thread = None
        self._drv_list_build_worker = None

    def _flush_drv_list_build_if_stale(self, generation: int) -> None:
        if not self._drv_list_build_stale(generation):
            return
        if not self._drv_list_build_pending:
            return
        prof = self._hardware_profile
        if not prof:
            self._drv_list_build_pending = False
            self._drv_list_build_pending_full = None
            return
        on_ready = self._drv_list_build_on_ready
        pending_full = self._drv_list_build_pending_full
        self._drv_list_build_pending = False
        self._drv_list_build_pending_full = None
        self._drv_list_build_on_ready = None
        self._refresh_unified_driver_table(
            prof,
            on_ready=on_ready,
            full=pending_full,
        )

    @QtCore.Slot(int, object)
    def _on_drv_list_build_finished(self, generation: int, devices: object) -> None:
        if self._drv_list_build_stale(generation):
            self._flush_drv_list_build_if_stale(generation)
            return
        try:
            import driver_index as drvidx
        except ImportError:
            drvidx = None
        on_ready = self._drv_list_build_on_ready
        pending = self._drv_list_build_pending
        pending_full = self._drv_list_build_pending_full
        self._drv_list_build_on_ready = None
        self._drv_list_build_pending = False
        self._drv_list_build_pending_full = None
        prof = self._hardware_profile
        if not prof or not isinstance(devices, list):
            if on_ready:
                on_ready()
            if pending and prof:
                self._refresh_unified_driver_table(
                    prof,
                    on_ready=on_ready,
                    full=pending_full,
                )
            return
        self._drv_unified_cache = devices
        self._prepare_culprit_include_defaults(prof)
        mode = (
            self.drv_view_filter.currentData()
            if hasattr(self, "drv_view_filter")
            else "all"
        )
        if mode == "all":
            self._apply_all_devices_include_defaults(prof)
        else:
            self._apply_common_device_include_defaults(prof)

        def _after_table() -> None:
            self._after_drv_table_sync()
            if on_ready:
                on_ready()
            if pending:
                self._refresh_unified_driver_table(
                    prof,
                    on_ready=None,
                    full=pending_full,
                )

        self._rebuild_drv_table_display()
        self._sync_drv_unified_table(on_complete=_after_table)
        self._sync_driver_workflow_buttons()
        if drvidx is not None and not self._shutting_down:
            idx_err = drvidx.peek_index_error()
            if idx_err:
                self.statusBar().showMessage(
                    f"Driver index note: {idx_err[:100]}", 10000
                )

    @QtCore.Slot(int, str)
    def _on_drv_list_build_failed(self, generation: int, err: str) -> None:
        if self._drv_list_build_stale(generation):
            self._flush_drv_list_build_if_stale(generation)
            return
        import traceback

        detail = traceback.format_exc()
        if hasattr(self, "drv_scan_status"):
            self.drv_scan_status.setText(f"Could not build device list: {err}")
        self._show_actionable_error(
            "Driver list",
            f"Driver list update failed: {err}",
            detail or err,
        )
        on_ready = self._drv_list_build_on_ready
        self._drv_list_build_on_ready = None
        pending = self._drv_list_build_pending
        pending_full = self._drv_list_build_pending_full
        self._drv_list_build_pending = False
        self._drv_list_build_pending_full = None
        if on_ready:
            on_ready()
        if pending:
            prof = self._hardware_profile
            if prof:
                self._refresh_unified_driver_table(
                    prof,
                    on_ready=on_ready,
                    full=pending_full,
                )
        self._end_drv_list_build_progress_if_owned()

    def _ensure_full_driver_device_list(self, *, quiet: bool = False) -> None:
        """Background load of every signed driver row for the Drivers tab."""
        if self._all_devices_loaded:
            return
        if self._drv_all_load_thread and self._drv_all_load_thread.isRunning():
            return
        prof = self._hardware_profile
        if not prof and self._last_model:
            prof = self._profile_from_model(self._last_model)
            if prof.get("bios_driver_info") or prof.get("system_ctx"):
                self._hardware_profile = prof
        if prof:
            existing = self._full_driver_rows(prof)
            if existing and self._driver_list_looks_full(existing, prof):
                self._all_devices_loaded = True
                self._drv_tab_ui_stale = True
                self._update_drivers_tab_status_only(prof)
                return
            if (
                app_set.is_full_install_mode(self._settings)
                and self._merge_cached_all_drivers(prof)
            ):
                merged = self._full_driver_rows(prof)
                if merged and self._driver_list_looks_full(merged, prof):
                    self._all_devices_loaded = True
                    self._drv_tab_ui_stale = True
                    self._update_drivers_tab_status_only(prof)
                    return
        self._start_load_all_driver_devices(quiet=quiet)

    def _start_load_all_driver_devices(
        self, *, force_refresh: bool = False, quiet: bool = False
    ) -> None:
        if self._drv_all_load_thread and self._drv_all_load_thread.isRunning():
            return
        if (
            not force_refresh
            and app_set.is_full_install_mode(self._settings)
            and self._all_devices_loaded
            and hwcache.has_full_device_list(self._hardware_profile)
            and hwcache.is_cache_fresh(settings=self._settings)
        ):
            self.statusBar().showMessage(
                f"Using saved device list ({hwcache.cache_age_summary()}).",
                5000,
            )
            if self._hardware_profile:
                self._drv_tab_ui_stale = True
            return
        prof = self._hardware_profile
        if not prof:
            if self._hw_thread and self._hw_thread.isRunning():
                self._pending_load_all_drivers_after_hw = (force_refresh, quiet)
                if not quiet:
                    self.statusBar().showMessage(
                        "Hardware scan in progress — device list will load when it finishes.",
                        6000,
                    )
                return
            self._pending_load_all_drivers_after_hw = (force_refresh, quiet)
            if not quiet:
                self.statusBar().showMessage("Scanning hardware before loading device list…", 6000)
            self._start_hardware_scan(force_refresh_cache=force_refresh)
            return
        self._hardware_profile = prof
        self._drv_all_load_quiet = quiet
        import driver_catalog as drvcat

        drvcat.clear_installed_package_versions_cache()
        pnp_index = (
            (prof.get("system_ctx") or {}).get("pnp_enrichment")
            or prof.get("pnp_enrichment")
            or {}
        )
        import gui_theme as theme

        self._set_refresh_device_list_ui(enabled=False, label=theme.BTN_DRV_LOADING)
        if quiet:
            self.statusBar().showMessage(
                "Loading full device list for Drivers tab…", 12000
            )
        else:
            if getattr(self, "_task_progress_depth", 0) > 0:
                self._set_task_progress(label="Loading full device list…", maximum=0)
            else:
                self._begin_task_progress("Loading full device list…", maximum=0)
            self.drv_scan_status.setText("Loading full device list…")
            self.statusBar().showMessage("Loading full device list…")
        self._session_log_begin(
            "load_devices",
            "Loading full signed-driver device list",
            "_session_log_load_token",
        )
        self._drv_all_load_thread = QtCore.QThread()
        self._drv_all_load_worker = LoadAllDriversWorker(pnp_index)
        self._drv_all_load_worker.moveToThread(self._drv_all_load_thread)
        self._drv_all_load_thread.started.connect(self._drv_all_load_worker.run)
        self._drv_all_load_worker.progress.connect(
            self._signal_relay.drv_all_load_progress
        )
        self._drv_all_load_worker.finished.connect(
            self._signal_relay.drv_all_devices_loaded
        )
        self._drv_all_load_worker.failed.connect(
            self._signal_relay.drv_all_devices_load_failed
        )
        self._drv_all_load_worker.finished.connect(self._drv_all_load_thread.quit)
        self._drv_all_load_worker.failed.connect(self._drv_all_load_thread.quit)
        self._drv_all_load_thread.finished.connect(self._cleanup_drv_all_load_thread)
        self._drv_all_load_thread.start()

    def _full_driver_rows(self, prof: dict | None = None) -> list[dict]:
        if self._session_all_drivers:
            return self._session_all_drivers
        if prof is None:
            prof = self._hardware_profile
        bio = (prof or {}).get("bios_driver_info") or {}
        return list(bio.get("all_drivers") or [])

    def _set_session_all_drivers(self, rows: list) -> None:
        self._session_all_drivers = list(rows or [])

    def _attach_all_drivers_to_profile(self, prof: dict, rows: list) -> None:
        """Store full inventory in session memory — not in the live profile dict."""
        self._set_session_all_drivers(rows)
        bio = dict(prof.get("bios_driver_info") or {})
        bio.pop("all_drivers", None)
        if self._session_all_drivers:
            bio["all_drivers_count"] = len(self._session_all_drivers)
        prof["bios_driver_info"] = bio

    @staticmethod
    def _read_worker_driver_rows(worker: object | None) -> list:
        if worker is None:
            return []
        path = str(getattr(worker, "result_path", "") or "").strip()
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    return data
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        return list(getattr(worker, "rows_result", None) or [])

    def _cleanup_drv_all_load_thread(self) -> None:
        thread = self._drv_all_load_thread
        worker = self._drv_all_load_worker
        self._drv_all_load_thread = None
        self._drv_all_load_worker = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    @QtCore.Slot(int)
    def _on_drv_all_devices_loaded(self, count: int) -> None:
        if self._shutting_down:
            return
        self._session_log_end(
            "load_devices",
            f"Loaded {count} device(s)",
            "_session_log_load_token",
            extra={"device_count": count},
        )
        quiet = getattr(self, "_drv_all_load_quiet", False)
        self._drv_all_load_quiet = False
        chaining_search = self._after_hw_driver_search == "checked"
        if quiet:
            if (
                not chaining_search
                and hasattr(self, "_task_progress_frame")
                and self._task_progress_frame.isVisible()
            ):
                self._end_task_progress()
        elif not chaining_search:
            self._end_task_progress()
        elif chaining_search:
            self._set_task_progress(label="Updating device list…", maximum=0)
        self._set_refresh_device_list_ui(enabled=True)
        self._drv_load_apply_quiet = quiet
        self._drv_load_apply_count = count
        self._drv_load_apply_worker = self._drv_all_load_worker
        QtCore.QTimer.singleShot(50, self._apply_loaded_driver_rows_deferred)

    def _apply_loaded_driver_rows_deferred(self) -> None:
        if self._shutting_down:
            return
        quiet = getattr(self, "_drv_load_apply_quiet", False)
        worker = getattr(self, "_drv_load_apply_worker", None)
        count = getattr(self, "_drv_load_apply_count", 0)
        rows = self._read_worker_driver_rows(worker)
        n = len(rows) if rows else (count if count >= 0 else 0)
        prof = self._hardware_profile
        if prof is not None and rows:
            self._attach_all_drivers_to_profile(prof, rows)
            self._all_devices_loaded = True
        self._drv_tab_ui_stale = True
        if prof is not None:
            self._update_drivers_tab_status_only(prof)
        self.statusBar().showMessage(
            f"Loaded {n} device(s) in memory — open Drivers tab when ready.",
            12000,
        )
        self._session_hw_inventory_ready = True
        if self._drivers_tab_is_active():
            QtCore.QTimer.singleShot(150, self._populate_drivers_tab)
        self._sync_driver_workflow_buttons()
        if not quiet and prof is not None and rows and app_set.is_full_install_mode(
            self._settings
        ):
            QtCore.QTimer.singleShot(
                3000,
                lambda p=prof: self._start_save_hardware_profile(p),
            )
        if self._after_hw_driver_search:
            QtCore.QTimer.singleShot(
                500,
                self._finish_hw_then_continue_driver_search,
            )

    def _start_save_hardware_profile(self, prof: dict) -> None:
        if self._shutting_down:
            return
        if self._hw_save_thread and self._hw_save_thread.isRunning():
            return
        rows = self._full_driver_rows(prof)
        self._hw_save_thread = QtCore.QThread()
        self._hw_save_worker = SaveHardwareProfileWorker(prof, all_drivers=rows)
        self._hw_save_worker.moveToThread(self._hw_save_thread)
        self._hw_save_thread.started.connect(self._hw_save_worker.run)
        self._hw_save_worker.finished.connect(self._hw_save_thread.quit)
        self._hw_save_thread.finished.connect(self._cleanup_hw_save_thread)
        self._hw_save_thread.start()

    def _cleanup_hw_save_thread(self) -> None:
        self._hw_save_thread = None
        self._hw_save_worker = None

    @QtCore.Slot(str)
    def _on_drv_all_devices_load_failed(self, err: str) -> None:
        if self._shutting_down:
            return
        self._session_log_end(
            "load_devices",
            f"Load failed: {err[:200]}",
            "_session_log_load_token",
            status="error",
        )
        quiet = getattr(self, "_drv_all_load_quiet", False)
        self._drv_all_load_quiet = False
        chaining = self._cancel_chained_driver_search_workflow()
        if quiet:
            if self._task_progress_frame.isVisible():
                self._end_task_progress()
        else:
            self._end_task_progress()
        self._set_refresh_device_list_ui(enabled=True)
        if quiet:
            msg = f"Full device list could not load: {err[:80]}"
            if chaining:
                msg += " Driver update search was cancelled."
            detail = f"Could not load all devices:\n{err}"
            if chaining:
                detail += (
                    "\n\nThe driver update search was cancelled. "
                    "Fix the issue and click Search again."
                )
            self._show_actionable_error("Device list", msg, detail)
        elif not self._shutting_down:
            detail = f"Could not load all devices:\n{err}"
            if chaining:
                detail += (
                    "\n\nThe driver update search was cancelled. "
                    "Fix the issue and click Search again."
                )
            QtWidgets.QMessageBox.warning(self, "Device list", detail)
        self._sync_driver_workflow_buttons()
