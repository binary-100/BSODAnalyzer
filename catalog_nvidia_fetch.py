"""NVIDIA vendor Ajax/processfind lookup and offer fetch (extracted from driver_catalog)."""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from datetime import datetime

from catalog_scoring import (
    _looks_like_nvidia_branch_version,
    _looks_like_nvidia_internal_version,
    parse_driver_package_date,
    parse_driver_version,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


# Retired NVIDIA/AMD endpoints — must not appear in backlog/docs as active work (see audit_vendor_apis.py).
_NVIDIA_RETIRED_API_MARKERS = (
    "GetByDeviceID",
    "func=GetByDeviceID",
    "nvidia_xml",
)


def _nvidia_windows_os_id() -> str:
    """NVIDIA AjaxDriverService osID: 135 = Win11 64-bit, 57 = Win10 64-bit."""
    if sys.platform != "win32":
        return "135"
    ver = sys.getwindowsversion()
    if ver.major >= 10 and ver.build >= 22000:
        return "135"
    return "57"


def _nvidia_pci_dev_from_ctx(ctx: dict) -> str:
    """Four-digit PCI DEV id for NVIDIA GPU (uppercase hex), or empty."""
    pnp = _dc("_nvidia_pnp_id_from_ctx")(ctx)
    if not pnp:
        return ""
    m = re.search(r"DEV_([0-9A-F]{4})", pnp.upper())
    return m.group(1) if m else ""


def _nvidia_psid_pfid_candidates(ctx: dict) -> list[tuple[str, str]]:
    """Ordered (psid, pfid) pairs for NVIDIA AjaxDriverService lookup."""
    import gpu_vendor_maps as gvm

    return gvm.nvidia_psid_pfid_candidates(
        device_label=_dc("_ctx_device_label")(ctx),
        pci_dev=_nvidia_pci_dev_from_ctx(ctx),
    )


def _nvidia_gpu_within_support_floor(ctx: dict) -> bool:
    import gpu_vendor_maps as gvm

    return gvm.nvidia_gpu_supported(
        _dc("_ctx_device_label")(ctx),
        _nvidia_pci_dev_from_ctx(ctx),
    )


def _nvidia_ajax_result_plausible(di: dict, ctx: dict) -> bool:
    """Reject Ajax hits that target a different GPU generation (e.g. RTX 610 on GTX 1060)."""
    ver = (di.get("Version") or "").strip()
    if not ver or not _looks_like_nvidia_branch_version(ver):
        return False
    name = urllib.parse.unquote_plus(
        (di.get("NameLocalized") or di.get("Name") or "").strip()
    ).lower()
    label = _dc("_ctx_device_label")(ctx)
    is_gtx = bool(re.search(r"\bgtx\s*\d", label, re.I))
    is_legacy_geforce = is_gtx and not re.search(r"\brtx\s*\d", label, re.I)
    if is_legacy_geforce:
        if "rtx driver release" in name:
            return False
        if (parse_driver_version(ver) or ()) > (parse_driver_version("591.00") or ()):
            return False
    if re.search(r"\brtx\s*(20|30)\d{2}\b", label, re.I):
        if (parse_driver_version(ver) or ()) >= (parse_driver_version("610.00") or ()):
            if "security update" not in name and "game ready" not in name:
                return False
    return True


def _nvidia_psid_pfid_from_ctx(ctx: dict) -> tuple[str, str]:
    """Primary product series / product IDs for NVIDIA manual lookup."""
    candidates = _nvidia_psid_pfid_candidates(ctx)
    if candidates:
        return candidates[0]
    return "120", "942"


def _nvidia_normalize_release_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", s)
    if m:
        try:
            dt = datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y"
            )
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    parsed = parse_driver_package_date(s)
    if parsed:
        return parsed.isoformat()
    return s


def _nvidia_offer_from_ajax(di: dict, ctx: dict) -> dict:
    ver = (di.get("Version") or "").strip()
    name = urllib.parse.unquote_plus(
        (di.get("NameLocalized") or di.get("Name") or "").strip()
    )
    rel = (di.get("ReleaseDateTime") or di.get("Release") or "").strip()
    date = _nvidia_normalize_release_date(rel)
    dl = (di.get("DownloadURL") or "").strip()
    details = (di.get("DetailsURL") or "").strip()
    display = (di.get("DisplayVersion") or di.get("GFE_DisplayVersion") or ver).strip()
    url = dl or details or "https://www.nvidia.com/en-us/drivers/"
    notes = f"From NVIDIA driver lookup (Game Ready WHQL). Branch version {ver}."
    if display and display != ver:
        notes += f" Windows reports {display} for some packages."
    if _looks_like_nvidia_branch_version(ver):
        notes += (
            f" Compare using the branch version (e.g. {ver}), "
            "not HD Audio / USBC component versions."
        )
    offer = {
        "source": "vendor",
        "source_label": "Manufacturer (NVIDIA)",
        "title": name or "NVIDIA Game Ready Driver",
        "version": ver,
        "date": date,
        "url": url,
        "download_kind": "url",
        "update_id": (di.get("ID") or "").strip(),
        "instance_id": "",
        "notes": notes,
        "confidence": "high",
    }
    if dl and any(
        dl.lower().split("?")[0].endswith(ext)
        for ext in _dc("_DOWNLOAD_EXTENSIONS")
    ):
        offer["install_verified"] = True
        offer["download_resolvable"] = True
    if display and display != ver and _looks_like_nvidia_internal_version(display):
        offer["windows_display_version"] = display
    return offer


