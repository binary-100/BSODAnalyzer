"""Comprehensive firmware/update scan for all discovery-tier devices (live network)."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import device_enrichment as de
import driver_catalog as dc
import firmware_catalog as fwcat
from bsod_hardware_wmi import (
    get_bios_and_driver_versions,
    get_hardware_profile_wmi_bundle,
    get_ssd_firmware_inventory,
)
from scripts.live_firmware_device_discovery import discover_firmware_capable_devices

_USB_VID_PID_RE = re.compile(r"VID[_&]([0-9A-F]{4}).*?PID[_&]([0-9A-F]{4})", re.I)

_PERIPHERAL_UTILITY_URLS = {
    "razer": ("Razer Synapse", "https://www.razer.com/synapse-4"),
    "logitech": ("Logitech G HUB / Options+", "https://www.logitech.com/en-us/software"),
    "corsair": ("CORSAIR iCUE", "https://www.corsair.com/icue"),
    "steelseries": ("SteelSeries GG", "https://steelseries.com/gg"),
    "keychron": ("Keychron software", "https://www.keychron.com/pages/download"),
    "elgato": ("Elgato software", "https://www.elgato.com/en/downloads"),
}

_VENDOR_FETCHERS = {
    "nvidia": dc.fetch_nvidia_driver_offer,
    "amd": dc.fetch_amd_driver_offers,
    "realtek": dc.fetch_realtek_driver_offers,
    "mediatek": dc.fetch_mediatek_driver_offers,
    "qualcomm": dc.fetch_qualcomm_driver_offers,
    "broadcom": dc.fetch_broadcom_driver_offers,
    "logitech": dc.fetch_logitech_driver_offers,
}


def _usb_vid_pid(device_id: str) -> tuple[str, str]:
    m = _USB_VID_PID_RE.search(device_id or "")
    if not m:
        return "", ""
    return m.group(1).upper(), m.group(2).upper()


def _vendor_from_device_id(device_id: str) -> str:
    vid, _ = _usb_vid_pid(device_id)
    if vid:
        return (de._USB_VID_VENDORS.get(vid.lower()) or "").lower()
    m = re.search(r"VEN_([0-9A-F]{4})", device_id or "", re.I)
    if m:
        return (de._PCI_VEN_VENDORS.get(m.group(1).lower()) or "").lower()
    return ""


def _friendly_usb_label(device_id: str, name: str) -> str:
    vid, pid = _usb_vid_pid(device_id)
    vendor = _vendor_from_device_id(device_id)
    if vendor:
        return f"{vendor.title()} USB device ({vid}:{pid})"
    return name


def _search_mscatalog_firmware(query: str, *, limit: int = 5) -> list[dict]:
    if not dc._v6_catalog_enabled() or dc.is_quick_check_mode():
        return []
    try:
        import catalog_ps_module as cps
    except ImportError:
        return []
    dc.ensure_mscatalog_module_ready(check_online=True)
    rows, err = dc._search_mscatalog_updates_cached(
        query,
        limit=limit,
        include_preview=False,
    )
    if err and not rows:
        return []
    offers: list[dict] = []
    for row in rows or []:
        title = (row.get("title") or "")[:120]
        tl = title.lower()
        if "firmware" not in tl and "uefi" not in tl and "bios" not in tl:
            continue
        ver = (row.get("version") or "").strip()
        uid = (row.get("update_id") or "").strip()
        url = dc._microsoft_catalog_url(title)
        if uid:
            url = (
                f"https://www.catalog.update.microsoft.com/ScopedViewInline.aspx"
                f"?updateid={uid}"
            )
        offers.append({
            "source": "microsoft_catalog",
            "source_label": "Microsoft Update Catalog",
            "title": title,
            "version": ver or "—",
            "url": url,
            "query": query,
        })
    return offers


def _search_wu_optional_firmware(keywords: list[str]) -> list[dict]:
    if dc.run_powershell is None:
        return []
    kw_ps = json.dumps([k.lower() for k in keywords if k])
    ps = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$keywords = {kw_ps}
$Session = New-Object -ComObject Microsoft.Update.Session
$Searcher = $Session.CreateUpdateSearcher()
$Searcher.Online = $true
try {{ $Result = $Searcher.Search("IsInstalled=0 and IsHidden=0") }}
catch {{ $Result = $Searcher.Search("IsInstalled=0") }}
$rows = @()
for ($i = 0; $i -lt $Result.Updates.Count; $i++) {{
  $u = $Result.Updates.Item($i)
  $title = [string]$u.Title
  $tl = $title.ToLower()
  if ($tl -notmatch 'firmware|uefi|bios|embedded|ec firmware|system firmware') {{ continue }}
  $hit = $false
  foreach ($kw in $keywords) {{
    if ($kw -and $tl.Contains($kw.ToLower())) {{ $hit = $true; break }}
  }}
  if (-not $hit -and $keywords.Count -gt 0) {{ continue }}
  $ver = ''
  try {{ $ver = [string]$u.DriverVerVersion }} catch {{}}
  $rows += [PSCustomObject]@{{
    Title = $title
    Version = $ver
    UpdateId = [string]$u.Identity.UpdateID
  }}
  if ($rows.Count -ge 6) {{ break }}
}}
if ($rows.Count -gt 0) {{ $rows | ConvertTo-Json -Compress }}
"""
    ok, out = dc.run_powershell(ps, timeout=120)
    text = (out or "").strip()
    if not ok or not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = parsed if isinstance(parsed, list) else [parsed]
    offers: list[dict] = []
    for row in rows:
        title = (row.get("Title") or "")[:120]
        ver = (row.get("Version") or "").strip()
        offers.append({
            "source": "windows_update",
            "source_label": "Windows Update (optional)",
            "title": title,
            "version": ver or "—",
            "url": dc._microsoft_catalog_url(title),
            "update_id": (row.get("UpdateId") or "").strip(),
        })
    return offers


