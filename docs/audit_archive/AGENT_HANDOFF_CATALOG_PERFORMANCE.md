# BSOD Analyzer — Agent Handoff: Catalog Scan Performance

**Purpose:** Brief another AI agent on this project, what we are trying to achieve, what we tried, what failed, and where we are stuck.  
**Last updated:** 2026-07-20  
**Current dev version:** 6.1.26 (`bsod_analyzer.py` → `BSODAnalyzer_v6\BSODAnalyzer.exe`)  
**Stable baseline:** v6.1.20 at `C:\Users\binar\Documents\BSODAnalyzer\StableBuilds\v6.1.20\`

---

## 1. Project summary

**BSOD Analyzer** is a Windows portable GUI tool (PySide6 + PyInstaller) that:

- Analyzes BSOD minidumps (bundled WinDbg/CDB)
- Inventories hardware and drivers (WMI/PnP)
- **Searches for driver/firmware updates** from many sources: OEM (Dell/Alienware APIs), Windows Update COM, Microsoft Update Catalog (MSCatalogLTS PowerShell module), Intel/AMD/NVIDIA vendor scrapers, extended vendor scrapers, and per-HWID `Get-WindowsDriver -Online`

The user cares most about the **Drivers tab → Search for driver updates** flow: a **full scan of 152 included devices** on their Alienware m17 R5 AMD (152 in scan scope, 158 in full inventory).

**Repository root:** `c:\Users\binar\OneDrive\Desktop\BSODAnalyzer`

---

## 2. Current goal (what we are trying to do)

**Primary goal:** Make full 152-device catalog scans **faster than v6.1.20**, which reliably completed in **~20–24 minutes** on the user's machine.

**Hard constraints from the user:**

- Do **not** suggest deselecting devices or shrinking scan scope for benchmarking — **152 devices is the baseline**
- Preserve a known-good build (v6.1.20 stable archive) while experimenting in dev
- Scans must **complete without hanging**; progress UI must reflect real progress

**Secondary goals:**

- Keep coverage: OEM, WU, MSCatalog, vendor scrapers, per-HWID online store
- Avoid `Get-WindowsDriver -Online -All` during GUI scans (hangs on this machine)
- Maintain portable-mode behavior and session logging for diagnosis

**Honest status:** After 6.1.21–6.1.25 optimization attempts, **6.1.26 is aimed at matching 6.1.20 speed again**, not beating it yet. The original speed-up plan did not pay off on this hardware.

---

## 3. Measured timings (user's Alienware, 152 devices, full scan)

From `%TEMP%\BSODAnalyzer\session_log.jsonl`:

| Build / era | Start → End (local) | `elapsed_ms` | Notes |
|-------------|---------------------|--------------|-------|
| **~6.1.20** | 15:47 → 16:08 | 1,226,792 (~**20.4 min**) | Completed, 3 updates |
| **~6.1.20** | 17:04 → 17:28 | 1,425,528 (~**23.8 min**) | Completed, 3 updates |
| **6.1.23** | 19:54 → (MSCatalog pre-warm) | — | ~54 min in MSCatalog pre-warm alone; hung appearance |
| **6.1.24** | 23:00 → 23:14 export | — | Stuck on lazy `-All` for no-HWID USB devices after OEM finished |
| **6.1.25** | 23:53 → 00:32 | 2,364,236 (~**39.4 min**) | Completed all 152; MSCatalog dominated device phase (~38 min) |
| **6.1.26** | — | — | **Not yet timed on user machine**; expected ~20–25 min |

Warm-up phase (WU + HWID batch warm) is consistently **~50–60 seconds**. The device-check phase is where time is won or lost.

---

## 4. Version history (6.1.20 → 6.1.26)

| Version | Intent | Outcome on user's PC |
|---------|--------|----------------------|
| **6.1.20** | Stable baseline; Realtek 2.5GbE fixes, session logs, progress UI | **~20–24 min**, reliable |
| **6.1.21** | Multi-HWID PS warm (10/batch); MSCatalog upfront pre-warm; parallel OEM+Microsoft per device | Pre-warm added **~54 min** before device checks |
| **6.1.22** | Global `run_catalog_powershell()` lock; 4 parallel workers; `-All` prefetch at warm | **Hung** on `-All` prefetch (~43+ min, no progress) |
| **6.1.23** | Remove `-All` prefetch; 180s `-All` timeout; warm-phase progress % | Fixed `-All` prefetch hang; pre-warm still slow |
| **6.1.24** | MSCatalog pre-warm **off by default**; per-device "Checking…" progress | Pre-warm fixed; still slow if `-All` lazy path runs |
| **6.1.25** | Never `-All` during GUI scans; `include_all` default off | **Completed** but **~39 min**; progress bar broken |
| **6.1.26** | 1 MSCatalog query per PCI device in batch mode; progress bar fixes | Built; **awaiting user timing run** |

---

## 5. Architecture of a full GUI catalog scan

High-level pipeline in `driver_catalog.build_multi_device_driver_comparison()`:

```
1. ensure_mscatalog_module_ready()
2. _get_cached_wu_driver_rows()          — Windows Update COM, once per scan (~30–65 s)
3. warm_batched_microsoft_online_store() — 173 HWIDs in 18 PS batches (~10 s)
4. warm_batched_mscatalog_queries()      — OFF by default (gui_mscatalog_prewarm=false)
5. For each batch of 8 devices, up to 4 parallel workers:
     For each device:
       a. Manufacturer tier (HTTP scrapers, parallel internally)
       b. OEM + Microsoft WU/store in parallel (_run_catalog_source_tasks)
       c. MSCatalog search if not deferred (should_defer_microsoft_catalog)
