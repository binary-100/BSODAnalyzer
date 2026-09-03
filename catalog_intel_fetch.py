"""Intel vendor download-page scrape and offer fetch (extracted from driver_catalog)."""

from __future__ import annotations

import re


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_INTEL_DOWNLOAD_REFERER = (
    "https://www.intel.com/content/www/us/en/download-center/home.html"
)

_INTEL_DSA_URL = (
    "https://www.intel.com/content/www/us/en/download/785597/"
    "intel-driver-and-support-assistant.html"
)


def _intel_attach_direct_download(
    page_url: str,
    html: str,
    installer_filename: str,
) -> tuple[str, bool]:
    """Resolve Intel product page to a direct installer when possible."""
    direct = ""
    try:
        import vendor_download_resolve as vdr

        direct = vdr.extract_intel_direct_download_url(
            html,
            page_url,
            installer_filename,
        )
        if not direct and page_url:
            ok, _, resolved = vdr.resolve_intel_download_url(page_url, html=html)
            if ok:
                direct = resolved
    except ImportError:
        pass
    return direct, bool(direct)


def _intel_scrape_result_parts(raw: tuple | list | None) -> tuple[str, str, str, str]:
    if not raw:
        return "", "", "", ""
    parts = list(raw)
    while len(parts) < 4:
        parts.append("")
    return parts[0], parts[1], parts[2], parts[3]


def _parse_intel_download_html(html: str, *, hint: str = "graphics") -> tuple[str, str, str]:
    """Parse Intel download detail HTML for (version, date, installer_filename).

    Version/date rules live in ``vendor_extractors.BUNDLED_EXTRACTORS['intel']``;
    installer filename stays here (not a version-shaped extraction).
    """
    import vendor_extractors as vex

    ver = vex.extract_bundled_version("intel", html, hint=hint)
    date_raw = vex.extract_bundled_date("intel", html, hint=hint)
    date_s = _dc("_realtek_normalize_date")(date_raw) if date_raw else ""
    installer = ""
    m = re.search(r"Download\s+([A-Za-z0-9_.-]+\.(?:exe|msi|zip))", html or "", re.I)
    if m:
        installer = m.group(1).strip()
    return ver, date_s, installer


def _intel_best_version_from_html(html: str, *, hint: str = "graphics") -> str:
    """Fallback when Intel product pages are client-rendered shells without Latest labels."""
    import vendor_extractors as vex

    return vex.extract_bundled_version("intel", html, hint=hint)


def _parse_intel_version_from_embedded_json(html: str, *, hint: str = "graphics") -> str:
    """Extract version from __NEXT_DATA__ / similar blobs (AMD-style Intel pages)."""
    import vendor_extractors as vex

    return vex.extract_bundled_version("intel", html, hint=hint)


def _intel_page_needs_js_render(html: str, *, hint: str = "graphics") -> bool:
    if not html:
        return False
    ver, _, _ = _parse_intel_download_html(html, hint=hint)
    if ver:
        return False
    try:
        import vendor_page_render as vpr
    except ImportError:
        return False
    return vpr.page_likely_needs_js_render(html)


def _fetch_intel_page_html(url: str, *, hint: str = "graphics") -> tuple[bool, str, str]:
    """HTTP GET with optional headless-browser fallback for JS-rendered Intel pages."""

    def _get(target: str) -> tuple[bool, str]:
        return _dc("_vendor_http_get_robust")(
            target,
            referer=_INTEL_DOWNLOAD_REFERER,
            insecure_fallback=True,
        )

    try:
        import vendor_page_render as vpr
    except ImportError:
        ok, html = _get(url)
        return ok, html, "http"
    return vpr.fetch_html_with_js_fallback(
        url,
        _get,
        needs_js=lambda body: _intel_page_needs_js_render(body, hint=hint),
    )


def _intel_product_url(hint: str, *, ctx: dict | None = None) -> str:
    if hint == "graphics" and ctx is not None:
        import gpu_vendor_maps as gvm

        bucket = gvm.intel_graphics_bucket_id(
            _dc("_ctx_device_label")(ctx),
            instance_id=(ctx.get("instance_id") or ""),
        )
        return gvm.intel_graphics_product_url(bucket)
    defaults = {
        "graphics": (
            "https://www.intel.com/content/www/us/en/download/19344/"
            "intel-graphics-windows-dch-drivers.html"
        ),
        "chipset": (
            "https://www.intel.com/content/www/us/en/download/19347/"
            "chipset-inf-utility.html"
        ),
        "wifi": (
            "https://www.intel.com/content/www/us/en/download/19351/"
            "intel-wireless-wi-fi-drivers.html"
        ),
    }
    key = {"graphics": "graphics_product", "chipset": "chipset_product", "wifi": "wifi_product"}.get(
        hint, "graphics_product"
    )
    default = defaults.get(hint, defaults["graphics"])
    try:
        import vendor_endpoint_health as veh

        return veh.get_endpoint("intel", key, default)
    except ImportError:
        return default


