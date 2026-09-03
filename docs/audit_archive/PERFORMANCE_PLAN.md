# BSOD Analyzer — Performance Plan (archived)

> **Archived 2026-08-16.** Phase 6 **complete** — canonical record is [`../ROADMAP.md`](../ROADMAP.md) § Phase 6.

**Goal (historical):** beat v6.1.20 baseline (~20–24 min for ~152 devices) reliably, without hangs from 6.1.21–6.1.25 regressions.

---

## Key measurement (why parallel batch won)

~85% of each MSCatalog query was network round-trip; legacy path serialized every query behind one global catalog PS lock (one `powershell.exe` per query).

| Phase of one query | Time | Share |
|--------------------|------|-------|
| Process spawn | ~174 ms | 5% |
| `Import-Module MSCatalogLTS` | ~316 ms | 10% |
| Network `Get-MSCatalogUpdate` | ~2,800 ms | 85% |

**Fix shipped:** `catalog_ps_batch.py` — one PowerShell session, bounded internal parallelism (`pwsh` 7 `ForEach-Object -Parallel`), seeds per-scan cache before per-device checks.

---

## Results (reference hardware, Aug 2026)

| Metric | Pre-6.2.0 | Post Phase 6 |
|--------|-----------|--------------|
| p50 full driver scan | ~20–24 min | **~4.84 min** |
| p95 | — | **~8.21 min** |
| Policy | — | prewarm off; parallel batch on; no GUI `Get-WindowsDriver -Online -All` |

Details, settings JSON, validation commands: **ROADMAP § Phase 6**.

---

## Validation tools (still current)

```bat
py -3 scripts\compare_catalog_scan_timings.py --last 5
py -3 scripts\live_validate_analysis.py
run_tests.bat
```

---

## Related files

| Piece | Location |
|-------|----------|
| Parallel batch | `catalog_ps_batch.py` |
| Warm pipeline | `catalog_mscatalog_session.py` / `driver_catalog.py` |
| Timing compare | `scripts/compare_catalog_scan_timings.py` |
| Handoff notes | `docs/AGENT_HANDOFF_CATALOG_PERFORMANCE.md` |
