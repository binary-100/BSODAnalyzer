"""Catalog offer enrich/sort/filter pipeline (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_scoring import compare_firmware_versions, compare_versions


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def _finalize_catalog_offers(
    offers: list[dict],
    installed: str,
    *,
    device_ctx: dict | None = None,
    installed_date: str = "",
) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for o in offers:
        key = (o.get("source"), o.get("version"), o.get("title"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(o)
    dctx = device_ctx or {}
    idate = installed_date or _installed_driver_date_from_ctx(dctx)
    unique = enrich_offers_with_comparison(
        unique,
        installed,
        idate,
        device_ctx=device_ctx,
    )
    unique = resolve_uncertain_catalog_offers(
        unique,
        installed,
        installed_date=idate,
        device_ctx=dctx,
    )
    unique = annotate_offer_source_conflicts(unique)
    unique = sort_catalog_offers(unique)
    return filter_offers_for_display(unique)

_STATUS_RANK = {
    "newer": 0,
    "same": 1,
    "uncertain": 2,
    "older": 3,
    "unknown": 4,
    "n/a": 5,
    "none": 6,
    "error": 7,
}

def offer_source_sort_tier(source: str | None) -> int:
    """Package list order: device manufacturer → OEM → Microsoft (matches Action Plan)."""
    s = (source or "").lower()
    if s in ("vendor", "ssd_vendor", "utility"):
        return 0
    if s in ("oem", "oem_firmware"):
        return 1
    if s == "microsoft":
        return 2
    return 3

def _installed_driver_date_from_ctx(ctx: dict) -> str:
    for row in ctx.get("installed_rows") or []:
        d = (row.get("date") or "").strip()
        if d:
            return d
    vcs = ctx.get("video_controllers") or []
    label = (ctx.get("device_label") or "").lower()
    for vc in vcs:
        if not isinstance(vc, dict):
            continue
        dd = (vc.get("driver_date") or "").strip()
        if not dd:
            continue
        vc_name = (vc.get("name") or "").lower()
        if label and vc_name and (label in vc_name or vc_name in label):
            return dd
    if vcs and isinstance(vcs[0], dict):
        return (vcs[0].get("driver_date") or "").strip()
    return ""

def sort_catalog_offers(offers: list[dict]) -> list[dict]:
    """Sort offers: newer packages first, installable links, then manufacturer → OEM → Microsoft."""
    return sorted(
        offers,
        key=lambda x: (
            _STATUS_RANK.get((x.get("vs_installed") or "unknown").lower(), 99),
            _offer_installability_rank(x),
            offer_source_sort_tier(x.get("source")),
            (x.get("source_label") or "").lower(),
            (x.get("title") or "").lower(),
        ),
    )

def _offer_installability_rank(offer: dict) -> int:
    """Lower rank = more likely to install directly (direct package or resolvable vendor URL)."""
    if offer.get("install_verified") or offer.get("download_resolvable"):
        return 0
    kind = _dc('_offer_download_kind')(offer).lower()
    if kind in ("cab", "package", "direct", "optional_updates", "uri", "catalog"):
        return 0
    url = (offer.get("url") or "").strip().lower()
    path = url.split("?")[0]
    if any(path.endswith(ext) for ext in _dc('_DOWNLOAD_EXTENSIONS')):
        return 1
    if "todownload" in url or "downloadmirror.intel.com" in url:
        return 2
    if "intel.com" in url and "/download/" in url:
        return 3
    if (offer.get("source") or "").lower() == "microsoft" and offer.get("update_id"):
        return 1
    return 4

_UNVERIFIED_NEWER_NOTE = (
    "A newer version was found but no verified installer download is attached — "
    "use Microsoft Update Catalog, OEM packages, or the vendor auto-detect tool "
    "before installing."
)

_SAME_WITHOUT_VERSION_NOTE = (
    "Package sameness could not be confirmed — this offer has no comparable version."
)

def _append_compare_note(note: str, extra: str) -> str:
    note = (note or "").strip()
    extra = (extra or "").strip()
    if not extra:
        return note
    if extra in note:
        return note
    return f"{note} {extra}".strip() if note else extra

def resolve_uncertain_catalog_offers(
    offers: list[dict],
    installed: str,
    *,
    installed_date: str = "",
    device_ctx: dict | None = None,
) -> list[dict]:
    """
    Second-pass verification — try to resolve uncertain rows instead of leaving them stuck.

    Uses install-path probing, cross-source version consensus, version-identity maps,
    and alternate installed baselines (suite vs component, branch vs internal, …).
    """
    if not offers:
        return []
    pool = list(offers)
    resolved: list[dict] = []
    for row in pool:
        updated = _dc('_try_resolve_uncertain_offer')(
            row,
            pool,
            installed,
            installed_date,
            device_ctx,
        )
        resolved.append(updated)
    return resolved

def filter_offers_for_display(offers: list[dict] | None) -> list[dict]:
    """Drop older packages and informational Microsoft placeholder rows."""
    return [
        o
        for o in (offers or [])
        if (
            (o.get("vs_installed") or "").lower() != "older"
            or o.get("reference_older_oem")
        )
        and not _dc('_is_informational_catalog_offer')(o)
    ]

def annotate_offer_source_conflicts(offers: list[dict]) -> list[dict]:
    """Mark OEM vs Microsoft rows when both publish different version strings (D20)."""
    oem_versions: list[str] = []
    ms_versions: list[str] = []
    for o in offers or []:
        src = (o.get("source") or "").lower()
        if src == "oem" and o.get("status_neutral"):
            continue
        ver = _dc('_offer_version_from_fields')(o)
        if not ver:
            continue
        if src == "oem":
            oem_versions.append(ver)
        elif src == "microsoft":
            ms_versions.append(ver)
    if not oem_versions or not ms_versions:
        return list(offers or [])
    conflict = False
    for ov in oem_versions:
        for mv in ms_versions:
            if compare_versions(ov, mv) not in ("same", "unknown"):
                conflict = True
                break
        if conflict:
            break
    if not conflict:
        return list(offers or [])
    note = (
        "OEM and Microsoft catalog list different package versions — both are shown. "
        "Prefer OEM for model-specific WHQL; use Microsoft for generic HWID matches."
    )
    out: list[dict] = []
    for o in offers or []:
        row = dict(o)
        src = (row.get("source") or "").lower()
        if src == "oem" and row.get("status_neutral"):
            out.append(row)
            continue
        if src in ("oem", "microsoft") and _dc('_offer_version_from_fields')(row):
            row["source_conflict"] = True
            existing = (row.get("compare_note") or "").strip()
            if note not in existing:
                row["compare_note"] = f"{existing} {note}".strip() if existing else note
        out.append(row)
    return out

def offer_source_conflict_summary(offers: list[dict] | None) -> str:
    """One-line banner when OEM and Microsoft versions disagree."""
    flagged = [o for o in (offers or []) if o.get("source_conflict")]
    if not flagged:
        return ""
    oem = next(
        (o for o in flagged if (o.get("source") or "").lower() == "oem"),
        None,
    )
    ms = next(
        (o for o in flagged if (o.get("source") or "").lower() == "microsoft"),
        None,
    )
    if oem and ms:
        ov = _dc('_offer_version_from_fields')(oem) or "?"
        mv = _dc('_offer_version_from_fields')(ms) or "?"
        return (
            f"Source conflict: OEM v{ov} vs Microsoft v{mv} — "
            "compare both packages before installing."
        )
    return (
        "Source conflict: OEM and Microsoft catalog disagree on version — "
        "compare both packages before installing."
    )

def enrich_offers_with_comparison(
    offers: list[dict],
    installed_version: str,
    installed_date: str = "",
    *,
    device_ctx: dict | None = None,
) -> list[dict]:
    inst = (installed_version or "").strip()
    inst_date = (installed_date or "").strip()
    out = []
    for o in offers:
        row = dict(o)
        cand = _dc('_offer_version_from_fields')(row)
        probe = (
            cand
            and (row.get("source") or "").lower() in ("vendor", "oem", "ssd_vendor")
            and not _dc('_offer_has_installable_package')(row)
        )
        row = _dc('_recompare_offer_row')(
            row,
            inst,
            inst_date,
            device_ctx=device_ctx,
            probe_install=bool(probe),
        )
        out.append(row)
    return out

def enrich_firmware_offers_with_comparison(
    offers: list[dict],
    installed_version: str,
    installed_date: str = "",
) -> list[dict]:
    inst = (installed_version or "").strip()
    inst_date = (installed_date or "").strip()
    out: list[dict] = []
    for o in offers:
        row = dict(o)
        if row.get("coverage_check_failed"):
            row["vs_installed"] = "uncertain"
            row["installed_version"] = inst or "?"
            row["installed_date"] = inst_date
            out.append(row)
            continue
        cand = _dc('_offer_version_from_fields')(row)
        if cand:
            row["version"] = cand
        vs = compare_firmware_versions(
            inst,
            cand,
            title=(row.get("title") or ""),
        )
        row["vs_installed"] = vs
        if vs == "unknown":
            row["compare_note"] = (
                row.get("compare_note")
                or "Firmware version formats differ — compare manually on the vendor site."
            )
        row["installed_version"] = inst or "?"
        row["installed_date"] = inst_date
        out.append(row)
    return out

def finalize_catalog_offers(
    offers: list[dict],
    installed_version: str,
    installed_date: str = "",
    *,
    firmware: bool = False,
) -> list[dict]:
    """Enrich, annotate OEM/Microsoft conflicts, sort, and filter for display."""
    if firmware:
        enriched = enrich_firmware_offers_with_comparison(
            offers, installed_version, installed_date
        )
    else:
        enriched = enrich_offers_with_comparison(
            offers, installed_version, installed_date, device_ctx=None
        )
    enriched = annotate_offer_source_conflicts(enriched)
    enriched = sort_catalog_offers(enriched)
    return filter_offers_for_display(enriched)
