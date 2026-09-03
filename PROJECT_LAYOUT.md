# BSOD Analyzer — project layout

**Status:** Active — **flat layout** (git root = product root = agent root)  
**Version:** see [`VERSION.txt`](VERSION.txt)

---

## Desktop layout (end state)

| Folder | Role |
|--------|------|
| `Desktop\BSODAnalyzer\` | **This repo** — edit, test, build here |
| `Desktop\BSODAnalyzer_StableBuilds\` | Max **3** user-approved stables (see `docs/AUDIT.md` §B stable policy) |

**Copy to USB from the stable archive** — not from a duplicate folder inside the dev tree.

---

## Folder glossary (project root)

| Path | Kind | Keep? | Notes |
|------|------|-------|-------|
| `*.py`, `tests\`, `docs\`, `scripts\` | **Source** | Yes | Edit and test here |
| `DebuggingTools\` | **Build input** | Yes | CDB bundled into `BSODAnalyzer_v6\_internal\` |
| `PowerShellModules\` | **Build input** | Yes | MSCatalogLTS vendored for v6 builds |
| `BSODAnalyzer_v6\` | **Build output** | Yes | Latest CI/local portable build (`build_ci.bat`) |
| `%LOCALAPPDATA%\BSODAnalyzer\` | **Runtime user data** | On target PC | Maintenance USB + full install: settings, catalog cache, default exports (see `app_settings.py`) |
| `BSODAnalyzer_portable\` (beside exe or source) | **Legacy orphan** | Gitignored | Old stick-side folder from pre–PC-local builds; app ignores it except optional OneDrive warning — safe to delete when empty |
| `BSODAnalyzer_v6\BSODAnalyzer_portable\` | **Legacy (dist)** | Rare | Same dirname if an old build created stick-side data; not used by current builds |
| `build\`, `dist\` | **Build scratch** | No | PyInstaller intermediates — delete anytime; gitignored |
| `docs\repo_flatten_archive\` | **Archive** | Yes | Pre-2026-08-30 repo-root + migration docs |

### Naming (product terms)

- **`BSODAnalyzer_v6`** — portable app distribution folder (exe + `_internal\`).
- **`BSODAnalyzer_portable`** — legacy stick-side folder name only; durable state is PC-local (`%LOCALAPPDATA%\BSODAnalyzer\`). USB holds launcher + runtime only.

---

## Commands (from project root)

```bat
run_tests.bat
run_audit.cmd
set BUILD_NOPAUSE=1
call build_ci.bat
Refresh-AgentContext.cmd
```

---

## Agent / pack

| Item | Path |
|------|------|
| Agent entry | [`AGENTS.md`](AGENTS.md) |
| Product truth | [`docs/PRODUCT_REFERENCE.md`](docs/PRODUCT_REFERENCE.md) |
| Work queue | [`docs/WORK_QUEUE.md`](docs/WORK_QUEUE.md) |
| Pack refresh | [`Refresh-AgentContext.cmd`](Refresh-AgentContext.cmd) |

No nested `app\` folder — if `app\` reappears, treat it as obsolete (audit flags it).

---

## Flatten record

See [`docs/REPO_FLATTEN_PLAN.md`](docs/REPO_FLATTEN_PLAN.md).
