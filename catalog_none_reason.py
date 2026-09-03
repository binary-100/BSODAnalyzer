"""None-reason classification, coverage-gap detection, progress formatting."""

from __future__ import annotations

import driver_version_identity as dvi

from catalog_device_context import (
    _ctx_device_label,
    _ctx_is_amd_chipset_platform_row,
    _ctx_is_chipset_component_plumbing,
    is_driver_scan_excluded_ctx,
)
from catalog_oem_filters import _STANDARD_PNP_MANUFACTURERS
from catalog_offer_pipeline import filter_offers_for_display
from catalog_row_rejects import _GENERIC_PNP_DEVICE_LABELS
from catalog_scoring import (
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    _looks_like_windows_inbox_driver_version,
    compare_versions,
)
from catalog_tier_policy import _is_informational_catalog_offer
from catalog_offer_status import best_authoritative_offer, best_versioned_offer


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def possible_coverage_gap(
    installed: str,
    offers: list[dict] | None,
    *,
    status: str = "",
    device_ctx: dict | None = None,
) -> bool:
    """True when installed beats every catalog offer — search may have missed an update."""
    inst = (installed or "").strip()
    if not inst or inst in ("?", "—", "N/A", "n/a"):
        return False
    st = (status or "").strip().lower()
    if st == "newer":
        return False
    if device_ctx:
        c = device_ctx
        if is_driver_scan_excluded_ctx(c):
            return False
        if _ctx_is_chipset_component_plumbing(c):
            return False
        if _ctx_device_label(c) in _GENERIC_PNP_DEVICE_LABELS:
            return False
        mfr = (
            (c.get("manufacturer") or c.get("driver_provider") or c.get("inf_manufacturer") or "")
            .strip()
            .lower()
        )
        if mfr in _STANDARD_PNP_MANUFACTURERS or "(standard" in mfr:
            return False
        inst_ver = (installed or c.get("primary_version") or "").strip()
        pnp = (c.get("pnp_class") or "").lower()
        if _looks_like_windows_inbox_driver_version(inst_ver) and pnp in (
            "system", "computer", "processor", "monitor", "keyboard", "mouse", "hidclass",
        ):
            return False
    display = filter_offers_for_display(offers or [])
    versioned = [
        o for o in display
        if (_dc("_offer_version_from_fields")(o) or "").strip()
    ]
    if device_ctx and _ctx_is_amd_chipset_platform_row(device_ctx):
        inst_suite = _looks_like_amd_chipset_package_version(inst)
        if inst_suite:
            versioned = [
                o for o in versioned
                if not _looks_like_amd_adrenalin_version(
                    (_dc("_offer_version_from_fields")(o) or "").strip()
                )
            ]
    if not versioned:
        return st in ("none", "unknown", "uncertain", "")
    for o in versioned:
        ver = (_dc("_offer_version_from_fields")(o) or "").strip()
        vs_field = (o.get("vs_installed") or "").lower()
        if vs_field == "uncertain" and ver and compare_versions(inst, ver) == "newer":
            return True
        rel = compare_versions(inst, ver)
        if rel in ("same", "newer"):
            return False
        if dvi.catalog_offer_matches_installed(inst, ver, device_ctx=device_ctx):
            return False
    return True


def classify_none_reason(
    ctx: dict | None,
    offers: list[dict] | None,
    *,
    status: str = "",
) -> str:
    """
    Why a device row ended at status ``none`` — for UI grouping and export diagnostics.

    Returns empty string when status is not a none-class state.
    """
    st = (status or "").strip().lower()
    if st not in ("none", "unknown", ""):
        return ""
    c = dict(ctx or {})
    if is_driver_scan_excluded_ctx(c):
        return "scan_excluded"
    if _ctx_is_chipset_component_plumbing(c):
        return "chipset_component"
    label = _ctx_device_label(c)
    if label in _GENERIC_PNP_DEVICE_LABELS:
        return "standard_device"
    mfr = (
        (c.get("manufacturer") or c.get("driver_provider") or c.get("inf_manufacturer") or "")
        .strip()
        .lower()
    )
    if mfr in _STANDARD_PNP_MANUFACTURERS or "(standard" in mfr:
        return "standard_device"
    inst = (c.get("primary_version") or "").strip()
    pnp = (c.get("pnp_class") or "").lower()
    if _looks_like_windows_inbox_driver_version(inst) and pnp in (
        "system",
        "computer",
        "processor",
        "monitor",
        "keyboard",
        "mouse",
        "hidclass",
        "media",
        "softwaredevice",
    ):
        return "standard_device"
    pool = offers or []
    if pool and all(
        o.get("informational_only") or o.get("status_neutral") or _is_informational_catalog_offer(o)
        for o in pool
    ):
        return "informational_only"
    return "no_match"


def none_reason_display_label(reason: str) -> str:
    """Human label for ``classify_none_reason`` codes."""
    labels = {
        "standard_device": "Standard / inbox",
        "chipset_component": "Chipset component",
        "informational_only": "Reference only",
        "coverage_gap": "No official match — recheck",
        "scan_excluded": "Firmware tab",
        "no_match": "No catalog match",
    }
    return labels.get((reason or "").strip(), "")


def format_device_check_progress(
    name: str,
    entry: dict,
    *,
    done: int | None = None,
    total: int | None = None,
) -> str:
    """One-line per-device result for GUI progress (installed vs catalog)."""
    inst = (entry.get("installed_version") or "?").strip()
    status = (entry.get("status") or "unknown").strip()
    offers = entry.get("offers") or []
    short = (name or "device")[:44]
    if done is not None and total is not None and total > 0:
        prefix = f"Checked {done}/{total}"
    else:
        prefix = "Checked"
    if status == "newer":
        best = best_authoritative_offer(offers)
        if not best:
            best = best_versioned_offer(offers)
        if best:
            ver = _dc("_offer_version_from_fields")(best) or (best.get("version") or "").strip()
            src = (best.get("source_label") or best.get("source") or "").strip()
            if ver:
                extra = f" via {src}" if src else ""
                return f"{prefix} {short}: {inst} → {ver}{extra}"
            title = (best.get("title") or "update")[:40]
            return f"{prefix} {short}: newer — {title}"
        return f"{prefix} {short}: newer package available"
    if status == "same":
        return f"{prefix} {short}: {inst} — up to date"
    if entry.get("error"):
        return f"{prefix} {short}: error — {str(entry['error'])[:48]}"
    if offers:
        srcs: list[str] = []
        for o in offers[:4]:
            s = (o.get("source_label") or o.get("source") or "").strip()
            if s and s not in srcs:
                srcs.append(s)
        tail = f" ({', '.join(srcs[:2])})" if srcs else ""
        ver_offer = best_versioned_offer(offers)
        if ver_offer:
            ver = _dc("_offer_version_from_fields")(ver_offer) or (ver_offer.get("version") or "")
            if ver:
                return f"{prefix} {short}: {inst} — catalog {ver}{tail}"
        return f"{prefix} {short}: {inst} — {len(offers)} offer(s){tail}"
    return f"{prefix} {short}: {inst} — no WU/OEM match"


__all__ = [
    "classify_none_reason",
    "format_device_check_progress",
    "none_reason_display_label",
    "possible_coverage_gap",
]
