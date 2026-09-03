"""Peripheral firmware — search vendor support sites for published firmware updaters.

Many USB peripherals publish firmware on vendor support portals (standalone downloaders
or KB articles), not only through desktop apps like Synapse or G HUB. This module
searches those sites before falling back to utility-only links.

Backends:
  - ``razer_kw`` — mysupport.razer.com keyword search (static HTML)
  - ``zendesk_api`` — Zendesk Help Center JSON search (Logitech, Corsair, SteelSeries, Elgato)
  - ``hyperx_web`` — hyperx.com support / NGENUITY page (link-only when no API)
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable

_USB_VID_PID_RE = re.compile(r"VID[_&]([0-9A-F]{4}).*?PID[_&]([0-9A-F]{4})", re.I)

# --- Shared version extraction (title + body) ---
_VERSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Firmware update v([\d._r]+)", re.I),
    re.compile(r"Update firmware version\s+([\d.]+(?:\.\d+)*)", re.I),
    re.compile(r"firmware version\s+([\d.]+(?:\.\d+)*)", re.I),
    re.compile(r"Software Version:\s*([\d.]+(?:\.\d+)*)", re.I),
    re.compile(
        r"Version[\s\S]{0,400}?<td>\s*([\d]+(?:\.[\d]+){1,4})\s*</td>",
        re.I,
    ),
    re.compile(
        r"\|\s*Version\s*\|\s*Release Date\s*\|[\s\S]*?\|\s*([\d]+(?:\.[\d]+){1,4})\s*\|",
        re.I,
    ),
    re.compile(r"\bfirmware\s+v?\s*([\d]+(?:\.[\d]+){1,4}[a-z]?)\b", re.I),
)

_GENERIC_ZENDESK_TITLE_RE = re.compile(
    r"supported in .*firmware update tool|what are the devices",
    re.I,
)

_GENERIC_LABEL_TOKENS = frozenset({
    "hid", "keyboard", "mouse", "device", "gaming", "virtual", "usb", "wireless",
    "receiver", "composite", "consumer", "control", "interface", "logitech", "razer",
})

_RAZER_FW_TITLE_RE = re.compile(
    r"<h3><a href='/app/answers/detail/a_id/(\d+)[^']*'>([^<]+)</a></h3>",
    re.I,
)
_RAZER_H1_RE = re.compile(r"<h1[^>]*>([^<]+)", re.I)
_RAZER_SKU_RE = re.compile(r"RZ03-\d{5}", re.I)
_RAZER_DOWNLOAD_RE = re.compile(r"https?://rzr\.to/[A-Za-z0-9]+", re.I)

_ZENDESK_H1_RE = re.compile(r"<h1[^>]*>([^<]+)", re.I)


@dataclass(frozen=True)
class UsbProductHint:
    vendor_key: str
    product_name: str
    sku: str = ""
    search_terms: tuple[str, ...] = ()
    firmware_article_ids: tuple[str, ...] = ()


USB_PRODUCT_HINTS: dict[str, UsbProductHint] = {
    "1532:0277": UsbProductHint(
        "razer",
        "Razer Pro Type Ultra",
        sku="RZ03-04110",
        search_terms=("Pro Type Ultra firmware", "RZ03-04110 firmware"),
        firmware_article_ids=("6217",),
    ),
    "1532:027b": UsbProductHint(
        "razer",
        "Razer Pro Type Ultra",
        sku="RZ03-04110",
        search_terms=("Pro Type Ultra firmware", "RZ03-04110 firmware"),
        firmware_article_ids=("6217",),
    ),
    "046d:c081": UsbProductHint(
        "logitech",
        "Logitech G900 Gaming Mouse",
        search_terms=("G900 firmware", "G900 Gaming Mouse firmware"),
    ),
    "046d:408a": UsbProductHint(
        "logitech",
        "Logitech MX Keys",
        search_terms=(
            "MX Keys firmware release notes",
            "MX Keys firmware update",
        ),
        firmware_article_ids=("14648663676183",),
    ),
    "046d:c52b": UsbProductHint(
        "logitech",
        "Logitech MX Master 3",
        search_terms=("MX Master 3 firmware",),
    ),
    "1b1c:1b3d": UsbProductHint(
        "corsair",
        "CORSAIR K70 RGB PRO",
        search_terms=("K70 RGB PRO firmware", "K70 firmware"),
    ),
    "1038:161c": UsbProductHint(
        "steelseries",
        "SteelSeries Apex Pro",
        search_terms=("Apex Pro firmware",),
    ),
}


@dataclass(frozen=True)
class PeripheralReferenceProfile:
    vendor_key: str
    device_id: str
    label: str
    pnp_class: str = "Keyboard"
    subcategory: str = "keyboard"
    notes: str = ""


PERIPHERAL_REFERENCE_PROFILES: tuple[PeripheralReferenceProfile, ...] = (
    PeripheralReferenceProfile(
        "razer",
        r"HID\VID_1532&PID_0277&MI_00\9&2CE64270&0&0000",
        "Razer Pro Type Ultra",
        notes="mysupport article a_id/6217 — not Synapse",
    ),
    PeripheralReferenceProfile(
        "logitech",
        r"HID\VID_046D&PID_C232\2&357F35A&0&0000",
        "Logitech Gaming Virtual Keyboard",
        notes="Virtual HID — search support articles by vendor + class",
    ),
    PeripheralReferenceProfile(
        "corsair",
        r"HID\VID_1B1C&PID_1B3D&MI_00\8&0000000&0&0000",
        "CORSAIR K70 RGB PRO",
        notes="Corsair web firmware utility + iCUE articles",
    ),
)


@dataclass
class PeripheralScrapeResult:
    title: str
    version: str
    url: str
    notes: str
    coverage_check_failed: bool = False
    coverage_reason: str = ""
    parse_method: str = ""
    product_name: str = ""
    sku: str = ""
    download_url: str = ""


@dataclass(frozen=True)
class FallbackLink:
    title: str
    url: str
    notes: str = ""


@dataclass(frozen=True)
class VendorSiteConfig:
    vendor_key: str
    display_name: str
    backend: str  # razer_kw | zendesk_api | hyperx_web
    base_url: str = ""
    locale_path: str = "/hc/en-us"
    fallback_links: tuple[FallbackLink, ...] = ()
    desktop_app: str = ""
    search_fn: Callable[[dict, "VendorSiteConfig", dict[str, str] | None], PeripheralScrapeResult | None] | None = None


def usb_vid_pid(device_id: str) -> tuple[str, str]:
    m = _USB_VID_PID_RE.search(device_id or "")
    if not m:
        return "", ""
    return m.group(1).upper(), m.group(2).upper()


def product_hint(device_id: str, label: str = "") -> UsbProductHint | None:
    vid, pid = usb_vid_pid(device_id)
    if vid and pid:
        hit = USB_PRODUCT_HINTS.get(f"{vid}:{pid}".lower())
        if hit:
            return hit
    text = (label or "").lower()
    if "pro type ultra" in text:
        return USB_PRODUCT_HINTS.get("1532:0277")
    return None


def _model_tokens(label: str, hint: UsbProductHint | None) -> list[str]:
    tokens: list[str] = []
    if hint:
        if hint.product_name:
            tokens.extend(re.findall(r"[a-z0-9]{2,}", hint.product_name.lower()))
        if hint.sku:
            tokens.append(hint.sku.lower())
        tokens.extend(t.lower() for t in hint.search_terms)
    try:
        import driver_catalog as dc

        mh = dc._peripheral_model_hint(label or "")
        if mh:
            tokens.extend(re.findall(r"[a-z0-9]{2,}", mh.lower()))
    except ImportError:
        pass
    label_tokens = [
        t for t in re.findall(r"[a-z0-9]{2,}", (label or "").lower())
        if t not in _GENERIC_LABEL_TOKENS and len(t) >= 3
    ]
    tokens.extend(label_tokens)
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:12]


def build_search_queries(ctx: dict, cfg: VendorSiteConfig) -> list[str]:
    device_id = ctx.get("device_id") or ctx.get("instance_id") or ""
    label = ctx.get("device_label") or ctx.get("name") or ""
    sub = (ctx.get("subcategory") or ctx.get("pnp_class") or "device").lower()
    hint = product_hint(device_id, label)
    tokens = _model_tokens(label, hint)
    queries: list[str] = []

    if hint:
        queries.extend(hint.search_terms)
        if hint.product_name:
            queries.append(f"{hint.product_name} firmware")
        if hint.sku:
            queries.append(f"{hint.sku} firmware")

    # Model-ish tokens from label (G810, K70, Apex Pro, …)
    try:
        import driver_catalog as dc

        mh = dc._peripheral_model_hint(label or "")
        if mh:
            queries.append(f"{mh} firmware")
            queries.append(f"{mh} firmware update")
    except ImportError:
        pass

    if tokens:
        strong = [t for t in tokens if len(t) >= 4][:3]
        for t in strong:
            queries.append(f"{t} firmware update")

    device_word = "keyboard" if "keyboard" in sub else "mouse" if "mouse" in sub else "headset" if "headset" in sub else "device"
    queries.append(f"{cfg.display_name} {device_word} firmware update")
    queries.append(f"{device_word} firmware updater")

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        qn = " ".join(q.split()).strip()
        if len(qn) < 6 or qn.lower() in seen:
            continue
        seen.add(qn.lower())
        out.append(qn)
    return out[:8]


def _http_get(url: str, *, accept: str = "text/html,application/xhtml+xml") -> tuple[bool, str]:
    import driver_catalog as dc

    return dc._http_get(url, headers={"Accept": accept})


def _cache_key(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:16]


def _fetch_article_html(url: str, cache: dict[str, str] | None, cache_key: str) -> tuple[bool, str]:
    key = cache_key or _cache_key(url)
    if cache is not None and key in cache:
        return True, cache[key]
    try:
        import firmware_catalog as fwcat

        ok, html = fwcat._fetch_vendor_page_html(url)
    except ImportError:
        ok, html = _http_get(url)
    if cache is not None and ok and html:
        cache[key] = html
    return ok, html or ""


def extract_firmware_version(html: str, title: str = "") -> str:
    blob = f"{title}\n{html or ''}"
    for pat in _VERSION_PATTERNS:
        m = pat.search(blob)
        if m:
            return m.group(1).strip()
    return ""


def _score_article(
    title: str,
    snippet: str,
    *,
    queries: list[str],
    hint: UsbProductHint | None,
    subcategory: str,
) -> int:
    tl = f"{title} {snippet}".lower()
    score = 0
    if "firmware" in tl:
        score += 15
    if "updater" in tl or "update tool" in tl:
        score += 8
    if "firmware update" in tl:
        score += 10
    # Prefer articles that embed a version in the title (Logitech pattern)
    if re.search(r"firmware version\s+[\d.]+", tl, re.I):
        score += 12
    sub = subcategory.lower()
    if sub in tl:
        score += 6
    # Penalize wrong device classes
    if sub == "keyboard" and any(x in tl for x in ("ssd", "headset", "mouse firmware", "camera", "facecam")):
        score -= 25
    if sub == "mouse" and "keyboard" in tl and "mouse" not in tl:
        score -= 10
    if hint:
        if hint.product_name.lower() in tl:
            score += 20
        if hint.sku and hint.sku.lower() in tl:
            score += 25
        for term in hint.search_terms:
            tok = term.lower().replace(" firmware", "").strip()
            if tok and tok in tl:
                score += 15
        pn_tokens = [
            t for t in re.findall(r"[a-z0-9]{3,}", hint.product_name.lower())
            if t not in _GENERIC_LABEL_TOKENS
        ]
        if pn_tokens and not any(t in tl for t in pn_tokens[:4]):
            score -= 35
    if _GENERIC_ZENDESK_TITLE_RE.search(title):
        score -= 50
    for q in queries:
        for tok in re.findall(r"[a-z0-9]{3,}", q.lower()):
            if tok in _GENERIC_LABEL_TOKENS:
                continue
            if tok in tl:
                score += 8
    return score


def _robust_get(url: str, *, accept: str = "text/html,application/xhtml+xml") -> tuple[bool, str]:
    try:
        import vendor_firmware_fetch as vff

        return vff.fetch_http_robust(url, accept=accept)
    except ImportError:
        return _http_get(url, accept=accept)


def _robust_get_json(url: str) -> tuple[bool, str]:
    try:
        import vendor_firmware_fetch as vff

        return vff.fetch_json_robust(url)
    except ImportError:
        return _http_get(url, accept="application/json")


def search_zendesk_articles(
    base_url: str,
    query: str,
    locale_path: str = "/hc/en-us",
    *,
    cache: dict[str, str] | None = None,
) -> list[dict]:
    q_norm = " ".join((query or "").split()).strip().lower()
    cache_key = f"zendesk:{base_url.rstrip('/')}:{locale_path}:{q_norm}"
    if cache is not None and cache_key in cache:
        try:
            cached = json.loads(cache[cache_key])
            if isinstance(cached, list):
                return cached
        except json.JSONDecodeError:
            pass

    q = urllib.parse.quote(query)
    url = f"{base_url.rstrip('/')}/api/v2/help_center/articles/search.json?query={q}"
    ok, body = _robust_get_json(url)
    if not ok or not body or not body.lstrip().startswith("{"):
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []
    results = list(data.get("results") or [])
    if cache is not None:
        cache[cache_key] = json.dumps(results)
    return results


def search_razer_articles(
    query: str,
    html: str | None = None,
    *,
    cache: dict[str, str] | None = None,
) -> list[tuple[str, str, str]]:
    """Return list of (article_id, title, url)."""
    cache_key = f"razer_search:{query}"
    page = html
    if page is None and cache is not None:
        page = cache.get(cache_key)
    if page is None:
        url = f"https://mysupport.razer.com/app/answers/list/kw/{urllib.parse.quote(query)}"
        ok, page = _robust_get(url)
        if not ok:
            return []
        if cache is not None and page:
            cache[cache_key] = page
    hits: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for aid, title in _RAZER_FW_TITLE_RE.findall(page or ""):
        if aid in seen:
            continue
        seen.add(aid)
        tl = title.strip()
        if "firmware" not in tl.lower():
            continue
        article_url = f"https://mysupport.razer.com/app/answers/detail/a_id/{aid}"
        hits.append((aid, tl, article_url))
    return hits


def parse_razer_article(html: str, *, article_url: str) -> PeripheralScrapeResult | None:
    if not html:
        return None
    title = ""
    m_h1 = _RAZER_H1_RE.search(html)
    if m_h1:
        title = re.sub(r"\s+", " ", m_h1.group(1)).strip()
    if not title or "firmware" not in title.lower():
        return None
    version = extract_firmware_version(html, title)
    sku_m = _RAZER_SKU_RE.search(html)
    sku = sku_m.group(0).upper() if sku_m else ""
    dl_m = _RAZER_DOWNLOAD_RE.search(html)
    download_url = dl_m.group(0) if dl_m else ""
    notes = (
        "Standalone Razer Support firmware updater — many Razer devices are updated here, "
        "not through Synapse. Windows only reports the HID driver version."
    )
    if not version:
        return PeripheralScrapeResult(
            title=title[:120],
            version="",
            url=article_url,
            notes=notes,
            coverage_check_failed=True,
            coverage_reason="parse_failed",
            parse_method="razer_support_article",
            sku=sku,
            download_url=download_url,
        )
    return PeripheralScrapeResult(
        title=title[:120],
        version=version,
        url=article_url,
        notes=notes,
        parse_method="razer_support_article",
        sku=sku,
        download_url=download_url,
    )


def parse_zendesk_article(html: str, *, article_url: str, title_hint: str = "") -> PeripheralScrapeResult | None:
    if not html:
        return None
    title = (title_hint or "").strip()
    if not title:
        m_h1 = _ZENDESK_H1_RE.search(html)
        if m_h1:
            title = re.sub(r"\s+", " ", m_h1.group(1)).strip()
    if not title:
        return None
    tl = title.lower()
    if _GENERIC_ZENDESK_TITLE_RE.search(title):
        return None
    if "firmware" not in tl and "firmware" not in html.lower()[:8000]:
        return None
    version = extract_firmware_version(html, title)
    notes = (
        "Firmware published on the vendor support site — may be a standalone updater or "
        "instructions for the desktop app. Windows only reports the HID/driver package version."
    )
    if not version:
        return PeripheralScrapeResult(
            title=title[:120],
            version="",
            url=article_url,
            notes=notes,
            coverage_check_failed=True,
            coverage_reason="parse_failed",
            parse_method="zendesk_support_article",
        )
    return PeripheralScrapeResult(
        title=title[:120],
        version=version,
        url=article_url,
        notes=notes,
        parse_method="zendesk_support_article",
    )


def _collect_candidates(
    ctx: dict,
    cfg: VendorSiteConfig,
    cache: dict[str, str] | None,
) -> list[tuple[int, str, str, str]]:
    """Return scored candidates: (score, url, title, backend_tag)."""
    device_id = ctx.get("device_id") or ""
    label = ctx.get("device_label") or ctx.get("name") or ""
    sub = (ctx.get("subcategory") or ctx.get("pnp_class") or "device").lower()
    hint = product_hint(device_id, label)
    queries = build_search_queries(ctx, cfg)
    candidates: list[tuple[int, str, str, str]] = []

    if cfg.backend == "razer_kw":
        if hint:
            for aid in hint.firmware_article_ids:
                url = f"https://mysupport.razer.com/app/answers/detail/a_id/{aid}"
                candidates.append((1000, url, hint.product_name, "razer_known"))
        for q in queries:
            search_html = (cache or {}).get(f"razer_search:{q}")
            for aid, title, url in search_razer_articles(q, search_html, cache=cache):
                sc = _score_article(title, "", queries=queries, hint=hint, subcategory=sub)
                candidates.append((sc, url, title, "razer_search"))

    elif cfg.backend == "zendesk_api":
        if hint:
            for aid in hint.firmware_article_ids:
                for loc in (cfg.locale_path, "/hc/en-001"):
                    url = f"{cfg.base_url.rstrip('/')}{loc}/articles/{aid}"
                    candidates.append((1000, url, hint.product_name, "zendesk_known"))
        seen_ids: set[str] = set()
        for q in queries:
            rows = search_zendesk_articles(cfg.base_url, q, cfg.locale_path, cache=cache)
            for row in rows:
                aid = str(row.get("id") or "")
                if not aid or aid in seen_ids:
                    continue
                seen_ids.add(aid)
                title = (row.get("title") or "").strip()
                snippet = (row.get("snippet") or "").strip()
                if "firmware" not in f"{title} {snippet}".lower():
                    continue
                url = (row.get("html_url") or "").strip()
                if not url:
                    url = f"{cfg.base_url.rstrip('/')}{cfg.locale_path}/articles/{aid}"
                sc = _score_article(title, snippet, queries=queries, hint=hint, subcategory=sub)
                candidates.append((sc, url, title, "zendesk_api"))

    elif cfg.backend == "hyperx_web":
        for link in cfg.fallback_links:
            candidates.append((5, link.url, link.title, "hyperx_link"))
        # Phase C — also search HP Support (HyperX is HP-owned) when Zendesk API works.
        for q in queries[:3]:
            for base in ("https://support.hp.com",):
                rows = search_zendesk_articles(base, q, "/us-en", cache=cache)
                for row in rows:
                    title = (row.get("title") or "").strip()
                    snippet = (row.get("snippet") or "").strip()
                    if "firmware" not in f"{title} {snippet}".lower():
                        continue
                    if "hyperx" not in f"{title} {snippet}".lower() and "hyper x" not in f"{title} {snippet}".lower():
                        continue
                    url = (row.get("html_url") or "").strip()
                    aid = str(row.get("id") or "")
                    if not url and aid:
                        url = f"{base.rstrip('/')}/us-en/articles/{aid}"
                    sc = _score_article(title, snippet, queries=queries, hint=hint, subcategory=sub)
                    candidates.append((sc, url, title, "hp_hyperx_api"))

    # dedupe by URL keeping best score
    best: dict[str, tuple[int, str, str, str]] = {}
    for item in candidates:
        url = item[1]
        if url not in best or item[0] > best[url][0]:
            best[url] = item
    return sorted(best.values(), key=lambda x: (-x[0], x[1]))


def _fetch_from_site(ctx: dict, cfg: VendorSiteConfig, cache: dict[str, str] | None) -> PeripheralScrapeResult | None:
    device_id = ctx.get("device_id") or ""
    label = ctx.get("device_label") or ctx.get("name") or ""
    hint = product_hint(device_id, label)
    candidates = _collect_candidates(ctx, cfg, cache)

    for score, url, title, tag in candidates[:8]:
        if score < 5 and tag not in ("razer_known", "zendesk_known"):
            continue
        cache_key = f"article:{_cache_key(url)}"
        ok, html = _fetch_article_html(url, cache, cache_key)
        if not ok:
            continue
        if cfg.backend == "razer_kw":
            parsed = parse_razer_article(html, article_url=url)
        elif cfg.backend == "zendesk_api":
            parsed = parse_zendesk_article(html, article_url=url, title_hint=title)
        elif cfg.backend == "hyperx_web":
            parsed = parse_zendesk_article(html, article_url=url, title_hint=title)
            if parsed:
                parsed.notes = (
                    (parsed.notes or "")
                    + " HyperX firmware may also be published on HP Support or via NGENUITY."
                ).strip()
        else:
            parsed = None
        if parsed is None:
            continue
        if parsed.coverage_check_failed and tag not in ("razer_known", "zendesk_known"):
            continue
        if hint and not parsed.product_name:
            parsed = PeripheralScrapeResult(
                title=parsed.title,
                version=parsed.version,
                url=parsed.url,
                notes=parsed.notes,
                coverage_check_failed=parsed.coverage_check_failed,
                coverage_reason=parsed.coverage_reason,
                parse_method=parsed.parse_method or tag,
                product_name=hint.product_name,
                sku=parsed.sku or hint.sku,
                download_url=parsed.download_url,
            )
        elif not parsed.parse_method:
            parsed.parse_method = tag
        return parsed

    # Fallback portal links — still better than "open Synapse" alone
    if cfg.fallback_links:
        link = cfg.fallback_links[0]
        return PeripheralScrapeResult(
            title=link.title,
            version="",
            url=link.url,
            notes=link.notes or (
                f"No product-specific firmware article matched on {cfg.display_name} Support. "
                f"Search the portal for your model + 'firmware', or try {cfg.desktop_app or 'the vendor app'}."
            ),
            coverage_check_failed=True,
            coverage_reason="model_not_on_page",
            parse_method="fallback_portal",
            product_name=hint.product_name if hint else "",
            sku=hint.sku if hint else "",
        )

    return PeripheralScrapeResult(
        title=f"{cfg.display_name} peripheral — {(label or device_id)[:60]}",
        version="",
        url=cfg.base_url or "",
        notes=(
            f"Could not find a firmware article on {cfg.display_name}'s support site automatically. "
            "Search the vendor support portal for your product name + 'firmware'."
        ),
        coverage_check_failed=True,
        coverage_reason="model_not_on_page",
        product_name=hint.product_name if hint else "",
    )


VENDOR_SITE_REGISTRY: dict[str, VendorSiteConfig] = {
    "razer": VendorSiteConfig(
        "razer",
        "Razer",
        "razer_kw",
        base_url="https://mysupport.razer.com",
        desktop_app="Razer Synapse (optional — lighting/macros)",
        fallback_links=(
            FallbackLink(
                "Razer Support — search firmware articles",
                "https://mysupport.razer.com/app/answers/list/kw/firmware%20update",
                "Many Razer keyboards use standalone updaters here, not Synapse.",
            ),
        ),
    ),
    "logitech": VendorSiteConfig(
        "logitech",
        "Logitech",
        "zendesk_api",
        base_url="https://support.logi.com",
        desktop_app="Logi Options+ / G HUB",
        fallback_links=(
            FallbackLink(
                "Logitech Firmware Update Tool (legacy)",
                "https://support.logi.com/hc/en-us/articles/1500007306382-Firmware-Update-Tool",
                "Older standalone tool — many current devices use Options+ or G HUB instead.",
            ),
        ),
    ),
    "corsair": VendorSiteConfig(
        "corsair",
        "Corsair",
        "zendesk_api",
        base_url="https://help.corsair.com",
        desktop_app="CORSAIR iCUE",
        fallback_links=(
            FallbackLink(
                "CORSAIR Web Firmware Update Utility",
                "https://help.corsair.com/hc/en-us/articles/41337096296209-About-the-CORSAIR-Firmware-Update-Utility-website",
                "Browser-based updater for many keyboards, mice, and headsets — separate from iCUE.",
            ),
            FallbackLink(
                "iCUE — update device firmware",
                "https://help.corsair.com/hc/en-us/articles/360025278572-iCUE-Update-device-firmware",
            ),
        ),
    ),
    "steelseries": VendorSiteConfig(
        "steelseries",
        "SteelSeries",
        "zendesk_api",
        base_url="https://support.steelseries.com",
        desktop_app="SteelSeries GG",
        fallback_links=(
            FallbackLink(
                "SteelSeries — check firmware status",
                "https://support.steelseries.com/hc/en-us/articles/9196885563277-How-To-Check-if-your-SteelSeries-Product-s-Firmware-is-Up-To-Date",
            ),
        ),
    ),
    "elgato": VendorSiteConfig(
        "elgato",
        "Elgato",
        "zendesk_api",
        base_url="https://help.elgato.com",
        desktop_app="Elgato software",
        fallback_links=(
            FallbackLink(
                "Elgato Support — firmware articles",
                "https://help.elgato.com/hc/en-us/search?query=firmware+update",
            ),
        ),
    ),
    "hyperx": VendorSiteConfig(
        "hyperx",
        "HyperX",
        "hyperx_web",
        base_url="https://www.hyperx.com",
        desktop_app="HyperX NGENUITY",
        fallback_links=(
            FallbackLink(
                "HyperX NGENUITY — firmware via desktop app",
                "https://hyperx.com/pages/ngenuity",
                "HyperX does not expose a public Zendesk API; firmware is usually via NGENUITY.",
            ),
            FallbackLink(
                "HyperX support / drivers",
                "https://hyperx.com/pages/support/drivers",
            ),
        ),
    ),
}

# Alias keys from device_enrichment
_VENDOR_ALIASES = {
    "alienware": "dell",
}


def resolve_vendor_key(vendor_key: str) -> str:
    vk = (vendor_key or "").strip().lower()
    return _VENDOR_ALIASES.get(vk, vk)


def vendor_verify_info(vendor_key: str) -> dict[str, str]:
    """Desktop app name + support URL for manual firmware verification."""
    vk = resolve_vendor_key(vendor_key)
    cfg = VENDOR_SITE_REGISTRY.get(vk)
    if not cfg:
        return {}
    url = ""
    if cfg.fallback_links:
        url = cfg.fallback_links[0].url
    elif cfg.base_url:
        url = cfg.base_url
    return {
        "vendor_key": vk,
        "app_name": cfg.desktop_app or cfg.display_name,
        "url": url,
    }


def scrape_result_to_dict(result: PeripheralScrapeResult) -> dict:
    return {
        "title": result.title,
        "version": result.version,
        "url": result.url,
        "notes": result.notes,
        "coverage_check_failed": result.coverage_check_failed,
        "coverage_reason": result.coverage_reason,
        "parse_method": result.parse_method,
        "product_name": result.product_name,
        "sku": result.sku,
        "download_url": result.download_url,
    }


def coverage_gap_message(reason: str, vendor_disp: str) -> str:
    name = vendor_disp or "vendor"
    messages = {
        "fetch_failed": f"Could not load the {name} support page. Open the link manually.",
        "model_not_on_page": (
            f"Searched {name} Support but no product-specific firmware article matched. "
            "Try searching the portal for your exact model + 'firmware'."
        ),
        "parse_failed": (
            f"Found a {name} support article but could not read a firmware version from the page — "
            "open the link and compare manually."
        ),
        "utility_only": f"{name} may only publish firmware through their desktop app.",
    }
    return messages.get(reason, messages["parse_failed"])


def warm_peripheral_search_cache(
    devices: list[dict],
    cache: dict[str, str],
    *,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Dedupe and pre-run support-site searches once per firmware scan."""
    if not devices or cache is None:
        return

    razer_queries: set[str] = set()
    zendesk_tasks: set[tuple[str, str, str]] = set()

    for dev in devices:
        if (dev.get("category") or "").strip() != "usb_peripheral":
            continue
        vendor = (dev.get("vendor_key") or "").strip().lower()
        if not vendor:
            device_id = dev.get("device_id") or ""
            label = dev.get("resolved_name") or dev.get("component") or dev.get("name") or ""
            hint = product_hint(device_id, label)
            if hint and hint.vendor_key:
                vendor = hint.vendor_key
        cfg = VENDOR_SITE_REGISTRY.get(vendor)
        if not cfg:
            continue
        ctx = {
            "device_id": dev.get("device_id") or "",
            "device_label": dev.get("resolved_name") or dev.get("component") or dev.get("name") or "",
            "name": dev.get("name") or "",
            "subcategory": dev.get("subcategory") or "",
            "pnp_class": dev.get("pnp_class") or "",
        }
        for q in build_search_queries(ctx, cfg):
            qn = " ".join(q.split()).strip()
            if len(qn) < 6:
                continue
            if cfg.backend == "razer_kw":
                razer_queries.add(qn)
            elif cfg.backend == "zendesk_api":
                zendesk_tasks.add((cfg.base_url, cfg.locale_path, qn))
            elif cfg.backend == "hyperx_web":
                for base in ("https://support.hp.com",):
                    zendesk_tasks.add((base, "/us-en", qn))

    total = len(razer_queries) + len(zendesk_tasks)
    if not total:
        return
    if progress:
        progress(f"Warming {total} peripheral support search(es)…")

    for q in sorted(razer_queries):
        key = f"razer_search:{q}"
        if key not in cache:
            search_razer_articles(q, cache=cache)
    for base, locale, q in sorted(zendesk_tasks):
        key = f"zendesk:{base.rstrip('/')}:{locale}:{q.lower()}"
        if key not in cache:
            search_zendesk_articles(base, q, locale, cache=cache)


