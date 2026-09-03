# BSOD Analyzer — Driver catalog audit (v6.0.14–6.0.19)

**Status:** Closed (2026-05-30)  
**Scope:** `driver_catalog.py`, `catalog_cache.py`, `catalog_export.py`, Drivers tab export/splitter

This document supersedes informal catalog-audit notes from the v6.0.14–6.0.16 review. Older files such as `CODE_AUDIT_v5.2.18.md` cover the v5 wizard-removal era only.

---

## Shipped fixes

| Version | Focus |
|---------|--------|
| **6.0.14** | Realtek UAD Microsoft Update Catalog — role-aware queries, HWID gates |
| **6.0.15** | OEM match-score gates; class rejection; Drivers tab splitter rebalance |
| **6.0.16** | OEM session cache (raw rows); batch chipset installed version |
| **6.0.17** | Cache machine identity; AMD/NVIDIA per-device warm keys; OEM session all vendors; chipset pipeline parity; status honesty; MSI live OEM |
| **6.0.18** | Session persist from warmed cache; export debug fields; export batch precedence; chipset PnP anchor; WU cap metadata; stale detection with profile |
| **6.0.19** | Audit doc closure; splitter min heights; regression tests for remaining gaps |
| **6.0.20** | Known-limitations mitigations — chipset MS gate, cache identity, partial OEM persist, portable per-unit cache |

---

## Audit checklist (all addressed)

| ID | Severity | Topic |
|----|----------|--------|
| C1–C3 | Critical | Disk/session cache identity; AMD vendor cache keys |
| H1–H6 | High | OEM session all vendors; cache lock; chipset pipeline; status same/none; WU+OEM freshness; MSI live path |
| M1–M7 | Medium | NVIDIA warm key; session persist; chipset ctx; score dedupe; export fields; export precedence; WU row cap metadata |

---

## Known limitations

Informational only (not backlog). See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## Tests

Coverage in `tests/test_driver_catalog_quality.py`, `tests/test_catalog_export.py`, `tests/test_catalog_audit_coverage.py`, `tests/test_driver_catalog_gui_stable.py`.
