"""Live OEM API fetch and row cache (extracted from driver_catalog)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable

import oem_effective_version as oev
from catalog_scoring import (
    compare_versions,
    extract_version_from_text,
    parse_driver_version,
)

_HTTP_TIMEOUT = 22
_OEM_MIN_MATCH_SCORE = 5


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def clear_oem_cache() -> None:
    _dc('_OEM_ROWS_CACHE').clear()
    _dc('clear_vendor_scrape_cache')()
    try:
        import catalog_cache as ccat
        ccat.clear_oem_cache_file()
    except ImportError:
        pass

def _warm_oem_session_cache(system_ctx: dict | None) -> None:
    """Load raw OEM catalog rows once per batch (per-device filtering happens later)."""
    try:
        import oem_enterprise_catalog as oec
        oec.clear_session_cache()
    except ImportError:
        pass
    if _dc('is_quick_check_mode')() or not _dc('_oem_session_cache_enabled'):
        return
    try:
        import catalog_cache as ccat
    except ImportError:
        ccat = None  # type: ignore[assignment]
    if ccat and ccat.should_use_disk_cache():
        offers, blob = ccat.load_oem_offers(system_ctx)
        if blob and offers:
            return
    for tag, fn in _oem_live_row_warmers(system_ctx):
        try:
            _cached_oem_rows(tag, fn, system_ctx)
        except Exception:
            continue

def _oem_row_cache_key(oem_tag: str, system_ctx: dict | None) -> str:
    try:
        import catalog_cache as ccat
        fp = ccat.machine_fingerprint(system_ctx)
    except ImportError:
        ctx = system_ctx or {}
        fp = (
            f"{(ctx.get('system_manufacturer') or '').lower()}|"
            f"{(ctx.get('system_model') or '').lower()}"
        )
    return f"rows:{oem_tag}:{fp}"

def _cached_oem_rows(
    oem_tag: str,
    fetch_fn: Callable[[dict | None], tuple[list[dict], str]],
    system_ctx: dict | None,
) -> tuple[list[dict], str]:
    """Cache raw OEM catalog rows per machine identity (filter per device afterward)."""
    if not _dc('_oem_session_cache_enabled'):
        return fetch_fn(system_ctx)
    key = _oem_row_cache_key(oem_tag, system_ctx)
    with _dc('_CATALOG_CACHE_LOCK'):
        now = time.monotonic()
        hit = _dc('_OEM_ROWS_CACHE').get(key)
        if hit and (now - hit[1]) < _dc('_OEM_CACHE_TTL_SEC'):
            _dc('_lru_cache_touch')(_dc('_OEM_ROWS_CACHE'), key)
            rows, fallback = hit[0]
            return list(rows), fallback
        rows, fallback = fetch_fn(system_ctx)
        _dc('_lru_cache_set')(
            _dc('_OEM_ROWS_CACHE'),
            key,
            ((list(rows), fallback), now),
            max_entries=_dc('_OEM_CACHE_MAX_ENTRIES'),
        )
        return rows, fallback

def _oem_live_row_warmers(system_ctx: dict | None) -> list[tuple[str, Callable]]:
    """OEM APIs whose raw rows can be warmed once per batch scan."""
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb = (ctx.get("baseboard_manufacturer") or "").lower()
    warmers: list[tuple[str, Callable]] = []
    if "dell" in mfr or "alienware" in mfr:
        warmers.append(("dell", lambda ctx: _dc("_fetch_dell_oem_rows_live")(ctx)))
    if "lenovo" in mfr or "thinkpad" in mfr or "ideapad" in mfr:
        warmers.append(("lenovo", lambda ctx: _dc("_fetch_lenovo_oem_rows_live")(ctx)))
    if "hp" in mfr or "hewlett" in mfr:
        warmers.append(("hp", lambda ctx: _dc("_fetch_hp_oem_rows_live")(ctx)))
    if "asus" in mfr or "rog" in mfr or _manufacturer_matches(bb, "asus"):
        warmers.append(("asus", lambda ctx: _dc("_fetch_asus_oem_rows_live")(ctx)))
    if _manufacturer_matches(mfr, "msi", "micro-star") or _manufacturer_matches(bb, "msi"):
        warmers.append(("msi", lambda ctx: _dc("_fetch_msi_oem_rows_live")(ctx)))
    if _manufacturer_matches(mfr, "gigabyte", "aorus") or _manufacturer_matches(bb, "gigabyte", "aorus"):
        warmers.append(("gigabyte", lambda ctx: _dc("_fetch_gigabyte_oem_rows_live")(ctx)))
    if "acer" in mfr:
        warmers.append(("acer", lambda ctx: _dc("_fetch_acer_oem_rows_live")(ctx)))
    return warmers

def _system_has_msi_oem(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb = (ctx.get("baseboard_manufacturer") or "").lower()
    return _manufacturer_matches(mfr, "msi", "micro-star") or _manufacturer_matches(bb, "msi")

def _system_has_gigabyte_oem(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb = (ctx.get("baseboard_manufacturer") or "").lower()
    return _manufacturer_matches(mfr, "gigabyte", "aorus") or _manufacturer_matches(bb, "gigabyte", "aorus")

_DELL_DRIVER_ID_RE = re.compile(r"[?&]driverId=([A-Z0-9]+)", re.I)

_DELL_FILE_LOCATION_RE = re.compile(
    r"FileLocation\s*:\s*['\"]?(https?://[^'\"\s]+)['\"]?",
    re.I,
)

_DELL_DL_DIRECT_RE = re.compile(
    r"https://dl\.dell\.com/[^\s\"'<>]+\.(?:exe|cab|zip|msi)",
    re.I,
)

def _is_dell_driver_details_url(url: str) -> bool:
    low = (url or "").lower()
    return "dell.com" in low and "driversdetails" in low and "driverid=" in low

def _resolve_dell_driver_download_url(page_url: str) -> tuple[bool, str, str]:
    """Resolve Dell DriversDetails page → dl.dell.com direct package URL."""
    page_url = (page_url or "").strip()
    if not page_url:
        return False, "Missing Dell driver page URL.", ""
    ok, html = _dc('_http_get')(
        page_url,
        referer="https://www.dell.com/support/home/en-us",
    )
    if not ok:
        return False, f"Could not load Dell driver page ({html}).", ""
    match = _DELL_FILE_LOCATION_RE.search(html)
    if match:
        return True, "", match.group(1).rstrip("'\"")
    hits = _DELL_DL_DIRECT_RE.findall(html)
    if hits:
        return True, "", hits[0]
    return False, "Dell driver page did not expose a direct download link.", ""

def _fetch_live_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    """Query OEM APIs directly when the on-disk OEM cache is empty (per device check)."""
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    bb = ((system_ctx or {}).get("baseboard_manufacturer") or "").lower()
    offers: list[dict] = []
    if "dell" in mfr or "alienware" in mfr:
        try:
            offers.extend(_dc("fetch_dell_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("dell OEM live fetch", exc)
    if "lenovo" in mfr or "thinkpad" in mfr or "ideapad" in mfr:
        try:
            offers.extend(_dc("fetch_lenovo_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("lenovo OEM live fetch", exc)
    if "hp" in mfr or "hewlett" in mfr:
        try:
            offers.extend(_dc("fetch_hp_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("hp OEM live fetch", exc)
    if "asus" in mfr or "rog" in mfr or _manufacturer_matches(bb, "asus"):
        try:
            offers.extend(_dc("fetch_asus_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("asus OEM live fetch", exc)
    if _system_has_msi_oem(system_ctx):
        try:
            offers.extend(_dc("fetch_msi_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("msi OEM live fetch", exc)
    if _system_has_gigabyte_oem(system_ctx):
        try:
            offers.extend(_dc("fetch_gigabyte_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("gigabyte OEM live fetch", exc)
    if "acer" in mfr:
        try:
            offers.extend(_dc("fetch_acer_oem_offers")(ctx, system_ctx))
        except Exception as exc:
            _dc('_log_catalog_skip')("acer OEM live fetch", exc)
    return offers


_DELL_SERVICE_TAG_PS_CACHE: str | None = None


def _dell_service_tag(system_ctx: dict | None) -> str | None:
    global _DELL_SERVICE_TAG_PS_CACHE
    tag = (system_ctx or {}).get("service_tag") or ""
    if tag and len(tag) >= 5 and tag.upper() not in ("NONE", "DEFAULT", "TO BE FILLED", "SYSTEM SERIAL"):
        return tag.strip()
    if _DELL_SERVICE_TAG_PS_CACHE:
        return _DELL_SERVICE_TAG_PS_CACHE
    ok, out = _dc('_run_catalog_ps')(
        r"(Get-CimInstance Win32_BIOS -EA 0 | Select-Object -ExpandProperty SerialNumber | Out-String).Trim()"
    )
    if ok and out and len(out) >= 5:
        _DELL_SERVICE_TAG_PS_CACHE = out.splitlines()[0].strip()
        return _DELL_SERVICE_TAG_PS_CACHE
    return None

_DELL_DUP_NS = "{openmanage/cm/dm}"

def _dell_dup_catalog_paths(system_ctx: dict | None) -> list[str]:
    """Local Dell/Alienware Update Service manifest(s) for this system SKU."""
    sku = ((system_ctx or {}).get("system_sku") or "").strip().upper()
    base = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Dell", "UpdateService", "Temp")
    if not os.path.isdir(base):
        return []
    paths: list[str] = []
    if sku:
        for name in os.listdir(base):
            if not name.lower().endswith(".xml"):
                continue
            stem = name[:-4]
            if stem.upper().endswith(f"_{sku}") or f"_{sku}_" in stem.upper():
                paths.append(os.path.join(base, name))
    if not paths:
        mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
        if "dell" in mfr or "alienware" in mfr:
            for name in os.listdir(base):
                if name.lower().endswith(".xml") and (
                    name.lower().startswith("alienware_") or name.lower().startswith("dell_")
                ):
                    paths.append(os.path.join(base, name))
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths

def _dell_dup_display_text(parent, tag: str) -> str:
    if parent is None:
        return ""
    for el in parent.findall(f".//{_DELL_DUP_NS}{tag}"):
        for disp in el.findall(f"{_DELL_DUP_NS}Display"):
            text = (disp.text or "").strip()
            if text:
                return text
    return ""

def parse_dell_software_manifest_root(root: ET.Element) -> list[dict]:
    """Parse Dell DUP / driver-pack metadata XML (SoftwareComponent entries)."""
    base_loc = (root.get("baseLocation") or "downloads.dell.com").strip("/")
    best: dict[tuple[str, str], dict] = {}
    for comp in root.findall(f".//{_DELL_DUP_NS}SoftwareComponent"):
        title = _dell_dup_display_text(comp, "Name")
        if not title:
            continue
        ver = (comp.get("vendorVersion") or comp.get("dellVersion") or "").strip()
        if not ver:
            continue
        rel = (comp.get("releaseID") or comp.get("packageID") or "").strip()
        date_raw = _dc('_normalize_oem_date')(comp.get("releaseDate") or comp.get("dateTime") or "")
        cat = _dell_dup_display_text(comp, "Category")
        rel_path = (comp.get("path") or "").strip()
        url = ""
        if rel_path:
            url = f"https://{base_loc}/{rel_path.lstrip('/')}"
        else:
            info = comp.find(f"{_DELL_DUP_NS}ImportantInfo")
            if info is not None and info.get("URL"):
                url = info.get("URL") or ""
            elif rel:
                url = (
                    "https://www.dell.com/support/home/us/en/19/Drivers/"
                    f"DriversDetails?driverId={rel}"
                )
        inner_versions = oev.parse_dell_dup_component_inner_versions(comp)
        row = {
            "title": title,
            "version": ver,
            "date": date_raw,
            "url": url,
            "category": cat,
        }
        if inner_versions:
            row["inner_versions"] = inner_versions
        key = (title.lower(), cat.lower())
        prev = best.get(key)
        if not prev or compare_versions(prev.get("version") or "", ver) in ("newer", "unknown"):
            best[key] = row
    return list(best.values())

def _parse_dell_dup_manifest(path: str) -> list[dict]:
    """Parse Dell Update Service DUP catalog XML into OEM catalog rows."""
    try:
        with open(path, encoding="utf-16", errors="replace") as fh:
            root = ET.fromstring(fh.read())
    except (OSError, ET.ParseError):
        return []
    return parse_dell_software_manifest_root(root)

def _merge_enterprise_oem_rows(
    rows: list[dict],
    system_ctx: dict | None,
    vendor: str,
) -> list[dict]:
    """Supplement OEM API rows from official enterprise deployment catalogs."""
    if not rows and vendor not in ("dell", "hp", "lenovo"):
        return rows
    try:
        import oem_enterprise_catalog as oec
    except ImportError:
        return rows
    fn = {
        "dell": oec.dell_enterprise_rows,
        "hp": oec.hp_enterprise_rows,
        "lenovo": oec.lenovo_enterprise_rows,
    }.get(vendor)
    if not fn:
        return rows
    try:
        extra = fn(system_ctx)
        if extra:
            return oec.merge_oem_row_lists(rows, extra)
    except Exception as exc:
        _dc('_log_catalog_skip')(f"{vendor} enterprise OEM merge", exc)
    return rows

def _get_dell_oem_rows_from_local_dup(system_ctx: dict | None) -> list[dict]:
    for path in _dell_dup_catalog_paths(system_ctx):
        rows = _parse_dell_dup_manifest(path)
        if rows:
            return rows
    return []

def _get_dell_oem_rows_from_api(system_ctx: dict | None) -> list[dict]:
    tag = _dell_service_tag(system_ctx)
    if not tag:
        return []
    url = f"https://www.dell.com/support/home/api/v1/drivers/latest/{urllib.parse.quote(tag)}"
    ok, body = _dc('_http_get')(url, headers={"Accept": "application/json"})
    if not ok or not body:
        return []
    try:
        payload = json.loads(body)
        return _normalize_oem_driver_rows(payload)
    except (json.JSONDecodeError, TypeError):
        return []

def _oem_search_keywords(ctx: dict) -> list[str]:
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _dc('_ctx_device_label')(ctx)
    keywords: list[str] = []
    is_gpu_row = pnp == "display" or any(
        k in label for k in ("geforce", "radeon", "graphics", "arc ", "iris", "uhd graphics")
    )
    if is_gpu_row:
        keywords.extend(["video", "graphics", "display", "gpu", "radeon", "geforce", vk])
    elif pnp in ("media", "audio", "audioendpoint") or "audio" in label:
        keywords.extend(["audio", "sound"])
        if vk:
            keywords.append(vk)
    elif (
        vk in ("nvidia", "amd", "intel")
        and ctx.get("hw_category") != "chipset"
        and not _dc('_nvidia_is_audio_or_usb_component')(ctx)
        and pnp not in ("media", "audio", "audioendpoint")
    ):
        keywords.extend(["video", "graphics", "display", "gpu", vk])
    elif pnp == "net":
        keywords.extend(["network", "wireless", "wi-fi", "wifi", "ethernet", "wlan", "bluetooth"])
    elif ctx.get("hw_category") == "chipset":
        keywords.extend(["chipset", "system", "amd", "intel", "platform"])
    elif pnp == "audio":
        keywords.extend(["audio", "sound", "realtek"])
    else:
        keywords.append(vk or "driver")
    if vk:
        keywords.insert(0, vk)
    return list(dict.fromkeys(k for k in keywords if k))

def _oem_pnp_category_hints(pnp: str) -> list[str]:
    """Map PnP class to common OEM driver category words (Dell/HP/Lenovo listings)."""
    p = (pnp or "").lower()
    hints: dict[str, list[str]] = {
        "display": ["video", "graphics", "display", "gpu"],
        "net": ["network", "wireless", "wi-fi", "wifi", "ethernet", "wlan", "bluetooth"],
        "media": ["audio", "sound", "realtek", "microphone", "speaker"],
        "audioendpoint": ["audio", "sound"],
        "hdc": ["storage", "sata", "nvme", "raid", "ahci"],
        "scsiadapter": ["storage", "sata", "nvme", "raid"],
        "usb": ["usb", "chipset", "controller"],
        "system": ["chipset", "system", "platform"],
        "monitor": ["monitor", "display"],
        "bluetooth": ["bluetooth", "wireless"],
        "biometric": ["fingerprint", "biometric"],
        "image": ["camera", "webcam", "imaging"],
    }
    return hints.get(p, [])

def _oem_row_match_score(row: dict, ctx: dict) -> int:
    """Keyword/category alignment for OEM rows — excludes version presence bonus."""
    bonus = 4 if (row.get("version") or "").strip() else 0
    return _score_oem_row_for_ctx(row, ctx) - bonus

def _oem_row_eligible_for_ctx(row: dict, ctx: dict, *, min_match: int = _OEM_MIN_MATCH_SCORE) -> bool:
    if _dc('_shared_catalog_row_rejects')(row, ctx):
        return False
    return _oem_row_match_score(row, ctx) >= min_match

def _is_generic_oem_support_row(row: dict) -> bool:
    title = (row.get("title") or "").lower()
    if row.get("version"):
        return False
    if "support" in title and ("—" in title or " - " in title):
        return True
    if title.endswith("your model") or title.endswith("support"):
        return True
    return False

def _score_oem_driver_entry(title: str, category: str, keywords: list[str]) -> int:
    t = (title or "").lower()
    c = (category or "").lower()
    return sum(2 for kw in keywords if kw and (kw in t or kw in c))

def _score_oem_row_for_ctx(row: dict, ctx: dict) -> int:
    """Score an OEM catalog row against a device context (stronger than keyword-only)."""
    title = row.get("title") or ""
    cat = row.get("category") or ""
    keywords = _oem_search_keywords(ctx)
    score = _score_oem_driver_entry(title, cat, keywords)
    title_l = title.lower()
    cat_l = cat.lower()
    label = (ctx.get("device_label") or ctx.get("target_device_name") or "").lower()
    for tok in re.findall(r"[a-z0-9]+", label):
        if len(tok) >= 4 and tok in title_l:
            score += 3
    pnp = (ctx.get("pnp_class") or "").lower()
    for hint in _oem_pnp_category_hints(pnp):
        if hint in title_l or hint in cat_l:
            score += 2
    vk = (ctx.get("vendor_key") or "").lower()
    if vk and len(vk) >= 3 and (vk in title_l or vk in cat_l):
        score += 3
    if row.get("version"):
        score += 4
    if _is_generic_oem_support_row(row):
        score -= 25
    return score

def _normalize_oem_driver_row_dict(d: dict) -> dict | None:
    """Map one OEM JSON object to a catalog row."""
    if not isinstance(d, dict):
        return None
    title = (
        d.get("title") or d.get("Title") or d.get("name") or d.get("Name")
        or d.get("DriverName") or d.get("driverName") or d.get("Description") or ""
    )
    title = str(title).strip()
    if not title:
        return None
    ver = (
        d.get("version") or d.get("Version") or d.get("versionString")
        or d.get("VersionString") or d.get("DriverVersion") or d.get("driverVersion")
        or d.get("FileVersion") or ""
    )
    if isinstance(ver, dict):
        ver = ver.get("number") or ver.get("version") or ""
    ver = str(ver).strip()
    date = _dc('_normalize_oem_date')(
        d.get("releaseDate") or d.get("ReleaseDate") or d.get("date")
        or d.get("ReleaseDateString") or d.get("versionUpdatedDateString") or ""
    )
    cat = (
        d.get("category") or d.get("Category") or d.get("type")
        or d.get("Type") or d.get("accordionName") or d.get("DriverType") or ""
    )
    dl = (
        d.get("downloadUrl") or d.get("DownloadUrl") or d.get("url")
        or d.get("URI") or d.get("fileUrl") or d.get("FileUrl") or ""
    )
    files = d.get("files") or d.get("Files") or d.get("FilesList") or []
    if isinstance(files, list) and files and not dl:
        f0 = files[0]
        if isinstance(f0, dict):
            dl = f0.get("downloadUrl") or f0.get("Url") or f0.get("url") or ""
        else:
            dl = str(f0)
    row = {
        "title": title,
        "version": ver,
        "date": date,
        "url": str(dl).strip(),
        "category": str(cat).strip(),
    }
    inner = oev.extract_oem_inner_versions_from_item(d)
    if inner:
        row["inner_versions"] = inner
    return row

def _iter_oem_driver_leaf_dicts(node, *, depth: int = 0):
    """Walk nested OEM API JSON (Dell DriverSet, HP WCC, etc.)."""
    if depth > 10:
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_oem_driver_leaf_dicts(item, depth=depth + 1)
        return
    if not isinstance(node, dict):
        return
    row = _normalize_oem_driver_row_dict(node)
    if row and (row.get("version") or row.get("url")):
        yield row
        return
    for key in (
        "drivers", "Drivers", "DriverList", "Packages", "downloads",
        "DriverSet", "driverSet", "groups", "result", "data", "items",
        "softwareDriversList", "latestVersionDriver", "DriverFiles",
    ):
        child = node.get(key)
        if child is not None:
            yield from _iter_oem_driver_leaf_dicts(child, depth=depth + 1)
    for val in node.values():
        if isinstance(val, (list, dict)) and not isinstance(val, str):
            yield from _iter_oem_driver_leaf_dicts(val, depth=depth + 1)

def _normalize_oem_driver_rows(payload) -> list[dict]:
    """Flatten Dell/Lenovo/HP/ASUS JSON shapes into {title, version, date, url, category}."""
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in _iter_oem_driver_leaf_dicts(payload):
        key = (row.get("title") or "", row.get("version") or "")
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows

def _oem_pick_rows_for_ctx(
    scored: list[tuple[int, dict]],
    ctx: dict,
    max_rows: int,
) -> list[tuple[int, dict]]:
    """Prefer newest Realtek NIC OEM package when Dell lists multiple matching network rows."""
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if vk == "realtek" and pnp == "net":
        top = scored[0][0]
        nic_rows = [
            (s, r) for s, r in scored
            if s >= top - 3
            and "realtek" in (r.get("title") or "").lower()
            and "ethernet" in (r.get("title") or "").lower()
        ]
        if nic_rows:
            nic_rows.sort(
                key=lambda xr: parse_driver_version(xr[1].get("version") or "") or (),
                reverse=True,
            )
            return nic_rows[:max_rows]
    return scored[:max_rows]

def _oem_offers_from_rows(
    rows: list[dict],
    ctx: dict,
    source_label: str,
    notes: str,
    fallback_url: str,
    max_rows: int = 2,
) -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for row in rows:
        if not row.get("title"):
            continue
        if _is_generic_oem_support_row(row):
            continue
        if not _oem_row_eligible_for_ctx(row, ctx):
            continue
        score = _score_oem_row_for_ctx(row, ctx)
        scored.append((score, row))
    offers = []
    for score, row in _oem_pick_rows_for_ctx(scored, ctx, max_rows):
        offer = {
            "source": "oem",
            "source_label": source_label,
            "title": row["title"][:120],
            "version": row.get("version") or "",
            "date": row.get("date") or "",
            "url": row.get("url") or fallback_url,
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": notes,
            "confidence": "high" if row.get("version") else "medium",
            "category": row.get("category") or "",
            "oem_match_score": score,
        }
        if row.get("inner_versions"):
            offer["inner_versions"] = row["inner_versions"]
        offers.append(offer)
    return offers

_KNOWN_OEM_PC_MAKERS = (
    "dell", "alienware", "lenovo", "thinkpad", "ideapad", "hp", "hewlett",
    "asus", "rog", "msi", "micro-star", "gigabyte", "aorus", "acer",
)

def system_has_oem_driver_catalog(system_ctx: dict | None) -> bool:
    """True when this PC maker has a supported OEM driver API in our catalog."""
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    bb = ((system_ctx or {}).get("baseboard_manufacturer") or "").lower()
    if any(tag in mfr for tag in _KNOWN_OEM_PC_MAKERS):
        return True
    return any(tag in bb for tag in ("msi", "micro-star", "gigabyte", "aorus", "asus"))

def _oem_catalog_sources(system_ctx: dict | None) -> list[tuple[str, Callable]]:
    """(source_label, get_rows_fn) for every OEM API that applies to this PC."""
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb = (ctx.get("baseboard_manufacturer") or "").lower()
    sources: list[tuple[str, Callable]] = []
    if "dell" in mfr or "alienware" in mfr:
        sources.append(("OEM (Dell / Alienware)", lambda ctx: _dc("get_dell_oem_rows")(ctx)))
    if "lenovo" in mfr or "thinkpad" in mfr or "ideapad" in mfr:
        sources.append(("OEM (Lenovo)", lambda ctx: _dc("get_lenovo_oem_rows")(ctx)))
    if "hp" in mfr or "hewlett" in mfr:
        sources.append(("OEM (HP)", lambda ctx: _dc("get_hp_oem_rows")(ctx)))
    if "asus" in mfr or "rog" in mfr:
        sources.append(("OEM (ASUS / ROG)", lambda ctx: _dc("get_asus_oem_rows")(ctx)))
    if _manufacturer_matches(mfr, "msi", "micro-star") or _manufacturer_matches(bb, "msi"):
        sources.append(("OEM (MSI)", lambda ctx: _dc("get_msi_oem_rows")(ctx)))
    if _manufacturer_matches(mfr, "gigabyte", "aorus") or _manufacturer_matches(bb, "gigabyte", "aorus"):
        sources.append(("OEM (Gigabyte / AORUS)", lambda ctx: _dc("get_gigabyte_oem_rows")(ctx)))
    if "acer" in mfr:
        sources.append(("OEM (Acer)", lambda ctx: _dc("get_acer_oem_rows")(ctx)))
    return sources

def _oem_rows_to_catalog_offers(
    rows: list[dict],
    source_label: str,
    fallback_url: str,
    *,
    note: str = "",
) -> list[dict]:
    """All OEM API rows for disk cache (device matching happens at scan time)."""
    offers: list[dict] = []
    default_note = note or "Model-specific WHQL package from PC maker catalog."
    for row in rows:
        if not row.get("title") or _is_generic_oem_support_row(row):
            continue
        offers.append({
            "source": "oem",
            "source_label": source_label,
            "title": row["title"][:120],
            "version": row.get("version") or "",
            "date": row.get("date") or "",
            "url": row.get("url") or fallback_url,
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": default_note,
            "confidence": "high" if row.get("version") else "medium",
            "category": row.get("category") or "",
        })
    return offers

def fetch_oem_catalog_for_system(system_ctx: dict | None) -> list[dict]:
    """Fetch full versioned OEM catalogs from every API that applies to this PC."""
    offers: list[dict] = []
    tag = _dell_service_tag(system_ctx) or ""
    for label, getter in _oem_catalog_sources(system_ctx):
        try:
            rows, fallback = getter(system_ctx)
        except Exception:
            continue
        if not rows:
            continue
        extra = ""
        if "Dell" in label and tag:
            extra = f" Service tag {tag}."
        elif "Lenovo" in label:
            mtm = re.sub(
                r"[^A-Z0-9]",
                "",
                ((system_ctx or {}).get("machine_type") or (system_ctx or {}).get("baseboard_product") or "").upper(),
            )[:10]
            if mtm:
                extra = f" Machine type {mtm}."
        offers.extend(
            _oem_rows_to_catalog_offers(
                rows,
                label,
                fallback,
                note=f"{label} catalog.{extra}".strip(),
            )
        )
    return offers

def _fetch_dell_oem_rows_live(system_ctx: dict | None) -> tuple[list[dict], str]:
    """Fetch Dell/Alienware catalog rows (uncached)."""
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    if "dell" not in mfr and "alienware" not in mfr:
        return [], ""
    tag = _dell_service_tag(system_ctx)
    fallback = (
        f"https://www.dell.com/support/home/en-us/product-support/servicetag/{tag}/drivers"
        if tag
        else "https://www.dell.com/support/home"
    )
    rows = _dc("_get_dell_oem_rows_from_api")(system_ctx)
    if not rows:
        rows = _dc("_get_dell_oem_rows_from_local_dup")(system_ctx)
    else:
        rows = _dc("_merge_dell_dup_inner_versions_into_rows")(rows, system_ctx)
    rows = _dc("_merge_enterprise_oem_rows")(rows, system_ctx, "dell")
    rows = _dc("_merge_dell_dup_inner_versions_into_rows")(rows, system_ctx)
    return rows, fallback

def _normalize_oem_row_match_key(title: str) -> str:
    """Normalize OEM driver titles for DUP inner-version merge."""
    import html as htmlmod

    t = htmlmod.unescape(title or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for suffix in (
        " controller driver",
        " driver",
        " drivers",
        " application",
        " utility",
        " installer",
    ):
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
    return t


def _dup_inner_version_indexes(
    dup_rows: list[dict],
) -> tuple[dict[tuple[str, str], list[dict]], dict[str, list[dict]]]:
    """Build (title, version) and normalized-title indexes from DUP manifest rows."""
    by_title_ver: dict[tuple[str, str], list[dict]] = {}
    by_title: dict[str, list[dict]] = {}
    title_counts: dict[str, int] = {}
    for dr in dup_rows:
        inner = dr.get("inner_versions")
        if not inner:
            continue
        norm = _normalize_oem_row_match_key(dr.get("title") or "")
        ver = (dr.get("version") or "").strip()
        if norm and ver:
            by_title_ver[(norm, ver)] = inner
        if norm:
            title_counts[norm] = title_counts.get(norm, 0) + 1
            if norm not in by_title:
                by_title[norm] = inner
    # Title-only fallback only when the DUP catalog has a single row for that title.
    by_title = {k: v for k, v in by_title.items() if title_counts.get(k) == 1}
    return by_title_ver, by_title


def _merge_dup_inner_versions_into_rows(
    rows: list[dict],
    dup_rows: list[dict],
) -> list[dict]:
    """Attach DUP per-PCI inner versions when live/API rows only have wrapper version."""
    if not rows or not dup_rows:
        return rows
    by_title_ver, by_title = _dup_inner_version_indexes(dup_rows)
    if not by_title_ver and not by_title:
        return rows
    merged: list[dict] = []
    for row in rows:
        out = dict(row)
        if out.get("inner_versions"):
            merged.append(out)
            continue
        norm = _normalize_oem_row_match_key(out.get("title") or "")
        ver = (out.get("version") or "").strip()
        inner = by_title_ver.get((norm, ver)) if norm and ver else None
        if not inner and norm:
            inner = by_title.get(norm)
        if inner:
            out["inner_versions"] = inner
        merged.append(out)
    return merged


def _merge_dell_dup_inner_versions_into_rows(
    rows: list[dict],
    system_ctx: dict | None,
) -> list[dict]:
    """Attach DUP inner_versions from local Dell SoftwareComponent manifests."""
    dup_rows = _dc("_get_dell_oem_rows_from_local_dup")(system_ctx)
    return _merge_dup_inner_versions_into_rows(rows, dup_rows)

def get_dell_oem_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    """Raw Dell/Alienware catalog rows and support URL."""
    return _cached_oem_rows("dell", lambda ctx: _dc("_fetch_dell_oem_rows_live")(ctx), system_ctx)

def fetch_dell_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    rows, fallback = _dc("get_dell_oem_rows")(system_ctx)
    if not rows:
        return []
    tag = _dell_service_tag(system_ctx) or ""
    return _oem_offers_from_rows(
        rows, ctx, "OEM (Dell / Alienware)",
        f"Service tag {tag}. WHQL build for this model.", fallback,
    )

def _fetch_lenovo_oem_rows_live(system_ctx: dict | None) -> tuple[list[dict], str]:
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    if "lenovo" not in mfr and "thinkpad" not in mfr and "ideapad" not in mfr:
        return [], ""
    mtm = (system_ctx or {}).get("machine_type") or (system_ctx or {}).get("baseboard_product") or ""
    mtm = re.sub(r"[^A-Z0-9]", "", mtm.upper())
    if len(mtm) >= 10:
        mtm = mtm[:10]
    elif len(mtm) >= 7:
        mtm = mtm[:7]
    else:
        mtm = ""
    serial = _dell_service_tag(system_ctx) or ""
    fallback = "https://support.lenovo.com/us/en/solutions/ht003013"
    if mtm:
        fallback = f"https://pcsupport.lenovo.com/us/en/products/{mtm}/downloads"
    rows: list[dict] = []
    if mtm:
        for api_url in (
            f"https://support.lenovo.com/us/en/api/v4/downloads/products/{mtm}/drivers",
            f"https://pcsupport.lenovo.com/us/en/api/v4/downloads/products/{mtm}/drivers",
        ):
            ok, body = _dc('_vendor_fetch_get')(api_url, accept="application/json")
            if ok and body:
                try:
                    rows = _normalize_oem_driver_rows(json.loads(body))
                    if rows:
                        break
                except json.JSONDecodeError:
                    continue
    if not rows and serial:
        detect_url = "https://support.lenovo.com/us/en/api/v4/downloads/detect"
        try:
            payload = json.dumps({
                "SerialNumber": serial,
                "ProductName": (system_ctx or {}).get("system_model") or mtm,
            }).encode("utf-8")
            req = urllib.request.Request(
                detect_url,
                data=payload,
                headers={
                    "User-Agent": _dc('catalog_user_agent')(),
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            rows = _normalize_oem_driver_rows(json.loads(body))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
    rows = _dc("_merge_enterprise_oem_rows")(rows, system_ctx, "lenovo")
    return rows, fallback

def get_lenovo_oem_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    return _cached_oem_rows("lenovo", lambda ctx: _dc("_fetch_lenovo_oem_rows_live")(ctx), system_ctx)

def fetch_lenovo_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    rows, fallback = _dc("get_lenovo_oem_rows")(system_ctx)
    if not rows:
        return []
    mtm = re.sub(
        r"[^A-Z0-9]",
        "",
        ((system_ctx or {}).get("machine_type") or (system_ctx or {}).get("baseboard_product") or "").upper(),
    )[:10]
    serial = _dell_service_tag(system_ctx) or ""
    note = f"Machine type {mtm}." if mtm else f"Serial {serial[:6]}…."
    return _oem_offers_from_rows(
        rows, ctx, "OEM (Lenovo)", f"{note} Model-specific WHQL drivers.", fallback,
    )

def _manufacturer_matches(mfr: str, *needles: str) -> bool:
    m = (mfr or "").lower()
    return any(n in m for n in needles if n)

def _windows_osid() -> str:
    """ASUS osid: 52 = Windows 11 64-bit, 45 = Windows 10 64-bit."""
    if sys.platform != "win32":
        return ""
    ver = sys.getwindowsversion()
    return "52" if ver.major >= 10 and ver.build >= 22000 else "45"

def _oem_model_candidates(system_ctx: dict | None) -> list[str]:
    """Model strings to try for OEM APIs (system model, baseboard, combined)."""
    ctx = system_ctx or {}
    candidates = []
    for key in ("system_model", "baseboard_product", "machine_type"):
        val = (ctx.get(key) or "").strip()
        if val and val not in candidates:
            candidates.append(val)
    bb = (ctx.get("baseboard_product") or "").strip()
    sys_m = (ctx.get("system_model") or "").strip()
    if bb and sys_m and f"{bb} {sys_m}" not in candidates:
        candidates.append(f"{bb} {sys_m}")
    return candidates[:6]

def _slug_for_oem_api(name: str) -> str:
    """MSI/Gigabyte-style slug: PRO Z790-A WIFI -> PRO-Z790-A-WIFI."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").upper()).strip("-")
    return s[:48] if s else ""

