# Analysis core spike (D1 — harness plumbing)

**Quarantined** — do not import from `bsod_minidump.py`, GUI, or PyInstaller until Build phase D2b is approved.

| Doc | Purpose |
|-----|---------|
| [`../../ANALYSIS_CORE_PLAN.md`](../../ANALYSIS_CORE_PLAN.md) | Layer model + **PAGE vs MDMP** |
| [`../../INTEGRATION_PATH.md`](../../INTEGRATION_PATH.md) | How to port into production |
| [`../../NATIVE_DUMP_ENGINE_PLAN.md`](../../NATIVE_DUMP_ENGINE_PLAN.md) | Phase D1–D6 checklist |
| [`CORPUS_POLICY.md`](CORPUS_POLICY.md) | Corpus rules + D1 acceptance |

**D1 status:** harness + PAGE header bugcheck read + checked-in fixture — **not** full CDB parity on real dumps until maintainer corpus + D2 driver attribution.

---

## Layout

```
analysis_core/
  contract.py          — dict schema + parity diff (hex-normalized)
  native_minimal.py    — PAGE triage header + limited MDMP
  cdb_reference.py     — CDB via find_cdb(); optional enrich
  parity_harness.py    — CLI; strict exit when corpus has diffs
  fixtures/            — committed synthetic PAGE sample
  corpus/              — gitignored real *.dmp
```

---

## Run parity harness

From repo root:

```bat
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py --include-fixtures --no-strict
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py --corpus D:\path\to\dumps
```

| Flag | Behavior |
|------|----------|
| *(default)* | Empty corpus → exit 0 |
| *(default)* | Non-empty corpus → **strict** exit 1 on any diff |
| `--no-strict` | Report diffs but exit 0 |
| `--include-fixtures` | Also scan `fixtures/*.dmp` |
| `--no-enrich` | Skip `enrich_windbg_analysis` on both sides |

---

## Tests

```bat
py -3 tests\run_test_module.py tests\test_analysis_core_spike.py
```

Included in full `run_tests.bat` suite.

---

## Build agent notes

1. Reimplement `native_minimal.py` in production — **no** `from analysis_core import …` in source tree.
2. Primary format target: **PAGE** triage (`C:\Windows\Minidump\`), not MDMP stream type 4.
3. Evaluate kdmp-parser for faulting driver + stack (D2–D3).
4. Keep CDB as reference until D4 fallback policy is coded.
