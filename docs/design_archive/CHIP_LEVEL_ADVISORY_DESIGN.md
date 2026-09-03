> **Archived 2026-08-13** — Phase 8 RFC source only. **Backlog** — see ROADMAP § Backlog (parked). Do not implement B–F without user-approved RFC.
>
> **Canonical app path (2026):** BSODAnalyzer/ (repo). Desktop copy may remain for convenience.

# BSOD Analyzer — Extended Driver Sources & Chip-Level Updates (Design Reference)

**Document purpose:** Living design reference for optional chip-level / third-party driver discovery, verification, install, rollback, and related official-path work. **Update this file** as we discover fixes, methods, and policy changes. **Do not implement from this doc until the plan is signed off.**

**Created:** 2026-08-06  
**Last updated:** 2026-08-06  

**Motivating case:** MediaTek MT7921 Wi-Fi — installed `3.5.0.1392`; **IObit Driver Booster v13.5** reported `3.6.0.1434` (2026-07-01); BSOD Analyzer (official sources only) did not surface that version.

**Related context:** User suspects an early BSOD may have followed a **chipset/platform driver** installed via a third-party updater. Mitigation should be **validation before install**, **install journaling**, **crash correlation after**, and **rollback** — not blanket blocking for users who opt in.

**Canonical app path:** `BSODAnalyzer\` (repo). **`PROJECT_LAYOUT.md`** at repo root.

**Folder contract:** See repo root **`PROJECT_LAYOUT.md`** and **`docs/ROADMAP.md`** § Backlog.

---

## Table of contents

0. [Release & stable-build policy](#0-release--stable-build-policy)
1. [Executive summary](#1-executive-summary)
2. [Investigation recap (MT7921)](#2-investigation-recap-mt7921)
3. [Problem statement](#3-problem-statement)
4. [Product philosophy (revised)](#4-product-philosophy-revised)
5. [Architecture — source tiers](#5-architecture--source-tiers)
6. [Implementation phases (master plan)](#6-implementation-phases-master-plan)
7. [Opt-in consent & settings](#7-opt-in-consent--settings)
8. [Pre-install verification](#8-pre-install-verification)
9. [Install journal, rollback & crash correlation](#9-install-journal-rollback--crash-correlation)
10. [Scan performance vs verify/install UX](#10-scan-performance-vs-verifyinstall-ux)
11. [UX copy (draft)](#11-ux-copy-draft)
12. [Positives & negatives](#12-positives--negatives)
13. [Success criteria](#13-success-criteria)
14. [Effort sketch](#14-effort-sketch)
15. [Changelog](#15-changelog)
16. [Appendices](#16-appendices)

---

## 0. Release & stable-build policy

**User policy (2026-08-06) — agents and builds must follow:**

| Rule | Detail |
|------|--------|
| **No stable archive before field test** | Do **not** copy builds to `BSODAnalyzer_StableBuilds` until the user has tested the build on real hardware and signed off. |
| **Not every version gets a stable slot** | Minor/polish-only releases (e.g. “center app on launch”) do **not** need a stable archive. Reserve stable saves for **meaningful** releases (catalog behavior, crash UX, driver-source changes, etc.). |
| **CI build ≠ stable build** | `build_ci.bat` produces `BSODAnalyzer_v6\BSODAnalyzer.exe` for testing. Stable archive (`scripts\save_stable_build.bat`) is a **separate, manual** step after user approval. |
| **Max 3 stables** | `BSODAnalyzer_StableBuilds` holds only the **three most recent builds you have field-tested and approved**. Delete all others when promoting a new stable. |
| **Prune old stables** | Remove superseded or never-validated entries (e.g. v6.4.55 was archived before field test — remove until approved). |

**Agent note:** `build_and_deploy_v6.bat` currently auto-runs stable save — **change build scripts later** so stable archive is opt-in, not automatic on every CI build.

**Stable archive location:** `C:\Users\binar\OneDrive\Desktop\BSODAnalyzer_StableBuilds\`

---

## 1. Executive summary

| Layer | Default | Opt-in “Extended driver sources” |
|-------|---------|----------------------------------|
| **Discovery** | Manufacturer → OEM → Microsoft only | + Chip-level / curated third-party index |
| **Display** | Official status drives row color/Status column | + Separate “Extended” offers in inspector (and optional filter) |
| **Download / install** | Official packages only (existing flow) | User **may download and install through the app** after opt-in consent |
| **Safety** | Source-authoritative ranking | Verify pipeline + restore point + install journal + crash correlation |

**Phase A (official fixes only)** — **implemented in v6.4.55**, pending user field test. No third-party logic.

**Phases B–F (this doc)** — planned; **no code until plan approved.**

---

## 2. Investigation recap (MT7921)

| Source | Result |
|--------|--------|
| Installed | `3.5.0.1392` on `PCI\VEN_14C3&DEV_7961&SUBSYS_E0B7105B` |
| Microsoft Update Catalog | **No** `3.6.0.1434` |
| Windows Update (user machine) | 0 optional driver packages at time of probe |
| Dell service-tag OEM cache | MT7921 Wi-Fi up to **3.3.3.760** (below installed) |
| MediaTek.com | Legacy product page; no consumer download |
| Station-Drivers / Necacom | **3.6.0.1434**; **Officiel: non**; lists SUBSYS_E0B7105B |
| IObit Driver Booster 13.5 | HWID-wide private database; not Dell-validated |

**Root causes we missed official parity with Driver Booster:**

1. Third-party repacks outside our source model (by design pre–Phase B).
2. MSCatalog HWID-only batch query returned zero rows for `PCI\VEN_14C3&DEV_7961` → **fixed in Phase A** with name fallbacks.
3. Dell OEM rows rejected by `oem_radio_chip_mismatch` for MT7921 label format → **fixed in Phase A**.

---

## 3. Problem statement

- Users comparing us to **Driver Booster** see updates we don’t show.
- Official-only messaging (`coverage_gap`) is honest but incomplete when chip-level packages exist elsewhere.
- Users who **choose** to use extended sources should not face artificial friction (external browser-only, no install path) **after informed opt-in**.
- Users who **don’t** opt in keep today’s conservative behavior.
- **BSOD correlation** should improve when a driver update precedes crashes — install journal + rollback, not “never help.”

---

## 4. Product philosophy (revised)

### Default experience (unchanged trust)

- Official tiers set **authoritative** status (`Update available`, `Up to date`, `No official match`, etc.).
- Extended/third-party offers **never** overwrite official status in the Status column unless we later explicitly design a combined mode (not planned).

### Opt-in experience (user request — 2026-08-06)

> If the user enables extended driver sources, they should be able to **discover, download, and install** those packages **through BSOD Analyzer**. They opted in; we explain risks at enable time. **Don’t make it needlessly difficult** (no “link only” dead-end for opted-in users).

**Still required even when opted in:**

- Clear labeling (`Extended · unvalidated`, separate from OEM/Microsoft).
- Pre-install **verify** step (signature, INF/HWID) with readable results.
- **Restore point** prompt before install (or documented system restore guidance).
- **Install journal** entry (version, hash, device, timestamp, source URL).
- **Chipset/platform class:** stricter gates (extra warning, verify mandatory, optional block — see Section 8).

**Not the lesson from BSOD history:** “Never touch third-party.”  
**The lesson:** “Validate, record, correlate, rollback.”

---

## 5. Architecture — source tiers

```
Tier 0: Manufacturer (NVIDIA/AMD/Intel/Realtek/…)
Tier 1: OEM (Dell / service tag)
Tier 2: Microsoft (WU + MSCatalog)
───────────────────────────────────── authoritative → summarize_offer_status()

