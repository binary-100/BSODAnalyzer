# BSOD Analyzer — Roadmap (single plan of attack)

**Goal:** One ordered checklist for all open product work. **Runtime order = build order.** Implement the next unchecked phase only.

| | |
|---|---|
| **Version** | see [`VERSION.txt`](VERSION.txt) · update ROADMAP header when a phase ships |
| **Last updated** | 2026-09-01 |
| **Design tiers (explore → intent → design → build)** | [`upgrade/DESIGN_TIERS.md`](upgrade/DESIGN_TIERS.md) · Plans: [`upgrade/plans/`](upgrade/plans/README.md) |
| **Structure rules** | Starter pack `pack/docs/PHASED_FEATURE_DESIGN.md` · `.cursor/rules/generic-phased-feature-design.mdc` |
| **Capabilities / agent rules** | [`PRODUCT_REFERENCE.md`](PRODUCT_REFERENCE.md) |
| **Tradeoffs (not backlog)** | [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) |
| **Crash-linked drivers** | [`DRIVER_VERIFICATION_PLAN.md`](DRIVER_VERIFICATION_PLAN.md) — **Phases 1–7 complete** |

**Supersedes:** scattered items in old `IMPROVEMENT_BACKLOG.md` §1/§4/§6, PRODUCT_REFERENCE §4.1 bullets, Desktop Chip-Level doc Phases B–F (until Phase 8).

---

## Master checklist

Check phases **in order**. Phase ☑ when all **required** sub-steps are done.

| Phase | Name | Status | Ships in |
|-------|------|--------|----------|
| **1** | Baseline validation & planning consolidate | ☑ | 6.4.70 + doc |
| **2** | Capture pipeline hardening | ☑ | 6.4.72 |
| **3** | Log age & relevance | ☑ | 6.4.73 (3a–3c; optional Summary focus → Parked) |
| **4** | Extended in-app log attribution | ☑ | 6.4.74 |
| **5** | Repair UX & documentation clarity | ☑ | 6.4.75 |
| **6** | Catalog scan performance | ☑ | 6.2.0–6.2.1 + 6.4.76 |
| **7** | Doc hygiene & cross-links | ☑ | 6.4.77 |

