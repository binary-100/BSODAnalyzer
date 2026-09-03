# OneDrive cleanup (Phase 8)

**Status:** Ready when you want to free sync space.

## Current layout (post Phase 6)

| Path | Notes |
|------|--------|
| `Desktop\BSODAnalyzer\` | Dev tree — consider moving to `C:\Dev\BSODAnalyzer` |
| `Desktop\BSODAnalyzer_StableBuilds\` | Keep — 3 approved stables |

## Safe to remove

- Old field-test export triplets on Desktop (keep latest only)
- `app\dist\`, `app\build\`, `__pycache__` after builds

## Tool mitigations (v6.4.61+)

Settings save retries + OneDrive fallback; local export folder when Desktop is synced.
