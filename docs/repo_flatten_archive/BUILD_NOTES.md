# BSOD Analyzer — build notes

**Canonical source:** `Desktop\BSODAnalyzer\app\`  
**Version:** see `app\VERSION.txt`

## Build (from `app\`)

```bat
set BUILD_NOPAUSE=1
call build_ci.bat
```

Output: `app\BSODAnalyzer_v6\BSODAnalyzer.exe`

Stable archives (manual only): `app\scripts\save_stable_build.bat` → `Desktop\BSODAnalyzer_StableBuilds\`

## Historical release notes

Parallel catalog work (6.2.x): [`app/docs/release_notes/BUILD_NOTES_v6.2.md`](app/docs/release_notes/BUILD_NOTES_v6.2.md)