def _compare_installed(installed: str, offer_ver: str, *, title: str = "") -> str:
    if not offer_ver or offer_ver in ("—", "?"):
        return "uncertain"
    if not installed or installed in ("—", "?"):
        return "uncertain"
    if dc.compare_firmware_versions:
        try:
            return dc.compare_firmware_versions(installed, offer_ver, title=title)
        except Exception:
            pass
    return dc.compare_driver_to_installed(installed, offer_ver, source=title)[0]


def _summarize_offers(offers: list[dict], installed: str) -> dict:
    enriched = []
    for o in offers:
        vs = _compare_installed(
            installed,
            (o.get("version") or "").strip(),
            title=o.get("title") or "",
        )
        enriched.append({**o, "vs_installed": vs})
    newer = [o for o in enriched if o.get("vs_installed") == "newer"]
    same = [o for o in enriched if o.get("vs_installed") == "same"]
    uncertain = [o for o in enriched if o.get("vs_installed") == "uncertain"]
    if newer:
        status = "update_available"
    elif same:
        status = "up_to_date"
    elif enriched:
        status = "verify_manually"
    else:
        status = "no_offers"
    return {
        "status": status,
        "offers": enriched,
        "update_count": len(newer),
        "same_count": len(same),
        "uncertain_count": len(uncertain),
    }


def _ctx_for_candidate(c: dict) -> dict:
    device_id = c.get("device_id") or ""
    vendor = (c.get("vendor_key") or _vendor_from_device_id(device_id)).lower()
    name = c.get("name") or ""
    if c.get("category") == "usb_peripheral":
        name = _friendly_usb_label(device_id, name)
    return {
        "device_label": name,
        "target_device_name": c.get("name") or name,
        "vendor_key": vendor,
        "pnp_class": (c.get("pnp_class") or "").lower(),
        "instance_id": device_id,
        "primary_version": c.get("installed_version") or "",
    }


