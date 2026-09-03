# BSOD Analyzer

**Version:** see [`app/VERSION.txt`](app/VERSION.txt)

## Quick start

| Task | Where |
|------|--------|
| Run the app | `app\BSODAnalyzer_v6\BSODAnalyzer.exe` |
| Edit source | `app\` |
| Tests | `app\run_tests.bat` |
| Build | `app\build_ci.bat` (`BUILD_NOPAUSE=1` for agents) |
| Layout contract | `PROJECT_LAYOUT.md` |
| Audit | Step 1: `app\run_audit.cmd` → step 2: semantic report + `app\scripts\verify_semantic_audit.cmd` → step 3: `app\scripts\finalize_audit.cmd` — see `app\docs\AUDIT.md` |

## Stable builds (max 3, user-approved)

`Desktop\BSODAnalyzer_StableBuilds\` — policy and folder names: [`PROJECT_LAYOUT.md`](PROJECT_LAYOUT.md)

## Layout

```
BSODAnalyzer/
  README.md
  PROJECT_LAYOUT.md
  app/                 ← source, tests, builds
    bsod_analyzer.py
    BSODAnalyzer_v6/
    tests/
    docs/
```

## Field test on another PC

1. Copy the latest **user-approved stable** from `Desktop\BSODAnalyzer_StableBuilds\` to a flash drive.
2. Run → Drivers → Refresh → Search (Quick check off).
3. Tools → Export scan results.

Compare exports: `py -3 app\scripts\compare_catalog_exports.py a.json b.json`
