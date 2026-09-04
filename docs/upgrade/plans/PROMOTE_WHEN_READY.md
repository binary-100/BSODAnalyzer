# Promote when ready — Native dump track

**Purpose:** Single checklist for “are we done planning?” vs “ceremony to start Build.”  
**Not buildable until** ROADMAP work queue + HANDOFF + user “implement Phase X.”

Last updated: **2026-09-04**

**Practical handoff:** ROADMAP row + `HANDOFF_WQ*.md` are for **formal tracking**, not a prerequisite to read docs or to build when **you** scope the task in chat (see § Lightweight session openers). Tier 3 spike code stays quarantined until you say **implement Phase D1**.

---

## Planning work — status

| Item | Status | Notes |
|------|--------|-------|
| Layer model + contract | ☑ | [`ANALYSIS_CORE_PLAN.md`](ANALYSIS_CORE_PLAN.md) |
| Production touch map | ☑ | [`INTEGRATION_PATH.md`](INTEGRATION_PATH.md) |
| D1 spike + tests | ☑ | [`spikes/analysis_core/`](spikes/analysis_core/README.md), `tests/test_analysis_core_spike.py` |
| Real-dump parity baseline | ☑ | § below + [`NATIVE_DUMP_ENGINE_PLAN.md`](NATIVE_DUMP_ENGINE_PLAN.md) |
| Cross-links (ROADMAP, DOC_MAP, …) | ☑ | On disk; **commit pending** |
| kdmp-parser / D2 building-block note | ☑ | [`NATIVE_DUMP_ENGINE_PLAN.md`](NATIVE_DUMP_ENGINE_PLAN.md) § D2 building blocks |
| Planning defaults (slice scope) | ◐ | [`ANALYSIS_CORE_PLAN.md`](ANALYSIS_CORE_PLAN.md) § Open decisions — **confirm before promote** |
| Git commit of above | ☐ | **Do before promote** so Claude diffs one commit |
| ROADMAP work queue row | ☐ | Ceremony — day you promote |
| `HANDOFF_WQnnn_native_dump_d1.md` | ☐ | Ceremony — day you promote |
| Production code / Run Analysis change | ☐ | **Build** — D1 reimplements harness only; D2b first user-visible |

**Nothing else is required in planning** unless you want to extend corpus (more dump variety) or revisit track order (Rescue vs Native).

---

## Lightweight session openers (preferred — saves tokens)

Paste **one** line. You control build vs orient by wording — no promote ceremony required.

**Orient / review only (no production code):**

```
Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\SESSION.md and confirm where we stand on the native dump upgrade; do not change production code.
```

**Implement Native D1 (after git commit on main includes this planning work):**

```
Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\SESSION.md, C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\plans\NATIVE_DUMP_ENGINE_PLAN.md (Phase D1), and C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\upgrade\plans\INTEGRATION_PATH.md; implement Phase D1 only — reimplement the spike harness in scripts/tests, no Run Analysis wiring.
```

Optional reads if the agent needs depth: `ANALYSIS_CORE_PLAN.md`, `docs/upgrade/plans/spikes/analysis_core/`.

Formal **`HANDOFF_WQ*.md` + ROADMAP row** — only when you want Done-log / WQ tracking (see § Promote ceremony).

---

## Parity baseline (host 2026-09-04)

Corpus: `C:\Windows\Minidump\` · 5 files · CDB via `find_cdb()`.

| File | Stop (native = CDB) | Bugcheck parity | Still CDB-only |
|------|---------------------|-----------------|----------------|
| `012926-15546-01.dmp` | `0x124` WHEA_UNCORRECTABLE_ERROR | ☑ | driver, bucket, stack |
| `080426-18703-01.dmp` | `0x50` PAGE_FAULT_IN_NONPAGED_AREA | ☑ | driver, bucket, stack |
| `082126-18484-01.dmp` | `0xA` IRQL_NOT_LESS_OR_EQUAL | ☑ | driver, bucket, stack |
| `082326-19171-01.dmp` | `0x154` UNEXPECTED_STORE_EXCEPTION | ☑ | driver, bucket, stack |
| `121425-16515-01.dmp` | `0x50` PAGE_FAULT_IN_NONPAGED_AREA | ☑ | driver, bucket, stack |

Re-run:

```bat
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py --corpus C:\Windows\Minidump --no-strict
```

---

## Planning defaults (confirm or edit before promote)

| Decision | Planning default | Override when |
|----------|------------------|---------------|
| First build slice | **D1 only** | User wants D1+D2 in one session |
| CDB on hot path until | **D4** (fallback policy) | User wants fallback at D2b |
| First track to promote | **Native dump** | User prioritizes Guided G1 or Rescue 9a |

---

## Promote ceremony (day you start Build)

1. **Commit** all Tier 3 + spike + test changes on `main` (or feature branch).
2. Add **ROADMAP work queue** row: Native dump · Phase **D1** · link HANDOFF path.
3. Create **`docs/handoffs/active/HANDOFF_WQnnn_native_dump_d1.md`** (registry + one session opener).
4. Optional: **WQ-003** in [`WORK_QUEUE.md`](../../WORK_QUEUE.md) for maintainer radar.
5. Fresh chat (e.g. Claude): session opener below.

---

## Build session opener (after steps 1–3)

```
Read C:\Users\binar\OneDrive\Desktop\BSODAnalyzer\docs\handoffs\active\HANDOFF_WQnnn_native_dump_d1.md and implement Phase D1 only.
```

(Replace `WQnnn` with actual id from WORK_QUEUE / ROADMAP.)

**D1 scope reminder:** Production parity harness + corpus workflow — **no** Run Analysis default change. See [`INTEGRATION_PATH.md`](INTEGRATION_PATH.md) § Phase D1.

---

## Optional (only if you care before promote)

| Extra | Value |
|-------|-------|
| More dumps in local `corpus/` (gitignored) | Broader baseline before D2 |
| Fix `test_workflow_copy_batch4.py` flake | Cleaner `run_tests.bat` for build agent |
| Rescue / Guided planning | Only if reordering tracks before Native |

---

## Related

- [`../BUILD_HANDOFF.md`](../BUILD_HANDOFF.md) · [`NATIVE_DUMP_ENGINE_PLAN.md`](NATIVE_DUMP_ENGINE_PLAN.md) · [`SESSION.md`](../../handoffs/SESSION.md)
