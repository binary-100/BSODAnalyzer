# BSOD Analyzer — Code audit snapshot (v5.2.18)

> **Note:** For the v6 driver catalog audit (OEM matching, cache identity, batch pipeline), see [`CODE_AUDIT_v6_catalog.md`](CODE_AUDIT_v6_catalog.md) in this folder. This file is the v5.2.17→5.2.18 wizard-removal cleanup record only.

Date: 2026-05-30

This document records the post–wizard-removal cleanup (v5.2.17 → v5.2.18).

## Current user workflow (portable and full install)

1. **Toolbar → Search for driver updates** — inventory if needed, then catalog check on **Include** devices.
2. **Drivers tab → Search included devices** — same workflow as the toolbar button.
3. **Drivers ⋮** — Refresh device list; **Refresh driver database** (full install).
4. **Tools** — Refresh driver database, export full install report, activity history, log cleanup.
5. **Firmware tab** — **Search for firmware updates** on checked components.

No launch popups, no hardware scope dialogs, no driver maintenance wizard.

## Shipped in v5.2.18

| Area | Change |
|------|--------|
| Copy | Firmware/Drivers banners, filter tooltips, About, preferences, first-run text |
| UX | Drivers tab button relabeled; Tools menu uses “full install” / “activity” wording |
| Hygiene | Removed `should_show_maintenance_primary_ui`, `_should_auto_hardware_scan_on_launch`, `use_checked_only`, `retry_hw`, orphan settings keys |
| Preferences | Removed inert “Scan hardware at launch” option |
| Docs | README, VERSION.txt, backlog updated |

## Intentionally kept

- **Log cleanup wizard** — crash logs/dumps only.
- **Driver pipeline batches** — still used for large **crash-report** auto-checks after analysis.
- **`touch_last_maintenance` / activity log** — internal names; user-facing text says “driver activity”.

## Shipped in v5.2.20

- Removed silent 35/150 caps in `build_multi_device_driver_comparison` — Include column is the only scope control
- Large-scan status hint (>20 devices) on status bar and Drivers hint panel

## Shipped in v5.2.19

- Driver pipeline simplified to **crash-report-only** (`_run_next_crash_report_driver_batch`)
- Removed dead maintenance pipeline (`_finish_driver_update_pipeline`, `_drv_pipeline_running`, etc.)
- BSOD analysis path unchanged: post-analysis checks remain async via `_schedule_crash_report_update_checks`

## Re-check after large changes

- Portable vs full install cache behavior
- Include defaults vs user overrides after force-refresh
- Crash Details refresh after hardware (full install + prior analysis)
- Packages panel vs Updates available filter consistency
