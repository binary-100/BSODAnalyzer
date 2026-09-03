"""Network vendor fetch — Killer, Broadcom, Qualcomm, MediaTek (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_scoring import parse_driver_version
from catalog_tier_policy import _NETWORK_VENDOR_KEYS


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_INTEL_KILLER_PAGE = (
    "https://www.intel.com/content/www/us/en/download/19779/intel-killer-performance-suite.html"
)
_BROADCOM_NET_SEARCH = (
    "https://www.broadcom.com/support/download-search?pg=Ethernet+Controllers&pf=NetXtreme"
)
_MEDIATEK_PRODUCT_BASE = "https://www.mediatek.com/products/broadband-wifi"
_MEDIATEK_DEV_SLUG: dict[str, str] = {
    "7630": "mt7630",
    "7612": "mt7612",
    "7615": "mt7615",
    "7921": "mt7921",
    "7961": "mt7921",
    "7922": "mt7922",
    "7925": "mt7925",
    "7927": "mt7927",
    "0616": "mt7921",
}


def _network_vendor_cache_key(ctx: dict) -> str | None:
    vk = (ctx.get("vendor_key") or "").lower()
    if vk not in _NETWORK_VENDOR_KEYS:
        return None
    if vk == "killer":
        return "killer:suite"
    if vk == "broadcom":
        return "broadcom:netxtreme"
    if vk == "qualcomm":
        chip = _dc("_qualcomm_chip_hint")(ctx)
        return f"qualcomm:{chip or 'generic'}"
    if vk == "mediatek":
        slug = _dc("_mediatek_product_slug")(ctx)
        return f"mediatek:{slug or 'generic'}"
    return None


def _killer_component_version(html: str, device_label: str) -> str:
    """Extract Wi-Fi/Ethernet driver version from Killer suite release notes."""
    label = (device_label or "").lower()
    patterns: list[str] = []
    if "ethernet" in label or re.search(r"\be[0-9]{4}\b", label, re.I):
        patterns.append(
            r"([\d.]+)\s+(?:\([^)]*\)\s*,?\s*)*for Intel[^<\n]*Ethernet"
        )
    if any(k in label for k in ("wi-fi", "wifi", "wireless", " ax", " be")):
        patterns.append(
            r"([\d.]+)\s+(?:\([^)]*\)\s*,?\s*)*for Intel[^<\n]*Wi-Fi"
        )
    found: list[str] = []
    for pat in patterns:
        found.extend(re.findall(pat, html, re.I))
    if not found:
        return ""
    return max(found, key=lambda v: parse_driver_version(v) or ())


def fetch_killer_driver_offers(ctx: dict) -> list[dict]:
    """Intel Killer Performance Suite — unified Wi-Fi/Ethernet package."""
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "killer":
        return []
    cache_key = "killer:suite"
    cached = _dc("_vendor_scrape_cache_get")(cache_key)
    if cached and isinstance(cached, tuple) and len(cached) >= 3:
        best = cached[2]
        if isinstance(best, dict):
            return [dict(best)]
    ok, html = _dc("_vendor_http_get_robust")(
        _INTEL_KILLER_PAGE,
        referer="https://www.intel.com/content/www/us/en/download-center/home.html",
        insecure_fallback=True,
    )
    suite_ver, date_s, _installer = (
        _dc("_parse_intel_download_html")(html) if ok else ("", "", "")
    )
    comp_ver = _killer_component_version(html, ctx.get("device_label") or "") if ok else ""
    ver = comp_ver or suite_ver
    title = "Intel Killer Performance Suite"
    if comp_ver and suite_ver and comp_ver != suite_ver:
        title = f"Intel Killer driver ({comp_ver}) — suite {suite_ver}"
    notes = (
        "Unified Intel Killer Wi‑Fi/Ethernet package from Intel Download Center. "
        "Suite version covers multiple adapters; confirm yours in the release notes."
    )
    confidence = "medium" if ver else "low"
    if not ok:
        return [
            _dc("_vendor_coverage_gap_offer")(
                source_label="Manufacturer (Killer)",
                vendor_disp="Intel Killer",
                title=title,
                url=_INTEL_KILLER_PAGE,
            )
        ]
    offer = _dc("_vendor_offer_row")(
        vendor_key="killer",
        title=title,
        version=ver,
        date=date_s,
        url=_INTEL_KILLER_PAGE,
        notes=notes,
        confidence=confidence,
    )
    if ver:
        _dc("_vendor_scrape_cache_set")(cache_key, (ver, date_s, offer))
    return [offer]


def fetch_broadcom_driver_offers(ctx: dict) -> list[dict]:
    """Broadcom NetXtreme — vendor portal is SPA; provide targeted link + guidance."""
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "broadcom":
        return []
    label = (ctx.get("device_label") or "").lower()
    url = _BROADCOM_NET_SEARCH
    if "wireless" in label or "wifi" in label or "wi-fi" in label:
        url = _dc("_VENDOR_DRIVER_URLS").get("broadcom", (url,))[0]
    return [_dc("_vendor_offer_row")(
        vendor_key="broadcom",
        title="Broadcom NetXtreme / wireless — support downloads",
        url=url,
        notes=(
            "Broadcom does not expose a stable public driver API. "
            "Compare Microsoft Update Catalog hits first; use Broadcom or your PC maker "
            "for NetXtreme Ethernet WHQL packages."
        ),
        confidence="low",
    )]


def _qualcomm_chip_hint(ctx: dict) -> str:
    label = (ctx.get("device_label") or "").upper()
    inst = (ctx.get("instance_id") or "").upper()
    for src in (label, inst):
        m = re.search(r"\b(QCA[A-Z0-9]{3,6}|WCN[A-Z0-9]{3,6}|QCN[A-Z0-9]{3,6})\b", src)
        if m:
            return m.group(1)
        m = re.search(r"\b(AR[A-Z0-9]{3,5})\b", src)
        if m:
            return m.group(1)
    return ""


def fetch_qualcomm_driver_offers(ctx: dict) -> list[dict]:
    """Qualcomm / Atheros Wi‑Fi — OEM + Microsoft catalog path."""
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "qualcomm":
        return []
    chip = _qualcomm_chip_hint(ctx)
    url, title = _dc("_VENDOR_DRIVER_URLS").get(
        "qualcomm",
        ("https://www.qualcomm.com/support", "Qualcomm support"),
    )
    note = (
        "Qualcomm/Atheros Wi‑Fi drivers are usually shipped via PC maker or "
        "Microsoft Update Catalog (HWID search). Compare catalog results above first."
    )
    if chip:
        title = f"Qualcomm / Atheros {chip} — support"
        note = (
            f"Search Microsoft Update Catalog for '{chip}' or your adapter HWID. "
            "Qualcomm consumer Wi‑Fi drivers are rarely on qualcomm.com — use OEM or catalog."
        )
    return [_dc("_vendor_offer_row")(
        vendor_key="qualcomm",
        title=title,
        url=url,
        notes=note,
        confidence="low",
    )]


def _mediatek_product_slug(ctx: dict) -> str | None:
    inst = (ctx.get("instance_id") or "").upper()
    dev_m = re.search(r"DEV_([0-9A-F]{4})", inst)
    if dev_m:
        slug = _MEDIATEK_DEV_SLUG.get(dev_m.group(1))
        if slug:
            return slug
    label = (ctx.get("device_label") or "").lower()
    for token, slug in (
        ("7921", "mt7921"),
        ("7922", "mt7922"),
        ("7925", "mt7925"),
        ("7630", "mt7630"),
        ("7612", "mt7612"),
    ):
        if token in label:
            return slug
    return None


def _scrape_mediatek_product_rows(slug: str) -> list[dict]:
    from catalog_mscatalog_session import is_quick_check_mode

    if is_quick_check_mode():
        return []
    page = f"{_MEDIATEK_PRODUCT_BASE}/{slug}"
    ok, html = _dc("_vendor_http_get_robust")(page, insecure_fallback=True)
    if not ok:
        return []
    import vendor_extractors as vex

    return [
        {
            "title": (r.get("title") or "")[:120],
            "version": (r.get("version") or "").strip(),
            "date": r.get("date") or "",
            "url": r.get("url") or "",
        }
        for r in vex.extract_bundled_rows("mediatek", html or "")
        if (r.get("version") or "").strip()
    ]


def fetch_mediatek_driver_offers(ctx: dict) -> list[dict]:
    """MediaTek Wi‑Fi — scrape legacy product pages when a direct ZIP exists."""
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "mediatek":
        return []
    slug = _mediatek_product_slug(ctx)
    product_url = (
        f"{_MEDIATEK_PRODUCT_BASE}/{slug}" if slug
        else _dc("_VENDOR_DRIVER_URLS").get(
            "mediatek", ("https://www.mediatek.com/products/broadband-wifi", "")
        )[0]
    )
    rows = _dc("_scrape_mediatek_product_rows")(slug) if slug else []
    if rows:
        best = max(rows, key=lambda r: parse_driver_version(r.get("version") or "") or ())
        return [_dc("_vendor_offer_row")(
            vendor_key="mediatek",
            title=best.get("title") or f"MediaTek {slug} driver",
            version=best.get("version") or "",
            url=best.get("url") or product_url,
            notes=(
                f"Direct MediaTek.com download for {slug} (legacy/business partner package). "
                "Modern MT7921+ Wi‑Fi is usually via PC maker or Microsoft catalog."
            ),
            confidence="medium" if best.get("version") else "low",
        )]
    chip = slug or "Wi‑Fi"
    return [_dc("_vendor_offer_row")(
        vendor_key="mediatek",
        title=f"MediaTek {chip} — product / support",
        url=product_url,
        notes=(
            "MediaTek MT7921 and newer Wi‑Fi drivers are OEM-specific. "
            "Use Microsoft Update Catalog HWID results or your PC maker's support site."
        ),
        confidence="low",
    )]


def fetch_network_vendor_offers(ctx: dict) -> list[dict]:
    """Batch 3 network vendor scrapers (v6): Killer, Broadcom, Qualcomm, MediaTek."""
    if not _dc("_v6_catalog_enabled")():
        return []
    vk = (ctx.get("vendor_key") or "").lower()
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        vk, _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    dispatch = {
        "killer": lambda c: _dc("fetch_killer_driver_offers")(c),
        "broadcom": lambda c: _dc("fetch_broadcom_driver_offers")(c),
        "qualcomm": lambda c: _dc("fetch_qualcomm_driver_offers")(c),
        "mediatek": lambda c: _dc("fetch_mediatek_driver_offers")(c),
    }
    fn = dispatch.get(vk)
    if not fn:
        return []
    cache_key = _dc("_network_vendor_cache_key")(ctx)
    if cache_key:
        cached = _dc("_vendor_scrape_cache_get")(cache_key)
        if cached and isinstance(cached, tuple) and len(cached) >= 3:
            best = cached[2]
            if isinstance(best, dict) and (best.get("title") or best.get("url")):
                return [dict(best)]
    offers = fn(ctx)
    if cache_key and offers:
        best = offers[0]
        _dc("_vendor_scrape_cache_set")(
            cache_key,
            (best.get("version") or "", best.get("date") or "", best),
        )
    return offers
