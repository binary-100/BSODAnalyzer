# Module index — BSOD Analyzer (flat root)

**Purpose:** Navigate **138** production modules at repo root without restructuring the tree.  
**Source:** [`docs/.audit_domain_expanded.json`](.audit_domain_expanded.json) · audit sections per [`AUDIT.md`](AUDIT.md) § Domain map.  
**Last updated:** 2026-09-03 · version: see [`VERSION.txt`](../VERSION.txt)

Task-oriented “start here” rows: [`AGENT_READINESS.md`](AGENT_READINESS.md) § Module navigation.

---

## D — BSOD analysis, hardware & reports

`action_plan_ui.py` · `analyzer_gather.py` · `analyzer_hardware.py` · `bsod_analyzer.py` · `bsod_crash_report.py` · `bsod_events.py` · `bsod_hardware_wmi.py` · `bsod_minidump.py` · `bsod_runtime.py` · `bsod_workflow.py` · `crash_report_culprit.py` · `crash_report_events.py` · `crash_report_fix_plan.py` · `crash_report_format.py` · `crash_report_narrative.py` · `crash_report_timeline.py` · `device_enrichment.py` · `driver_verification.py` · `gui_mixin_analysis.py` · `gui_mixin_minidump.py` · `log_attribution.py` · `log_read_windows.py` · `system_health_actions.py`

## E — GUI, threads, workers & theme

`bsod_gui_qt.py` · `bsod_gui_workers.py` · `fix_progress.py` · `gui_app_context.py` · `gui_app_icon.py` · `gui_catalog_parallel.py` · `gui_checkbox_style.py` · `gui_html_safe.py` · `gui_include_header.py` · `gui_mixin_action_plan.py` · `gui_mixin_analysis.py` · `gui_mixin_catalog.py` · `gui_mixin_catalog_export.py` · `gui_mixin_catalog_install.py` · `gui_mixin_catalog_layout.py` · `gui_mixin_catalog_packages.py` · `gui_mixin_catalog_scan.py` · `gui_mixin_catalog_shell.py` · `gui_mixin_drivers.py` · `gui_mixin_drivers_inventory.py` · `gui_mixin_drivers_table.py` · `gui_mixin_drivers_workflow.py` · `gui_mixin_firmware.py` · `gui_mixin_firmware_inventory.py` · `gui_mixin_firmware_scan.py` · `gui_mixin_firmware_table.py` · `gui_mixin_firmware_workflow.py` · `gui_mixin_lifecycle.py` · `gui_mixin_maintenance.py` · `gui_mixin_minidump.py` · `gui_mixin_settings.py` · `gui_mixin_shell.py` · `gui_mixin_system.py` · `gui_mixin_tabs.py` · `gui_mixin_task_progress.py` · `gui_mixin_vendor_health.py` · `gui_mixin_window_chrome.py` · `gui_qt_bootstrap.py` · `gui_signal_relay.py` · `gui_theme.py` · `gui_vendor_icons.py` · `gui_widgets.py`

## F — Settings, paths & portable-first

`app_settings.py` · `catalog_cache.py` · `hardware_cache.py` · `system_network_power.py`

## G — Driver catalog, index & vendors

`catalog_amd_fetch.py` · `catalog_chipset_comparison.py` · `catalog_device_comparison.py` · `catalog_device_context.py` · `catalog_device_profiles.py` · `catalog_device_roles.py` · `catalog_download.py` · `catalog_export.py` · `catalog_extended_fetch.py` · `catalog_http.py` · `catalog_installed_packages.py` · `catalog_intel_fetch.py` · `catalog_lru_cache.py` · `catalog_microsoft_fetch.py` · `catalog_microsoft_scoring.py` · `catalog_mscatalog_queries.py` · `catalog_mscatalog_session.py` · `catalog_multi_device.py` · `catalog_network_fetch.py` · `catalog_none_reason.py` · `catalog_nvidia_fetch.py` · `catalog_oem_filters.py` · `catalog_oem_live.py` · `catalog_oem_offers.py` · `catalog_offer_compare.py` · `catalog_offer_pipeline.py` · `catalog_offer_status.py` · `catalog_online_store.py` · `catalog_ps_batch.py` · `catalog_ps_context.py` · `catalog_ps_module.py` · `catalog_realtek_fetch.py` · `catalog_realtek_queries.py` · `catalog_row_rejects.py` · `catalog_scan_summary.py` · `catalog_scoring.py` · `catalog_system_actions.py` · `catalog_tier_policy.py` · `catalog_vendor_cache.py` · `catalog_vendor_offers.py` · `catalog_wu_scoring.py` · `driver_catalog.py` · `driver_index.py` · `driver_list_build.py` · `driver_version_identity.py` · `gpu_vendor_maps.py` · `gui_mixin_catalog.py` · `gui_mixin_catalog_export.py` · `gui_mixin_catalog_install.py` · `gui_mixin_catalog_packages.py` · `gui_mixin_catalog_scan.py` · `gui_mixin_drivers.py` · `gui_mixin_drivers_inventory.py` · `gui_mixin_drivers_table.py` · `gui_mixin_drivers_workflow.py` · `gui_mixin_vendor_health.py` · `oem_effective_version.py` · `oem_enterprise_catalog.py` · `vendor_download_resolve.py` · `vendor_endpoint_audit.py` · `vendor_endpoint_health.py` · `vendor_extractor_repair.py` · `vendor_extractors.py` · `vendor_fetch.py` · `vendor_page_render.py`

## H — Firmware

`firmware_catalog.py` · `firmware_peripheral_discovery.py` · `firmware_peripheral_installed.py` · `firmware_peripheral_vendors.py` · `firmware_ssd_vendors.py` · `gui_mixin_firmware.py` · `gui_mixin_firmware_inventory.py` · `gui_mixin_firmware_scan.py` · `gui_mixin_firmware_table.py` · `gui_mixin_firmware_workflow.py` · `vendor_firmware_fetch.py`

## I — Export, install & backup

`bsod_runtime.py` · `catalog_export.py` · `driver_backup.py` · `driver_install.py`

## J — Session, logging & preferences

`bsod_gui_log_cleanup.py` · `bsod_gui_preferences.py` · `log_cleanup.py` · `maintenance_log.py` · `session_log.py` · `timestamped_log_io.py`

## Other root modules

| Module | Notes |
|--------|--------|
| `product_version.py` | Version / product line helpers (build §C) |
| `conftest.py` | Pytest bootstrap (tests §A) |

**Scripts** (not root modules): see [`scripts/README.md`](../scripts/README.md).
