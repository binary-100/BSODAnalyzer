"""Firmware tab workflow buttons and component scan entry."""

from __future__ import annotations

from gui_app_context import *  # noqa: F403


class GuiFirmwareWorkflowMixin:
    def _firmware_tab_index(self) -> int:
        if not hasattr(self, "_firmware_tab_widget"):
            return -1
        return self.tabs.indexOf(self._firmware_tab_widget)

    def _on_main_tab_changed(self, index: int) -> None:
        self._sync_global_toolbar_for_tab(index)
        if index == self._drivers_tab_index():
            self._sync_catalog_tab_layout("drivers")
            self._maybe_notify_portable_cache_mismatch()
            self._defer_stale_catalog_refresh_prompt()
            if self._drv_tab_ui_stale or not self._drv_unified_cache:
                prof = self._hardware_profile
                if prof is None and self._last_model:
                    prof = self._profile_from_model(self._last_model)
                    if prof.get("bios_driver_info") or prof.get("system_ctx"):
                        self._hardware_profile = prof
                if prof:
                    self._apply_driver_only_view_defaults()
                    self._populate_drivers_tab()
                self._sync_driver_workflow_buttons()
        if index == self._firmware_tab_index():
            self._sync_catalog_tab_layout("firmware")
            prof = self._hardware_profile
            if prof:
                self._populate_firmware_tab()

    def _firmware_scan_workflow_busy(self) -> bool:
        return (
            self._ssd_fw_thread is not None and self._ssd_fw_thread.isRunning()
        ) or (self._fw_thread is not None and self._fw_thread.isRunning())

    def _fw_components_ready_for_search(self) -> bool:
        return bool(self._ssd_firmware_loaded)

    def _firmware_catalog_search_busy(self) -> bool:
        return self._fw_thread is not None and self._fw_thread.isRunning()

    def _fw_search_button_enabled(self) -> bool:
        if not self._fw_components_ready_for_search():
            return False
        if self._firmware_catalog_search_busy():
            return False
        return bool(self._fw_checked_target_keys())

    def _sync_fw_workflow_buttons(self) -> None:
        if not hasattr(self, "fw_btn_scan_components"):
            return
        import gui_theme as theme

        load_running = (
            self._ssd_fw_thread is not None and self._ssd_fw_thread.isRunning()
        )
        catalog_busy = self._firmware_scan_workflow_busy()
        if load_running:
            self.fw_btn_scan_components.setEnabled(False)
        else:
            self.fw_btn_scan_components.setEnabled(not catalog_busy)
            if self.fw_btn_scan_components.isEnabled():
                self.fw_btn_scan_components.setText(theme.BTN_FW_LOAD)
        search_ok = False
        if hasattr(self, "fw_btn_check"):
            search_ok = self._fw_search_button_enabled()
            self.fw_btn_check.setEnabled(search_ok)
        if hasattr(self, "fw_btn_scan_components") and hasattr(self, "fw_btn_check"):
            self._apply_catalog_workflow_highlight(
                self.fw_btn_scan_components,
                self.fw_btn_check,
                search_enabled=search_ok,
                load_enabled=self.fw_btn_scan_components.isEnabled(),
            )

    def _on_scan_for_components(self) -> None:
        """Load BIOS/SSD inventory for the Firmware tab (step 1 — not catalog search)."""
        idx = self._firmware_tab_index()
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        if self._firmware_scan_workflow_busy():
            self.statusBar().showMessage("Component load already in progress…", 5000)
            return
        self._fw_include_user_customized = False
        self._sync_fw_workflow_buttons()
        self._ensure_ssd_firmware_inventory(
            force_refresh=True,
        )
