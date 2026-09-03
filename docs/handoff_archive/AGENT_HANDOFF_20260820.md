# Agent handoff — BSOD Analyzer (2026-08-20)

> **Superseded for session state** by
> [`AGENT_HANDOFF_20260821.md`](AGENT_HANDOFF_20260821.md) — read that first.
> **Still current here:** §4 component-install model, §5 communication rules,
> §6 field-test checklist, §7 catalog backlog.
> **Stale here:** §2 build status, §10 git state, suite timing in §2.

**Purpose:** Onboard the next agent (Claude or other) to continue **fine-tuning** catalog accuracy, component install, and field validation — without re-litigating settled decisions.

| | |
|---|---|
| **Canonical version (source)** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\bsod_analyzer.py` → `VERSION = "6.5.7"` |
| **Built portable (2026-08-20 ~23:26 local)** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\BSODAnalyzer.exe` |
| **Stable archive** | **Not** auto-saved — user field-tests first; then `scripts\save_stable_build.bat /Force` |
| **Field-test machine** | Alienware **m17 R5 AMD** (portable USB workflow) |
| **Host** | User runs **Cursor as Administrator** — agent shell is elevated |

**This file (full path):**  
`C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_HANDOFF_20260820.md`

**Built portable (full path):**  
`C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\BSODAnalyzer.exe`

---

## 0. Ordered reading list (Claude — read in this order)

Do **not** skip ahead to code until pass 1 is done. Use **full paths** below.

### Pass 1 — Session context (required)

| # | Read | Full path | Why |
|---|------|-----------|-----|
| 1 | **This handoff** | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_HANDOFF_20260820.md` | Today’s work, build state, component-install model, user rules |
| 2 | Agent entry | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\AGENTS.md` | Commands, version sync, tests, builds, portable policy |
| 3 | Product truth | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\PRODUCT_REFERENCE.md` | What ships, agent §2 obligations (run validation yourself) |
| 4 | Readiness | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AGENT_READINESS.md` | Priority order (accuracy → speed → efficiency), validation tiers, module navigation |

### Pass 2 — Before changing catalog / install behavior

| # | Read | Full path | Why |
|---|------|-----------|-----|
| 5 | Limitations | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\KNOWN_LIMITATIONS.md` | Accepted tradeoffs — don’t “fix” as bugs |
| 6 | Roadmap | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\ROADMAP.md` | Work queue (empty), backlog — don’t start parked items unprompted |
| 7 | Status pointer | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\IMPROVEMENT_BACKLOG.md` | Hub only — links, no duplicate plans |
| 8 | Catalog split map | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\CATALOG_MODULE_SPLIT.md` | Where catalog logic lives after facade split |
| 9 | Doc index | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\DOC_MAP.md` | Which doc owns what (avoid editing pointers) |

### Pass 3 — Only when touching that subsystem

| # | Read | Full path | When |
|---|------|-----------|------|
| 10 | Facade / orchestration | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\FACADE_ORCHESTRATION.md` | Changing `bsod_analyzer.py` exports or facade gate |
| 11 | Driver verification (complete) | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\DRIVER_VERIFICATION_PLAN.md` | Crash-linked driver UX |
| 12 | Scripts index | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\scripts\README.md` | Adding or running maintenance scripts |
| 13 | Performance context (may lag version) | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\PERFORMANCE_PLAN.md` | MSCatalog timing design — **verify against code** |
| 14 | Phase 8 RFC (backlog only) | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\design_archive\CHIP_LEVEL_ADVISORY_DESIGN.md` | Only if user promotes Phase 8 |

### Pass 4 — Full audit only (user asks “audit” / “check everything”)

| # | Read | Full path |
|---|------|-----------|
| 15 | Audit procedure | `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\AUDIT.md` |
| 16 | Every doc in DOC_MAP § Active inventory | paths listed in `DOC_MAP.md` |
| 17 | Skill | `%USERPROFILE%\.cursor\skills\agent-code-audit\SKILL.md` |

### Do not read first (historical / stale risk)

