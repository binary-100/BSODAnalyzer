# BSOD Analyzer — Product reference (agents & reviewers)

**Read this before advising the user, validating behavior, or planning features.**

| | |
|---|---|
| **Canonical version** | `bsod_analyzer.py` → `VERSION` (see [`VERSION.txt`](../VERSION.txt)) |
| **Last updated** | 2026-09-05 · sync this date when capabilities change |
| **Open work / plan of attack** | [`ROADMAP.md`](ROADMAP.md) — **single phased checklist** (implement next unchecked phase only) |
| **Accepted tradeoffs** | [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) |
| **Crash-linked drivers** | [`DRIVER_VERIFICATION_PLAN.md`](DRIVER_VERIFICATION_PLAN.md) — complete |
| **Phased planning rules** | Starter pack `PHASED_FEATURE_DESIGN.md` (profile `%USERPROFILE%\.cursor\rules\`) |
| **Agent entry point** | [`../AGENTS.md`](../AGENTS.md) |
| **Agent readiness (65k LOC)** | [`AGENT_READINESS.md`](AGENT_READINESS.md) — session self-audit, validation tiers, navigation, current slicing priority |
| **Architecture health (archive)** | [`audit_archive/EVALUATION.md`](audit_archive/EVALUATION.md), [`audit_archive/PERFORMANCE_PLAN.md`](audit_archive/PERFORMANCE_PLAN.md) — historical design context |
| **Full audit procedure** | [`AUDIT.md`](AUDIT.md) + `AGENTS.md` § Audits |

---

## 1. Product goals

BSOD Analyzer helps a technician on a **portable USB workflow** diagnose Windows crashes and driver problems on a machine they are at — without requiring the user to dig through Event Viewer, registry, or WinDbg manually.

| Goal | How we achieve it |
|------|-------------------|
| **Honest attribution** | Verified / Focus / Unknown ladder — never claim a faulting `.sys` without a matching minidump or corroborated WER record |
| **Actionable repair path** | Summary repair narrative, Action Plan steps, Drivers tab crash-linked rows with catalog search |
| **Official sources first** | Manufacturer → OEM → Microsoft for driver updates; no third-party install path in shipping code |
| **Portable-first** | Fresh device inventory each session; per-machine catalog cache under `driver_catalog\<fingerprint>\` |
| **Complete exports** | Support/forum uploads get full reports — clarity over trimming |
| **Agent-runnable validation** | Agents run analysis on the host; they do not ask the user to validate what the app already does |

**Not goals:** Replace WinDbg for deep kernel debugging; auto-enable Driver Verifier; blanket third-party driver installs; pre-warm MSCatalog (~54 min regression history).

---

## 2. Agent obligations (read every session)

### Agents MUST do themselves

| Task | How |
|------|-----|
| **Run tests after code changes** | **`run_tests.bat`** from the project root (pytest discovery — every `test_*` collected; gates in `test_test_discovery.py` + `test_static_analysis.py`). Targeted: `py -3 tests\run_test_module.py tests\…`. Never ask the user |
| **Qt test / popup follow-up** | Agent reads `qt_platform.log`, runs agent-hygiene orphan cleanup, re-runs tests — see [`AGENT_READINESS.md`](AGENT_READINESS.md) § Qt test bootstrap |
| **Validate analysis on the user's machine** | Run `py -3 scripts\live_validate_analysis.py` from the project root (admin shell). Output: `app\live_validation_output.json` |
| **Check admin / dump / CDB state programmatically** | Use `gather_report_data()`, `get_dump_config()`, `find_cdb()`, `is_user_admin()` — not user interviews |
| **Investigate attribution bugs** | Read event logs, minidumps, `driver_verification.py`, repair narrative output |

### Agents MUST NOT ask the user to do

| Wrong (offload) | Right (in-app or agent) |
|-----------------|-------------------------|
| "Enable memory dumps in Windows" | App: **Enable Memory Dump** button, auto-prompt when `needs_config`, Action Plan step |
| "Run as Administrator" | App: UAC relaunch on startup, admin banner, `data_gaps` when logs fail |
| "Run Analysis and send me the export" | Agent: run `live_validate_analysis.py` or `gather_report_data()` |
| "Build 6.4.x and confirm Summary" | Agent: validate via Python on host; user builds only when they want a packaged `.exe` |
| "Check Reliability Monitor manually" | App: Live Kernel + Reliability bundle during Run Analysis (Settings toggle) |
| "Install WinDbg / CDB yourself" | App: prompt before Run Analysis when online (no WinDbg app); Advanced → Install/Update; bundled CDB offline fallback |
| "Run tests" / "rerun run_tests.bat" | Agent: full or targeted suite via `run_tests.bat` / `run_test_module.py` |
| "Kill hung Python" / "fix Qt popup env vars" | Agent: `agent_hygiene_full_check`, orphan cleanup, read `qt_platform.log`, fix bootstrap — see `AGENT_READINESS.md` § Qt test bootstrap |

### Host environment (this machine)

The user runs **Cursor as Administrator**. Treat the **agent shell as elevated** — use it for `live_validate_analysis.py`, event-log reads, dump checks, and full test suites. Do **not** ask the user to rerun commands as admin or to perform agent hygiene manually.

**When suggesting next steps to the user**, frame as what they will **see in the app** after Run Analysis, or what **we need to implement** — not manual Windows housekeeping the app or agent already owns.

---

## 3. What the app does today

### 3.1 Run Analysis pipeline

Entry: **Run Analysis** (GUI) or `gather_report_data()` / `run_analysis()` (CLI).

Parallel collection includes:

| Source | Module / function | Purpose |
|--------|-------------------|---------|
| WER Event **1001** | `bsod_events.query_bugcheck_events` | Verified BSOD records, bugcheck params, dump path |
| Kernel-Power **41**, Event **6008** | same | Shutdown timing; 41 bugcheck field **not** trusted alone |
| **Minidumps** | `list_dumps`, `analyze_recent_minidumps` | CDB `!analyze` on up to 3 recent `.dmp` files |
| **Event timestamps** | `bsod_events._parse_event_time` | Event Log strings parsed as **local** when naive (not mislabeled UTC) — affects timeline, fix-progress dates |
| **WHEA-Logger 18** | `query_whea_hardware_errors` | Hardware component names |
| **Thermal** | `query_thermal_events` | Throttling near crash |
| **Boot / recovery** | `query_boot_recovery_events` | Startup Repair, Kernel-Boot, Wininit |
| **Live Kernel + Reliability** | `query_reliability_livekernel_bundle` | Optional (Settings) |
| **Application crashes** | `query_application_crashes` | Event 1000 context |
| **PnP + driver inventory** | `get_bios_and_driver_versions`, full inventory pass | ~150 devices, versions, enrichment |
| **Dump registry config** | `get_dump_config` | `CrashDumpEnabled` → `needs_config` |
| **CDB path** | `find_cdb` | Prefers engine with `winext\ext.dll` (WinDbg app); skips incomplete local copy |

Derivations: `build_report_derivations()` → `build_display_model()` for GUI; text via `format_output()`.

### 3.2 Crash attribution & narrative (6.4.70+)

| Output | Location | Behavior |
|--------|----------|----------|
| **Repair narrative** | Summary, Quick Answer, Action Plan | What happened / what failed / what to check; AMD/Intel **suite decomposition** (PSP, SMBus, GPIO, …) |
| **Confidence ladder** | Summary, Quick Answer | Verified / Focus / Moderate / Unknown + "what would change" |
| **Incident timeline** | Summary panel | Shutdown vs bugcheck vs boot/recovery vs stale minidump |
| **Driver verification** | Section 3b export, Drivers tab | Suspects → device map → local verify → optional auto crash-linked catalog |
| **Boot/recovery playbook** | Action Plan | When shutdown without matching dump + boot events near incident |

**Dump/incident matching:** `_dump_matches_recent_events()` — older dumps (e.g. Aug 4) do **not** drive the latest incident banner (Aug 9 shutdown).

**Boot correlation:** `boot_events_near_crash()` — searches **full** boot list, not only newest N rows.

### 3.3 Driver catalog (Drivers tab)

- Official tiers: manufacturer → OEM (Dell service tag) → Microsoft WU + MSCatalog — see **§12 Driver catalog reference**
- **Windows Update rows:** OEM PC-maker reject rules apply only to OEM-sourced rows (`_row_is_oem_sourced`) — WU optional updates for attached devices (monitors, USB audio, docks) are not suppressed by OEM suite filters (6.5.8)
- **MSCatalog query cache:** per-scan dedup clears in place across facade re-exports — warmed queries are not re-issued mid-scan (6.5.8)
- Full scan **~4–6 min** on ~150 devices with **PowerShell 7** (portable, no `-All` online WU in GUI); MSCatalog network dominates
- **Auto crash-linked catalog** after analysis (default on, max ~6 devices)
- Crash-linked / Needs attention filters; no novice export trimming

### 3.10 Self-diagnostics (when the app itself crashes)

Use these when BSOD Analyzer’s **own** GUI or process faults (Windows Event 1000 on `BSODAnalyzer.exe`, blank window, instant exit) — not for the PC’s BSOD under diagnosis.

| Artifact | Portable mode | Full install |
|----------|---------------|--------------|
| **`gui_crash.log`** | `%TEMP%\BSODAnalyzer\gui_crash.log` | `%LOCALAPPDATA%\BSODAnalyzer\gui_crash.log` |
| **`BSODAnalyzer_self_crash.txt`** | Portable exports folder, else `%TEMP%\BSODAnalyzer\` | `%LOCALAPPDATA%\BSODAnalyzer\` |
| **`session_log.jsonl`** (timing) | `%TEMP%\BSODAnalyzer\session_log.jsonl` | App data dir (same folder as `gui_crash.log`) |

Uncaught exceptions and faulthandler output append to these files. Attach them when reporting app crashes. Qt hardening notes: [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) § Self-diagnostics.

**Session timing compare:** `py -3 scripts/compare_catalog_scan_timings.py` — read-only; does not affect scans.

### 3.4 In-app remediation (already built)

| Feature | UI / API |
|---------|----------|
| Enable minidumps | Advanced → **Enable Memory Dump**; auto-prompt when `needs_config`; `enable_memory_dumps_or_report_status()` |
| **Local Debugging Tools repair** | Auto during Run Analysis when local copy lacks `ext.dll` and WinDbg app is installed (`repair_local_cdb_engine_if_needed`) |
| Admin elevation | Startup `request_admin_elevation()`; banner when not admin |
| **WinDbg online install prompt** | Before Run Analysis when online and Microsoft's WinDbg app is missing; direct MSIX + Add-AppxPackage (not winget install); Settings → Preferences to disable |
| Install/update CDB | Run Analysis prompt (online) or Advanced → Debugging Tools buttons |
| Open in WinDbg | Advanced → launch latest dump |
| Export report | File → export; Quick Answer + full technical sections |
| **Capture readiness** | Summary panel after Run Analysis — admin, dumps, CDB, minidump folder, dump vs incident (`build_capture_readiness`) |
| Compare catalog exports | Tools → Compare |
| Log cleanup | Tools → Log cleanup (WER archives, etc.) — **cleanup only**, not analysis input |
| **Action Plan inline checks** | Action Plan tab — **Run SFC**, **Run DISM**, **Start memory test**, **Schedule disk check** on matching steps; admin-gated for SFC/DISM/chkdsk (6.5.9) |
| **Active NIC power** | Settings → Preferences → **Keep active adapter awake** — default-route Wi‑Fi/Ethernet only; catalog scan hint when power saving is on (6.5.9) |
| **Minidump stack panel** | Advanced tab — dump picker, up to 12 stack frames, highlights first non-kernel module; re-analyze selected dump (6.5.9) |
| **Battery catalog performance** | `SetThreadExecutionState` during catalog scan; MSCatalog batch timeout fixes on battery (6.5.9) |

### 3.5 Data gaps

Partial failures surface in Summary as **Data gaps** (yellow). Agents use these to distinguish "app failed to read" vs "Windows had nothing to record."

### 3.6 GUI tabs & technician workflow

| Tab | Role |
|-----|------|
| **Summary** | Run Analysis results: repair narrative, confidence, incident timeline, cause banner |
| **Action Plan** | Numbered fix steps, download links (BIOS, chipset, GPU, OEM) — **this is the workflow**; no separate guided wizard |
| **Drivers** | Full catalog scan, Needs attention / crash-linked filters, Search for updates, driver backup/install, **component-only OEM bundle install** when device selected (6.5.7+) |
| **Firmware** | SSD + peripheral firmware inventory and vendor search; Download action after confirm (6.5.8 fix) |
| **Advanced** | Memory dump enable, CDB install/update, WinDbg launch, raw WinDbg output |
| **Settings** | Portable/full install, reliability events toggle, auto crash-linked catalog, backup folder |

**Typical flow:** Run Analysis → read Summary + Action Plan → Drivers (Needs attention / crash-linked) → optional full catalog Refresh → apply updates with backup when prompted.

**Report modes:** Simple vs technical detail toggle in GUI; exports include Quick Answer + full sections (no novice trim — support needs complete data).

### 3.7 Portable vs full install

| Mode | Default | Notes |
|------|---------|-------|
| **Portable (Maintenance USB)** | **Yes** | Launcher on USB; **durable state on the target PC** — `%LOCALAPPDATA%\BSODAnalyzer\` (settings, catalog cache per machine fingerprint, default exports) |
| **Full install** | Legacy | Same PC-local root by default; optional custom data dir — do not invest here unless feature requires it (`AGENTS.md`) |

Fresh device inventory each portable session is **intentional**, not a bug. The USB stick holds the exe/runtime only; it does not accumulate serviced-PC data.

### 3.8 Driver backup & install (in-app)

- Settings: backup-before-install (default on when configured)
- Drivers tab: install/update via existing plumbing (`pnputil`, OEM EXE where supported)
- `driver_backup.py` — controlled backup root; not a user manual step

### 3.9 Important settings keys

| Key | Default | Effect |
|-----|---------|--------|
| `auto_crash_linked_catalog` | on | Post–Run Analysis mini-scan for crash-linked rows (~6 devices) |
| Include Reliability / Live Kernel | Settings checkbox | `query_reliability_livekernel_bundle` during analysis |
| `gui_mscatalog_prewarm` | **off** | Legacy setting — parallel batch warm is the supported path (ROADMAP Phase 6) |
| `gui_mscatalog_batched_parallel` | **on** | Parallel MSCatalog in one pwsh process (~5 min scans) |
| `install_mode` | portable | portable vs full-install data layout |

---

## 4. Windows limits (app cannot fix — explain honestly)

| Situation | App behavior |
|-----------|--------------|
| Shutdown/boot failure **without** minidump | Focus area + boot playbook + platform targets — **cannot** name one `.sys` for that incident |
| Event 41 bugcheck field without WER 1001 / dump | Shown but **not verified** as stop code |
| Dumps enabled but no new `.dmp` after incident | Capture readiness checks folder, disk, `MinidumpDir`; Action Plan cites root cause (full disk, permissions, cleanup) |
| Incomplete local Debugging Tools | Auto-repair from WinDbg app (2d); falls back to app CDB if repair unavailable |
| WER 1001 cites `DumpFile` but file missing | Search alternate minidump folders; parse WER ReportArchive for module hint; analyze relocated dump if found |

### 4.1 Not yet in the analysis pipeline (future in-app — not user homework)

These are **gaps to implement**, not things to tell the user to do manually:

| Source | Potential value |
|--------|-----------------|
| WER **ReportArchive** / ReportQueue XML | Faulting module when no minidump — **shipped (4a–4b):** broad archive/queue scan + suspect/narrative merge |
| Event 1001 **DumpFile** path vs file missing on disk | **Shipped (2f):** alternate-folder search + WER hint + prerequisite-aware gap text |
| `setupapi.dev.log` | **Shipped (4c):** driver install/rollback correlation near incident |
| Minidump folder disk space / `MinidumpDir` / permissions | **Shipped (2e):** capture readiness + Action Plan steps |
| CBS / component store logs | **Shipped (4d):** servicing / pending-restart hints near incident |

Log cleanup (Tools) **lists** WER folders for deletion — parsing for attribution is a **separate read path** (`log_attribution.py`, Phase 4).

---

## 5. Terminology (Summary, Quick Answer, Drivers tab)

Canonical labels used in the repair narrative, export Section 1, and confidence banner.

### 5.1 Confidence levels (Summary banner)

| Level | Meaning |
|-------|---------|
| **Verified** | A minidump (or corroborated WER + matching context) names a faulting `.sys` for the **latest** incident |
| **Focus area** | Shutdown/boot problem without a matching dump — platform/chipset suite and related rows are the directed fix path |
| **Moderate** | Crash-related events logged; no confirmed faulting driver for the latest incident |
| **Unknown / limited** | No recent targeted events, or insufficient data |

### 5.2 Repair narrative sections (GUI + export)

| Section | Role |
|---------|------|
| **What happened** | Factual incident description from event logs |
| **What failed (this incident)** | What the crash record shows — or honest limit when Windows did not save a minidump (logging gap, not “analysis failed”) |
| **What to check on this PC** | `repair_targets` — same row labels as **Drivers → Needs attention** |
| **Why this order** | Rationale for fix sequence (boot/platform → BIOS → storage/GPU); replaces legacy “How sure we are” |
| **Separate note** | Older minidump or WER from a **different** incident (Phase 3 historical rules) |

### 5.3 Event log terms

| Term | Meaning |
|------|---------|
| **Event 1001 (WER BugCheck)** | Verified BSOD record in System log — includes bugcheck params and often dump path |
| **Event 41 (Kernel-Power)** | Unexpected shutdown; **bugcheck field alone is not verified** without WER 1001 or matching minidump |
| **Event 6008** | Unexpected shutdown (previous shutdown was unexpected) |
| **Incident grouping** | Events within **~2 minutes** = one incident (`INCIDENT_GROUP_WINDOW_MINUTES`) |
| **Historical** | Outside the latest incident window or a different calendar day — must not explain the newest shutdown |

### 5.4 Drivers tab filters

| Filter | Meaning |
|--------|--------|
| **Needs attention** | Crash-linked device rows only (after Run Analysis) — Action Plan steps cite these **exact labels** |
| **Updates available** | Catalog found a newer driver than installed |
| **All devices** | Full inventory (many inbox Microsoft rows — normal) |

---

## 6. Locked product decisions (do not re-litigate)

| Topic | Decision |
|-------|----------|
| Guided fix wizard | **No** — Action Plan tab is the workflow |
| Novice export trim | **No** — full exports for support |
| Concurrent driver + firmware search | **Declined** (global catalog state) |
| Extended / third-party driver install | **Not shipped** — see §10 |
| **Log age & relevance** | **Deferred** until repair narrative validated on hardware — note in backlog §6 only; do not keep raising in chat |
| Agent compiles/builds | **Only when user asks** — agents validate via Python on host |
| Stable archive (`BSODAnalyzer_StableBuilds`) | User field-test first; max 3; not every version; CI build ≠ stable |

---

## 7. Validation on the host (agents)

```bat
cd app
set PYTHONPATH=%CD%
py -3 scripts\live_validate_analysis.py
```

Reads: `live_validation_output.json` — admin, `needs_config`, narrative, timeline, windbg summary, `data_gaps`, confidence.

**Do not** ask the user to build, run, and upload unless they explicitly want a packaged build test or the agent cannot execute Python on the machine.

### 7.1 Reference hardware (field validation)

Primary test machine: **Alienware m17 R5 (AMD)** — Aug 9 shutdown without matching dump, Aug 4 older minidump, AMD chipset suite 8.07 + PSP/SMBus/GPIO decomposition. Live validation script output on this machine is the baseline for narrative/boot-recovery/CDB behavior.

### 7.2 Build & test (agents)

| Action | Command / rule |
|--------|------------------|
| Tests | `run_tests.bat` from the project root (syncs version first) |
| CI build | `BUILD_NOPAUSE=1` + `build_ci.bat` — **only when user requests build** |
| GUI tests | `QT_QPA_PLATFORM=offscreen`; full suite several minutes |
| Version bump | `bsod_analyzer.py` → `VERSION` only; run `scripts\apply_version.py sync` |

---

## 8. Future / deferred work

**Single source:** [`ROADMAP.md`](ROADMAP.md) — Phases 1–8 in order.

| Phase band | Topic |
|------------|--------|
| **1–6** | Baseline through catalog performance — **complete** |
| **7** | Doc hygiene — **complete** (6.4.77) |
| **8** | Extended driver sources — Chip-Level RFC ([`design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md`](design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md)) — not shipped |
| **Appendix** | Log age display + cleanup UX — deferred ([ROADMAP appendix](ROADMAP.md#appendix--log-age-display--cleanup-deferred)) |

**Declined:** ROADMAP § Closed · PRODUCT_REFERENCE §6.

**Deep dives:** §12 Driver catalog · §10 Chip-Level archive.

---

## 9. Keeping this document current

**Update `PRODUCT_REFERENCE.md` when you ship or materially change:**

- Run Analysis data sources or attribution logic
- In-app remediation (dump enable, CDB, admin, export)
- Agent validation workflow
- Product goals or declined features
- Version in header (match `bsod_analyzer.py`)

**Also update:** [`ROADMAP.md`](ROADMAP.md) (work queue / backlog / phase ☑), `KNOWN_LIMITATIONS.md` (tradeoffs), `DRIVER_VERIFICATION_PLAN.md` (verification phases).

**Do not duplicate** full backlog, audit checklists, or performance plans here — link instead.

---

## 10. Chip-Level Advisory (archived — Phase 8 RFC)

**Canonical copy:** [`docs/design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md`](design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md) (archived 2026-08-13 from Desktop design doc).

| | |
|---|---|
| **Purpose** | Future **opt-in Tier 3** extended/third-party driver discovery, verify pipeline, in-app install, install journal, crash correlation |
| **Shipped from it?** | **Phase A official-path fixes** (through enterprise OEM manifests in [`VERSION.txt`](../VERSION.txt)). **Phases B–F not implemented.** |
| **Active build order?** | **No** — ROADMAP backlog; RFC before any B–F code |
| **Desktop copy** | `BSODAnalyzer_Chip_Level_Advisory_Design.md` may remain as convenience; repo archive is authoritative for clones |

---

## 11. Key code map

**Do not maintain a second module list here** — it drifts after every maintainability slice.

| Need | Canonical doc |
|------|----------------|
| **Where to start for a task** (modules + tests) | [`AGENT_READINESS.md`](AGENT_READINESS.md) § Module navigation |
| **Every production module → audit section** | [`AUDIT.md`](AUDIT.md) § Domain map |
| **Extract / slice scripts** (read before re-planning a cut) | [`scripts/README.md`](../scripts/README.md) § Module extraction |
| **Catalog pipeline behavior** (tiers, timing, deferral) | §12 below |

---

## 12. Driver catalog reference (descriptive)

How **Search for driver updates** works today. **Policy:** speed and accuracy together — no coverage cuts. Full history: [`ROADMAP.md`](ROADMAP.md) § Phase 6 · [`AGENT_HANDOFF_CATALOG_PERFORMANCE.md`](AGENT_HANDOFF_CATALOG_PERFORMANCE.md).

### 12.1 Source tiers (per device)

| Order | Tier | Notes |
|-------|------|-------|
| 1 | **Manufacturer** | NVIDIA / AMD / Intel / Realtek / … scrapers when applicable |
| 2 | **OEM** | Dell/Alienware service-tag API; **+ enterprise manifests** (Dell/HP/Lenovo deployment catalogs, 6.4.78) when supported |
| 3 | **Microsoft** | WU COM + per-HWID online store (batched warm; **no `-All`** in GUI) |
| 4 | **MSCatalog** | Microsoft Update Catalog (PowerShell / MSCatalogLTS) |

Primary GPU display rows may be **manufacturer-authoritative only** (skip lower tiers when vendor lookup applies).

### 12.2 Full GUI scan pipeline

1. WU COM once (~20 s)  
2. Batched HWID online-store warm (~13 s)  
3. **Parallel MSCatalog warm** — unique queries in one `pwsh` process (~2–3 min; **59%** of wall time)  
4. Vendor scrape warm  
5. **4 parallel workers** — per device: tiers above; MSCatalog mostly cache hits  
6. **Gap fallback** (`gui_gap_catalog_fallback`) — HWID-verified name search only for devices with **zero offers**

### 12.3 MSCatalog deferral (accuracy — do not broaden without approval)

`should_defer_microsoft_catalog()` skips MSCatalog when OEM/manufacturer already returned a **useful versioned** answer (same/newer than installed, or nuanced rules when nothing installed). **Realtek NET never defers.** Stale OEM rows and incomparable formats do **not** defer — MSCatalog may have newer UAD builds.

### 12.4 Cache & settings

| Item | Location / default |
|------|-------------------|
| Per-machine catalog cache | `%LOCALAPPDATA%\BSODAnalyzer\driver_catalog\<fingerprint>\` (portable + full install default) |
| Parallel MSCatalog | `gui_mscatalog_batched_parallel: true`, throttle **5**, chunk **24** |
| Legacy prewarm flag | `gui_mscatalog_prewarm: false` (unused — batch warm handles MSCatalog) |
| **Requires** | **PowerShell 7** for ~5 min scans; PS 5.1 falls back to slower sequential batch |

### 12.5 Bundle verification (multi-driver packages)

When a vendor or OEM offer represents a **suite** (AMD Chipset Software, Dell DUP with `inner_versions`, etc.), the app compares **per-component** versions and may **upgrade** a wrapper row from "same" to "newer" when any member is stale (6.5.27+).

| Class | Offer-side manifest | Status |
|-------|---------------------|--------|
| AMD chipset (platform row) | `Info.xml` from AMD chipset package — downloaded/cached under catalog cache (`catalog_amd_chipset_manifest.py`, 6.5.28) | Vendor offer gets `bundle_components`; rollup wired |
| Offers with `inner_versions` | Normalized via `bundle_verification.py` | Rollup on compare |
| Primary GPU + OEM graphics bundle | Display + gpu_companion inventory vs bundle manifest (6.5.29) | Wrapper rollup on primary display row |
| Intel chipset, selective install | Planned — [`DRIVER_BUNDLE_VERIFICATION_PLAN.md`](DRIVER_BUNDLE_VERIFICATION_PLAN.md) | Not yet |

Skipped in **quick-check** catalog mode (no manifest download). Requires **7-Zip** (bundled or on PATH) when `Info.xml` is not embedded in the `.exe` bytes.

### 12.6 After catalog code changes

| Check | Tool |
|-------|------|
| Timing | `py -3 scripts/compare_catalog_scan_timings.py` |
| Accuracy / narrative | `py -3 scripts/live_validate_analysis.py` |
| Tests | `run_tests.bat` |