def _nvidia_fetch_ajax_driver_lookup(
    ctx: dict,
    *,
    os_id: str | None = None,
    psid: str | None = None,
    pfid: str | None = None,
) -> dict | None:
    """NVIDIA Game Ready version via AjaxDriverService (current live API)."""
    os_id = os_id or _nvidia_windows_os_id()
    if psid is None or pfid is None:
        default_psid, default_pfid = _nvidia_psid_pfid_from_ctx(ctx)
        psid = psid or default_psid
        pfid = pfid or default_pfid
    url = (
        "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/"
        f"AjaxDriverService.php?func=DriverManualLookup&psid={psid}&pfid={pfid}"
        f"&osID={os_id}&languageCode=1033&isWHQL=1&dch=1&sort1=0&numberOfResults=1"
    )
    ok, body = _dc("_http_get")(url)
    if not ok or not (body or "").strip():
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    ids = data.get("IDS") or []
    if not ids:
        return None
    di = (ids[0] or {}).get("downloadInfo") or {}
    if not (di.get("Version") or "").strip():
        return None
    return di


def _nvidia_fetch_ajax_best_match(ctx: dict, *, os_id: str | None = None) -> dict | None:
    """Try psid/pfid candidates until one returns a GPU-plausible driver."""
    os_id = os_id or _nvidia_windows_os_id()
    for psid, pfid in _nvidia_psid_pfid_candidates(ctx):
        hit = _dc("_nvidia_fetch_ajax_driver_lookup")(
            ctx, os_id=os_id, psid=psid, pfid=pfid
        )
        if hit and _dc("_nvidia_ajax_result_plausible")(hit, ctx):
            return hit
    return None


def _nvidia_fetch_ajax_alternate_os(ctx: dict) -> dict | None:
    """Try the other Windows osID when the primary lookup returns nothing."""
    primary = _nvidia_windows_os_id()
    for alt in ("135", "57"):
        if alt == primary:
            continue
        hit = _dc("_nvidia_fetch_ajax_best_match")(ctx, os_id=alt)
        if hit:
            return hit
    return None


def _nvidia_parse_processfind_html(html: str) -> dict | None:
    """Parse processFind.aspx driver list (HTML fallback when JSON API fails)."""
    rows = re.findall(r'id=["\']driverList["\'][^>]*>([\s\S]*?)</tr>', html, re.I)
    best_ver = ""
    best_date = ""
    for row in rows:
        ver_m = re.search(r'class=["\']version["\'][^>]*>([^<]+)', row, re.I)
        if not ver_m:
            continue
        ver = ver_m.group(1).strip()
        if not re.match(r"^\d{3}\.\d{2,3}$", ver):
            continue
        date_m = re.search(r'class=["\']date["\'][^>]*>([^<]+)', row, re.I)
        date_s = date_m.group(1).strip() if date_m else ""
        if not best_ver or (parse_driver_version(ver) or ()) > (
            parse_driver_version(best_ver) or ()
        ):
            best_ver = ver
            best_date = date_s
    if not best_ver:
        cells = re.findall(r">(\d{3}\.\d{2,3})<", html)
        if not cells:
            return None
        best_ver = max(cells, key=lambda v: parse_driver_version(v) or ())
    return {
        "Version": best_ver,
        "ReleaseDateTime": best_date,
        "NameLocalized": "GeForce Game Ready Driver",
        "DownloadURL": "",
        "ID": "",
    }


def _nvidia_fetch_processfind_lookup(ctx: dict) -> dict | None:
    os_id = _nvidia_windows_os_id()
    psid, pfid = _nvidia_psid_pfid_from_ctx(ctx)
    url = (
        "https://www.nvidia.com/Download/processFind.aspx?"
        f"psid={psid}&pfid={pfid}&osid={os_id}&lid=1&dtcid=1&lang=en-us"
    )
    ok, html = _dc("_http_get")(url)
    if not ok:
        return None
    return _dc("_nvidia_parse_processfind_html")(html)


