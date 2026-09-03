"""Realtek UAD/OEM catalog query and compare helpers (from driver_catalog)."""

from __future__ import annotations

from datetime import datetime

from catalog_device_context import _ctx_device_label
from catalog_row_rejects import (
    _realtek_catalog_row_is_wdm_codec,
    _realtek_device_component_role,
)


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def _is_primary_realtek_wdm_oem_offer(offer: dict, ctx: dict) -> bool:
    if (offer.get("source") or "").lower() != "oem":
        return False
    if (ctx.get("vendor_key") or "").lower() != "realtek":
        return False
    if _realtek_device_component_role(ctx) != "wdm":
        return False
    return _realtek_catalog_row_is_wdm_codec(offer)


def _soften_stale_realtek_wdm_oem_compare(offer: dict, ctx: dict) -> None:
    """Keep matched Dell Realtek HD visible when installed codec is already newer."""
    if (offer.get("vs_installed") or "").lower() != "older":
        return
    if not _is_primary_realtek_wdm_oem_offer(offer, ctx):
        return
    inst = (ctx.get("primary_version") or offer.get("installed_version") or "").strip()
    cand = _dc("_offer_version_from_fields")(offer) or "?"
    offer["vs_installed"] = "same"
    offer["status_neutral"] = True
    offer["compare_note"] = (
        f"Installed Realtek driver ({inst}) is newer than this Dell package ({cand}) — "
        "no update needed from this source; refresh the OEM catalog if Dell published a "
        "newer build."
    )


def _realtek_uad_catalog_queries(ctx: dict) -> list[str]:
    """Targeted Microsoft Update Catalog searches for Realtek UAD packages."""
    role = _realtek_device_component_role(ctx)
    year = datetime.now().year
    years = (str(year), str(year - 1))
    queries: list[str] = []
    if role == "wdm":
        for y in years:
            queries.append(f"Realtek Media {y}")
        queries.extend([
            "Realtek sound 22H2",
            "Realtek sound 23H2",
            "Realtek High Definition Audio Driver",
            "Realtek Semiconductor Corp Media",
            "Realtek UAD Driver",
        ])
    elif role == "apo":
        for y in years:
            queries.append(f"Realtek AudioProcessingObject {y}")
        queries.append("Realtek Audio Effects Component")
    elif role == "swc":
        for y in years:
            queries.append(f"Realtek SoftwareComponent {y}")
        label = _ctx_device_label(ctx)
        if "universal service" in label:
            queries.append("Realtek Audio Universal Service")
        elif "hardware support" in label:
            queries.append("Realtek Hardware Support Application")
        elif "asio" in label:
            queries.append("Realtek Asio Component")
    elif role == "net":
        queries.extend([
            "Realtek PCIe Ethernet Controller Driver",
            "Realtek Gaming 2.5GbE Family Controller",
            "Realtek Ethernet Controller Driver",
        ])
    return queries


__all__ = [
    "_is_primary_realtek_wdm_oem_offer",
    "_realtek_uad_catalog_queries",
    "_soften_stale_realtek_wdm_oem_compare",
]