def _oem_model_slug_variants(name: str) -> list[str]:
    """Alternate model strings for OEM APIs (ASUS/MSI/Gigabyte)."""
    raw = (name or "").strip()
    if not raw:
        return []
    variants = [raw]
    trimmed = re.sub(r"\s*\([^)]*\)\s*", " ", raw).strip()
    if trimmed and trimmed not in variants:
        variants.append(trimmed)
    slug = _slug_for_oem_api(raw)
    if slug and slug not in variants:
        variants.append(slug)
    compact = re.sub(r"[^A-Za-z0-9]", "", raw.upper())
    if compact and compact not in variants:
        variants.append(compact)
    if re.search(r"\bROG\b", raw, re.I):
        no_rog = re.sub(r"\bROG\s+", "", raw, flags=re.I).strip()
        if no_rog and no_rog not in variants:
            variants.append(no_rog)
    return variants[:8]

def _gigabyte_support_page_urls(slug: str, system_ctx: dict | None) -> list[str]:
    if not slug:
        return []
    ctx = system_ctx or {}
    model_l = f"{ctx.get('system_model') or ''} {ctx.get('baseboard_product') or ''}".lower()
    paths = [f"https://www.gigabyte.com/Motherboard/{slug}/support"]
    if any(k in model_l for k in ("laptop", "notebook", "aero", "aorus")):
        paths.insert(0, f"https://www.gigabyte.com/Laptop/{slug}/support")
    if "aorus" in model_l:
        paths.insert(0, f"https://www.gigabyte.com/AORUS/{slug}/support")
    paths.append(f"https://www.gigabyte.com/Support/Motherboard/{slug}#support-dl-driver")
    return list(dict.fromkeys(paths))