def _nvidia_html_fallback_enabled(settings: dict | None = None) -> bool:
    try:
        import app_settings as app_set

        s = settings if settings is not None else app_set.load_settings()
        return bool(s.get("nvidia_html_lookup_fallback"))
    except ImportError:
        return False


def _nvidia_lookup_download_info(
    ctx: dict,
    *,
    settings: dict | None = None,
) -> tuple[dict | None, str]:
    """Ordered NVIDIA sources; records failed steps in vendor_fetch diagnostics."""
    try:
        import vendor_fetch as vf
    except ImportError:
        for name, fn in (
            ("ajax_grd", lambda: _dc("_nvidia_fetch_ajax_best_match")(ctx)),
            ("ajax_alt_os", lambda: _dc("_nvidia_fetch_ajax_alternate_os")(ctx)),
        ):
            hit = fn()
            if hit:
                return hit, name
        if _nvidia_html_fallback_enabled(settings):
            hit = _dc("_nvidia_fetch_processfind_lookup")(ctx)
            if hit:
                return hit, "processfind_html"
        return None, ""

    steps: list[vf.FetchStep] = [
        vf.FetchStep("ajax_grd", lambda: _dc("_nvidia_fetch_ajax_best_match")(ctx)),
        vf.FetchStep("ajax_alt_os", lambda: _dc("_nvidia_fetch_ajax_alternate_os")(ctx)),
    ]
    if _nvidia_html_fallback_enabled(settings):
        steps.append(
            vf.FetchStep(
                "processfind_html",
                lambda: _dc("_nvidia_fetch_processfind_lookup")(ctx),
            )
        )
    result = vf.run_steps(steps, vendor="nvidia")
    return result.value, result.method


def fetch_nvidia_driver_offer(ctx: dict) -> list[dict]:
    from catalog_mscatalog_session import is_quick_check_mode

    if not _dc("_nvidia_ctx_eligible")(ctx):
        return []
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        "nvidia", _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    pnp_id = _dc("_nvidia_pnp_id_from_ctx")(ctx)

    if pnp_id and not _nvidia_gpu_within_support_floor(ctx):
        url, _ = _dc("_VENDOR_DRIVER_URLS").get(
            "nvidia", ("https://www.nvidia.com/en-us/drivers/", "")
        )
        return [
            _dc("_vendor_coverage_gap_offer")(
                source_label="Manufacturer (NVIDIA)",
                vendor_disp="NVIDIA",
                title="NVIDIA driver downloads — below supported generation (GTX 900+)",
                url=url,
            )
        ]

    if not pnp_id:
        if not is_quick_check_mode():
            ajax_di, method = _dc("_nvidia_lookup_download_info")(ctx)
            if ajax_di:
                offer = _dc("_nvidia_offer_from_ajax")(ajax_di, ctx)
                if method == "processfind_html":
                    offer["notes"] = (
                        "From NVIDIA driver search page (HTML fallback; JSON lookup failed)."
                    )
                    offer["confidence"] = "medium"
                return [offer]
        url, _ = _dc("_VENDOR_DRIVER_URLS").get(
            "nvidia", ("https://www.nvidia.com/en-us/drivers/", "")
        )
        return [{
            "source": "vendor",
            "source_label": "Manufacturer (NVIDIA)",
            "title": "NVIDIA driver downloads",
            "version": "",
            "date": "",
            "url": url,
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": "Could not read GPU hardware ID; open NVIDIA site manually.",
            "confidence": "low",
        }]

    cache_key = _dc("_nvidia_vendor_cache_key")(ctx)
    cached_offer = _dc("_vendor_scrape_cache_get")(cache_key)
    if isinstance(cached_offer, dict) and cached_offer.get("title"):
        return [cached_offer]

    if not is_quick_check_mode():
        ajax_di, method = _dc("_nvidia_lookup_download_info")(ctx)
        if ajax_di:
            offer = _dc("_nvidia_offer_from_ajax")(ajax_di, ctx)
            if method == "processfind_html":
                offer["notes"] = (
                    "From NVIDIA driver search page (HTML fallback; JSON lookup failed)."
                )
                offer["confidence"] = "medium"
            _dc("_vendor_scrape_cache_set")(cache_key, offer)
            return [offer]

    url, _ = _dc("_VENDOR_DRIVER_URLS").get(
        "nvidia", ("https://www.nvidia.com/en-us/drivers/", "")
    )
    return [{
        "source": "vendor",
        "source_label": "Manufacturer (NVIDIA)",
        "title": "NVIDIA driver downloads (manual)",
        "version": "",
        "date": "",
        "url": url,
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": (
            "NVIDIA automatic lookup failed (Ajax + HTML fallbacks). "
            "Download from the site."
        ),
        "confidence": "low",
    }]
