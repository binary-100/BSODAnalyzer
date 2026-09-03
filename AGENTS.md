# AGENTS.md

Instructions for AI coding agents working in **BSOD Analyzer**.

**Universal entry:** **`AI_INSTRUCTIONS.md`** (all AI tools). This file adds project specifics.

## Read first

**[`docs/PRODUCT_REFERENCE.md`](docs/PRODUCT_REFERENCE.md)** — what the app does, product goals, agent obligations (validate yourself; do not ask the user to do in-app work), and how to run live validation. **Update it when capabilities change.**

**[`docs/AGENT_READINESS.md`](docs/AGENT_READINESS.md)** — session-start self-audit, audit reconciliation, tiered validation, module navigation (~69k LOC), and **current build priority** (maintainability slicing before new ROADMAP work). **Substantial workstreams:** follow § Session-start self-audit (8 sections). **Update when priority or scale assumptions change.**

Also enforced by **`.cursor/rules/agent-readiness.mdc`** (always-on pointer — canonical text stays in the doc above).

**Next major upgrade (planning only until work queue):** [`docs/upgrade/README.md`](docs/upgrade/README.md) — one folder; gate: `.cursor/rules/design-tier-gate.mdc`.

**Handoffs (implement / confirm):** [`docs/handoffs/README.md`](docs/handoffs/README.md) — temporary only; **delete when Done** (record in WORK_QUEUE). Pack handoff convention: `%USERPROFILE%\.cursor\AgentStarterPack\pack\docs\AGENT_HANDOFFS.md` · BSOD override: `.cursor/rules/project-handoffs.mdc`.

## Cursor rules (Model A — factory)

