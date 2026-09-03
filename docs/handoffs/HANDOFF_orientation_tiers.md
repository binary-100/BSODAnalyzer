# Handoff — layout and tier model

## Handoff registry

| Field | Value |
|-------|-------|
| **handoff_id** | HANDOFF_orientation_tiers |
| **kind** | orientation |
| **status** | active |
| **multi_agent** | no |
| **wq_id** | |
| **plan** | |
| **phases** | |
| **agents_remaining** | |
| **completed** | |

**Session opener (only — give the other agent this single line):**

`Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\HANDOFF_orientation_tiers.md and confirm.`

---

Project layout and tier model updated 2026-08-26 (work queue row updated 2026-08-30). Do not use removed paths. Do not fork generic rules in BSOD.

## Read first (in order)

1. `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\AGENTS.md`
2. `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\README.md`
3. `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\DESIGN_TIERS.md`
4. `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\ROADMAP.md` (Work queue + Approved intent only)

## Tier model (summary)

- Tier 1 Exploration: upgrade/inbox/ — not on ROADMAP (Action Plan checklist is active here)
- Tier 2 Approved intent: ROADMAP section — three upgrade tracks; agents watch here
- Tier 3 Design: upgrade/plans/ — links from Tier 2 rows; does NOT remove Tier 2 rows
- Build: ROADMAP work queue + "implement Phase X" only — see work queue for current **Next**
- Parked: upgrade/parked/PARKED.md — hidden; do NOT read unless I ask

## Approved intent (three tracks, outcome names)

- Rescue: bootable USB for offline target PC
- Analysis: built-in minidump engine (no CDB install)
- UX: guided diagnosis in plain language + hardware guidance

## Build gate

`C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\.cursor\rules\design-tier-gate.mdc`

## Product truth

`C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\PRODUCT_REFERENCE.md`

## Agent Starter Pack

Edit generic rules in `C:\Users\binar\OneDrive\Desktop\AgentStarterPack\pack\rules\` only (`PACK_MAINTENANCE.md`).

## Confirm with three bullets

1. Approved intent vs work queue vs Parked
2. What is not buildable without promotion
3. Where Action Plan checklist lives (Tier 1 exploration)