def _check_windows_firmware(c: dict, system_ctx: dict, progress) -> dict:
    installed = c.get("installed_version") or ""
    name = c.get("name") or ""
    offers: list[dict] = []
    queries = [
        f"{name} firmware",
        "system firmware",
        "device firmware",
        "embedded controller firmware",
    ]
    mfr = (system_ctx.get("system_manufacturer") or "").strip()
    model = (system_ctx.get("system_model") or "").strip()
    if mfr:
        queries.insert(0, f"{mfr} {model} firmware".strip())
    for q in queries[:5]:
        progress(f"MSCatalog: {q[:50]}…")
        offers.extend(_search_mscatalog_firmware(q))
    progress("Windows Update optional firmware…")
    offers.extend(
        _search_wu_optional_firmware(
            [name.lower(), "system firmware", mfr.lower(), model.lower()]
        )
    )
    return _summarize_offers(offers, installed)


def _check_usb_peripheral(c: dict, progress) -> dict:
    installed = c.get("installed_version") or ""
    device_id = c.get("device_id") or ""
    vendor = _vendor_from_device_id(device_id) or (c.get("vendor_key") or "")
    label = _friendly_usb_label(device_id, c.get("name") or "")
    offers: list[dict] = []
    ctx = _ctx_for_candidate(c)
    ctx["device_id"] = device_id
    ctx["device_label"] = c.get("name") or label

    # Vendor support articles (Razer mysupport, etc.) — before generic utility links.
    try:
        import firmware_peripheral_vendors as fpv

        if vendor in fpv.PERIPHERAL_VENDOR_REGISTRY:
            progress(f"Support article lookup: {vendor}…")
            row = fpv.fetch_vendor_peripheral_firmware(vendor, ctx)
            if row:
                offers.append(fpv.peripheral_offer_from_row(row, installed=installed, device_label=label))
    except ImportError:
        pass
    except Exception as exc:
        offers.append({
            "source": "error",
            "source_label": "Support article lookup",
            "title": f"{vendor} support lookup failed",
            "version": "—",
            "url": "",
            "notes": str(exc)[:120],
        })

    if vendor:
        for q in (
            f"{vendor} firmware",
            f"{vendor} keyboard firmware",
            f"{vendor} peripheral firmware",
        ):
            progress(f"MSCatalog: {q}…")
            offers.extend(_search_mscatalog_firmware(q, limit=3))

    fn = _VENDOR_FETCHERS.get(vendor)
    if fn:
        progress(f"Vendor lookup: {vendor}…")
        try:
            offers.extend(fn(ctx) or [])
        except Exception as exc:
            offers.append({
                "source": "error",
                "source_label": "Vendor lookup",
                "title": f"{vendor} lookup failed",
                "version": "—",
                "url": "",
                "notes": str(exc)[:120],
            })

    has_support_article = any(
        (o.get("source") or "") == "peripheral_vendor"
        and (o.get("url") or "").strip()
        and not o.get("coverage_check_failed")
        for o in offers
    )
    has_published_version = any(
        (o.get("source") or "") == "peripheral_vendor"
        and (o.get("version") or "").strip() not in ("", "—")
        for o in offers
    )

    util = _PERIPHERAL_UTILITY_URLS.get(vendor)
    if util and not has_support_article:
        title, url = util
        notes = (
            "Searched the vendor support site first — no firmware article matched. "
            "MCU firmware may still be on the support portal under your exact model name, "
            "or via the desktop app. Windows only reports the HID driver version."
        )
        if vendor == "razer":
            notes = (
                "Some Razer devices (e.g. Pro Type Ultra) publish firmware only on "
                "mysupport.razer.com — not in Synapse. Search your product name + "
                "'firmware' on Razer Support if no article was matched automatically."
            )
        offers.append({
            "source": "utility",
            "source_label": "Vendor desktop app (fallback)",
            "title": f"{title} — check for {label} firmware",
            "version": "—",
            "url": url,
            "notes": notes,
        })
    elif util and has_support_article and vendor == "razer":
        title, url = util
        offers.append({
            "source": "utility",
            "source_label": "Optional — Synapse",
            "title": f"{title} — lighting/macros only for {label}",
            "version": "—",
            "url": url,
            "notes": (
                "Firmware for this device is updated via the Razer Support article above, "
                "not Synapse. Synapse is optional for lighting and macro configuration."
            ),
        })

    return _summarize_offers(offers, installed)


