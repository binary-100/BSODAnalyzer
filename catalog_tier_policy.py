"""Catalog tier/deferral/OEM-skip policy (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_device_context import _device_is_chipset_plumbing
from catalog_offer_pipeline import (
    _finalize_catalog_offers,
    _installed_driver_date_from_ctx,
)
from catalog_scoring import compare_versions


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_NETWORK_VENDOR_KEYS = frozenset({"killer", "broadcom", "qualcomm", "mediatek"})


def _is_informational_catalog_offer(offer: dict) -> bool:
    if offer.get("informational") or offer.get("informational_only"):
        return True
    if (offer.get("version") or "").strip():
        return False
    if (offer.get("wu_offered") or offer.get("update_id")):
        return False
    title = (offer.get("title") or "").lower()
    if any(
        phrase in title
        for phrase in (
            "no optional driver updates pending",
            "online catalog scan skipped",
            "could not query windows update",
            "windows online driver catalog unavailable",
            "search catalog:",
        )
    ):
        return True
    return _dc("_offer_download_kind")(offer) == "uri" and not (offer.get("update_id") or "").strip()


def _is_manufacturer_catalog_offer(offer: dict) -> bool:
    """Device-vendor package (not PC maker OEM, Microsoft, or utility/link rows)."""
    src = (offer.get("source") or "").lower()
    return src not in ("oem", "oem_firmware", "microsoft", "utility")


def has_actionable_versioned_manufacturer_offer(offers: list[dict] | None) -> bool:
    """True when a manufacturer source returned a versioned package (tier-1 satisfied)."""
    for o in offers or []:
        if not _is_manufacturer_catalog_offer(o):
            continue
        if _is_informational_catalog_offer(o) or o.get("informational_only"):
            continue
        if _dc("_offer_version_from_fields")(o):
            return True
    return False


def _ctx_is_chipset_catalog(ctx: dict) -> bool:
    if ctx.get("hw_category") == "chipset":
        return True
    return _device_is_chipset_plumbing(ctx)


def _ctx_gpu_or_network_catalog(ctx: dict) -> bool:
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp in ("display", "net"):
        return True
    vk = (ctx.get("vendor_key") or "").lower()
    if vk in _NETWORK_VENDOR_KEYS:
        return True
    label = (ctx.get("device_label") or "").lower()
    return "wi-fi" in label or "wifi" in label or "wireless" in label or "ethernet" in label


def _manufacturer_confident_newer_offer(offers: list[dict] | None) -> bool:
    """GPU/network early exit: skip OEM when manufacturer tier has high-confidence newer."""
    for o in offers or []:
        if not _is_manufacturer_catalog_offer(o):
            continue
        if (o.get("vs_installed") or "").lower() != "newer":
            continue
        if (o.get("confidence") or "").lower() == "low":
            continue
        if not _dc("_offer_version_from_fields")(o):
            continue
        if _is_informational_catalog_offer(o) or o.get("informational_only"):
            continue
        return True
    return False


def _manufacturer_gpu_lookup_uncertain(
    offers: list[dict] | None,
    ctx: dict,
    *,
    system_ctx: dict | None = None,
) -> bool:
    """Primary GPU: manufacturer fetch blocked or returned no version (P4 MSCatalog gate)."""
    if not _dc("_is_primary_gpu_display_manufacturer_authoritative")(ctx, system_ctx):
        return False
    mfr = [o for o in (offers or []) if _is_manufacturer_catalog_offer(o)]
    if not mfr:
        return True
    for o in mfr:
        if o.get("coverage_check_failed") or o.get("generation_mismatch"):
            return True
    if not any(_dc("_offer_version_from_fields")(o) for o in mfr):
        return True
    return False


def _should_skip_oem_after_manufacturer_tier(
    ctx: dict,
    manufacturer_offers: list[dict],
    installed: str,
    *,
    system_ctx: dict | None = None,
) -> bool:
    """
    Tiered search (B + selective C): manufacturer first, OEM second when needed.
    Chipset always runs OEM; primary GPU display skips OEM always; other GPU/network
    skip OEM on confident manufacturer newer.
    """
    if _dc("_is_primary_gpu_display_manufacturer_authoritative")(ctx, system_ctx):
        return True
    if _ctx_is_chipset_catalog(ctx):
        return False
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if vk == "realtek" and pnp == "net":
        return False
    if not manufacturer_offers:
        return False
    enriched = _finalize_catalog_offers(
        list(manufacturer_offers),
        installed,
        device_ctx=ctx,
        installed_date=_installed_driver_date_from_ctx(ctx),
    )
    mfr = [o for o in enriched if _is_manufacturer_catalog_offer(o)]
    if _ctx_gpu_or_network_catalog(ctx):
        return _manufacturer_confident_newer_offer(mfr)
    return has_actionable_versioned_manufacturer_offer(mfr)


def has_actionable_versioned_offer(offers: list[dict] | None) -> bool:
    """True when OEM or device-vendor sources returned a versioned package (not a support link)."""
    for o in offers or []:
        src = (o.get("source") or "").lower()
        if src in ("microsoft", "utility"):
            continue
        if src == "oem" and not (o.get("version") or "").strip():
            ver = _dc("_offer_version_from_fields")(o)
            if not ver:
                continue
        ver = _dc("_offer_version_from_fields")(o)
        if ver:
            return True
    return False


def should_defer_microsoft_catalog(
    offers: list[dict] | None,
    installed: str,
    ctx: dict | None = None,
) -> bool:
    """
    Defer slow MSCatalog when OEM/vendor already returned a useful versioned package
    that is same or newer than installed. Stale OEM rows and incomparable version
    formats do not defer — MSCatalog may have newer UAD builds (e.g. Realtek 1125 vs 11.x).
    """
    if ctx and (ctx.get("vendor_key") or "").lower() == "realtek":
        if (ctx.get("pnp_class") or "").lower() == "net":
            return False
    inst = (installed or "").strip()
    if not inst:
        return has_actionable_versioned_offer(offers)
    found_versioned = False
    for o in offers or []:
        src = (o.get("source") or "").lower()
        if src in ("microsoft", "utility"):
            continue
        if _dc("_is_oem_support_link_offer")(o):
            continue
        ver = _dc("_offer_version_from_fields")(o)
        if not ver:
            continue
        found_versioned = True
        cmp = compare_versions(inst, ver)
        if cmp in ("newer", "same"):
            return True
    return False if found_versioned else has_actionable_versioned_offer(offers)


def _oem_disk_offers_stale_vs_installed(filtered: list[dict], ctx: dict) -> bool:
    """True when cached OEM packages are all older than the installed driver."""
    installed = (ctx.get("primary_version") or "").strip()
    for inv in ctx.get("installed_rows") or []:
        installed = installed or (inv.get("version") or "").strip()
    if not installed:
        return False
    oem_versioned = [
        o for o in filtered
        if (o.get("source") or "").lower() == "oem"
        and _dc("_offer_version_from_fields")(o)
        and not _dc("_is_oem_support_link_offer")(o)
    ]
    if not oem_versioned:
        return False
    return all(
        compare_versions(installed, _dc("_offer_version_from_fields")(o)) == "older"
        for o in oem_versioned
    )


__all__ = [
    "_NETWORK_VENDOR_KEYS",
    "_ctx_gpu_or_network_catalog",
    "_ctx_is_chipset_catalog",
    "_is_informational_catalog_offer",
    "_is_manufacturer_catalog_offer",
    "_manufacturer_confident_newer_offer",
    "_manufacturer_gpu_lookup_uncertain",
    "_oem_disk_offers_stale_vs_installed",
    "_should_skip_oem_after_manufacturer_tier",
    "has_actionable_versioned_manufacturer_offer",
    "has_actionable_versioned_offer",
    "should_defer_microsoft_catalog",
]
