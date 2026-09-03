# Upgrade program — start here

**One folder** for the next major BSOD Analyzer upgrade. Isolated from shipped product docs and production source.

| | |
|---|---|
| **Last updated** | 2026-08-26 |
| **Canonical root** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\` |
| **Tier 2 (agents watch)** | [`../ROADMAP.md`](../ROADMAP.md) § **Approved intent** |
| **Parked (hidden)** | [`parked/PARKED.md`](parked/PARKED.md) |
| **Build gate** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\.cursor\rules\design-tier-gate.mdc` |

---

## Folder layout

```
upgrade/
  README.md
  DESIGN_TIERS.md
  PLANNING_AGENT.md
  BUILD_HANDOFF.md
  inbox/           ← Tier 1 Exploration
  plans/           ← Tier 3 Design
  parked/          ← hidden; not agent default
```

---

## Approved intent (Tier 2 — on ROADMAP)

| Name | PLAN |
|------|------|
| **Rescue: bootable USB for offline target PC** | [`plans/RESCUE_USB_PLAN.md`](plans/RESCUE_USB_PLAN.md) |
| **Analysis: built-in minidump engine (no CDB install)** | [`plans/NATIVE_DUMP_ENGINE_PLAN.md`](plans/NATIVE_DUMP_ENGINE_PLAN.md) |
| **UX: guided diagnosis in plain language + hardware guidance** | [`plans/GUIDED_DIAGNOSTIC_PLAN.md`](plans/GUIDED_DIAGNOSTIC_PLAN.md) |

**Work queue:** empty. **Exploration (Tier 1):** Action Plan checklist — [`inbox/EXPLORATION_LOG.md`](inbox/EXPLORATION_LOG.md).

Index: [`plans/NEXT_UPGRADE_INDEX.md`](plans/NEXT_UPGRADE_INDEX.md) · Process: [`DESIGN_TIERS.md`](DESIGN_TIERS.md)

---

## Agents

| Session | Start |
|---------|--------|
| Maintenance | `AGENTS.md` + `PRODUCT_REFERENCE.md` |
| Upgrade overview | This file + `plans/NEXT_UPGRADE_INDEX.md` |
| Build one phase | `BUILD_HANDOFF.md` + one PLAN + user phase |
| Planning only | `PLANNING_AGENT.md` |
| Parked ideas | **Only if user asks** → `parked/PARKED.md` |

Current snapshot: [`DESIGN_TIERS.md`](DESIGN_TIERS.md) § Current state.