This repo is the **dev factory**. Generic Agent Starter Pack rules load from **`%USERPROFILE%\.cursor\rules\`** (global install). **Project** [`.cursor/rules/`](.cursor/rules/) holds **BSOD-specific** rules only — do not re-copy generic `generic-*.mdc` here (avoids duplicate always-on context).

**After `Refresh-AgentContext.cmd`:** the pack sync may re-copy generic rules and recreate `docs/handoff_archive/` — **delete those again** (keep **11** project `.mdc` files; no `handoff_archive/`). Context files (`AGENT_SESSION_START.md`, `AGENT_REFRESH.md`, `AGENT_CONTEXT.json`) should be kept.

## Session start

When **`docs/AGENT_SESSION_START.md`** exists, read it on the **first turn** of a new session before substantial work. It reports stale vs fresh context and lists required absolute paths.

## Project

- **Name:** BSOD Analyzer v6
- **Version (canonical):** `bsod_analyzer.py` → `VERSION = "x.y.z"`
- **Test command:** `run_tests.bat` (auto-syncs version first)
- **CI build:** `build_ci.bat` with `BUILD_NOPAUSE=1`

## Version sync — already implemented here

**This repo is the reference implementation** for Agent Starter Pack 1.3.0+ (`docs/VERSION_SYNC.md` in the starter pack). You do **not** copy templates into this project — they already exist as production scripts.

| Piece | Location |
|-------|----------|
| Canonical version | `bsod_analyzer.py` → `VERSION` |
| Sync script | `scripts/apply_version.py` (`sync` + optional `PRESETS`) |
| Auto-sync before tests | `run_tests.bat` (first step) |
| Build sync | `build_and_deploy_v6.bat` after tests |
| Consistency test | `tests/test_version_consistency.py` |
| Cursor rule | `.cursor/rules/version-sync.mdc` |

**Agents:** bump `VERSION` in `bsod_analyzer.py` only — never hand-edit `VERSION.txt`. Run `py -3 scripts\apply_version.py sync` or `run_tests.bat`. Add a `PRESETS` entry when shipping with custom release-note text.

Docs/backlog: prefer linking to `VERSION.txt` over hard-coding version numbers in headers.

**Product & agent behavior:** [`docs/PRODUCT_REFERENCE.md`](docs/PRODUCT_REFERENCE.md) (keep current when shipping features).

## Coding efficiency

Speed and accuracy matter for **users**; **efficiency** matters for the codebase — less noise, fewer redundant hot-path calls, cleaner module boundaries. That helps maintainability and keeps the tool responsive on weaker PCs.

- Reuse existing helpers; do not duplicate catalog/analysis tiers.
- Do not add dead branches, unused settings, or “maybe later” code without a ROADMAP/work-queue item.
- Audits flag dead/redundant code under AUDIT §2b — fix or improve when found.
- **Facade / re-export work:** run **`scripts\verify_facade_gate.cmd`** (T3) before claiming done — [`docs/FACADE_ORCHESTRATION.md`](docs/FACADE_ORCHESTRATION.md).
- **Risk in plans or “done”:** mandatory table in [`docs/AGENT_READINESS.md`](docs/AGENT_READINESS.md) § Risk and validation reporting; verify with **`scripts\verify_agent_report.cmd --require …`** when claiming gates ran.

## Stale agent context

If an audit reports **Agent context stale / never refreshed / unreadable**, do not hand the user a command to type. **Offer to run `Refresh-AgentContext.cmd` for this project** and run it once they approve, then read the regenerated `docs/AGENT_REFRESH.md` in the same turn. Details in **`AI_INSTRUCTIONS.md`**.

## Agent runs commands (user verifies)

You run sync, verify, test, and fix commands; the user reviews output and may pivot. Do not offload executable work as "please run X." See **`AI_INSTRUCTIONS.md`** and **`docs/portable/GENERIC_RULES.md`** § agent-defaults-always.

## Before long shell commands

Use **agent-hygiene** MCP when available:

1. `agent_hygiene_full_check`
2. After force-kill: `cleanup_orphan_agent_processes` (`dry_run=True` first)

Without MCP: `%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\cleanup-orphan-processes.ps1`

## Audits

Ask for **an audit** or **check everything**. One audit = three steps (skill **`agent-code-audit`**):

1. **`run_audit.cmd`** — full tests (never `-SkipTests`); read **`docs/.audit_agent_manifest.json`**
2. Fill **`docs/.audit_semantic_report.json`**; **`scripts\verify_semantic_audit.cmd`**
3. **`scripts\finalize_audit.cmd`** — completion gate (skips tests when manifest proof valid)

Execute **all sections** in **`docs/AUDIT.md`**. Report only **Fix** and **Improve** — every gap is Fix (remove) or Improve (mitigate). **Audit Improve ≠ product backlog** ([`ROADMAP.md`](docs/ROADMAP.md)). Include efficiency / dead code (AUDIT §2b) and **doc duplication / drift** (§2c, §M; inventory [`DOC_MAP.md`](docs/DOC_MAP.md)).

- Product plan: `docs/ROADMAP.md` · status pointer: `docs/IMPROVEMENT_BACKLOG.md` (links only)
- Limitations (not bugs): `docs/KNOWN_LIMITATIONS.md`
- Old audits: `docs/audit_archive/` (ignore)

## Tests

- **Discovery is pytest** — a new `test_*` function runs with no `__main__` block. Dev deps: `requirements-dev.txt`.
- Standing gates: `tests/test_test_discovery.py` (all defined tests collected) · `tests/test_static_analysis.py` (pyflakes: undefined names, star-import resolution, shadowed dict keys). Rationale and history: [`docs/TEST_HARNESS_PLAN.md`](docs/TEST_HARNESS_PLAN.md).
- Build widgets through `offscreen_widget()` / `offscreen_main_window()` in `tests/gui_test_harness.py` — raw construction aborts teardown with `0xC0000409`.

## GUI tests

- Skill **agent-gui-test-hygiene**
- **Agent runs tests** — `run_tests.bat` or `py -3 tests\run_test_module.py tests\…`; never ask the user to run them or fix Qt env vars
- **`QT_QPA_PLATFORM=offscreen` is required but not sufficient** — bootstrap stack in [`docs/AGENT_READINESS.md`](docs/AGENT_READINESS.md) § Qt test bootstrap
- **Qt popup reported:** agent reads `qt_platform.log`, hygiene-check orphans, re-runs tests, fixes bypass — same session
- **Host:** user runs Cursor **as Administrator** — assume elevated agent shell for validation and tests

## Builds (agents)

```bat
set BUILD_NOPAUSE=1
call build_ci.bat
```

Output: `BSODAnalyzer_v6\BSODAnalyzer.exe`

## Portable-first product direction

**Canonical product:** Maintenance USB workflow (`install_mode: portable` = launcher layout). Durable data on the **target PC** at `%LOCALAPPDATA%\BSODAnalyzer\` — settings, catalog cache (`driver_catalog\<fingerprint>\`), default exports. The stick holds exe/runtime only.

**Full install mode** (`%LOCALAPPDATA%\BSODAnalyzer\`, hardware cache, driver index, remember-checks) remains in the codebase for compatibility — **do not remove it without an explicit user request**. Treat it as **legacy / deprecated for new investment**:

| Principle | Detail |
|-----------|--------|
| Primary user | Tech with USB stick; fresh device inventory each launch is **intentional** (current WMI/PnP snapshot). |
| Scan budget | Driver catalog ~5 min and firmware in the same ballpark — session persistence is no longer the main speed lever. After catalog changes, run `scripts/compare_catalog_scan_timings.py` (read-only) against `session_log.jsonl` for before/after p50. |
| Agent default | Implement, test, and optimize **portable first**. |
| Full-install work | Only when a feature **requires** installed layout or **measurably** cannot work portable — document why before building. |
| UX | No portable-hostile prompts (stale DB nag, install-mode choice on first launch); full-install via Settings only. |

We have **not** identified a feature that meets the “big unless” bar yet. Revisit only if something truly needs full install.

## Multi-step features

Follow starter pack **`pack/docs/PHASED_FEATURE_DESIGN.md`** (profile rule `generic-phased-feature-design.mdc`): one phase sequence; runtime order = build order; optional work nested under a phase or in a keyed appendix.

**Active plan:** [`docs/ROADMAP.md`](docs/ROADMAP.md) — work queue empty · **Approved intent:** three upgrade tracks · **Parked:** [`docs/upgrade/parked/PARKED.md`](docs/upgrade/parked/PARKED.md) · **Exploration:** Action Plan checklist (Tier 1).

**Next upgrade (Tier 3, not buildable):** `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\README.md` — point build agents here. Snapshot: [`docs/upgrade/DESIGN_TIERS.md`](docs/upgrade/DESIGN_TIERS.md).

**Current agent focus:** Promote from **Approved intent** to work queue when user directs — maintainability milestone ☑ (**6.5.0**). GUI on `gui_app_context` → `core`.

**Completed plan:** [`docs/DRIVER_VERIFICATION_PLAN.md`](docs/DRIVER_VERIFICATION_PLAN.md) (crash-linked verification).

## Starter pack (global — not copied into this repo)

Install once per machine: `C:\Users\binar\OneDrive\Desktop\AgentStarterPack\Install-AgentStarterPack.cmd`  
Onboarding: `C:\Users\binar\.cursor\AgentStarterPack\pack\docs\START_HERE.md`  
**This factory:** generic rules in **`%USERPROFILE%\.cursor\rules\`** only — see **Cursor rules (Model A)** above. Refresh audit/context: **`Refresh-AgentContext.cmd`** at repo root.  
Pack maintenance (other repos): `C:\Users\binar\.cursor\AgentStarterPack\pack\docs\PACK_MAINTENANCE.md`  
Verify: `C:\Users\binar\.cursor\AgentStarterPack\pack\scripts\doctor.ps1`

**"For new Python projects"** in starter pack docs means **other repos** you bootstrap later — not this one.
