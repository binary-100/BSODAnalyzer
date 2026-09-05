# Driver bundle verification — unified plan

**Status:** In progress (Phase 1 started 2026-09-05)  
**WQ:** WQ-003  
**Priority:** User-facing accuracy (AGENT_READINESS § Priority order)

AMD chipset SMBus stale while suite matches was the **first found instance** — not the only target. All multi-driver packages use the same subsystem.

---

## Goal

One **bundle verification** pipeline for every multi-driver offer:

1. **Manifest adapters** normalize offer-side components (wrapper version + labeled members).
2. **Installed matcher** maps inventory to the same labels.
3. **Compare** per component; **rollup** worst member drives wrapper-row status when wrapper alone would say "same".
4. **Selective install** (existing 6.5.7 path) uses the same component map.

---

## Bundle classes (all in scope)

| Class | Manifest source | Installed signal | Notes |
|-------|-----------------|------------------|-------|
| AMD chipset | `Info.xml` / `DevID.xml` | Platform + plumbing INFs | `amd_chipset_manifest.py` |
| Intel chipset INF | INF/CAT metadata, ARP suite | Plumbing INFs | Adapter Phase 3 |
| Dell/HP/Lenovo DUP | DUP XML → `inner_versions` | Per-device INF | Extend merge coverage |
| OEM graphics multi-driver | DUP / package XML | `gpu_companion` rows | Thermal, NPCF, audio |
| Realtek combo OEM | OEM manifest | Media + net + APO rows | Cross-scheme labels |
| MS Catalog multi-HWID CAB | Catalog metadata | HWID inventory | Per-HWID effective version |
| AMD Adrenalin bundle refs | Vendor scrape + package | Display + companion | Do not confuse with chipset |

---

## Phases (runtime order = build order)

| Phase | ID | Deliverable | Status |
|-------|-----|-------------|--------|
| 1 | BV-1 | `bundle_verification.py` — compare, rollup, inner_versions → components | ☑ |
| 1 | BV-2 | `amd_chipset_manifest.py` — Info.xml parser (production) | ☑ |
| 1 | BV-3 | Chipset platform rollup wired (`catalog_chipset_comparison`, `catalog_multi_device`) | ☑ |
| 1 | BV-4 | `bundle_components` on all offers with `inner_versions` (`catalog_offer_compare`) | ☑ |
| 1 | BV-5 | Tests `tests/test_bundle_verification.py` | ☑ |
| 2 | BV-6 | AMD vendor fetch: download/cache manifest; attach `bundle_components` to AMD chipset vendor offer | ☑ |
| 2 | BV-7 | Generic wrapper-row rollup hook for non-chipset synthetic rows (OEM graphics bundle parent) | ☑ |
| 3 | BV-8 | Intel chipset manifest adapter + rollup | ☑ |
| 3 | BV-9 | Enterprise manifest (`catalog_oem_live`) — full inner_versions on all DUP rows | ☑ |
| 4 | BV-10 | Selective install generalization (DevID.xml / DUP tag → extract path) | ☑ |
| 4 | BV-11 | GUI component table + export + `driver_verification.py` narrative uses rollup | ☐ |
| 4 | BV-12 | Live probe scenario + Alienware fixture | ☐ |

---

## Modules

| Module | Role |
|--------|------|
| `bundle_verification.py` | Normalized compare + rollup (vendor-agnostic) |
| `amd_chipset_manifest.py` | AMD Info.xml / DevID.xml adapter |
| `intel_chipset_manifest.py` | Intel chipset INF DriverVer adapter |
| `catalog_intel_chipset_manifest.py` | Intel chipset package fetch/cache → `bundle_components` |
| `oem_effective_version.py` | PCI/ACPI inner version pick (extend, do not fork) |
| `catalog_chipset_comparison.py` | Platform row integration |
| `catalog_offer_compare.py` | Offer enrichment |
| `catalog_multi_device.py` | Device status from rollup |
| `bundle_selective_install.py` | DevID.xml / DUP tag / Intel INF → extract path for component install |
| `driver_install.py` | Selective component install (Phase 4) |

---

## Validation

| Tier | Command | When |
|------|---------|------|
| T1 | `py -3 tests\run_test_module.py tests\test_bundle_verification.py` | Each phase |
| T2 | `run_tests.bat` | Before done |
| T3 | `py -3 scripts\live_machine_probe.py --scan` (admin) | After BV-6+ on factory PC |

---

## Related docs

**Related (not pack scope):** Product plan in this repo only. Starter Pack handoff is a separate transfer file: **`AgentStarterPack_Audit_And_Rules_Upgrade_2026-09-05.md`** (filename only; USB/email — not in repo).
- Audit taxonomy: same file § AUDIT-* items
