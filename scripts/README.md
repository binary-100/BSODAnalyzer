# BSOD Analyzer — `scripts/` index

Agent and maintainer utilities. Run from **repo root** unless noted (`py -3 scripts\<name>.py`).

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
| `build_amd_logo_png.py` | AMD vendor icon (`assets/vendor_icons/amd.png`) |
| `build_pause_policy.bat` | CI/agent non-interactive build helper |
| `save_stable_build.bat` | Manual stable archive → Desktop `BSODAnalyzer_StableBuilds` |

## Module boundaries (maintainability)

Catalog/crash/GUI splits are **complete** (6.5.0). Module map and slice history: [`CATALOG_MODULE_SPLIT.md`](../docs/CATALOG_MODULE_SPLIT.md) · [`FACADE_ORCHESTRATION.md`](../docs/FACADE_ORCHESTRATION.md). One-time `extract_*.py` slicers were removed 2026-09-03 — use git history if you need the old automation.

## Vendor maps & assets

| Script | Purpose |
|--------|---------|
| `build_amd_gpu_map.py` | AMD GPU ID → marketing name map |
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
| `firmware_ssd_coverage_audit.py` | SSD firmware coverage (writes `firmware_ssd_coverage_audit.json`) |
| `firmware_peripheral_coverage_audit.py` | USB/peripheral firmware coverage (writes `firmware_peripheral_coverage_audit.json`) |
| `simulate_catalog_rejections.py` | Rejection rule simulation |
| `catalog_layout_preview.py` | Catalog table layout preview → `docs/catalog_layout_previews/` |

## Package analysis & misc

| Script | Purpose |
|--------|---------|
| `analyze_amd_chipset_package.py` | AMD chipset CAB inspection |
| `probe_nvidia_psid_pfid.py` | NVIDIA PSID/PFID probe |
| `probe_gui_bootstrap.py` | Qt bootstrap probe |
| `verify_gui_launch.py` | GUI launch smoke |

---

**Adding scripts:** prefix with `diag_`, `live_`, or `compare_` when possible; document here under the matching section.
