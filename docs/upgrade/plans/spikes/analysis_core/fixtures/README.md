# Checked-in dump fixtures (synthetic)

| File | Format | Purpose |
|------|--------|---------|
| `page_minimal.dmp` | PAGE / DUMP_HEADER64 | Bugcheck `0x124` at header offset `0x38` — validates PAGE parser without customer dumps |

Regenerate:

```bat
py -3 -c "import struct; from pathlib import Path; buf=bytearray(0x1000); struct.pack_into('<I',buf,0,0x45474150); struct.pack_into('<I',buf,0x38,0x124); Path(r'docs/upgrade/plans/spikes/analysis_core/fixtures/page_minimal.dmp').write_bytes(bytes(buf))"
```

Real BSOD minidumps on Windows 10/11 are typically **PAGE triage**, not classic **MDMP**. See [`../CORPUS_POLICY.md`](../CORPUS_POLICY.md).
