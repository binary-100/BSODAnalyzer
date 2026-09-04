# Design spikes (Tier 3 — quarantined)

**Optional POC under `docs/upgrade/plans/spikes/` only.**

| Spike | Purpose |
|-------|---------|
| [`analysis_core/`](analysis_core/README.md) | **D1** — contract, native BugCheck reader stub, CDB parity harness |

| Allowed | Forbidden |
|---------|-----------|
| Standalone scripts on sample dumps | Import into production source without approval |
| Parity native vs CDB reports | Wire into `bsod_minidump.py` / GUI / PyInstaller |
| Tests via `tests/test_analysis_core_spike.py` | Copy spike tree into `src/` wholesale |

Gate: [`.cursor/rules/design-tier-gate.mdc`](../../../../.cursor/rules/design-tier-gate.mdc)

Reimplement learnings cleanly in the source tree during Build — see [`../INTEGRATION_PATH.md`](../INTEGRATION_PATH.md).