def _parse_hp_wcc_driver_details(payload: dict) -> list[dict]:
    rows: list[dict] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return rows
    for group in data.get("softwareTypes") or []:
        if not isinstance(group, dict):
            continue
        cat = (group.get("accordionName") or group.get("name") or "").strip()
        for item in group.get("softwareDriversList") or []:
            if not isinstance(item, dict):
                continue
            latest = item.get("latestVersionDriver") or item
            if not isinstance(latest, dict):
                continue
            title = (latest.get("title") or latest.get("name") or "HP driver").strip()
            ver = str(latest.get("version") or "").strip()
            date = _dc('_normalize_oem_date')(
                latest.get("versionUpdatedDateString")
                or latest.get("releaseDateString")
                or latest.get("releaseDate")
                or ""
            )
            url = (latest.get("fileUrl") or latest.get("url") or "").strip()
            rows.append({
                "title": title[:120],
                "version": ver,
                "date": date,
                "url": url,
                "category": cat,
            })
    return rows

def _hp_typeahead_product_hints(query: str) -> dict | None:
    q = urllib.parse.quote((query or "").strip()[:80])
    if not q:
        return None
    url = (
        "https://support.hp.com/typeahead"
        f"?q={q}&resultLimit=8&store=tmsstore&languageCode=en"
        "&filters=class:(pm_series_value^1.1 OR pm_name_value OR pm_number_value)"
        " AND (hiddenproduct:no OR (!_exists_:hiddenproduct))"
        "&printFields=tmspmseriesvalue,tmspmnamevalue,tmspmnumbervalue,class,"
        "productid,seofriendlyname,activewebsupportflag,navigationpath,childnodes"
    )
    ok, body = _dc('_http_get')(url, headers={"Accept": "application/json"})
    if not ok or not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    matches = data.get("matches") or []
    if not isinstance(matches, list):
        return None
    series_oid = ""
    product_number_oid = ""
    product_line = ""
    for m in matches:
        if not isinstance(m, dict):
            continue
        pm_class = (m.get("pmClass") or m.get("class") or "").lower()
        pid = str(m.get("productId") or m.get("productid") or "").strip()
        if not pid:
            continue
        if pm_class == "pm_series_value" and not series_oid:
            series_oid = pid
        elif pm_class == "pm_name_value":
            if not product_number_oid:
                product_number_oid = pid
            if not series_oid:
                series_oid = str(m.get("pmSeriesOid") or m.get("tmspmseriesvalue") or "").strip()
        elif pm_class == "pm_number_value" and not product_number_oid:
            product_number_oid = pid
    if not series_oid and product_number_oid:
        series_oid = product_number_oid
    if not series_oid:
        return None
    return {
        "series_oid": series_oid,
        "product_number_oid": product_number_oid or series_oid,
        "product_line_code": product_line,
    }