def fetch_vendor_peripheral_firmware(
    vendor_key: str,
    ctx: dict,
    *,
    html_cache: dict[str, str] | None = None,
) -> dict | None:
    vk = resolve_vendor_key(vendor_key)
    cfg = VENDOR_SITE_REGISTRY.get(vk)
    if not cfg:
        return None
    parsed = _fetch_from_site(ctx, cfg, html_cache)
    if parsed is None:
        return None
    return scrape_result_to_dict(parsed)


def peripheral_offer_from_row(row: dict, *, installed: str = "", device_label: str = "") -> dict:
    import driver_catalog as dc

    ver = (row.get("version") or "").strip()
    inst = (installed or "").strip()
    inst_src = (row.get("installed_source") or "").strip()
    long_title = (row.get("title") or "").strip()
    product = (row.get("product_name") or device_label or "").strip()
    display = product or long_title or "Peripheral firmware"
    vs = "n/a"
    comparable_inst = inst and inst not in ("", "—", "?", "0")
    if ver and comparable_inst:
        if inst_src in ("user_confirmed", "pnp_firmware_property", "vendor_app_cache"):
            vs = dc.compare_firmware_versions(inst, ver, title=long_title or display)
        elif inst_src in ("hid_driver", "driver_version"):
            vs = "uncertain"
        elif not inst.startswith("10.0."):
            vs = dc.compare_firmware_versions(inst, ver, title=long_title or display)
    elif ver:
        vs = "catalog_only"
    elif long_title or row.get("url"):
        vs = "uncertain"
    if ver and comparable_inst and vs == "n/a":
        vs = "catalog_only"

    return {
        "source": "peripheral_vendor",
        "source_label": "Vendor support site",
        "title": display,
        "display_title": display,
        "full_title": long_title or display,
        "version": ver,
        "url": row.get("url") or "",
        "download_url": row.get("download_url") or "",
        "notes": row.get("notes") or "",
        "vs_installed": vs,
        "coverage_check_failed": bool(row.get("coverage_check_failed")),
        "coverage_reason": row.get("coverage_reason") or "",
        "parse_method": row.get("parse_method") or "",
        "product_name": row.get("product_name") or "",
        "sku": row.get("sku") or "",
    }


