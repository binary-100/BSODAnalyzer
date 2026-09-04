# Built-in crash analysis — replace WinDbg/CDB (Tier 3)

**Also listed as:** Native dump engine · **`NATIVE_DUMP_ENGINE_PLAN.md`**

**Status:** Draft · **Tier 2:** ROADMAP **Approved intent** (“Analysis: built-in minidump engine”) · **Not buildable until work queue + user approval**

| | |
|---|---|
| **Tier map** | [`../DESIGN_TIERS.md`](../DESIGN_TIERS.md) § Current state |
| **Index** | [`NEXT_UPGRADE_INDEX.md`](NEXT_UPGRADE_INDEX.md) |
| **Layers + contract** | [`ANALYSIS_CORE_PLAN.md`](ANALYSIS_CORE_PLAN.md) |
| **Build wiring** | [`INTEGRATION_PATH.md`](INTEGRATION_PATH.md) |
| **D1 spike** | [`spikes/analysis_core/README.md`](spikes/analysis_core/README.md) |
| **Today (shipping code)** | `bsod_minidump.analyze_minidump_with_cdb` → subprocess `!analyze -v; kv` |
| **Target (after Build)** | `analyze_minidump_native()` (name TBD) → same dict → existing report/GUI unchanged |

Last updated: **2026-09-03**

---

## What “replace WinDbg” means here

| In scope | Out of scope (for this track) |
|----------|-------------------------------|
| **Built into the app** — no user install of Debugging Tools / WinDbg for Run Analysis | Shipping WinDbg UI or teaching `!analyze` commands |
| Native parse of kernel minidumps / triage dumps | Full interactive kernel debugger |
| Same Quick Answer / confidence / Drivers crash-linked inputs | Mandatory 100% parity with every `!analyze` edge case on day one |
| Cross-platform core (Linux rescue + Windows maintenance) | Replacing “Open in WinDbg” advanced escape hatch — **keep Level E forever** on Windows maintenance |
| Open-source–friendly own code path | Redistributing CDB as the **primary** engine in OSS release (TBD at D1) |

**Integration point:** Replace the CDB subprocess path in `bsod_minidump.py` (and callers in `analyzer_gather`) with native analysis that emits the **same structured dict** today’s pipeline already consumes. Rename `enrich_windbg_analysis` → neutral name when shipping (e.g. `enrich_dump_analysis`).

---

## Goal

Parse kernel minidump / triage dumps **natively** so BSOD Analyzer attributes crashes **without requiring WinDbg install or user-facing debugger prompts**. Same output schema as today’s CDB parse; optional CDB fallback when confidence is low.

## Non-goals (v1 — depth can grow)

- Committing to a single dump technology before parity harness (Native D1)
- Interactive kernel debugger as the **default** user surface (expert depth can come later)

## Not ruled out (evaluate with data)

- Matching or exceeding today’s CDB/`!analyze` attribution on hard dumps
- Additional analysis layers after native v1 proves gaps

---

## What we extract today from CDB (parity target)

From `analyze_minidump_with_cdb` parse:

`faulting_driver`, `bugcheck_code`, `bugcheck_p1`, `bugcheck_str`, `failure_bucket_id`, `stack_frames` (≤12), `process_name`, `symbol_name` → `enrich_windbg_analysis()`.

---

## Architecture layers

| Layer | Source | Native approach |
|-------|--------|-----------------|
| 1 | Dump file format | Read bugcheck, params, context RIP, module list from triage streams |
| 2 | Module attribution | Map RIP → loaded `.sys` base/size |
| 3 | Stack | Top frames as module+offset; PDB optional later |
| 4 | Heuristics | Own taxonomy + confidence; CDB fallback |

**Building blocks (evaluate in spikes):** [kdmp-parser](https://github.com/0vercl0k/kdmp-parser), [kdmp-parser-rs](https://github.com/wbenny/kdmp-parser-rs).

---

## Options considered

| Option | Verdict |
|--------|---------|
| A — Hide bundled CDB only | Short-term UX; doesn’t fix size/cross-platform |
| B — Native + CDB fallback | **Recommended** |
| C — Full !analyze clone | **Reject** |

---

## Phased checklist

| Phase | Name | Required | Status |
|-------|------|----------|--------|
| **D1** | Parity harness — corpus of `.dmp`; native vs CDB diff report | yes | ◐ **Harness plumbing** — PAGE header read + fixtures; full parity needs maintainer corpus — [`spikes/analysis_core/`](spikes/analysis_core/README.md) |
| **D2** | Native extractor v1 — bugcheck, P1–P4, RIP, module-for-RIP | yes | ☐ |
| **D2b** | Adapter — same dict as CDB path; `analysis_source: native\|cdb` | yes | ☐ |
| **D3** | Stack frames without PDB | yes | ☐ |
| **D4** | Confidence score + CDB fallback threshold | yes | ☐ |
| **D5** | Shrink portable build — optional CDB pack | optional | ☐ |
| **D6** | Cross-platform parser (Rust) for rescue USB | optional | ☐ |

Spikes: [`spikes/analysis_core/README.md`](spikes/analysis_core/README.md) — **D1 scaffold in place**; reimplement in production at Build.

---

## Parity baseline (host 2026-09-04)

Recorded before promote. Corpus: `C:\Windows\Minidump\` (5 files). Harness: `parity_harness.py --no-strict`.

| File | Stop (native = CDB) | Bugcheck fields | CDB-only fields (D2–D3) |
|------|---------------------|-----------------|-------------------------|
| `012926-15546-01.dmp` | `0x124` WHEA_UNCORRECTABLE_ERROR | ☑ match | driver (`AuthenticAMD`), bucket, stack |
| `080426-18703-01.dmp` | `0x50` PAGE_FAULT_IN_NONPAGED_AREA | ☑ match | driver, bucket, stack |
| `082126-18484-01.dmp` | `0xA` IRQL_NOT_LESS_OR_EQUAL | ☑ match | driver, bucket, stack |
| `082326-19171-01.dmp` | `0x154` UNEXPECTED_STORE_EXCEPTION | ☑ match | driver, bucket, stack |
| `121425-16515-01.dmp` | `0x50` PAGE_FAULT_IN_NONPAGED_AREA | ☑ match | driver, bucket, stack |

**D1 Build exit:** reproduce harness in `scripts/` (or equivalent); fixtures + optional maintainer corpus; bugcheck parity holds on PAGE dumps.

Full checklist: [`PROMOTE_WHEN_READY.md`](PROMOTE_WHEN_READY.md).

---

## WinDbg removal levels (maintenance exe)

See [`ANALYSIS_CORE_PLAN.md`](ANALYSIS_CORE_PLAN.md) § WinDbg / CDB — levels A–F. This track targets **A–D** on Windows; **E** (Open in WinDbg) stays.

---

## Decisions log

| Date | Decision |
|------|----------|
| 2026-08-24 | Strategy B — native primary, CDB fallback |
| 2026-08-24 | Portable build already bundles Debugging Tools; native engine removes *dependency* narrative and incomplete-engine failures |

---

## Open questions

- Hide `.sys` in novice view while native uses modules internally? (see Guided PLAN)
- Symbol server for function names — Phase D7 or never?
- User corpus of anonymized dumps for D1?

---

## Handoff

```
Implement Phase D1 only (spikes + harness under `upgrade/plans/spikes/`; no production wiring).
Then D2–D2b before changing Run Analysis default path.
```