def _check_driver_bundled(
    c: dict,
    *,
    system_ctx: dict,
    pnp_list: list,
    inventory: list,
    progress,
) -> dict:
    installed = c.get("installed_version") or ""
    name = c.get("name") or ""
    device_id = c.get("device_id") or ""
    vendor = _vendor_from_device_id(device_id) or (c.get("vendor_key") or "")
    ctx = _ctx_for_candidate(c)
    offers: list[dict] = []

    fn = _VENDOR_FETCHERS.get(vendor)
    if fn:
        progress(f"Manufacturer API: {vendor}…")
        try:
            vendor_offers = fn(ctx) or []
            for o in vendor_offers:
                o = dict(o)
                o.setdefault(
                    "notes",
                    "Driver package may include VBIOS/radio firmware — compare versions.",
                )
            offers.extend(vendor_offers)
        except Exception as exc:
            offers.append({
                "source": "error",
                "source_label": "Vendor lookup",
                "title": f"{vendor} lookup failed",
                "version": "—",
                "url": "",
                "notes": str(exc)[:120],
            })

    progress(f"Driver catalog: {name[:50]}…")
    try:
        comp = dc.build_device_driver_comparison(
            name,
            pnp_list,
            inventory,
            system_ctx,
            progress=progress,
        )
        for o in comp.get("offers") or []:
            o = dict(o)
            tl = (o.get("title") or "").lower()
            if "firmware" in tl or vendor in ("nvidia", "amd", "mediatek", "realtek"):
                offers.append(o)
            elif o.get("vs_installed") == "newer":
                offers.append(o)
        if comp.get("skipped_reason") == "firmware_class":
            offers.append({
                "source": "info",
                "source_label": "Catalog",
                "title": "Excluded from driver scan (firmware class)",
                "version": "—",
                "url": "",
                "notes": "Use firmware-specific sources above.",
            })
    except Exception as exc:
        offers.append({
            "source": "error",
            "source_label": "Driver catalog",
            "title": "Driver comparison failed",
            "version": "—",
            "url": "",
            "notes": str(exc)[:160],
        })

    fw_queries = []
    if vendor:
        fw_queries.append(f"{vendor} firmware")
    if "nvidia" in name.lower() or "geforce" in name.lower():
        fw_queries.append("nvidia vbios firmware")
    if "realtek" in name.lower():
        fw_queries.append("realtek firmware")
    if "mediatek" in name.lower() or "mt7921" in name.lower():
        fw_queries.append("mediatek firmware")
    for q in fw_queries[:3]:
        progress(f"MSCatalog firmware: {q}…")
        offers.extend(_search_mscatalog_firmware(q, limit=2))

    return _summarize_offers(offers, installed)


