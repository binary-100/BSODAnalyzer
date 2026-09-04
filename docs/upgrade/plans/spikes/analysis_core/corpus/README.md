# Parity corpus (maintainer-local)

Place anonymized kernel minidump files here as `*.dmp`. **Do not commit** customer dumps to git.

Suggested collection:

- Your own test VMs after forced bugchecks
- Public samples from kdmp-parser / WinDbg training sets (verify license)

Run:

```bat
py -3 docs\upgrade\plans\spikes\analysis_core\parity_harness.py
```

Record aggregate diff counts in Native D1 phase notes when promoting to Build.

Policy: [`../CORPUS_POLICY.md`](../CORPUS_POLICY.md)
