# Driver verification (crash-linked) — phased plan

**Goal:** When logs point at a driver, name suspects, verify installed state, run catalog when justified, and report one evidence chain with confidence labels.

**Runtime status (6.4.67):** Phases 1–7 implemented in `driver_verification.py`. GUI Phase 6 auto-run uses `auto_crash_linked_catalog` (default on).

**Roadmap:** Phases 1–7 ☑ complete. Further crash-attribution work: [`ROADMAP.md`](ROADMAP.md) Phases 2–5.

---

## Phase 1 — Crash evidence

**Status:** Done (`gather_report_data`)

---

## Phase 2 — Build suspect list

**Status:** Done — `build_crash_suspect_list()`

---

## Phase 3 — Map suspects to devices

**Status:** Done — `map_suspects_to_devices()` (platform/chipset synthetic rows + manual hints)

---

## Phase 4 — Local verification

**Status:** Done — `verify_suspect_drivers_locally()`

---

## Phase 5 — Catalog gate

**Status:** Done — `gate_catalog_for_suspects()`

---

## Phase 6 — Catalog check

**Status:** Done

- Manual: Drivers tab → Search on crash-linked / Include rows
- **Auto (6.4.67):** After Run Analysis, `crash_linked_catalog_device_names()` + `DriverCatalogWorker` for gated rows (max ~6 devices)
- Merge: `apply_catalog_results_from_gui()` → `rebuild_verification_report_lines()`

---

## Phase 7 — Unified report

**Status:** Done

- Section **3b. DRIVER VERIFICATION** in text export
- **DRIVER ATTRIBUTION** in Quick Answer
- **Confidence ladder** in Summary (`build_crash_confidence_summary`)
- Action Plan: `merge_verification_action_steps()`

---

## Confidence ladder (novice-facing)

| Level | When |
|-------|------|
| **Verified** | Minidump matches latest incident and names faulting module |
| **Focus area** | Latest shutdown/boot event without matching dump; crash-linked platform/chipset focus |
| **Moderate** | Crash logged; driver not confirmed |
| **Unknown** | No recent crash events in targeted logs |

“What would change this” lists: matching minidump, enable dumps, verify chipset components.

---

## Tests

- `tests/test_driver_verification.py`
- `tests/test_crash_confidence.py`
