# BSOD Analyzer — `scripts/` index

One-off and agent utilities. Run from repo **`app\`** unless noted. Paths below are relative to `app\scripts\`.

**Do not move scripts casually** — batch files, docs, and agents reference these paths.

---

## Version & build

| Script | Purpose |
|--------|---------|
| `apply_version.py` | Sync `VERSION.txt`, dist README, presets from `bsod_analyzer.py` |
| `sync_install_fallbacks.py` | Refresh shipped WinDbg MSIX fallback URL/version from winget-pkgs GitHub |
| `sync_dist_readme.py` | Refresh bundled `BSODAnalyzer_v6\README.txt` |
| `finalize_portable_dist.py` | Post-PyInstaller portable layout fixes |
| `build_app_icon.py` | Regenerate application icon assets |
| `build_pause_policy.bat` | CI/agent non-interactive build helper |
| `save_stable_build.bat` | Manual stable archive → Desktop `BSODAnalyzer_StableBuilds` |

## Module extraction (maintainability)

Read the matching script **before** re-planning a slice. Status: [`CATALOG_MODULE_SPLIT.md`](../docs/CATALOG_MODULE_SPLIT.md).

### Catalog (`driver_catalog.py`)

| Script | Purpose |
|--------|---------|
| `extract_catalog_scoring.py` | Scoring, version compare, package dates |
| `extract_catalog_offer_pipeline.py` | enrich/sort/filter offers, `_finalize_catalog_offers` |
| `extract_catalog_oem_live.py` | Live OEM API fetch |
| `extract_catalog_mscatalog_session.py` | MSCatalog session / batch warm |
| `extract_catalog_device_profiles.py` | GPU/chipset/audio/network profiles |
| `extract_catalog_oem_filters.py` | OEM brand alignment, PC-maker rejects |
| `extract_catalog_row_rejects.py` | Row rejection, HWID match, MSCatalog row filters |
| `extract_catalog_device_context.py` | Device label, vendor/chipset/GPU classification, scan exclusion |
| `extract_catalog_tier_policy.py` | Tier/deferral/OEM-skip policy, MSCatalog defer gate |
| `extract_catalog_offer_status.py` | Offer status eligibility, summarize_offer_status |
| `extract_catalog_none_reason.py` | None-reason classification, coverage-gap detection |
| `extract_catalog_offer_compare.py` | Per-offer compare / uncertain resolution (see `_build_slice_modules.py`) |
| `extract_catalog_realtek_queries.py` | Realtek UAD catalog queries |
| `extract_catalog_mscatalog_queries.py` | MSCatalog search query builders |
| `extract_catalog_chipset_comparison.py` | Chipset/platform comparison (see `_build_slice_batch2.py`) |
| `remove_catalog_installed_packages.py` | Drop installed-package block after `catalog_installed_packages.py` extract |

### Crash report

| Script | Purpose |
|--------|---------|
| `extract_bsod_minidump.py` | Minidump / CDB slice from `bsod_analyzer.py` |
| `extract_analyzer_gather.py` | Run Analysis gather → `analyzer_gather.py` (uses `_ba()` for test patch compat) |
| `extract_analyzer_hardware.py` | Hardware profile scan → `analyzer_hardware.py` (**re-measure line range after gather extract**) |
| `extract_bsod_crash_report.py` | Crash report / recommendations slice |
| `extract_crash_report_timeline.py` | Timeline slice → `crash_report_timeline.py` |
| `extract_crash_report_culprit.py` | Culprit device matching → `crash_report_culprit.py` |
| `extract_crash_report_fix_plan.py` | Fix focus / platform links → `crash_report_fix_plan.py` |
| `extract_crash_report_format.py` | Text report + display model → `crash_report_format.py` |
| `extract_crash_report_narrative.py` | Cause typing + confidence/narrative → `crash_report_narrative.py` |

### GUI mixins

| Script | Purpose |
|--------|---------|
| `extract_gui_mixin_shell.py` | Shell init / startup (phase 1) |
| `extract_gui_mixin_shell_phase2.py` | Settings, catalog layout, task progress, maintenance |
| `extract_gui_mixin_shell_phase3.py` | Lifecycle, window chrome, tabs, catalog shell |
| `extract_gui_mixin_catalog_scan.py` | Catalog scan workers + batch merge |
| `extract_gui_mixin_catalog_phase2.py` | Packages, install, export mixins |
| `extract_gui_mixin_drivers_table.py` | Unified drivers table styling / populate |
| `extract_gui_mixin_drivers_inventory.py` | HW scan + full driver list workers |
| `extract_gui_mixin_drivers_workflow.py` | Search workflow, crash-linked auto-check |
| `extract_gui_mixin_firmware_splits.py` | Firmware tab workflow / inventory / table / scan |
| `split_gui_modules.py` | Historical GUI mixin split helper |

### Other

| Script | Purpose |
|--------|---------|
| `extract_amd_chipset_installer.py` | AMD chipset CAB / installer inspection (also under Package analysis) |

## Vendor maps & assets

| Script | Purpose |
|--------|---------|
| `build_amd_gpu_map.py` | AMD GPU ID → marketing name map |
| `build_amd_logo_png.py` | AMD logo asset |
| `build_intel_graphics_map.py` | Intel graphics map |
| `build_nvidia_gpu_map.py` | NVIDIA GPU map |
| `refresh_vendor_icons.py` | Vendor tab icon refresh |
| `sign_vendor_manifest.py` | HMAC-sign remote lookup manifest JSON |

## Diagnostics (`diag_*`)

Local debugging — safe to run on a dev machine; not part of CI.

| Script | Purpose |
|--------|---------|
| `diag_driver_catalog.py` | Catalog pipeline probes |
| `diag_full_scan_timing.py` | End-to-end scan timing breakdown |
| `diag_realtek_audio.py` / `diag_realtek_batch.py` | Realtek audio catalog paths |
| `diag_nvidia_*.py` | NVIDIA scrape/parse/process probes |
| `diag_dell_product.py` | Dell product ID resolution |
| `diag_vendor_endpoints.py` | Vendor HTTP endpoint smoke |
| `diag_wu_nvidia.py` | WU NVIDIA row inspection |
| `diag_after_fix.py` | Post-fix verification helper |

## Live machine probes (`live_*`)

Require network and/or real hardware; longer runs.

| Script | Purpose |
|--------|---------|
| `live_build_smoke.py` | Frozen exe smoke |
| `live_machine_probe.py` | Hardware/inventory probe |
| `live_workflow_timing.py` | Workflow wall-clock |
| `live_validate_analysis.py` | Live analysis validation |
| `live_populate_export_timing.py` | Export populate timing |
| `live_probe_gating.py` | Catalog gating on live machine |
| `live_firmware_*.py` | Firmware discovery / scan / secondary tier |

## Compare, audit & capture

| Script | Purpose |
|--------|---------|
| `verify_facade_gate.cmd` / `verify_facade_gate.py` | **T3 gate** — facade audit + probe + **records `facade` proof** |
| `verify_agent_report.cmd` / `verify_agent_report.py` | **Proof verifier** — `--require facade,t2,t4` (exit 0 = gates actually ran on this tree) |
| `agent_gate_proof.py` | Proof read/write library (`docs/.agent_gate_proof.json`) |
| `audit_facade_complete.py` | Full facade static/runtime scan → `docs/_FACADE_AUDIT_REPORT.txt` |
| `probe_ba_symbols.py` | Runtime resolve all `_ba('…')` and `core.*` on `bsod_analyzer` |
| `compare_catalog_scan_timings.py` | Scan timing A/B |
| `compare_catalog_exports.py` | Export diff |
| `compare_driver_update_baselines.py` | Driver update baseline diff |
| `capture_driver_update_baseline.py` | Save driver update baseline |
| `audit_vendor_apis.py` | Vendor API health audit |
| `run_lookup_audit_now.py` | Lookup manifest audit |
| `firmware_ssd_coverage_audit.py` | SSD firmware coverage |
| `firmware_peripheral_coverage_audit.py` | USB/peripheral firmware coverage |
| `simulate_catalog_rejections.py` | Rejection rule simulation |
| `catalog_layout_preview.py` | Catalog table layout preview |

## Package analysis & misc

| Script | Purpose |
|--------|---------|
| `analyze_amd_chipset_package.py` | AMD chipset CAB inspection |
| `extract_amd_chipset_installer.py` | See § Module extraction → Other |
| `probe_nvidia_psid_pfid.py` | NVIDIA PSID/PFID probe |
| `_map_chipset_to_system.py` | Chipset → system row mapping helper |
| `_diff_scan_exports.py` | Scan export diff (internal) |

---

**Adding scripts:** prefix with `diag_`, `live_`, `extract_`, or `compare_` when possible; document here under the matching section.
