"""
BIOS/UEFI and device-firmware discovery for OEM laptops and DIY motherboards.
Download-only — never flashes firmware from this tool.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

import driver_catalog as dc

try:
    from bsod_hardware_wmi import _parse_json_date, get_ssd_firmware_inventory
    from bsod_crash_report import _system_manufacturer_oem_url
except ImportError:
    _parse_json_date = lambda s: s or ""  # type: ignore[assignment, misc]
    _system_manufacturer_oem_url = lambda _ctx: None  # type: ignore[assignment, misc]
    get_ssd_firmware_inventory = lambda: []  # type: ignore[assignment, misc]

_FIRMWARE_KEYWORDS = (
    "bios",
    "uefi",
    "firmware",
    "system firmware",
    "embedded controller",
    " ec ",
    "capsule",
    "microcode",
    "me firmware",
    "intel me",
    "amd agesa",
    "agesa",
    "flash",
)

_UTILITY_KEYWORDS = (
    ("samsung", "Samsung Magician (SSD firmware)", "https://semiconductor.samsung.com/consumer-storage/magician/"),
    ("western digital", "WD Dashboard (SSD firmware)", "https://support-en.wd.com/downloads.aspx"),
    ("wd ", "WD Dashboard (SSD firmware)", "https://support-en.wd.com/downloads.aspx"),
    ("crucial", "Crucial Storage Executive", "https://www.crucial.com/support/storage-executive"),
    ("micron", "Micron Storage Executive", "https://www.micron.com/support/ssd-storage-support"),
    ("intel", "Intel SSD tools", "https://www.intel.com/content/www/us/en/support/articles/000005910/memory-and-storage.html"),
    ("sk hynix", "SK hynix SSD firmware", "https://www.skhynix.com/ssd/"),
    ("sandisk", "SanDisk SSD Dashboard", "https://support-en.sandisk.com/downloads.aspx"),
    ("kingston", "Kingston SSD Manager", "https://www.kingston.com/en/support/technical/ssdmanager"),
)

_FIRMWARE_WARNINGS = [
    "Firmware updates can brick your PC if interrupted. Use AC power, do not restart during the update.",
    "Install BIOS/UEFI only with the manufacturer's utility or instructions. BSOD Analyzer never flashes firmware.",
    "Create a restore point and back up important data before updating BIOS.",
]


def _fetch_vendor_page_html(url: str) -> tuple[bool, str]:
    """HTTP GET with WAF retry and optional headless-browser fallback."""

    try:
        import vendor_firmware_fetch as vff

        ok, body, _method = vff.fetch_html_with_js_fallback(url)
        return ok, body
    except ImportError:
        pass

    def _get(target: str) -> tuple[bool, str]:
        return dc._http_get(
            target,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )

    try:
        import vendor_page_render as vpr
    except ImportError:
        return _get(url)
    ok, body, _method = vpr.fetch_html_with_js_fallback(url, _get, allow_js=True)
    return ok, body


def is_firmware_catalog_row(row: dict) -> bool:
    """True if an OEM catalog row looks like BIOS/UEFI/firmware (not a regular driver)."""
    blob = f"{row.get('title', '')} {row.get('category', '')}".lower()
    if any(kw in blob for kw in _FIRMWARE_KEYWORDS):
        return True
    if re.search(r"\b(bios|uefi)\b", blob):
        return True
    return False


def is_storage_firmware_title(row: dict) -> bool:
    """True when an OEM row is SSD/drive firmware — not motherboard BIOS/UEFI."""
    blob = f"{row.get('title') or ''} {row.get('category') or ''}".lower()
    if not blob.strip():
        return False
    storage_hints = (
        "solid state drive",
        " ssd ",
        "ssd firmware",
        "nvme",
        "hard drive",
        "hard disk",
        " hdd",
        "drive firmware update for",
        "storage drive",
    )
    if any(h in blob for h in storage_hints):
        return True
    if "firmware" in blob and any(k in blob for k in ("ssd", "nvme", "solid state")):
        return True
    if re.search(r"\b(drive|disk)\s+firmware\b", blob):
        return True
    return False


def is_bios_catalog_row(row: dict) -> bool:
    """True for motherboard/system BIOS/UEFI packages — excludes storage drive firmware."""
    return is_firmware_catalog_row(row) and not is_storage_firmware_title(row)


_SSD_MODEL_GENERIC_TOKENS = frozenset({
    "samsung",
    "western",
    "digital",
    "solid",
    "state",
    "disk",
    "drive",
    "nvme",
    "pci",
    "express",
    "series",
    "brand",
    "ssd",
    "intel",
    "micron",
    "crucial",
    "kingston",
    "sandisk",
    "wd",
    "wdc",
    "tb",
    "gb",
})


def _ssd_model_match_tokens(model: str) -> list[str]:
    """Distinctive model tokens — exclude vendor/size words that match wrong OEM SKUs."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", (model or "").lower()) if len(t) >= 3]
    distinctive = [t for t in tokens if t not in _SSD_MODEL_GENERIC_TOKENS]
    strong = [t for t in distinctive if len(t) >= 4]
    if strong:
        return strong[:6]
    return distinctive[:4]


def _offer_from_row(
    row: dict,
    source_label: str,
    installed_version: str,
    *,
    kind: str = "bios",
    notes: str = "",
) -> dict:
    title = (row.get("title") or "Firmware")[:120]
    ver = (row.get("version") or "").strip() or dc.extract_version_from_text(title)
    return {
        "source": "oem_firmware",
        "source_label": source_label,
        "title": title,
        "version": ver,
        "date": dc._normalize_oem_date(row.get("date") or ""),
        "url": (row.get("url") or "").strip(),
        "download_kind": "url",
        "vs_installed": dc.compare_firmware_versions(installed_version, ver, title=title),
        "notes": notes or _FIRMWARE_WARNINGS[1],
        "kind": kind,
        "confidence": "high" if ver else "medium",
    }


