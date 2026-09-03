# Catalog module split (maintainability)

**Slice status:** ☑ **Complete** — shipped in maintainability milestone **6.5.0** (catalog slices through 6.4.105 + facade decouple).  
**Orchestration:** ☑ **`driver_catalog.py`** ~665 LOC — imports, re-exports, OEM session cache, and `_log_catalog_skip` only.  
**Next maintainability target:** none required for release — GUI `core` barrel deferred by design (see [`FACADE_ORCHESTRATION.md`](FACADE_ORCHESTRATION.md)).  
**Canonical version:** see [`VERSION.txt`](../VERSION.txt)

Phase 8 (extended driver sources) is **Parked** — see **`ROADMAP.md`** and **`upgrade/parked/PARKED.md`**.

---

## Why

| Module | ~Lines | Risk |
|--------|-------:|------|
| `driver_catalog.py` | ~665 | Re-exports + OEM session cache only |
| `bsod_crash_report.py` | ~1,006 | Orchestration + analysis helpers (slices in `crash_report_*`) |
| `crash_report_narrative.py` | ~676 | Cause typing, confidence ladder, log narrative |
| `bsod_analyzer.py` | ~344 | CLI/GUI entry, admin, re-exports |
| `analyzer_gather.py` | ~420 | `gather_report_data`, firmware inventory for Run Analysis |
| `analyzer_hardware.py` | ~129 | Drivers-tab hardware profile scan |
| Large GUI mixins | mostly split | Residual hotspots in `gui_mixin_catalog.py` stub / drivers workflow |

---

## Target modules

| New module | Responsibility | Status |
|------------|----------------|--------|
| **`catalog_scoring.py`** | Version parse/compare, package dates, `compare_driver_to_installed` | ☑ |
| **`catalog_offer_pipeline.py`** | enrich/sort/filter offers, `_finalize_catalog_offers` | ☑ |
| **`catalog_oem_live.py`** | Live OEM API fetch (`_fetch_live_oem_offers`, per-vendor) | ☑ |
| **`catalog_mscatalog_session.py`** | Batch warm, online store cache, GUI session flags | ☑ |
| **`catalog_device_profiles.py`** | GPU/chipset/audio/network dual-version profiles | ☑ |
| **`catalog_http.py`** | Shared GET/POST, robust vendor fetch, HTML payload sniff | ☑ |
| **`catalog_oem_filters.py`** | OEM brand alignment, PC-maker reject filters | ☑ |
| **`catalog_row_rejects.py`** | Row rejection, HWID match, MSCatalog row filters | ☑ (6.4.81) |
| **`catalog_device_context.py`** | Device label, vendor/chipset/GPU classification | ☑ (6.4.81) |
| **`catalog_tier_policy.py`** | Tier/deferral/OEM-skip policy, network vendor keys | ☑ (6.4.81) |
| **`catalog_offer_status.py`** | Offer status eligibility, summarize_offer_status | ☑ (6.4.82) |
| **`catalog_none_reason.py`** | None-reason classification, progress formatting | ☑ (6.4.82) |
| **`catalog_offer_compare.py`** | Per-offer compare, verification, uncertain-resolution | ☑ (6.4.83) |
| **`catalog_realtek_queries.py`** | Realtek UAD catalog queries | ☑ (6.4.83) |
| **`catalog_mscatalog_queries.py`** | MSCatalog search query builders | ☑ (6.4.83) |
| **`catalog_chipset_comparison.py`** | Chipset/platform comparison | ☑ (6.4.84) |
| **`catalog_installed_packages.py`** | Add/Remove Programs version cache | ☑ (6.4.85) |
| **`catalog_lru_cache.py`** | Generic LRU touch/set for session caches | ☑ (6.4.86) |
| **`catalog_vendor_cache.py`** | Vendor scrape cache, cache keys, batch warm | ☑ (6.4.86) |
| **`catalog_wu_scoring.py`** | WU row scoring, bulk-offer filter | ☑ (6.4.87) |
| **`catalog_microsoft_scoring.py`** | Online store + MSCatalog row scoring | ☑ (6.4.88) |
| **`catalog_microsoft_fetch.py`** | WU / online store / MSCatalog fetch | ☑ (6.4.89) |
| **`catalog_intel_fetch.py`** | Intel download-page scrape | ☑ (6.4.90) |
| **`catalog_amd_fetch.py`** | AMD download-page scrape | ☑ (6.4.91) |
| **`catalog_nvidia_fetch.py`** | NVIDIA Ajax/processfind lookup | ☑ (6.4.92) |
| **`catalog_realtek_fetch.py`** | Realtek download-center scrape | ☑ (6.4.93) |
| **`catalog_network_fetch.py`** | Killer / Broadcom / Qualcomm / MediaTek | ☑ (6.4.94) |
| **`catalog_extended_fetch.py`** | Marvell, Synaptics/Elan, peripherals | ☑ (6.4.95) |
| **`catalog_multi_device.py`** | Multi-device batch check pipeline | ☑ (6.4.96) |
| **`catalog_download.py`** | Package download, URL resolve, MSCatalog fetch-to-disk | ☑ (6.4.98) |
| **`catalog_system_actions.py`** | System Restore, Device Manager, driver backup | ☑ (6.4.99) |
| **`catalog_vendor_offers.py`** | Vendor offer rows, manufacturer lookup gating | ☑ (6.4.100) |
| **`catalog_oem_offers.py`** | OEM offer orchestration, disk-cache freshness | ☑ (6.4.101) |
| **`catalog_ps_context.py`** | PowerShell bridge, PnPSigned index, system ctx probe | ☑ (6.4.102) |
| **`catalog_scan_summary.py`** | Scan mode summary, uncertain-offer inspector | ☑ (6.4.103) |
| **`catalog_online_store.py`** | Online store load gate, storage matching | ☑ (6.4.104) |
| **`catalog_device_comparison.py`** | Per-device tier orchestration | ☑ (6.4.105) |
| **`driver_catalog.py`** | Re-exports + OEM session cache | ☑ |
| **`crash_report_narrative.py`** | Cause typing, confidence ladder, log narrative | ☑ (6.4.110) |
| **`analyzer_gather.py`** | Run Analysis data gathering (`gather_report_data`, firmware inventory) | ☑ (6.4.109) |
| **`analyzer_hardware.py`** | Drivers-tab hardware profile scan | ☑ (6.4.109) |
| **`bsod_analyzer.py`** | CLI/GUI entry, admin, re-exports | ☑ (6.4.109) |

**GUI mixins** — see table in prior sections; shell/drivers/firmware splits ☑ through 6.4.80+.

---

## Rules

1. **Behavior unchanged** — extract + re-export; run full `run_tests.bat` after each slice.
2. **Stable imports** — keep `driver_catalog.compare_versions` etc. working via re-exports.
3. **One slice per change** — do not move scoring + OEM + MSCatalog in one commit.
4. **Post-slice docs** — `AUDIT.md` domain map → this file → `scripts/README.md` → `AGENT_READINESS.md` § Module navigation.

---

## Phase 1 checklist (catalog_scoring)

- [x] Extract `parse_driver_version`, `compare_versions`, `parse_driver_package_date`, `driver_date_is_trustworthy`
- [x] Move `compare_driver_to_installed` + NVIDIA/AMD/Realtek mixed-scheme helpers
- [x] Move offer pipeline (`sort_catalog_offers`, `enrich_offers_with_comparison`, …)

See git history and [`ROADMAP.md`](ROADMAP.md) § Maintainability.
