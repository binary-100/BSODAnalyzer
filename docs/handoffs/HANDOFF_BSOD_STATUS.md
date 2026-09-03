# Handoff — BSOD Analyzer status (2026-09-02)

## Handoff registry

| Field | Value |
|-------|-------|
| **handoff_id** | HANDOFF_BSOD_STATUS |
| **kind** | orientation |
| **status** | active |
| **multi_agent** | no |
| **wq_id** | — |
| **plan** | — |
| **phases** | — |
| **agents_remaining** | |
| **completed** | |

**Session opener (only — give the other agent this single line):**

`Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\HANDOFF_BSOD_STATUS.md and confirm.`

---

## Executive summary

BSOD Analyzer **v6.5.27** is the current shipping line. **Phases 1–7** on [`ROADMAP.md`](../ROADMAP.md) are ☑; the **maintainability / facade milestone (6.5.0)** is ☑. There is **no active product work queue row** — next product direction lives under ROADMAP **Approved intent** (three upgrade tracks, Tier 3 plans drafted, **not buildable** until promoted).

**Portable-first / Maintenance USB** is settled policy: durable data on the **target PC** at `%LOCALAPPDATA%\BSODAnalyzer\`; the stick holds exe/runtime only. **Full install mode** remains in code for compatibility — do not remove without explicit user request.

**Agent environment:** Cursor as **Administrator**; Agent Starter Pack **1.8.0 / audit engine 2.22.65** installed and refreshed for this repo (2026-09-02).

---

## What shipped recently

| When | What | Evidence |
|------|------|----------|
| **2026-08-31** | **WQ-001** Maintenance USB PC-local data (M1–M4) | [`handoff_archive/HANDOFF_WQ001_maintenance_usb_data.md`](../handoff_archive/HANDOFF_WQ001_maintenance_usb_data.md); `run_tests.bat` exit 0 |
| **2026-09-01** | **WQ-002** Stick-side migration **removed** (M2 retired) | `migrate_maintenance_usb_from_stick` gone from `app_settings.py`; legacy flat cache uses `maintenance_data_dir()` in `catalog_cache.py`; docs: `KNOWN_LIMITATIONS.md`, `ROADMAP.md`, `AGENT_READINESS.md`, `PROJECT_LAYOUT.md`, `MAINTENANCE_USB_DATA_PLAN.md` |
| **2026-09-02** | Git remote + full tree tracking | `https://github.com/binary-100/BSODAnalyzer.git` · branch `main` · 867 paths tracked |
| **2026-09-02** | Agent Starter Pack upgrade on dev machine | Generic rules synced (12); audit system synced; `docs/AGENT_SESSION_START.md` reports engine **2.22.65** fresh |

**Stable build on disk:** `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer_StableBuilds\v6.5.27` (see `STABLE_BUILD_LOCATION.txt`).

---

## Where we are (product)

### Master roadmap

| Area | Status |
|------|--------|
| Phases **1–7** (capture, logs, repair UX, catalog perf, doc hygiene) | ☑ |
| **Driver verification** plan Phases 1–7 | ☑ [`DRIVER_VERIFICATION_PLAN.md`](../DRIVER_VERIFICATION_PLAN.md) |
| **Maintainability** (catalog split, crash-report slices, facade Option 2) | ☑ **6.5.0** — [`FACADE_ORCHESTRATION.md`](../FACADE_ORCHESTRATION.md), [`CATALOG_MODULE_SPLIT.md`](../CATALOG_MODULE_SPLIT.md) |
| **ROADMAP work queue** | **Empty** — nothing is **Next** for product build |
| **Approved intent** (Tier 2 — watch, do not build) | Rescue USB · Native dump engine · Guided diagnostic UX — see [`upgrade/README.md`](../upgrade/README.md) |
| **Exploration (Tier 1)** | Action Plan checklist — [`upgrade/inbox/EXPLORATION_LOG.md`](../upgrade/inbox/EXPLORATION_LOG.md) |
| **Parked** | [`upgrade/parked/PARKED.md`](../upgrade/parked/PARKED.md) — read only when user asks |

### Process work queue ([`docs/WORK_QUEUE.md`](../WORK_QUEUE.md))

| ID | Status |
|----|--------|
| WQ-001 Maintenance USB PC-local | **Done** 2026-08-31 |
| WQ-002 Stick migration removed | **Done** 2026-09-01 |
| Active / Inbox | **Empty** |

---

## Architecture snapshot (~69k LOC)

