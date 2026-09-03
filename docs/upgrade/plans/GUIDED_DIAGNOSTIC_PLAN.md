# Guided diagnostic engine — design plan (Tier 3)

**Status:** Draft · **Tier 2:** ROADMAP **Approved intent** · **Not buildable until work queue + user approval**

| | |
|---|---|
| **Index** | [`NEXT_UPGRADE_INDEX.md`](NEXT_UPGRADE_INDEX.md) |
| **Today** | Quick Answer, confidence ladder, repair narrative, Action Plan |

Last updated: **2026-08-24**

---

## Goal

**More than log files:** correlate timeline, dumps, hardware signals, driver state, and change history — then present deep insight in **plain language**. When evidence points to **hardware**, guide the user toward **which component class or part** to replace (realistic v1: RAM, disk, GPU, PSU/thermal — not chip-level repair).

**Product principle:** Answer first, evidence second. Maximum analysis power; minimum debugger vocabulary in default UI.

## Non-goals (v1 surface — not permanent product limits)

- Exposing raw WinDbg command UX to default users (depth may still use debugger technology internally)
- Guaranteeing slot-level diagnosis (“DIMM2”) without strong WHEA/dump evidence
- Trimming exports for novice mode (display policy only — full export unchanged)

---

## Evidence layers

| Layer | Question | Today | Upgrade |
|-------|----------|-------|---------|
| L1 Timeline | What happened when? | Strong | + offline/rescue |
| L2 Attribution | What faulted? | CDB-dependent | Native dump engine |
| L3 Context | HW / heat / config? | WHEA, thermals, inventory | + change detection, suspicion score |
| L4 Correlation | Repeating pattern? | Recurring faulting module | Crash signatures |
| L5 Repair | What to do? | Action Plan, Drivers | + checklist (Concept B) |

---

## Display tiers (UX)

| Tier | Audience | Show | Hide in default |
|------|----------|------|-----------------|
| **D1 Novice** | Never updated anything | Plain English headline; ≤3 steps; traffic-light confidence | `.sys`, Event IDs, stacks |
| **D2 Comfortable** | Device Manager user | + driver name/version, timeline, “why confident” | Raw hex, bucket strings |
| **D3 Technician** | Shop / export | Stacks, Advanced panel, full export | — |

**Rule:** D1 never requires D3. Export stays complete (existing policy).

---

## Phased checklist

| Phase | Name | Required | Status |
|-------|------|----------|--------|
| **G1** | Plain-language layer — bugcheck families, `.sys` → friendly names in Summary | yes | ☐ |
| **G2** | Wire native dump v1 (depends Native D2b) | yes | ☐ |
| **G3** | Crash signatures — “same driver N× in 14 days” | yes | ☐ |
| **G4** | Pre-crash change detection — driver/WU timeline | optional | ☐ |
| **G5** | Hardware suspicion + **parts guidance** (WHEA, thermals, bugcheck class → “likely RAM / disk / GPU / PSU”) | yes | ☐ |
| **G6** | Action Plan checklist — [`ACTION_PLAN_CHECKLIST_PLAN.md`](../ACTION_PLAN_CHECKLIST_PLAN.md) | optional | ☐ |
| **G7** | Rescue + offline narrative | optional | ☐ |

G6 links existing backlog item; migrate reference to `design/` when AP work starts.

---

## Cause families (G1 — plain English)

Map stop codes to user-facing families: **driver**, **memory**, **disk**, **power/thermal**, **hardware (WHEA)**, **unknown** — with honest Unknown when evidence insufficient.

---

## Open questions

- Show “possible RAM issue” prominently or after driver steps fail?
- Deep scan: always on Run Analysis vs opt-in (time budget)?
- D1: hide `.sys` entirely vs “Technical details” expando?

---

## Handoff

```
Implement Phase G1 only (display/copy; no new data sources).
G2 blocked on NATIVE_DUMP_ENGINE_PLAN D2b.
```