def _hp_wcc_product_specs(
    series_oid: str,
    *,
    serial: str = "",
    product_number: str = "",
) -> dict:
    payload = {
        "cc": "us",
        "lc": "en",
        "utcOffset": "M0700",
        "devices": [{
            "seriesOid": None,
            "modelOid": int(series_oid) if str(series_oid).isdigit() else series_oid,
            "serialNumber": serial or None,
            "displayProductNumber": product_number or None,
            "countryOfPurchase": "us",
        }],
        "skipSyncCall": False,
        "captchaToken": "",
    }
    ok, body = _dc("_http_post_json")(
        "https://support.hp.com/wcc-services/profile/devices/warranty/specs?cache=true",
        payload,
        referer="https://support.hp.com/",
    )
    if not ok or not body:
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {}
    devices = data.get("devices") or []
    if not isinstance(devices, list) or not devices:
        return {}
    dev0 = devices[0] if isinstance(devices[0], dict) else {}
    specs = dev0.get("productSpecs") or {}
    block = specs.get("data") if isinstance(specs, dict) else {}
    if not isinstance(block, dict):
        block = dev0.get("productSpecs") if isinstance(dev0.get("productSpecs"), dict) else {}
    return block if isinstance(block, dict) else {}

def _hp_pick_windows_os_tms_id(series_oid: str) -> str:
    url = (
        "https://support.hp.com/wcc-services/swd-v2/osVersionData"
        f"?cc=us&lc=en&productOid={urllib.parse.quote(series_oid)}"
    )
    ok, body = _dc('_http_get')(url, headers={"Accept": "application/json"})
    if not ok or not body:
        return ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ""
    platforms = (
        ((data.get("data") or {}).get("osAvailablePlatformsAnsOS") or {}).get("osPlatforms")
        or []
    )
    candidates: list[tuple[int, str, str]] = []
    for plat in platforms:
        if not isinstance(plat, dict):
            continue
        if (plat.get("osName") or "").lower() != "windows":
            continue
        for ver in plat.get("osVersions") or []:
            if not isinstance(ver, dict):
                continue
            name = (ver.get("name") or ver.get("osVersionName") or "").lower()
            tid = str(ver.get("id") or ver.get("osTMSId") or "").strip()
            if not tid:
                continue
            rank = 0
            if "11" in name:
                rank += 20
            elif "10" in name:
                rank += 10
            if "64" in name:
                rank += 5
            if "24h2" in name or "23h2" in name:
                rank += 3
            candidates.append((rank, name, tid))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][2]

