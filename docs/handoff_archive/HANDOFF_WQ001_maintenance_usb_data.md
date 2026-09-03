# Handoff — Maintenance USB PC-local data

## Handoff registry

| Field | Value |
|-------|-------|
| **handoff_id** | HANDOFF_WQ001 |
| **kind** | build |
| **status** | completed |
| **multi_agent** | no |
| **wq_id** | WQ-001 |
| **plan** | upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md |
| **phases** | M1-M4 |
| **agents_remaining** | |
| **completed** | 2026-08-31 |

**Session opener (only — give the other agent this single line):**

`Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\active\HANDOFF_WQ001_maintenance_usb_data.md and implement.`

---

## Instructions (for the agent that opens this file)

**Workspace:** project root is `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer` (no `app\` subfolder).

1. Read [`upgrade/BUILD_HANDOFF.md`](../../upgrade/BUILD_HANDOFF.md).
2. Read [`upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md`](../../upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md).
3. Implement **Phases M1 → M2 → M3 → M4 in order** (one phase at a time; do not skip ahead).
4. Follow [`AGENTS.md`](../../../AGENTS.md) — run `run_tests.bat` before claiming done (~8 min full suite; not a hang).
5. Do **not** start Action Plan checklist UI, native dump, guided diagnostic, or rescue tracks.
6. On completion: follow **`C:\Users\binar\.cursor\AgentStarterPack\pack\docs\WORK_COMPLETION.md`** and project `docs/WORK_COMPLETION.md` — preview archive only unless user confirms **`-Apply`**.

---

## User decision (summary)

| Decision | Detail |
|----------|--------|
| **Maintenance USB** | Exe on USB; **memory on the PC being serviced** |
| **Stick surface** | Launcher + runtime only — no catalog cache, no settings, no auto exports folder |
| **User exports** | Save dialog / explicit paths only — user may save to USB if they choose |
| **Security** | Avoid host-derived data accumulating on removable media (policy + privacy) |
| **Install vs portable** | Same capabilities — local install is packaging convenience, not a feature tier |

---

## What to change (start here)

| Area | File(s) |
|------|---------|
| Config root routing | `app_settings.py` — `_config_dir`, `catalog_cache_dir`, `_settings_path`, `_ensure_dir` |
| Catalog migration from stick | `catalog_cache.py` — `migrate_legacy_catalog_cache` |
| Enterprise manifest path | `oem_enterprise_catalog.py` |
| Vendor caches | `vendor_endpoint_health.py`, `vendor_extractor_repair.py` |
| First launch save | `bsod_gui_qt.py` — `_ensure_install_mode_chosen` (must write PC-local after M1) |
| Dist docs | `scripts/finalize_portable_dist.py`, `BSODAnalyzer_v6/README.txt`, `scripts/sync_dist_readme.py` |
| Tests | `tests/test_data_dir_settings.py`, catalog cache tests, add regression: portable exe path → LOCALAPPDATA writes |

**Existing helper:** `default_full_install_data_dir()` → `%LOCALAPPDATA%\BSODAnalyzer\` — reuse or alias for maintenance portable data; avoid duplicating two trees on the same PC.

---

## Acceptance checklist

- [x] M1: New portable sessions write **zero** durable files beside exe (except migration readme if used)
- [x] M2: Legacy `BSODAnalyzer_portable\` on stick migrated once to PC-local
- [x] M3: Default export folder not stick-side
- [x] M4: `PRODUCT_REFERENCE.md` §3.7 + `AGENTS.md` portable section updated
- [x] `run_tests.bat` exit 0

---

## Related design (do not implement in this slice)

- Tier 1 Action Plan checklist — [`ACTION_PLAN_CHECKLIST_PLAN.md`](../../ACTION_PLAN_CHECKLIST_PLAN.md) (future state also PC-local)
- Three deployment modes — [`upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md`](../../upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md) § vocabulary

**Confirm when done:** List paths written in a test portable run and where they landed.