Phases **1–7** are the numbered roadmap; all ☑. Open product work lives in the [work queue](#work-queue-current) and [Approved intent](#approved-intent) below. Parked ideas: [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md) (hidden — not agent default).

**Maintainability milestone (6.5.0):** catalog module split, crash-report slices, orchestration peel (`analyzer_gather` / `analyzer_hardware`), facade Option 2 (124 re-exports, production decouple), agent validation gates — see [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) and [`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md).

**Legend:** ☑ done · ◐ in progress · ☐ not started · 🔥 back burner (on work queue, saved for last)

---

## Work queue (current)

| Name | PLAN | Phase | Status |
|------|------|-------|--------|
| *(empty)* | | | |

**Recently shipped:** Maintenance USB PC-local data (WQ-001, M1–M4) — ☑ [`upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md`](upgrade/plans/MAINTENANCE_USB_DATA_PLAN.md); evidence in [`WORK_QUEUE.md`](WORK_QUEUE.md) Done log. Stick-side migration removed (M2 retired).

Promote from [Approved intent](#approved-intent) when ready for upgrade tracks below.

**Back burner:** *(empty)* — use when an item stays on the work queue but should run last.

### Planning vocabulary (do not confuse with audit)

| Term | Meaning |
|------|---------|
| **Work queue** | What we build next (`ROADMAP.md` here). |
| **Back burner** | On the work queue, **saved for last**. |
| **Approved intent (Tier 2)** | Product direction we are keeping — **agents watch this section**. Not buildable until work queue. See [`upgrade/DESIGN_TIERS.md`](upgrade/DESIGN_TIERS.md). |
| **Design (Tier 3)** | Full PLAN in [`upgrade/plans/`](upgrade/plans/README.md). **Does not remove** Approved intent row — row links here. Not buildable until work queue + “implement Phase X”. |
| **Exploration (Tier 1)** | Spitball in [`upgrade/inbox/`](upgrade/inbox/README.md) — not on this doc until promoted to Approved intent. |
| **Parked** | Not investing now — [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md). **Not** on agent default lists. |
| **Audit Improve** | Ephemeral audit findings — **not** product planning. Never auto-sync here. |

When you say **“backlog”** in chat, clarify: **Approved intent**, **Parked**, or **audit Improve**.

---

## Approved intent

Product direction we are pursuing — **not current build order**. Promote to the work queue when ready.

**Naming:** outcome-based titles only (see [`upgrade/DESIGN_TIERS.md`](upgrade/DESIGN_TIERS.md)).

| Name | Design (Tier 3) | Build |
|------|-----------------|-------|
| **Rescue: bootable USB for offline target PC** | **Drafted** — [`upgrade/plans/RESCUE_USB_PLAN.md`](upgrade/plans/RESCUE_USB_PLAN.md) · boot OS: [`upgrade/plans/RESCUE_BOOT_ENVIRONMENT.md`](upgrade/plans/RESCUE_BOOT_ENVIRONMENT.md) | Not buildable |
| **Analysis: built-in minidump engine (no CDB install)** | **Drafted** — [`upgrade/plans/NATIVE_DUMP_ENGINE_PLAN.md`](upgrade/plans/NATIVE_DUMP_ENGINE_PLAN.md) | Not buildable |
| **UX: guided diagnosis in plain language + hardware guidance** | **Drafted** — [`upgrade/plans/GUIDED_DIAGNOSTIC_PLAN.md`](upgrade/plans/GUIDED_DIAGNOSTIC_PLAN.md) | Not buildable |

**Upgrade hub:** [`upgrade/README.md`](upgrade/README.md) · **Build handoff:** [`upgrade/BUILD_HANDOFF.md`](upgrade/BUILD_HANDOFF.md)

**Parked ideas (hidden):** [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md) — open only when reviewing or reviving.

---

## Parked (reference only — not active)

**Do not implement.** Full list: [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md).

Includes: agent tooling handoff, Summary recent-window Settings, Tools log cleanup suggestions, drivers chip-level sources (RFC). Historical Phase 8 sub-phases (8a–8e) — see design archive via Parked file.

---

## Legacy backlog section (removed)

Former “Backlog (parked)” rows were split into **Approved intent** (three upgrade tracks), **Exploration** (Action Plan checklist — Tier 1), or **Parked** (everything else). Do not recreate a combined backlog table.

### Phase 8 detail (historical — see Parked)

**Status:** **Parked** — see [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md). No code until revived to Approved intent + work queue.

Source: [`docs/design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md`](design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md) (Phases B–F).

| Sub | Work | Status |
|-----|------|--------|
| **8a** | Discovery index (metadata only) | ☐ |
| **8b** | Consent UI + settings | ☐ |
| **8c** | Verify pipeline | ☐ |
| **8d** | In-app install (opt-in) | ☐ |
| **8e** | Install journal + crash correlation | ☐ |

**Done when:** Full chip-level doc success criteria met; default experience unchanged when OFF.

---

## Maintainability (parallel — not a ROADMAP phase number)

**Status:** ☑ Catalog split complete (6.4.79) · [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md)

Split oversized modules for **general** maintainability (reviews, tests, any future feature — not only Phase 8).

| Slice | Module | Status |
|-------|--------|--------|
| 1 | `catalog_scoring.py` — version/date compare + `compare_driver_to_installed` | ☑ |
| 2 | Offer pipeline (`enrich`, `sort`, `_finalize_catalog_offers`) | ☑ |
| 3 | Live OEM fetch block | ☑ |
| 4 | MSCatalog session / batch warm | ☑ |
| 5a | `bsod_minidump.py` — CDB + minidump I/O / WER recovery | ☑ |
| 5b | `bsod_crash_report.py` — analysis, recommendations, report formatting | ☑ |

---

## Phase 1 — Baseline validation & planning consolidate

**Status:** ☑ Done (2026-08-13)

**Done when:**

- [x] Live validation on reference hardware (Alienware m17 R5 AMD) via `scripts/live_validate_analysis.py`
- [x] Repair narrative + boot/recovery correlation verified on host
- [x] `PRODUCT_REFERENCE.md` created (capabilities, agent obligations)
- [x] `ROADMAP.md` created (this file) — single plan of attack
- [x] CDB `ext.dll` engine selection + `boot_events_near_crash()` (6.4.70 fixes)

**Reference baseline:** Aug 9 shutdown without matching dump; Aug 4 older minidump; AMD chipset 8.07 + PSP/SMBus/GPIO decomposition; dumps enabled; admin OK.

---

## Phase 2 — Capture pipeline hardening

**Status:** ☑ Complete (6.4.72 — live validation + full test suite passed on reference hardware)

**Why here:** Silent capture failures block definitive attribution. User must never be told to “enable dumps” when the app can verify and fix capture state.

| Sub | Work | Required | Status |
|-----|------|----------|--------|
| **2a** | CDB: skip incomplete local engine; prefer WinDbg app when `winext\ext.dll` missing | yes | ☑ |
| **2b** | Boot/recovery: correlate against full boot list (`boot_events_near_crash`) | yes | ☑ |
| **2c** | **Capture readiness panel** — Summary or Advanced: Admin ✓/✗, dumps ✓/✗, CDB engine ✓/✗, last dump time vs latest incident | yes | ☑ |
| **2d** | Auto-repair local `DebuggingTools` from WinDbg app when incomplete (copy engine with `ext.dll`) | yes | ☑ |
| **2e** | Minidump prerequisites: `%SystemRoot%\Minidump` writable, disk space, `MinidumpDir` registry | yes | ☑ |
| **2f** | WER 1001 `DumpFile` missing: relocate search + WER ReportArchive module hint (not gap-only) | optional | ☑ |

**Done when:** 2c–2e complete; live validation shows readiness panel; no silent CDB/analyze failures on reference hardware.

**Build:** `bsod_analyzer.py`, `gui_mixin_analysis.py` or Advanced tab, tests in `test_live_validation_fixes.py`, `test_minidump_prerequisites.py`.

---

## Phase 3 — Log age & relevance

**Status:** ☑ Complete (6.4.73 — 3a–3c; optional Summary focus → [Parked](upgrade/parked/PARKED.md))

**Why here:** Old events/dumps confuse “latest incident” until capture is trustworthy.

| Sub | Work | Required | Status |
|-----|------|----------|--------|
| **3a** | Define read windows (events, boot, dumps, WHEA) — document in KNOWN_LIMITATIONS | yes | ☑ |
| **3b** | Timeline + export: label incidents outside primary window as historical | yes | ☑ |
| **3c** | Narrative: stronger stale-dump separation (older_incident_note when faulting module present) | yes | ☑ |
| **3d** | Optional “focus last N days” + unified log-cleanup UX | optional | ☐ **parked** — see [Parked](upgrade/parked/PARKED.md) + appendix below |

**Done when:** Aug 4 dump never reads as Aug 9 cause; exports window documented.

**Implement now:** **3a–3c only.** Do not block Phase 3 on 3d or cleanup UX redesign.

**Validation:** After ship, run `scripts/live_validate_analysis.py` (Phase 2 + 3 unit tests and live sub-step checks).

---

## Phase 4 — Extended in-app log attribution

**Status:** ☑ Done (6.4.74)

**Why here:** More definitive answers without manual user steps — parse sources Windows already wrote.

| Sub | Work | Required | Status |
|-----|------|----------|--------|
| **4a** | Parse WER **ReportArchive** / ReportQueue XML for faulting module / bucket | yes | ☑ |
| **4b** | Merge WER XML hints into driver verification suspects + repair narrative | yes | ☑ |
| **4c** | `setupapi.dev.log` — recent driver install/rollback lines near incident | optional | ☑ |
| **4d** | CBS / component store hints for boot-loop confusion | optional | ☑ |

**Done when:** No-dump incidents gain module hints when WER XML exists; covered by tests with fixture XML.

**Validation:** After ship, run `scripts/live_validate_analysis.py` (Phase 2–4 unit tests and live sub-step checks).

**Note:** Log cleanup (Tools) stays delete-only — parsing is separate read path (`log_attribution.py`).

---

## Phase 5 — Repair UX & documentation clarity

**Status:** ☑ Done (6.4.75)

| Sub | Work | Required | Status |
|-----|------|----------|--------|
| **5a** | Action Plan steps cite exact **Drivers tab row names** from `repair_targets` | yes | ☑ |
| **5b** | **Terminology** section in PRODUCT_REFERENCE (Verified/Focus/Moderate, Event 41 vs 1001, incident grouping ~2 min) | yes | ☑ |
| **5c** | Quick Answer / narrative copy — confident fix path; **Why this order** (replaces How sure) | yes | ☑ |

**Done when:** Action Plan strings match Drivers → Needs attention labels; PRODUCT_REFERENCE § terminology added; no-dump copy leads with fix plan not "Unknown".

**Validation:** After ship, run `scripts/live_validate_analysis.py` (Phase 2–5 unit tests and live sub-step checks).

---

## Phase 6 — Catalog scan performance

**Status:** ☑ **Complete** (acceptance met 2026-07-21; documentation closed 2026-08-13)

**Why this phase existed:** Full **Drivers → Search for driver updates** on ~152 devices took **~20–24 min** on reference hardware (6.1.20). Experiments in 6.1.21–6.1.25 tried more parallelism and MSCatalog pre-warm; they **hung or slowed** scans because catalog PowerShell was serialized. v6.2.0 changed the architecture (parallel MSCatalog inside one process). See also [`PERFORMANCE_PLAN.md`](../../PERFORMANCE_PLAN.md) (historical analysis) and [`audit_archive/AGENT_HANDOFF_CATALOG_PERFORMANCE.md`](audit_archive/AGENT_HANDOFF_CATALOG_PERFORMANCE.md) (6.1.x handoff).

---

### Product policy (catalog work)

| Rule | Rationale |
|------|-----------|
| **Speed and accuracy together** | Never ship a speed change that reduces driver/update coverage or hides actionable rows. |
| **Full device list stays** | ~152 included devices is the benchmark; do not shrink scope to “look faster.” |
| **Gap fallback for empty rows** | HWID-verified coverage-gap pass (6.2.4) when a device has zero offers after normal tiers. |
| **Deferral stays tuned** | `should_defer_microsoft_catalog()` — validate accuracy changes on Alienware baseline before broadening rules. |
| **Parallel batch warm** | Supported path: `gui_mscatalog_batched_parallel` seeds cache before the device loop. |
| **No `Get-WindowsDriver -Online -All` in GUI scans** | Hung 43+ min on reference hardware; permanent guard. |
| **Measure before claiming a win** | After timing change: [`scripts/compare_catalog_scan_timings.py`](../scripts/compare_catalog_scan_timings.py). After accuracy change: [`scripts/live_validate_analysis.py`](../scripts/live_validate_analysis.py). |

---

### Measured acceptance (reference hardware — Alienware m17 R5 AMD)

Source: `%TEMP%\BSODAnalyzer\session_log.jsonl` — **48** completed full scans (≥140 devices), 2026-07-19 through 2026-08-10.

| Metric | Target | Measured |
|--------|--------|----------|
| **p50** | ≤ 12 min | **4.84 min** |
| **p95** | ≤ 18 min | **8.21 min** |
| Pre-6.2 baseline (6.1.20) | ~20–24 min | **20.45 / 23.76 min** (2 runs) |
| Worst regression (6.1.25) | — | **39.40 min** (1 run) |
| First post-6.2 scan | — | **4.26 min** (2026-07-20 20:19) |
| Post-6.2 median (44 runs) | — | **4.79 min** |

**Cliff (documented):** No completed scan between 6.1.25 end (39.4 min) and first 6.2.0 fast run (4.26 min). Pre-6.2 median **22.1 min** → post-6.2 median **4.79 min** (**4.6×**).

**Where time goes today** (one measured run: 150 devices, **231.5 s** total, 2026-08-10):

| Phase | Wall time | Share |
|-------|-----------|-------|
| WU COM + setup | ~20 s | 9% |
| HWID online-store warm (165 IDs, 17 batches) | ~13 s | 6% |
| **MSCatalog parallel warm** (155 queries, throttle 5, 7 chunks) | **~137 s** | **59%** |
| Device loop (4 workers, OEM / manufacturer / WU) | ~62 s | 27% |

Micro-benchmark on this machine (`PERFORMANCE_PLAN.md`): 8 live MSCatalog queries — serial **332.6 s** vs pwsh parallel **38.5 s** (**8.6×**).

---

### History — what we tried vs what worked

| Era / version | What changed | Measured outcome |
|---------------|--------------|------------------|
| **6.1.20** | Stable baseline | **~20–24 min**, reliable |
| **6.1.21–6.1.23** | MSCatalog upfront pre-warm (417 queries), parallel workers | **~54 min** pre-warm alone; scan looked frozen |
| **6.1.22–6.1.23** | `-All` prefetch at warm | **43+ min** hang |
| **6.1.24–6.1.25** | Pre-warm off; still multi-query per device + lazy `-All` | **~39 min** completed; MSCatalog dominated |
| **6.1.26** | ~1 MSCatalog query per PCI device in batch mode | Not separately timed before 6.2.0 |
| **6.2.0** | `catalog_ps_batch.py` — one pwsh process, `ForEach-Object -Parallel`, batch warm before device loop | **4.26 min** first full scan |
| **6.2.1** | JSON sentinel + warning suppression (0-results bug); chunked progress | Accuracy restored (Realtek UAD, etc.) |
| **6.2.4** | `gui_gap_catalog_fallback` — HWID-verified name search for zero-offer devices | Coverage without false positives |
| **6.4.76** | `_is_online()` 60 s cache in `catalog_ps_module.py` | Small latency trim only |

**Lesson (root cause):** ~**85%** of each MSCatalog query is network I/O to `catalog.update.microsoft.com`. Extra `powershell.exe` processes and outer thread workers **queued on one lock** — they did not parallelize network. The fix was **internal parallelism in one process**, not more subprocesses or skipping devices.

---

### How a full GUI catalog scan works today

Pipeline in `driver_catalog._build_multi_device_driver_comparison_body()` (GUI batch):

```
1. ensure_mscatalog_module_ready()
2. Windows Update COM once (~20 s)
3. warm_batched_microsoft_online_store() — HWIDs in PS batches (~10–15 s)
4. warm_batched_mscatalog_queries() — unique queries, parallel in one pwsh (~2–3 min)
5. _warm_vendor_scrapes_for_contexts()
6. ThreadPoolExecutor (4 workers) — per device: manufacturer → OEM ∥ Microsoft → MSCatalog (cache hits)
7. _augment_gap_devices_with_verified_catalog() — optional HWID-verified gap fill
```

MSCatalog still uses **one global catalog PS lock** at a time — but step 4 seeds the per-scan cache so step 6 rarely opens new catalog network work.

---

### Sub-steps (6a–6d) — final status

Maps [`audit_archive/PERFORMANCE_PLAN.md`](audit_archive/PERFORMANCE_PLAN.md) phases 1–4 to roadmap labels:

| Sub | Perf plan | Work | Status | Ships / evidence |
|-----|-----------|------|--------|------------------|
| **6a** | Phase 1 | Batched parallel MSCatalog in one PS session | ☑ **Required — done** | 6.2.0–6.2.1 · `catalog_ps_batch.py`, `_warm_mscatalog_parallel()` |
| **6b** | Phase 2 | Deferral rules | ☑ **Closed as-is** | `should_defer_microsoft_catalog()` only — tuned for accuracy. |
| **6c** | Phase 3 | HTTP-parallel + PS-batched pipeline | ☑ **Required — done** | Warm-then-loop in `driver_catalog.py:7387+`. No separate refactor needed. |
| **6d** | Phase 4 | Cheap wins | ☑ **Required — done** | pwsh preferred · `_is_online` cache (6.4.76). Workers stay **4** (device loop ~27% — lowering default not worth it). |

**Also shipped (accuracy + speed, not optional):**

- HWID strings excluded from MSCatalog title search (`is_hwid_search` in `catalog_ps_module.py`)
- `gui_mscatalog_batched_parallel: true` — parallel warm runs before the device loop (replaces legacy per-query subprocess storm)
- Progress bar fixes (6.1.26) — indeterminate bar no longer masks real `Checked X/Y` progress

---

### Canonical production settings

Defaults in `app_settings.py` / portable `settings.json`:

```json
"gui_mscatalog_batched_parallel": true,
"gui_mscatalog_parallel_throttle": 5,
"gui_mscatalog_parallel_chunk": 24,
"gui_mscatalog_prewarm": false,
"gui_batched_online_store": true,
"gui_batched_online_store_include_all": false,
"gui_catalog_parallel_workers": 4,
"gui_gap_catalog_fallback": true
```

**Requires PowerShell 7 (`pwsh`)** for parallel MSCatalog; Windows PowerShell 5.1 falls back to sequential in one session (still faster than one-process-per-query, but not ~5 min). UI warns before Search when pwsh is missing.

---

### Key files

| Piece | Location |
|-------|----------|
| Parallel MSCatalog batch | `catalog_ps_batch.py` |
| Warm + device pipeline | `driver_catalog.py` (`warm_batched_mscatalog_queries`, `_build_multi_device_driver_comparison_body`) |
| MSCatalog module + online cache | `catalog_ps_module.py` |
| Catalog PS lock | `bsod_runtime.py` → `run_catalog_powershell()` |
| GUI progress / session log | `gui_mixin_catalog.py`, `session_log.py` |
| Timing compare (read-only) | `scripts/compare_catalog_scan_timings.py` |
| Historical handoff | `docs/AGENT_HANDOFF_CATALOG_PERFORMANCE.md` |

---

### Validation after any future catalog change

| Check | Command / action |
|-------|------------------|
| **Timing regression** | Full driver Search (~152 devices) → `py -3 scripts/compare_catalog_scan_timings.py --last 5` (or `--before YYYY-MM-DD` vs prior era) |
| **Accuracy / narrative** | `py -3 scripts/live_validate_analysis.py` — Alienware baseline (AMD chipset, no-dump copy, driver_display, etc.) |
| **Unit tests** | `run_tests.bat` — especially `test_driver_catalog_quality.py`, `test_catalog_ps_module.py` |

**Do not** change catalog timing or deferral without **`compare_catalog_scan_timings.py`** and **`live_validate_analysis.py`** passing on reference hardware.

---

### Done when (Phase 6)

- [x] p50 ≤ 12 min and p95 ≤ 18 min on reference hardware
- [x] No hang regressions — guards remain in code
- [x] Parallel MSCatalog batch shipped with accuracy fixes (6.2.1, gap fallback 6.2.4)
- [x] Policy + history documented in this section
- [x] Read-only timing compare tool for future builds

**No further Phase 6 implementation required.**

---

## Phase 7 — Doc hygiene & cross-links

**Status:** ☑ **Complete** (6.4.77 · 2026-08-13)

**Why here:** Phases 1–6 shipped capabilities and closed catalog performance; root/app docs still referenced old versions, stale evaluation claims, or missing cross-links. Phase 7 makes the doc set trustworthy so agents do not re-litigate Phase 6 or misread product state.

**Implement in numeric order: 7a → 7b → 7c → 7d → 7e** (sub-step number = build order).

| Sub | Work | Required | Status |
|-----|------|----------|--------|
| **7a** | Archive Chip-Level Advisory → `docs/design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md` | yes | ☑ |
| **7b** | Sync `KNOWN_LIMITATIONS.md` (version, catalog timing/policy, ROADMAP link) | yes | ☑ |
| **7c** | Refresh `EVALUATION.md` (banner, R1 catalog closed, ROADMAP link) | yes | ☑ |
| **7d** | Self-diagnostics section in `PRODUCT_REFERENCE.md` (`gui_crash.log`, paths) | yes | ☑ |
| **7e** | Driver catalog reference appendix in `PRODUCT_REFERENCE.md` §12 | yes | ☑ |

### 7a — Archive Chip-Level design

- Copied Desktop `BSODAnalyzer_Chip_Level_Advisory_Design.md` → [`design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md`](design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md)
- Archive header: Phase 8 RFC only; not active build order
- Phase 8 in this roadmap links to archive path

### 7b — KNOWN_LIMITATIONS sync

- Header version **6.4.77**
- § Catalog scan timing aligned with Phase 6 measured p50/p95 and policy
- Link to ROADMAP Phase 6

### 7c — EVALUATION.md refresh

- Removed stale v6.1.26 scope; added ROADMAP/PRODUCT_REFERENCE banner
- R1 catalog latency marked **addressed** (Phase 6); R3/R5 updated
- Bottom line: maintainability next, not catalog speed

### 7d — Self-diagnostics (PRODUCT_REFERENCE §3.10)

- Portable vs full-install paths for `gui_crash.log`, `BSODAnalyzer_self_crash.txt`, `session_log.jsonl`
- Cross-link KNOWN_LIMITATIONS § Self-diagnostics

### 7e — Driver catalog appendix (PRODUCT_REFERENCE §12)

- Tier order, pipeline, defer rules, gap fallback, cache paths, settings, validation tools
- **Descriptive only** — links to ROADMAP Phase 6 for policy

**Done when:** All five sub-steps ☑; PRODUCT_REFERENCE header version synced; Phase 8 points at design archive.

**Validation:** Doc-only — no code change required; optional link sanity by reading updated paths.

---

## Closed — product decisions (historical)

| Item | Reason |
|------|--------|
| Guided fix wizard | Action Plan tab is the workflow |
| Novice export trim | Support needs full exports |
| Concurrent driver + firmware search | Global catalog state |
| `-All` in GUI / winget drivers / bundled Playwright | See git history |

---

## Shipped recently (reference only)

| Version band | Highlights |
|--------------|------------|
| 6.4.63–6.4.69 | Driver attribution, auto crash-linked catalog, boot playbook, incident timeline, Qt hardening |
| 6.4.70 | Repair narrative, boot correlation fix, CDB ext.dll selection |
| 6.4.71–6.4.72 | Capture readiness, CDB auto-repair, minidump prerequisites (2e), WER dump recovery (2f) |
| 6.4.73 | Log read windows (3a), historical timeline/export labels (3b), stale-dump narrative (3c) |
| 6.4.74 | Extended log attribution — WER archive/queue (4a–4b), setupapi.dev.log (4c), CBS hints (4d) |
| 6.4.75 | Repair UX — exact Drivers row names in Action Plan (5a), terminology doc (5b), Why this order copy (5c) |
| 6.2.0–6.2.1 | Catalog scan performance (Phase 6a/6c) — parallel MSCatalog batch; 6.2.1 accuracy fixes |
| 6.4.76 | Phase 6d — `_is_online` cache; `compare_catalog_scan_timings.py`; ROADMAP Phase 6 closed |
| 6.4.77 | Phase 7 doc hygiene — design archive, EVALUATION/KNOWN_LIMITATIONS sync, PRODUCT_REFERENCE §3.10 + §12 |
| 6.5.18–6.5.23 | Dependency install reliability — PS7 MSI-first (+ winget-pkgs manifest fallback); WinDbg Run Analysis prompt + direct MSIX (`Add-AppxPackage`, no `winget install`); install logs; continue-with-bundled-CDB on failure; `scripts/sync_install_fallbacks.py` |

Full history: git log · ROADMAP § Shipped recently.

---

## How agents use this doc

1. Read [`PRODUCT_REFERENCE.md`](PRODUCT_REFERENCE.md) for what exists today.
2. Implement the **work queue** top item only — not Approved intent, not Parked, not Exploration, not audit Improve unless the user asked.
3. **Approved intent** = future direction; read linked Tier 3 PLAN only when implementing a promoted slice or user points you there.
4. **Do not read** [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md) unless the user asks.
5. Report progress as **work-queue item** or **“through Phase N”** when shipping numbered phases.
6. On ship: bump `VERSION`, update work queue, update PRODUCT_REFERENCE if capabilities changed.
7. **Do not** ask the user to validate items agents can run (`live_validate_analysis.py`).
8. **After each slice ships:** `run_tests.bat` + `live_validate_analysis.py` where relevant.

---

## Appendix — Documentation items (tie to phases)

Items from product-reference “worth adding later” — **do not duplicate elsewhere**; check off when parent phase completes:

| Doc item | Owner phase | Action when done |
|----------|-------------|------------------|
| Terminology & attribution rules | **5b** | Add PRODUCT_REFERENCE § |
| Incident grouping (~2 min window) | **5b** | Same section |
| Self-diagnostics paths | **7d** | PRODUCT_REFERENCE §3.10 — **done** |
| Catalog reference appendix | **7e** | PRODUCT_REFERENCE §12 — **done** |
| Glossary (stop codes, crash-linked) | **5b** or **7e** | PRODUCT_REFERENCE §5 |
| Capture readiness | **2c** | PRODUCT_REFERENCE §3.4 — **done** |

---

## Appendix — Log age display + cleanup (deferred)

**Status:** **Parked** — see [`upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md). Technical detail below for revive.

**Problem:** Two related ideas feel overlapping to users:

| Idea | What it is | Today |
|------|------------|--------|
| **Summary focus (3d)** | Which incidents Summary *emphasizes* | Not built |
| **Log cleanup** | Delete old dumps/WER/logs from *disk* | Tools → Log cleanup (explicit, destructive) |

Mixing them is wonky: a “last 14 days” filter is a **view**; cleanup is **permanent deletion**. Tying them together (auto-delete what’s “out of focus”) would be dangerous and confusing.

### Unified plan (simple end-user model)

**Layer 1 — Automatic (Phase 3a–3c, ship first)**  
No new settings. The app always:

- Reads only documented windows (3a).
- Labels older incidents **Historical** in timeline/export (3b).
- Keeps stale dumps out of the latest-incident narrative (3c — partial today via `older_incident_note`).

User does nothing extra; Aug 4 vs Aug 9 stays honest.

**Layer 2 — Delete old artifacts (existing Tools, enhance later)**  
One place only: **Tools → Log cleanup**.

Future enhancements (not 3d):

- Age-based suggestions: “Minidumps older than 30 days (2 files, ~40 MB)” with explicit checkboxes.
- **Keep** guidance tied to analysis: “Unresolved latest incident (Aug 9) — keep newest minidump until fixed or exported.”
- Never auto-delete from a Summary focus setting.

**Layer 3 — Optional display preference (deferred 3d)**  
**Settings → Preferences** only (no popup on Run Analysis):

- ☐ **Emphasize Summary on recent incidents** + dropdown **7 / 14 / 30 / 90 / All time** (default **All time**).
- Affects Summary / Quick Answer emphasis only; full export and Advanced sections still include everything Windows still has on disk.
- When enabled, muted banner: *“Emphasizing last N days — full report includes all events on disk.”*

**Explicit non-goals**

- No wizard, no modal on each analysis.
- No auto-delete when N-day focus is enabled.
- No trimming exports for “novice mode.”

**Done when (this appendix):** User can choose display focus without affecting cleanup; cleanup suggests safe age cuts with export-first copy; docs state the two layers clearly in PRODUCT_REFERENCE.

**Owner phase:** Optional **3d** after 3a–3c ☑; cleanup UX improvements may ship in the same version or a follow-up Tools pass.
