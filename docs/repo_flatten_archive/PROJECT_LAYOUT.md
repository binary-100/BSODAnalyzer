# BSOD Analyzer — Project layout

**Status:** Active — post Phase 6 rename complete  
**Version:** see `app\VERSION.txt`  
**Source:** `Desktop\BSODAnalyzer\app\`

---

## Desktop layout (end state)

| Folder | Role |
|--------|------|
| `Desktop\BSODAnalyzer\` | Active development (`app\` = canonical source) |
| `Desktop\BSODAnalyzer_StableBuilds\` | Max **3** user-approved stables (see `docs/AUDIT.md` §B stable policy) |

**Copy to USB from the stable archive** — not from a duplicate folder inside the dev tree.

---

## Folder glossary (`app\`)

| Path | Kind | Keep? | Notes |
|------|------|-------|-------|
| `*.py`, `tests\`, `docs\`, `scripts\` | **Source** | Yes | Edit and test here |
| `DebuggingTools\` | **Build input** | Yes | CDB bundled into `BSODAnalyzer_v6\_internal\` by PyInstaller |
| `PowerShellModules\` | **Build input** | Yes | MSCatalogLTS vendored for v6 builds |
| `BSODAnalyzer_v6\` | **Build output** | Yes | Latest CI/local portable build (`build_ci.bat`); regenerated |
| `BSODAnalyzer_portable\` | **Runtime user data** | Gitignored | Settings, exports, catalog cache — created beside whichever exe ran (source dev runs write here) |
| `BSODAnalyzer_v6\BSODAnalyzer_portable\` | **Runtime user data** | Inside build | Same as above when running the packaged exe |
| `build\`, `dist\` | **Build scratch** | No | PyInstaller intermediates — delete anytime; gitignored |
| `BSODAnalyzer_v6_stable\` | **Removed** | No | Was an in-repo copy of the Desktop stable archive; use `BSODAnalyzer_StableBuilds\` only |

### Naming confusion (intentional product terms)

- **`BSODAnalyzer_v6`** = the **portable app distribution folder** (exe + `_internal\`).
- **`BSODAnalyzer_portable`** = **user data only** (not a second app). Name is fixed in `app_settings.py` for USB workflow.

---

## Development tree

```
BSODAnalyzer/
  README.md
  PROJECT_LAYOUT.md
  app/                    ← edit, test, build here
    bsod_analyzer.py
    run_tests.bat
    run_audit.cmd
    docs/AUDIT.md
    DebuggingTools/       ← build input (CDB)
    PowerShellModules/    ← build input (MSCatalogLTS)
    BSODAnalyzer_v6/      ← build output (regenerated)
    tests/
```

**Commands (from `app\`):**

```bat
run_tests.bat
run_audit.cmd
set BUILD_NOPAUSE=1
call build_ci.bat
```

---

## Stable builds

Manual archive only: `scripts\save_stable_build.bat` — never automatic on CI.

**Archive location:** `Desktop\BSODAnalyzer_StableBuilds\vX.Y.Z\`  
**Pointer file:** `app\STABLE_BUILD_LOCATION.txt` (updated when you save a stable)

**Desktop stable slots:** max **3** user-approved builds. Replace oldest when promoting a new stable (see `app\STABLE_BUILD_LOCATION.txt` for current pointer). Audit gate checks slot count and forbidden cruft (see `docs\AUDIT.md` §B).

After field-testing `BSODAnalyzer_v6\`, run:

```bat
scripts\save_stable_build.bat /Force
```

---

## Build cruft policy

These are **expected after builds** but should not accumulate in the dev tree:

| Path | Action |
|------|--------|
| `app\build\`, `app\dist\` | Delete after builds (gitignored) |
| `app\BSODAnalyzer_v6_stable\` | Do not create — removed from workflow |
| `app\BSODAnalyzer_portable\` | Safe to delete (dev/test user data; recreated on run) |
| `_cli_*.txt`, `_gui_*.txt`, `_tmp_*`, `live_cli_report.txt` | Agent/dev temp — delete; gitignored |

---

## Migration phases

| Phase | Status |
|-------|--------|
| 0–5 | Done |
| 6 Rename Opus → BSODAnalyzer | Done |
| 7 Archive cleanup | Done |
| 8 OneDrive cleanup | See `ONEDRIVE_CLEANUP.md` |

---

## Cursor workspace

Open: `Desktop\BSODAnalyzer\app`

Agent audit: `docs\AUDIT.md` + `run_audit.cmd`
