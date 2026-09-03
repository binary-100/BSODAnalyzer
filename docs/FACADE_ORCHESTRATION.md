# Facade & orchestration (`bsod_analyzer.py`)

**Version context:** see [`VERSION.txt`](../VERSION.txt) · **Last updated:** 2026-08-20

This doc is the **canonical gate and design reference** for work on `bsod_analyzer.py` re-exports, orchestration peels, and facade pruning. Agents must follow it before claiming facade work is “checked” or “safe.”

Related: [`AGENT_READINESS.md`](AGENT_READINESS.md) § Tiered validation **T3**, [`CATALOG_MODULE_SPLIT.md`](CATALOG_MODULE_SPLIT.md), [`scripts/README.md`](../scripts/README.md) § Facade gate.

---

## What `bsod_analyzer.py` is today

| Piece | Role |
|-------|------|
| **Local defs** | `request_admin_elevation`, `is_user_admin`, `run_analysis`, CLI/GUI entry — ~7 functions |
| **Re-exports** | ~124 symbols (6.4.112) from owner modules |
| **Consumers** | GUI via `import bsod_analyzer as core` in `gui_app_context.py` (star-imported by all mixins); workers; tests; catalog/firmware modules; lazy `_ba()` in peeled modules |

**Not a stable public API today** — it is a **compatibility barrel** so GUI mixins, tests (`mock.patch("bsod_analyzer.*")`), and PyInstaller entry keep working after module splits.

---

## Mandatory gate (T3 — Facade / orchestration)

Run **before** any re-export prune, orchestration change, or “facade is safe” claim:

```bat
cd app
scripts\verify_facade_gate.cmd
scripts\verify_agent_report.cmd --require facade
```

**Exit 0 required** for both: the first **runs and records** proof; the second **verifies** the proof matches this git tree and is fresh. Then **T2** / **T4** as applicable — see [`AGENT_READINESS.md`](AGENT_READINESS.md).

### What the gate checks (not optional)

| Check | Why |
|-------|-----|
| Static: every `core.*`, `_ba('…')`, `from bsod_analyzer import`, `mock.patch("bsod_analyzer.*")` | GUI mixins do not import `bsod_analyzer` literally — they use `gui_app_context` |
| Runtime: `hasattr(bsod_analyzer, sym)` for all 38 `_ba` + 94 `core.*` symbols | Import counts miss peeled-module `_ba` paths (e.g. `_parse_event_time`, `device_enrichment`) |
| Prune list = exports − used − local − body_only | “Unused” from grep alone has caused false prune lists |
| Import chain + PyInstaller hiddenimports | Portable exe must still import peeled modules |
| Decouple list | Production modules still importing the barrel instead of owner modules |

**Forbidden:** partial import grep, spot-checking 4 symbols, or reporting “checked” without exit 0 from `verify_facade_gate.cmd`.

When presenting facade options or claiming facade work is done, also follow **`AGENT_READINESS.md` § Risk and validation reporting** — state **Agent runs it?** for each named risk; if Yes and gates pass, **Remaining risk: none**.

---

## Latest machine-readable scan

Regenerate on every facade evaluation:

```bat
py -3 scripts\audit_facade_complete.py
```

Output: [`docs/_FACADE_AUDIT_REPORT.txt`](_FACADE_AUDIT_REPORT.txt) (gitignored artifact; copy summary into commit message if pruning).

---

## Design axes (speed · accuracy · efficiency)

| Axis | Facade prune / decouple impact |
|------|--------------------------------|
| **Speed (user)** | ~None — `import bsod_analyzer` ≈ 50–70ms; `_ba()` ≈ sub-µs; catalog scan ~5 min unchanged |
| **Accuracy** | **High risk if gate skipped** — missing re-export breaks runtime paths tests do not cover |
| **Efficiency (maintainability)** | **Main benefit** — smaller barrel, clearer owner modules, less circular-import glue |

Pruning duplicate re-exports does **not** make scans faster or analysis smarter. Decoupling catalog imports **does** reduce accidental coupling for future catalog work.

---

## Top 3 options (evaluate with fresh `_FACADE_AUDIT_REPORT.txt`)

**Shipped (6.4.112): Option 2** — pruned 39 dead re-exports; decoupled 17 production modules off the barrel (GUI unchanged).

**Shipped (6.4.113):** `product_version.py` reads `VERSION.txt` directly — last production decouple candidate.

Numbers below are from the **post-Option-2 gate**; re-run before any new facade work.

### Option 1 — Prune verified duplicates only (low risk)

**Do:** Remove **31** symbols listed under `prune_candidates` in the audit report — each verified unused via static + runtime probe. Keep the barrel otherwise as-is.

| | |
|---|---|
| **Speed** | No meaningful change |
| **Accuracy** | Low risk **if** gate exit 0 before and after |
| **Efficiency** | Modest — ~19% fewer dead re-exports |
| **Effort** | ~1 session — delete imports, T2 + gate + T4 |

**Best when:** You want incremental cleanup without touching GUI or catalog import style.

### Option 2 — Documented facade + decouple catalog/firmware (recommended)

**Do:** Option 1 **plus** retarget **production** modules listed under `DECOUPLE CANDIDATES` to owner modules (`bsod_hardware_wmi`, `bsod_crash_report`, `bsod_runtime`, `crash_report_culprit`, etc.). Leave `gui_app_context` → `core` unchanged for now.

| | |
|---|---|
| **Speed** | No meaningful change (may slightly reduce import fan-in for catalog-only scripts) |
| **Accuracy** | Neutral if gated; **reduces** future peel regressions |
| **Efficiency** | **Best architectural win** — catalog stack stops depending on full barrel |
| **Effort** | ~2–3 sessions — ~15 production files, mostly lazy imports |

**Best when:** Maintainability is the goal and you want the next catalog slice to import real owners, not the whole app shell.

### Option 3 — Keep as-is (valid)

**Do:** No prune. Fix only gate failures (missing `_ba` targets). Use `verify_facade_gate.cmd` on any future orchestration touch.

| | |
|---|---|
| **Speed / accuracy** | Unchanged |
| **Efficiency** | Technical debt remains but **contained** if gate is enforced |
| **Effort** | Zero now |

**Best when:** ROADMAP product work resumes and facade churn is not worth the review cost this month.

### Not recommended now

| Approach | Why |
|----------|-----|
| **Aggressive prune (>31)** | Prior scans wrongly marked GUI-only symbols as unused |
| **Replace GUI `core` barrel** | High churn across ~20 mixins; no user speed gain |
| **Thin “public API” module** | Extra layer; tests patch `bsod_analyzer.*` today |

---

## After shipping facade changes

1. `scripts\verify_facade_gate.cmd` → exit 0 (records `facade` proof)  
2. `scripts\verify_agent_report.cmd --require facade` (+ `t2`, `t4` as applicable) → exit 0  
3. `run_tests.bat` → exit 0 (records `t2` proof)  
4. Admin: `py -3 scripts\live_validate_analysis.py` when analysis paths touched (records `t4` proof)  
5. Bump `VERSION` + `apply_version.py sync`  
6. Update this doc only if gate commands or option tradeoffs change  

---

## Post-slice checklist (facade work)

- [ ] Gate exit 0 (`verify_facade_gate.cmd`) + proof verified (`verify_agent_report.cmd --require facade`)
- [ ] T2 full suite
- [ ] T4 live validation if analysis/GUI workers touched
- [ ] No new `core.*` / `_ba` without re-export or direct owner import
- [ ] `_FACADE_AUDIT_REPORT.txt` regenerated in session (artifact)