def _hp_product_number_from_model(model: str) -> str:
    model = (model or "").strip()
    if not model:
        return ""
    return re.sub(r"[^A-Z0-9#]", "", model.upper())[:12]

def _hp_fetch_wcc_driver_rows(system_ctx: dict | None) -> list[dict]:
    ctx = system_ctx or {}
    serial = _dell_service_tag(system_ctx) or ""
    model = (ctx.get("system_model") or "").strip()
    product = _hp_product_number_from_model(model)
    hints = None
    for query in (product, model, serial):
        if not query:
            continue
        hints = _hp_typeahead_product_hints(query)
        if hints:
            break
    if not hints:
        return []
    series_oid = hints["series_oid"]
    specs = _hp_wcc_product_specs(
        series_oid,
        serial=serial,
        product_number=product,
    )
    os_tms = _hp_pick_windows_os_tms_id(series_oid)
    if not os_tms:
        return []
    payload = {
        "productLineCode": specs.get("productLineCode") or hints.get("product_line_code") or "6U",
        "lc": "en",
        "cc": "us",
        "osTMSId": os_tms,
        "osName": "Windows",
        "productNumberOid": int(
            specs.get("productNumberOid") or hints.get("product_number_oid") or series_oid
        ),
        "productSeriesOid": int(specs.get("productSeriesOid") or series_oid),
        "platformId": os_tms,
    }
    ok, body = _dc("_http_post_json")(
        "https://support.hp.com/wcc-services/swd-v2/driverDetails",
        payload,
        referer="https://support.hp.com/",
    )
    if not ok or not body:
        return []
    try:
        return _parse_hp_wcc_driver_details(json.loads(body))
    except json.JSONDecodeError:
        return []

