"""Set VERSION in bsod_analyzer.py and root VERSION.txt for v5 or v6 builds.

Canonical runtime version: bsod_analyzer.VERSION
VERSION.txt is derived — do not edit by hand; use apply_version.py or run_tests.bat (auto-sync).

  py -3 scripts/apply_version.py 6.0.21   # bump + preset highlights
  py -3 scripts/apply_version.py sync      # align VERSION.txt (+ dist) to bsod_analyzer.VERSION
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRESETS = {
    "5": ("5.4.13", "AMD vendor icon — user-approved reference PNG (no other v5 changes)"),
    "5.4.13": ("5.4.13", "AMD vendor icon — user-approved reference PNG (no other v5 changes)"),
    "6": ("6.0.0", "v6 — driver catalog overhaul (MSCatalogLTS, accuracy, scrapers)"),
    "6.0.0": ("6.0.0", "v6 — driver catalog overhaul (MSCatalogLTS, accuracy, scrapers)"),
    "6.0.1": ("6.0.1", "v6 Batch 2 — Realtek download-center scraper (audio, PCIe/USB Ethernet)"),
    "6.0.2": ("6.0.2", "v6 Batch 3 — Killer, Broadcom, Qualcomm, MediaTek network vendor scrapers"),
    "6.0.3": ("6.0.3", "v6 Batch 4 — OEM API depth (HP WCC), source conflict UI, cache freshness UX"),
    "6.0.4": ("6.0.4", "v6 Batch 5 — WU COM depth, MSCatalog INF metadata, per-HWID online store, stale DB prompt"),
    "6.0.5": ("6.0.5", "v6 Batch 6 — Marvell, Synaptics/Elan, Logitech/Samsung/TP-Link/NETGEAR scrapers + Intel DSA/AMD family"),
    "6.0.6": ("6.0.6", "v6 Batch 7 — scan mode clarity, uncertain inspector, firmware fusion pipeline, SSD MSCatalog/OEM depth"),
    "6.0.14": ("6.0.14", "Realtek UAD Microsoft Update Catalog search — role-aware queries, HWID gates, WDM vs APO filtering"),
    "6.0.15": ("6.0.15", "OEM per-device matching gates — stop GPU packages on unrelated devices; Drivers tab layout rebalance"),
    "6.0.16": ("6.0.16", "Fix OEM session cache poisoning + batch chipset installed version from registry"),
    "6.0.17": ("6.0.17", "Audit batch — cache identity, OEM session all vendors, chipset pipeline parity, status fixes"),
    "6.0.18": ("6.0.18", "Catalog medium fixes — session persist, export debug fields, chipset PnP anchor, stale detection"),
    "6.0.19": ("6.0.19", "Close catalog audit — tests, docs, Drivers/Firmware splitter min heights"),
    "6.0.20": ("6.0.20", "Catalog limitation mitigations — cache identity, partial OEM, portable per-unit cache"),
    "6.0.21": ("6.0.21", "Fix GUI Not Responding — no sync catalog WMI on UI thread during Search/tab switch"),
    "6.0.22": ("6.0.22", "Drivers/Firmware UX — tab layout, chipset version, hide crash banner on catalog tabs"),
    "6.0.23": ("6.0.23", "Package table equal-thirds columns; taller inspector pane at default window size"),
    "6.0.24": ("6.0.24", "Move Download/Install driver actions to bottom toolbar on Drivers tab"),
    "6.0.25": ("6.0.25", "Footer toolbar — catalog Download/Install at end of row so core buttons stay fixed"),
    "6.0.26": ("6.0.26", "Drivers/Firmware device list — narrow Installed column, wider Status, Device stretches"),
    "6.0.27": ("6.0.27", "Driver updates without Run Analysis — hardware scan + Refresh device list standalone"),
    "6.0.28": ("6.0.28", "Drivers tab equal-thirds layout; fixed in-tab progress bar on catalog tabs"),
    "6.0.29": ("6.0.29", "Resizable catalog panes/columns; Firmware tab mirrors Drivers layout"),
    "6.0.30": ("6.0.30", "Search workflow feedback, chipset in driver-only list, column/package layout fixes"),
    "6.0.34": (
        "6.0.34",
        "Manufacturer lookup health — flag broken APIs, user-approved repair to settings file only (no exe changes)",
    ),
    "6.1.0": (
        "6.1.0",
        "v6.1 — one-click manufacturer lookup repair, fix-progress after BSOD, Intel chipset scrape depth, live API health",
    ),
    "6.1.2": (
        "6.1.2",
        "Realtek Dell OEM + MSCatalog depth — NIC 1125→1168 family, stale OEM refresh, UAD 6.0.x (incl. 9986) discovery",
    ),
    "6.1.3": (
        "6.1.3",
        "Drivers/Firmware workflow UX — ① Load / ② Search gating, All devices default, firmware off Drivers tab, Needs attention after driver crash only",
    ),
    "6.1.4": (
        "6.1.4",
        "Catalog accuracy — Realtek/AMD OEM rejects, NIC status rollup, coverage-gap flag, Alienware golden fixture, primary-device Search queue",
    ),
    "6.1.5": (
        "6.1.5",
        "Fix coverage-gap false positives, AMD component vs suite version compare, SMBUS chipset OEM reject, Realtek display name",
    ),
    "6.1.6": (
        "6.1.6",
        "Unified export (choose files, all selected by default), driver-only export without Run Analysis, OEM reject on foreign USB/peripheral devices via manufacturer + brand alignment",
    ),
    "6.1.7": (
        "6.1.7",
        "Export dialog checkmarks match Include columns; fix catalog export thread staying active after save",
    ),
    "6.1.8": (
        "6.1.8",
        "Python 3.14 build; PowerShell 7 optional upgrade prompt + parallel PnP parent lookup; OEM/catalog accuracy (Dell Update reject, vendor icons, verified PnP parent notes)",
    ),
    "6.1.9": (
        "6.1.9",
        "Realtek audio Updates list restored (MS Catalog WDM trust); reject Airplane Mode on monitors; Dell Realtek HD on codec row not inbox HD controller",
    ),
    "6.2.0": (
        "6.2.0",
        "Opus — parallel Microsoft Update Catalog searches (one PowerShell process, pwsh 7 ForEach-Object -Parallel) replacing serialized per-query subprocesses; large catalog-scan speed-up with automatic sequential fallback",
    ),
    "6.2.1": (
        "6.2.1",
        "Opus fixes — parallel MSCatalog no longer returns 0 results (warning-stream pollution broke JSON parsing; now suppressed + sentinel-wrapped, never poisons the cache); chunked progress ends the catalog-phase visual hang; AMD PSP suite-vs-component comparison reads Uncertain (not a false update); Realtek audio keeps name-based UAD catalog queries; Drivers/Firmware Device column stretches widest (Installed > Status)",
    ),
    "6.2.4": (
        "6.2.4",
        "Opus — HWID-verified coverage-gap catalog pass: devices left with zero offers after the normal sources get one automatic, name-based Microsoft Update Catalog search, surfacing ONLY hardware-ID-verified matches (fills gaps on non-OEM/no-scraper hardware with no false positives, no user action). Internal cleanup: single canonical is_hwid_search predicate shared across the single-search, batch, and query-builder paths.",
    ),
    "6.2.5": (
        "6.2.5",
        "Firmware tab — fix BIOS vs SSD catalog misclassification (Dell storage packages no longer shown as BIOS); stricter retail SSD model matching; reject MSCatalog inbox Samsung firmware-driver rows; honest SSD coverage-gap / Verify manually when vendor compare fails; Firmware tab Verify manually filter; OEM date normalization (February 0 fix).",
    ),
    "6.2.6": (
        "6.2.6",
        "Firmware tab — secondary USB/peripheral tier: multi-vendor support-site search (Razer/Logitech/Corsair/SteelSeries/Elgato); USB product hints resolve generic HID names; PnP firmware property + vendor-app cache + user-confirmed installed version; Secondary (USB / PnP) filter and Set installed firmware on Firmware tab.",
    ),
    "6.2.7": (
        "6.2.7",
        "Portable-first UX — silent portable default on first launch (no install-mode dialog); stale DB tab prompt off in portable; block driver Search during Tools refresh (and vice versa); PowerShell 7 prompt before driver/firmware Search (~5× faster with pwsh); dependencies cheatsheet doc.",
    ),
    "6.2.8": (
        "6.2.8",
        "Firmware tab parity with Drivers — fix icon/Include column rendering (no selection tint bleed); add Search by name filter; stable Include defaults (BIOS/SSD checked, secondary unchecked); Available packages heading aligned.",
    ),
    "6.2.9": (
        "6.2.9",
        "Drivers/Firmware tab layout parity — shared splitter and column widths (no jump when switching tabs); dark-theme checkbox/selection styling; cleaner package labels (no v—); deduped UEFI names; Not reported for missing firmware revision.",
    ),
    "6.2.10": (
        "6.2.10",
        "Restore native Include checkmarks; firmware select-all defaults; independent Load components (auto hardware scan); consistent inspector/packages pane; Logitech icons from USB VID.",
    ),
    "6.2.11": (
        "6.2.11",
        "Remove white focus box on icon/Include columns (table delegate); export defaults to Desktop (OneDrive-aware) with folder open button and write check.",
    ),
    "6.2.12": (
        "6.2.12",
        "Export files flush to disk immediately (fsync + Explorer refresh); fix deferred export writes when closing during async export.",
    ),
    "6.2.13": (
        "6.2.13",
        "Firmware Tier 1 — hide redundant UEFI rows when BIOS exists; structured G HUB/Razer app readers; MX Keys release-notes article; verify-in-vendor-app UX and Confirm firmware version.",
    ),
    "6.2.14": (
        "6.2.14",
        "Fix Logitech USB PID map — 046d:c081 is G900 mouse (not MX Keys); MX Keys uses 046d:408a.",
    ),
    "6.2.15": (
        "6.2.15",
        "Fix Firmware Search button staying disabled after Load components — reset Include defaults on reload and unify enable logic.",
    ),
    "6.2.20": (
        "6.2.20",
        "3C catalog layout default — 1280×960 window, 12px content typography, banner hidden on Drivers/Firmware.",
    ),
    "6.2.21": (
        "6.2.21",
        "Catalog table grid lines, tighter tab chrome, firmware Installed row fix, richer session log timestamps.",
    ),
    "6.2.22": (
        "6.2.22",
        "Default window 1536×960 (16:10 aspect ratio).",
    ),
    "6.2.23": (
        "6.2.23",
        "Unified catalog row colors on Drivers and Firmware — green update tint, red culprit, no amber split.",
    ),
    "6.2.24": (
        "6.2.24",
        "Catalog rows: amber = update available, green = up to date; status Up to date text green.",
    ),
    "6.2.25": (
        "6.2.25",
        "View menu — Night (dark) and Day (light) appearance; theme persists in settings.",
    ),
    "6.2.26": (
        "6.2.26",
        "View → Manly mode — bold pastel palette (lavender, peach, mint, rose row tints).",
    ),
    "6.2.27": (
        "6.2.27",
        "Fix Manly mode driver scan — row styling reads live gui_theme tokens at runtime.",
    ),
    "6.2.28": (
        "6.2.28",
        "Theme refresh — severity meter, compare table, summary HTML, and action links use live palette.",
    ),
    "6.2.29": (
        "6.2.29",
        "Pre-compile hygiene — block export during catalog search; themed data-gap warnings; row a11y text.",
    ),
    "6.2.30": (
        "6.2.30",
        "Wider Installed column (Drivers/Firmware match); OneDrive Desktop export refresh.",
    ),
    "6.2.31": (
        "6.2.31",
        "Export scan duration in JSON/text summaries; firmware catalog session timing.",
    ),
    "6.2.32": (
        "6.2.32",
        "OEM audio noise cleanup, catalog table a11y (icon/Include), export index gap detail.",
    ),
    "6.2.33": (
        "6.2.33",
        "Unified Install driver flow (internal milestone before 6.3.0 packaging).",
    ),
    "6.3.0": (
        "6.3.0",
        "v6.3 — unified Install driver (catalog download, pnputil/WU/vendor launcher), export timing, catalog a11y/index.",
    ),
    "6.3.1": (
        "6.3.1",
        "Persist downloaded driver package path on package rows — skip re-download on install retry.",
    ),
    "6.4.0": (
        "6.4.0",
        "v6.4 — driver backup/restore library, install safeguards, Tools → Driver backups, Microsoft logo fix.",
    ),
    "6.4.1": (
        "6.4.1",
        "Two-tone theme-aware checkbox ticks (fill + border + check) on Night, Day, and Manly; future-theme fallbacks.",
    ),
    "6.4.2": (
        "6.4.2",
        "Two-tone checkboxes on Drivers/Firmware Include columns and all QCheckBox/QAbstractItemView indicators app-wide.",
    ),
    "6.4.11": (
        "6.4.11",
        "Option 4 catalog chrome (filter tray, accent borders, unified tables); NVIDIA/AMD branch compare for installed driver tier; invalidate installed-version cache on refresh.",
    ),
    "6.4.12": (
        "6.4.12",
        "C4 app icon (lens + chip + bug) — themed window/taskbar icon for Night, Day, and Manly; Night .ico baked into BSODAnalyzer.exe.",
    ),
    "6.4.13": (
        "6.4.13",
        "C4 app icon now uses approved gallery artwork (logo_concept_C4_lens_chip_bug_themes.png) instead of placeholder vector.",
    ),
    "6.4.14": (
        "6.4.14",
        "Icon padding fix; Day/Manly catalog row selection uses theme TABLE_SELECTION; Option 4 catalog chrome QSS applied.",
    ),
    "6.4.15": (
        "6.4.15",
        "Fix startup crash after UAC (include-header + Fusion table style); admin relaunch sets exe working directory.",
    ),
    "6.4.16": (
        "6.4.16",
        "Fix Day/Manly catalog zebra rows (explicit CARD/CARD_ALT per row); restore Option 4 chrome by removing card QSS override.",
    ),
    "6.4.17": (
        "6.4.17",
        "Catalog hover uses accent tint (not selection blue); update/up-to-date rows use readable TEXT; solid green for up-to-date on all themes.",
    ),
    "6.4.18": (
        "6.4.18",
        "Visible search field border; accent list/inspector page break; compare-table grid on Day/Manly; modern flat scrollbars.",
    ),
    "6.5.0": (
        "6.5.0",
        "v6.5 maintainability milestone — catalog/crash/orchestration module splits, facade decouple (124 exports), agent validation gates, portable build",
    ),
    "6.5.1": (
        "6.5.1",
        "Fix Run Analysis (_parse_json_date) and firmware tab (driver_catalog._slug_for_oem_api re-export)",
    ),
    "6.5.2": (
        "6.5.2",
        "Fix module-split regressions: crash_report_format imports, catalog progress, facade re-exports",
    ),
    "6.5.3": (
        "6.5.3",
        "Complete crash_report_format peel fixes (verified frozen --cli); clean PyInstaller rebuild",
    ),
    "6.5.4": (
        "6.5.4",
        "Fix driver package row click (staticmethod self bug in _format_catalog_package_label)",
    ),
    "6.5.5": (
        "6.5.5",
        "Filter ACC suite from Dell internal nodes; LG SWC WU offer on monitor only",
    ),
    "6.5.6": (
        "6.5.6",
        "Catalog device roles from inventory; WU update_id dedup + parent/child assignment",
    ),
    "6.5.7": (
        "6.5.7",
        "Component-targeted OEM bundle install; per-device ACPI inner version; bundle UX messages",
    ),
    "6.5.8": (
        "6.5.8",
        "Test harness trust (pytest discovery + pyflakes gate); WU offers for attached devices; "
        "event-time UTC fix; Firmware Download + Activity history + MSI support link; MSCatalog cache drift fix",
    ),
    "6.5.10": (
        "6.5.10",
        "Manly mode — richer lavender window/card chrome (less gray vs Day)",
    ),
    "6.5.24": (
        "6.5.24",
        "Audit Improve — dedicated tests for LRU/minidump/action-plan/log modules; doc scale sync; remove dead winget SDK install path; portable rebuild.",
    ),
    "6.5.25": (
        "6.5.25",
        "Drivers tab — auto-load after analysis, global progress bar on catalog tabs, unified status mirroring during Run Analysis and catalog work; reuse analysis driver inventory (no duplicate WMI scan).",
    ),
    "6.5.26": (
        "6.5.26",
        "Catalog progress bar — full-width alignment with Driver/Firmware cards; rounded pill styling (8px) matching tab chrome.",
    ),
    "6.5.27": (
        "6.5.27",
        "Summary/Action header progress — full-width rounded bar with caption; log-analysis scope only (100% before driver/firmware tab work); post-analysis device load quiet on banner tabs.",
    ),
}


def apply(version: str, highlights: str) -> None:
    core = ROOT / "bsod_analyzer.py"
    text = core.read_text(encoding="utf-8")
    text, n = re.subn(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"Could not update VERSION in {core}")
    core.write_text(text, encoding="utf-8")

    from datetime import date

    today = date.today().isoformat()
    major = version.split(".")[0]
    body = (
        f"BSOD Analyzer v{version}\n\n"
        f"====================\n\n"
        f"Release date: {today}\n\n"
        f"Version: {version}\n\n"
        f"Distribution folder: BSODAnalyzer_v{major}\\\n\n"
        f"v{version} highlights:\n\n"
        f"- {highlights}\n"
    )
    (ROOT / "VERSION.txt").write_text(body, encoding="utf-8")
    print(f"Applied version {version}")


def read_source_version() -> str:
    core = ROOT / "bsod_analyzer.py"
    text = core.read_text(encoding="utf-8")
    m = re.search(r'^VERSION = "([^"]+)"', text, re.M)
    if not m:
        raise SystemExit(f"Could not read VERSION from {core}")
    return m.group(1)


def parse_version_txt(text: str) -> str | None:
    for line in text.splitlines():
        m = re.search(r"Version:\s*(\d+\.\d+\.\d+)", line, re.I)
        if m:
            return m.group(1)
    m = re.search(r"v(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else None


def read_version_txt() -> str | None:
    path = ROOT / "VERSION.txt"
    if not path.is_file():
        return None
    return parse_version_txt(path.read_text(encoding="utf-8"))


def sync_distribution_artifacts(version: str) -> None:
    """Copy VERSION.txt and README into BSODAnalyzer_v* when that folder exists."""
    major = version.split(".")[0]
    dist = ROOT / f"BSODAnalyzer_v{major}"
    if not dist.is_dir():
        return
    src_ver = ROOT / "VERSION.txt"
    if src_ver.is_file():
        shutil.copy2(src_ver, dist / "VERSION.txt")
    try:
        from sync_dist_readme import sync_dist_readme
    except ImportError:
        sys.path.insert(0, str(ROOT / "scripts"))
        from sync_dist_readme import sync_dist_readme  # type: ignore[no-redef]
    sync_dist_readme(dist)


def sync_from_source() -> None:
    """Align VERSION.txt (and dist copies) to bsod_analyzer.VERSION without bumping the code version."""
    ver = read_source_version()
    on_disk = read_version_txt()
    if on_disk == ver:
        print(f"Version {ver} already synced (VERSION.txt matches bsod_analyzer.py)")
    else:
        note = PRESETS.get(ver, (ver, f"BSOD Analyzer v{ver}"))[1]
        apply(ver, note)
    sync_distribution_artifacts(ver)


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "sync":
        sync_from_source()
        return
    if len(sys.argv) != 2 or sys.argv[1] not in PRESETS:
        opts = ", ".join(sorted(PRESETS)) + ", sync"
        raise SystemExit(f"Usage: apply_version.py [{opts}]")
    ver, note = PRESETS[sys.argv[1]]
    apply(ver, note)


if __name__ == "__main__":
    main()
