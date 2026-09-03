# BSOD Analyzer — Agent readiness (session start)

**Use this at the start of a substantial workstream** — after reading [`PRODUCT_REFERENCE.md`](PRODUCT_REFERENCE.md) and [`../AGENTS.md`](../AGENTS.md).

| | |
|---|---|
| **Canonical version** | see [`VERSION.txt`](../VERSION.txt) |
| **Last updated** | 2026-09-01 |
| **Scale (approx.)** | ~69k LOC production Python (root `*.py`) · **138** modules · **144** test files · see [`VERSION.txt`](../VERSION.txt) |
| **Current build priority** | Promote from **Approved intent** when user directs — maintainability milestone **6.5.0** ☑; see [`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md) |
| **Host environment** | User runs **Cursor as Administrator** — agents assume an **elevated agent shell** for tests, live validation, and hygiene (do not ask the user to rerun as admin) |
| **Product backlog** | [`ROADMAP.md`](ROADMAP.md) — work queue empty; **do not start new product features** until cleanup/slicing is where we want it |
| **Split playbook** | [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) |
| **Full audit** | [`AUDIT.md`](AUDIT.md) + `AGENTS.md` § Audits |

---

## Priority order (non-negotiable)

1. **User-facing accuracy** — crash attribution, repair narrative, catalog offer correctness.
2. **User-facing speed** — catalog scan ~5 min p50; do not regress without `scripts/compare_catalog_scan_timings.py`.
3. **Codebase efficiency** — module boundaries, dead code, test hygiene — **supports** 1 and 2; never trades them away.

When tradeoffs conflict, state them explicitly. Do not assume “smaller diff” or “fewer files” wins.

---

## Current build priority

**Owner decision (2026-08-20):** maintainability + facade work **complete** — shipped as **6.5.0**. Next: ROADMAP when user promotes backlog items.

| Order | Target | ~LOC | Playbook |
|-------|--------|-----:|----------|
| **1** | `driver_catalog.py` | ~665 (re-exports + OEM cache) | ☑ **Complete** — [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) |
| **2** | `bsod_crash_report.py` + `crash_report_*` | ~1,780 + ~3,540 across 6 modules | ☑ **Complete** (6.4.110) |
| **3** | `bsod_analyzer.py` orchestration | ~394 shell + gather/hardware slices | ☑ **Complete** (6.4.111) |
| **4** | Facade prune / decouple (optional) | 124 exports · 0 prune backlog | ☑ **Complete** (6.4.112) — [`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md) |

**Not in scope until cleanup is done:** new ROADMAP work-queue items, Phase 8, or features not already in [`ROADMAP.md`](ROADMAP.md) backlog.

After each slice: **`AUDIT.md` domain map** → **`CATALOG_MODULE_SPLIT.md`** → **`scripts/README.md`** (if new utility script) → **§ Module navigation** below → **`DOC_MAP.md`** (if new doc). See [`DOC_MAP.md`](DOC_MAP.md) § Post-slice checklist.

---

## Session-start self-audit (mandatory for large tasks)

Inspect the repo before assuming something is missing. Do not ask the user for information you can discover (commands, layout, test paths, audit artifacts).

When starting a substantial session — or when the user asks for readiness — respond with these sections:

1. **What you already know** — facts with evidence (files, test results, LOC, version).
2. **What seems well established already** — docs, rules, automation that already match the task.
3. **Audit findings reconciliation** — reconcile last audit; do not restate blindly (see [§ Reconciliation](#audit-findings-reconciliation)).
4. **What is still missing, weak, or ambiguous** — highest-leverage gaps only.
5. **What you are currently inferring instead of knowing** — label confidence (high / medium / low).
6. **What you need from the user next** — minimum context only; say “nothing needed” when docs suffice.
7. **Readiness rating** — overall and per task type.
8. **Safe next actions** — what to do now vs what needs supervision.

Keep it concrete. Separate facts from assumptions. No generic best-practices lecture.

---

## Audit findings reconciliation

The audit tool (`run_audit.cmd`, `docs/.audit_semantic_report.json`, `docs/.audit_agent_manifest.json`) reports **Fix** and **Improve**. Treat labels as:

| Label | Meaning |
|-------|---------|
| **Fix** | Likely requires correction — correctness, safety, reliability, compatibility, validation, or other functional outcome. |
| **Improve** | Quality, maintainability, clarity, consistency, structure, or workflow — not always mandatory before shipping the current task. |

**Improve ≠ ROADMAP backlog.** Audit Improve is ephemeral; product backlog lives in [`ROADMAP.md`](ROADMAP.md).

The audit tool is **important signal, not ground truth.** Reconcile each significant finding:

| Classification | When to use |
|----------------|-------------|
| **Confirmed fix** | Verified in code/tests; still open or just fixed. |
| **Confirmed improve** | Still valid; worth scheduling in maintainability work. |
| **Likely duplicate** | Already tracked elsewhere or mitigated by tests. |
| **Likely outdated** | Refactor shipped since report (e.g. LOC-based mixin warnings after 6.4.80 splits). |
| **Needs human judgment** | Real tradeoff; user must pick priority. |
| **Low-confidence signal** | Heuristic only (e.g. “no direct test reference” while `test_improve_coverage.py` imports the module). |

For each important finding, note:

- **Agree / partially agree / disagree / need more evidence**
- **Scope:** local · cross-file · architectural
- **Confidence:** high · medium · low

After **large refactors or module splits**, refresh or downgrade stale Improve lines in the semantic report on the next audit — do not chase fixed LOC counts.

### Documentation awareness (full audits)

**“Check everything” includes all active docs**, not only code and machine stale-pattern scans. Canonical inventory: [`DOC_MAP.md`](DOC_MAP.md).

| Principle | Detail |
|-----------|--------|
| **Read before duplicating** | If a plan, backlog row, or obligation already lives in a canonical doc, link — do not copy into rules, pointers, or new markdown. |
| **Improve without edit** | Stale version, duplicated audit steps, or overlapping agent obligations → report **Improve** even when fixing would churn docs or is deferred. |
| **Fix when harmful** | Wrong build/test command or contradictory product behavior in docs → **Fix** when it misleads agents or breaks workflow. |
| **Code same standard** | Domain-map modules: read for awareness; efficiency opportunities may stay **Improve** if change risks speed or accuracy. |

Reconcile doc findings like code findings (duplicate / outdated / confirmed improve) in § Audit findings reconciliation above.

---

## Tiered validation

Match validation depth to change type. Full suite is **144 test files / 1,124 tests, ~4–5 minutes**; use tiers to preserve agent speed without skipping gates before “done.”

**The suite discovers tests via pytest.** Adding a `test_*` function is enough — a file needs no `if __name__ == "__main__":` block, and a partial block no longer hides the rest of the file. Two permanent gates enforce this: `tests/test_test_discovery.py` (everything defined is collected) and `tests/test_static_analysis.py` (pyflakes — undefined names, star-import resolution, shadowed dict keys). Both run inside `run_tests.bat`; see [`TEST_HARNESS_PLAN.md`](TEST_HARNESS_PLAN.md).

| Tier | When | Command |
|------|------|---------|
| **T0 — Targeted** | Single-module logic, test-only edits, mock fixes | `py -3 tests\run_test_module.py tests\test_<area>.py` (never bare `py -3 tests\...py` for GUI-touching tests) |
| **T1 — Domain batch** | One subsystem (catalog, GUI, crash report) | All related `tests/test_*.py` for that domain |
| **T2 — Full suite** | Before claiming done, after any slice/re-export, before build | `run_tests.bat` from the project root |
| **T3 — Facade / orchestration** | Touch `bsod_analyzer.py` re-exports, prune, orchestration peel, or claim facade “checked” | `scripts\verify_facade_gate.cmd` → exit 0 · see [`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md) |
| **T4 — Live analysis** | Analysis pipeline, attribution, minidump, repair narrative | Admin: `py -3 scripts\live_validate_analysis.py` → `live_validation_output.json` |
| **T5 — Perf spot-check** | Catalog scan / warm-path changes | `py -3 scripts\compare_catalog_scan_timings.py` (read-only) |
| **T6 — Full audit** | User asks for audit / check everything | `run_audit.cmd` → semantic report → `finalize_audit.cmd` |

**Minimum before “done” on maintainability slices:** T0 on touched tests → **T2 full suite** (required by [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md)).

**Minimum before “done” on facade / re-export work:** **T3 facade gate** → **T2** → **T4** when analysis or GUI workers touched ([`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md)).

**Minimum before “done” on analysis behavior:** T2 + **T4** when admin is available.

---

## Risk and validation reporting (mandatory)

**Problem this closes:** agents name a risk or gap (“low risk *if*…”, “could break unless…”) without saying whether they **run the mitigation**, so the user cannot tell if the option still carries that risk.

**Canonical rule:** whenever you mention a **risk, gap, or conditional mitigation** in a plan, option list, or “done” summary, include the table below in the same response. No implied homework for the user (see [`PRODUCT_REFERENCE.md`](PRODUCT_REFERENCE.md) §2).

| Column | Required content |
|--------|------------------|
| **Risk** | What could go wrong |
| **Mitigation** | Check, script, or fix that addresses it |
| **Agent runs it?** | **Yes** · **No** · **Blocked** (reason) — never omit |
| **Evidence** | Command run + exit code / counts (same session) |
| **Remaining risk** | **None** if Yes + pass; else what is still open |

### Language rules

| Forbidden | Use instead |
|-----------|-------------|
| “Low risk if gate before/after” (no Yes/No) | “**Yes** — I will run / ran `verify_facade_gate.cmd`; before exit 0, after exit 0 → **remaining: none**” |
| “Checked everything” without gates | Name tiers run (T2/T3/T4/T6) + exit codes |
| “Gaps remain” / “you could run…” for agent-owned validation | Run it; put result in **Evidence** |
| “Should be fine” | Evidence row or **Remaining risk** spelled out |

If **Agent runs it? = Yes** and evidence shows pass, **Remaining risk** must be **None** for that item — not hedged again with “if”.

If **Agent runs it? = No** or **Blocked**, say what is left so the user can choose to accept, redirect, or wait.

### What enforces this (machine + process)

Not honor system only — layered as follows:

| Layer | Enforces | Agent obligation |
|-------|----------|-------------------|
| **Scripts (exit 0)** | `verify_facade_gate.cmd` (T3), `run_tests.bat` (T2), `live_validate_analysis.py` (T4), `run_audit.cmd` + `finalize_audit.cmd` (T6) | Run applicable tiers **before claiming done**; report exit codes in **Evidence** |
| **Always-on rules** | `.cursor/rules/agent-readiness.mdc`, `loop-back-protocol.mdc`, `product-reference.mdc` | Read this section on substantial work; loop back on repeat asks |
| **Repeat-user pushback** | [`loop-back-protocol.mdc`](../.cursor/rules/loop-back-protocol.mdc) | Re-read workstream from start; diff claim vs repo; **different method**, not same partial scan |
| **User review** | This table in chat | User can reject plans/options missing **Agent runs it?** |
| **Machine proof file** | `docs/.agent_gate_proof.json` + `scripts/verify_agent_report.cmd` | Gates that ran successfully stamp proof; verifier fails if agent claims checks without fresh proof |

### Machine proof (not honor system)

Successful gate runs **record proof** to `docs/.agent_gate_proof.json` (gitignored):

| Gate ID | Recorded when | Verifier |
|---------|---------------|----------|
| `facade` | `scripts/verify_facade_gate.cmd` exit 0 | `--require facade` |
| `t2` | `run_tests.bat` all pass | `--require t2` |
| `t4` | `scripts/live_validate_analysis.py` OK | `--require t4` |

**Verify proof (agent or user):**

```bat
cd app
scripts\verify_agent_report.cmd --require facade,t2,t4
```

Checks: gate recorded · exit 0 · timestamp within `--max-age-minutes` (default 720) · `git HEAD` matches proof (unless `--allow-stale-git`).

**Evidence column in the risk table** should cite proof verification when claiming gates ran, e.g. `verify_agent_report.cmd --require facade,t2 exit 0`.

### Example (facade / re-export work)

| Risk | Mitigation | Agent runs it? | Evidence | Remaining risk |
|------|------------|----------------|----------|----------------|
| `_ba` / `core.*` break after prune | T3 facade gate + runtime probe | **Yes** | `verify_facade_gate.cmd` exit 0 before/after | **None** |
| Analysis regression | T2 + T4 | **Yes** | `run_tests.bat` 123/123; `live_validate_analysis.py` OK | **None** |
| GUI mixin `core.*` missed by import grep | Gate scans all `core.*` refs | **Yes** | audit report: 0 broken symbols | **None** |

---

## Module navigation (~69k LOC)

**Canonical agent code map** — audit completeness lives in [`AUDIT.md`](AUDIT.md) § Domain map; product §11 is pointer-only. Before re-planning a slice, read [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) and [`scripts/README.md`](../scripts/README.md).

| Task | Start modules | Key tests |
|------|---------------|-----------|
| **Run Analysis / attribution** | `bsod_analyzer.py` → `analyzer_gather.py`, `analyzer_hardware.py`, `bsod_events.py`, `bsod_minidump.py`, `bsod_crash_report.py`, `driver_verification.py` | `test_analysis_correctness_batch2.py`, `test_crash_confidence.py`, `test_live_validation_fixes.py`, `test_batch1_v529.py`, `test_driver_only_workflow.py` |
| **Repair narrative / timeline** | `bsod_crash_report.py`, `crash_report_narrative.py`, `crash_report_timeline.py`, `crash_report_culprit.py`, `crash_report_fix_plan.py`, `crash_report_format.py`, `crash_report_events.py` | `test_crash_repair_narrative.py`, `test_incident_timeline.py`, `test_culprit_resolution_s10.py`, `test_crash_confidence.py` |
| **Catalog orchestration & shared slices** | `driver_catalog.py` · `catalog_device_comparison.py` · `catalog_multi_device.py` · `catalog_*_fetch.py` · … | `test_driver_scan_scope.py`, `test_driver_catalog_quality.py`, `test_extended_vendor_scraper.py` |
| **Vendor scrape / extract** | `vendor_fetch.py`, `vendor_extractors.py`, `vendor_extractor_repair.py` | `test_vendor_source_hardening.py`, `test_extractor_parity.py`, `test_extended_vendor_scraper.py` |
| **OEM / MSCatalog / PowerShell** | `catalog_oem_live.py`, `catalog_mscatalog_session.py`, `catalog_oem_filters.py`, `catalog_ps_module.py`, `catalog_ps_batch.py` | `test_oem_depth_batch4.py`, `test_batched_online_store.py` |
| **GUI shell / tabs** | `bsod_gui_qt.py`, `gui_app_context.py`, `gui_mixin_shell.py`, `gui_mixin_*` | `test_gui_phase2_offscreen.py`, `test_improve_coverage.py` |
| **Catalog tab workflow** | `gui_mixin_catalog_scan.py`, `gui_mixin_catalog_packages.py`, `gui_mixin_catalog_install.py`, `gui_mixin_catalog_export.py` | `test_driver_catalog_gui_stable.py`, `test_catalog_export.py` |
| **Drivers tab workflow** | `gui_mixin_drivers.py`, `gui_mixin_drivers_workflow.py`, `gui_mixin_drivers_inventory.py`, `gui_mixin_drivers_table.py` | `test_gui_phase3_widgets.py`, `test_driver_catalog_gui_stable.py` |
| **Firmware tab** | `gui_mixin_firmware*.py`, `firmware_catalog.py` | `test_firmware_catalog_parity.py`, `test_vendor_firmware_fetch.py` |
| **Portable / settings** | `app_settings.py`, `catalog_cache.py`, `bsod_gui_preferences.py` | `test_data_dir_settings.py`, `test_portable_build_smoke.py` |
| **Session / logs** | `session_log.py`, `log_cleanup.py`, `maintenance_log.py` | `test_session_log.py`, `test_improve_coverage.py` |

**Largest files (navigation hotspots):** `bsod_crash_report.py`, `bsod_hardware_wmi.py`, `catalog_oem_live.py`, `firmware_catalog.py`, `driver_catalog.py` (mostly re-exports).

---

## Test mock conventions (catalog / vendor)

Production HTTP for vendor paths uses **robust helpers**, not bare `_http_get`:

| Helper | Typical use |
|--------|-------------|
| `_vendor_http_get_robust` | Marvell, Killer, Realtek, generic vendor pages |
| `_amd_http_get_robust` | AMD download center / product pages |

When writing or fixing tests, **patch the helper the production path actually calls**. Patching `driver_catalog._http_get` is legacy and will fail after refactors (see `test_vendor_source_hardening.py` for the current pattern).

After HTTP-layer moves, grep tests for `_http_get` and update mocks.

---

## Qt test bootstrap (prevent platform plugin popups)

Setting **`QT_QPA_PLATFORM=offscreen` alone is not enough** — Qt also needs **`QT_PLUGIN_PATH`** pointing at PySide6’s `plugins` folder. Without that, Windows shows a native **“no Qt platform plugin could be initialized”** dialog (often twice).

| Layer | What it does |
|-------|----------------|
| **`run_tests.bat`** | Sets `PYTHONSTARTUP=tests\_qt_startup.py` + runs each file via `tests/run_test_module.py`; `:run_one` compares `%ERRORLEVEL%` to `0` so a **negative** crash code cannot report `OK` |
| **`tests/_qt_startup.py`** | Installs import guard + plugin paths before any test code runs |
| **`tests/run_test_module.py`** | Same guard for single-file runs (agents should use this); delegates collection to `pytest.main()`, `--legacy` for the old `runpy` path |
| **`conftest.py`** · **`pytest.ini`** | Plugin bootstrap before PySide6 under bare `pytest`; one process per file stays the rule (tests share module-level caches) |
| **`gui_qt_bootstrap.py`** | `register_qt_plugins_for_import()`, `install_pyside6_import_guard()` |
| **`gui_app_context.py`** | Registers plugins before PySide6 (all mixin imports) |

**Widget lifetime is part of the bootstrap.** A parentless widget, or a `QPixmap`/`QIcon`
built with no `QApplication`, is torn down during interpreter shutdown and aborts the
process with `0xC0000409`. Use **`offscreen_widget()`** / **`offscreen_main_window()`** from
[`tests/gui_test_harness.py`](../tests/gui_test_harness.py) rather than constructing
widgets directly — see [`TEST_HARNESS_PLAN.md`](TEST_HARNESS_PLAN.md) § Qt crashes.

**Agents MUST (never offload to the user):**

```bat
cd app
run_tests.bat
```

Or targeted: `py -3 tests\run_test_module.py tests\test_<area>.py` with `PYTHONPATH=app`.

**Do not** run bare `py -3 tests\test_*.py` (missing plugin bootstrap → native Qt popup on Windows).

**If the user reports a Qt platform plugin popup:** the **agent** (same session) must:

1. Read `%TEMP%\BSODAnalyzer\qt_platform.log` (`gui_qt_bootstrap.read_qt_platform_log()`)
2. Run `agent_hygiene_full_check` and clean orphan `python.exe` / `py.exe` from hung test runs (`dry_run` first)
3. Re-run affected tests via `run_test_module.py` or full `run_tests.bat`
4. Fix code/docs if bootstrap was bypassed — do **not** ask the user to run tests, kill processes, or edit env vars

---

## What agents can do safely vs with supervision

### Usually safe (standard tiers)

- One-slice module extractions per `CATALOG_MODULE_SPLIT.md`
- Test and mock fixes; `test_improve_coverage.py` extensions for new modules
- Doc updates; version bump + `apply_version.py sync`
- Bug fixes in modules with existing regression tests (T0 → T2)

### Needs tighter supervision

- Edits inside `driver_catalog.py` offer pipeline or vendor tier ordering
- Vendor extractor rules / live scrape behavior
- Crash confidence ladder, minidump↔incident matching, repair narrative wording
- GUI threading, worker lifecycle, scan mutual exclusion
- Anything that adds install paths or third-party sources (Phase 8 bar)

---

## Readiness checklist (quick)

Before a large change, confirm:

- [ ] Read `PRODUCT_REFERENCE.md` §2 (agent obligations)
- [ ] Know current priority (this doc § Current build priority)
- [ ] Identified entry modules (navigation table above)
- [ ] Picked validation tier (T0–T2 minimum; **T3** if facade/orchestration)
- [ ] If facade work: `scripts\verify_facade_gate.cmd` exit 0 ([`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md))
- [ ] If naming risks in plan or “done”: filled **§ Risk and validation reporting** table (Agent runs it? + Evidence)
- [ ] If claiming gates ran: `scripts\verify_agent_report.cmd --require …` exit 0 matches Evidence
- [ ] If using last audit: reconciled stale Improve items
- [ ] If touching vendor HTTP: mock robust helpers, not `_http_get`

---

## Related docs

| Doc | Role |
|-----|------|
| [`../AGENTS.md`](../AGENTS.md) | Commands, audits, portable-first, version sync |
| [`PRODUCT_REFERENCE.md`](PRODUCT_REFERENCE.md) | Product behavior + agent must/must-not |
| [`ROADMAP.md`](ROADMAP.md) | Product phases and backlog (paused for new work until cleanup done) |
| [`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md) | Facade gate (T3), prune/decouple options |
| [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) | Split rules and completed slices |
| [`AUDIT.md`](AUDIT.md) | Full audit A–N + domain map |
| [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | Accepted tradeoffs (not bugs) |