def _parse_asus_driver_json(payload: dict) -> list[dict]:
    rows: list[dict] = []
    result = payload.get("Result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return rows
    for group in result.get("Obj") or []:
        if not isinstance(group, dict):
            continue
        cat = (group.get("Name") or "").strip()
        for f in group.get("Files") or []:
            if not isinstance(f, dict):
                continue
            dl = f.get("DownloadUrl") or {}
            url = ""
            if isinstance(dl, dict):
                url = (dl.get("Global") or dl.get("China") or "").strip()
            title = (f.get("Title") or f.get("Name") or "ASUS driver").strip()
            ver = (f.get("Version") or "").strip()
            date = _dc('_normalize_oem_date')(f.get("ReleaseDate") or "")
            rows.append({
                "title": title[:120],
                "version": ver,
                "date": date,
                "url": url,
                "category": cat,
            })
    return rows

def _fetch_asus_oem_rows_live(system_ctx: dict | None) -> tuple[list[dict], str]:
    try:
        import vendor_firmware_fetch as vff

        rows, fallback, status = vff.fetch_asus_product_rows(system_ctx)
        if rows:
            return rows, fallback
        if status == "waf_blocked":
            return [], fallback or "https://www.asus.com/support/download-center/"
    except ImportError:
        pass
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    bb_mfr = ((system_ctx or {}).get("baseboard_manufacturer") or "").lower()
    if not _manufacturer_matches(mfr, "asus", "rog", "republic of gamers") and not _manufacturer_matches(
        bb_mfr, "asus"
    ):
        return [], ""
    osid = _windows_osid()
    fallback = "https://www.asus.com/support/download-center/"
    all_rows: list[dict] = []
    tried: set[str] = set()
    for model in _oem_model_candidates(system_ctx):
        for variant in _oem_model_slug_variants(model):
            if variant in tried:
                continue
            tried.add(variant)
            for base, extra in (
                (f"https://www.asus.com/support/api/product.asmx/GetPDDrivers?osid={osid}&website=global&model=", ""),
                (f"https://rog.asus.com/support/webapi/product/GetPDDrivers?website=global&model=", f"&osid={osid}&systemCode=rog"),
            ):
                url = base + urllib.parse.quote(variant) + extra
                ok, body = _dc('_http_get')(url, headers={"Accept": "application/json"})
                if not ok or not body or '"FAIL"' in body[:120]:
                    continue
                try:
                    data = json.loads(body)
                    if (data.get("Status") or "").upper() == "FAIL":
                        continue
                    rows = _parse_asus_driver_json(data)
                    if rows:
                        all_rows = rows
                        break
                except json.JSONDecodeError:
                    continue
            if all_rows:
                break
        if all_rows:
            break
    return all_rows, fallback

def get_asus_oem_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    return _cached_oem_rows("asus", lambda ctx: _dc("_fetch_asus_oem_rows_live")(ctx), system_ctx)

def fetch_asus_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    all_rows, fallback = _dc("get_asus_oem_rows")(system_ctx)
    if not all_rows:
        return []
    return _oem_offers_from_rows(
        all_rows, ctx, "OEM (ASUS / ROG)",
        "Drivers from ASUS support API for this model.", fallback,
    )

def _parse_msi_driver_json(payload: dict) -> list[dict]:
    rows: list[dict] = []
    downloads = (payload.get("result") or {}).get("downloads") if isinstance(payload, dict) else None
    if not isinstance(downloads, dict):
        return rows
    for cat, items in downloads.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append({
                "title": (item.get("download_title") or "MSI driver").strip()[:120],
                "version": str(item.get("download_version") or "").strip(),
                "date": _dc('_normalize_oem_date')(item.get("download_release") or ""),
                "url": (item.get("download_url") or "").strip(),
                "category": str(cat),
            })
    return rows

def _fetch_msi_oem_rows_live(
    system_ctx: dict | None,
    *,
    catalog_type: str = "driver",
) -> tuple[list[dict], str]:
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    bb_mfr = ((system_ctx or {}).get("baseboard_manufacturer") or "").lower()
    if not _manufacturer_matches(mfr, "msi", "micro-star") and not _manufacturer_matches(bb_mfr, "msi"):
        return [], ""
    fallback = "https://www.msi.com/support/download"
    ctype = catalog_type if catalog_type in ("driver", "bios", "firmware") else "driver"
    tried: set[str] = set()
    for model in _oem_model_candidates(system_ctx):
        for variant in _oem_model_slug_variants(model):
            slug = _slug_for_oem_api(variant)
            if len(slug) < 4 or slug in tried:
                continue
            tried.add(slug)
            api = (
                f"https://www.msi.com/api/v1/product/support/panel"
                f"?product={urllib.parse.quote(slug)}&type={ctype}&page=1&per_page=80"
            )
            ok, body = _dc('_vendor_fetch_get')(api, accept="application/json")
            if not ok or not body:
                continue
            try:
                data = json.loads(body)
                if (data.get("status") or {}).get("code") != 200:
                    continue
                rows = _parse_msi_driver_json(data)
                if rows:
                    return rows, fallback
            except json.JSONDecodeError:
                continue
    return [], fallback

def get_msi_oem_rows(system_ctx: dict | None, *, catalog_type: str = "driver") -> tuple[list[dict], str]:
    if catalog_type != "driver":
        return _dc("_fetch_msi_oem_rows_live")(system_ctx, catalog_type=catalog_type)
    return _cached_oem_rows("msi", lambda ctx: _dc("_fetch_msi_oem_rows_live")(ctx), system_ctx)

def fetch_msi_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    rows, fallback = _dc("get_msi_oem_rows")(system_ctx, catalog_type="driver")
    if not rows:
        return []
    slug = _slug_for_oem_api((_oem_model_candidates(system_ctx) or [""])[0])
    return _oem_offers_from_rows(
        rows, ctx, "OEM (MSI)",
        f"Product {slug} — MSI support API.", fallback,
    )

def _gigabyte_support_slug(system_ctx: dict | None) -> str:
    ctx = system_ctx or {}
    for val in (ctx.get("baseboard_product"), ctx.get("system_model")):
        slug = _slug_for_oem_api(val or "")
        if len(slug) >= 5:
            return slug
    return ""

def _parse_gigabyte_support_html(html: str, page_url: str) -> list[dict]:
    """Gigabyte support page rows — fileTitle/fileVersion via bundled extractor."""
    import vendor_extractors as vex

    rows: list[dict] = []
    seen: set[str] = set()
    for r in vex.extract_bundled_rows("gigabyte", html or ""):
        title = (r.get("title") or "")[:120]
        ver = (r.get("version") or "").strip()
        key = f"{title}|{ver}"
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "title": title,
            "version": ver,
            "date": r.get("date") or "",
            "url": page_url,
            "category": "driver",
        })
    # FileList folder links are URL-structure parsing (not version extraction).
    for folder, rel in re.findall(r"/FileList/(Driver|Software|BIOS)/([^\"'\\s?]+)", html or ""):
        full = f"https://download.gigabyte.com/FileList/{folder}/{rel}"
        if full in seen:
            continue
        seen.add(full)
        fname = urllib.parse.unquote(rel.split("/")[-1])
        title = re.sub(r"^(?:mb_)?(?:driver|bios)_\d+_", "", fname, flags=re.I)
        title = re.sub(r"\.(zip|exe|msi)$", "", title, flags=re.I).replace("_", " ").strip() or fname
        ver_m = re.search(r"(\d+\.\d+\.\d+(?:\.\d+)?)", fname)
        rows.append({
            "title": title[:120],
            "version": ver_m.group(1) if ver_m else "",
            "date": "",
            "url": full,
            "category": folder.lower(),
        })
    return rows

