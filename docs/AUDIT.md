# Audit

When you ask for **an audit**, that means **everything** — one pass, no gaps. Report **only Fix and Improve**.

**Improve ≠ backlog.** **Improve** is an audit finding category (works but could be better). **Backlog** is parked **product work** in [`ROADMAP.md`](ROADMAP.md). When the user says **“improve list”** or **“audit items”**, they mean audit **Fix/Improve** output — not the ROADMAP backlog.

---

## Coverage contract (read first)

This document is the **complete, closed scope** for every audit. There are:

- **No partial audits**
- **No “extend coverage later”**
- **No “worth adding to the checklist”** in audit reports
- **No Phase A/B, overlays, or add-ons menus**

The agent runs **`run_audit.cmd`** (machine + semantic gate, step 1) **and** executes **every section A–N** below (code review). Findings go under **Fix** or **Improve** only. Complete the audit with **`scripts\finalize_audit.cmd`** after the semantic report passes verify (step 3).

If the project gains a **new subsystem** (new top-level module or major folder), update **this file’s domain map** and **`run_audit.ps1`** in the same change — not as a follow-up audit suggestion.

---

## How to run

```bat
cd app
run_audit.cmd
scripts\verify_semantic_audit.cmd
scripts\finalize_audit.cmd
```

**One standard:** full `run_tests.bat` + all machine/code checks on step 1. **Do not use `-SkipTests`** for an audit — that is incomplete and will fail Fix. Step 3 **`finalize_audit.cmd`** re-runs machine + semantic verify without retesting when manifest test proof is still valid.

Machine script + agent together = full audit. Merge all findings into Fix and Improve.

---

## Agent deep scan (mandatory with every audit)

The machine gate (`run_audit.cmd`) does **not** replace human/agent review. **Passing finalize with blanket “Nothing found.” on every section without reading the codebase is an incomplete audit — forbidden.**

Every audit **must** include the steps below **before** claiming complete. Report gaps only as **Fix** or **Improve**.

**Two full reads:** (1) **every domain-map production module** — awareness even when no code change is safe yet; (2) **every active doc in [`DOC_MAP.md`](DOC_MAP.md)** — duplication, stale commands, and contradictions are **Improve** territory (§2c, §M). Do not duplicate work on top of stale or parallel docs because you skipped the read.

### Incomplete audit (forbidden)

| Shortcut | Why it fails |
|----------|----------------|
| Machine gate only (`run_audit.cmd` + empty semantic JSON) | Skips all code/doc review |
| Bulk `"Nothing found."` on A–N without opening domain-map modules | Not a deep scan |
| Bulk `"Nothing found."` on **M** without reading every doc in [`DOC_MAP.md`](DOC_MAP.md) | Doc review skipped |
| Missing `modulesReviewed[]` for D–K | Cannot prove per-module review |
| Stale semantic (`generatedAt` before test pass, or `testsGitHead` drift) | Reuses old review |
| FinalizeOnly without a **same-session** semantic pass | Reuses stale review |
| Subset tests or `-SkipTests` | Not full suite |
| “Gate clean so we’re done” | Gate ≠ audit |

### Minimum evidence per section (semantic report)

For each letter **A–N**, the semantic `summary` must reflect **work done in this session**:

- **Clean section:** `"Nothing found."` only after reviewing every checklist bullet **and** every domain-map module for that letter (or machine fixes already listed).
- **Non-clean:** cite at least one `` `path/file.ext` `` or `tests/...` in the summary text; populate `evidence[]`.
- **Section B:** copy `inventoryAck` counts exactly from auto-generated `docs/.audit_inventory.json` (written on test pass).
- **Sections D–K:** list every expanded domain-map module for that letter in `modulesReviewed[]` (see `docs/.audit_domain_expanded.json`).
- **Section M:** read every file in [`DOC_MAP.md`](DOC_MAP.md) inventory; copy **`docReviewAck`** from `docs/.audit_doc_inventory.json` (generated on test pass); summary must cite doc count reviewed or ≥1 concrete doc finding.
- **All sections:** set top-level `testsGitHead` from `docs/.audit_agent_manifest.json`; `generatedAt` must be **after** `testsPassedAt`.

**Domain map:** every production `*.py` at project root (except dev-only `preview_amd_logos.py`) must map to a section. Orphans → **Fix** (add to map) or **Improve** (remove/merge module). Machine gate flags unmapped root `*.py` automatically.

### 1. Repository inventory

