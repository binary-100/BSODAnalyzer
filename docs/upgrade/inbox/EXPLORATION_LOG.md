# Exploration log (Tier 1)

Spitball and active exploration. **Not build order.** **Not** on ROADMAP.

| | |
|---|---|
| **Last updated** | 2026-08-30 |
| **Process** | [`../DESIGN_TIERS.md`](../DESIGN_TIERS.md) |
| **Promote to Tier 2** | Add row to [`../../ROADMAP.md`](../../ROADMAP.md) § Approved intent |

---

## Active exploration

| Name | Status | Notes |
|------|--------|--------|
| **Action Plan: step checklist and session progress** | **Active** | UI direction (Concept B) in [`../../action_plan_tab_mockups.html`](../../action_plan_tab_mockups.html). Flow and behavior **still being figured out**. Draft notes: [`../../ACTION_PLAN_CHECKLIST_PLAN.md`](../../ACTION_PLAN_CHECKLIST_PLAN.md). **→ Tier 2 when** checklist behavior and user flow are decided. |

---

## Open questions (not list rows — notes on a parent track)

| Question | Parent track |
|----------|--------------|
| Dump depth: native vs bundled CDB vs hybrid | **Analysis: built-in minidump engine** → [`../plans/NATIVE_DUMP_ENGINE_PLAN.md`](../plans/NATIVE_DUMP_ENGINE_PLAN.md) |
| Interactive debugger UX (not default surface) | Analysis / guided UX |
| Rescue boot OS: Linux vs WinPE vs hybrid | **Rescue: bootable USB** → [`../plans/RESCUE_BOOT_ENVIRONMENT.md`](../plans/RESCUE_BOOT_ENVIRONMENT.md) |

---

## Archive (promoted — historical)

| Idea | Now at |
|------|--------|
| Bootable rescue USB | Approved intent → [`../plans/RESCUE_USB_PLAN.md`](../plans/RESCUE_USB_PLAN.md) |
| Replace WinDbg/CDB for users | Approved intent → [`../plans/NATIVE_DUMP_ENGINE_PLAN.md`](../plans/NATIVE_DUMP_ENGINE_PLAN.md) |
| Deep diagnostics + plain UX | Approved intent → [`../plans/GUIDED_DIAGNOSTIC_PLAN.md`](../plans/GUIDED_DIAGNOSTIC_PLAN.md) |
| Tier workflow (explore → intent → design → build) | Meta → [`../DESIGN_TIERS.md`](../DESIGN_TIERS.md) |

---

## Context (product direction)

- **End product:** one flash drive — **rescue** + **maintenance**.
- **Foundation shipped:** ROADMAP Phases 1–7 ☑ · maintainability 6.5.0 ☑.
- **Parked ideas:** [`../parked/PARKED.md`](../parked/PARKED.md) — not active lists.
- **Maintenance USB data (build queued 2026-08-30):** [`../plans/MAINTENANCE_USB_DATA_PLAN.md`](../plans/MAINTENANCE_USB_DATA_PLAN.md) · opener [`../handoffs/active/HANDOFF_WQ001_maintenance_usb_data.md`](../handoffs/active/HANDOFF_WQ001_maintenance_usb_data.md).

See [`../plans/NEXT_UPGRADE_INDEX.md`](../plans/NEXT_UPGRADE_INDEX.md).
