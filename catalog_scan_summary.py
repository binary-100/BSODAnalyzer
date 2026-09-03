"""Scan mode summaries and uncertain-offer inspector text (extracted from driver_catalog)."""

from __future__ import annotations

from datetime import datetime

from catalog_mscatalog_session import is_quick_check_mode
from catalog_offer_pipeline import filter_offers_for_display, sort_catalog_offers
from catalog_offer_status import summarize_offer_status


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def build_summary_comparison_from_device_entries(
    device_entries: list[dict],
    *,
    faulting_driver: str | None = None,
) -> dict:
    """Merge per-device scan rows into one Summary-tab comparison payload."""
    offers: list[dict] = []
    installed = "?"
    seen_offer: set[tuple] = set()
    for entry in device_entries or []:
        inst = (entry.get("installed_version") or "").strip()
        if inst and inst not in ("?", "—"):
            installed = inst
        for o in entry.get("offers") or []:
            key = (
                o.get("source"),
                o.get("version"),
                (o.get("title") or "")[:80],
            )
            if key in seen_offer:
                continue
            seen_offer.add(key)
            offers.append(dict(o))
    offers = sort_catalog_offers(offers)
    label = faulting_driver or ""
    if device_entries:
        label = (device_entries[0].get("device_name") or label) or label
    return {
        "device_name": label,
        "installed_version": installed,
        "offers": offers,
        "status": summarize_offer_status(offers),
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
def catalog_scan_mode_summary(
    *,
    full_install: bool = False,
    quick_check: bool | None = None,
    gui_mode: bool = False,
) -> dict[str, str]:
    """Describe active vs skipped catalog sources (E22 — quick vs full scan clarity)."""
    if quick_check is None:
        quick_check = is_quick_check_mode()
    if full_install:
        quick_check = False
    mode = "quick check" if quick_check else "full scan"
    if full_install:
        mode = "full install scan"

    active: list[str] = ["OEM catalog (disk cache + live scrape)"]
    skipped: list[str] = []
    if not quick_check:
        active.append("Microsoft Update Catalog (MSCatalogLTS)")
        active.append("Windows Update optional packages (COM)")
        active.append("Intel / AMD / NVIDIA vendor scrapers")
        active.append(
            "Primary GPU display (NVIDIA/AMD/Intel): manufacturer-only "
            "(OEM + Microsoft skipped for those rows)"
        )
        if _dc("_v6_catalog_enabled")():
            active.append("Extended vendor scrapers (Marvell, Synaptics, …)")
        skipped.append(
            "OEM, WU, and MSCatalog batch queries for primary GPU display devices"
        )
    else:
        skipped.append("Microsoft Update Catalog search")
        skipped.append("Live OEM page scrape (uses session/disk cache only)")

    if gui_mode and _dc("_v6_catalog_enabled")():
        active.append("Per-HWID Get-WindowsDriver -Online (batched warm)")
        skipped.append("Get-WindowsDriver -Online -All during GUI catalog scans")
        skipped.append("Online HWID warm for primary GPU display devices")
    elif gui_mode:
        skipped.append("Get-WindowsDriver -Online -All (disabled in GUI for stability)")
    else:
        active.append("Get-WindowsDriver -Online catalog")

    detail_lines = [
        f"Scan mode: {mode}",
        "",
        "Active sources:",
        *[f"  • {s}" for s in active],
    ]
    if skipped:
        detail_lines.extend(["", "Skipped in this mode:", *[f"  • {s}" for s in skipped]])
    if quick_check and not full_install:
        detail_lines.extend([
            "",
            "Quick check uses cached OEM rows and skips slow live searches. "
            "Turn off Quick check in Settings for a full catalog scan.",
        ])
    elif full_install:
        detail_lines.extend([
            "",
            "Full install mode always runs a complete scan (Quick check is off). "
            "Results are saved to the local driver index.",
        ])
    else:
        detail_lines.extend([
            "",
            "Portable mode: catalog results are session-only unless saved in Settings.",
        ])

    return {
        "mode": mode,
        "short": f"{mode} · {len(active)} source group(s)",
        "detail": "\n".join(detail_lines),
        "active_sources": ", ".join(active[:3]) + ("…" if len(active) > 3 else ""),
        "active_list": list(active),
        "skipped_list": list(skipped),
    }
def build_uncertain_inspector_summary(
    offers: list[dict] | None,
    installed_version: str = "",
    *,
    status: str = "",
) -> str:
    """List every catalog source when version compare is unknown/uncertain (E23)."""
    relevant = filter_offers_for_display(offers or [])
    if not relevant:
        return ""
    st = (status or "").lower()
    uncertain_rows = [
        o
        for o in relevant
        if (o.get("vs_installed") or "").lower() in ("unknown", "uncertain")
    ]
    if st not in ("unknown", "uncertain") and not uncertain_rows:
        return ""
    inst = (installed_version or "").strip() or "?"
    lines = [
        f"Installed: {inst}",
        "Catalog sources found — version compare could not pick a winner:",
        "",
    ]
    show = uncertain_rows if uncertain_rows else relevant
    for i, o in enumerate(show[:12], 1):
        src = o.get("source_label") or o.get("source") or "?"
        ver = _dc("_offer_version_from_fields")(o) or "—"
        vs = (o.get("vs_installed") or "unknown").capitalize()
        note = (o.get("compare_note") or o.get("notes") or "").strip()
        conflict = " [source conflict]" if o.get("source_conflict") else ""
        fresh = (o.get("data_freshness") or "").strip()
        fresh_bit = f" ({fresh})" if fresh else ""
        lines.append(f"{i}. {src}{fresh_bit}: v{ver} → {vs}{conflict}")
        if note:
            lines.append(f"   {note[:200]}")
    return "\n".join(lines)