- Count trackable files under the repo (exclude only gitignored build trees: `dist`, `build`, bundled `BSODAnalyzer_v6/_internal` unless checking packaging).
- Record: Python module count, test file count, approximate Python LOC, markdown/rules/assets/scripts counts.
- List **orphan production modules** (root `*.py` not in the domain map below).
- Note runtime/machine data that must not live in source (`BSODAnalyzer_portable/`, `live_*.json`, export baselines).

### 2. Static analysis (production code)

Run or equivalent review:

- `except:` / bare `except Exception: pass` — log, narrow, or document intentional callback guards.
- `shell=True`, `os.system`, `eval`/`exec` (excluding Qt `.exec()`), hardcoded secrets, unsafe pickle/yaml.
- Modules **>2000 lines** — maintainability risk; cross-check [`docs/CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md).
- Stale path grep: `Opus`, `BSODAnalyzer_Opus`, `junction`, forbidden audit artifacts.
- `.gitignore` gaps for recurring cruft.

### 2b. Efficiency, dead code & redundancy (production code)

Beyond correctness — keep the codebase lean so scans and analysis stay fast on modest hardware:

| Look for | Report as |
|----------|-----------|
| **Dead code** — unreachable branches, unused functions/imports, orphaned settings keys, commented-out blocks that duplicate live paths | **Improve** (remove when safe + tested) or **Fix** if it misleads maintainers |
| **Redundant work** — duplicate helpers, repeated network/PS/subprocess calls in hot paths (catalog warm, per-device loop, analysis gather) | **Improve** (consolidate or cache) |
| **Spaghetti coupling** — cross-import cycles, god-module calls that bypass established module boundaries | **Improve** — tie to [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) |
| **Resource waste** — unbounded lists, duplicate full inventory builds, redundant WMI passes in one user action | **Improve** |

**When writing code (not only auditing):** prefer one clear path, reuse existing helpers, avoid copy-paste tiers, and do not add settings or branches “for later” without a tracked work-queue item.

### 2c. Documentation — read everything; report duplication & drift

Every **full audit** must **read all active docs** in [`DOC_MAP.md`](DOC_MAP.md) (not only machine stale-pattern scans). Same standard as code: **awareness first** — report **Improve** even when you do not edit, so agents do not duplicate on top of stale or parallel docs.

| Look for | Report as |
|----------|-----------|
| **Stale facts** — wrong version, old command (`build_and_deploy_v5.bat` vs `build_ci.bat`), obsolete paths | **Fix** if it breaks build/test/agent workflow; else **Improve** |
| **Duplicated content** — same backlog table, audit steps, or obligations copied in pointer docs | **Improve** — cite canonical owner in [`DOC_MAP.md`](DOC_MAP.md) |
| **Contradictions** — portable-first, audit steps, test commands differ between docs/rules | **Fix** or **Improve** by severity |
| **Missing pointer** — new doc with no row in `DOC_MAP.md` | **Improve** (add to map same session if you add a doc) |
| **Rule bloat** — `.mdc` repeats paragraphs from canonical markdown | **Improve** — thin rule + link only |
| **Archive treated as live** — `audit_archive/`, root `EVALUATION.md` stubs cited as current policy | **Improve** |

**Do not** add new plan items to `IMPROVEMENT_BACKLOG.md` — update `ROADMAP.md` or link only. **Do not** create a second doc when `DOC_MAP.md` already assigns an owner.

**Speed / accuracy tradeoff:** doc dedup is **Improve**, not mandatory pre-release — unless wrong commands cause failed tests or wrong product behavior.

### 3. Semantic review — sections A–N

For **each** section A–N in the checklist below:

- Read `docs/.audit_agent_manifest.json` → `machineFixesBySection[letter]`.
- If machine listed fixes → semantic summary **must** cite them + `evidence[]`.
- If machine clean → review `agentFocus` / checklist items anyway (code, docs, assets, rules, scripts).
- Record in `docs/.audit_semantic_report.json` — **all 14 sections**, `reviewed: true`.

### 4. Close the gate

```bat
run_audit.cmd
scripts\verify_semantic_audit.cmd
scripts\finalize_audit.cmd
```

Do **not** claim audit complete unless finalize exits **0**.

---

## Full checklist (A–N, all mandatory)

### A. Tests & version
- `run_tests.bat` with `QT_QPA_PLATFORM=offscreen` — full suite
- `bsod_analyzer.py` ↔ `VERSION.txt` synced
- `BSODAnalyzer_v6\VERSION.txt` matches canonical `VERSION` when present
- `tests/test_version_consistency.py` passes

### B. Files & folders (entire repo tree)
- Layout matches `PROJECT_LAYOUT.md` — canonical paths exist, no unexpected duplicates
- **All** active markdown (`*.md` at repo root, `docs\`, `AGENTS.md`) — read per [`DOC_MAP.md`](DOC_MAP.md); no stale paths (Opus, junction, interim rename), no contradictions with current layout
- Build cruft: no `dist\`, `build\`, duplicate `BSODAnalyzer_v6_stable\`, stale `live_*.json`, stale `*.log` in repo root
- Test/cache cruft: no committed `__pycache__` / `.pytest_cache` trees that should be gitignored
- No committed secrets: `.env`, API keys, tokens, private keys in tracked files (excluding test fixtures and bundled third-party trees)
- `proposed_patches\`, obsolete migration scripts, duplicate launchers — delete or **Improve** if still needed
- Stable policy: `Desktop\BSODAnalyzer_StableBuilds\` — max **3** user-approved stables; validated dev baseline **6.4.78+** (see `PROJECT_LAYOUT.md` § Stable builds)
- No forbidden audit artifacts: old overlay/checklist rules, `run_tests_with_timeout.bat`, active `CODE_AUDIT_*.md` outside `audit_archive\`
- Large or misplaced artifacts (old exports on Desktop, duplicate exes, stray Desktop folders) — **Fix** or **Improve**
- Phase 8 OneDrive cleanup status consistent with `ONEDRIVE_CLEANUP.md`

### C. Build, packaging & bundled runtime
- `BSODAnalyzer_v6\BSODAnalyzer.exe` exists; dist `VERSION.txt` matches code
- `build_and_deploy_v6.bat` does not auto-save stables
- `BSODAnalyzer.spec`, `finalize_portable_dist.py`, `build_ci.bat` — portable layout correct
- Bundled runtime paths valid: CDB / DebuggingTools, PowerShell 7, 7-Zip (`test_portable_build_smoke.py`, `test_powershell7.py`, `test_seven_zip_runtime.py`)
- Dist README synced (`sync_dist_readme.py` / `BSODAnalyzer_v6\README.txt`)

### D. Code — BSOD analysis, hardware & reports
- `bsod_analyzer.py` — analysis pipeline, recommendations, CDB/minidump, report formatting
- `gather_report_data`, `newest_minidump_analysis` — correct “latest” selection
- Event 1001 / minidump gaps — regressions only (not accepted limitations)
- Redundant gather passes or duplicate event-log reads in one analysis run → **Improve**
- Crash-linked driver workflow — `has_crash_faulting_driver`, deferred update checks
- `bsod_runtime.py` — PowerShell runner, paths, export helpers
- `bsod_hardware_wmi.py` — WMI/PnP inventory correctness

### E. Code — GUI, threads, workers & theme
- `bsod_gui_qt.py`, `gui_mixin_*`, `bsod_gui_workers.py`, `gui_signal_relay.py`
- Long work off main thread; no UI updates from workers (`test_gui_main_thread_guard.py`)
- Driver vs firmware vs export — mutual exclusion during scans (`test_pre_compile_hygiene.py`)
- Progress bars and flags reset on finish, error, cancel
- Shutdown: thread / `BackgroundJob` cleanup on window close
- Theme, accessibility, warning colors — regressions in catalog rows and data-gap HTML

### F. Code — settings, paths & portable-first
- `app_settings.py` — portable vs full-install; OneDrive settings fallback (6.4.61+)
- Catalog cache per machine fingerprint in portable mode (`catalog_cache.py`)
- **Portable-first policy** (`AGENTS.md`): new/changed code defaults to portable workflow; full-install-only paths need documented justification
- `tests/test_data_dir_settings.py` and related path tests pass

### G. Code — driver catalog, index & vendors
- `driver_catalog.py`, `driver_index.py`, `driver_list_build.py`
- `catalog_scoring.py`, `catalog_offer_pipeline.py`, `catalog_oem_live.py`, `catalog_mscatalog_session.py`, `catalog_device_profiles.py`
- `catalog_ps_module.py`, `catalog_ps_batch.py` — PS catalog batch pipeline
- `vendor_fetch.py`, `vendor_extractors.py`, `vendor_extractor_repair.py`, `vendor_endpoint_health.py`, `vendor_endpoint_audit.py`
- `oem_effective_version.py`, `gpu_vendor_maps.py`
- Hint vs verified scan; driver version identity
- Swallowed exceptions that hide failures → **Fix**
- Dead, duplicate, or unreachable catalog/analysis paths → **Improve** (see §2b)
- Vendor URL rot: `test_catalog_audit_coverage`, `test_vendor_endpoint_health`, `test_parser_rot_detection`, `test_vendor_source_hardening`

### H. Code — firmware
- `firmware_catalog.py`, `vendor_firmware_fetch.py`
- `firmware_ssd_vendors.py`, `firmware_peripheral_vendors.py`, `firmware_peripheral_discovery.py`, `firmware_peripheral_installed.py`
- `gui_mixin_firmware.py` — firmware tab workers and UI
- SSD vs peripheral coverage; batch warm; attention filters
- Tests: `test_vendor_firmware_fetch`, `test_firmware_*`, `test_analysis_firmware_inventory`

### I. Code — export, install & backup
- `catalog_export.py` — export correctness, portable vs full-install paths
- Export blocked while driver/firmware scans run
- `driver_install.py`, `driver_backup.py` — install/backup flows
- `tests/test_catalog_export.py`, `test_driver_install_flow.py`, `test_update_reporting_policy.py`

### J. Code — session, logging & preferences
- `session_log.py` — session logging, rotation, no silent log loss
- `bsod_gui_preferences.py` — prefs persist correctly in portable and full-install modes
- `tests/test_session_log.py`

### K. Security & subprocess hygiene
- No hardcoded credentials or live tokens in source
- Subprocess / shell invocation — no unsafe string concatenation with untrusted paths in export, fetch, and install paths
- Vendor fetch and catalog scripts — timeouts and failure surfaces visible to UI/logs

### L. Agent / Cursor wiring
- Only `audit.mdc` + `docs/AUDIT.md` + `agent-code-audit` skill — no legacy audit rules
- `AGENTS.md` matches current commands (`run_tests.bat`, `run_audit.cmd`, `build_ci.bat`)
- **Audit harness (Section L):** `verify-audit-system.ps1` passes when `run_audit.cmd` reaches a **complete semantic pass** (see machine layer table). After **audit-system** edits, run `scripts\sync_audit_system.cmd` then `verify-audit-system.ps1` before product audit. Product machine checks (L wiring, gitignore, forbidden rules) run every audit via `audit_code_checks.py`.
- Project rules do not contradict portable-first or audit protocol

### M. Docs & reference consistency

**Read [`DOC_MAP.md`](DOC_MAP.md) inventory end-to-end** — every file listed, plus any new `*.md` / `.mdc` not yet in the map.

- Root `README.md`, `PROJECT_LAYOUT.md`, `BUILD_NOTES.md`, `CONSOLIDATION.md` — accurate or clearly archived stub
- `AGENTS.md`, `docs/PRODUCT_REFERENCE.md`, `docs/AGENT_READINESS.md`, `docs/ROADMAP.md`, `docs/IMPROVEMENT_BACKLOG.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/CATALOG_MODULE_SPLIT.md` — consistent with each other; pointers do not duplicate ROADMAP tables
- `.cursor/rules/*.mdc` and repo `.cursor/rules/product-reference.mdc` — thin triggers only; no contradictions with canonical docs
- Prefer linking to `VERSION.txt` over stale hard-coded version numbers in doc headers (`VERSIONING.md`, phase headers)
- HTML mockups under `docs\` — no dead Opus/junction paths unless archived
- §2c duplication/stale findings — at least note “reviewed DOC_MAP overlap zones” in semantic summary (or list specific **Improve** lines)

Semantic **M** summary must name **doc count reviewed** or cite **≥1** concrete doc finding (including “nothing found after full DOC_MAP read”).

### N. Recent changes
- If `VERSION` bumped recently, re-read all files changed for that release against sections D–M

### Reference only (do not report unless wrong)
- [`ROADMAP.md`](ROADMAP.md) — product work queue and backlog
- [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — accepted tradeoffs
- [`IMPROVEMENT_BACKLOG.md`](IMPROVEMENT_BACKLOG.md) — status pointer only (not audit Improve, not the backlog)
- [`audit_archive/`](audit_archive/) — historical audits
- `scripts\` dev/diag tools — report only if broken, committed secrets, or blocking build/test

---

## Domain map (every production module → section)

| Module / area | Section |
|---------------|---------|
| `bsod_analyzer.py`, `analyzer_gather.py`, `analyzer_hardware.py`, `bsod_minidump.py`, `bsod_crash_report.py`, `crash_report_events.py`, `crash_report_timeline.py`, `crash_report_culprit.py`, `crash_report_fix_plan.py`, `crash_report_format.py`, `crash_report_narrative.py` | D |
| `bsod_events.py`, `bsod_workflow.py`, `device_enrichment.py` | D |
| `driver_verification.py`, `log_attribution.py`, `log_read_windows.py` | D |
| `action_plan_ui.py`, `system_health_actions.py` | D |
| `bsod_runtime.py` | D, I |
| `bsod_hardware_wmi.py` | D |
| `gui_mixin_minidump.py` | D, E |
| `bsod_gui_qt.py`, `gui_qt_bootstrap.py`, `gui_mixin_shell.py`, `gui_mixin_settings.py`, `gui_mixin_catalog_layout.py`, `gui_mixin_catalog_shell.py`, `gui_mixin_task_progress.py`, `gui_mixin_maintenance.py`, `gui_mixin_lifecycle.py`, `gui_mixin_window_chrome.py`, `gui_mixin_tabs.py`, `gui_mixin_system.py` | E |
| `gui_mixin_action_plan.py` | E |
| `gui_mixin_analysis.py` | D, E |
| `gui_mixin_drivers.py`, `gui_mixin_drivers_table.py`, `gui_mixin_drivers_inventory.py`, `gui_mixin_drivers_workflow.py` | E, G |
| `gui_mixin_firmware.py`, `gui_mixin_firmware_workflow.py`, `gui_mixin_firmware_inventory.py`, `gui_mixin_firmware_table.py`, `gui_mixin_firmware_scan.py` | E, H |
| `gui_mixin_catalog.py`, `gui_mixin_catalog_scan.py`, `gui_mixin_catalog_packages.py`, `gui_mixin_catalog_install.py`, `gui_mixin_catalog_export.py` | E, G |
| `gui_mixin_firmware.py` | E, H |
| `gui_mixin_vendor_health.py` | E, G |
| `gui_app_context.py`, `gui_app_icon.py`, `gui_checkbox_style.py`, `gui_html_safe.py`, `gui_include_header.py`, `gui_vendor_icons.py` | E |
| `bsod_gui_workers.py`, `gui_signal_relay.py`, `gui_widgets.py`, `gui_*` chrome | E |
| `fix_progress.py`, `gui_catalog_parallel.py`, `gui_theme.py` | E |
| `app_settings.py`, `catalog_cache.py`, `hardware_cache.py`, `system_network_power.py` | F |
| `driver_catalog.py`, `driver_index.py`, `driver_list_build.py`, `driver_version_identity.py` | G |
| `catalog_scoring.py`, `catalog_offer_pipeline.py`, `catalog_oem_live.py`, `catalog_mscatalog_session.py`, `catalog_device_profiles.py`, `catalog_device_roles.py`, `catalog_http.py`, `catalog_oem_filters.py`, `catalog_row_rejects.py`, `catalog_device_context.py`, `catalog_tier_policy.py`, `catalog_offer_status.py`, `catalog_offer_compare.py`, `catalog_none_reason.py`, `catalog_realtek_queries.py`, `catalog_realtek_fetch.py`, `catalog_network_fetch.py`, `catalog_extended_fetch.py`, `catalog_multi_device.py`, `catalog_download.py`, `catalog_system_actions.py`, `catalog_vendor_offers.py`, `catalog_oem_offers.py`, `catalog_ps_context.py`, `catalog_scan_summary.py`, `catalog_online_store.py`, `catalog_device_comparison.py`, `catalog_mscatalog_queries.py`, `catalog_chipset_comparison.py`, `catalog_installed_packages.py`, `catalog_lru_cache.py`, `catalog_vendor_cache.py`, `catalog_wu_scoring.py`, `catalog_microsoft_scoring.py`, `catalog_microsoft_fetch.py`, `catalog_intel_fetch.py`, `catalog_amd_fetch.py`, `catalog_nvidia_fetch.py`, `catalog_ps_module.py`, `catalog_ps_batch.py` | G |
| `catalog_export.py` | G, I |
| `vendor_fetch.py`, `vendor_extractors.py`, `vendor_extractor_repair.py` | G |
| `vendor_download_resolve.py`, `vendor_page_render.py` | G |
| `vendor_endpoint_health.py`, `vendor_endpoint_audit.py` | G |
| `oem_effective_version.py`, `gpu_vendor_maps.py`, `oem_enterprise_catalog.py` | G |
| `firmware_catalog.py`, `vendor_firmware_fetch.py` | H |
| `firmware_ssd_vendors.py`, `firmware_peripheral_*.py` | H |
| `driver_install.py`, `driver_backup.py` | I |
| `session_log.py`, `bsod_gui_preferences.py` | J |
| `bsod_gui_log_cleanup.py`, `log_cleanup.py`, `maintenance_log.py`, `timestamped_log_io.py` | J |
| `product_version.py`, `BSODAnalyzer.spec`, `build_*.bat`, `finalize_portable_dist.py` | C |
| Tests: `tests\` | A (+ domain sections they cover) |
| Pytest bootstrap: `conftest.py` (app root) | A |
| Agent: `.cursor\`, `AGENTS.md`, starter pack | L |

**Dev-only (excluded from domain-map auto-check):** `preview_amd_logos.py` · all `scripts\*.py` (listed in `docs/AUDIT.config.json` `excludeModules`)

---

## Automation (manifest 2.4)

| Check | How |
|-------|-----|
| **Tests** | Full **`run_tests.bat`** only — every `tests/test_*.py`; no subset, no `-SkipTests` |
| **sectionTests in config** | Coverage map for D–K; execution via full suite only |
| **Agent manifest** | `docs/.audit_agent_manifest.json` — **all sections A–N** from checklist + hints + domain map |
| **Semantic report (machine-verifiable)** | Tooling auto-writes template + `docs/.audit_inventory.json` + `docs/.audit_domain_expanded.json` on test pass; **auditor** fills `docs/.audit_semantic_report.json` |
| **Audit receipt** | `docs/.audit_receipt.json` on successful finalize (gitignored) |
| **Except-pass allowlist** | `docs/audit_allowlist.json` — documented intentional `except: pass` lines (committed) |
| **Finalize (no retest)** | `scripts\finalize_audit.cmd` after semantic verify — reuses manifest `testsGitHead` (git SHA or `tree:…` fingerprint); full `run_audit.cmd` only if tree changed |
| **Phase timing** | `docs/.audit_timing.jsonl` — per-phase seconds appended each run (gitignored) |
| **machineCoverage** | Manifest maps every enabled machine check per section + `agentFocus` hints for semantic review |
| **Section F / L / M / N machine** | F: portable policy; L: wiring; M: version docs + HTML stale; N: git VERSION delta |
| **Template** | `scripts\write_semantic_audit_template.cmd` after machine pass |
| **`-SkipTests` debug** | Lightweight path (no import smoke); still fails incomplete |
| **Audit file set** | `pack/audit/manifest.json` |
| **Sync drift** | Every audit runs `sync-audit-system.ps1 -VerifyOnly` |
| **Section L harness verify** | `verify-audit-system.ps1` runs at end of `run_audit.cmd` **only when** semantic report verify passed **and** sync drift check passed. Skipped when semantic incomplete (finish report first) or sync drift (run `sync_audit_system.cmd`). Independent of product Fix lines (e.g. Section M stale docs). |

Scripts: `%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\` (`run_audit_core.ps1`, `audit_code_checks.py`, `sync-audit-system.ps1`)

---

## Report format (only this)

```markdown
## Fix
- **Item** — location — what's wrong and what to do

## Improve
- **Item** — location — suggestion
```

If none: **Nothing found.**

**Forbidden in reports:** P0/P1 labels, pass/fail banners, phase menus, “coverage gaps”, “worth adding to checklist”, or suggestions to expand audit scope instead of Fix/Improve on the project.

---

## After an audit

Say **“fix the audit items”** or **“tackle the improve list”** — that means audit **Fix/Improve** bullets only. To schedule product work, add or promote items in **`ROADMAP.md`** (work queue or backlog) — audits do not auto-append there.

Agent fixes audit items, re-runs step 1 **`run_audit.cmd`** if tests need refreshing (or semantic + **`finalize_audit.cmd`** if only the report changed), re-audits.

---

## Entry points

| Piece | Location |
|-------|----------|
| Run (step 1) | `run_audit.cmd` |
| Finalize (step 3) | `scripts\finalize_audit.cmd` |
| Protocol | `docs\AUDIT.md` |
| Rule | `.cursor\rules\audit.mdc` |
| Skill | `agent-code-audit` |

Maintenance: `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\AUDIT_SYSTEM.md`