def _fetch_gigabyte_oem_rows_live(system_ctx: dict | None) -> tuple[list[dict], str]:
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    bb_mfr = ((system_ctx or {}).get("baseboard_manufacturer") or "").lower()
    if not _manufacturer_matches(mfr, "gigabyte") and not _manufacturer_matches(bb_mfr, "gigabyte"):
        return [], ""
    slug = _gigabyte_support_slug(system_ctx)
    if not slug:
        return [], ""
    for page_url in _gigabyte_support_page_urls(slug, system_ctx):
        ok, html = _dc('_vendor_fetch_get')(
            page_url, accept="text/html", referer="https://www.gigabyte.com/"
        )
        if not ok or not html:
            continue
        rows = _parse_gigabyte_support_html(html, page_url)
        if rows:
            return rows, page_url
    page_url = f"https://www.gigabyte.com/Motherboard/{slug}/support"
    return [], page_url

def get_gigabyte_oem_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    return _cached_oem_rows("gigabyte", lambda ctx: _dc("_fetch_gigabyte_oem_rows_live")(ctx), system_ctx)

def _parse_gigabyte_bios_html(html: str, page_url: str) -> list[dict]:
    """BIOS-only parse from Gigabyte support HTML (incl. embedded JSON metadata)."""
    rows = _parse_gigabyte_support_html(html, page_url)
    bios = [
        r for r in rows
        if (r.get("category") or "").lower() == "bios"
        or re.search(r"\b(bios|uefi|agesa|capsule)\b", (r.get("title") or ""), re.I)
    ]
    if bios:
        return bios
    for m in re.finditer(
        r'"fileTitle"\s*:\s*"((?:[^"\\]|\\.)+)"\s*,\s*"fileVersion"\s*:\s*"([^"]+)"',
        html,
    ):
        title = m.group(1).replace("\\/", "/").strip()
        if not re.search(r"\b(bios|uefi|agesa)\b", title, re.I):
            continue
        ver = m.group(2).strip() or extract_version_from_text(title)
        rows.append({
            "title": title[:120],
            "version": ver,
            "date": "",
            "url": page_url,
            "category": "bios",
        })
    return rows

def get_gigabyte_bios_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    """BIOS/UEFI-only rows — multiple support URL shapes + browser-like HTTP."""
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    bb_mfr = ((system_ctx or {}).get("baseboard_manufacturer") or "").lower()
    if not _manufacturer_matches(mfr, "gigabyte") and not _manufacturer_matches(bb_mfr, "gigabyte"):
        return [], ""
    slug = _gigabyte_support_slug(system_ctx)
    if not slug:
        return [], ""
    fallback = f"https://www.gigabyte.com/Motherboard/{slug}/support#support-dl-bios"
    urls = [
        f"https://www.gigabyte.com/Motherboard/{slug}/support",
        f"https://www.gigabyte.com/Support/Motherboard/{slug}#support-dl-bios",
        f"https://www.gigabyte.com/Motherboard/{slug}/support#support-dl-bios",
    ]
    for url in urls:
        ok, html = _dc('_http_get')(url, referer="https://www.gigabyte.com/")
        if not ok or not html:
            continue
        rows = _parse_gigabyte_bios_html(html, url)
        if rows:
            return rows, fallback
    return [], fallback

def _walk_json_for_bios_rows(node, fallback: str, rows: list[dict], seen: set[str]) -> None:
    """Recursively find BIOS-like download objects in embedded JSON."""
    if isinstance(node, dict):
        title = str(
            node.get("title") or node.get("Title") or node.get("name")
            or node.get("fileName") or node.get("driverName") or ""
        ).strip()
        cat = str(node.get("category") or node.get("Category") or node.get("type") or "").lower()
        ver = str(
            node.get("version") or node.get("Version") or node.get("fileVersion")
            or node.get("driverVersion") or ""
        ).strip()
        url = str(
            node.get("url") or node.get("downloadUrl") or node.get("DownloadUrl") or fallback
        ).strip()
        blob = f"{title} {cat}".lower()
        if title and (
            "bios" in cat or "uefi" in cat
            or re.search(r"\b(bios|uefi|firmware)\b", blob)
        ):
            key = (title, ver)
            if key not in seen:
                seen.add(key)
                if not ver:
                    ver = extract_version_from_text(title)
                rows.append({
                    "title": title[:120],
                    "version": ver,
                    "date": _dc('_normalize_oem_date')(node.get("date") or node.get("releaseDate") or ""),
                    "url": url or fallback,
                    "category": "BIOS",
                })
        for v in node.values():
            _walk_json_for_bios_rows(v, fallback, rows, seen)
    elif isinstance(node, list):
        for item in node:
            _walk_json_for_bios_rows(item, fallback, rows, seen)

def _extract_json_blobs_from_html(html: str) -> list:
    """Pull JSON objects embedded in support pages (__NEXT_DATA__, etc.)."""
    blobs: list = []
    for pat in (
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>({.+?})</script>',
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
        r'window\.__NUXT__\s*=\s*({.+?});',
    ):
        for m in re.finditer(pat, html, re.I | re.S):
            try:
                blobs.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                continue
    return blobs

def _parse_acer_bios_html(html: str, fallback: str) -> list[dict]:
    """Extract BIOS/UEFI packages from Acer support HTML/embedded JSON."""
    rows: list[dict] = []
    seen: set[str] = set()
    for blob in _extract_json_blobs_from_html(html):
        _walk_json_for_bios_rows(blob, fallback, rows, seen)
    for block in re.findall(
        r'"(?:title|driverName|name|fileName)"\s*:\s*"([^"]{4,120})"[^}]{0,500}?'
        r'"(?:version|driverVersion|ver|fileVersion)"\s*:\s*"([^"]+)"',
        html,
        re.I | re.S,
    ):
        title, ver = block[0], block[1]
        if not re.search(r"\b(bios|uefi|firmware)\b", title, re.I):
            continue
        key = (title, ver)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "title": title[:120],
            "version": ver,
            "date": "",
            "url": fallback,
            "category": "BIOS",
        })
    for url in re.findall(r"https://global-download\.acer\.com/[^\"'\\s<>]+", html):
        low = url.lower()
        if not any(x in low for x in ("bios", "uefi", "firmware")):
            continue
        if url in seen:
            continue
        seen.add(url)
        fname = url.split("/")[-1].split("?")[0]
        ver_m = re.search(r"(\d+\.\d+\.\d+(?:\.\d+)?|[A-Z]\d{2,})", fname, re.I)
        rows.append({
            "title": fname[:120],
            "version": ver_m.group(1) if ver_m else "",
            "date": "",
            "url": url,
            "category": "BIOS",
        })
    return rows