Tier 3: Extended / chip-level (OPT-IN ONLY)
  source: "extended" | "chip_advisory"
  trust: low → medium (after verify)
  feeds: separate offer list; optional Download / Verify / Install actions
  does NOT promote to tier-0..2 status
```

**Trigger Tier 3 discovery** (when setting ON):

- Network devices first (MediaTek, Qualcomm, Broadcom, Killer, Realtek Ethernet).
- After official scan completes OR in parallel **only for devices with `coverage_gap`** (keeps scan time down).
- **Exclude:** chipset/platform, standard inbox, scan-excluded firmware class.

---

## 6. Implementation phases (master plan)

### Phase A — Official-path fixes ✅ (code shipped v6.4.55, **not stable-approved**)

| Item | Status |
|------|--------|
| Fix `oem_radio_chip_mismatch` for MT7921-style labels | ✅ |
| `_mediatek_mscatalog_queries` batch fallbacks | ✅ |
| Coverage gap copy → “No official match — recheck” | ✅ |
| Dell OEM cache auto-refresh | Deferred (use Tools → Refresh driver database when stale) |

**Third-party?** **No.**

---

### Phase B — Extended source discovery (metadata + index)

**Goal:** Find chip-level packages; store metadata; no install yet.

| Step | Source | Notes |
|------|--------|-------|
| B1 | Extended MSCatalog name queries | Already partially done for MediaTek in Phase A |
| B2 | Curated `data/extended_driver_index.json` | Version, date, URL, HWIDs, `official: false`, source site; seed MT7921 / 3.6.0.1434 |
| B3 | Optional signed update feed later | Replace or augment static JSON |

**No live scraping** Station-Drivers in v1 (ToS/maintenance). Manual or agent-maintained index.

**Output:** `extended_offers[]` on device result + export.

---

### Phase C — Settings, consent UI, inspector display

**Goal:** Opt-in with explicit consent; show extended offers separately.

- Settings → **“Extended driver sources (chip-level / third-party)”** — default **OFF**.
- **First-enable dialog** (required) — full risk text (Section 7); user must confirm.
- Drivers inspector: section **“Extended sources (opt-in)”** below official offers.
- Optional filter: **“Extended only”** / badge on row.
- Export fields: `extended_sources_enabled`, `extended_offers[]`.

**Still no install** in Phase C — “Verify…” button disabled or hidden until Phase D.

---

### Phase D — Verify pipeline (on-demand, post-scan)

**Goal:** User clicks **Verify package** → download to temp → run checks (Section 8) → show report.

- Runs **after** catalog scan (user-initiated per offer).
- Progress UI: “Downloading…”, “Checking signature…”, “Reading INF…” — user is **active**, not idle waiting on scan.
- Results: safety tier S0–S5, pass/fail per check, recommendation (Install allowed / Not recommended / Blocked).
- Temp files cleaned up; optional “Open folder” for advanced users.

**Scan time impact:** **None** on default path; verify is per-offer async.

---

### Phase E — Download & install through app (opt-in only)

**Goal:** Opted-in users install from BSOD Analyzer, not external tools.

**Flow:**

1. User has extended sources **ON** + passed verify (or acknowledged skip for S3 with extra confirm).
2. Prompt: **Create restore point** (PowerShell / WMI / `rstrui` guidance if automation fails).
3. **Download** to controlled cache dir under portable settings (not random temp).
4. **Install** via existing driver install plumbing (`pnputil`, OEM EXE silent flags where safe) — extend as needed for repack EXE layout.
5. Write **install journal** record (Section 9).
6. Post-install: re-read installed version; update row.

**Chipset/platform:** Install button **disabled** for extended tier (S5) unless future explicit exception with signed OEM-only path — **default block**.

---

### Phase F — Crash correlation & rollback

**Goal:** If BSOD after an extended (or any catalog) install, help user understand and revert.

| Feature | Description |
|---------|-------------|
| **Install journal** | Persistent log: device, before/after version, package hash, source, tier, timestamp |
| **Crash correlation** | On Run Analysis, compare crash module/date to journal entries → “Possible link to driver X installed on DATE” |
| **Rollback** | Reinstall prior version from backup/journal if we cached package or driver store export; else guide to Device Manager → Roll Back Driver / restore point |
| **Forward path** | If rollback stale, suggest newer **official** offer if available |

Integrates with existing crash-link ⓘ UX on Drivers tab where applicable.

---

## 7. Opt-in consent & settings

### Setting keys (proposed)

| Key | Default | Purpose |
|-----|---------|---------|
| `gui_extended_driver_sources` | `false` | Master opt-in |
| `gui_extended_driver_sources_network_only` | `true` | Limit discovery scope |
| `gui_extended_install_require_verify` | `true` | Block install until verify pass (recommended) |
| `gui_extended_install_allow_verify_skip` | `false` | Expert: skip verify with extra confirm |

### First-enable dialog (draft — user must scroll + check box)

**Title:** Enable extended driver sources?

**Body (summary):**

- Shows drivers from **chip-level and third-party indexes**, not only Dell, Microsoft, and device vendors.
- Packages may **not be tested for your exact laptop model** even if they match your wireless chip ID.
- Some packages are **repacks** (e.g. community driver sites), not PC-maker releases.
- **Wrong drivers can cause crashes, Wi-Fi failure, or boot issues** — including chipset-related BSODs reported by other users.
- BSOD Analyzer will offer **verify checks** and **restore point** guidance before install.
- You can turn this off anytime; official driver scanning is unchanged.

**Checkbox:** “I understand and want to enable extended driver sources.”

**Buttons:** Enable / Cancel

---

## 8. Pre-install verification

Run in **Phase D** before Phase E install. See earlier tier table; **revised for opt-in install:**

| Tier | Install when opted in? |
|------|------------------------|
| **S0 Official** | Yes — existing path |
| **S1 MSCatalog weak match** | Optional updates / existing Microsoft path |
| **S2 Signed + SUBSYS INF match** | **Yes**, after verify + restore point prompt |
| **S3 Signed, DEV-only match** | **Yes**, with extra confirmation dialog |
| **S4 Unsigned / repack metadata** | **Verify must extract & sign-check**; if unsigned → **block in-app install**, link out only |
| **S5 Chipset / platform** | **Block in-app install** from extended tier always |

### Checks (automated)

- Authenticode / catalog signature  
- INF hardware ID vs device `DeviceID` (prefer SUBSYS)  
- Version consistency (INF vs claimed)  
- OS/arch match  
- Bundled devices in package (warn if BT/audio co-install)  
- Optional: hash match to MSCatalog if same version exists  

---

## 9. Install journal, rollback & crash correlation

### Journal record (JSON lines or SQLite under portable settings)

```json
{
  "id": "uuid",
  "timestamp": "ISO-8601",
  "device_name": "MediaTek Wi-Fi 6 MT7921 Wireless LAN Card",
  "device_id": "PCI\\VEN_14C3&DEV_7961&...",
  "installed_before": "3.5.0.1392",
  "installed_after": "3.6.0.1434",
  "source_tier": "extended",
  "source_label": "Station-Drivers index",
  "package_url": "https://...",
  "package_sha256": "...",
  "verify_tier": "S2",
  "restore_point_created": true,
  "backup_driver_path": "optional cached prior driver"
}
```

### Crash correlation logic (high level)

1. After Run Analysis, if new BSOD and minidump/module available:
2. Load journal entries from last N days.
3. If faulting module or crash-linked device matches journal device/driver family → surface in Crash tab + Drivers inspector.
4. Offer: **Roll back driver** | **Check for official update** | **Export timeline for support**.

### Rollback

- Prefer: driver already backed up via existing `driver_backup` flow before extended install.
- Fallback: Device Manager roll back + system restore instructions.
- Never silent rollback — user confirms.

---

## 10. Scan performance vs verify/install UX

| Stage | When | Time budget | User perception |
|-------|------|-------------|-----------------|
| **Official catalog scan** | Search driver catalogs | Keep **~4–7 min** baseline on ~142 devices | Background wait |
| **Extended discovery** | Only if opt-in; prefer `coverage_gap` devices + network class | +small (indexed metadata = fast; extra MSCatalog only if not cached) | Can show as second pass: “Checking extended sources…” |
| **Verify** | User clicks per offer | 30s–2 min | **Active** — progress steps |
| **Download + install** | User clicks Install | 1–5 min | **Active** — progress + restore point |

**Principle:** Don’t inflate mandatory scan time. Extended work is **opt-in** and mostly **user-triggered** after scan.

---

## 11. UX copy (draft)

**Extended offer row (opt-in):**

> **3.6.0.1434** · Extended (third-party index) · MT7921 · Not Dell-validated · [Verify] [Install]

**After verify:**

> Signed · INF matches your SUBSYS · Ready to install — restore point recommended

**Crash correlation:**

> A BSOD occurred **2 days after** installing **MediaTek WLAN 3.6.0.1434** (extended source). Consider rolling back or updating via Dell/Microsoft.

---

## 12. Positives & negatives

### Positives

- Parity with tools users already run (Driver Booster), without hiding options.
- Informed opt-in respects user agency.
- Verify + journal + rollback addresses BSOD concern constructively.
- Official path remains default and trustworthy.
- Scan time stays lean; heavy work is post-scan and user-driven.

### Negatives / risks

- Support burden if extended install breaks Wi-Fi.
- Index maintenance (JSON curation).
- Legal: link/download third-party files — don’t re-host; cache is user-initiated.
- Install EXE variability (repack layouts) — test matrix needed.
- Chipset mistakes are catastrophic — keep S5 block.
- Script change needed: stop auto stable archive on every build.

---

## 13. Success criteria

### Phase A (v6.4.55 — field test pending)

- [ ] MT7921 shows Dell OEM offers in inspector (not rejected).
- [ ] MSCatalog name fallbacks run in batch scan.
- [ ] “No official match — recheck” when appropriate.

### Phases B–F (future)

- [ ] Extended OFF: identical to post–Phase A official behavior.
- [ ] Extended ON: MT7921 shows 3.6.0.1434 in extended section with source label.
- [ ] Consent dialog on first enable; cannot enable without checkbox.
- [ ] Verify → Install works in-app for S2; S5 chipset blocked.
- [ ] Install journal written; crash analysis references recent install when relevant.
- [ ] Rollback path documented and functional for at least Wi-Fi case.
- [ ] Full driver scan time not regressed > ~10% with extended OFF.

---

## 14. Effort sketch

| Phase | Estimate | Depends on |
|-------|----------|------------|
| A | Done | Field test |
| B — Discovery index | 2–3 days | JSON schema, matching |
| C — Consent + UI | 2 days | B |
| D — Verify pipeline | 3–5 days | B, signing/INF tools |
| E — In-app install | 3–4 days | D, existing install flow |
| F — Journal + rollback + crash link | 3–5 days | E, crash export |
| Build script: stable opt-in | 0.5 day | User policy |
| **Total B–F** | **~3–4 weeks** incremental | Phased ship OK |

**Recommended ship order:** B → C → D → E → F (each shippable behind flags).

---

## 15. Changelog

| Date | Change |
|------|--------|
| 2026-08-06 | Initial doc (MT7921 / Driver Booster investigation) |
| 2026-08-06 | Phase A implemented in v6.4.55 (archived prematurely — see Section 0) |
| 2026-08-06 | **Major revision:** stable-build policy; opt-in install through app; Phases B–F; install journal & crash correlation; scan vs verify UX; philosophy reframed (validate/rollback, not block) |

---

## 16. Appendices

### Appendix A — Conversation audit (topics that belong in this doc)

| Topic | In doc? | Section |
|-------|---------|---------|
| MT7921 / 3.5.0.1392 vs 3.6.0.1434 | ✅ | §2 |
| IObit Driver Booster v13.5 comparison | ✅ | §2, §3 |
| Station-Drivers / Necacom as source | ✅ | §2, §6-B |
| Phase A official-only fixes | ✅ | §6-A |
| `oem_radio_chip_mismatch` bug | ✅ | §6-A |
| MSCatalog HWID blind spot | ✅ | §6-A |
| Coverage gap / official-only messaging | ✅ | §6-A |
| Opt-in extended sources | ✅ | §4, §7 |
| Download + install **through app** when opted in | ✅ | §4, §6-E |
| Consent dialog at enable | ✅ | §7 |
| Pre-install verification | ✅ | §8 |
| Install journal | ✅ | §9 |
| Rollback | ✅ | §9 |
| Crash correlation after update | ✅ | §6-F, §9 |
| Chipset BSOD — stricter gates, not blanket ban | ✅ | §4, §8 |
| Scan time vs post-scan verify | ✅ | §10 |
| Stable archive only after test; no minor-version hoarding | ✅ | §0 |
| No code until plan settled | ✅ | Header, §6 |
| Positives/negatives of advisory tier | ✅ | §12 |
| Safety tiers S0–S5 | ✅ | §8 |
| MSCatalog parallel / batched queries (perf) | ✅ | §10 (unchanged official path) |
| Dell OEM cache stale — Refresh DB | ✅ | §6-A |
| WU empty on user machine | ✅ | §2 |
| MediaTek vendor page no download | ✅ | §2 |
| **Not in this doc** (separate workstreams) | | |
| Crash-link ⓘ tooltip Option E | — | Drivers UX mockups / shipped 6.4.53+ |
| Firmware tab mirror Run Analysis | — | Firmware inventory work / 6.4.54 |
| Filter combo chevron / Needs attention filter | — | Separate UX backlog |
| Removing auto stable save from `build_ci.bat` | ⚠️ | §0 noted; **implement when touching build scripts** |

### Appendix B — Related code (when implementation starts)

- `driver_catalog.py` — tiers, offers, verify hooks
- `gui_mixin_drivers.py` — inspector, install flow
- `driver_backup.py` — pre-install backup
- `scripts/save_stable_build.bat` — stable policy
- `build_and_deploy_v6.bat` — remove auto stable save
- Desktop doc: this file

### Appendix C — Open questions

- [ ] Ship `extended_driver_index.json` in repo vs signed remote feed?
- [ ] Allow extended discovery for Bluetooth in same repack as Wi-Fi?
- [ ] Expert mode: skip verify with typed confirmation?
- [ ] How long to retain install journal (30 / 90 / unlimited days)?
- [ ] Prune v6.4.55 from StableBuilds until field-tested?
- [ ] Rename feature in UI: “Extended sources” vs “Chip-level updates” vs “Third-party index”?

---

*End of document — edit freely as the project evolves.*
