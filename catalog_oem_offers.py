"""OEM offer orchestration and disk-cache freshness (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_mscatalog_session import is_quick_check_mode
from catalog_offer_status import _is_oem_support_link_offer
from catalog_tier_policy import _oem_disk_offers_stale_vs_installed
from catalog_wu_scoring import _filter_offers_for_device_ctx


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def _tag_offer_freshness(offers: list[dict], freshness: str) -> list[dict]:
    out: list[dict] = []
    for o in offers:
        row = dict(o)
        row["data_freshness"] = freshness
        out.append(row)
    return out
def oem_data_freshness_note(freshness: str) -> str:
    labels = {
        "live": "Live OEM query (just fetched from the PC maker support API).",
        "session": (
            "Session cache from this app run — use Tools → Refresh driver database "
            "for a full OEM rebuild."
        ),
        "disk": "On-disk OEM database (from Refresh driver database).",
        "stale_disk": (
            "Stale on-disk OEM data — use Tools → Refresh driver database "
            "for a full update."
        ),
    }
    return labels.get((freshness or "").strip(), "")
def _oem_support_link_offers(system_ctx: dict | None, *, note: str) -> list[dict]:
    if not _dc("system_has_oem_driver_catalog")(system_ctx):
        return []
    oem_url = _dc("_system_manufacturer_oem_url")(system_ctx)
    if not oem_url:
        return []
    mfr_disp = (system_ctx or {}).get("system_manufacturer") or "OEM"
    model = (system_ctx or {}).get("system_model") or ""
    return [{
        "source": "oem",
        "source_label": f"OEM ({mfr_disp})",
        "title": f"{mfr_disp} support — {model or 'your model'}".strip(),
        "version": "",
        "date": "",
        "url": oem_url,
        "download_kind": "url",
        "update_id": "",
        "instance_id": "",
        "notes": note,
        "confidence": "low",
    }]
def fetch_oem_driver_offers_deep(system_ctx: dict | None) -> list[dict]:
    """Fetch full OEM catalogs for disk cache (no per-device scoring at build time)."""
    offers = _dc("fetch_oem_catalog_for_system")(system_ctx)
    if not offers and _dc("system_has_oem_driver_catalog")(system_ctx):
        offers.extend(
            _oem_support_link_offers(
                system_ctx,
                note="Version not available via API; open support site for model-specific WHQL drivers.",
            )
        )
    return offers
def fetch_oem_driver_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    """OEM drivers: on-disk cache in full install; deep scrape only on database refresh."""
    try:
        import catalog_cache as ccat
    except ImportError:
        ccat = None  # type: ignore[assignment]

    if ccat and ccat.is_force_deep_catalog():
        offers = fetch_oem_driver_offers_deep(system_ctx)
        ccat.save_oem_offers(offers, system_ctx=system_ctx)
        return _filter_offers_for_device_ctx(list(offers), ctx)

    if ccat and ccat.should_use_disk_cache():
        offers, blob = ccat.load_oem_offers(system_ctx)
        if blob and offers:
            filtered = _filter_offers_for_device_ctx(list(offers), ctx)
            freshness = "disk" if ccat.is_catalog_fresh(blob) else "stale_disk"
            filtered = _tag_offer_freshness(filtered, freshness)
            oem_only = [o for o in filtered if (o.get("source") or "").lower() == "oem"]
            if oem_only and all(_is_oem_support_link_offer(o) for o in oem_only):
                filtered = []
            if not ccat.is_catalog_fresh(blob):
                extra = (
                    " Cached OEM data — use Tools → Refresh driver database "
                    "for a full update."
                )
                for o in filtered:
                    if o.get("source") == "oem":
                        o["notes"] = ((o.get("notes") or "") + extra).strip()
            if filtered and not _oem_disk_offers_stale_vs_installed(filtered, ctx):
                return filtered
            live = _dc("_fetch_live_oem_offers")(ctx, system_ctx)
            if live:
                return _tag_offer_freshness(live, "live")
            if filtered:
                extra = (
                    " Cached OEM package is older than your installed driver — "
                    "use Tools → Refresh driver database for a full update."
                )
                for o in filtered:
                    if (o.get("source") or "").lower() == "oem":
                        o["notes"] = ((o.get("notes") or "") + extra).strip()
                return filtered
            return _oem_support_link_offers(
                system_ctx,
                note="No matching OEM package for this device in the cached catalog.",
            )

    if is_quick_check_mode():
        live = _dc("_fetch_live_oem_offers")(ctx, system_ctx)
        if live:
            return live
        return _oem_support_link_offers(
            system_ctx,
            note="Quick check: opens your PC maker's support site (no OEM API scrape).",
        )

    live = _dc("_fetch_live_oem_offers")(ctx, system_ctx)
    if live:
        return live
    return _oem_support_link_offers(
        system_ctx,
        note=(
            "OEM database not built yet on this PC. "
            "Search for driver updates to build the catalog cache."
        ),
    )
