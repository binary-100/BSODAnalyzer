# BSOD Analyzer — Known limitations (informational)

**Not a backlog.** Accepted tradeoffs and operator notes. Open product work: [`ROADMAP.md`](ROADMAP.md).

Last updated: **2026-09-01** (see [`VERSION.txt`](../VERSION.txt))

---

## Crash analysis

### Log read windows (Phase 3)

Analysis reads **the newest N records** per log source (not “everything since date X”). Limits are defined in `log_read_windows.py` and summarized in every full export under Section 4.

| Source | Typical limit |
|--------|----------------|
| WER BugCheck (1001) | 30 events |
| Kernel-Power 41 / unexpected shutdown 6008 | 20 / 15 |
| Merged crash-event list returned to analysis | 25 |
| Boot / Startup Repair / Kernel-Boot / Wininit | 20 / 30 / 25 |
| WHEA-Logger 18 | 15 |
| Application Error 1000 | 30 |
| Thermal log | 20 |
| Reliability Live Kernel / WER system (optional) | 25 / 20 |
| Minidumps on disk | All listed; up to **3** newest analyzed with WinDbg |

**Primary incident window:** 30 days before the **latest** incident — older timeline/export rows are labeled **Historical**. Minidump↔incident time match uses a **72-hour** window.

Older minidumps on disk can predate the event-log window; they are never treated as explaining the latest shutdown unless times match.

### Shutdown without a matching minidump

When the latest incident is an unexpected shutdown or boot recovery event and **no minidump matches that time**, the tool **cannot name a single faulting `.sys` file**. It will show a **confidence ladder** (Verified / Focus area / Unknown) and crash-linked **focus** (e.g. AMD Chipset / Platform) when catalog context supports it.

**Mitigation (6.4.67):** Summary and Quick Answer include “What would change this” (enable dumps, wait for next matching minidump). Action Plan no longer suggests “Run as Administrator” when already elevated with dumps enabled.

### Event 41 bugcheck field

Kernel-Power Event 41 may include a bugcheck parameter that is **not verified** without WER BugCheck Event 1001 or a matching minidump. The tool does not treat it as a confirmed stop code.

---

## Driver catalog

### Chipset without PnP anchor

When device inventory has no AMD/Intel plumbing device (SMBus, GPIO, ME, etc.), chipset rows use a synthetic context without `instance_id`. Microsoft Update Catalog HWID matching is skipped; OEM and AMD/Intel vendor paths remain.

**Mitigation (6.4.67):** Driver verification lists **installed bundle components** (PSP, SMBus, GPIO, …) on the platform row when inventory provides them. Post-analysis **auto crash-linked catalog** (setting `auto_crash_linked_catalog`, default on) checks gated crash-linked rows without a full manual Search.

### WU 8000-row session cap

Full Windows Update driver scans cap in-memory rows at 8000. Truncation is recorded in the cache (`rows_truncated`, `rows_original_count`) and in status text.

**No change planned** — uncapped payloads risk memory and table performance on large catalogs.

### Catalog “none” noise on full scans

Full scans often show **none** for inbox Microsoft devices (WAN miniports, Bluetooth PAN, etc.). That is expected and not a crash signal.

**Mitigation (6.4.67):** Summary tip directs users to **Needs attention / crash-linked** rows first; novice view hides deep technical sections.

### GUI Microsoft online catalog (batched)

The portable GUI does **not** run `Get-WindowsDriver -Online -All` during device checks (stability). HWID warm runs in batches instead.

See prior sections in this file for tiered search, AMD chipset version scrape, OEM heuristics, and portable cache layout (unchanged from 6.2.x).

### Enterprise OEM manifests (6.4.78)

Dell (`DriverPackCatalog.cab`), HP (`HPClientDriverPackCatalog.cab`), and Lenovo (`catalogv2.xml`) enterprise deployment catalogs supplement consumer OEM APIs during the **once-per-scan OEM warm**. Manifests cache under `driver_catalog/_enterprise_manifests/` for **7 days**; Dell may fetch one small per-model metadata XML for individual driver rows. No MSCatalog queries added; no opt-in validation funnel.