def _collect_oem_firmware_rows(
    system_ctx: dict,
    progress: Callable[[str], None] | None = None,
) -> list[tuple[str, dict, str]]:
    """Query applicable OEM APIs/pages for BIOS/firmware rows."""
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb_mfr = (ctx.get("baseboard_manufacturer") or "").lower()
    tasks: list[tuple[str, Callable[[], tuple[list[dict], str]]]] = []

    def add(label: str, fn: Callable[[], tuple[list[dict], str]]) -> None:
        tasks.append((label, fn))

    if "dell" in mfr or "alienware" in mfr:
        add("Dell", lambda: dc.get_dell_oem_rows(ctx))
    if any(x in mfr for x in ("lenovo", "thinkpad", "ideapad")):
        add("Lenovo", lambda: dc.get_lenovo_oem_rows(ctx))
    if "hp" in mfr or "hewlett" in mfr:
        add("HP", lambda: dc.get_hp_oem_rows(ctx))
    if dc._manufacturer_matches(mfr, "asus", "rog") or dc._manufacturer_matches(bb_mfr, "asus"):
        add("ASUS", lambda: dc.get_asus_oem_rows(ctx))
    if dc._manufacturer_matches(mfr, "msi", "micro-star") or dc._manufacturer_matches(bb_mfr, "msi"):
        add("MSI BIOS", lambda: dc.get_msi_oem_rows(ctx, catalog_type="bios"))
        add("MSI", lambda: dc.get_msi_oem_rows(ctx, catalog_type="driver"))
    if dc._manufacturer_matches(mfr, "gigabyte") or dc._manufacturer_matches(bb_mfr, "gigabyte"):
        add("Gigabyte BIOS", lambda: dc.get_gigabyte_bios_rows(ctx))
    if dc._manufacturer_matches(mfr, "acer"):
        add("Acer BIOS", lambda: dc.get_acer_bios_rows(ctx))

    collected: list[tuple[str, dict, str]] = []

    def work(item: tuple[str, Callable[[], tuple[list[dict], str]]]) -> list[tuple[str, dict, str]]:
        label, fn = item
        rows, fallback = fn()
        out: list[tuple[str, dict, str]] = []
        for row in rows:
            if not is_bios_catalog_row(row):
                continue
            r = dict(row)
            if not r.get("url"):
                r["url"] = fallback
            out.append((label, r, fallback))
        return out

    if not tasks:
        return collected

    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as ex:
        futures = {ex.submit(work, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            name = futures[fut]
            if progress:
                progress(f"Finished {name} firmware catalog…")
            try:
                collected.extend(fut.result())
            except Exception:
                continue
    return collected


def _collect_oem_storage_firmware_rows(
    ctx: dict,
    progress: Callable[[str], None] | None = None,
) -> list[tuple[str, dict, str]]:
    """OEM rows that look like SSD/storage firmware (E25 — extended OEM coverage)."""
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb_mfr = (ctx.get("baseboard_manufacturer") or "").lower()
    tasks: list[tuple[str, Callable[[], tuple[list[dict], str]]]] = []

    def add(label: str, fn: Callable[[], tuple[list[dict], str]], match: bool) -> None:
        if match:
            tasks.append((label, fn))

    add("Dell", lambda: dc.get_dell_oem_rows(ctx), "dell" in mfr or "alienware" in mfr)
    add(
        "Lenovo",
        lambda: dc.get_lenovo_oem_rows(ctx),
        any(x in mfr for x in ("lenovo", "thinkpad", "ideapad")),
    )
    add("HP", lambda: dc.get_hp_oem_rows(ctx), "hp" in mfr or "hewlett" in mfr)
    add(
        "ASUS",
        lambda: dc.get_asus_oem_rows(ctx),
        dc._manufacturer_matches(mfr, "asus", "rog")
        or dc._manufacturer_matches(bb_mfr, "asus"),
    )
    add(
        "MSI",
        lambda: dc.get_msi_oem_rows(ctx),
        dc._manufacturer_matches(mfr, "msi", "micro-star")
        or dc._manufacturer_matches(bb_mfr, "msi"),
    )
    add(
        "Gigabyte",
        lambda: dc.get_gigabyte_bios_rows(ctx),
        dc._manufacturer_matches(mfr, "gigabyte")
        or dc._manufacturer_matches(bb_mfr, "gigabyte"),
    )
    add("Acer", lambda: dc.get_acer_bios_rows(ctx), dc._manufacturer_matches(mfr, "acer"))

    collected: list[tuple[str, dict, str]] = []
    if not tasks:
        return collected

    def work(item: tuple[str, Callable[[], tuple[list[dict], str]]]) -> list[tuple[str, dict, str]]:
        label, fn = item
        rows, fallback = fn()
        out: list[tuple[str, dict, str]] = []
        for row in rows:
            if not is_storage_firmware_row(row, ""):
                continue
            r = dict(row)
            if not r.get("url"):
                r["url"] = fallback
            out.append((label, r, fallback))
        return out

    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as ex:
        futures = {ex.submit(work, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            name = futures[fut]
            if progress:
                progress(f"Finished {name} storage firmware catalog…")
            try:
                collected.extend(fut.result())
            except Exception:
                continue
    return collected


def is_storage_firmware_row(row: dict, model: str) -> bool:
    """True if OEM row looks like SSD/storage firmware for this drive model."""
    title = (row.get("title") or "").lower()
    cat = (row.get("category") or "").lower()
    blob = f"{title} {cat}"
    if not any(k in blob for k in ("firmware", "ssd", "nvme", "storage", "solid state", "hdd")):
        if "firmware" not in title:
            return False
    if not (model or "").strip():
        return any(
            k in blob
            for k in ("ssd firmware", "nvme firmware", "storage firmware", "solid state", "drive firmware")
        ) or ("firmware" in title and ("ssd" in title or "nvme" in title))
    model_l = (model or "").lower()
    match_tokens = _ssd_model_match_tokens(model_l)
    if not match_tokens:
        return False
    if not any(t in title for t in match_tokens):
        return False
    return True


def _model_search_tokens(model: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (model or "").lower()) if len(t) >= 3][:6]


def _installed_is_drive_firmware_revision(installed: str) -> bool:
    """True when WMI reports a retail SSD firmware string (not a Windows driver version)."""
    inst = (installed or "").strip()
    if not inst or inst in ("?", "—", "N/A"):
        return False
    if dc._looks_like_windows_inbox_driver_version(inst):
        return False
    if re.match(r"^10\.0\.", inst):
        return False
    return True


def _reject_inbox_ssd_firmware_package(
    title: str,
    version: str,
    installed: str,
    *,
    vs_installed: str = "",
) -> bool:
    """True when a Microsoft catalog/WU row is a generic inbox firmware *driver* package.

    Retail SSDs report firmware like ``8B2QJXD7`` while MSCatalog often lists
    ``Samsung … Firmware Driver Update (10.0.x)`` — not comparable drive firmware.
    """
    if not _installed_is_drive_firmware_revision(installed):
        return False
    title_l = (title or "").lower()
    if "firmware driver" in title_l:
        return True
    ver = (version or "").strip()
    if re.match(r"^10\.0\.", ver) and (vs_installed or "").strip() == "unknown":
        return True
    if dc._looks_like_windows_inbox_driver_version(ver) and (
        vs_installed or ""
    ).strip() == "unknown":
        return True
    return False


def _ssd_microsoft_offer_actionable(offer: dict, installed: str) -> bool:
    """True when a Microsoft SSD firmware row is safe to stop the fallback chain on."""
    vs = (offer.get("vs_installed") or "").strip()
    if vs in ("newer", "same", "older"):
        return True
    title = offer.get("title") or ""
    ver = (offer.get("version") or "").strip()
    if ver in ("", "—"):
        return False
    if _reject_inbox_ssd_firmware_package(
        title, ver, installed, vs_installed=vs
    ):
        return False
    return vs != "unknown"


def fetch_windows_update_storage_firmware(model: str, installed: str) -> dict | None:
    """Query Windows Update for optional packages that look like SSD/storage firmware."""
    if dc.run_powershell is None:
        return None
    model_ps = (model or "").replace("'", "''")[:80]
    ps = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$model = '{model_ps}'.ToLower()
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Searcher.Online = $true
try {{
  $Result = $Searcher.Search("IsInstalled=0 and IsHidden=0")
}} catch {{
  $Result = $Searcher.Search("IsInstalled=0")
}}
$best = $null
for ($i = 0; $i -lt $Result.Updates.Count; $i++) {{
  $u = $Result.Updates.Item($i)
  $title = ([string]$u.Title).ToLower()
  if ($title -notmatch 'firmware|ssd|nvme|solid state|samsung|western digital|crucial|intel.*ssd') {{ continue }}
  $hit = $false
  foreach ($tok in $model.Split(' ', [StringSplitOptions]::RemoveEmptyEntries)) {{
    if ($tok.Length -ge 4 -and $title.Contains($tok.ToLower())) {{ $hit = $true; break }}
  }}
  if (-not $hit) {{ continue }}
  $ver = ''
  try {{ $ver = [string]$u.DriverVerVersion }} catch {{}}
  if (-not $ver -and $u.Title -match '(\d+\.\d+\.\d+(?:\.\d+)?|[A-Z]?\d{{4,6}})') {{ $ver = $Matches[1] }}
  $best = [PSCustomObject]@{{
    Title = [string]$u.Title
    Version = $ver
    UpdateId = [string]$u.Identity.UpdateID
  }}
  break
}}
if ($best) {{ $best | ConvertTo-Json -Compress }}
"""
    ok, out = dc.run_powershell(ps, timeout=90)
    text = (out or "").strip()
    if not ok or not text or not text.startswith("{"):
        return None
    try:
        row = json.loads(out)
        title = (row.get("Title") or "Storage firmware")[:120]
        ver = (row.get("Version") or "").strip()
        vs = dc.compare_firmware_versions(installed, ver, title=title)
        if _reject_inbox_ssd_firmware_package(title, ver, installed, vs_installed=vs):
            return None
        if vs not in ("newer", "same", "older"):
            return None
        return {
            "title": title,
            "version": ver,
            "url": dc._microsoft_catalog_url(title),
            "notes": "Optional update from Windows Update — verify before installing firmware.",
            "update_id": (row.get("UpdateId") or "").strip(),
            "vs_installed": vs,
        }
    except json.JSONDecodeError:
        return None


def fetch_mscatalog_storage_firmware_offers(
    model: str,
    installed: str,
    vendor_key: str = "",
) -> list[dict]:
    """MSCatalogLTS search for SSD/NVMe firmware packages (E25, v6 full scan only)."""
    if not dc._v6_catalog_enabled() or dc.is_quick_check_mode():
        return []
    try:
        import catalog_ps_module as cps
    except ImportError:
        return []
    dc.ensure_mscatalog_module_ready(check_online=True)
    tokens = _model_search_tokens(model)
    if not tokens:
        return []
    primary = tokens[0]
    vk = (vendor_key or "").strip().lower()
    queries = [f"{primary} ssd firmware", f"{primary} nvme firmware"]
    if vk and vk not in ("unknown", "generic"):
        queries.insert(0, f"{vk} {primary} firmware")
    offers: list[dict] = []
    seen: set[str] = set()
    for query in queries[:4]:
        rows, _err = cps.search_mscatalog_updates(
            query,
            limit=4,
            include_file_names=True,
        )
        for row in rows or []:
            title = (row.get("title") or "").strip()
            title_l = title.lower()
            if not any(
                k in title_l
                for k in ("firmware", "ssd", "nvme", "storage", "solid state", "drive")
            ):
                continue
            if not any(t in title_l for t in tokens[:3]):
                continue
            uid = (row.get("update_id") or "").lower()
            if uid and uid in seen:
                continue
            if uid:
                seen.add(uid)
            ver = (row.get("version") or "").strip() or dc.extract_version_from_text(title)
            vs = dc.compare_firmware_versions(installed, ver, title=title)
            if _reject_inbox_ssd_firmware_package(title, ver, installed, vs_installed=vs):
                continue
            if vs not in ("newer", "same", "older"):
                continue
            url = (
                f"https://www.catalog.update.microsoft.com/ScopedViewInline.aspx?updateid={uid}"
                if uid
                else dc._microsoft_catalog_url(title)
            )
            offers.append({
                "source": "microsoft",
                "source_label": "Microsoft Update Catalog",
                "title": title[:120],
                "version": ver or "—",
                "date": dc._normalize_oem_date(row.get("date") or ""),
                "url": url,
                "download_kind": "catalog",
                "vs_installed": vs,
                "notes": (
                    "SSD/storage firmware from Microsoft Update Catalog — "
                    "verify model before installing."
                ),
                "kind": "ssd",
                "confidence": "medium",
                "installed_model": model,
                "installed_firmware": installed,
                "update_id": uid,
                "catalog_tier": (row.get("catalog_tier") or "standard"),
                "search_query": query,
            })
            if len(offers) >= 2:
                return offers
    return offers


def _firmware_coverage_gap_offer(
    *,
    source_label: str,
    title: str,
    url: str,
    model: str,
    installed: str,
    vendor_disp: str = "",
    coverage_reason: str = "",
) -> dict:
    """Honest \"couldn't verify\" SSD firmware row when vendor scrape failed."""
    name = vendor_disp or source_label
    try:
        import firmware_ssd_vendors as fsv

        note = fsv.coverage_gap_message(coverage_reason or "parse_failed", name)
    except ImportError:
        note = (
            f"Couldn't verify the latest {name} firmware automatically. "
            "Open the vendor page to confirm."
        )
    return {
        "source": "ssd_vendor",
        "source_label": source_label,
        "title": title,
        "version": "—",
        "date": "",
        "url": url,
        "download_kind": "url",
        "vs_installed": "uncertain",
        "notes": note,
        "kind": "ssd",
        "confidence": "low",
        "coverage_check_failed": True,
        "coverage_reason": coverage_reason or "parse_failed",
        "installed_model": model,
        "installed_firmware": installed,
    }


def _fetch_vendor_ssd_firmware(
    vendor_key: str,
    model: str,
    *,
    serial_number: str = "",
    storage_class: str = "",
    html_cache: dict[str, str] | None = None,
) -> dict | None:
    """Best-effort latest SSD firmware from vendor support pages."""
    try:
        import firmware_ssd_vendors as fsv
    except ImportError:
        fsv = None
    if fsv is not None:
        return fsv.fetch_vendor_ssd_firmware(
            vendor_key,
            model,
            serial_number=serial_number,
            storage_class=storage_class,
            html_cache=html_cache,
        )

    # Minimal fallback if registry module unavailable
    vk = (vendor_key or "").strip().lower()
    if not vk or not (model or "").strip():
        return None
    return {
        "title": f"SSD — {model[:60]}",
        "version": "",
        "url": "",
        "notes": "Open the drive manufacturer's support site.",
        "coverage_check_failed": True,
        "coverage_reason": "utility_only",
    }


def build_ssd_firmware_offers(
    drives: list[dict],
    oem_catalog_rows: list[tuple[str, dict, str]],
    progress: Callable[[str], None] | None = None,
    scan_cache: dict[str, str] | None = None,
    unit_done: Callable[[str], None] | None = None,
) -> list[dict]:
    """Per-drive SSD firmware offers with version compare when catalog data exists."""
    offers: list[dict] = []
    flat_oem = [row for _, row, _ in oem_catalog_rows]

    for drive in drives or []:
        model = (drive.get("model") or "").strip()
        installed = (drive.get("firmware_revision") or "").strip() or "?"
        vendor = (drive.get("vendor_key") or "").strip()
        if not model:
            continue
        if progress:
            progress(f"Checking SSD firmware for {model[:40]}…")

        added = False
        oem_matches: list[tuple[int, int, str, dict]] = []
        rank_map = {"newer": 3, "unknown": 2, "same": 1, "older": 0, "n/a": 0}
        for row in flat_oem:
            if not is_storage_firmware_row(row, model):
                continue
            title = row.get("title") or ""
            ver = (row.get("version") or "").strip() or dc.extract_version_from_text(title)
            vs = dc.compare_firmware_versions(installed, ver, title=title)
            rank = rank_map.get(vs, 2)
            ver_rank = len(dc.parse_driver_version(ver))
            oem_matches.append((rank, ver_rank, vs, row))
        oem_matches.sort(key=lambda x: (-x[0], -x[1]))
        actionable = [m for m in oem_matches if m[2] in ("newer", "same", "older")]
        seen_titles: set[str] = set()
        for _rank, _ver_rank, vs, row in actionable[:2]:
            title_key = (row.get("title") or "").lower()[:80]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            offer = _offer_from_row(
                row,
                "OEM (storage firmware)",
                installed,
                kind="ssd",
                notes=f"OEM catalog entry for {model}. Install via manufacturer utility.",
            )
            offer["vs_installed"] = vs
            offer["installed_model"] = model
            offer["installed_firmware"] = installed
            offers.append(offer)
            added = True

        if not added:
            for ms_offer in fetch_mscatalog_storage_firmware_offers(model, installed, vendor):
                if not _ssd_microsoft_offer_actionable(ms_offer, installed):
                    continue
                offers.append(ms_offer)
                added = True
                break

        if not added:
            for store_offer in dc.fetch_storage_driver_store_offers(
                model, installed, vendor
            ):
                if not _ssd_microsoft_offer_actionable(store_offer, installed):
                    continue
                offers.append(store_offer)
                added = True
                break

        if not added:
            wu = fetch_windows_update_storage_firmware(model, installed)
            if wu and _ssd_microsoft_offer_actionable(wu, installed):
                offers.append({
                    "source": "microsoft",
                    "source_label": "Microsoft (Windows Update)",
                    "title": wu["title"],
                    "version": wu.get("version") or "—",
                    "date": "",
                    "url": wu.get("url") or "",
                    "download_kind": "catalog",
                    "vs_installed": wu.get("vs_installed") or "unknown",
                    "notes": wu.get("notes") or "",
                    "kind": "ssd",
                    "confidence": "medium",
                    "installed_model": model,
                    "installed_firmware": installed,
                })
                added = True

        if not added and vendor:
            vf = _fetch_vendor_ssd_firmware(
                vendor,
                model,
                serial_number=(drive.get("serial_number") or "").strip(),
                storage_class=(drive.get("storage_class") or "").strip(),
                html_cache=scan_cache,
            )
            if vf:
                if vf.get("coverage_check_failed"):
                    offers.append(
                        _firmware_coverage_gap_offer(
                            source_label=f"SSD ({vendor})",
                            title=vf.get("title") or model,
                            url=vf.get("url") or "",
                            model=model,
                            installed=installed,
                            vendor_disp=vendor,
                            coverage_reason=(vf.get("coverage_reason") or "parse_failed"),
                        )
                    )
                else:
                    ver = (vf.get("version") or "").strip()
                    vs = dc.compare_firmware_versions(
                        installed, ver, title=vf.get("title") or ""
                    )
                    if vs == "unknown":
                        offers.append(
                            _firmware_coverage_gap_offer(
                                source_label=f"SSD ({vendor})",
                                title=vf.get("title") or model,
                                url=vf.get("url") or "",
                                model=model,
                                installed=installed,
                                vendor_disp=vendor,
                                coverage_reason="compare_unknown",
                            )
                        )
                    else:
                        offers.append({
                            "source": "ssd_vendor",
                            "source_label": f"SSD ({vendor})",
                            "title": vf.get("title") or model,
                            "version": ver or "—",
                            "date": "",
                            "url": vf.get("url") or "",
                            "download_kind": "url",
                            "vs_installed": vs,
                            "notes": vf.get("notes") or "",
                            "kind": "ssd",
                            "confidence": "medium" if ver else "low",
                            "installed_model": model,
                            "installed_firmware": installed,
                        })
                added = True

        if not added:
            offers.append({
                "source": "ssd_local",
                "source_label": "Installed SSD",
                "title": f"{model} (installed firmware {installed})",
                "version": "—",
                "date": "",
                "url": "",
                "download_kind": "url",
                "vs_installed": "unknown",
                "notes": "No online firmware match — check the drive manufacturer's support site.",
                "kind": "ssd",
                "confidence": "low",
                "installed_model": model,
                "installed_firmware": installed,
            })
        if unit_done:
            unit_done(model[:40] or "SSD")

    return offers


def build_ssd_uncertain_inspector_summary(
    offers: list[dict] | None,
    drives: list[dict] | None = None,
    *,
    status: str = "",
    focus_model: str = "",
) -> str:
    """Per-drive MSCatalog/vendor breakdown when SSD firmware compare is uncertain."""
    relevant = [
        o for o in (offers or []) if (o.get("kind") or "").lower() in ("ssd", "firmware", "")
    ]
    if not relevant:
        return dc.build_uncertain_inspector_summary(offers or [], status=status)

    st = (status or "").lower()
    uncertain = [
        o
        for o in relevant
        if (o.get("vs_installed") or "").lower() in ("unknown", "uncertain")
    ]
    if st not in ("unknown", "uncertain") and not uncertain:
        return ""

    drive_rows = list(drives or [])
    focus = (focus_model or "").strip()
    models: list[str] = []
    if focus:
        models = [focus]
    elif drive_rows:
        models = [
            (d.get("model") or "").strip()
            for d in drive_rows
            if (d.get("model") or "").strip()
        ]
    else:
        models = sorted({
            (o.get("installed_model") or "").strip()
            for o in relevant
            if (o.get("installed_model") or "").strip()
        })

    if not models:
        inst = (relevant[0].get("installed_firmware") or "?").strip() or "?"
        return dc.build_uncertain_inspector_summary(relevant, inst, status=st)

    lines = ["SSD firmware — per-drive source breakdown:", ""]
    status_rank = {"newer": 3, "uncertain": 2, "unknown": 2, "same": 1, "older": 0}
    per_drive_status: dict[str, str] = {}

    for model in models:
        installed = "?"
        for d in drive_rows:
            if (d.get("model") or "").strip() == model:
                installed = (d.get("firmware_revision") or "?").strip() or "?"
                break
        drive_offers = [
            o
            for o in relevant
            if not (o.get("installed_model") or "").strip()
            or (o.get("installed_model") or "").strip() == model
        ]
        if not drive_offers:
            continue
        lines.append(f"Drive: {model}")
        lines.append(f"Installed firmware: {installed}")
        for i, o in enumerate(drive_offers[:10], 1):
            src = o.get("source_label") or o.get("source") or "?"
            ver = dc._offer_version_from_fields(o) or "—"
            vs = (o.get("vs_installed") or "unknown").capitalize()
            query = (o.get("search_query") or "").strip()
            query_bit = f" · query «{query}»" if query else ""
            note = (o.get("compare_note") or o.get("notes") or "").strip()
            lines.append(f"  {i}. {src}: v{ver} → {vs}{query_bit}")
            if note:
                lines.append(f"     {note[:180]}")
            rank = status_rank.get((o.get("vs_installed") or "").lower(), 1)
            prev = per_drive_status.get(model, "")
            if not prev or rank > status_rank.get(prev, 0):
                per_drive_status[model] = (o.get("vs_installed") or "unknown").lower()
        lines.append("")

    if len(per_drive_status) > 1:
        vals = set(per_drive_status.values())
        if len(vals) > 1:
            lines.append(
                "Drives disagree — compare each model separately before updating firmware."
            )
            lines.append("")

    conflict = dc.offer_source_conflict_summary(relevant)
    if conflict:
        lines.extend([conflict, ""])

    lines.append(
        "Use the packages table and the vendor utility (Magician, WD Dashboard, etc.) "
        "to verify before installing."
    )
    return "\n".join(lines).strip()


def is_utility_or_link_offer(offer: dict) -> bool:
    """True when the row is a toolbox/support link without a comparable version."""
    kind = (offer.get("kind") or "").lower()
    src = (offer.get("source") or "").lower()
    if kind in ("utility", "link", "support"):
        return True
    if src in ("utility", "support", "ssd_local"):
        return True
    ver = (offer.get("version") or "").strip()
    if ver in ("", "—", "?", "-"):
        return bool((offer.get("url") or "").strip())
    return False


def offers_are_utility_only(offers: list[dict] | None) -> bool:
    rows = [o for o in (offers or []) if (o.get("title") or o.get("url"))]
    if not rows:
        return False
    return all(is_utility_or_link_offer(o) for o in rows)


def build_firmware_utility_inspector_summary(
    offers: list[dict] | None,
    *,
    component_label: str = "",
    kind: str = "",
) -> str:
    """Structured steps when firmware Search found utility/support links only."""
    rows = [o for o in (offers or []) if (o.get("title") or o.get("url"))]
    if not rows:
        return ""
    label = (component_label or "This component").strip()
    kind_l = (kind or "").lower()
    if kind_l == "bios":
        intro = (
            f"{label} — no automatic BIOS version match.\n"
            "Firmware is updated through your PC maker's utility or support site, not from this app."
        )
    elif kind_l.startswith("ssd"):
        intro = (
            f"{label} — use the drive manufacturer's desktop utility to compare and flash firmware."
        )
    else:
        intro = f"{label} — open the manufacturer utility or support page below."
    lines = [intro, ""]
    for i, o in enumerate(rows[:8], 1):
        title = (o.get("title") or "Support link").strip()
        src = (o.get("source_label") or o.get("source") or "Link").strip()
        note = (o.get("notes") or "").strip()
        lines.append(f"{i}. {src}: {title}")
        if note:
            lines.append(f"   {note[:220]}")
    lines.extend([
        "",
        "Steps:",
        "  1. Open the link in the packages table (double-click or Download).",
        "  2. Compare installed version shown above with the vendor's latest release.",
        "  3. Install only using the manufacturer's instructions — never flash from this app.",
    ])
    return "\n".join(lines)


def build_bios_uncertain_inspector_summary(
    offers: list[dict] | None,
    installed_version: str = "",
    *,
    status: str = "",
    system_ctx: dict | None = None,
) -> str:
    """BIOS-specific uncertain breakdown (OEM catalog + live scrape sources)."""
    bios_rows = [
        o for o in (offers or []) if (o.get("kind") or "").lower() == "bios"
    ]
    base_rows = bios_rows or list(offers or [])
    summary = dc.build_uncertain_inspector_summary(
        base_rows,
        installed_version,
        status=status,
    )
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").strip()
    model = (ctx.get("system_model") or "").strip()
    machine = " ".join(x for x in (mfr, model) if x).strip()
    prefix_lines = [
        "System BIOS — version compare is uncertain.",
        f"Installed: {(installed_version or '?').strip()}",
    ]
    if machine:
        prefix_lines.append(f"System: {machine}")
    prefix_lines.append(
        "Confirm the package matches your exact model on the OEM support site before flashing."
    )
    prefix_lines.append("")
    if summary:
        return "\n".join(prefix_lines) + "\n" + summary
    if not base_rows:
        prefix_lines.extend([
            "No OEM BIOS package was parsed automatically.",
            "",
            "Try Tools → Refresh driver database (full install), then Search again.",
            "Or open your PC maker's support site → BIOS/Firmware for your service tag/model.",
        ])
        return "\n".join(prefix_lines)
    return "\n".join(prefix_lines)


def finalize_firmware_offers(
    offers: list[dict],
    *,
    bios_installed: str = "",
    bios_date: str = "",
) -> list[dict]:
    """E24: same enrichment/conflict pipeline as the driver catalog."""
    merged: list[dict] = []
    for o in offers or []:
        kind = (o.get("kind") or "").lower()
        if kind in ("link", "utility"):
            merged.append(dict(o))
            continue
        if kind == "peripheral":
            inst = (o.get("installed_firmware") or o.get("installed") or "?").strip()
            merged.extend(
                dc.finalize_catalog_offers([dict(o)], inst, "", firmware=True)
            )
            continue
        if kind == "ssd":
            inst = (o.get("installed_firmware") or bios_installed or "?").strip()
            inst_d = ""
        else:
            inst = bios_installed
            inst_d = bios_date
        merged.extend(
            dc.finalize_catalog_offers([dict(o)], inst, inst_d, firmware=True)
        )
    seen: set[tuple] = set()
    unique: list[dict] = []
    for o in merged:
        key = (
            o.get("source"),
            o.get("version"),
            o.get("title"),
            o.get("installed_firmware"),
            o.get("kind"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(o)
    return dc.sort_catalog_offers(unique)


def _supplemental_firmware_utilities(
    system_ctx: dict | None,
    pnp_list: list | None,
) -> list[dict]:
    """SSD/GPU utility pages when we detect relevant hardware (not version-matched)."""
    ctx = system_ctx or {}
    present = ctx.get("present_drivers") or set()
    text_blobs: list[str] = []
    for vc in ctx.get("video_controllers") or []:
        if isinstance(vc, dict):
            text_blobs.append(f"{vc.get('name', '')} {vc.get('driver_version', '')}")
    for ent in (pnp_list or [])[:200]:
        text_blobs.append((ent.get("Name") or ""))
    blob = " ".join(text_blobs).lower()

    utilities: list[dict] = []
    seen_urls: set[str] = set()
    for needle, title, url in _UTILITY_KEYWORDS:
        if needle not in blob and needle not in " ".join(present).lower():
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        utilities.append({
            "source": "utility",
            "source_label": "Device utility",
            "title": title,
            "version": "—",
            "date": "",
            "url": url,
            "download_kind": "url",
            "vs_installed": "n/a",
            "notes": "Manufacturer SSD/GPU utility — may include firmware updates. Follow their instructions.",
            "kind": "utility",
            "confidence": "low",
        })

    if present & {"nvlddmkm", "nvlddmkm.sys"} or "nvidia" in blob:
        url = "https://www.nvidia.com/en-us/drivers/"
        if url not in seen_urls:
            utilities.append({
                "source": "utility",
                "source_label": "GPU vendor",
                "title": "NVIDIA driver download (display/VBIOS updates ship with driver)",
                "version": "—",
                "date": "",
                "url": url,
                "download_kind": "url",
                "vs_installed": "n/a",
                "notes": "GPU firmware is usually updated via the graphics driver package, not separately.",
                "kind": "utility",
                "confidence": "low",
            })
    if (present & {"amdkmdag", "atikmdag"} or "amd radeon" in blob or "advanced micro" in blob):
        url = "https://www.amd.com/en/support/download/drivers.html"
        if url in seen_urls:
            return utilities[:6]
        seen_urls.add(url)
        utilities.append({
            "source": "utility",
            "source_label": "GPU vendor",
            "title": "AMD driver download",
            "version": "—",
            "date": "",
            "url": url,
            "download_kind": "url",
            "vs_installed": "n/a",
            "notes": "GPU firmware is usually updated via the graphics driver package.",
            "kind": "utility",
            "confidence": "low",
        })
    return utilities[:6]


def get_firmware_support_links(system_ctx: dict | None) -> list[dict]:
    links: list[dict] = []
    url = _system_manufacturer_oem_url(system_ctx)
    mfr = (system_ctx or {}).get("system_manufacturer") or "PC manufacturer"
    if url:
        links.append({"label": f"{mfr} support (system)", "url": url})
    bb = (system_ctx or {}).get("baseboard_manufacturer") or ""
    bb_prod = (system_ctx or {}).get("baseboard_product") or ""
    if bb and bb_prod:
        slug = dc._slug_for_oem_api(bb_prod)
        # WMI reports trade names, not brands: MSI boards say "Micro-Star International
        # Co., Ltd." and never the literal "msi". _manufacturer_matches owns those aliases.
        if dc._manufacturer_matches(bb, "asus", "asustek"):
            links.append({
                "label": "ASUS motherboard support",
                "url": "https://www.asus.com/support/download-center/",
            })
        elif dc._manufacturer_matches(bb, "msi", "micro-star") and slug:
            links.append({
                "label": "MSI motherboard support",
                "url": f"https://www.msi.com/Motherboard/support/{slug}",
            })
        elif dc._manufacturer_matches(bb, "gigabyte", "aorus") and slug:
            links.append({
                "label": "Gigabyte motherboard support",
                "url": f"https://www.gigabyte.com/Motherboard/{slug}/support",
            })
    tag = dc._dell_service_tag(system_ctx)
    if tag and "dell" in mfr.lower():
        links.append({
            "label": "Dell BIOS & drivers",
            "url": f"https://www.dell.com/support/home/en-us/product-support/servicetag/{tag}/drivers",
        })
    return links


def firmware_target_unit_count(target_keys: list[str] | None) -> int:
    """Count GUI-selected firmware targets for determinate progress (Checked X/Y)."""
    keys = [k.strip() for k in (target_keys or []) if k and str(k).strip()]
    if not keys:
        return 0
    total = 0
    if "bios" in keys:
        total += 1
    for key in keys:
        if key.startswith("ssd:"):
            model = key[4:].strip().lower()
            if model and model != "none":
                total += 1
        elif key.startswith(("peripheral:", "winfw:")):
            total += 1
    return total


def build_firmware_comparison(
    bios_info: dict | None,
    system_ctx: dict | None,
    pnp_list: list | None = None,
    ssd_firmware: list | None = None,
    progress: Callable[[str], None] | None = None,
    target_keys: list[str] | None = None,
    secondary_firmware: list | None = None,
) -> dict:
    """
    Compare installed BIOS (Win32_BIOS) vs OEM catalog entries where available.
    Includes supplemental SSD/GPU utility links.

    target_keys: optional subset, e.g. ["bios", "ssd:Samsung 990 PRO"]. None = all.
    secondary_firmware: when set (including []), reuse Load-components inventory
        instead of re-running PnP/USB discovery during search.
    """
    keys = [k.strip() for k in (target_keys or []) if k and str(k).strip()]
    check_all = not keys
    check_bios = check_all or "bios" in keys
    ssd_models: set[str] = set()
    peripheral_keys: set[str] = set()
    winfw_keys: set[str] = set()
    for k in keys:
        if k.startswith("ssd:"):
            model = k[4:].strip().lower()
            if model and model != "none":
                ssd_models.add(model)
        elif k.startswith("peripheral:"):
            peripheral_keys.add(k)
        elif k.startswith("winfw:"):
            winfw_keys.add(k)

    unit_total = firmware_target_unit_count(keys)
    unit_cur = 0

    def _emit_unit_done(detail: str) -> None:
        nonlocal unit_cur
        if unit_total <= 0 or not progress:
            return
        unit_cur += 1
        suffix = " — finalizing…" if unit_cur >= unit_total else ""
        progress(f"Checked {unit_cur}/{unit_total} — {detail}{suffix}")

    if progress:
        progress("Preparing system context…")
    ctx = dc.extend_system_ctx_for_catalog(dict(system_ctx or {}))
    scan_cache: dict[str, str] = {}

    check_ssd = check_all or bool(ssd_models) or any(k == "ssd:none" for k in keys)
    check_secondary = check_all or bool(peripheral_keys) or bool(winfw_keys)

    secondary_devices_pre: list[dict] | None = None
    if check_secondary:
        if secondary_firmware is not None:
            secondary_devices_pre = list(secondary_firmware)
        elif pnp_list:
            try:
                import firmware_peripheral_discovery as fpdisc

                if progress:
                    progress("Discovering secondary firmware devices…")
                secondary_devices_pre = fpdisc.discover_secondary_firmware_devices(
                    list(pnp_list),
                    (system_ctx or {}).get("driver_rows"),
                    query_pnp_firmware=not dc.is_quick_check_mode(),
                    has_bios=True,
                )
            except ImportError:
                secondary_devices_pre = []

    if not dc.is_quick_check_mode():
        try:
            import vendor_firmware_fetch as vff

            if progress:
                progress("Warming firmware catalogs (batch)…")
            vff.warm_firmware_batch(
                ctx,
                ssd_drives=ssd_firmware if check_ssd else None,
                secondary_devices=secondary_devices_pre if check_secondary else None,
                scan_cache=scan_cache,
                progress=progress,
            )
        except ImportError:
            if not dc.is_quick_check_mode():
                dc._warm_oem_session_cache(ctx)

    if dc._v6_catalog_enabled() and not dc.is_quick_check_mode():
        dc.ensure_mscatalog_module_ready(progress=progress)
    if not dc._should_skip_online_driver_store(system_ctx, ctx):
        dc.ensure_online_driver_store_loaded(progress=progress)
    elif progress:
        progress(
            "Using OEM firmware sources "
            "(skipping full online driver catalog for stability)."
        )
    bios = dict(bios_info or {})
    installed_ver = (bios.get("version") or "").strip()
    installed_date = _parse_json_date(bios.get("date", ""))

    if progress and unit_total > 0:
        progress(f"Checking {unit_total} firmware component(s)")

    raw: list = []
    if check_bios:
        if progress:
            progress("Querying OEM firmware catalogs…")
        raw = _collect_oem_firmware_rows(ctx, progress=progress)
    if check_bios and check_ssd:
        if progress:
            progress("Checking OEM storage firmware…")
        raw.extend(_collect_oem_storage_firmware_rows(ctx, progress=progress))

    offers: list[dict] = []
    if check_bios:
        seen_titles: set[str] = set()
        bios_candidates: list[dict] = []
        for label, row, fallback in raw:
            if not is_bios_catalog_row(row):
                continue
            title_key = (row.get("title") or "").lower()[:80]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            offer = _offer_from_row(
                row,
                f"OEM ({label})",
                installed_ver,
                kind="bios",
                notes=(
                    f"{_FIRMWARE_WARNINGS[1]} "
                    f"Package from {label} catalog."
                ),
            )
            bios_candidates.append(offer)

        bios_candidates.sort(
            key=lambda x: (
                0 if x.get("vs_installed") == "newer" else 1,
                0 if x.get("version") else 1,
                -len(dc.parse_driver_version(x.get("version") or "")),
            ),
        )
        offers.extend(bios_candidates[:8])
        if (
            not bios_candidates
            and not ctx.get("_firmware_live_bios_done")
            and not dc.is_quick_check_mode()
        ):
            ctx["_firmware_live_bios_done"] = True
            live_ctx = {
                "device_label": (ctx.get("system_model") or "BIOS"),
                "vendor_key": "",
                "pnp_class": "system",
            }
            for o in dc._fetch_live_oem_offers(live_ctx, ctx):
                title_l = (o.get("title") or "").lower()
                if not any(kw in title_l for kw in _FIRMWARE_KEYWORDS):
                    continue
                if is_bios_catalog_row({
                    "title": o.get("title"),
                    "category": "",
                }):
                    ver = (o.get("version") or "").strip()
                    offers.append({
                        "source": "oem_firmware",
                        "source_label": o.get("source_label") or "OEM",
                        "title": (o.get("title") or "BIOS")[:120],
                        "version": ver,
                        "date": dc._normalize_oem_date(o.get("date") or ""),
                        "url": (o.get("url") or "").strip(),
                        "download_kind": "url",
                        "vs_installed": dc.compare_firmware_versions(
                            installed_ver, ver, title=o.get("title") or ""
                        ),
                        "notes": o.get("notes") or _FIRMWARE_WARNINGS[1],
                        "kind": "bios",
                        "confidence": "high" if ver else "medium",
                    })

        _emit_unit_done("BIOS")

    ssd_offers: list[dict] = []
    if check_ssd:
        if progress:
            progress("Comparing SSD firmware…")
        if ssd_firmware is None:
            try:
                from bsod_hardware_wmi import get_ssd_firmware_inventory
                ssd_firmware = get_ssd_firmware_inventory()
            except ImportError:
                ssd_firmware = []
        drives = list(ssd_firmware or [])
        if ssd_models:
            drives = [
                d
                for d in drives
                if (d.get("model") or "").strip().lower() in ssd_models
            ]
        ssd_offers = build_ssd_firmware_offers(
            drives, raw, progress=progress, scan_cache=scan_cache, unit_done=_emit_unit_done
        )
        offers.extend(ssd_offers)

    secondary_devices: list[dict] = []
    if check_secondary and pnp_list:
        sec_keys = None
        if not check_all:
            sec_keys = list(peripheral_keys | winfw_keys)
        known = secondary_firmware
        if known is None and secondary_devices_pre is not None:
            known = secondary_devices_pre
        secondary_devices, sec_offers = discover_and_build_secondary_offers(
            pnp_list,
            (system_ctx or {}).get("driver_rows"),
            progress=progress,
            target_keys=sec_keys,
            query_pnp_firmware=not dc.is_quick_check_mode(),
            known_devices=known,
            scan_cache=scan_cache,
            unit_done=_emit_unit_done,
        )
        offers.extend(sec_offers)

    utilities: list[dict] = []
    if check_all:
        if progress:
            progress("Adding GPU utility links…")
        utilities = _supplemental_firmware_utilities(ctx, pnp_list)
    # Only add generic utilities for vendors we did not already match per-drive.
    ssd_vendors = {d.get("vendor_key") for d in (ssd_firmware or []) if d.get("vendor_key")}
    for u in utilities:
        title_l = (u.get("title") or "").lower()
        if "samsung" in title_l and "samsung" in ssd_vendors:
            continue
        if "wd dashboard" in title_l and "wd" in ssd_vendors:
            continue
        if "crucial" in title_l and "crucial" in ssd_vendors:
            continue
        offers.append(u)

    support_urls = get_firmware_support_links(ctx)
    if not offers and support_urls:
        offers.append({
            "source": "support",
            "source_label": "Support page",
            "title": "Open manufacturer support to find BIOS/firmware",
            "version": "—",
            "date": "",
            "url": support_urls[0]["url"],
            "download_kind": "url",
            "vs_installed": "unknown",
            "notes": "No BIOS package was parsed automatically. Use the support site BIOS/Firmware section.",
            "kind": "link",
            "confidence": "low",
        })

    offers = finalize_firmware_offers(
        offers,
        bios_installed=installed_ver,
        bios_date=installed_date,
    )
    scan_mode = dc.catalog_scan_mode_summary(
        quick_check=dc.is_quick_check_mode(),
        gui_mode=True,
    )

    return {
        "installed": {
            "manufacturer": (bios.get("manufacturer") or "").strip(),
            "version": installed_ver or "?",
            "date": installed_date,
        },
        "offers": offers,
        "support_urls": support_urls,
        "warnings": list(_FIRMWARE_WARNINGS),
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "has_catalog_bios": any(o.get("kind") == "bios" for o in offers),
        "ssd_drives": ssd_firmware or [],
        "has_ssd_compare": bool(ssd_offers),
        "secondary_devices": secondary_devices,
        "has_secondary_compare": bool(secondary_devices),
        "target_keys": keys if keys else None,
        "scan_mode": scan_mode.get("mode") or "",
        "scan_mode_detail": scan_mode.get("detail") or "",
    }


def _short_winfw_label(label: str) -> str:
    s = (label or "").strip()
    if not s:
        return "System firmware"
    low = s.lower()
    if low.startswith("system firmware —"):
        rest = s.split("—", 1)[-1].strip()
        return rest or s
    if low.startswith("system firmware -"):
        rest = s.split("-", 1)[-1].strip()
        return rest or s
    return s


def build_secondary_firmware_offers(
    secondary_devices: list[dict],
    *,
    progress: Callable[[str], None] | None = None,
    target_keys: list[str] | None = None,
    scan_cache: dict[str, str] | None = None,
    unit_done: Callable[[str], None] | None = None,
) -> list[dict]:
    """Peripheral + Windows FIRMWARE class offers via vendor support-site search."""
    try:
        import firmware_peripheral_discovery as fpdisc
        import firmware_peripheral_vendors as fpv
    except ImportError:
        return []

    allow = {k.strip() for k in (target_keys or []) if k and str(k).strip()}
    check_all = not allow
    offers: list[dict] = []

    for dev in secondary_devices or []:
        key = (dev.get("key") or "").strip()
        if not key:
            continue
        if not check_all and key not in allow:
            continue
        vendor = (dev.get("vendor_key") or "").strip().lower()
        label = (dev.get("resolved_name") or dev.get("component") or dev.get("name") or "").strip()
        installed = (dev.get("installed") or dev.get("driver_version") or "—").strip()
        category = (dev.get("category") or "").strip()
        if category == "usb_peripheral" and not vendor:
            hint = fpv.product_hint(dev.get("device_id") or "", label)
            if hint and hint.vendor_key:
                vendor = hint.vendor_key

        if category == "usb_peripheral" and vendor in fpv.VENDOR_SITE_REGISTRY:
            if progress:
                progress(f"Support site: {label[:50]}…")
            ctx = {
                "device_id": dev.get("device_id") or "",
                "device_label": label,
                "name": dev.get("name") or "",
                "subcategory": dev.get("subcategory") or "",
                "pnp_class": dev.get("pnp_class") or "",
            }
            try:
                row = fpv.fetch_vendor_peripheral_firmware(vendor, ctx, html_cache=scan_cache)
            except Exception:
                row = None
            if row:
                offer = fpv.peripheral_offer_from_row(
                    {**row, "installed_source": dev.get("installed_source") or ""},
                    installed=installed,
                    device_label=label,
                )
                offer["kind"] = "peripheral"
                offer["installed_firmware"] = installed
                offer["installed_source"] = dev.get("installed_source") or ""
                offer["target_key"] = key
                offer["device_id"] = dev.get("device_id") or ""
                offers.append(offer)
            if unit_done:
                unit_done(label[:50] or key)
            continue

        if category == "windows_firmware":
            if progress:
                progress(f"Windows firmware node: {label[:50]}…")
            short = _short_winfw_label(label)
            offers.append({
                "source": "pnp_firmware",
                "source_label": "Windows firmware device",
                "title": short,
                "display_title": short,
                "full_title": label or short,
                "version": "",
                "url": "",
                "vs_installed": "uncertain",
                "notes": (
                    "PnP firmware-class device — compare against your PC maker's "
                    "BIOS/embedded firmware packages on the OEM support site."
                ),
                "kind": "peripheral",
                "confidence": "low",
                "target_key": key,
                "installed_firmware": installed,
            })
            if unit_done:
                unit_done(label[:50] or key)
            continue

        if unit_done and not check_all:
            unit_done(label[:50] or key)

    return offers


def discover_and_build_secondary_offers(
    pnp_list: list | None,
    driver_rows: list | None = None,
    *,
    progress: Callable[[str], None] | None = None,
    target_keys: list[str] | None = None,
    query_pnp_firmware: bool = True,
    known_devices: list | None = None,
    scan_cache: dict[str, str] | None = None,
    unit_done: Callable[[str], None] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Discover secondary devices and fetch support-site offers.

    When known_devices is provided (including an empty list after Load components),
    skip PnP/USB discovery and build offers from that inventory only.
    """
    try:
        import firmware_peripheral_discovery as fpdisc
    except ImportError:
        return [], []
    if known_devices is not None:
        if progress:
            n = len(known_devices)
            progress(
                f"Using loaded peripheral inventory ({n} device(s))…"
                if n
                else "Using loaded peripheral inventory (none found at load)…"
            )
        devices = fpdisc.finalize_secondary_firmware_devices(
            list(known_devices),
            has_bios=True,
        )
    else:
        if progress:
            progress("Discovering secondary firmware devices…")
        devices = fpdisc.discover_secondary_firmware_devices(
            list(pnp_list or []),
            driver_rows,
            query_pnp_firmware=query_pnp_firmware,
            has_bios=True,
        )
    offers = build_secondary_firmware_offers(
        devices,
        progress=progress,
        target_keys=target_keys,
        scan_cache=scan_cache,
        unit_done=unit_done,
    )
    return devices, offers


def open_firmware_offer(offer: dict) -> tuple[bool, str, str | None]:
    """Open firmware download or support URL (same safety model as driver downloads)."""
    return dc.download_driver_offer(offer)