def _intel_dsa_url() -> str:
    default = (
        "https://www.intel.com/content/www/us/en/download/785597/"
        "intel-driver-and-support-assistant.html"
    )
    try:
        import vendor_endpoint_health as veh

        return veh.get_endpoint("intel", "dsa_fallback", default)
    except ImportError:
        return default


def _intel_fetch_product_page(hint: str, *, ctx: dict | None = None) -> tuple[str, str, str, str] | None:
    url = _dc("_intel_product_url")(hint, ctx=ctx)
    ok, html, _method = _dc("_fetch_intel_page_html")(url, hint=hint)
    if not ok:
        return None
    ver, date_s, installer = _dc("_parse_intel_download_html")(html, hint=hint)
    if not ver:
        ver = _dc("_intel_best_version_from_html")(html, hint=hint)
    if not ver:
        _dc("_record_vendor_empty_extraction")(
            "intel", f"intel_{hint}_product: page loaded but no version extracted"
        )
        return None
    direct, _verified = _intel_attach_direct_download(url, html, installer)
    return ver, date_s, url, direct


def _intel_fetch_dsa_graphics_page() -> tuple[str, str, str, str] | None:
    """DSA page still embeds recent 32.0.x.x graphics builds when product pages do not."""
    url = _intel_dsa_url()
    ok, html = _dc("_vendor_http_get_robust")(
        url,
        referer="https://www.intel.com/content/www/us/en/download-center/home.html",
        insecure_fallback=True,
    )
    if not ok:
        return None
    ver = _intel_best_version_from_html(html, hint="graphics")
    if ver:
        return ver, "", url, ""
    _dc("_record_vendor_empty_extraction")(
        "intel", "intel_dsa_graphics: page loaded but no version extracted"
    )
    return None


def _intel_fetch_dsa_chipset_page() -> tuple[str, str, str, str] | None:
    """DSA page often lists chipset INF builds when the chipset product page is a JS shell."""
    url = _intel_dsa_url()
    ok, html = _dc("_http_get")(
        url,
        headers={"Accept": "text/html,application/xhtml+xml"},
        referer="https://www.intel.com/content/www/us/en/download-center/home.html",
        insecure_fallback=True,
    )
    if not ok:
        return None
    ver = _intel_best_version_from_html(html, hint="chipset")
    if ver:
        return ver, "", url, ""
    _dc("_record_vendor_empty_extraction")(
        "intel", "intel_dsa_chipset: page loaded but no version extracted"
    )
    return None


def _scrape_intel_download_page(url: str, *, hint: str = "graphics") -> tuple[str, str, str, str]:
    ok, html, _method = _dc("_fetch_intel_page_html")(url, hint=hint)
    if not ok:
        return "", "", url, ""
    ver, date_s, installer = _dc("_parse_intel_download_html")(html, hint=hint)
    direct, _verified = _intel_attach_direct_download(url, html, installer)
    return ver, date_s, url, direct


def _scrape_intel_driver_version(
    product_hint: str = "graphics",
    *,
    ctx: dict | None = None,
) -> tuple[str, str, str, str]:
    """Scrape Intel download pages — product page, then DSA fallback for graphics."""
    hint = product_hint or "graphics"
    fallback_url = _dc("_intel_product_url")(
        hint if hint in ("graphics", "chipset", "wifi") else "graphics",
        ctx=ctx,
    )

    try:
        import vendor_fetch as vf
    except ImportError:
        hit = _dc("_intel_fetch_product_page")(hint, ctx=ctx)
        if hit:
            return hit
        if hint == "graphics":
            hit = _dc("_intel_fetch_dsa_graphics_page")()
            if hit:
                return hit
        if hint == "chipset":
            hit = _dc("_intel_fetch_dsa_chipset_page")()
            if hit:
                return hit
        return "", "", fallback_url, ""

    steps: list[vf.FetchStep] = [
        vf.FetchStep(
            f"intel_{hint}_product",
            lambda h=hint, c=ctx: _dc("_intel_fetch_product_page")(h, ctx=c),
        ),
    ]
    if hint == "graphics":
        steps.append(
            vf.FetchStep("intel_dsa_graphics", lambda: _dc("_intel_fetch_dsa_graphics_page")())
        )
    if hint == "chipset":
        steps.append(
            vf.FetchStep("intel_dsa_chipset", lambda: _dc("_intel_fetch_dsa_chipset_page")())
        )
    result = vf.run_steps(steps, vendor="intel")
    if result.value:
        return _dc("_intel_scrape_result_parts")(result.value)
    return "", "", fallback_url, ""