6. persist / GUI update
```

**Per-device tier order:** manufacturer → OEM → Microsoft (WU + online store) → MSCatalog (when not deferred).

**Parallelism:**

- Outer: `ThreadPoolExecutor` with `gui_catalog_parallel_workers` (default **4**) over device batches of **8**
- Inner: OEM ∥ Microsoft per device (up to 2 threads)
- Manufacturer tasks may also use thread pools

**Serialization bottleneck:**

- All catalog PowerShell (`run_catalog_powershell()` in `bsod_runtime.py`) shares **one global lock**: WU COM scripts, `Get-WindowsDriver -Online`, MSCatalogLTS searches
- Parallel device workers **contend** on this lock for MSCatalog — they do not truly run catalog PS in parallel

---

## 6. Root causes of hangs and slowness

### 6.1 Hang: MSCatalog upfront pre-warm (6.1.21–6.1.23)

- **417 unique MSCatalog queries** run sequentially before any `Checked 1/152`
- **~54 minutes** on user's machine (session log: query 1/417 … 417/417)
- Export showed all 152 devices **pending** — scan looked frozen

**Fix:** `gui_mscatalog_prewarm` default **false**; queries run during device loop with dedup cache only.

### 6.2 Hang: `Get-WindowsDriver -Online -All` prefetch (6.1.22)

- Warm phase tried to load full online catalog upfront for no-HWID devices
- **Hung 43+ minutes** with no progress after "loading full catalog…"

**Fix:** Removed upfront `-All` prefetch in 6.1.23+.

### 6.3 Hang: lazy `-All` during parallel device checks (6.1.24–6.1.25)

- First batch often includes **no-HWID USB/HID devices** (keyboard, USB hubs)
- With `gui_batched_online_store_include_all=true`, each worker triggered `_lazy_load_online_driver_store_all()`
- **`Get-WindowsDriver -Online -All`** blocked all 4 workers (OEM finished in ~0.4 s, then silence for 13+ min)

**Fix (6.1.25):** Never run `-All` during GUI catalog session; no-HWID devices use WU + MSCatalog only.

### 6.4 Slowness: MSCatalog query volume (6.1.21–6.1.25)

- `_catalog_search_queries_for_ctx()` builds up to **5 queries per device** (10 for Realtek): full instance ID, VEN&DEV, SUBSYS, device label, vendor+label, OEM keywords, Realtek UAD queries
- Each query = **one PowerShell MSCatalogLTS invocation** under global lock
- **6.1.25 device phase ~38 min** (~15 s/device average); log shows `Finished microsoft catalog` every 5–20 s per device
- Parallel workers **do not speed up** PS-bound MSCatalog — they queue

**Partial fix (6.1.26):** `_batch_mscatalog_queries_for_ctx()` limits batch scans to **1 HWID-base query** per PCI device (3 for Realtek net); early exit on HWID match.

### 6.5 UI: progress bar did not fill correctly (6.1.24–6.1.25)

- Scan started with `maximum=0` (indeterminate)
- Any message containing `"catalog"` or `"Checking"` reset bar to indeterminate — including `"Finished microsoft catalog"` and `"Checking USB Device…"` **after** `Checked 50/152`
- Percent label showed raw count `(50%)` instead of `50/152 = 33%`

**Fix (6.1.26):** Start at `0/152`; only `Checked X/Y` and warm-up phases move fill; percent math fixed.

---

## 7. What actually helped vs hurt

| Change | Helped? | Notes |
|--------|---------|-------|
| Batched HWID warm (10/script) | **Small win** | Warm phase ~10 s vs many individual PS calls |
| Parallel OEM + Microsoft | **Modest** | Overlaps HTTP/disk; not PS-bound |
| 4 parallel device workers | **Mixed** | Helps HTTP tiers; **hurts or neutral** when MSCatalog dominates (lock contention) |
| Global PS lock | **Stability** | Prevents overlapping PS subprocesses; **caps parallelism** |
| MSCatalog upfront pre-warm | **Hurt badly** | ~54 min regression |
| `-All` prefetch / lazy `-All` | **Hurt / hang** | Disabled in GUI |
| Up to 5 MSCatalog queries/device | **Hurt badly** | ~39 min vs ~20 min baseline |
| 1 MSCatalog query/device (6.1.26) | **Expected help** | Not yet measured on user machine |

**Conclusion:** Optimizations assumed parallelism would speed the scan, but the **slowest work (MSCatalog PS) is serialized**. Adding parallel workers increased contention without reducing total PS work. **Reducing query count** is the lever that matches the bottleneck.

---

## 8. Key files and settings

| Item | Location |
|------|----------|
| Version | `bsod_analyzer.py` → `VERSION = "6.1.26"` |
| Catalog logic | `driver_catalog.py` (~11k lines) |
| PS serialization | `bsod_runtime.py` → `run_catalog_powershell()`, `_CATALOG_PS_LOCK` |
| MSCatalog PS wrapper | `catalog_ps_module.py` |
| GUI progress | `gui_mixin_catalog.py` → `_on_drv_catalog_progress()` |
| GUI worker | `bsod_gui_workers.py` → `DriverCatalogWorker`, `set_gui_catalog_session()` |
| Settings defaults | `app_settings.py` |
| Session log | `%TEMP%\BSODAnalyzer\session_log.jsonl` |
| Stable archive script | `scripts\save_stable_build.bat` |
| Build | `build_and_deploy_v6.bat` → `BSODAnalyzer_v6\` |
| Limitations doc | `docs\KNOWN_LIMITATIONS.md` |

**Relevant settings (defaults in 6.1.26):**

```json
"gui_batched_online_store": true,
"gui_batched_online_store_include_all": false,
"gui_catalog_parallel_workers": 4,
"gui_mscatalog_prewarm": false
```

**Important flags on device context during batch scan:**

- `ctx["_batch_driver_check"] = True` — enables reduced MSCatalog query set in 6.1.26
- `ctx["_gui_driver_catalog"] = True` — GUI mode guards
- `set_gui_catalog_session(True)` on worker thread — blocks `-All`

---

## 9. Test machine profile (user)

- **Model:** Alienware m17 R5 AMD  
- **Service tag:** DZ6R1Q3  
- **Scan scope:** 152 included devices (Drivers tab)  
- **Typical results:** 3 newer, ~70 uncertain, ~74 none (versioning/heuristic limits)  
- **OEM:** Dell/Alienware catalog supported  

---

## 10. Open questions for another agent

We want **ideas that beat ~20 min for 152 devices** without sacrificing reliability or the full device list.

### 10.1 Bottleneck analysis

- Is **global PS lock** the right model? Alternatives: dedicated MSCatalog worker queue, batch PS script with multiple queries, persistent PS runspace?
- Can MSCatalog searches be **batched into one PowerShell session** per N queries (like HWID warm) instead of one subprocess per query?
- What is the **minimum MSCatalog query set** that preserves coverage for PCI vs USB/HID vs chipset?

### 10.2 Work reduction (likely highest ROI)

- **Aggressive deferral:** Skip MSCatalog when OEM *or* manufacturer returns *any* versioned offer, not only when same/newer than installed
- **Class-based skip:** Skip MSCatalog for generic USB/HID/keyboard/hub classes entirely in full scan
- **Two-tier scan modes:** "Fast" (WU+OEM+vendor) vs "Deep" (+MSCatalog) — user asked for speed but may accept explicit modes
- **Shared query schedule:** Precompute unique MSCatalog queries across 152 devices (~173 HWIDs but 417+ query strings historically) and run once with dedup — without the 54-min regression ( smarter scheduling, timeouts, progress )

### 10.3 Parallelism strategy

- Should `gui_catalog_parallel_workers` default to **1 or 2** when PS-heavy, higher only for HTTP-heavy phases?
- Split pipeline: **Phase A** HTTP (parallel) → **Phase B** PS catalog (serial, deduped queue)
- Does parallel OEM+Microsoft still help if MSCatalog always runs afterward?

### 10.4 `-All` and no-HWID devices

- Is skipping `-All` permanently acceptable for GUI, or is there a safe timeout/kill pattern that works on this machine?
- How much coverage is lost for Realtek GbE and similar no-HWID devices without `-All`?

### 10.5 Measurement

- Export phase timings (WU / HWID warm / MSCatalog / per-tier) into catalog JSON or session log for A/B
- Define acceptance: **p50 & p95** wall time for 152-device scan on this hardware

---

## 11. Suggested experiments (prioritized)

1. **Time 6.1.26** on user machine — confirm return to ~20–25 min band  
2. **Profile:** Count MSCatalog PS invocations and wall time per scan (6.1.20 vs 6.1.26)  
3. **Defer MSCatalog** when OEM returned any offer with a parseable version — measure skip rate  
4. **Batch MSCatalog PS** — e.g. 10 queries per script (mirror HWID warm pattern)  
5. **Lower parallel workers to 2** during batch scan — test if lock contention matters after query reduction  
6. **Optional fast scan** setting — document tradeoff clearly  

---

## 12. What not to recommend

- Reducing included device count for "performance testing" (user rejected this)
- Re-enabling upfront MSCatalog pre-warm of 400+ queries without strict timeout and incremental progress tied to overall %
- Re-enabling `Get-WindowsDriver -Online -All` during parallel device checks without proven kill/timeout on this hardware
- More parallel workers as the primary fix while PS remains globally serialized

---

## 13. How to reproduce / diagnose

1. Run `BSODAnalyzer_v6\BSODAnalyzer.exe` (6.1.26+) as admin portable mode  
2. Load devices, ensure 152 included, run **Search for driver updates**  
3. Watch `%TEMP%\BSODAnalyzer\session_log.jsonl` for:
   - `"phase": "start"` / `"phase": "end"` with `elapsed_ms`
   - `Checked X/152` cadence
   - `Finished microsoft catalog` frequency (MSCatalog cost proxy)
   - Stalls after `Finished oem` without `Finished microsoft` (historical `-All` hang signature)
4. Export catalog JSON from GUI for partial-state snapshots  

---

## 14. Summary one-liner for the next agent

**We tried to speed up 152-device driver catalog scans via batched HWID warm, parallel OEM/Microsoft, parallel device workers, and MSCatalog pre-warm; pre-warm and extra MSCatalog queries made scans hang or take ~39 min instead of ~20 min because all PowerShell catalog I/O is serialized — 6.1.26 rolls back the harmful parts and caps MSCatalog to ~1 query per PCI device; we still need a strategy that beats 6.1.20, likely by doing less MSCatalog work or batching PS differently, not by adding more parallel threads behind one lock.**

---

*Generated for external AI review. For in-repo context see also `docs/KNOWN_LIMITATIONS.md`, `docs/IMPROVEMENT_BACKLOG.md`, and conversation transcript `d28af20e-0fbb-4ae1-89f0-6924c5f68199` in Cursor agent transcripts.*
