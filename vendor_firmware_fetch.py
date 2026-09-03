"""Robust OEM/storage firmware fetch — WAF-aware HTTP, vendor-specific APIs."""
from __future__ import annotations

import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import driver_catalog as dc

_ASUS_REFERER = "https://www.asus.com/support/download-center/"
_ROG_REFERER = "https://rog.asus.com/support/"
SEAGATE_DOWNLOAD_FINDER = "https://apps1.seagate.com/downloads/request.html"


def fetch_http_robust(
    url: str,
    *,
    referer: str | None = None,
    accept: str = "text/html,application/xhtml+xml",
) -> tuple[bool, str]:
    """WAF-aware GET shared by driver and firmware catalog paths."""
    return dc._vendor_http_get_robust(
        url,
        referer=referer,
        accept=accept,
        attempts=3,
    )


def fetch_json_robust(
    url: str,
    *,
    referer: str | None = None,
    accept: str = "application/json, text/plain, */*",
) -> tuple[bool, str]:
    """WAF-aware GET for vendor JSON APIs (MSI, Lenovo, HP SWD, Zendesk, …)."""
    return fetch_http_robust(url, referer=referer, accept=accept)


def warm_oem_catalogs_parallel(
    system_ctx: dict | None,
    *,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Populate OEM session cache once per firmware scan (parallel)."""
    if dc.is_quick_check_mode() or not dc._oem_session_cache_enabled:
        return
    warmers = dc._oem_live_row_warmers(system_ctx)
    if not warmers:
        return
    if progress:
        progress(f"Warming {len(warmers)} OEM catalog(s)…")

    def _warm_one(item: tuple[str, Callable]) -> None:
        tag, fn = item
        try:
            dc._cached_oem_rows(tag, fn, system_ctx)
        except Exception as exc:
            try:
                import session_log

                session_log.progress(
                    "firmware",
                    f"OEM warm {tag}: {type(exc).__name__}",
                    extra={"status": "skip"},
                )
            except Exception:
                pass  # optional session_log; must not break OEM warm path

    workers = min(6, len(warmers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_warm_one, w) for w in warmers]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as exc:
                try:
                    import session_log

                    session_log.progress(
                        "firmware",
                        f"OEM warm task: {type(exc).__name__}",
                        extra={"status": "skip"},
                    )
                except Exception:
                    pass  # optional session_log; must not break OEM warm path


def warm_ssd_vendor_pages(
    drives: list[dict] | None,
    scan_cache: dict[str, str],
    *,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Pre-fetch unique SSD vendor support pages (one URL per vendor per scan)."""
    if not drives or scan_cache is None:
        return
    try:
        import firmware_ssd_vendors as fsv
    except ImportError:
        return

    seen_urls: set[str] = set()
    tasks: list[tuple[str, str, str]] = []
    for drive in drives:
        vk = (drive.get("vendor_key") or "").strip().lower()
        if not vk or vk == "seagate":
            continue
        cfg = fsv.SSD_VENDOR_REGISTRY.get(vk)
        if not cfg or not cfg.primary_url:
            continue
        url = cfg.primary_url.strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        tasks.append((vk, url, cfg.display_name))

    if not tasks:
        return
    if progress:
        progress(f"Warming {len(tasks)} SSD vendor page(s)…")

    def _fetch_one(item: tuple[str, str, str]) -> tuple[str, str, str]:
        vk, url, _name = item
        ok, html, _method = fetch_html_with_js_fallback(url)
        return vk, url, html if ok else ""

    with ThreadPoolExecutor(max_workers=min(4, len(tasks))) as ex:
        for fut in as_completed([ex.submit(_fetch_one, t) for t in tasks]):
            try:
                vk, url, html = fut.result()
            except Exception:
                continue
            if not html:
                continue
            scan_cache[vk] = html
            scan_cache[url] = html
            scan_cache[f"ssd_page:{url}"] = html


def warm_firmware_batch(
    system_ctx: dict | None,
    *,
    ssd_drives: list[dict] | None = None,
    secondary_devices: list[dict] | None = None,
    scan_cache: dict[str, str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """
    One-shot firmware scan warm: OEM catalogs, SSD vendor pages, peripheral searches.

    Returns the shared ``scan_cache`` dict (mutated in place).
    """
    cache = scan_cache if scan_cache is not None else {}
    if dc.is_quick_check_mode():
        return cache

    warm_oem_catalogs_parallel(system_ctx, progress=progress)
    warm_ssd_vendor_pages(ssd_drives, cache, progress=progress)

    if secondary_devices:
        try:
            import firmware_peripheral_vendors as fpv

            fpv.warm_peripheral_search_cache(
                secondary_devices,
                cache,
                progress=progress,
            )
        except ImportError:
            pass
    return cache


def fetch_html_with_js_fallback(
    url: str,
    *,
    referer: str | None = None,
) -> tuple[bool, str, str]:
    """HTML GET with optional headless fallback when static fetch is blocked."""

    def _get(target: str) -> tuple[bool, str]:
        return fetch_http_robust(
            target,
            referer=referer or url,
            accept="text/html,application/xhtml+xml",
        )

    try:
        import vendor_page_render as vpr
    except ImportError:
        ok, body = _get(url)
        return ok, body, "http"
    ok, body, method = vpr.fetch_html_with_js_fallback(url, _get, allow_js=True)
    return ok, body or "", method or "http"


def fetch_asus_product_rows(
    system_ctx: dict | None,
) -> tuple[list[dict], str, str]:
    """
    ASUS / ROG product catalog via JSON API (drivers + BIOS + firmware categories).

    Returns (rows, fallback_support_url, status) where status is
    ``ok`` | ``waf_blocked`` | ``model_not_found`` | ``not_applicable``.
    """
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").lower()
    bb_mfr = (ctx.get("baseboard_manufacturer") or "").lower()
    if not dc._manufacturer_matches(mfr, "asus", "rog", "republic of gamers") and not dc._manufacturer_matches(
        bb_mfr, "asus"
    ):
        return [], "", "not_applicable"

    osid = dc._windows_osid()
    fallback = "https://www.asus.com/support/download-center/"
    all_rows: list[dict] = []
    waf_hit = False
    tried: set[str] = set()

    api_endpoints: list[tuple[str, str, str]] = []
    for model in dc._oem_model_candidates(ctx):
        for variant in dc._oem_model_slug_variants(model):
            if variant in tried:
                continue
            tried.add(variant)
            enc = urllib.parse.quote(variant)
            api_endpoints.append(
                (
                    f"https://www.asus.com/support/api/product.asmx/GetPDDrivers?"
                    f"osid={osid}&website=global&model={enc}",
                    _ASUS_REFERER,
                    "asus_api",
                )
            )
            api_endpoints.append(
                (
                    f"https://rog.asus.com/support/webapi/product/GetPDDrivers?"
                    f"website=global&model={enc}&osid={osid}&systemCode=rog",
                    _ROG_REFERER,
                    "rog_api",
                )
            )

    for url, referer, _tag in api_endpoints:
        ok, body = fetch_http_robust(
            url,
            referer=referer,
            accept="application/json, text/plain, */*",
        )
        if not ok or not body:
            if body and _looks_like_bot_challenge(body):
                waf_hit = True
            continue
        if '"FAIL"' in body[:160] or '"Status":"FAIL"' in body[:200]:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            if _looks_like_bot_challenge(body):
                waf_hit = True
            continue
        if (data.get("Status") or "").upper() == "FAIL":
            continue
        rows = dc._parse_asus_driver_json(data)
        if rows:
            all_rows = rows
            break

    if all_rows:
        _record_vendor_health("asus", ok=True, note=f"{len(all_rows)} catalog row(s)")
        return all_rows, fallback, "ok"

    # HTML fallback: model support page may list BIOS when JSON API is blocked.
    model = (ctx.get("system_model") or ctx.get("baseboard_product") or "").strip()
    if model:
        slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
        for page_url in (
            f"https://www.asus.com/supportonly/{slug}/helpdesk_download/",
            f"https://rog.asus.com/laptops/{slug}/helpdesk_download/",
        ):
            ok, html, method = fetch_html_with_js_fallback(page_url, referer=_ASUS_REFERER)
            if not ok or not html:
                if waf_hit or (html and _looks_like_bot_challenge(html)):
                    waf_hit = True
                continue
            scraped = _parse_asus_support_html_firmware_rows(html, model)
            if scraped:
                _record_vendor_health("asus", ok=True, note=f"html:{method}:{len(scraped)} row(s)")
                return scraped, fallback, "ok_html_fallback"

    if waf_hit:
        _record_vendor_health("asus", ok=False, note="waf_or_challenge")
        return [], fallback, "waf_blocked"

    _record_vendor_health("asus", ok=False, note="model_not_found")
    return [], fallback, "model_not_found"


def _parse_asus_support_html_firmware_rows(html: str, model: str) -> list[dict]:
    """Best-effort BIOS/firmware rows from ASUS support HTML when JSON API fails."""
    if not html:
        return []
    rows: list[dict] = []
    model_tok = (model or "").split()[0].lower()[:12]
    for m in re.finditer(
        r'href=["\']([^"\']+\.(?:zip|exe|cap|bin|CAP))["\']',
        html,
        re.I,
    ):
        url = urllib.parse.urljoin("https://www.asus.com/", m.group(1))
        start = max(0, m.start() - 400)
        window = html[start : m.end() + 120].lower()
        if not any(k in window for k in ("bios", "uefi", "firmware", "ec ", " capsule")):
            continue
        if model_tok and model_tok not in window and "bios" not in window:
            continue
        ver = ""
        vm = re.search(r"\b(\d+\.\d+(?:\.\d+){0,3})\b", window)
        if vm:
            ver = vm.group(1)
        title_m = re.search(r">([^<]{8,100})<", html[start : m.end()])
        title = (title_m.group(1).strip() if title_m else "ASUS BIOS/firmware")[:120]
        rows.append({
            "title": title,
            "version": ver,
            "date": "",
            "url": url,
            "category": "BIOS",
        })
    return rows


def _record_vendor_health(vendor: str, *, ok: bool, note: str = "") -> None:
    try:
        import vendor_endpoint_health as veh

        veh.record_probe(vendor, "firmware_catalog", ok=ok, detail=note[:200])
    except (ImportError, AttributeError):
        pass


def _looks_like_bot_challenge(body: str) -> bool:
    try:
        import vendor_page_render as vpr

        return vpr.looks_like_bot_challenge(body or "")
    except ImportError:
        low = (body or "").lower()
        return "access denied" in low or "cf-browser-verification" in low


_SEAGATE_DOWNLOAD_FINDER = SEAGATE_DOWNLOAD_FINDER
_SEAGATE_FINDER_REFERER = "https://www.seagate.com/support/downloads/"
_SEAGATE_HYBRID_SUPPORT = (
    "https://www.seagate.com/support/internal-hard-drives/laptop-hard-drives/firecuda-2-5/"
)


def normalize_seagate_model(model: str) -> str:
    """Base model token (ST2000LX001) from WMI strings like ST2000LX001-1RG174."""
    m = (model or "").strip().upper()
    if not m:
        return ""
    m = m.split()[0]
    if "-" in m:
        m = m.split("-", 1)[0]
    return m


def seagate_support_url_for_model(model: str) -> str:
    base = normalize_seagate_model(model)
    if base.startswith(("ST2000LX", "ST1000LX", "ST500LX", "ST1000LM", "ST500LM")):
        return _SEAGATE_HYBRID_SUPPORT
    return "https://www.seagate.com/support/downloads/"


def fetch_seagate_firmware_lookup(
    serial: str,
    model: str,
) -> tuple[bool, str, str]:
    """
    Query Seagate Download Finder with serial + model.

    Returns ``(ok, html_body, status)`` where status is
    ``ok`` | ``no_update`` | ``invalid_serial`` | ``blocked`` | ``error``.
    """
    serial = (serial or "").strip()
    model = normalize_seagate_model(model)
    if not serial or not model:
        return False, "", "missing_input"
    if serial.upper().startswith("ST") and len(serial) > 6:
        return False, "", "invalid_serial"

    try:
        import urllib.request
        from http.cookiejar import CookieJar

        cj = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        opener.open(
            urllib.request.Request(_SEAGATE_DOWNLOAD_FINDER, headers=headers),
            timeout=20,
        )
        data = urllib.parse.urlencode({
            "action": "requestFirmware",
            "serialNumber": serial,
            "partNumber": model,
            "displayModelPartTextbox": "true",
            "showSingleInput": "true",
            "countryCode": "US",
            "agreeEulaSelected": "on",
            "hiddenAgreeEula": "true",
            "deviceType": "Desktop",
            "deviceOrientation": "Landscape",
            "deviceOS": "Windows",
        }).encode()
        post_headers = dict(headers)
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Referer"] = _SEAGATE_DOWNLOAD_FINDER
        resp = opener.open(
            urllib.request.Request(
                _SEAGATE_DOWNLOAD_FINDER,
                data=data,
                headers=post_headers,
                method="POST",
            ),
            timeout=30,
        )
        body = resp.read().decode("utf-8", "replace")
    except Exception:
        _record_vendor_health("seagate", ok=False, note="download_finder_error")
        return False, "", "error"

    low = body.lower()
    if _looks_like_bot_challenge(body):
        _record_vendor_health("seagate", ok=False, note="waf_or_challenge")
        return False, body, "blocked"
    if any(x in low for x in (
        "no firmware update",
        "already has the latest",
        "firmware update is not available",
        "does not have a firmware update",
    )):
        _record_vendor_health("seagate", ok=True, note="no_update")
        return True, body, "no_update"
    if any(x in low for x in ("invalid serial", "not recognize", "unrecognized input")):
        return False, body, "invalid_serial"

    parsed = parse_seagate_download_finder_html(body, model)
    if parsed.get("version"):
        _record_vendor_health("seagate", ok=True, note=f"fw:{parsed['version']}")
        return True, body, "ok"
    if "download" in low and model.lower() in low:
        _record_vendor_health("seagate", ok=True, note="result_no_version")
        return True, body, "ok"
    return False, body, "error"


def parse_seagate_download_finder_html(html: str, model: str) -> dict:
    """Extract firmware version + download URL from Download Finder result HTML."""
    if not html:
        return {}
    base = normalize_seagate_model(model)
    low = html.lower()
    version = ""
    url = ""

    for pat in (
        r"\b(CC\d{2,4}|SN\d{2,4}|TN\d{2,4}|SU[A-Z0-9]{2,6})\b",
        r"Firmware\s+(?:Version|Rev(?:ision)?)\s*[:\-]?\s*([A-Z0-9]{2,12})",
        r"Latest\s+firmware\s*[:\-]?\s*([A-Z0-9]{2,12})",
        r"Recommended\s+firmware\s*[:\-]?\s*([A-Z0-9]{2,12})",
    ):
        for m in re.finditer(pat, html, re.I):
            cand = m.group(1).upper()
            if cand in ("DOWNLOAD", "FIRMWARE", "RESULTS") or cand.isdigit() or len(cand) < 2:
                continue
            version = cand
            break
        if version:
            break

    for m in re.finditer(r'href=["\']([^"\']+\.(?:lod|bin|zip|exe))["\']', html, re.I):
        href = m.group(1)
        if base and base.lower() not in href.lower() and version and version.lower() not in href.lower():
            continue
        url = urllib.parse.urljoin(_SEAGATE_DOWNLOAD_FINDER, href)
        vm = re.search(r"([A-Z]{2}\d{2,4})", href, re.I)
        if vm and not version:
            version = vm.group(1).upper()
        break

    if not version and base.lower() in low:
        vm = re.search(rf"{re.escape(base)}[^<]{{0,200}}\b([A-Z]{{2}}\d{{2,4}})\b", html, re.I)
        if vm:
            version = vm.group(1).upper()

    return {"version": version, "url": url}
