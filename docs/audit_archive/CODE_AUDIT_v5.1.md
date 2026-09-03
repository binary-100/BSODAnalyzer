# BSOD Analyzer — Code audit (v5.1)

**Date:** 2026-05-30  
**Scope:** Qt GUI, core modules, full-install caches, build

## Architecture

| Module | Role |
|--------|------|
| `bsod_analyzer.py` | Analysis, recommendations, CDB, report formatting |
| `bsod_runtime.py` | PowerShell runner, paths, export |
| `bsod_events.py` | Event log queries, crash timeline, reliability bundle |
| `bsod_hardware_wmi.py` | WMI hardware profile, driver inventory, device lists |
| `bsod_gui_qt.py` | PySide6 UI + background workers |
| `bsod_gui_workers.py` | Shared `QThread` helper |
| `driver_index.sqlite` | Driver + firmware check memory (replaces `check_cache.json`) |
| `hardware_profile_cache.sqlite` | Gzip JSON device list (full install) |
| `catalog_cache.py` | On-disk WU + OEM driver database |

**Entry:** `bsod_gui_qt.run_gui_qt()` (frozen exe default). CLI: `bsod_analyzer.py --cli`.  
**Removed:** Legacy Tkinter GUI.

## Caching / batching (no duplicate work)

- **WU drivers:** Session cache → disk (`wu_driver_cache.json`) → deep refresh on maintenance only.
- **OEM:** Session cache during refresh → disk (`oem_catalog_cache.json`) → routine checks read disk.
- **Driver checks:** `build_multi_device_driver_comparison` warms WU once, then parallel per-device compares.
- **Check results:** Single store in `driver_index.sqlite` (not JSON + SQLite).

## Full install

- Device list: SQLite + gzip, ~30-day freshness prompt.
- Maintenance wizard: user-initiated only; no scheduled tasks.
