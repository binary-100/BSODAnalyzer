# BSOD Analyzer versioning

## Product lines

| Line | Folder | Build script | Scope |
|------|--------|--------------|--------|
| **v5 maintenance** | `BSODAnalyzer_v5\` | `build_and_deploy_v5.bat` | Bugfix-only (5.4.13: AMD logo). No v6 catalog work. |
| **v6 active** | `BSODAnalyzer_v6\` | `build_and_deploy_v6.bat` | Driver catalog overhaul, MSCatalogLTS, accuracy, scrapers. |

Source code is shared. `product_version.is_v6_line()` gates v6-only behavior at runtime.  
Development default: see **`VERSION.txt`** / `bsod_analyzer.py` → `VERSION` (never hard-code in docs).

## Recompile

**v6 (default / CI):**
```bat
build_ci.bat
```
or `build_and_deploy_v6.bat` (runs full `run_tests.bat` first).

**v5 maintenance only:**
```bat
build_and_deploy_v5.bat
```
Applies 5.4.13, builds AMD PNG from reference, runs `run_tests_v5.bat`, deploys to `BSODAnalyzer_v5\`, then restores the v6 dev version in source (see `scripts/apply_version.py`).

## Layout

| Location | Role |
|----------|------|
| **Repo root** | Python source, specs (`BSODAnalyzer.spec` = v6, `BSODAnalyzer.v5.spec` = v5) |
| **BSODAnalyzer_v5/** | Last stable v5 portable app |
| **BSODAnalyzer_v6/** | Current v6 portable app |
| **PowerShellModules/** | Bundled MSCatalogLTS (v6 builds only) |
| **dist/v5_build**, **dist/v6_build** | PyInstaller output (safe to delete) |

## Version bumps

| Type | Action |
|------|--------|
| **v5 patch** (e.g. 5.4.13 → 5.4.14) | Update `scripts/apply_version.py` preset `5`, AMD-only changes, `build_and_deploy_v5.bat` |
| **v6 minor/patch** | `py scripts/apply_version.py 6` or edit `VERSION` + `VERSION.txt`, then `build_and_deploy_v6.bat` |

## v6 build model

- PyInstaller **onedir** (`BSODAnalyzer.exe` + `_internal\`).
- CDB from `DebuggingTools\x64\`.
- MSCatalogLTS from `PowerShellModules\` (writable copy beside exe on first run; online gallery update when connected).

## v5 build model

- Same onedir layout as v5.4.12.
- **No** `PowerShellModules` bundle.
- **amd.png** from user reference via `scripts/build_amd_logo_png.py` (removes `amd.svg` if present).

## Requirements

- Python 3.14+ recommended (3.12+ supported); PySide6 and PyInstaller
- `DebuggingTools\x64\cdb.exe` at repo root
- v6: run `scripts\vendor_mscataloglts.ps1` once (or let `build_and_deploy_v6.bat` run it)
- AMD logo: committed as `assets\vendor_icons\amd_reference.png` + `amd.png` (both v5 and v6 builds)
