# Copilot instructions — BSODAnalyzer

**Session start:** read **`docs/AGENT_SESSION_START.md`** when present (stale/fresh + required reads).

Follow **`AGENTS.md`** and **`AI_INSTRUCTIONS.md`** in this repository.

**Agent runs commands; user verifies outcomes** — run sync/tests/fixes yourself; report exit codes so the user can pivot.

## Audits

When the user asks for an **audit**: run **`run_audit.cmd`**, complete the semantic report workflow in **`docs/AUDIT.md`**, and respond with **Fix** and **Improve** sections only.

## Builds and tests

- Tests: **`run_tests.bat`**
- CI-style build: set **`BUILD_NOPAUSE=1`** then **`build_ci.bat`**
- Do not leave Windows batch files waiting on `pause`

## Version

Canonical version lives in **`main.py`** (`VERSION` constant). Do not hand-edit **`VERSION.txt`** — run version sync per **`AGENTS.md`**.
