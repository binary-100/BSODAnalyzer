"""Catalog offer status eligibility and summarization (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_offer_pipeline import (
    _STATUS_RANK,
    filter_offers_for_display,
    offer_source_sort_tier,
)
from catalog_scoring import compare_versions
from catalog_device_context import (
    _ctx_is_intel_chipset_platform_row,
    _device_is_intel_chipset_plumbing,
)
from catalog_tier_policy import _is_informational_catalog_offer


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def _offer_is_intel_chipset_inf(offer: dict) -> bool:
    title = (offer.get("title") or "").lower()
    label = (offer.get("source_label") or "").lower()
    return "chipset" in title and ("intel" in title or "intel" in label)


def _is_oem_support_link_offer(offer: dict) -> bool:
    if (offer.get("source") or "").lower() != "oem":
        return False
    if _dc("_offer_version_from_fields")(offer):
        return False
    title = (offer.get("title") or "").lower()
    return "support" in title and ("—" in title or " - " in title or "your model" in title)


def _microsoft_offer_status_eligible(offer: dict) -> bool:
    """Microsoft packages may drive device status only with WU or HWID proof."""
    if (offer.get("source") or "").lower() != "microsoft":
        return True
    vs = (offer.get("vs_installed") or "").lower()
    if vs not in ("newer", "same"):
        return True
    if offer.get("wu_offered") or offer.get("hwid_matched"):
        return True
    if vs == "same" and _dc("_offer_version_from_fields")(offer):
        return True
    return False


def _offer_contributes_to_status(offer: dict, device_ctx: dict | None = None) -> bool:
    if offer.get("status_neutral"):
        return False
    if offer.get("informational_only") or _is_informational_catalog_offer(offer):
        return False
    ctx = device_ctx or {}
    if (
        _device_is_intel_chipset_plumbing(ctx)
        and not _ctx_is_intel_chipset_platform_row(ctx)
        and _offer_is_intel_chipset_inf(offer)
    ):
        return False
    src = (offer.get("source") or "").lower()
    vs = (offer.get("vs_installed") or "").lower()
    if vs == "older":
        return False
    if src == "oem":
        if _is_oem_support_link_offer(offer):
            return False
        if vs == "newer":
            if not _dc("_offer_version_from_fields")(offer):
                return False
            if not _dc("_offer_has_installable_package")(offer):
                return False
        return bool(_dc("_offer_version_from_fields")(offer) or vs in ("same", "uncertain", "unknown"))
    if src == "microsoft":
        if vs == "newer" and not _microsoft_offer_status_eligible(offer):
            return False
        if vs == "newer" and not _dc("_offer_trusted_for_confident_newer")(offer):
            return False
        return bool(
            _dc("_offer_version_from_fields")(offer)
            or offer.get("wu_offered")
            or vs in ("same", "uncertain", "unknown")
        )
    if src in ("vendor", "ssd_vendor"):
        if vs == "newer" and not _dc("_offer_has_installable_package")(offer):
            return False
    return bool(_dc("_offer_version_from_fields")(offer) or vs in ("newer", "same", "uncertain", "unknown"))


def _tier_has_actionable_offers(
    offers: list[dict],
    device_ctx: dict | None = None,
) -> bool:
    return any(_offer_contributes_to_status(o, device_ctx) for o in offers)


def _best_status_from_offers(
    offers: list[dict],
    device_ctx: dict | None = None,
) -> str:
    """Best status among offers that may drive device row status."""
    eligible = [o for o in offers if _offer_contributes_to_status(o, device_ctx)]
    if not eligible:
        return "none"
    if any((o.get("vs_installed") or "").lower() == "newer" for o in eligible):
        return "newer"
    best = "none"
    for o in eligible:
        vs = (o.get("vs_installed") or "unknown").lower()
        if vs not in _STATUS_RANK:
            vs = "unknown"
        if vs == "uncertain":
            continue
        if _STATUS_RANK[vs] < _STATUS_RANK[best]:
            best = vs
    if best in ("none", "unknown"):
        versioned = best_versioned_offer(eligible)
        if versioned:
            vs = (versioned.get("vs_installed") or "unknown").lower()
            if vs in _STATUS_RANK and vs != "uncertain":
                return vs
    if best == "none" and any(
        (o.get("vs_installed") or "").lower() == "uncertain" for o in eligible
    ):
        return "uncertain"
    return best


def _status_relevant_offers(offers: list | None) -> list[dict]:
    """Offers that are not informational-only placeholders."""
    return [
        o for o in (offers or [])
        if not o.get("informational_only")
        and not o.get("status_neutral")
        and not _is_informational_catalog_offer(o)
    ]


def summarize_offer_status(
    offers: list | None,
    *,
    device_ctx: dict | None = None,
) -> str:
    """Source-authoritative status: device vendor → OEM → Microsoft."""
    if not offers:
        return "none"
    relevant = filter_offers_for_display(offers)
    pool = _status_relevant_offers(offers)
    if not relevant:
        if not any(_offer_contributes_to_status(o, device_ctx) for o in pool):
            uncertain_versioned = [
                o for o in pool
                if _dc("_offer_version_from_fields")(o)
                and (o.get("vs_installed") or "").lower() == "uncertain"
            ]
            if uncertain_versioned:
                return "uncertain"
            versioned = [
                o for o in pool
                if _dc("_offer_version_from_fields")(o)
                and (o.get("vs_installed") or "").lower() != "uncertain"
            ]
            if versioned and all((o.get("vs_installed") or "").lower() == "older" for o in versioned):
                return "none"
            if any(_dc("_offer_version_from_fields")(o) for o in pool):
                return "uncertain"
            return "none"
        uncertain_versioned = [
            o for o in pool
            if _dc("_offer_version_from_fields")(o)
            and (o.get("vs_installed") or "").lower() == "uncertain"
        ]
        if uncertain_versioned:
            return "uncertain"
        versioned = [
            o for o in pool
            if _dc("_offer_version_from_fields")(o)
            and (o.get("vs_installed") or "").lower() != "uncertain"
        ]
        if versioned and all((o.get("vs_installed") or "").lower() == "older" for o in versioned):
            return "none"
        if any(_dc("_offer_version_from_fields")(o) for o in pool):
            return "uncertain"
        return "none"
    fallback = "none"
    for tier in (0, 1, 2):
        tier_offers = [
            o for o in relevant if offer_source_sort_tier(o.get("source")) == tier
        ]
        if not tier_offers or not _tier_has_actionable_offers(tier_offers, device_ctx):
            continue
        status = _best_status_from_offers(tier_offers, device_ctx)
        if status == "newer":
            return "newer"
        if status in ("same", "older"):
            return status
        if status == "uncertain":
            fallback = "uncertain"
    return fallback


def best_catalog_offer_version(offers: list[dict] | None) -> str:
    """Highest version string among display-eligible catalog offers."""
    best = ""
    for o in filter_offers_for_display(offers or []):
        ver = (_dc("_offer_version_from_fields")(o) or "").strip()
        if not ver:
            continue
        if not best or compare_versions(ver, best) == "newer":
            best = ver
    return best



def best_authoritative_offer(
    offers: list[dict] | None,
    *,
    device_ctx: dict | None = None,
) -> dict | None:
    """Best package for status display using manufacturer → OEM → Microsoft priority."""
    relevant = filter_offers_for_display(offers or [])
    for tier in (0, 1, 2):
        tier_offers = [
            o for o in relevant if offer_source_sort_tier(o.get("source")) == tier
        ]
        if not tier_offers or not _tier_has_actionable_offers(tier_offers, device_ctx):
            continue
        best: dict | None = None
        best_rank = 99
        for o in tier_offers:
            if not _offer_contributes_to_status(o, device_ctx):
                continue
            ver = _dc("_offer_version_from_fields")(o)
            vs = (o.get("vs_installed") or "unknown").lower()
            rank = _STATUS_RANK.get(vs, 99)
            if rank < best_rank or (rank == best_rank and ver and not best):
                best_rank = rank
                best = dict(o)
                if ver:
                    best["version"] = ver
        if best:
            return best
    return None


def best_versioned_offer(offers: list[dict] | None) -> dict | None:
    """Highest-scoring package with a version string (for UI display)."""
    best: dict | None = None
    best_rank = 99
    for o in filter_offers_for_display(offers or []):
        ver = _dc("_offer_version_from_fields")(o)
        if not ver:
            continue
        vs = (o.get("vs_installed") or "unknown").lower()
        rank = _STATUS_RANK.get(vs, 99)
        if rank < best_rank:
            best_rank = rank
            best = dict(o)
            best["version"] = ver
    return best


__all__ = [
    "_best_status_from_offers",
    "_is_oem_support_link_offer",
    "_microsoft_offer_status_eligible",
    "_offer_contributes_to_status",
    "_offer_is_intel_chipset_inf",
    "_status_relevant_offers",
    "_tier_has_actionable_offers",
    "best_catalog_offer_version",
    "summarize_offer_status",
    "best_authoritative_offer",
    "best_versioned_offer",
]
