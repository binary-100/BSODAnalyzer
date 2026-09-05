"""Unified driver bundle verification — component manifests, compare, status rollup.

Any multi-driver package (OEM DUP, AMD/Intel chipset, graphics companion bundles, …)
normalizes to labeled components; status rollups use worst-component vs offer manifest.
"""

from __future__ import annotations

from catalog_scoring import compare_versions

# Short labels shared with catalog_device_profiles chipset bundle display.
_CHIPSET_LABEL_ALIASES: dict[str, str] = {
    "psp": "PSP",
    "smbus": "SMBus",
    "gpio": "GPIO",
    "i2c": "I2C",
    "micropep": "MicroPEP",
    "micro pep": "MicroPEP",
    "provisioning": "PPM",
    "ppm": "PPM",
    "serial io": "Serial IO",
    "management engine": "MEI",
    "mei": "MEI",
    "chipset inf": "Chipset INF",
    "sata": "SATA",
    "usb 3": "USB3",
    "usb3": "USB3",
    "usb4": "USB3",
    "thermal": "Thermal",
    "npcf": "NPCF",
    "platform controllers": "NPCF",
    "display": "Display",
    "graphics": "Display",
    "audio": "Audio",
    "net": "Network",
    "ethernet": "Network",
}


def component_label_from_text(name: str, *, default: str = "Other") -> str:
    """Map a manifest or device display name to a stable short label."""
    blob = (name or "").strip().lower()
    if not blob:
        return default
    for key, label in _CHIPSET_LABEL_ALIASES.items():
        if key in blob:
            return label
    return default


def _index_by_label(components: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in components or []:
        if not isinstance(row, dict):
            continue
        label = (row.get("label") or "").strip()
        if not label:
            label = component_label_from_text(
                row.get("device_name") or row.get("name") or ""
            )
        if label == "Other":
            continue
        ver = (row.get("version") or "").strip()
        if not ver:
            continue
        prev = out.get(label)
        if not prev or compare_versions(prev.get("version") or "", ver) == "older":
            out[label] = {
                "label": label,
                "device_name": (row.get("device_name") or row.get("name") or label).strip(),
                "version": ver,
            }
    return out


def compare_bundle_component_sets(
    installed: list[dict] | None,
    offer: list[dict] | None,
) -> tuple[list[dict], str, str]:
    """
    Compare installed vs offer bundle components by short label.

    Returns (detail_rows, rollup_status, rollup_note).
    rollup_status is ``newer`` when any installed component is behind offer;
    ``same`` when all matched labels match; ``unknown`` when nothing to compare.
    """
    inst_map = _index_by_label(installed or [])
    offer_map = _index_by_label(offer or [])
    if not offer_map or not inst_map:
        return [], "unknown", ""

    details: list[dict] = []
    any_stale = False
    any_compared = False
    stale_labels: list[str] = []

    for label in sorted(set(inst_map) & set(offer_map)):
        iver = inst_map[label]["version"]
        over = offer_map[label]["version"]
        vs = compare_versions(iver, over)
        any_compared = True
        row = {
            "label": label,
            "installed_version": iver,
            "offer_version": over,
            "vs_offer": vs,
            "device_name": inst_map[label].get("device_name") or label,
        }
        details.append(row)
        if vs == "newer":
            any_stale = True
            stale_labels.append(label)

    if not any_compared:
        return details, "unknown", ""
    if any_stale:
        short = ", ".join(stale_labels[:4])
        if len(stale_labels) > 4:
            short += f", +{len(stale_labels) - 4} more"
        note = (
            f"Bundle wrapper matches but component(s) behind offer manifest: {short}. "
            "Reinstall the bundle or update individual components."
        )
        return details, "newer", note
    return details, "same", ""


def bundle_components_from_inner_versions(inner_versions: list[dict] | None) -> list[dict]:
    """Normalize OEM ``inner_versions`` entries to bundle component rows."""
    out: list[dict] = []
    for entry in inner_versions or []:
        if not isinstance(entry, dict):
            continue
        ver = (entry.get("version") or "").strip()
        if not ver:
            continue
        name = (
            entry.get("component_name")
            or entry.get("name")
            or entry.get("title")
            or ""
        ).strip()
        label = (entry.get("label") or "").strip()
        if not label:
            label = component_label_from_text(name)
        out.append(
            {
                "label": label,
                "device_name": name or label,
                "version": ver,
            }
        )
    return out


def apply_bundle_status_rollup(
    status: str,
    *,
    installed_components: list[dict] | None,
    offers: list[dict] | None,
    wrapper_status: str | None = None,
) -> tuple[str, list[dict], str]:
    """
    Upgrade device status when bundle components are stale despite wrapper ``same``.

    Returns (final_status, component_compare_detail, compare_note).
    """
    offer_components = best_offer_bundle_components(offers)
    details, rollup, note = compare_bundle_component_sets(
        installed_components,
        offer_components,
    )
    if rollup != "newer":
        return status, details, note
    wrap = (wrapper_status or status or "").lower()
    if wrap in ("same", "none", "uncertain", "unknown"):
        return "newer", details, note
    if wrap == "newer":
        return "newer", details, note
    return status, details, note


def best_offer_bundle_components(offers: list[dict] | None) -> list[dict]:
    """Pick the richest bundle component list from finalized offers."""
    best: list[dict] = []
    for offer in offers or []:
        if not isinstance(offer, dict):
            continue
        cand = offer.get("bundle_components")
        if not isinstance(cand, list) or not cand:
            inner = offer.get("inner_versions") or offer.get("offer_inner_versions")
            if isinstance(inner, list) and inner:
                cand = bundle_components_from_inner_versions(inner)
        if isinstance(cand, list) and len(cand) > len(best):
            best = cand
    return best


def enrich_offers_with_bundle_components(offers: list[dict] | None) -> None:
    """Attach ``bundle_components`` from ``inner_versions`` when missing."""
    for offer in offers or []:
        if not isinstance(offer, dict) or offer.get("bundle_components"):
            continue
        inner = offer.get("inner_versions") or offer.get("offer_inner_versions")
        if isinstance(inner, list) and inner:
            offer["bundle_components"] = bundle_components_from_inner_versions(inner)


def attach_wrapper_row_bundle_rollup(
    result: dict,
    *,
    installed_components: list[dict] | None,
    offers: list[dict] | None,
    device_ctx: dict | None = None,
    wrapper_status: str | None = None,
) -> None:
    """
    Generic wrapper-row hook — enrich offers and attach rollup fields to a comparison dict.

    Used by chipset platform rows and primary GPU rows comparing OEM graphics bundles.
    """
    enrich_offers_with_bundle_components(offers)
    installed = installed_components or []
    offer_components = best_offer_bundle_components(offers)
    if not offer_components or not installed:
        return
    if wrapper_status is None:
        from catalog_offer_status import summarize_offer_status

        wrapper_status = summarize_offer_status(offers, device_ctx=device_ctx)
    rollup_status, detail, rollup_note = apply_bundle_status_rollup(
        wrapper_status or "unknown",
        installed_components=installed,
        offers=offers,
        wrapper_status=wrapper_status,
    )
    result["bundle_offer_components"] = offer_components
    if detail:
        result["bundle_component_compare"] = detail
    if rollup_note:
        result["bundle_compare_note"] = rollup_note
    if rollup_status == "newer":
        result["bundle_status_rollup"] = rollup_status
