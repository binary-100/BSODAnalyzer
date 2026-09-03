# BSOD Analyzer

**Version:** see [`VERSION.txt`](VERSION.txt)

## Quick start

| Task | Command / path |
|------|----------------|
| Run the app | `BSODAnalyzer_v6\BSODAnalyzer.exe` |
| Tests | `run_tests.bat` |
| Build | `set BUILD_NOPAUSE=1` then `build_ci.bat` |
| Audit | `run_audit.cmd` (see [`docs/AUDIT.md`](docs/AUDIT.md)) |
| Agent entry | [`AGENTS.md`](AGENTS.md) |
| Layout contract | [`PROJECT_LAYOUT.md`](PROJECT_LAYOUT.md) |
| Refresh pack context | [`Refresh-AgentContext.cmd`](Refresh-AgentContext.cmd) |

**Cursor workspace:** open `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer` (this folder is the project root).

**Git remote:** `https://github.com/binary-100/BSODAnalyzer.git` — after clone, run `run_tests.bat` then `build_ci.bat` (with `BUILD_NOPAUSE=1`) to produce `BSODAnalyzer_v6\`.

## Stable builds (max 3, user-approved)

`C:\Users\binar\OneDrive\Desktop\BSODAnalyzer_StableBuilds\` — policy in [`PROJECT_LAYOUT.md`](PROJECT_LAYOUT.md)

## Field test on another PC

1. Copy the latest **user-approved stable** from Desktop stables to a flash drive.
2. Run → Drivers → Refresh → Search (Quick check off).
3. Tools → Export scan results.

Compare exports: `py -3 scripts\compare_catalog_exports.py a.json b.json`

## History

Repo flattened **2026-08-30** — former `app/` shell removed; see [`docs/REPO_FLATTEN_PLAN.md`](docs/REPO_FLATTEN_PLAN.md). Pre-flatten docs archived under [`docs/repo_flatten_archive/`](docs/repo_flatten_archive/).