| Layer | Notes |
|-------|--------|
| **Entry** | `bsod_analyzer.py` (VERSION), `bsod_gui_qt.py`, CLI via `bsod_workflow.py` |
| **Analysis** | `bsod_crash_report.py` + `crash_report_*` modules; minidump via CDB in `bsod_minidump.py` |
| **Catalog** | `driver_catalog.py` facade → `catalog_*` modules; ~5 min p50 scan budget |
| **GUI** | `gui_mixin_*` on `gui_app_context.py`; offscreen tests via `tests/gui_test_harness.py` |
| **Settings / paths** | `app_settings.py` — `maintenance_data_dir()`, portable vs `full` install branches **intentional** |
| **Tests** | `run_tests.bat` (pytest discovery); full suite ~8+ min; `QT_QPA_PLATFORM=offscreen` + harness required |

**Do not start** new ROADMAP features, Phase 8, or Tier 3 upgrade implementation until user promotes a row to the work queue and says **implement Phase X** per [`upgrade/BUILD_HANDOFF.md`](../upgrade/BUILD_HANDOFF.md).

---

## Agent obligations (short)

Full detail: [`PRODUCT_REFERENCE.md`](../PRODUCT_REFERENCE.md) §2, [`AGENT_READINESS.md`](../AGENT_READINESS.md).

| Agent runs | User verifies |
|------------|---------------|
| `run_tests.bat` after code changes | Output / exit code |
| `py -3 scripts\live_validate_analysis.py` (admin) | Attribution matches their machine |
| Dump enable, CDB install prompts, event log reads | Outcomes in app |
| Qt test hygiene if popups reported | — |

**Never** ask the user to enable dumps, run as admin, or run tests you can run in-session.

---

## Validation state (this handoff)

| Check | Result | Notes |
|-------|--------|-------|
| Version | **6.5.27** | `bsod_analyzer.py` + `VERSION.txt` |
| Agent context | **Fresh** | `docs/AGENT_SESSION_START.md` — pack 1.8.0, engine 2.22.65 |
| Full `run_tests.bat` at handoff write | **exit 0** | 2026-09-02 after handoff docs written |
| Live validation | **Not run** this session — run on host when changing analysis paths |

---

## Blockers and risks

### 1. Git repository state

**Resolved 2026-09-02:** Remote **`https://github.com/binary-100/BSODAnalyzer.git`**. Full flat tree tracked; build output (`BSODAnalyzer_v6/`) and CDB symbol cache gitignored. Clone → `run_tests.bat` → `build_ci.bat` for portable exe.

### 2. PRODUCT_REFERENCE date header

Header still says **2026-08-23** — update when next capability ships (version sync does not fix prose).

---

## Recommended next steps (when user asks)

1. **Promote upgrade track** — user picks one Approved intent row → ROADMAP work queue → `implement Phase X` with plan under `docs/upgrade/plans/`.
2. **Audit** — say **audit**; agent runs full `run_audit.cmd` protocol per `AGENTS.md`.
3. **Rebuild** — `set BUILD_NOPAUSE=1` + `build_ci.bat` after version bump; stable archive via `scripts\save_stable_build.bat` → Desktop `BSODAnalyzer_StableBuilds\`.

---

## Read order for a new agent

1. [`AGENTS.md`](../../AGENTS.md)
2. [`docs/PRODUCT_REFERENCE.md`](../PRODUCT_REFERENCE.md)
3. [`docs/AGENT_READINESS.md`](../AGENT_READINESS.md) — § Session-start self-audit for substantial work
4. [`docs/ROADMAP.md`](../ROADMAP.md) — work queue + Approved intent only
5. [`docs/WORK_QUEUE.md`](../WORK_QUEUE.md) — process radar
6. [`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md) — honest limits (not bugs)

**Upgrade planning only:** [`docs/upgrade/README.md`](../upgrade/README.md) + `.cursor/rules/design-tier-gate.mdc` — no production code from plans alone.

---

## Related handoffs

| File | Role |
|------|------|
| [`HANDOFF_orientation_tiers.md`](HANDOFF_orientation_tiers.md) | Tier 1–3 / design gate vocabulary |
| [`../handoff_archive/HANDOFF_WQ001_maintenance_usb_data.md`](../handoff_archive/HANDOFF_WQ001_maintenance_usb_data.md) | Completed WQ-001 slice |
| [`SESSION.md`](SESSION.md) | Short session pointer — no duplicate Next table |

**Pack (separate repo):** Agent Starter Pack status lives in `C:\Users\binar\OneDrive\Desktop\AgentStarterPack\docs\WORK_QUEUE.md` — not duplicated here.
