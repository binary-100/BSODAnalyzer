# Design spikes (Tier 3 — quarantined)

**Optional POC under `docs/upgrade/plans/spikes/` only.**

| Allowed | Forbidden |
|---------|-----------|
| Standalone scripts on sample dumps | Import into production source without approval |
| Parity native vs CDB reports | Wire into `bsod_minidump.py` / GUI / PyInstaller |

Gate: [`.cursor/rules/design-tier-gate.mdc`](../../../../.cursor/rules/design-tier-gate.mdc)

Reimplement learnings cleanly in the source tree during Build.
