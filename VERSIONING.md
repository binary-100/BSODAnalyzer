# BSOD Analyzer versioning

## Product line

| Line | Folder | Build script | Scope |
|------|--------|--------------|--------|
| **v6** | `BSODAnalyzer_v6\` | `build_ci.bat` / `build_and_deploy_v6.bat` | Driver catalog, MSCatalogLTS, accuracy, scrapers, portable Maintenance USB |

Canonical version: **`bsod_analyzer.py`** → `VERSION` (synced to `VERSION.txt` by `run_tests.bat` / `scripts/apply_version.py sync`).  
Development default: see **`VERSION.txt`** — never hard-code version numbers in docs.

`product_version.is_v6_line()` is true for all current builds (major ≥ 6).

## Recompile

```bat
set BUILD_NOPAUSE=1
call build_ci.bat
```

or `build_and_deploy_v6.bat` (runs full `run_tests.bat` first).

## Layout

| Location | Role |
|----------|------|
| **Repo root** | Python source, `BSODAnalyzer.spec` (v6 PyInstaller) |
| **BSODAnalyzer_v6/** | Current portable app output |
| **PowerShellModules/** | Bundled MSCatalogLTS |
| **dist/v6_build** | PyInstaller scratch (safe to delete) |

## Version bumps

Edit `VERSION` in `bsod_analyzer.py`, add a `PRESETS` entry in `scripts/apply_version.py` when shipping with custom release-note text, then:

```bat
py -3 scripts\apply_version.py sync
run_tests.bat
set BUILD_NOPAUSE=1
call build_ci.bat
```

## Build model

- PyInstaller **onedir** (`BSODAnalyzer.exe` + `_internal\`).
- CDB from `DebuggingTools\x64\`.
- MSCatalogLTS from `PowerShellModules\` (writable copy beside exe on first run; online gallery update when connected).

## Requirements

- Python 3.14+ recommended (3.12+ supported); PySide6 and PyInstaller
- `DebuggingTools\x64\cdb.exe` at repo root
- Run `scripts\vendor_mscataloglts.ps1` once (or let `build_and_deploy_v6.bat` run it)
- AMD logo: `assets\vendor_icons\amd_reference.png` + `amd.png`