- `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\audit_archive\` — old audits  
- `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\EVALUATION.md` — stub; see audit_archive  
- Transcript-only decisions — reconcile against files above

---

## 1. Repository layout

```
BSODAnalyzer/                    ← git root (sparse commits; most app/ may be untracked locally)
├── app/                         ← **all production source + builds**
│   ├── bsod_analyzer.py         ← VERSION single source of truth
│   ├── driver_catalog.py        ← ~665 LOC facade (catalog logic in catalog_*.py)
│   ├── driver_install.py        ← install + component bundle path
│   ├── catalog_device_roles.py  ← NEW 6.5.6 — roles + MSCatalog skip hints
│   ├── catalog_offer_compare.py ← compare + bundle component notes
│   ├── oem_effective_version.py ← inner_versions / per-component compare version
│   ├── device_enrichment.py     ← shared inventory enrichment (Run Analysis + Load Devices)
│   ├── docs/                    ← canonical docs (DOC_MAP.md indexes all)
│   ├── tests/                   ← 123 test files; run_tests.bat
│   ├── scripts/                 ← apply_version.py, live_validate_analysis.py, extract_*.py
│   └── BSODAnalyzer_v6/         ← PyInstaller portable output (v6.5.7)
├── EVALUATION.md, PERFORMANCE_PLAN.md  ← design context (may lag version)
└── .cursor/rules/               ← agent rules (product-reference, audit, phased design)
```

**Portable-first:** settings in `BSODAnalyzer_portable\`, per-machine catalog under `driver_catalog\<fingerprint>\`.

---

## 2. Build & validation (agent runs these)

| Task | Command (cwd: `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\app`) |
|------|--------|
| Sync version | `py -3 scripts\apply_version.py 6.5.7` or bump `VERSION` then `sync` |
| Tests | `run_tests.bat` (~6–7 min full suite) |
| CI build | `set BUILD_NOPAUSE=1` then `build_ci.bat` → `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\BSODAnalyzer.exe` |
| Live validation (admin) | `py -3 scripts\live_validate_analysis.py` → `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\live_validation_output.json` |
| Facade gate (if build fails) | `py -3 scripts\audit_facade_complete.py` → `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\_FACADE_AUDIT_REPORT.txt` |
| Catalog timing compare | `py -3 scripts\compare_catalog_scan_timings.py` (read-only, `%TEMP%\BSODAnalyzer\session_log.jsonl`) |

**6.5.8 build status:** Portable rebuilt 2026-08-21 — see `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\BSODAnalyzer.exe`. **Field sign-off on m17 R5 still pending.**

---

## 3. What we covered today (2026-08-20)

### 3.1 User-reported field issues (Alienware m17 R5)

| Issue | Root cause | Fix version |
|-------|------------|-------------|
| Crash clicking driver row | `@staticmethod` on method using `self` | **6.5.4** |
| Dell ACC shown as update for DBUtilDrv2 / DellInstrumentation | OEM suite-app filter missing "command center"; bogus version compare | **6.5.5** |
| LG monitor + SWC duplicate WU offers | WU trusted without HWID; no dedup | **6.5.5–6.5.6** |
| Load Devices not feeding catalog roles downstream | Roles not applied after enrichment | **6.5.6** |
| NPCF "newer" vs GeForce same @ 1088 | Separate PnP node; bundle vs component compare confusion | **6.5.7** compare notes + install path |
| Scan time reporting ambiguous ("Larger") | Agent communication error | **Process fix** — see §5 |

### 3.2 Shipped in source (6.5.6 → 6.5.7)

**6.5.6 — Catalog accuracy (no intentional scan-scope reduction)**

| Change | Files | Scan time | Accuracy |
|--------|-------|-----------|----------|
| Device roles from inventory | `catalog_device_roles.py`, `device_enrichment.py` | **Saves time** on skipped MSCatalog rows | **Improves** (LG parent/child, Dell internal) |
| WU `UpdateId` global dedup | `catalog_wu_scoring.py` `_batch_prefilter_wu_rows` | **No meaningful change** | **Improves** |
| Skip MSCatalog on monitor+SWC child, Dell internal | `catalog_mscatalog_queries.py` | **Saves time** per skipped device | **Improves** (child still searched) |
| SWC-on-monitor reject | `catalog_row_rejects.py` | — | **Improves** |

**6.5.7 — Component bundle model (general, not NPCF-only)**

| Change | Files |
|--------|-------|
| ACPI/instance inner version match | `oem_effective_version.py` `pick_inner_version_for_ctx` |
| Bundle compare notes (component-only install warning) | `catalog_offer_compare.py` `_append_oem_bundle_component_note` |
| Component extract → HWID INF → targeted pnputil | `driver_install.py` |
| Per-component downgrade gate (not wrapper vs GPU) | `driver_install.py` `component_install_version_gate` |
| Install passes `device_ctx` from GUI | `gui_mixin_catalog_install.py`, `bsod_gui_workers.py` |
| Failure copy (extract fail / no INF / don't run full bundle) | `driver_install.py` message helpers |
| Tests | `tests/test_catalog_device_roles.py`, `tests/test_driver_install_selective.py` |

### 3.3 Explicitly NOT shipped (user rejected accuracy risk)

| Item | Why |
|------|-----|
| **P2b smarter MSCatalog deferral** (skip searches when OEM says same) | **Risk if done wrong** — can miss updates (Realtek numbering, etc.) |
| **Skip generic USB/HID name searches** | Same category — not implemented |
| **P2a disk MSCatalog cache** | User passed — ~3–6 min scans acceptable; stale-cache risk |

**Already in codebase (not new in 6.5.6):** per-scan MSCatalog query dedup (`_search_mscatalog_updates_cached`, `warm_batched_mscatalog_queries`) — **saves time, no accuracy change**.

---

## 4. Component install — settled product model

**Rule:** Multi-driver OEM/chipset bundles are always **evaluated and installed at component granularity** for the **selected device row**. NPCF is the example; same for chipset INF vs suite headline, Realtek multi-INF, etc.

### Pipeline (target state)

```
Discover → inner_versions from OEM API
Compare  → resolve_offer_effective_version(offer, device_ctx)  [this row only]
Report   → "newer" if component > installed on THIS row; notes if other bundle parts older
Install  → extract (7z/cab/zip/exe) → find_inf_dirs_for_hwid_tokens → pnputil ONE dir
Gate     → component_install_version_gate — block if component would downgrade THIS row
Failure  → honest message; never silently launch full vendor EXE when device selected
```

### Status

| Step | Status |
|------|--------|
| Compare per-component | **Done** (with ACPI prefix; PCI inner match) |
| Report notes | **Done** |
| Install extract + HWID INF + pnputil | **Done** in source |
| Downgrade gate per component | **Done** in source |
| GUI device_ctx wiring | **Done** |
| Dell DUP `-s` silent extract when 7-Zip fails | **Not done** — top next slice |
| Field proof on real Dell GeForce DUP (NPCF) | **Pending** user test on m17 R5 |
| Confirm dialog says "component-only" | **Minor UX** — not done |
| Chipset bundle when `inner_versions` empty | **Partial** — INF token fallback exists; may need chipset-specific tokens |

### NPCF reference (user machine)

| Row | Installed | Relevant bundle piece | Correct action |
|-----|-----------|----------------------|----------------|
| GeForce primary | 32.0.16.1088 | Display 1060 in bundle | **Do not install** (older) |
| NPCF companion | 32.0.16.1051 | NPCF 1060 in bundle | **Valid update** — component INF only |

**Wrong gate (rejected):** blocking NPCF because bundle display portion < GPU. **Right gate:** compare/install NPCF component version vs NPCF installed only.

---

## 5. Communication & process rules (user is strict on these)

1. **Scan time tables:** Always **Saves time / No meaningful change / Costs time** — never "Larger" or ambiguous magnitude without direction.
2. **Accuracy column:** **Improves / No meaningful change / Risk if done wrong** — never imply speed work automatically costs accuracy without separating items.
3. **Scan baselines:** Use **complete** scans only (full device count in export). Do **not** cite the Aug 20 ~2.9 min scan #2 — incomplete/fluke.
4. **Transcript:** This thread (`6b4df7f3-7af6-4c03-98aa-3df0964ac93d`) + Jul 29 P0/P1 scan-time format — re-read before repeating mistakes.
5. **Agent obligations:** Run tests, live validation, builds yourself — see `PRODUCT_REFERENCE.md` §2.
6. **Audit Improve ≠ ROADMAP** — see `AGENT_READINESS.md` § Audit findings reconciliation.

---

## 6. Field-test checklist (m17 R5, portable 6.5.8+)

Copy `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\BSODAnalyzer_v6\` to USB, run **as Administrator**.

### Catalog accuracy (6.5.5–6.5.7)

1. Load devices → inventory count ~150.
2. Search for updates → **complete** scan; export shows **full** device count (do not use incomplete scans as timing baseline).
3. **LG:** WU offer on SWC child only; monitor parent not duplicate "newer".
4. **ACC / DellInstrumentation:** no false Dell Command Center update.
5. **NPCF:** if "newer", compare note mentions component-only / display portion older than GPU.
6. **Install (optional, careful):** NPCF Install attempts extract + HWID match — **not** full Dell wizard; clear message if extract fails.

### Harness / bug-fix regressions (6.5.8 — see `AGENT_HANDOFF_20260821.md` §2.3)

7. **Attached devices:** WU/Microsoft offers appear for external-monitor SWC, USB audio, docks (were missing when OEM rules hit WU rows).
8. **Firmware tab:** Download completes after confirmation (was `ValueError` on every click).
9. **Activity history** (full-install mode): dialog opens (was `NameError` on `mlog`).
10. **MSI board:** motherboard support link present (WMI name match, not literal `"msi"`).
11. **Reliability bundle:** LiveKernel events do not abort entire reliability query (undefined import fixed).
12. **Event times:** crash/shutdown labels are local-aware — not falsely suffixed `UTC` for local Event Log strings.

Session logs: `%TEMP%\BSODAnalyzer\session_log.jsonl` and Desktop exports `BSODAnalyzer_catalog_scan_*.json`.

---

## 7. Fine-tuning backlog (recommended next work)

Priority from user arc — **accuracy first**, then install hardening, then speed only without accuracy risk.

| Priority | Work | Scan time | Accuracy |
|----------|------|-----------|----------|
| **P0** | Field-verify 6.5.7 on m17 R5; fix regressions from export | — | — |
| **P1** | Dell DUP extract fallback (`-s` or vendor-specific) when 7-Zip can't open EXE | No change | **Improves** install success |
| **P1** | Install confirm dialog: "component-only from multi-driver bundle" | No change | UX clarity |
| **P1** | Per-component compare for chipset rows when suite headline ≠ INF version (extend existing `catalog_chipset_comparison.py` patterns) | No change | **Improves** |
| **P2** | Export scan phases with explicit saves/costs in JSON | No change | Reporting |
| **P3** | Tune parallel MSCatalog throttle on user's network | **Saves time** if catalog site keeps up | No change if cache-only |
| **Defer** | P2a disk cache, P2b deferral | Saves time | **Risk if wrong** |

**ROADMAP work queue:** empty — promote from backlog only when user asks (`ROADMAP.md` § Backlog: Phase 3d, Log cleanup UX, Phase 8 chip-level advisory).

**Maintainability:** catalog split, crash-report split, facade Option 2 — **complete** (6.5.0 milestone). No mandatory slicing before product fine-tuning unless user redirects.

---

## 8. Key modules for catalog/install work

| Module | Role |
|--------|------|
| `catalog_device_roles.py` | `catalog_role`, `catalog_skip_mscatalog`, parent/child index |
| `catalog_offer_compare.py` | `vs_installed`, reporting policy, bundle notes |
| `catalog_wu_scoring.py` | WU batch assignment, `_batch_prefilter_wu_rows` |
| `catalog_row_rejects.py` | Row-level rejects (`swc_driver_update_on_monitor`, etc.) |
| `catalog_oem_filters.py` | OEM brand/suite-app filters (ACC, etc.) |
| `oem_effective_version.py` | `inner_versions`, `resolve_offer_effective_version` |
| `driver_install.py` | Install pipeline + component path |
| `catalog_mscatalog_session.py` | MSCatalog cache, batch prewarm, dedup |
| `catalog_tier_policy.py` | GPU manufacturer-authoritative (skips redundant OEM/MS on primary GPU) |
| `driver_version_identity.py` | Cross-scheme version equivalence (Realtek NIC, etc.) |
| `gui_mixin_catalog_install.py` | Install UI, `_device_context_for_install` |

---

## 9. Known open accuracy items (from field logs, may persist until verified)

- **NPCF false "newer"** if inner version not resolved — depends on Dell DUP metadata + ACPI match; verify after 6.5.7 field run.
- **Five "newer" rows on 2043 export** — largely false positives (ACC×2, LG×2, NPCF); 6.5.5–6.5.7 address root causes — **confirm on fresh scan**.
- **Scan wall time ~6.5 min** on 150 devices (complete scan #1 Aug 20) — MSCatalog network dominates; role skips save modest time only.

---

## 10. Git / commit state

- Git root: `BSODAnalyzer/` — mostly **untracked** `app/` tree locally; last commit on master: minidump CDB fix (older).
- **No commit requested** for 6.5.4–6.5.7 work in this session.
- User rule: only commit when explicitly asked.

---

## 11. Docs to update when shipping capabilities

Per `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\PRODUCT_REFERENCE.md` header rule — bump **Last updated** and version references in:

- `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\PRODUCT_REFERENCE.md` §3 (if install behavior changes materially)
- `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\KNOWN_LIMITATIONS.md` (if accepting new limits)
- `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\VERSION.txt` via `apply_version.py` preset
- Link or supersede this handoff when field sign-off is done

---

## 12. One-line summary for Claude

**BSOD Analyzer v6.5.8 portable is built (`BSODAnalyzer_v6\BSODAnalyzer.exe`, 2026-08-21). Field-test on Alienware m17 R5 using §6 checklist (catalog + harness regressions). Next: Dell DUP extract fallback, audit harness gates, git commit if user wants it.**
