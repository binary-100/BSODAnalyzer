"""SSD firmware vendor registry — scrape configs + reference profiles for testing.

Each vendor entry defines how to locate model-specific firmware on the vendor site.
Reference profiles exercise parsers for drives that may not be installed on the
machine running tests (retail SKUs, common OEM parts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

_SSD_MODEL_GENERIC_TOKENS = frozenset({
    "samsung", "western", "digital", "solid", "state", "disk", "drive", "nvme",
    "pci", "express", "series", "brand", "ssd", "intel", "micron", "crucial",
    "kingston", "sandisk", "wd", "wdc", "tb", "gb", "kingston",
})


def _distinctive_tokens(model: str) -> list[str]:
    tokens = [t for t in re.split(r"[^a-z0-9]+", (model or "").lower()) if len(t) >= 3]
    distinctive = [t for t in tokens if t not in _SSD_MODEL_GENERIC_TOKENS]
    strong = [t for t in distinctive if len(t) >= 4]
    if strong:
        return strong[:6]
    return distinctive[:4]


def _model_anchor_pattern(model: str) -> str:
    """Regex fragment matching the model line (e.g. 990\\s*PRO)."""
    tokens = _distinctive_tokens(model)
    if not tokens:
        parts = [t for t in re.split(r"[^a-z0-9]+", (model or "").lower()) if len(t) >= 3]
        tokens = [t for t in parts if t not in ("ssd", "nvme", "series")][:4]
    if not tokens:
        return re.escape((model or "")[:12])
    return r"\s*".join(re.escape(t) for t in tokens[:4])


# Samsung retail firmware: 8B2QJXD7, 2B2QKXG7, etc.
_SAMSUNG_FW_REV = re.compile(r"\b([0-9][A-Z0-9]{6,10})\b", re.I)
_SAMSUNG_ISO_REV = re.compile(r"([0-9][A-Z0-9]{6,10})\.iso", re.I)

# WD / SanDisk often use dotted quads in download tables
_WD_FW_REV = re.compile(r"\b(\d+\.\d+(?:\.\d+){1,3})\b")

# Crucial / Micron-style alphanumeric packages
_CRUCIAL_FW_REV = re.compile(r"\b([A-Z0-9]{3,4}[A-Z0-9]{2,8})\b", re.I)


@dataclass(frozen=True)
class SsdReferenceProfile:
    """Known drive used to validate vendor parsing without local hardware."""

    vendor_key: str
    model: str
    example_installed: str
    notes: str = ""


@dataclass
class SsdVendorScrapeResult:
    title: str
    version: str
    url: str
    notes: str
    coverage_check_failed: bool = False
    coverage_reason: str = ""
    parse_method: str = ""


@dataclass(frozen=True)
class SsdVendorConfig:
    vendor_key: str
    display_name: str
    primary_url: str
    utility_label: str
    parse: Callable[[str, str], SsdVendorScrapeResult | None]
    alternate_urls: tuple[str, ...] = ()


def _samsung_series_heading(model: str) -> str:
    m = (model or "").lower()
    if "990 pro" in m or ("990" in m and "pro" in m):
        return "NVMe SSD-990 PRO Series Firmware"
    if "990 evo" in m:
        return "NVMe SSD-990 EVO"
    if "980 pro" in m:
        return "980 PRO"
    if "970 evo" in m:
        return "NVMe SSD-970 EVO Plus Series Firmware"
    if "970 pro" in m:
        return "970 PRO"
    if "870 evo" in m or "870 qvo" in m:
        return "870"
    if "860 evo" in m or "860 pro" in m:
        return "860"
    return ""


def _parse_samsung_tools(html: str, model: str) -> SsdVendorScrapeResult | None:
    url = "https://semiconductor.samsung.com/consumer-storage/support/tools/"
    base = SsdVendorScrapeResult(
        title=f"Samsung SSD — {model[:60]}",
        version="",
        url=url,
        notes="Use Samsung Magician to compare and update firmware.",
        coverage_check_failed=True,
        coverage_reason="fetch_failed",
    )
    if not html:
        return base

    low = html.lower()
    heading = _samsung_series_heading(model)
    chunk = ""
    parse_method = ""

    if heading and heading.lower() in low:
        m = re.search(re.escape(heading) + r"(.{0,6000})", html, re.I | re.S)
        if m:
            chunk = m.group(1)
            parse_method = "samsung_series_heading"
    if not chunk:
        anchor = _model_anchor_pattern(model)
        m = re.search(rf"({anchor}).{{0,5000}}", html, re.I | re.S)
        if m:
            chunk = m.group(0)
            parse_method = "samsung_model_anchor"

    if not chunk:
        tokens = _distinctive_tokens(model)
        if tokens and any(t in low for t in tokens):
            base.coverage_reason = "model_not_on_page"
            base.notes = (
                "Samsung tools page loaded but this exact model series was not found — "
                "confirm in Magician or pick the closest series on the support page."
            )
        else:
            base.coverage_reason = "model_not_on_page"
        return base

    iso_revs = _SAMSUNG_ISO_REV.findall(chunk)
    if not iso_revs:
        iso_revs = _SAMSUNG_FW_REV.findall(chunk)
    # De-dupe preserving order (first = primary download on page)
    seen: set[str] = set()
    ordered: list[str] = []
    for r in iso_revs:
        up = r.upper()
        if up in seen:
            continue
        seen.add(up)
        ordered.append(up)

    if not ordered:
        return SsdVendorScrapeResult(
            title=f"Samsung SSD — {model[:60]}",
            version="",
            url=url,
            notes="Found the model section on Samsung's page but no firmware revision string.",
            coverage_check_failed=True,
            coverage_reason="parse_failed",
            parse_method=parse_method,
        )

    latest = ordered[0]
    return SsdVendorScrapeResult(
        title=f"Samsung firmware ({model[:60]})",
        version=latest,
        url=url,
        notes=(
            f"Latest firmware listed on Samsung support tools for this series ({latest}). "
            "Confirm in Magician before flashing."
        ),
        coverage_check_failed=False,
        parse_method=parse_method,
    )


def _parse_wd_downloads(html: str, model: str) -> SsdVendorScrapeResult | None:
    url = "https://support-en.wdc.com/downloads.aspx?lang=en"
    base = SsdVendorScrapeResult(
        title=f"WD / SanDisk SSD — {model[:60]}",
        version="",
        url=url,
        notes="Use WD Dashboard to check firmware for this drive.",
        coverage_check_failed=True,
        coverage_reason="fetch_failed",
    )
    if not html:
        return base

    anchor = _model_anchor_pattern(model)
    tokens = _distinctive_tokens(model)
    m = re.search(rf"({anchor}).{{0,4000}}", html, re.I | re.S)
    chunk = m.group(0) if m else ""
    if not chunk and tokens:
        for tok in tokens:
            if tok in html.lower():
                idx = html.lower().find(tok)
                chunk = html[max(0, idx - 200): idx + 4000]
                break
    if not chunk:
        base.coverage_reason = "model_not_on_page"
        return base

    candidates: list[str] = []
    for ver_m in _WD_FW_REV.finditer(chunk):
        ver = ver_m.group(1)
        ctx = chunk[max(0, ver_m.start() - 120): ver_m.end() + 120].lower()
        if any(t in ctx for t in tokens) or re.search(anchor, ctx, re.I):
            candidates.append(ver)
    if not candidates:
        return SsdVendorScrapeResult(
            title=f"WD firmware ({model[:60]})",
            version="",
            url=url,
            notes="WD support page matched the model but no firmware version was parsed.",
            coverage_check_failed=True,
            coverage_reason="parse_failed",
        )

    latest = max(candidates, key=lambda v: tuple(int(x) for x in re.findall(r"\d+", v) or [0]))
    return SsdVendorScrapeResult(
        title=f"WD firmware ({model[:60]})",
        version=latest,
        url=url,
        notes="Parsed from WD support downloads — confirm in WD Dashboard.",
        coverage_check_failed=False,
        parse_method="wd_downloads_anchor",
    )


def _parse_crucial_firmware(html: str, model: str) -> SsdVendorScrapeResult | None:
    url = "https://www.crucial.com/support/ssd-firmware"
    base = SsdVendorScrapeResult(
        title=f"Crucial SSD — {model[:60]}",
        version="",
        url=url,
        notes="Use Crucial Storage Executive for firmware updates.",
        coverage_check_failed=True,
        coverage_reason="fetch_failed",
    )
    if not html:
        return base

    anchor = _model_anchor_pattern(model)
    m = re.search(rf"({anchor}).{{0,3000}}", html, re.I | re.S)
    chunk = m.group(0) if m else ""
    if not chunk:
        tokens = _distinctive_tokens(model)
        if not tokens or not any(t in html.lower() for t in tokens):
            base.coverage_reason = "model_not_on_page"
            return base
        idx = html.lower().find(tokens[0])
        chunk = html[max(0, idx - 100): idx + 3000]

    for ver_m in _CRUCIAL_FW_REV.finditer(chunk):
        ver = ver_m.group(1).upper()
        if len(ver) >= 4 and not ver.isdigit():
            return SsdVendorScrapeResult(
                title=f"Crucial firmware ({model[:60]})",
                version=ver,
                url=url,
                notes="Parsed from Crucial firmware page — confirm in Storage Executive.",
                coverage_check_failed=False,
                parse_method="crucial_anchor",
            )

    return SsdVendorScrapeResult(
        title=f"Crucial SSD — {model[:60]}",
        version="",
        url=url,
        notes="Crucial page matched but firmware revision was not parsed.",
        coverage_check_failed=True,
        coverage_reason="parse_failed",
    )


def _utility_only(
    vendor_key: str,
    label: str,
    url: str,
    model: str,
) -> SsdVendorScrapeResult:
    return SsdVendorScrapeResult(
        title=f"{label} — {model[:60]}",
        version="",
        url=url,
        notes=f"Use {label} to compare installed firmware with the latest release.",
        coverage_check_failed=True,
        coverage_reason="utility_only",
    )



def _is_seagate_hybrid_model(model: str, storage_class: str = "") -> bool:
    if (storage_class or "").strip() == "hybrid_hdd":
        return True
    m = (model or "").lower()
    return any(tok in m for tok in ("lx00", "lm01", "lm02", "lm00", "sshd", "firecuda"))


def _parse_seagate_hybrid(
    html: str,
    model: str,
    *,
    serial: str = "",
    storage_class: str = "",
) -> SsdVendorScrapeResult:
    support_url = "https://www.seagate.com/support/downloads/"
    finder_url = "https://apps1.seagate.com/downloads/request.html"
    base = SsdVendorScrapeResult(
        title=f"Seagate hybrid — {model[:60]}",
        version="",
        url=finder_url,
        notes="Seagate hybrid drives require serial-number lookup on the Download Finder.",
        coverage_check_failed=True,
        coverage_reason="serial_required",
    )
    try:
        import vendor_firmware_fetch as vff

        support_url = vff.seagate_support_url_for_model(model)
        finder_url = vff.SEAGATE_DOWNLOAD_FINDER
    except ImportError:
        vff = None

    serial = (serial or "").strip()
    page_html = html or ""

    if not page_html and serial and vff is not None:
        ok, page_html, status = vff.fetch_seagate_firmware_lookup(serial, model)
        if status == "no_update":
            return SsdVendorScrapeResult(
                title=f"Seagate hybrid — {model[:60]}",
                version="",
                url=finder_url,
                notes=(
                    "Seagate Download Finder reports this drive already has the latest firmware "
                    f"for serial …{serial[-4:]}."
                ),
                coverage_check_failed=False,
                parse_method="seagate_download_finder",
            )
        if not ok and status in ("blocked", "error", "invalid_serial"):
            reason = "fetch_failed" if status in ("blocked", "error") else "serial_required"
            base.coverage_reason = reason
            base.url = finder_url
            base.notes = (
                "Could not verify Seagate firmware automatically — use Download Finder with "
                f"serial …{serial[-4:]} and model {model.split()[0]}."
            )
            return base

    if page_html and vff is not None:
        parsed = vff.parse_seagate_download_finder_html(page_html, model)
        ver = (parsed.get("version") or "").strip()
        dl_url = (parsed.get("url") or "").strip() or finder_url
        if ver:
            return SsdVendorScrapeResult(
                title=f"Seagate firmware ({model[:60]})",
                version=ver,
                url=dl_url,
                notes=(
                    "Parsed from Seagate Download Finder — back up data before flashing hybrid firmware."
                ),
                coverage_check_failed=False,
                parse_method="seagate_download_finder",
            )

    if not serial:
        base.url = finder_url
        base.notes = (
            "Seagate requires the drive serial number for firmware lookup. "
            "Open Download Finder and enter serial + model."
        )
        return base

    base.url = finder_url
    base.notes = (
        "Download Finder did not return a parseable firmware version — "
        f"confirm manually with serial …{serial[-4:]}."
    )
    base.coverage_reason = "parse_failed"
    return base


def _parse_seagate_firmware(
    html: str,
    model: str,
    *,
    serial: str = "",
    storage_class: str = "",
) -> SsdVendorScrapeResult:
    if _is_seagate_hybrid_model(model, storage_class):
        return _parse_seagate_hybrid(html, model, serial=serial, storage_class=storage_class)
    return _utility_only(
        "seagate",
        "Seagate support",
        "https://www.seagate.com/support/downloads/",
        model,
    )


def _parse_utility_stub(_html: str, model: str, *, vk: str, label: str, url: str) -> SsdVendorScrapeResult:
    return _utility_only(vk, label, url, model)


SSD_VENDOR_REGISTRY: dict[str, SsdVendorConfig] = {
    "samsung": SsdVendorConfig(
        "samsung",
        "Samsung",
        "https://semiconductor.samsung.com/consumer-storage/support/tools/",
        "Samsung Magician",
        _parse_samsung_tools,
    ),
    "wd": SsdVendorConfig(
        "wd",
        "Western Digital",
        "https://support-en.wdc.com/downloads.aspx?lang=en",
        "WD Dashboard",
        _parse_wd_downloads,
    ),
    "sandisk": SsdVendorConfig(
        "sandisk",
        "SanDisk",
        "https://support-en.wdc.com/downloads.aspx?lang=en",
        "SanDisk Dashboard",
        _parse_wd_downloads,
    ),
    "crucial": SsdVendorConfig(
        "crucial",
        "Crucial",
        "https://www.crucial.com/support/ssd-firmware",
        "Crucial Storage Executive",
        _parse_crucial_firmware,
    ),
    "intel": SsdVendorConfig(
        "intel",
        "Intel",
        "https://www.intel.com/content/www/us/en/support/articles/000005910/memory-and-storage.html",
        "Intel SSD tools",
        lambda h, m: _parse_utility_stub(
            h, m, vk="intel", label="Intel SSD tools", url=
            "https://www.intel.com/content/www/us/en/support/articles/000005910/memory-and-storage.html"
        ),
    ),
    "kingston": SsdVendorConfig(
        "kingston",
        "Kingston",
        "https://www.kingston.com/en/support/technical/ssdmanager",
        "Kingston SSD Manager",
        lambda h, m: _parse_utility_stub(
            h, m, vk="kingston", label="Kingston SSD Manager",
            url="https://www.kingston.com/en/support/technical/ssdmanager",
        ),
    ),
    "skhynix": SsdVendorConfig(
        "skhynix",
        "SK hynix",
        "https://www.skhynix.com/ssd/",
        "SK hynix SSD support",
        lambda h, m: _parse_utility_stub(h, m, vk="skhynix", label="SK hynix SSD support", url="https://www.skhynix.com/ssd/"),
    ),
    "kioxia": SsdVendorConfig(
        "kioxia",
        "Kioxia",
        "https://storage.kioxia.com/ssd/support",
        "Kioxia SSD support",
        lambda h, m: _parse_utility_stub(h, m, vk="kioxia", label="Kioxia SSD support", url="https://storage.kioxia.com/ssd/support"),
    ),
    "toshiba": SsdVendorConfig(
        "toshiba",
        "Toshiba/Kioxia",
        "https://storage.kioxia.com/ssd/support",
        "Kioxia SSD support",
        lambda h, m: _parse_utility_stub(h, m, vk="toshiba", label="Kioxia SSD support", url="https://storage.kioxia.com/ssd/support"),
    ),
    "seagate": SsdVendorConfig(
        "seagate",
        "Seagate",
        "https://apps1.seagate.com/downloads/request.html",
        "Seagate Download Finder",
        lambda h, m: _parse_seagate_firmware(h, m),
    ),
    "adata": SsdVendorConfig(
        "adata",
        "ADATA",
        "https://www.adata.com/us/support/downloads",
        "ADATA SSD Toolbox",
        lambda h, m: _parse_utility_stub(h, m, vk="adata", label="ADATA SSD Toolbox", url="https://www.adata.com/us/support/downloads"),
    ),
    "micron": SsdVendorConfig(
        "micron",
        "Micron",
        "https://www.crucial.com/support/ssd-firmware",
        "Crucial Storage Executive",
        _parse_crucial_firmware,
    ),
    "corsair": SsdVendorConfig(
        "corsair",
        "Corsair",
        "https://www.corsair.com/downloads",
        "Corsair SSD utility",
        lambda h, m: _parse_utility_stub(h, m, vk="corsair", label="Corsair downloads", url="https://www.corsair.com/downloads"),
    ),
    "phison": SsdVendorConfig(
        "phison",
        "Phison",
        "",
        "OEM / drive maker utility",
        lambda h, m: SsdVendorScrapeResult(
            title=f"Phison-based SSD — {m[:60]}",
            version="",
            url="",
            notes="Phison controllers are updated via the SSD brand's toolbox (Samsung, WD, Corsair, etc.).",
            coverage_check_failed=True,
            coverage_reason="utility_only",
        ),
    ),
    "siliconpower": SsdVendorConfig(
        "siliconpower",
        "Silicon Power",
        "https://www.silicon-power.com/download/",
        "Silicon Power utility",
        lambda h, m: _parse_utility_stub(h, m, vk="siliconpower", label="Silicon Power downloads", url="https://www.silicon-power.com/download/"),
    ),
    "teamgroup": SsdVendorConfig(
        "teamgroup",
        "TeamGroup",
        "https://www.teamgroupinc.com/en/support/download/",
        "TeamGroup support",
        lambda h, m: _parse_utility_stub(h, m, vk="teamgroup", label="TeamGroup support", url="https://www.teamgroupinc.com/en/support/download/"),
    ),
}


# Reference drives for audit/tests — not tied to installed hardware.
SSD_REFERENCE_PROFILES: tuple[SsdReferenceProfile, ...] = (
    SsdReferenceProfile("samsung", "Samsung SSD 990 PRO 4TB", "8B2QJXD7", "User machine — retail NVMe"),
    SsdReferenceProfile("samsung", "Samsung SSD 990 PRO 2TB", "8B2QJXD7", "Same series as 4TB"),
    SsdReferenceProfile("samsung", "Samsung SSD 970 EVO Plus 1TB", "2B2QEXM7", "Common retail SATA/NVMe"),
    SsdReferenceProfile("samsung", "Samsung SSD 980 PRO 1TB", "5B2QGXA7", "Prior-gen PRO"),
    SsdReferenceProfile("wd", "WD_BLACK SN850X 2TB", "620361WD", "Retail WD NVMe"),
    SsdReferenceProfile("wd", "WDC WDS100T2B0C-00PXH0", "211070WD", "OEM WD Blue SN550 class"),
    SsdReferenceProfile("sandisk", "SanDisk Extreme Portable SSD", "", "Portable — often utility-only"),
    SsdReferenceProfile("crucial", "Crucial MX500 1TB", "M3CR010", "Common SATA"),
    SsdReferenceProfile("crucial", "Crucial P5 Plus 1TB", "P7CR403", "NVMe"),
    SsdReferenceProfile("intel", "INTEL SSDPEKNW512G8", "002C", "Legacy Intel NVMe — utility path"),
    SsdReferenceProfile("kingston", "KINGSTON SNV2S1000G", "SBFK61W1", "NV2 retail"),
    SsdReferenceProfile("skhynix", "SK hynix BC901 HFS512GEJ9X125N", "41062C20", "Common OEM laptop NVMe"),
    SsdReferenceProfile("kioxia", "KIOXIA-EXceria SSD 1TB", "ELFA01.0", "Retail Kioxia"),
    SsdReferenceProfile("seagate", "Seagate BarraCuda Q5 SSD 1TB", "SUFA01.0", "Seagate consumer SSD"),
    SsdReferenceProfile(
        "seagate",
        "ST2000LX001-1RG174",
        "CC43",
        "FireCuda 2TB SSHD — GL702VM class hybrid",
    ),
    SsdReferenceProfile("adata", "ADATA LEGEND 850 1TB", "SN13536", "Retail ADATA"),
    SsdReferenceProfile("micron", "Micron 2450 MTFDKBA512TFK", "E2MU200", "OEM Micron NVMe"),
    SsdReferenceProfile("corsair", "Corsair MP600 PRO XT 2TB", "5.0.0", "Phison-based — utility"),
)


def scrape_result_to_dict(result: SsdVendorScrapeResult) -> dict:
    return {
        "title": result.title,
        "version": result.version,
        "url": result.url,
        "notes": result.notes,
        "coverage_check_failed": result.coverage_check_failed,
        "coverage_reason": result.coverage_reason,
        "parse_method": result.parse_method,
    }


def coverage_gap_message(reason: str, vendor_disp: str) -> str:
    name = vendor_disp or "vendor"
    messages = {
        "fetch_failed": (
            f"Could not load the {name} support page (network or access blocked). "
            "Open the link manually to check firmware."
        ),
        "model_not_on_page": (
            f"The {name} support page loaded but this exact model/series was not found. "
            "Pick the closest product on the site or use the vendor desktop tool."
        ),
        "parse_failed": (
            f"The {name} page matched this drive but the tool could not read a firmware version "
            "from the page layout — open the link and compare manually."
        ),
        "compare_unknown": (
            f"A version was read from {name} but it could not be compared to the installed "
            "firmware string — confirm on the vendor page or in their desktop tool."
        ),
        "utility_only": (
            f"{name} does not expose a reliable public firmware version on the web — "
            "use the vendor desktop utility to compare and update."
        ),
        "serial_required": (
            f"{name} requires your drive serial number on the Download Finder — "
            "automatic lookup cannot run without it."
        ),
    }
    return messages.get(reason, messages["parse_failed"])


def fetch_vendor_ssd_firmware(
    vendor_key: str,
    model: str,
    *,
    html: str | None = None,
    serial_number: str = "",
    storage_class: str = "",
    html_cache: dict[str, str] | None = None,
) -> dict | None:
    """Scrape or stub the vendor SSD firmware row for ``vendor_key`` + ``model``."""
    vk = (vendor_key or "").strip().lower()
    cfg = SSD_VENDOR_REGISTRY.get(vk)
    if not cfg:
        return None

    page_html = html
    if page_html is None and html_cache:
        page_html = (
            html_cache.get(vk)
            or html_cache.get(cfg.primary_url)
            or html_cache.get(f"ssd_page:{cfg.primary_url}")
        )
    if page_html is None and vk != "seagate":
        import firmware_catalog as fwcat

        ok, page_html = fwcat._fetch_vendor_page_html(cfg.primary_url)
        if not ok:
            page_html = ""

    if vk == "seagate":
        parsed = _parse_seagate_firmware(
            page_html or "",
            model,
            serial=serial_number,
            storage_class=storage_class,
        )
    else:
        parsed = cfg.parse(page_html or "", model)
    if parsed is None:
        return None
    return scrape_result_to_dict(parsed)


def audit_reference_profile(
    profile: SsdReferenceProfile,
    *,
    live: bool = False,
    html_cache: dict[str, str] | None = None,
) -> dict:
    """Run vendor scrape for one reference profile (fixture or live HTML)."""
    import driver_catalog as dc

    cfg = SSD_VENDOR_REGISTRY.get(profile.vendor_key)
    if not cfg:
        return {
            "profile": profile,
            "status": "unsupported_vendor",
            "vendor_key": profile.vendor_key,
        }

    html = ""
    fetch_ok = True
    if live:
        import firmware_catalog as fwcat

        ok, html = fwcat._fetch_vendor_page_html(cfg.primary_url)
        fetch_ok = ok
    elif html_cache and profile.vendor_key in html_cache:
        html = html_cache[profile.vendor_key]
    elif html_cache and cfg.primary_url in html_cache:
        html = html_cache[cfg.primary_url]

    row = fetch_vendor_ssd_firmware(profile.vendor_key, profile.model, html=html)
    if not row:
        return {"profile": profile, "status": "no_config", "fetch_ok": fetch_ok}

    ver = (row.get("version") or "").strip()
    installed = (profile.example_installed or "").strip()
    vs = "n/a"
    if ver and installed:
        vs = dc.compare_firmware_versions(installed, ver, title=row.get("title") or "")
    elif ver and not installed:
        vs = "catalog_only"

    if row.get("coverage_check_failed"):
        status = row.get("coverage_reason") or "coverage_gap"
    elif vs in ("same", "older"):
        status = "up_to_date"
    elif vs == "newer":
        status = "update_available"
    elif vs == "catalog_only":
        status = "version_found"
    else:
        status = "compare_unknown"

    return {
        "profile": profile,
        "status": status,
        "fetch_ok": fetch_ok,
        "vs_installed": vs,
        "vendor_row": row,
        "parse_method": row.get("parse_method") or "",
    }
