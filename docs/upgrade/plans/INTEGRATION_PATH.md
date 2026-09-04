# Integration path — spike → production (Tier 3)

**Audience:** Build agents wiring analysis core into BSOD Analyzer.  
**Status:** Draft · **Last updated:** 2026-09-03

Parent: [`ANALYSIS_CORE_PLAN.md`](ANALYSIS_CORE_PLAN.md) · Spike: [`spikes/analysis_core/README.md`](spikes/analysis_core/README.md)

---

## Principle

1. **Prove in spike** (quarantined, pytest, optional CDB corpus).
2. **Reimplement cleanly** in production modules during Build — **do not** `import` spike code from `bsod_minidump.py`.
3. **One phase per session** unless user expands scope.

---

## Production touch map (after D2b)

| Step | Module | Change |
|------|--------|--------|
| 1 | `docs/upgrade/plans/spikes/analysis_core/contract.py` | Copy field list → production `dump_analysis_types.py` or docstring contract in `bsod_minidump.py` |
| 2 | New `dump_analysis_native.py` (name TBD) | Port logic from spike `native_minimal.py` → full D2 |
| 3 | `bsod_minidump.py` | Add `analyze_minidump_native()`; keep `analyze_minidump_with_cdb()` for D4 fallback |
| 4 | `bsod_minidump.py` | Add `analyze_minidump()` dispatcher: native → fallback if low confidence |
| 5 | `analyzer_gather.py` | Call dispatcher instead of CDB-only path in minidump bundle |
| 5b | `bsod_crash_report.py` | **`analyze_recent_minidumps`** — remove `if not cdb_path: return None` gate when native path can run; merge recurring-driver logic unchanged |
| 6 | `bsod_minidump.py` | Rename `enrich_windbg_analysis` → `enrich_dump_analysis` (re-export alias for compat) |
| 7 | Capture readiness / data gaps | Message when `analysis_source: none` — not “install WinDbg” as first line |
| 8 | Advanced tab | **Keep** `launch_latest_dump_in_windbg` (Level E) |
| 9 | Tests | Port parity cases from `tests/test_analysis_core_spike.py` → `tests/test_native_dump_*.py` |
| 10 | `PRODUCT_REFERENCE.md` | §3.1 minidump row when user-visible behavior changes |

**Forbidden in D1/D2 slice:** PyInstaller spec changes (D5), GUI redesign (G1), rescue offline readers (9a).

---

## Phase D1 (Build agent checklist)

**Goal:** Parity harness + corpus workflow — **no** Run Analysis default change.

- [ ] Copy corpus layout from spike `corpus/README.md`
- [ ] Production script or `scripts/dump_parity_harness.py` reimplemented from spike (not symlink)
- [ ] Document anonymized dump collection policy — [`spikes/analysis_core/CORPUS_POLICY.md`](spikes/analysis_core/CORPUS_POLICY.md)
- [ ] Exit criteria: harness exit 0 on `fixtures/` with `--include-fixtures`; real corpus documented separately
- [ ] `run_tests.bat` exit 0 (existing suite unchanged)

---

## Phase D2 + D2b (Build agent checklist)

**Goal:** Native v1 on hot path with adapter.

- [ ] `analyze_minidump_native` returns contract dict
- [ ] `analysis_source` + `analysis_confidence` populated
- [ ] Dispatcher used from gather path
- [ ] Tests: mock dump bytes + optional real corpus skips if no CDB
- [ ] `live_validate_analysis.py` still passes on admin host
- [ ] `run_tests.bat` exit 0

---

## Phase D4 (fallback)

- [ ] When `analysis_confidence == low`, call CDB path internally
- [ ] User sees same Summary — optional Advanced note “verified with debugging engine”
- [ ] Telemetry in export/session log: `native` vs `cdb` counts (optional)

---

## Guided diagnostic integration (G1, G2, …)

| Phase | Integration point |
|-------|-------------------|
| **G1** | `crash_report_narrative.py` / display model — map **cause taxonomy** to strings; no new dump parser |
| **G2** | Assert dump dict from dispatcher; remove CDB-specific labels in Summary when `analysis_source: native` |
| **G3–G5** | `build_report_derivations` — correlation and hardware suspicion inputs |

---

## Rescue integration (9a–9b, later)

| Phase | Integration point |
|-------|-------------------|
| **9a** | Target volume resolver — shared with spike offline tests |
| **9b** | Offline evtx/WER/minidump paths → same **acquisition** interfaces maintenance uses |
| **Analysis core** | Same native parser binary/library on Linux — **no CDB** |

---

## Validation tiers (Build agent)

Per [`AGENT_READINESS.md`](../../AGENT_READINESS.md):

| Phase | Minimum |
|-------|---------|
| D1 | T0 + spike/harness script exit 0 |
| D2b | T0–T2 + `live_validate_analysis.py` if dump path touched |
| G1 | T0–T2 + GUI offscreen tests if Summary strings change |

---

## Session opener template (for human)

```
Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\plans\INTEGRATION_PATH.md and C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\plans\NATIVE_DUMP_ENGINE_PLAN.md and implement Phase D1 only.
```

(Replace with active `HANDOFF_WQ*.md` when work queue row exists.)
