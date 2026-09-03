# Maintenance USB — PC-local data (Tier 3 / infrastructure)

**Status:** Approved for build · **Work queue:** [`ROADMAP.md`](../../ROADMAP.md) § Work queue  
**Decision date:** 2026-08-30 (product design — aligns portable launcher with Maintenance USB model)

| | |
|---|---|
| **Problem** | Portable mode writes catalog cache, settings, and other state beside the exe (often on the USB stick). That conflicts with privacy/policy goals and novice UX (“why is my stick full of PC data?”). |
| **Goal** | **Maintenance USB** = run from removable media; **all durable app state lives on the target PC** (`%LOCALAPPDATA%\BSODAnalyzer\`). The stick holds only the launcher/runtime unless the **user explicitly saves** a file (export dialog, baseline save, etc.). |
| **Not in scope** | Rescue boot USB (mode 3) · Action Plan checklist UI · Forcing full install · Feature gates between portable and local install |

---

## Deployment modes (vocabulary)

| Mode | Launch | Durable data home |
|------|--------|-------------------|
| **Maintenance USB** | `BSODAnalyzer.exe` from USB on **running Windows** | **Target PC** — `%LOCALAPPDATA%\BSODAnalyzer\` |
| **Local install** | Shortcut / copied folder on PC | Same PC-local store (no capability difference) |
| **Rescue USB** | Boot from USB (future) | Rescue plan — separate track |

**Rule:** `install_mode: portable` means **launcher layout**, not “persist beside exe.”

---

## Current behavior (wrong for Maintenance USB)

| Data | Today (portable) | Target |
|------|------------------|--------|
| `settings.json` | `BSODAnalyzer_portable\` beside exe (created first launch) | PC-local |
| Catalog cache | `BSODAnalyzer_portable\driver_catalog\<fingerprint>\` | PC-local per machine fingerprint |
| Default export folder helper | `BSODAnalyzer_portable\exports\` | PC-local default; user Save dialog may pick any path including USB |
| Vendor endpoint cache | `_ensure_dir()` → beside exe | PC-local |
| Session log (portable) | `%TEMP%\BSODAnalyzer\` | OK (ephemeral) |
| User-chosen export/baseline path | User dialog | Unchanged — user owns path |

Full install (`install_mode: full`) continues using `%LOCALAPPDATA%\BSODAnalyzer\` as today — unify portable-maintenance paths with the same root where practical.

---

## PC-local layout (proposed)

```
%LOCALAPPDATA%\BSODAnalyzer\
  settings.json                    # portable-maintenance prefs for this PC
  vendor_endpoints.json            # shared caches (if still file-based)
  driver_catalog\
    <machine_fingerprint>\         # WU + OEM catalog blobs (unchanged schema)
      wu_driver_cache.json
      oem_catalog_cache.json
  exports\                         # default export folder when Desktop is OneDrive-synced
  portable_redirects\              # existing — stick exe hash → settings path if needed
```

**Keying:** Catalog and machine-specific state use existing `machine_fingerprint()` / `fingerprint_cache_dirname()`. Settings are **per target PC**, not per USB stick.

---

## Phased checklist

| Phase | Name | Required | Status |
|-------|------|----------|--------|
| **M1** | Route portable `_config_dir()` / `catalog_cache_dir()` / `_settings_path()` to PC-local — stop writing beside exe | yes | ☑ |
| **M2** | One-time migration: read legacy `BSODAnalyzer_portable\` on stick → PC-local; do not require user action | yes | ☑ |
| **M3** | Default exports: never auto-create stick-side `exports\`; prefer PC-local or Desktop per existing OneDrive logic | yes | ☑ |
| **M4** | Tests + docs (`PRODUCT_REFERENCE`, `AGENTS.md`, dist README, `finalize_portable_dist.py`) | yes | ☑ |

**Do not implement M5+ in this slice** (future repair/checklist state uses same PC-local root).

---

## M1 — Core routing

**Primary file:** `app_settings.py`

1. Add `maintenance_data_dir()` (or rename conceptually): `%LOCALAPPDATA%\BSODAnalyzer\`, mkdir on use.
2. When `install_mode` is portable (maintenance launcher):
   - `_config_dir()` → `maintenance_data_dir()` (not `portable_settings_dir()`).
   - `catalog_cache_dir()` → `maintenance_data_dir() / "driver_catalog" / <fingerprint>` (drop stick path).
3. `_ensure_install_mode_chosen()` may still call `save_settings` — file must land PC-local.
4. Keep `portable_settings_dir()` for **migration read only** (M2) and dist seeding if needed; no new writes there after M1.
5. Revisit `data_sync_warning()` — warn on stick path only if legacy folder detected, not as normal operation.

**Also grep:** `portable_settings_dir()`, `_ensure_dir()`, `catalog_cache.py` migrate paths, `oem_enterprise_catalog.py`, `vendor_endpoint_health.py`, `vendor_extractor_repair.py`.

---

## M2 — Migration (retired 2026-09-01)

**Superseded:** Stick-side `BSODAnalyzer_portable\` migration removed after WQ-001 M1 shipped PC-local writes. The app no longer reads settings or catalog from beside the exe; orphan folders may remain on old USB copies (optional OneDrive warning only).

~~On first run after upgrade, if `<exe_dir>/BSODAnalyzer_portable/` exists:~~

~~1. Merge `settings.json` into PC-local …~~

**Catalog:** `migrate_legacy_catalog_cache` flat→fingerprint runs from PC-local `driver_catalog\` only.

---

## M3 — Exports

- `local_export_directory()` must not resolve beside exe in portable mode.
- User explicit Save / Export paths unchanged.
- Update `finalize_portable_dist.py` / dist `README.txt`: remove implication that `BSODAnalyzer_portable\` is normal for new runs (may keep empty seeded folder with README pointing to PC-local, or stop seeding — prefer **no stick data folder** in new builds).

---

## M4 — Verification

| Gate | Command |
|------|---------|
| Settings defaults | `py -3 tests\test_settings_defaults.py` |
| Data dir / portable | `py -3 tests\test_data_dir_settings.py` |
| Catalog cache | `py -3 tests\test_driver_catalog_quality.py` (cache sections) |
| Portable smoke | `py -3 tests\test_portable_build_smoke.py` if layout docs change |
| Full suite before done | `run_tests.bat` from the project root |

**Acceptance (manual):**

1. Run portable exe from a removable drive (or test path mimicking stick).
2. Run catalog scan / save settings / dismiss a prompt.
3. Confirm **no new files** under `<exe>\BSODAnalyzer_portable\` except migration artifact.
4. Confirm `%LOCALAPPDATA%\BSODAnalyzer\` contains settings + catalog cache.
5. Export via dialog to user-chosen folder — still works.

Update [`PRODUCT_REFERENCE.md`](../../PRODUCT_REFERENCE.md) §3.7 and [`AGENTS.md`](../../../AGENTS.md) portable-first table.

---

## Out of scope / non-goals

- No artificial limits on diagnostics for portable vs install.
- No Action Plan checkbox UI.
- No deletion of full-install mode.
- Rescue USB data layout.

---

## Handoff

**Build handoff:** create `docs/handoffs/active/HANDOFF_WQnnn_<slug>.md` when slice is Active; **delete** when Done — see [`../handoffs/README.md`](../handoffs/README.md).