def _attach_primary_results(c: dict, fw_result: dict) -> dict:
    installed = c.get("installed_version") or ""
    kind = "bios" if c.get("category") == "bios" else "ssd"
    offers: list[dict] = []
    for o in fw_result.get("offers") or []:
        if o.get("kind") != kind:
            if kind == "ssd" and o.get("kind") not in ("ssd", "utility"):
                continue
            if kind == "bios" and o.get("kind") not in ("bios", "link", "utility"):
                continue
        offers.append(dict(o))

    if kind == "ssd" and c.get("name"):
        model = c.get("name")
        offers = [
            o
            for o in offers
            if not o.get("installed_model")
            or (o.get("installed_model") or "").lower() == model.lower()
            or model.lower() in (o.get("title") or "").lower()
            or o.get("kind") == "utility"
            or o.get("source") == "utility"
        ]

    if not offers:
        return {
            "status": "verify_manually",
            "offers": [],
            "update_count": 0,
            "same_count": 0,
            "uncertain_count": 0,
            "note": "No catalog rows matched this primary device.",
        }

    newer = [o for o in offers if o.get("vs_installed") == "newer"]
    same = [o for o in offers if o.get("vs_installed") == "same"]
    uncertain = [o for o in offers if o.get("vs_installed") == "uncertain"]
    if newer:
        status = "update_available"
    elif same:
        status = "up_to_date"
    elif uncertain:
        status = "verify_manually"
    else:
        status = "verify_manually"
    return {
        "status": status,
        "offers": offers,
        "update_count": len(newer),
        "same_count": len(same),
        "uncertain_count": len(uncertain),
    }


