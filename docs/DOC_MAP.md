# Documentation map (canonical sources)

**Purpose:** One place to learn **which doc owns what** — so audits and agents do not duplicate content or “fix” the wrong file.  
**Audit:** Section **M** in [`AUDIT.md`](AUDIT.md) — read **every** active doc listed here each full audit; report duplication/stale content as **Improve** (awareness even when no edit is safe yet).

Last updated: **2026-09-01** · version: see [`VERSION.txt`](../VERSION.txt) · flat repo layout (2026-08-30)

---

## Rule: canonical vs pointer

| Kind | Rule | Examples |
|------|------|----------|
| **Canonical** | Owns the truth; update here when behavior changes | `PRODUCT_REFERENCE.md`, `ROADMAP.md`, `AUDIT.md` |
| **Pointer / hub** | Links only; **no** duplicated tables, phase lists, or backlog rows | `IMPROVEMENT_BACKLOG.md`, root `EVALUATION.md` |
| **Thin rule (`.mdc`)** | Triggers + 5–15 lines; **must link** to canonical doc | `product-reference.mdc`, `agent-readiness.mdc`, `qt-test-bootstrap.mdc` |
| **Archive** | Historical; do not treat as current policy | `docs/audit_archive/`, `docs/design_archive/`, root stubs → archive |

**Audit Improve** for docs = stale facts, duplicated sections, contradictory commands, or new content added to a pointer instead of the canonical owner.

---

## Active documentation inventory (read on full audit)

### Repo root

| File | Role |
|------|------|
| [`README.md`](../../README.md) | Quick start, layout pointer |
| [`PROJECT_LAYOUT.md`](../../PROJECT_LAYOUT.md) | Tree contract, stable builds |
| [`ONEDRIVE_CLEANUP.md`](../../ONEDRIVE_CLEANUP.md) | OneDrive / Phase 8 cleanup status |
| [`BUILD_NOTES.md`](../../BUILD_NOTES.md) | Build notes (user-facing) |
| [`CONSOLIDATION.md`](../../CONSOLIDATION.md) | Historical stub — pointer to `PROJECT_LAYOUT.md` |
| [`EVALUATION.md`](../../EVALUATION.md) | Archive stub → `docs/audit_archive/EVALUATION.md` |
| [`PERFORMANCE_PLAN.md`](../../PERFORMANCE_PLAN.md) | Archive stub → `docs/audit_archive/PERFORMANCE_PLAN.md` |

### Agent & product (project root)