def _intel_dsa_utility_offer(ctx: dict, *, scraped_version: str = "") -> dict:
    note = (
        "Intel Driver & Support Assistant auto-detects Intel hardware and suggests "
        "matching drivers. Use when catalog scrape has no version or for multi-Intel systems."
    )
    if not scraped_version:
        note = (
            "No version from Intel download pages — DSA is the recommended auto-detect path "
            "for this Intel device."
        )
    return {
        "source": "utility",
        "source_label": "Intel DSA",
        "title": "Intel Driver & Support Assistant (auto-detect)",
        "version": "",
        "date": "",
        "url": _INTEL_DSA_URL,
        "download_kind": "url",
        "update_id": "",
        "instance_id": ctx.get("instance_id") or "",
        "notes": note,
        "confidence": "medium",
    }


def fetch_intel_driver_offers(ctx: dict) -> list[dict]:
    vk = (ctx.get("vendor_key") or "").lower()
    if vk != "intel":
        return []
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        "intel", _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    hint = _dc("_intel_driver_hint_from_ctx")(ctx)
    if not hint:
        return []
    if hint == "graphics":
        import gpu_vendor_maps as gvm

        if not gvm.intel_igpu_supported(_dc("_ctx_device_label")(ctx)):
            url = _intel_product_url("graphics", ctx=ctx)
            return [
                _dc("_vendor_coverage_gap_offer")(
                    source_label="Manufacturer (Intel)",
                    vendor_disp="Intel",
                    title="Intel graphics — below supported generation",
                    url=url,
                )
            ]
        bucket = gvm.intel_graphics_bucket_id(
            _dc("_ctx_device_label")(ctx),
            instance_id=(ctx.get("instance_id") or ""),
        )
        cache_key = gvm.intel_graphics_cache_key(bucket)
    else:
        bucket = ""
        cache_key = f"intel:{hint}"
    cached = _dc("_vendor_scrape_cache_get")(cache_key)
    if cached:
        ver, date, page_url, direct_url = _dc("_intel_scrape_result_parts")(cached)
    else:
        ver, date, page_url, direct_url = _dc("_scrape_intel_driver_version")(hint, ctx=ctx)
        _dc("_vendor_scrape_cache_set")(cache_key, (ver, date, page_url, direct_url))
    title_map = {
        "graphics": "Intel Graphics (DCH) — latest WHQL",
        "chipset": "Intel Chipset INF utility",
        "wifi": "Intel Wi-Fi drivers",
    }
    if hint == "graphics" and bucket:
        import gpu_vendor_maps as gvm

        title_map["graphics"] = gvm.intel_graphics_bucket_title(bucket)
        installed = (ctx.get("primary_version") or "").strip()
        generation_mismatch = False
        if ver and not gvm.intel_graphics_version_applicable(
            device_label=_dc("_ctx_device_label")(ctx),
            bucket_id=bucket,
            installed_version=installed,
            scraped_version=ver,
        ):
            generation_mismatch = True
            ver = ""
    else:
        generation_mismatch = False
    offer_url = direct_url or page_url
    install_verified = bool(direct_url)
    notes = (
        "Version from Intel download page with verified installer link."
        if ver and install_verified
        else "Version from Intel download page; confirm product on Intel's site before installing."
    )
    if ver and not install_verified:
        notes = (
            "Intel lists a newer build but the direct installer was not resolved — "
            "prefer a Microsoft Update Catalog row or Intel DSA if Install fails."
        )
    offers = [{
        "source": "vendor",
        "source_label": "Manufacturer (Intel)",
        "title": title_map.get(hint, "Intel drivers"),
        "version": ver,
        "date": date,
        "url": offer_url,
        "vendor_page_url": page_url if direct_url else "",
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": notes,
        "confidence": "high" if ver and install_verified else ("medium" if ver else "low"),
        "download_resolvable": install_verified,
        "install_verified": install_verified,
    }]
    if generation_mismatch:
        offers[0]["generation_mismatch"] = True
        offers[0]["notes"] = (
            "Intel page version does not match this GPU generation — "
            "open Intel's site or Microsoft catalog to confirm."
        )
    if not ver and hint in ("graphics", "chipset") and not generation_mismatch:
        _dc("_record_vendor_empty_extraction")(
            "intel",
            f"fetch_intel_driver_offers({hint}): version-applicable but no version scraped",
        )
        offers.append(
            _dc("_vendor_coverage_gap_offer")(
                source_label="Manufacturer (Intel)",
                vendor_disp="Intel",
                title=title_map.get(hint, "Intel drivers"),
                url=page_url or _dc("_intel_product_url")(hint),
            )
        )
    if _dc("_v6_catalog_enabled")():
        offers.append(_dc("_intel_dsa_utility_offer")(ctx, scraped_version=ver))
    return offers
