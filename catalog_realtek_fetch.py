"""Realtek vendor download-center scrape and offer fetch (extracted from driver_catalog)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from catalog_scoring import (
    _realtek_net_version_major,
    parse_driver_package_date,
    parse_driver_version,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_REALTEK_BASE = "https://www.realtek.com"
_REALTEK_LIST_PAGE = _REALTEK_BASE + "/Download/List?cate_id={cate_id}"
_REALTEK_LIST_API = _REALTEK_BASE + "/Download/ListAllDownloadItem?cate_id={cate_id}"
_REALTEK_CATE_PAGES: dict[str, str] = {
    "593": "HD Audio codecs",
    "584": "PCIe Ethernet (FE/GbE/2.5G/5G/10G)",
    "583": "PCI GbE Ethernet",
    "585": "USB Ethernet",
    "587": "PCI Fast Ethernet",
}
_REALTEK_PCI_DEV_CATE: dict[str, str] = {
    "8125": "584",
    "8126": "584",
    "8136": "584",
    "8161": "584",
    "8162": "584",
    "8163": "584",
    "8167": "584",
    "8168": "584",
    "8152": "585",
    "8153": "585",
    "8156": "585",
    "8157": "585",
    "8159": "585",
    "8139": "587",
}


def _realtek_cate_id_for_ctx(ctx: dict) -> tuple[str | None, str]:
    """Pick Realtek download-center category for this device context."""
    pnp = (ctx.get("pnp_class") or "").lower()
    label = (ctx.get("device_label") or "").lower()
    hw = (ctx.get("hw_category") or "").lower()
    inst = (ctx.get("instance_id") or "").upper()
    dev_m = re.search(r"DEV_([0-9A-F]{4})", inst)
    dev = dev_m.group(1) if dev_m else ""
    if dev in _REALTEK_PCI_DEV_CATE:
        return _REALTEK_PCI_DEV_CATE[dev], f"pci_dev_{dev.lower()}"
    if pnp == "media" or hw == "audio" or any(
        k in label for k in ("audio", "sound", "speaker", "microphone", "codec")
    ):
        return "593", "audio"
    if pnp == "net" or hw == "network":
        if any(k in label for k in ("wireless", "wi-fi", "wifi", "wlan", "802.11")):
            return None, "wifi_oem"
        if "usb" in label:
            return "585", "usb_nic"
        if any(k in label for k in ("2.5", "2.5g", "5g", "10g", "8125")):
            return "584", "pcie_nic"
        if "pci" in label and "pcie" not in label and "express" not in label:
            return "583", "pci_nic"
        return "584", "pcie_nic"
    if pnp == "bluetooth" or "bluetooth" in label:
        return None, "bluetooth_oem"
    return None, "generic"


def _realtek_abs_url(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return _REALTEK_BASE + "/Download"
    if p.startswith("http://") or p.startswith("https://"):
        return p
    if not p.startswith("/"):
        p = "/" + p
    return _REALTEK_BASE + p


def _realtek_normalize_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _realtek_windows_download_score(item: dict) -> tuple:
    """Rank Realtek download rows — prefer main Windows driver installers."""
    name = (item.get("Name") or "").lower()
    desc = (item.get("Description") or "").lower()
    ver = parse_driver_version(item.get("Version") or "") or ()
    score = 0
    if (item.get("OSName") or "").lower() == "windows":
        score += 40
    if "install" in name or "auto installation" in desc:
        score += 30
    if any(k in desc for k in ("win11", "windows 11", "win10", "windows 10")):
        score += 20
    if "diagnostic" in name or "diagnostic" in desc:
        score -= 50
    if "beta" in name or "beta" in desc:
        score -= 60
    if "readme" in name:
        score -= 40
    date_str = _realtek_normalize_date(item.get("UpdateTime") or "")
    parsed = parse_driver_package_date(date_str)
    date_key = parsed or date(1970, 1, 1)
    return (score, ver, date_key)


def _realtek_rows_from_api_payload(data: dict) -> list[dict]:
    """Parse ListAllDownloadItem JSON into normalized scrape rows."""
    block = data.get("Data") or {}
    title = (block.get("Title") or "Realtek driver").strip()
    dl_items = block.get("DownloadItems") or {}
    rows: list[dict] = []
    if isinstance(dl_items, dict):
        for _os_name, items in dl_items.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if (item.get("OSName") or _os_name or "").lower() != "windows":
                    continue
                ver = (item.get("Version") or "").strip()
                if not ver:
                    continue
                rows.append({
                    "title": title,
                    "package_name": (item.get("Name") or title).strip(),
                    "description": (item.get("Description") or "").strip(),
                    "version": ver,
                    "date": _realtek_normalize_date(item.get("UpdateTime") or ""),
                    "url": _realtek_abs_url(item.get("DownloadUrl") or ""),
                })
    return rows


def _realtek_installed_version_from_ctx(ctx: dict) -> str:
    inst = (ctx.get("primary_version") or "").strip()
    for inv in ctx.get("installed_rows") or []:
        inst = inst or (inv.get("version") or "").strip()
    return inst


def _realtek_row_score(r: dict) -> int:
    return _realtek_windows_download_score({
        "Name": r.get("package_name"),
        "Description": r.get("description"),
        "Version": r.get("version"),
        "OSName": "Windows",
        "UpdateTime": r.get("date"),
    })


def _realtek_version_trustworthy(cate_id: str, version: str) -> bool:
    """Legacy Realtek HDA uses R2.xx — not comparable to inbox UAD 6.0.x."""
    ver = (version or "").strip()
    if not ver:
        return False
    if cate_id == "593":
        if re.match(r"R\d", ver, re.I):
            return False
        parts = parse_driver_version(ver)
        if not parts:
            return False
        return len(parts) >= 2 and parts[0] == 6
    return bool(parse_driver_version(ver))


def _realtek_best_row_for_ctx(rows: list[dict], cate_id: str, ctx: dict) -> dict | None:
    """Pick Realtek.com row: UAD 6.0.x for audio; same NIC major family as installed."""
    if not rows:
        return None
    inst = _realtek_installed_version_from_ctx(ctx)
    pool = rows
    if cate_id == "593":
        uad_rows = [
            r for r in rows
            if _realtek_version_trustworthy(cate_id, r.get("version") or "")
        ]
        if uad_rows:
            pool = uad_rows
    elif cate_id in ("584", "583", "585", "587"):
        im = _realtek_net_version_major(inst)
        if im:
            same_family = [
                r for r in rows
                if _realtek_net_version_major(r.get("version") or "") == im
            ]
            if same_family:
                pool = same_family
    return max(pool, key=_realtek_row_score)


def _scrape_realtek_category_rows(cate_id: str) -> list[dict]:
    from catalog_mscatalog_session import is_quick_check_mode

    if is_quick_check_mode():
        return []
    cache_key = f"realtek:{cate_id}"
    cached = _dc("_vendor_scrape_cache_get")(cache_key)
    if cached and isinstance(cached, tuple) and len(cached) >= 4:
        all_rows = cached[3]
        if isinstance(all_rows, list) and all_rows:
            return all_rows
    if cached and isinstance(cached, tuple) and len(cached) >= 3:
        best = cached[2]
        if isinstance(best, dict) and best.get("version"):
            return [best]
    page = _REALTEK_LIST_PAGE.format(cate_id=cate_id)
    api = _REALTEK_LIST_API.format(cate_id=cate_id)
    ok, body = _dc("_http_get")(
        api,
        headers={"Accept": "application/json, text/plain, */*"},
        referer=page,
        insecure_fallback=True,
    )
    if not ok or not body.lstrip().startswith("{"):
        return []
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not payload.get("Pass"):
        return []
    rows = _realtek_rows_from_api_payload(payload)
    if not rows:
        return []
    best = max(rows, key=_realtek_row_score)
    _dc("_vendor_scrape_cache_set")(
        cache_key,
        (best.get("version") or "", best.get("date") or "", best, rows),
    )
    return rows


def fetch_realtek_driver_offers(ctx: dict) -> list[dict]:
    """Realtek download-center scrape (v6): versioned Windows packages by product category."""
    if not _dc("_v6_catalog_enabled")():
        return []
    vk = (ctx.get("vendor_key") or "").lower()
    if vk != "realtek":
        return []
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        "realtek", _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    cate_id, hint = _realtek_cate_id_for_ctx(ctx)
    fallback_url, fallback_title = _dc("_VENDOR_DRIVER_URLS").get(
        "realtek",
        (_REALTEK_BASE + "/Download", "Realtek driver downloads"),
    )
    if not cate_id:
        note = (
            "Realtek Wi‑Fi / Bluetooth packages are often OEM-specific; "
            "use Microsoft catalog results or your PC maker's support site."
            if hint in ("wifi_oem", "bluetooth_oem")
            else "Could not map this Realtek device to a Realtek.com category."
        )
        return [{
            "source": "vendor",
            "source_label": "Manufacturer (Realtek)",
            "title": fallback_title,
            "version": "",
            "date": "",
            "url": fallback_url,
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": note,
            "confidence": "low",
        }]
    list_url = _REALTEK_LIST_PAGE.format(cate_id=cate_id)
    product_label = _REALTEK_CATE_PAGES.get(cate_id, "Realtek drivers")
    rows = _dc("_scrape_realtek_category_rows")(cate_id)
    if not rows:
        return [{
            "source": "vendor",
            "source_label": "Manufacturer (Realtek)",
            "title": f"{product_label} — Realtek download center",
            "version": "",
            "date": "",
            "url": list_url,
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": "Realtek API did not return a version; open the product page manually.",
            "confidence": "low",
        }]
    best = _realtek_best_row_for_ctx(rows, cate_id, ctx)
    if not best:
        best = max(rows, key=_realtek_row_score)
    pkg = (best.get("package_name") or best.get("title") or product_label).strip()
    ver = (best.get("version") or "").strip()
    confidence = "medium"
    notes = (
        f"Latest Windows package from Realtek.com ({product_label}). "
        "Confirm chip model on Realtek's site before installing."
    )
    offer_extra: dict = {}
    if not _realtek_version_trustworthy(cate_id, ver):
        notes = (
            f"Realtek.com lists legacy HDA packages for {product_label}. "
            "Modern Realtek UAD (6.0.x) is checked via Microsoft Update Catalog "
            "and your PC maker's driver catalog — compare those results first."
        )
        ver = ""
        confidence = "low"
        offer_extra = {"informational_only": True, "status_neutral": True}
    elif cate_id in ("584", "583", "585", "587"):
        site_latest = max(rows, key=_realtek_row_score)
        bm = _realtek_net_version_major(best.get("version") or "")
        sm = _realtek_net_version_major(site_latest.get("version") or "")
        if best is not site_latest and bm and sm and bm != sm:
            notes = (
                f"Matched installed Realtek NIC {bm}.x family on Realtek.com "
                f"(site also lists {sm}.x packages for other adapters)."
            )
    pkg_url = best.get("url") or list_url
    install_verified = bool(
        pkg_url
        and any(
            pkg_url.lower().split("?")[0].endswith(ext)
            for ext in _dc("_DOWNLOAD_EXTENSIONS")
        )
    )
    return [{
        "source": "vendor",
        "source_label": "Manufacturer (Realtek)",
        "title": pkg[:120],
        "version": ver,
        "date": best.get("date") or "",
        "url": pkg_url,
        "vendor_page_url": list_url if pkg_url != list_url else "",
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": notes,
        "confidence": "high" if ver and install_verified else confidence,
        "download_resolvable": install_verified or "todownload" in pkg_url.lower(),
        "install_verified": install_verified,
        **offer_extra,
    }]
