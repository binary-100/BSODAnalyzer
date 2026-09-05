"""AMD vendor download-page scrape and offer fetch (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_scoring import compare_versions, parse_driver_version


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_AMD_DRIVERS_DOWNLOAD_URL = "https://www.amd.com/en/support/download/drivers.html"


def _amd_drivers_download_url() -> str:
    try:
        import vendor_endpoint_health as veh

        return veh.get_endpoint(
            "amd",
            "download_page",
            _AMD_DRIVERS_DOWNLOAD_URL,
        )
    except ImportError:
        return _AMD_DRIVERS_DOWNLOAD_URL


def _parse_amd_page_version(html: str) -> str:
    """AMD graphics page version — rules in ``BUNDLED_EXTRACTORS['amd']['graphics']``."""
    import vendor_extractors as vex

    return vex.extract_bundled_version("amd", html, hint="graphics")


def _ctx_implies_notebook(ctx: dict, system_ctx: dict | None = None) -> bool:
    """Notebook/desktop hint for GPU product-page disambiguation (P3)."""
    import gpu_vendor_maps as gvm

    label = _dc("_ctx_device_label")(ctx)
    if gvm.label_implies_notebook(label):
        return True
    platform = _dc("_catalog_system_ctx_from")(ctx, system_ctx)
    model_l = f"{platform.get('system_model') or ''} {platform.get('baseboard_product') or ''}".lower()
    return any(k in model_l for k in ("laptop", "notebook", "mobile", " ultrabook"))


def _amd_graphics_product_url(ctx: dict, system_ctx: dict | None = None) -> str | None:
    """Bundled AMD graphics leaf URL for this GPU (P1)."""
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp != "display" and ctx.get("hw_category") != "gpu":
        return None
    if ctx.get("hw_category") == "chipset" or _dc("_device_is_amd_chipset_plumbing")(ctx):
        return None
    import gpu_vendor_maps as gvm

    return gvm.amd_product_url_for_ctx(
        device_label=_dc("_ctx_device_label")(ctx),
        instance_id=(ctx.get("instance_id") or ""),
        notebook=_ctx_implies_notebook(ctx, system_ctx),
    )


def _amd_gpu_family_hint(ctx: dict) -> str:
    label = (ctx.get("device_label") or "")
    for pat in (
        r"\b(RX\s*\d{4}(?:\s*XTX|\s*XT|\s*GRE|\s*XL)?)\b",
        r"\b(Radeon\s*(?:Pro\s*)?\d{4}[A-Z]*)\b",
        r"\b(Vega\s*\d+)\b",
        r"\b(R[79]\s*\d{3})\b",
    ):
        m = re.search(pat, label, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _version_near_product_in_html(html: str, product_hint: str) -> str:
    if not product_hint or not html:
        return ""
    hint = product_hint.lower().replace(" ", "")
    compact = re.sub(r"\s+", "", html.lower())
    idx = compact.find(hint.replace(" ", ""))
    if idx < 0:
        idx = compact.find(product_hint.lower().split()[0])
    if idx < 0:
        return ""
    window = html[max(0, idx - 400): idx + 1200]
    found = re.findall(r"(\d+\.\d+\.\d+(?:\.\d+)?)", window)
    if not found:
        return ""
    return max(found, key=lambda v: parse_driver_version(v) or ())


def _amd_fetch_page_html(url: str) -> tuple[bool, str]:
    """Static GET (retry + bot-challenge rejection); JS render only as fallback."""
    ok, body = _dc("_amd_http_get_robust")(url)
    if ok and body:
        return True, body
    try:
        import vendor_page_render as vpr
    except ImportError:
        return ok, body
    ok2, rendered, _method = vpr.fetch_html_with_js_fallback(
        url, _dc("_amd_http_get_robust"), allow_js=True
    )
    return ok2, rendered


def _amd_unescape_html(html: str) -> str:
    import html as htmlmod

    return htmlmod.unescape(html or "")


def _amd_chipset_leaf_urls(html: str) -> list[str]:
    """Chipset product pages linked from the unified AMD download hub."""
    text = _amd_unescape_html(html)
    found = re.findall(
        r"https://www\.amd\.com/en/support/downloads/drivers\.html/chipsets/[a-z0-9/_.-]+\.html",
        text,
        re.I,
    )
    seen: set[str] = set()
    out: list[str] = []
    for url in found:
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    return out


def _amd_chipset_leaf_priority(url: str) -> tuple[int, str]:
    """Prefer newer socket/chipset pages when probing a small sample."""
    u = url.lower()
    socket_rank = 0
    for idx, socket in enumerate(("am5", "am4", "am3", "embedded"), start=1):
        if f"/chipsets/{socket}/" in u:
            socket_rank = idx
            break
    leaf = u.rsplit("/", 1)[-1].replace(".html", "")
    return socket_rank, leaf


def _amd_fetch_chipset_from_hub_leaves(ctx: dict) -> tuple[str, str] | None:
    """Parse chipset leaf links from the download hub, then probe a few product pages."""
    ok, html = _dc("_amd_http_get_robust")(_amd_drivers_download_url())
    if not ok or not html:
        ok, html = _amd_fetch_page_html(_amd_drivers_download_url())
    if not ok or not html:
        return None
    urls = _amd_chipset_leaf_urls(html)
    if not urls:
        return None
    urls.sort(key=_amd_chipset_leaf_priority, reverse=True)
    best = ""
    for url in urls[:4]:
        ok_leaf, leaf_html = _amd_fetch_page_html(url)
        if not ok_leaf or not leaf_html:
            continue
        hit = _dc("_amd_version_from_html")(leaf_html, ctx)
        if not hit:
            continue
        ver = (hit[0] or "").strip()
        if ver and (not best or compare_versions(best, ver) in ("newer", "unknown")):
            best = ver
    if best:
        return best, ""
    _dc("_record_vendor_empty_extraction")(
        "amd", "amd_chipset_hub_leaves: pages loaded but no version extracted"
    )
    return None


def _amd_version_from_html(html: str, ctx: dict, *, product_page_only: bool = False) -> tuple[str, str] | None:
    if not html:
        return None
    import vendor_extractors as vex

    if ctx.get("hw_category") == "chipset" or _dc("_device_is_amd_chipset_plumbing")(ctx):
        ver = vex.extract_bundled_version("amd", html, hint="chipset")
        return (ver, "") if ver else None
    family = _amd_gpu_family_hint(ctx)
    if family:
        fam_ver = _version_near_product_in_html(html, family)
        if fam_ver:
            return fam_ver, ""
    ver = _parse_amd_page_version(html)
    if ver:
        return ver, ""
    if product_page_only:
        return None
    return None


def _amd_fetch_from_product_leaf(ctx: dict) -> tuple[str, str] | None:
    """Fetch version from bundled AMD graphics product leaf (P1/P2)."""
    url = _dc("_amd_graphics_product_url")(ctx)
    if not url:
        return None
    ok, html = _amd_fetch_page_html(url)
    if not ok or not html:
        return None
    hit = _dc("_amd_version_from_html")(html, ctx, product_page_only=True)
    if hit is None:
        _dc("_record_vendor_empty_extraction")(
            "amd", f"amd_product_leaf: page loaded but no version extracted ({url})"
        )
    return hit


def _amd_fetch_from_download_page(ctx: dict) -> tuple[str, str] | None:
    """AMD unified download center (static HTTP, retried past Akamai challenges)."""
    ok, html = _dc("_amd_http_get_robust")(_amd_drivers_download_url())
    if not ok:
        return None
    hit = _dc("_amd_version_from_html")(html, ctx)
    if hit is None:
        _dc("_record_vendor_empty_extraction")(
            "amd", "amd_download_center: page loaded but no version extracted"
        )
    return hit


def _amd_fetch_download_page_rendered(ctx: dict) -> tuple[str, str] | None:
    """Download hub with JS fallback when the static page is a thin shell."""
    ok, html = _amd_fetch_page_html(_amd_drivers_download_url())
    if not ok:
        return None
    hit = _dc("_amd_version_from_html")(html, ctx)
    if hit is None:
        _dc("_record_vendor_empty_extraction")(
            "amd", "amd_download_js: page loaded but no version extracted"
        )
    return hit


def _scrape_amd_driver_version(ctx: dict) -> tuple[str, str]:
    is_gpu = (ctx.get("pnp_class") or "").lower() == "display" or ctx.get("hw_category") == "gpu"
    is_chipset = ctx.get("hw_category") == "chipset" or _dc("_device_is_amd_chipset_plumbing")(ctx)
    gpu_leaf = _dc("_amd_graphics_product_url")(ctx) if is_gpu and not is_chipset else None

    try:
        import vendor_fetch as vf
    except ImportError:
        if gpu_leaf:
            hit = _dc("_amd_fetch_from_product_leaf")(ctx)
            if hit:
                return hit
            return "", ""
        if is_gpu and not is_chipset:
            hit = _dc("_amd_fetch_from_product_leaf")(ctx)
            if hit:
                return hit
        hit = _dc("_amd_fetch_from_download_page")(ctx)
        if hit:
            return hit
        hit = _dc("_amd_fetch_download_page_rendered")(ctx)
        if hit:
            return hit
        if is_chipset:
            hit = _dc("_amd_fetch_chipset_from_hub_leaves")(ctx)
            if hit:
                return hit
        return "", ""

    steps: list[vf.FetchStep] = []
    if is_gpu and not is_chipset:
        steps.append(
            vf.FetchStep(
                "amd_product_leaf",
                lambda: _dc("_amd_fetch_from_product_leaf")(ctx),
            )
        )
        if not gpu_leaf:
            steps.extend([
                vf.FetchStep(
                    "amd_download_center",
                    lambda: _dc("_amd_fetch_from_download_page")(ctx),
                ),
                vf.FetchStep(
                    "amd_download_js",
                    lambda: _dc("_amd_fetch_download_page_rendered")(ctx),
                ),
            ])
    else:
        steps.extend([
            vf.FetchStep(
                "amd_download_center",
                lambda: _dc("_amd_fetch_from_download_page")(ctx),
            ),
            vf.FetchStep(
                "amd_download_js",
                lambda: _dc("_amd_fetch_download_page_rendered")(ctx),
            ),
        ])
    if is_chipset:
        steps.append(
            vf.FetchStep(
                "amd_chipset_hub_leaves",
                lambda: _dc("_amd_fetch_chipset_from_hub_leaves")(ctx),
            )
        )
    result = vf.run_steps(steps, vendor="amd")
    if result.value:
        return result.value
    return "", ""


def _amd_vendor_version_lookup_applicable(ctx: dict) -> bool:
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp == "display":
        return True
    if ctx.get("hw_category") == "chipset" or _dc("_device_is_amd_chipset_plumbing")(ctx):
        return True
    label = _dc("_ctx_device_label")(ctx)
    return any(k in label for k in ("radeon", "graphics", "rx ", "vega"))


def fetch_amd_driver_offers(ctx: dict) -> list[dict]:
    from catalog_mscatalog_session import is_quick_check_mode

    vk = (ctx.get("vendor_key") or "").lower()
    if vk != "amd":
        return []
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        "amd", _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp == "display" and _dc("_amd_vendor_version_lookup_applicable")(ctx):
        import gpu_vendor_maps as gvm

        if not gvm.amd_gpu_supported(_dc("_ctx_device_label")(ctx)):
            url, title = _dc("_VENDOR_DRIVER_URLS").get(
                "amd", ("https://www.amd.com/en/support/download/drivers.html", "AMD drivers")
            )
            return [
                _dc("_vendor_coverage_gap_offer")(
                    source_label="Manufacturer (AMD)",
                    vendor_disp="AMD",
                    title=f"{title} — below supported generation",
                    url=url,
                )
            ]
    url, title = _dc("_VENDOR_DRIVER_URLS").get(
        "amd", ("https://www.amd.com/en/support/download/drivers.html", "AMD drivers")
    )
    if ctx.get("hw_category") == "chipset":
        url = _amd_drivers_download_url()
        title = "AMD chipset drivers (download center)"
    elif pnp == "display":
        leaf_url = _dc("_amd_graphics_product_url")(ctx)
        if leaf_url:
            url = leaf_url
    cache_key = _dc("_amd_vendor_cache_key")(ctx)
    ver = ""
    if _dc("_amd_vendor_version_lookup_applicable")(ctx):
        if is_quick_check_mode():
            ver = ""
        else:
            cached = _dc("_vendor_scrape_cache_get")(cache_key)
            if cached is not None:
                ver = cached[0] if isinstance(cached, tuple) else str(cached)
            else:
                ver, _ = _dc("_scrape_amd_driver_version")(ctx)
                _dc("_vendor_scrape_cache_set")(cache_key, (ver, ""))
    if ctx.get("hw_category") == "chipset" and ver and not _dc("_looks_like_amd_chipset_package_version")(ver):
        hub_hit = _dc("_amd_fetch_chipset_from_hub_leaves")(ctx)
        ver = hub_hit[0] if hub_hit and hub_hit[0] else ""
    family = _amd_gpu_family_hint(ctx)
    notes = "Latest version from AMD release notes / driver pages; pick your exact product on AMD's site."
    if not _dc("_amd_vendor_version_lookup_applicable")(ctx):
        notes = (
            "Generic AMD support link for this device class — version is not compared "
            "automatically; open only if this device is AMD graphics or chipset."
        )
    elif family and ctx.get("hw_category") != "chipset":
        notes = (
            f"Release notes searched for {family}; confirm the package matches your exact GPU "
            "on AMD's driver portal before installing."
        )
    if _dc("_amd_vendor_version_lookup_applicable")(ctx) and not ver and not is_quick_check_mode():
        _dc("_record_vendor_empty_extraction")(
            "amd", "fetch_amd_driver_offers: version-applicable but no version scraped"
        )
        return [
            _dc("_vendor_coverage_gap_offer")(
                source_label="Manufacturer (AMD)",
                vendor_disp="AMD",
                title=title if not family else f"{title} ({family})",
                url=url,
            )
        ]
    offer = {
        "source": "vendor",
        "source_label": "Manufacturer (AMD)",
        "title": title if not family else f"{title} ({family})",
        "version": ver,
        "date": "",
        "url": url,
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": notes,
        "confidence": "medium" if ver else "low",
        "informational_only": not _dc("_amd_vendor_version_lookup_applicable")(ctx),
    }
    if ctx.get("hw_category") == "chipset" and ver:
        try:
            import catalog_amd_chipset_manifest as acm

            components = acm.fetch_amd_chipset_bundle_components(ver, ctx)
            if components:
                offer["bundle_components"] = components
        except Exception:  # noqa: BLE001 — manifest fetch is best-effort
            pass
    return [offer]
