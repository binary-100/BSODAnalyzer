"""Audit manufacturer lookup pages — find broken URLs and user-approved replacements."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import vendor_endpoint_health as veh

_INTEL_DOWNLOAD_LINK_RE = re.compile(
    r"https://www\.intel\.com/content/www/us/en/download/\d+/[a-z0-9\-]+\.html",
    re.I,
)

INTEL_HINT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "graphics": ("graphics", "dch", "arc", "iris", "uhd"),
    "chipset": ("chipset", "inf", "platform"),
    "wifi": ("wireless", "wi-fi", "wifi", "wlan"),
}

# Shipped alternates — expanded in releases. Audit also tries DSA link harvest + remote manifest.
CANDIDATE_INTEL_PAGES: dict[str, list[str]] = {
    "graphics": [
        "https://www.intel.com/content/www/us/en/download/19344/"
        "intel-graphics-windows-dch-drivers.html",
    ],
    "chipset": [
        "https://www.intel.com/content/www/us/en/download/19347/"
        "chipset-inf-utility.html",
        "https://www.intel.com/content/www/us/en/download/17608/"
        "intel-chipset-inf-utility.html",
    ],
    "wifi": [
        "https://www.intel.com/content/www/us/en/download/19351/"
        "intel-wireless-wi-fi-drivers.html",
    ],
}

CANDIDATE_AMD_PAGES: list[str] = [
    "https://www.amd.com/en/support/download/drivers.html",
]

INTEL_HINT_BY_KEY = {
    "graphics_product": "graphics",
    "chipset_product": "chipset",
    "wifi_product": "wifi",
}

INTEL_LABEL_BY_KEY = {
    "graphics_product": "Intel graphics download page",
    "chipset_product": "Intel chipset download page",
    "wifi_product": "Intel Wi-Fi download page",
}

# Populated during audit when a remote manifest is fetched (not saved until user applies).
_runtime_manifest_candidates: dict[str, dict[str, list[str]]] = {}


@dataclass
class EndpointAuditRow:
    vendor: str
    endpoint_key: str
    label: str
    current_url: str
    status: str  # ok | broken | update_available | skipped
    recommended_url: str = ""
    version_sample: str = ""
    detail: str = ""


def _intel_page_applicable(key: str, system_ctx: dict | None) -> bool:
    try:
        import bsod_hardware_wmi as hw
    except ImportError:
        return True
    ctx = system_ctx or {}
    hint = INTEL_HINT_BY_KEY.get(key, "graphics")
    if hint == "chipset":
        return hw.intel_chipset_applicable(ctx)
    if hint == "wifi":
        return hw.intel_driver_lookup_applicable(ctx)
    return hw.intel_driver_lookup_applicable(ctx)


def _probe_intel_page(url: str, hint: str) -> str:
    import driver_catalog as dc

    ver, _, _ = dc._scrape_intel_download_page(url, hint=hint)
    return (ver or "").strip()


def _discover_intel_urls_from_dsa(hint: str) -> list[str]:
    """
    Harvest Intel download links from the DSA product page when we do not know the new URL.
    Conservative: keyword-filtered intel.com/download links only.
    """
    import driver_catalog as dc

    dsa = veh.get_endpoint(
        "intel",
        "dsa_fallback",
        veh.BUNDLED_ENDPOINTS.get("intel", {}).get("dsa_fallback", ""),
    )
    if not dsa:
        return []
    ok, html = dc._http_get(
        dsa,
        headers={"Accept": "text/html,application/xhtml+xml"},
        referer="https://www.intel.com/content/www/us/en/download-center/home.html",
        insecure_fallback=True,
    )
    if not ok:
        return []
    keywords = INTEL_HINT_KEYWORDS.get(hint, ())
    out: list[str] = []
    seen: set[str] = set()
    for link in _INTEL_DOWNLOAD_LINK_RE.findall(html):
        slug = link.lower()
        if keywords and not any(k in slug for k in keywords):
            continue
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def _manifest_candidates_for_hint(vendor: str, hint: str, key: str) -> list[str]:
    urls: list[str] = []
    for source in (
        veh.load_manifest().get("candidates") or {},
        _runtime_manifest_candidates,
    ):
        block = source.get(vendor.lower()) or {}
        for k in (hint, key):
            for u in block.get(k) or []:
                if isinstance(u, str) and u.strip():
                    urls.append(u.strip())
    return urls


def _intel_candidate_urls(key: str, hint: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for u in (
        list(CANDIDATE_INTEL_PAGES.get(hint, []))
        + _manifest_candidates_for_hint("intel", hint, key)
        + _discover_intel_urls_from_dsa(hint)
    ):
        if u and u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def _audit_intel_page(key: str, system_ctx: dict | None) -> EndpointAuditRow:
    hint = INTEL_HINT_BY_KEY.get(key, "graphics")
    label = INTEL_LABEL_BY_KEY.get(key, f"Intel {key}")
    default = (veh.BUNDLED_ENDPOINTS.get("intel") or {}).get(key, "")
    current = veh.get_endpoint("intel", key, default)

    if not _intel_page_applicable(key, system_ctx):
        return EndpointAuditRow(
            vendor="intel",
            endpoint_key=key,
            label=label,
            current_url=current,
            status="skipped",
            detail="Not applicable on this PC.",
        )

    ver = _probe_intel_page(current, hint) if current else ""
    if ver:
        return EndpointAuditRow(
            vendor="intel",
            endpoint_key=key,
            label=label,
            current_url=current,
            status="ok",
            version_sample=ver,
            detail="Current page returns a driver version.",
        )

    tried = {current}
    discovery_source = ""
    for alt in _intel_candidate_urls(key, hint):
        if not alt or alt in tried:
            continue
        tried.add(alt)
        alt_ver = _probe_intel_page(alt, hint)
        if alt_ver:
            if alt in _discover_intel_urls_from_dsa(hint):
                discovery_source = " (found via Intel DSA page)"
            elif alt in _manifest_candidates_for_hint("intel", hint, key):
                discovery_source = " (from developer lookup catalog)"
            else:
                discovery_source = " (known alternate)"
            return EndpointAuditRow(
                vendor="intel",
                endpoint_key=key,
                label=label,
                current_url=current,
                status="update_available",
                recommended_url=alt,
                version_sample=alt_ver,
                detail=(
                    "Current page did not return a version; another address works"
                    f"{discovery_source}."
                ),
            )

    return EndpointAuditRow(
        vendor="intel",
        endpoint_key=key,
        label=label,
        current_url=current,
        status="broken",
        detail=(
            "No version from the current page, shipped alternates, DSA link harvest, "
            "or developer catalog."
        ),
    )


def _audit_amd_download(system_ctx: dict | None) -> EndpointAuditRow:
    label = "AMD driver download page"
    default = veh.BUNDLED_ENDPOINTS.get("amd", {}).get("download_page", "")
    current = veh.get_endpoint("amd", "download_page", default)

    try:
        import bsod_hardware_wmi as hw
    except ImportError:
        hw = None  # type: ignore[assignment]

    if hw and not hw.amd_driver_lookup_applicable(system_ctx):
        return EndpointAuditRow(
            vendor="amd",
            endpoint_key="download_page",
            label=label,
            current_url=current,
            status="skipped",
            detail="Not applicable on this PC.",
        )

    import driver_catalog as dc

    ctx = {"hw_category": "graphics", "device_label": "AMD Radeon"}

    def version_at(url: str) -> str:
        ok, html = dc._http_get(url)
        if not ok or len(html) < 10_000:
            return ""
        fam = dc._amd_gpu_family_hint(ctx)
        if fam:
            fam_ver = dc._version_near_product_in_html(html, fam)
            if fam_ver:
                return fam_ver
        return dc._parse_amd_page_version(html) or ""

    ver = version_at(current) if current else ""
    if ver:
        return EndpointAuditRow(
            vendor="amd",
            endpoint_key="download_page",
            label=label,
            current_url=current,
            status="ok",
            version_sample=ver,
            detail="Current AMD download center returns a version.",
        )

    for alt in CANDIDATE_AMD_PAGES:
        if alt == current:
            continue
        alt_ver = version_at(alt)
        if alt_ver:
            return EndpointAuditRow(
                vendor="amd",
                endpoint_key="download_page",
                label=label,
                current_url=current,
                status="update_available",
                recommended_url=alt,
                version_sample=alt_ver,
                detail="Current page failed; a known alternate responds.",
            )

    return EndpointAuditRow(
        vendor="amd",
        endpoint_key="download_page",
        label=label,
        current_url=current,
        status="broken",
        detail="Could not read a version from AMD download pages.",
    )


def _audit_nvidia_lookup(system_ctx: dict | None) -> EndpointAuditRow:
    label = "NVIDIA driver lookup (Ajax / processFind)"
    current_ajax = veh.get_endpoint(
        "nvidia",
        "ajax_base",
        veh.BUNDLED_ENDPOINTS.get("nvidia", {}).get("ajax_base", ""),
    )

    try:
        import bsod_hardware_wmi as hw
    except ImportError:
        hw = None  # type: ignore[assignment]

    if hw and not hw.nvidia_driver_lookup_applicable(system_ctx):
        return EndpointAuditRow(
            vendor="nvidia",
            endpoint_key="ajax_base",
            label=label,
            current_url=current_ajax,
            status="skipped",
            detail="Not applicable on this PC.",
        )

    import driver_catalog as dc

    ctx = {
        "vendor_key": "nvidia",
        "pnp_class": "display",
        "device_label": "NVIDIA GeForce",
    }
    hit, method = dc._nvidia_lookup_download_info(ctx)
    ver = (hit or {}).get("Version") or ""
    if ver:
        return EndpointAuditRow(
            vendor="nvidia",
            endpoint_key="ajax_base",
            label=label,
            current_url=current_ajax,
            status="ok",
            version_sample=ver,
            detail=f"Lookup chain OK ({method or 'unknown method'}).",
        )

    return EndpointAuditRow(
        vendor="nvidia",
        endpoint_key="ajax_base",
        label=label,
        current_url=current_ajax,
        status="broken",
        detail="NVIDIA lookup returned no version. A program update may be required.",
    )


def run_lookup_address_audit(
    system_ctx: dict | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[EndpointAuditRow]:
    """Test lookup pages/APIs and recommend user-approved URL updates when alternates work."""
    global _runtime_manifest_candidates
    _runtime_manifest_candidates = {}

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    url = (veh.BUNDLED_LOOKUP_MANIFEST_URL or "").strip()
    remote_data: dict | None = None
    if url:
        prog("Checking developer lookup catalog…")
        remote_data, err = veh.fetch_remote_manifest(url)
        if remote_data and isinstance(remote_data.get("candidates"), dict):
            _runtime_manifest_candidates = remote_data["candidates"]

    rows: list[EndpointAuditRow] = []

    prog("Auditing NVIDIA lookup…")
    rows.append(_audit_nvidia_lookup(system_ctx))

    prog("Auditing AMD download page…")
    rows.append(_audit_amd_download(system_ctx))

    for key in ("graphics_product", "chipset_product", "wifi_product"):
        prog(f"Auditing {INTEL_LABEL_BY_KEY.get(key, key)}…")
        rows.append(_audit_intel_page(key, system_ctx))

    if remote_data and isinstance(remote_data.get("endpoints"), dict):
        for vendor, patch in remote_data["endpoints"].items():
            if not isinstance(patch, dict):
                continue
            for ep_key, ep_url in patch.items():
                if not isinstance(ep_url, str) or not ep_url.strip():
                    continue
                current = veh.get_endpoint(vendor, ep_key, ep_url)
                if current.strip() != ep_url.strip():
                    rows.append(
                        EndpointAuditRow(
                            vendor=vendor.lower(),
                            endpoint_key=ep_key,
                            label=f"{vendor.title()} {ep_key} (developer catalog)",
                            current_url=current,
                            status="update_available",
                            recommended_url=ep_url.strip(),
                            detail="Developer lookup catalog lists a newer address.",
                        )
                    )

    return rows


def recommended_patches(rows: list[EndpointAuditRow]) -> dict[str, dict[str, str]]:
    patches: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.status != "update_available":
            continue
        rec = (row.recommended_url or "").strip()
        if not rec:
            continue
        if rec == (row.current_url or "").strip():
            continue
        patches.setdefault(row.vendor, {})[row.endpoint_key] = rec
    return patches


def apply_audit_patches(
    rows: list[EndpointAuditRow],
    *,
    source: str = "user_audit",
) -> tuple[bool, str]:
    patches = recommended_patches(rows)
    if not patches:
        return False, "No recommended lookup page updates were found."
    return veh.apply_repair_manifest(patches, source=source)


def format_audit_report(rows: list[EndpointAuditRow]) -> str:
    status_labels = {
        "ok": "OK",
        "broken": "NEEDS ATTENTION",
        "update_available": "UPDATE AVAILABLE",
        "skipped": "SKIPPED",
    }
    lines = [
        "Manufacturer lookup page audit:",
        "(Tests download pages only — does not modify the program.)",
        "",
    ]
    updates = 0
    for row in rows:
        lines.append(f"• {row.label}: {status_labels.get(row.status, row.status)}")
        if row.current_url:
            lines.append(f"    Current: {row.current_url}")
        if row.version_sample:
            lines.append(f"    Sample version: {row.version_sample}")
        if row.recommended_url and row.status == "update_available":
            lines.append(f"    Recommended: {row.recommended_url}")
            updates += 1
        if row.detail:
            lines.append(f"    {row.detail}")
        lines.append("")

    if updates:
        lines.append(
            f"{updates} recommended update(s) found. "
            "Choose Apply to save new addresses to your settings folder only."
        )
    elif any(r.status == "broken" for r in rows):
        lines.append(
            "Some lookups failed and no alternate page was found. "
            "Try again later or install a newer BSOD Analyzer build."
        )
    else:
        lines.append("All applicable lookup pages look correct.")
    return "\n".join(lines)