def run_comprehensive_scan(progress=None) -> dict:
    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    prog("Discovering firmware-capable devices…")
    discovery = discover_firmware_capable_devices()
    candidates = discovery.get("candidates") or []

    prog("Loading hardware profile…")
    prof = get_hardware_profile_wmi_bundle() or {}
    drv_info = get_bios_and_driver_versions(include_all=True)
    inventory = list(drv_info.get("all_drivers") or drv_info.get("device_inventory") or [])
    pnp_list = list(prof.get("pnp_list") or [])
    bios_info = (prof.get("bios_driver_info") or {}).get("bios") or drv_info.get("bios") or {}
    ssd_list = get_ssd_firmware_inventory()

    system_ctx = {
        k: prof.get(k)
        for k in (
            "pnp_list",
            "present_drivers",
            "system_manufacturer",
            "system_model",
            "system_product_uuid",
            "gpu_vendor",
            "gpu_vendors_present",
            "has_amd_chipset",
            "has_intel_chipset",
            "has_sata",
            "has_nvme",
            "disk_rows",
            "video_controllers",
            "baseboard_manufacturer",
            "baseboard_product",
        )
        if prof.get(k) is not None
    }
    system_ctx["_gui_driver_catalog"] = True
    system_ctx = dc.extend_system_ctx_for_catalog(system_ctx)

    prog("Primary firmware pipeline (BIOS + SSD)…")
    dc.set_gui_catalog_session(True)
    try:
        dc.ensure_mscatalog_module_ready(progress=prog)
        if not dc._should_skip_online_driver_store(system_ctx, system_ctx):
            dc.ensure_online_driver_store_loaded(progress=prog)
        fw_result = fwcat.build_firmware_comparison(
            bios_info,
            system_ctx,
            pnp_list,
            ssd_list,
            progress=prog,
        )
    finally:
        dc.set_gui_catalog_session(False)

    device_results: list[dict] = []
    for i, c in enumerate(candidates, 1):
        cat = c.get("category") or ""
        tier = c.get("tier") or ""
        label = c.get("name") or "Device"
        prog(f"[{i}/{len(candidates)}] Checking {cat}: {label[:55]}…")

        if cat in ("bios", "ssd"):
            summary = _attach_primary_results(c, fw_result)
            sources = sorted({o.get("source_label") or o.get("source") for o in summary["offers"]})
        elif cat == "windows_firmware":
            summary = _check_windows_firmware(c, system_ctx, prog)
            sources = sorted({o.get("source_label") or o.get("source") for o in summary["offers"]})
        elif cat == "usb_peripheral":
            summary = _check_usb_peripheral(c, prog)
            sources = sorted({o.get("source_label") or o.get("source") for o in summary["offers"]})
        else:
            summary = _check_driver_bundled(
                c,
                system_ctx=system_ctx,
                pnp_list=pnp_list,
                inventory=inventory,
                progress=prog,
            )
            sources = sorted({o.get("source_label") or o.get("source") for o in summary["offers"]})

        device_results.append({
            "device": c,
            "check_summary": {
                "status": summary["status"],
                "update_count": summary["update_count"],
                "same_count": summary.get("same_count", 0),
                "uncertain_count": summary.get("uncertain_count", 0),
                "sources_checked": sources,
                "top_offers": [
                    {
                        "title": o.get("title"),
                        "version": o.get("version"),
                        "vs_installed": o.get("vs_installed"),
                        "source_label": o.get("source_label") or o.get("source"),
                        "url": o.get("url"),
                    }
                    for o in (summary.get("offers") or [])[:5]
                ],
            },
        })

    totals = {
        "devices_checked": len(device_results),
        "update_available": sum(
            1 for r in device_results if r["check_summary"]["status"] == "update_available"
        ),
        "up_to_date": sum(
            1 for r in device_results if r["check_summary"]["status"] == "up_to_date"
        ),
        "verify_manually": sum(
            1 for r in device_results if r["check_summary"]["status"] == "verify_manually"
        ),
        "no_offers": sum(
            1 for r in device_results if r["check_summary"]["status"] == "no_offers"
        ),
    }

    return {
        "system": discovery.get("system") or {},
        "discovery_summary": discovery.get("summary") or {},
        "scan_totals": totals,
        "primary_firmware_scan": {
            "fetched_at": fw_result.get("fetched_at"),
            "scan_mode": fw_result.get("scan_mode"),
            "offer_count": len(fw_result.get("offers") or []),
        },
        "device_results": device_results,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _print_report(data: dict) -> None:
    sys_info = data.get("system") or {}
    totals = data.get("scan_totals") or {}
    print("=" * 72)
    print("BSOD Analyzer — comprehensive firmware update scan")
    print("=" * 72)
    print(f"PC: {sys_info.get('manufacturer')} {sys_info.get('model')}")
    print(f"Scanned at: {data.get('fetched_at')}")
    print()
    print("Totals:")
    print(f"  Devices checked:     {totals.get('devices_checked', 0)}")
    print(f"  Update available:    {totals.get('update_available', 0)}")
    print(f"  Up to date:          {totals.get('up_to_date', 0)}")
    print(f"  Verify manually:     {totals.get('verify_manually', 0)}")
    print(f"  No offers found:     {totals.get('no_offers', 0)}")
    print()

    status_order = ("update_available", "verify_manually", "up_to_date", "no_offers")
    labels = {
        "update_available": "UPDATES AVAILABLE",
        "verify_manually": "VERIFY MANUALLY",
        "up_to_date": "UP TO DATE",
        "no_offers": "NO OFFERS FOUND",
    }
    by_status: dict[str, list] = {k: [] for k in status_order}
    for row in data.get("device_results") or []:
        st = (row.get("check_summary") or {}).get("status") or "no_offers"
        by_status.setdefault(st, []).append(row)

    for st in status_order:
        rows = by_status.get(st) or []
        if not rows:
            continue
        print("-" * 72)
        print(f"{labels.get(st, st.upper())} ({len(rows)})")
        print("-" * 72)
        for row in rows:
            dev = row.get("device") or {}
            summ = row.get("check_summary") or {}
            print(f"• [{dev.get('tier')}/{dev.get('category')}] {dev.get('name')}")
            print(f"  Installed: {dev.get('installed_version') or '—'}")
            print(f"  Sources: {', '.join(summ.get('sources_checked') or []) or '—'}")
            for o in summ.get("top_offers") or []:
                vs = o.get("vs_installed") or "?"
                print(
                    f"    [{vs}] {o.get('source_label')}: "
                    f"{(o.get('title') or '')[:65]} "
                    f"(v{o.get('version') or '?'})"
                )
            print()


def main() -> int:
    def progress(msg: str) -> None:
        print(f"  … {msg}")

    data = run_comprehensive_scan(progress=progress)
    print()
    _print_report(data)
    out = ROOT / "live_firmware_comprehensive_update_scan.json"
    out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"Full JSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