def get_acer_bios_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    """BIOS-focused Acer support fetch (serial/product pages + embedded JSON)."""
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    if not _manufacturer_matches(mfr, "acer"):
        return [], ""
    serial = _dell_service_tag(system_ctx) or ""
    model = (system_ctx or {}).get("system_model") or ""
    fallback = "https://www.acer.com/us-en/support/drivers-and-manuals"
    if serial:
        fallback = f"https://www.acer.com/us-en/support/product-support?serialNumber={urllib.parse.quote(serial)}"
    urls_to_try: list[str] = []
    if serial and len(serial) >= 8:
        sn = urllib.parse.quote(serial)
        urls_to_try.extend([
            f"https://www.acer.com/us-en/support/product-support/detail/{sn}",
            f"https://www.acer.com/acer-support/api/drivers/get?serialNumber={sn}",
            f"https://www.acer.com/support/api/v1/drivers?serialNumber={sn}",
        ])
    if model:
        q = urllib.parse.quote(model)
        urls_to_try.append(f"https://www.acer.com/us-en/support/drivers-and-manuals?search={q}")
    for url in urls_to_try:
        accept = "application/json" if "api" in url else "text/html"
        ok, body = _dc('_vendor_fetch_get')(url, accept=accept, referer="https://www.acer.com/")
        if not ok or not body:
            continue
        rows: list[dict] = []
        if body.lstrip().startswith("{"):
            try:
                data = json.loads(body)
                seen: set[str] = set()
                _walk_json_for_bios_rows(data, fallback, rows, seen)
                if not rows:
                    rows = _normalize_oem_driver_rows(data)
                    rows = [
                        r for r in rows
                        if re.search(r"\b(bios|uefi)\b", f"{r.get('title','')} {r.get('category','')}", re.I)
                    ]
            except json.JSONDecodeError:
                rows = []
        else:
            rows = _parse_acer_bios_html(body, fallback)
        if rows:
            return rows, fallback
    return [], fallback

def fetch_gigabyte_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    rows, page_url = _dc("get_gigabyte_oem_rows")(system_ctx)
    if not rows:
        return []
    slug = _gigabyte_support_slug(system_ctx) or ""
    return _oem_offers_from_rows(
        rows, ctx, "OEM (Gigabyte)",
        f"Drivers from Gigabyte support page ({slug}).", page_url,
    )

def _parse_acer_driver_html(html: str, fallback: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for block in re.findall(
        r'"(?:title|driverName|name)"\s*:\s*"([^"]{4,120})"[^}]{0,400}?'
        r'"(?:version|driverVersion|ver)"\s*:\s*"([^"]+)"',
        html,
        re.I | re.S,
    ):
        title, ver = block[0], block[1]
        key = (title, ver)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "title": title[:120],
            "version": ver,
            "date": "",
            "url": fallback,
            "category": "driver",
        })
    for url in re.findall(r"https://global-download\.acer\.com/[^\"'\\s<>]+", html):
        if url in seen:
            continue
        seen.add(url)
        fname = url.split("/")[-1].split("?")[0]
        ver_m = re.search(r"(\d+\.\d+\.\d+(?:\.\d+)?)", fname)
        rows.append({
            "title": fname[:120],
            "version": ver_m.group(1) if ver_m else "",
            "date": "",
            "url": url,
            "category": "driver",
        })
    return rows

def _fetch_acer_oem_rows_live(system_ctx: dict | None) -> tuple[list[dict], str]:
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    if not _manufacturer_matches(mfr, "acer"):
        return [], ""
    serial = _dell_service_tag(system_ctx) or ""
    model = (system_ctx or {}).get("system_model") or ""
    snid = (system_ctx or {}).get("snid") or ""
    fallback = "https://www.acer.com/us-en/support/drivers-and-manuals"
    if serial:
        fallback = f"https://www.acer.com/us-en/support/product-support?serialNumber={urllib.parse.quote(serial)}"
    urls_to_try = []
    if serial and len(serial) >= 8:
        urls_to_try.append(
            f"https://www.acer.com/us-en/support/product-support/detail/{urllib.parse.quote(serial)}"
        )
        urls_to_try.append(
            f"https://www.acer.com/us-en/support/drivers-and-manuals?serialNumber={urllib.parse.quote(serial)}"
        )
    if snid and len(str(snid)) >= 8:
        urls_to_try.append(
            f"https://www.acer.com/us-en/support/drivers-and-manuals?snid={urllib.parse.quote(str(snid))}"
        )
    if model:
        q = urllib.parse.quote(model)
        urls_to_try.append(f"https://www.acer.com/us-en/support/drivers-and-manuals?search={q}")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", model.strip()).strip("-").lower()
        if slug:
            urls_to_try.append(f"https://www.acer.com/us-en/support/product-support/{slug}")
    for url in urls_to_try:
        ok, html = _dc('_vendor_fetch_get')(url, accept="text/html")
        if not ok or not html:
            continue
        rows = _parse_acer_driver_html(html, fallback)
        if rows:
            return rows, fallback
    return [], fallback

def get_acer_oem_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    return _cached_oem_rows("acer", lambda ctx: _dc("_fetch_acer_oem_rows_live")(ctx), system_ctx)

def fetch_acer_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    all_rows, fallback = _dc("get_acer_oem_rows")(system_ctx)
    if not all_rows:
        return []
    serial = _dell_service_tag(system_ctx) or ""
    model = (system_ctx or {}).get("system_model") or ""
    note = f"Serial {serial[:8]}…." if serial else f"Model {model}."
    return _oem_offers_from_rows(
        all_rows, ctx, "OEM (Acer)", f"{note} Parsed from Acer support pages.", fallback,
    )

def _fetch_hp_oem_rows_live(system_ctx: dict | None) -> tuple[list[dict], str]:
    mfr = ((system_ctx or {}).get("system_manufacturer") or "").lower()
    if "hp" not in mfr and "hewlett" not in mfr:
        return [], ""
    serial = _dell_service_tag(system_ctx) or ""
    model = (system_ctx or {}).get("system_model") or ""
    product = _hp_product_number_from_model(model)
    fallback = "https://support.hp.com/us-en/drivers"
    if serial:
        fallback = f"https://support.hp.com/us-en/product?serialNumber={urllib.parse.quote(serial)}"
    rows: list[dict] = []
    if product:
        swd_url = f"https://hpsvcras.hp.com/endpoint/swd/v1?productNumber={urllib.parse.quote(product)}"
        ok, body = _dc('_vendor_fetch_get')(swd_url, accept="application/json")
        if ok and body:
            try:
                data = json.loads(body)
                items = data if isinstance(data, list) else data.get("Drivers") or data.get("packages") or []
                for item in items if isinstance(items, list) else []:
                    if not isinstance(item, dict):
                        continue
                    rows.append({
                        "title": item.get("Title") or item.get("name") or "HP driver",
                        "version": str(item.get("Version") or item.get("version") or "").strip(),
                        "date": _dc('_normalize_oem_date')(item.get("ReleaseDate") or ""),
                        "url": item.get("DownloadUrl") or item.get("url") or fallback,
                        "category": item.get("Category") or item.get("Type") or "",
                    })
            except json.JSONDecodeError:
                pass
    if not rows:
        rows = _dc("_hp_fetch_wcc_driver_rows")(system_ctx)
    elif _dc('_v6_catalog_enabled')():
        wcc = _dc("_hp_fetch_wcc_driver_rows")(system_ctx)
        seen = {(r.get("title"), r.get("version")) for r in rows}
        for r in wcc:
            key = (r.get("title"), r.get("version"))
            if key not in seen:
                rows.append(r)
                seen.add(key)
    rows = _dc("_merge_enterprise_oem_rows")(rows, system_ctx, "hp")
    return rows, fallback

def get_hp_oem_rows(system_ctx: dict | None) -> tuple[list[dict], str]:
    return _cached_oem_rows("hp", lambda ctx: _dc("_fetch_hp_oem_rows_live")(ctx), system_ctx)

def fetch_hp_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    rows, fallback = _dc("get_hp_oem_rows")(system_ctx)
    if not rows:
        return []
    model = (system_ctx or {}).get("system_model") or ""
    product = _hp_product_number_from_model(model)
    return _oem_offers_from_rows(
        rows, ctx, "OEM (HP)",
        f"Product {product or model}. HP SoftPaq / driver catalog.", fallback,
    )
