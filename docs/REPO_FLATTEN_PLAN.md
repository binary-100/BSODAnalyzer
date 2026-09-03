# Repo flatten plan — BSOD Analyzer

**Status:** Completed **2026-08-30**  
**Decision:** Option A — git root = product root = agent root (same as Agent Starter Pack flat bootstrap).

---

## Why

Phase 6 consolidation left a finished migration shell (`repo/` + `app/`). That caused duplicate agent surfaces (rules, WORK_QUEUE, refresh paths) and BSOD-specific shims. **Not a permanent architecture.**

---

## Phases

| Phase | Work | Evidence |
|-------|------|----------|
| 1 | Inventory + scripts | `scripts/flatten_repo.ps1`, `scripts/update_paths_after_flatten.ps1` |
| 2 | Lift `app/` to git root | `app/` directory removed |
| 3 | Path updates | `run_audit.ps1` flat RepoRoot logic; `AUDIT.config.json` §B paths |
| 4 | Root docs | `README.md`, `PROJECT_LAYOUT.md` rewritten; pre-flatten files in `docs/repo_flatten_archive/` |
| 5 | Verify | `run_tests.bat` exit 0 |

---

## Cursor / agents

- **Open workspace:** `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer`
- **Refresh:** `Refresh-AgentContext.cmd` at project root (no path args)
- **Removed:** `.agent-bootstrap.json`, repo-root `docs/WORK_QUEUE` stub, nested `app/app/.cursor`

---

## Do not restore

- Do not recreate `app/` as a source tree.
- Do not add repo-root-only agent rules separate from `.cursor/rules/`.
