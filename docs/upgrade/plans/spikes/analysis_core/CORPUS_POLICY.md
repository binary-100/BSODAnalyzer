# Parity corpus policy (D1)

Maintainer-local and checked-in fixtures for native vs CDB parity.

---

## Locations

| Path | Git | Purpose |
|------|-----|---------|
| `corpus/` | **Ignored** (`*.dmp`) | Real anonymized samples from the field |
| `fixtures/` | **Committed** | Synthetic PAGE/MDMP bytes for CI — no customer data |

---

## Collecting real samples (`corpus/`)

1. **Anonymize** — remove hostnames from paths in reports; do not commit `%COMPUTERNAME%` in filenames if identifiable.
2. **Prefer** your own test VMs after controlled bugchecks.
3. **Public sets** — kdmp-parser / training dumps only when license allows redistribution.
4. **Minimum for D1 sign-off** — at least **5** PAGE-format kernel minidumps with varied bugcheck codes (Windows 10/11 `C:\Windows\Minidump\` style).
5. **Record** aggregate match rate in Native D1 phase notes when promoting to Build.

---

## Acceptance (D1 Build promotion)

| Criterion | Target |
|-----------|--------|
| Harness runs | `parity_harness.py` exit 0 on `fixtures/` with `--include-fixtures` |
| Real corpus | Maintainer corpus exit 0 under default strict, **or** documented known gaps with ticket |
| Fields | `bugcheck_code`, `bugcheck_p1` match CDB on PAGE dumps; `faulting_driver` may differ until D2 triage driver list |
| CDB reference | `find_cdb()` must resolve — not merely importable |

---

## Running

```bat
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py --include-fixtures --no-strict
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py --corpus D:\path\to\anonymized
```

Default: **strict** exit 1 when corpus is non-empty and any field diff or native parse failure while CDB succeeds. Use `--no-strict` for exploratory diff reports.