---

## Install modes (portable vs full install)

**Policy:** Portable-first — fresh device inventory each session by design. See `AGENTS.md` § Portable-first.

| Mode | `install_mode` | Settings | Driver list / check cache | Catalog disk cache |
|------|----------------|----------|---------------------------|-------------------|
| **Portable** (default) | `portable` | `%LOCALAPPDATA%\BSODAnalyzer\settings.json` on the serviced PC | **Not persisted** — rebuilt each Search | Per-machine fingerprint under `%LOCALAPPDATA%\BSODAnalyzer\driver_catalog\<fingerprint>\` |
| **Full install** (legacy) | `full` | Same PC-local root (or custom data dir via Settings) | Persisted under full-install data dir | Same data dir (not fingerprint subfolder) |

**Maintenance USB:** The launcher runs from USB; durable state stays on the target PC. The stick holds exe/runtime only — not settings or catalog cache.

**Why full-install code remains:** Some users opt in via Settings → install mode. Branches in `app_settings.py`, `bsod_workflow.py`, `gui_mixin_drivers.py`, and `driver_catalog.py` (`full_install` scan phases, maintenance history, persistent driver index) are **intentional**, not dead code. We do **not** prune them without an explicit product decision to drop full-install support.

**Portable UX constraints:** No install-mode dialog on first launch; no stale DB tab nag in portable; Tools refresh and driver Search remain mutually exclusive.

---

## Build / packaging

### PyInstaller admin-manifest deprecation

PyInstaller may warn about legacy admin manifest embedding. Builds still succeed.

### Post-build CLI smoke

Frozen `--cli` analysis can exceed 5 minutes on slow machines; CI smoke timeout is **600 s** (6.4.67).

---

## Self-diagnostics

Uncaught GUI exceptions and faulthandler output append to `gui_crash.log` and **`BSODAnalyzer_self_crash.txt`** (portable exports folder or full-install data dir). Useful when Event 1000 shows Qt/runtime faults in the app itself.

**Mitigation (6.4.69):** Include-column header reposition is debounced and skipped during bulk table fills; Summary HTML panels use size-capped, non-re-entrant `setHtml`; export drain loops cannot nest. Historical `Qt6Core.dll | Stack buffer overrun` entries in the Application log may predate these fixes — re-test after building 6.4.69.

---

## Catalog scan timing

Full driver scans run a **~20 s** WU COM phase plus **~13 s** HWID online-store warm, then **~2–3 min** MSCatalog parallel warm (155 unique queries typical), then **~1 min** parallel device checks — **~3.9–5 min p50** for ~150–152 devices on reference hardware (Alienware m17 R5 AMD, **PowerShell 7 required** for parallel path, `session_log.jsonl` Aug 2026: p50 **4.84 min**, p95 **8.21 min**). Pre-6.2.0 baseline was **~20–24 min**; 6.1.25 regression peaked at **~39 min**.

**Policy (Phase 6):** Parallel batch warm (`gui_mscatalog_batched_parallel: true`); no GUI `Get-WindowsDriver -Online -All`. Details: [`ROADMAP.md`](ROADMAP.md) § Phase 6.

**Timing compare (read-only):** after catalog changes, run `py -3 scripts/compare_catalog_scan_timings.py` against `session_log.jsonl`.

---

## Related docs

- Historical catalog audit: [`audit_archive/CODE_AUDIT_v6_catalog.md`](audit_archive/CODE_AUDIT_v6_catalog.md)
- Open work: [`ROADMAP.md`](ROADMAP.md) (work queue + backlog)
- Driver verification phases: [`DRIVER_VERIFICATION_PLAN.md`](DRIVER_VERIFICATION_PLAN.md)