# Backward-compatible alias used by scripts
PERIPHERAL_VENDOR_REGISTRY = VENDOR_SITE_REGISTRY


def audit_reference_profile(
    profile: PeripheralReferenceProfile,
    *,
    live: bool = False,
    html_cache: dict[str, str] | None = None,
) -> dict:
    cfg = VENDOR_SITE_REGISTRY.get(profile.vendor_key)
    if not cfg:
        return {"profile": profile, "status": "unsupported_vendor"}

    ctx = {
        "device_id": profile.device_id,
        "device_label": profile.label,
        "subcategory": profile.subcategory,
        "pnp_class": profile.pnp_class,
    }
    cache = html_cache if not live else None
    row = fetch_vendor_peripheral_firmware(profile.vendor_key, ctx, html_cache=cache)
    if not row:
        return {"profile": profile, "status": "no_config"}

    ver = (row.get("version") or "").strip()
    if row.get("coverage_check_failed"):
        status = row.get("coverage_reason") or "coverage_gap"
    elif ver:
        status = "version_found"
    else:
        status = "link_only"

    return {
        "profile": profile,
        "status": status,
        "vendor_row": row,
        "parse_method": row.get("parse_method") or "",
    }


# --- Legacy names kept for existing tests ---
parse_razer_firmware_article = parse_razer_article
search_razer_firmware_articles = lambda q, html=None: [
    (a, t) for a, t, _u in search_razer_articles(q, html)
]
fetch_razer_peripheral_firmware = lambda ctx, html_cache=None: _fetch_from_site(
    ctx, VENDOR_SITE_REGISTRY["razer"], html_cache
)
