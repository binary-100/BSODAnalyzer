# BSOD Analyzer — build notes (v6.2.0–6.2.1, archived)

Historical notes from the parallel Microsoft Update Catalog work. Current build process: see repo root [`BUILD_NOTES.md`](../../../BUILD_NOTES.md).

---

## v6.2.1 — fixes for the issues you reported on the 6.2.0 build

The 6.2.0 parallel catalog phase had a real bug and is now fixed, plus three
accuracy/UX items:

1. **Catalog returned 0 results / "visual hang" (root cause found).**
   `Get-MSCatalogUpdate` prints `WARNING: We did not find any results for …` on
   the warning stream; PowerShell's `-Command` merges that into stdout, so the
   batch's JSON was preceded by WARNING lines and failed to parse — turning any
   partial miss into a **total 0-results run**. Fixed by suppressing the warning
   stream inside each runspace and wrapping the JSON in sentinels.
2. **Visual hang.** The warm now runs in **chunks** (default 24 queries).
3. **AMD PSP 11.0 wrongly flagged "Update".** AMD-suite-vs-component comparisons
   now read **Uncertain** with a large-version-gap guard.
4. **Realtek audio update missing.** Primary cause was the 0-results bug above;
   batch mode now keeps name-based UAD queries.
5. **Column widths.** Device (and Firmware's Component) now **stretch widest**.

---

## v6.2.0 — parallel catalog (superseded by 6.2.1)

- New module `catalog_ps_batch.py` — bounded internal parallelism for MSCatalog queries.
- `driver_catalog.py` — `warm_batched_mscatalog_queries()` uses batch path.
- `app_settings.py` — `gui_mscatalog_batched_parallel`, `gui_mscatalog_parallel_throttle`.
- Version bumped `6.1.26 → 6.2.0`.

See [`PERFORMANCE_PLAN.md`](../../../PERFORMANCE_PLAN.md) for measured basis and future phases.
