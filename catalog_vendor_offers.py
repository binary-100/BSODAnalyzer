"""Shared vendor offer rows and manufacturer lookup gating (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_extended_fetch import _EXTENDED_VENDOR_KEYS
from catalog_http import _http_get
from catalog_scoring import extract_version_from_text
from catalog_tier_policy import _NETWORK_VENDOR_KEYS


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def _catalog_system_ctx_from(ctx: dict, system_ctx: dict | None = None) -> dict:
    if system_ctx:
        return system_ctx
    stored = ctx.get("_catalog_system_ctx")
    return stored if isinstance(stored, dict) else {}
def _manufacturer_vendor_lookup_applicable(
    vendor_key: str,
    system_ctx: dict | None,
) -> bool:
    """PC-level gate: skip manufacturer HTTP when this vendor is absent from hardware."""
    from bsod_hardware_wmi import (
        amd_driver_lookup_applicable,
        catalog_hardware_context_confident,
        intel_driver_lookup_applicable,
        network_vendor_driver_lookup_applicable,
        nvidia_driver_lookup_applicable,
        realtek_driver_lookup_applicable,
        vendor_present_in_hardware,
    )

    vk = (vendor_key or "").lower().strip()
    if not vk:
        return False
    ctx = system_ctx or {}
    if not catalog_hardware_context_confident(ctx):
        return True
    if vk == "intel":
        return intel_driver_lookup_applicable(ctx)
    if vk == "amd":
        return amd_driver_lookup_applicable(ctx)
    if vk == "nvidia":
        return nvidia_driver_lookup_applicable(ctx)
    if vk == "realtek":
        return realtek_driver_lookup_applicable(ctx)
    if vk in _NETWORK_VENDOR_KEYS:
        return network_vendor_driver_lookup_applicable(vk, ctx)
    if vk in _EXTENDED_VENDOR_KEYS:
        return vendor_present_in_hardware(ctx, vk)
    return vendor_present_in_hardware(ctx, vk)
def _offer_version_from_fields(offer: dict) -> str:
    ver = (offer.get("version") or "").strip()
    if ver:
        return ver
    src = (offer.get("source") or "").lower()
    if src in ("oem", "vendor") and (offer.get("confidence") or "").lower() == "low":
        return ""
    extracted = extract_version_from_text(
        f"{offer.get('title') or ''} {offer.get('notes') or ''}"
    )
    if not extracted:
        return ""
    if "." not in extracted and src in ("oem", "vendor", "utility"):
        return ""
    return extracted
def _record_vendor_empty_extraction(vendor: str, detail: str) -> None:
    """Session signal for parser rot (page OK / applicable, no version)."""
    try:
        import vendor_fetch as vf

        vf.record_empty_extraction(vendor, detail)
    except ImportError:
        pass
def _vendor_fetch_get(
    url: str,
    *,
    accept: str = "text/html,application/xhtml+xml",
    referer: str | None = None,
    insecure_fallback: bool = False,
) -> tuple[bool, str]:
    """Shared robust GET for OEM/firmware vendor endpoints (parity with vendor_firmware_fetch)."""
    try:
        import vendor_firmware_fetch as vff

        if "json" in (accept or "").lower():
            return vff.fetch_json_robust(url, referer=referer, accept=accept)
        return vff.fetch_http_robust(
            url,
            referer=referer,
            accept=accept,
        )
    except ImportError:
        return _http_get(
            url,
            headers={"Accept": accept} if accept else None,
            referer=referer,
            insecure_fallback=insecure_fallback,
        )
def _vendor_coverage_gap_offer(
    *, source_label: str, title: str, url: str, vendor_disp: str = ""
) -> dict:
    """Honest "couldn't verify" row for a version-applicable device whose vendor
    fetch was blocked (bot wall / timeout / empty).

    Surfaces as ``uncertain`` instead of a silent no-offer that would read as
    "confirmed current" — the universal safety net so a blocked vendor never
    makes a device look up to date when we never actually managed to check it.
    """
    name = vendor_disp or source_label
    return {
        "source": "vendor",
        "source_label": source_label,
        "title": title,
        "version": "",
        "date": "",
        "url": url,
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "vs_installed": "uncertain",
        "notes": (
            f"Couldn't verify the latest {name} version automatically (the vendor site "
            "blocked or didn't answer the check). Open the vendor page to confirm."
        ),
        "confidence": "low",
        "coverage_check_failed": True,
    }
def _vendor_offer_row(
    *,
    vendor_key: str,
    title: str,
    version: str = "",
    date: str = "",
    url: str = "",
    notes: str = "",
    confidence: str = "low",
) -> dict:
    label = vendor_key.title()
    if vendor_key == "qualcomm":
        label = "Qualcomm / Atheros"
    return {
        "source": "vendor",
        "source_label": f"Manufacturer ({label})",
        "title": title[:120],
        "version": version,
        "date": date,
        "url": url,
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": notes,
        "confidence": confidence,
    }
def fetch_generic_vendor_offer(ctx: dict) -> list[dict]:
    vk = (ctx.get("vendor_key") or "").lower()
    if vk in ("nvidia", "amd", "intel") or vk in _NETWORK_VENDOR_KEYS or vk in _EXTENDED_VENDOR_KEYS or vk == "realtek":
        return []
    if not vk or vk not in _dc("_VENDOR_DRIVER_URLS"):
        return []
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        vk, _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    url, title = _dc("_VENDOR_DRIVER_URLS")[vk]
    return [{
        "source": "vendor",
        "source_label": f"Manufacturer ({vk.title()})",
        "title": title,
        "version": "",
        "date": "",
        "url": url,
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": "No live version API for this vendor; open the download center.",
        "confidence": "low",
        "vs_installed": "uncertain",
        "compare_note": "Vendor page has no version string — compare manually on the site.",
    }]