| File | Role |
|------|------|
| [`AGENTS.md`](../AGENTS.md) | Agent commands, version sync, audit entry, portable-first summary |
| [`docs/PRODUCT_REFERENCE.md`](PRODUCT_REFERENCE.md) | **Product truth** — capabilities, agent §2 obligations, pipeline |
| [`docs/AGENT_READINESS.md`](AGENT_READINESS.md) | Session self-audit, tiers, priorities, Qt bootstrap, **task → module navigation** |
| [`docs/ROADMAP.md`](ROADMAP.md) | **Product plan** — work queue, Approved intent, phase history |
| **Design tiers + upgrade program** | [`docs/upgrade/README.md`](upgrade/README.md) — hub |
| [`docs/upgrade/DESIGN_TIERS.md`](upgrade/DESIGN_TIERS.md) | Tier workflow + current state |
| [`docs/upgrade/parked/PARKED.md`](upgrade/parked/PARKED.md) | Parked ideas (hidden — not agent default) |
| [`docs/upgrade/BUILD_HANDOFF.md`](upgrade/BUILD_HANDOFF.md) | Implementation agent checklist |
| [`docs/upgrade/inbox/`](upgrade/inbox/README.md) | Tier 1 Exploration |
| [`docs/upgrade/plans/`](upgrade/plans/README.md) | Tier 3 Design PLANs |
| [`docs/handoffs/HANDOFF_BSOD_STATUS.md`](handoffs/HANDOFF_BSOD_STATUS.md) | Agent status handoff — product + process snapshot |
| [`docs/WORK_QUEUE.md`](WORK_QUEUE.md) | **Maintainer radar** — WQ ids, Done/Parked/Inbox (not product ROADMAP) |
| [`docs/WORK_COMPLETION.md`](WORK_COMPLETION.md) | Work-completion checklist (pack) |
| [`docs/REPO_FLATTEN_PLAN.md`](REPO_FLATTEN_PLAN.md) | Flat layout record (2026-08-30) |
| [`docs/handoffs/README.md`](handoffs/README.md) | Handoff discipline + active/completed registry |
| [`docs/IMPROVEMENT_BACKLOG.md`](IMPROVEMENT_BACKLOG.md) | **Pointer only** — links to ROADMAP / readiness |
| [`docs/KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | Accepted tradeoffs (not bugs) |
| [`docs/AUDIT.md`](AUDIT.md) | Full audit A–N, **audit domain map**, §2b/§2c |
| [`docs/CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md) | Module split status & rules |
| [`docs/TEST_HARNESS_PLAN.md`](TEST_HARNESS_PLAN.md) | **Suite trust** — pytest discovery, static gates, the bugs a green suite was hiding |
| [`docs/AGENT_HANDOFF_20260821.md`](AGENT_HANDOFF_20260821.md) | **Latest session handoff** — start here; supersedes the 2026-08-20 handoff for session state |
| [`docs/FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md) | Facade T3 gate, prune/decouple options |
| [`docs/DRIVER_VERIFICATION_PLAN.md`](DRIVER_VERIFICATION_PLAN.md) | Completed verification plan |
| [`docs/DEPENDENCIES_CHEATSHEET.txt`](DEPENDENCIES_CHEATSHEET.txt) | **Dependency matrix** — CDB/WinDbg, PS7, winget, MSCatalog, first-launch flow |
| [`scripts/README.md`](../scripts/README.md) | **Scripts index** — extract/diag/live utilities; update when adding `scripts/*.py` |
| [`VERSIONING.md`](../VERSIONING.md) | v5 vs v6 product lines (link `VERSION.txt` for current number) |

### Design & audit archive (read for context — not build order)

| File | Role |
|------|------|
| [`docs/design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md`](design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md) | **Phase 8 RFC** — opt-in chip-level / third-party drivers; **do not implement B–F** without user-approved RFC. Canonical link: `PRODUCT_REFERENCE.md` §10, `ROADMAP.md` § Backlog |
| [`docs/audit_archive/README.md`](audit_archive/README.md) | Old audit reports — historical only |
| [`docs/audit_archive/*`](audit_archive/) | Prior evaluations, performance plans, code audits |

### Cursor rules — agent surface (`.cursor/rules/` + repo root)

Read on audit for **stale commands** (wrong build bats, obsolete paths) and **bloat** (paragraphs duplicated from canonical markdown).

| File | Canonical doc | Notes |
|------|----------------|-------|
| `agent-readiness.mdc` | `AGENT_READINESS.md` | alwaysApply |
| `audit.mdc` | `AUDIT.md` | alwaysApply |
| `product-reference.mdc` (repo [`.cursor/rules/`](../../.cursor/rules/product-reference.mdc)) | `PRODUCT_REFERENCE.md` | alwaysApply at repo root |
| `qt-test-bootstrap.mdc` | `AGENT_READINESS.md` § Qt | |
| `gui-testing-roadmap.mdc` | `AGENTS.md` + harness docs | |
| `version-sync.mdc` | `AGENTS.md` § Version sync | |
| `terminal-and-build-hygiene.mdc` | generic rule + `AGENTS.md` paths | |
| `recompile-after-changes.mdc` | `AGENTS.md` + `AGENT_READINESS.md` § Tiered validation | **Not** “build every edit” |
| `audit-protocol.mdc` | `audit.mdc` + starter pack `AGENT_WORKFLOW.md` | Cross-project entry; **pointer only** |
| `loop-back-protocol.mdc` | starter pack `AGENT_WORKFLOW.md` | |
| `agent-defaults-always.mdc` | starter pack defaults + project paths | |
| `generic-phased-feature-design.mdc` | starter pack `PHASED_FEATURE_DESIGN.md` | |
| `generic-version-sync.mdc` | starter pack + `version-sync.mdc` | |
| `design-tier-gate.mdc` | `docs/upgrade/README.md` | alwaysApply — no implement from plans / Approved intent / Parked without approval |
| `upgrade-planning-only.mdc` | `docs/upgrade/PLANNING_AGENT.md` | opt-in planning chats |
| `full-paths-in-chat.mdc` | starter pack `full-paths-in-chat.mdc` | alwaysApply — full absolute paths in chat |
| `new-project-bootstrap.mdc` | starter pack (other repos) | |

### Project-local skills (`.cursor/skills/`)

Copies of hygiene/audit skills for this repo. **Canonical** copies live in `%USERPROFILE%\.cursor\skills\` — audit **Improve** if project copy diverges.

| Skill | Purpose |
|-------|---------|
| `agent-gui-test-hygiene` | Offscreen Qt hangs, QMessageBox teardown |
| `agent-terminal-hygiene` | Stale terminals, build pauses, orphans |
| `agent-code-audit` | (if present) Should match user-level skill + `AUDIT.md` |

---

## Code & script awareness (not markdown — read on audit / before slicing)

| Artifact | Role |
|----------|------|
| **`AUDIT.md` domain map** | Every production `app\*.py` → section A–N; orphan modules → Fix |
| **`AGENT_READINESS.md` § Module navigation** | Task-oriented “start here” for agents (see [code map policy](#code-map-policy-item-3)) |
| **`scripts/extract_*.py`** | Planned slice boundaries — read **before** re-planning a `driver_catalog.py` / GUI extract |
| **`tests/test_improve_coverage.py`** | Implicit “must import” module contract |
| **`tests/test_catalog_audit_coverage.py`** | Catalog invariants |
| **`tests/test_test_discovery.py`** | Every defined test is collected — guards the pytest discovery fix |
| **`tests/test_static_analysis.py`** + `tests/static_analysis.py` | pyflakes gate: undefined names, star-import resolution, shadowed dict keys |
| **`tests/gui_test_harness.py`** | `offscreen_widget` / `offscreen_main_window` / `report_contains` — use instead of raw widget construction |
| **`session_log.jsonl` + `compare_catalog_scan_timings.py`** | Perf baselines after catalog changes (T4) |

**Post-slice checklist** (when adding a production module): domain map → `CATALOG_MODULE_SPLIT.md` → `scripts/README.md` → navigation row in `AGENT_READINESS.md` → `DOC_MAP.md` if new doc.

---

## Known overlap zones (audit for drift)

Report as **Improve** when the same facts appear in multiple places **without** “see X” pointer-only style:

| Topic | Canonical owner | Common duplicates |
|-------|-----------------|-------------------|
| Agent must/must-not | `PRODUCT_REFERENCE.md` §2 | `product-reference.mdc`, `AGENTS.md`, `AGENT_READINESS.md` |
| Audit 3-step flow | `AUDIT.md` + `audit.mdc` | `audit-protocol.mdc` (pointer), `AGENTS.md`, skill |
| Improve vs backlog | `ROADMAP.md` § Planning vocabulary | `AUDIT.md`, `IMPROVEMENT_BACKLOG.md` |
| Qt test bootstrap | `AGENT_READINESS.md` § Qt | `AGENTS.md`, `qt-test-bootstrap.mdc` |
| Portable-first | `AGENTS.md` + `KNOWN_LIMITATIONS.md` | `PRODUCT_REFERENCE.md`, backlog pointer |
| Maintainability priority | `AGENT_READINESS.md` § Current build priority | `IMPROVEMENT_BACKLOG.md` § Current focus, `CATALOG_MODULE_SPLIT.md` |
| Version number | `VERSION.txt` / `bsod_analyzer.VERSION` | Doc headers, `VERSIONING.md` body |
| **Build / recompile policy** | `AGENTS.md` + `AGENT_READINESS.md` § Tiered validation | `recompile-after-changes.mdc`, `terminal-and-build-hygiene.mdc`, `bsod_analyzer.py` docstring |
| **Code map / where to start** | See [code map policy](#code-map-policy-item-3) | `PRODUCT_REFERENCE.md` §11, `AGENT_READINESS.md` § Module navigation, `AUDIT.md` domain map |
| Phase 8 chip-level design | `ROADMAP.md` § Backlog + archive stub in `PRODUCT_REFERENCE.md` §10 | Full `design_archive/CHIP_LEVEL_ADVISORY_DESIGN.md` cited as current policy |

**Not every overlap is wrong** — thin rules and hubs are intentional. **Improve** when content diverges or a pointer grows a second copy of tables/lists.

---

## Code map policy (item 3)

Three artifacts touch “where is the code?” — **different jobs, one canonical each:**

| Job | Canonical | Others should |
|-----|-----------|----------------|
| **Agent navigation** (“I need to fix catalog HTTP”) | `AGENT_READINESS.md` § Module navigation | Link only |
| **Audit completeness** (every module reviewed) | `AUDIT.md` domain map | Link only |
| **Product surface** (what subsystems exist for users/agents) | `PRODUCT_REFERENCE.md` §11 — **short pointer table** | Link to readiness + domain map; no third full module list |

Planned cleanup (item 3): ☑ **`PRODUCT_REFERENCE.md` §11** slimmed to links; **§ Module navigation** in this file is the agent canonical map.

---

## Awareness without change (audit policy)

Full audit **requires reading** all inventory docs, **agent surface** (`.mdc` + local skills), and **all** domain-map production modules (code). Findings may be **Improve only**:

- Document stale command or version — note even if fixing risks churn
- Duplicate backlog row — note even if ROADMAP is canonical
- Efficiency opportunity in docs (merge pointers) — note even if deferred
- Extract script exists for a slice you were about to re-plan — note in Improve

Do **not** skip reporting because “we might not fix it this session.” Do **not** auto-fix doc drift during a product code audit unless it is **Fix** (wrong instructions that cause test/build failure) or the user asked for doc cleanup.

---

## Related

- [`AUDIT.md`](AUDIT.md) §2c, §M  
- [`AGENT_READINESS.md`](AGENT_READINESS.md) § Audit findings reconciliation  
