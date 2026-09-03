"""Microsoft WU / online store / MSCatalog fetch helpers (extracted from driver_catalog)."""

from __future__ import annotations

from typing import Callable

from catalog_device_context import is_driver_scan_excluded_ctx
from catalog_microsoft_scoring import (
    _iter_online_store_rows_for_ctx,
    _score_catalog_row_for_ctx,
    _score_online_driver_store_row,
)
from catalog_mscatalog_queries import (
    _catalog_search_queries_for_ctx,
    _is_hwid_query,
)
from catalog_none_reason import possible_coverage_gap
from catalog_offer_status import summarize_offer_status
from catalog_row_rejects import (
    _GENERIC_PNP_DEVICE_LABELS,
    _catalog_row_hwid_matches_ctx,
    _prioritize_mscatalog_scored_rows,
    _realtek_catalog_row_is_companion_component,
    _realtek_catalog_row_is_wdm_codec,
    _realtek_device_component_role,
    _realtek_wdm_mscatalog_codec_rows_to_keep,
    _reject_mscatalog_row_for_ctx,
    _reject_realtek_catalog_row,
    _shared_catalog_row_rejects,
)
from catalog_scoring import _looks_like_realtek_wdm_version
from catalog_tier_policy import _is_informational_catalog_offer
from catalog_wu_scoring import _prefilter_wu_rows_for_ctx


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def fetch_microsoft_driver_store_offers(
    ctx: dict,
    *,
    max_results: int = 2,
) -> list[dict]:
    """Match device to Get-WindowsDriver -Online rows (versioned Microsoft catalog)."""
    per_hwid = _dc("_allow_per_hwid_online_store")(ctx)
    bulk_cached = _dc("_peek_online_driver_store_cache")()
    if _dc("_should_skip_online_driver_store")(ctx=ctx) and not per_hwid and not bulk_cached:
        if _dc("_gui_application_mode_active")() and not bulk_cached:
            return [{
                "source": "microsoft",
                "source_label": "Microsoft (Windows driver catalog)",
                "title": "Online catalog scan skipped in GUI",
                "version": "",
                "date": "",
                "url": "ms-settings:windowsupdate-optionalupdates",
                "download_kind": "uri",
                "update_id": "",
                "instance_id": ctx.get("instance_id") or "",
                "notes": (
                    "Get-WindowsDriver -Online -All is not run during GUI scans "
                    "(use Windows Update + MSCatalog for no-HWID devices)."
                ),
                "confidence": "low",
                "informational": True,
            }]
        if not bulk_cached:
            return []
    if per_hwid:
        rows, err = _dc("_get_cached_online_driver_store_for_ctx")(ctx)
        source_note = (
            "Matched via Get-WindowsDriver -Online for this hardware ID "
            "(batched per-HWID lookup)."
        )
    elif bulk_cached:
        rows, err = bulk_cached, ""
        source_note = (
            "Matched from batched Microsoft online driver catalog "
            "(Get-WindowsDriver -Online)."
        )
    else:
        rows, err = _dc("_get_cached_online_driver_store_rows")()
        source_note = (
            "Latest matching package in Microsoft's online driver catalog "
            "(Get-WindowsDriver -Online). Install via Windows Update or Optional updates."
        )
    candidate_rows = rows
    if rows and not per_hwid and _dc("_peek_online_driver_store_cache")():
        subset = _iter_online_store_rows_for_ctx(ctx)
        if subset:
            candidate_rows = subset
    if not rows:
        if err:
            return [{
                "source": "microsoft",
                "source_label": "Microsoft (driver catalog)",
                "title": "Windows online driver catalog unavailable",
                "version": "",
                "date": "",
                "url": "ms-settings:windowsupdate",
                "download_kind": "uri",
                "update_id": "",
                "instance_id": ctx.get("instance_id") or "",
                "notes": err,
                "confidence": "low",
            }]
        return []
    scored: list[tuple[int, dict]] = []
    for row in candidate_rows or rows:
        if _shared_catalog_row_rejects(row, ctx):
            continue
        s = _score_online_driver_store_row(row, ctx)
        if s < 12:
            continue
        scored.append((s, row))
    scored.sort(key=lambda x: -x[0])
    offers: list[dict] = []
    for _, row in scored[:max_results]:
        ver = (row.get("Version") or "").strip()
        title = (row.get("HardwareDescription") or row.get("ProviderName") or "Driver").strip()
        if not title:
            title = f"{row.get('ProviderName', 'Driver')} ({row.get('ClassName', '')})"
        offers.append({
            "source": "microsoft",
            "source_label": "Microsoft (Windows driver catalog)",
            "title": title[:120],
            "version": ver,
            "date": (row.get("Date") or "").strip(),
            "url": "ms-settings:windowsupdate-optionalupdates",
            "download_kind": "uri",
            "update_id": "",
            "instance_id": ctx.get("instance_id") or "",
            "notes": source_note,
            "confidence": "high" if ver else "medium",
        })
    return offers


def _merge_wu_rows_by_update_id(chunks: list[list[dict]]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        for row in chunk:
            if not isinstance(row, dict):
                continue
            uid = (row.get("UpdateId") or row.get("update_id") or "").strip().lower()
            title = (row.get("Title") or row.get("title") or "").strip().lower()
            key = uid or title
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged


def fetch_microsoft_catalog_search_offers(
    ctx: dict,
    *,
    max_results: int = 3,
    cache_only: bool = False,
) -> list[dict]:
    """Query Microsoft Update Catalog via bundled MSCatalogLTS (HWID + name searches)."""
    if not _dc("_v6_catalog_enabled")():
        return []
    if _dc("is_quick_check_mode")():
        return []
    try:
        import catalog_ps_module as cps  # noqa: F401
    except ImportError:
        return []

    _dc("ensure_mscatalog_module_ready")(check_online=False)
    queries = _catalog_search_queries_for_ctx(ctx)
    if not queries:
        return []

    vk = (ctx.get("vendor_key") or "").lower()
    if vk == "realtek":
        max_results = max(max_results, 5)

    scored: list[tuple[int, dict, bool]] = []
    seen_ids: set[str] = set()
    include_preview = _dc("catalog_include_preview_updates")()
    batch_scan = bool(ctx.get("_batch_driver_check"))
    for query in queries:
        rows, err = _dc("_search_mscatalog_updates_cached")(
            query,
            limit=max_results + 2,
            include_preview=include_preview,
            cache_only=cache_only,
        )
        if cache_only and not rows:
            continue
        if err and not rows:
            continue
        query_hwid_hit = False
        for row in rows:
            tier = (row.get("catalog_tier") or "standard").lower()
            if tier == "preview" and not include_preview:
                continue
            uid = (row.get("update_id") or "").lower()
            if uid and uid in seen_ids:
                continue
            if _reject_mscatalog_row_for_ctx(row, ctx, query):
                continue
            hwid_match = _catalog_row_hwid_matches_ctx(row, ctx)
            score = _score_catalog_row_for_ctx(row, ctx, query, hwid_match=hwid_match)
            min_score = 12 if hwid_match else 20
            if score < min_score:
                continue
            if uid:
                seen_ids.add(uid)
            scored.append((score, row, hwid_match))
            if batch_scan and hwid_match and score >= 12:
                query_hwid_hit = True
        if batch_scan and query_hwid_hit:
            break

    if vk == "realtek" and _realtek_device_component_role(ctx) == "wdm":
        wdm_hits = [
            item for item in scored
            if _realtek_catalog_row_is_wdm_codec(item[1]) and item[2]
        ]
        if wdm_hits:
            wdm_ids = {
                (item[1].get("update_id") or "").lower()
                for item in wdm_hits
            }
            scored = wdm_hits + [
                item for item in scored
                if (item[1].get("update_id") or "").lower() not in wdm_ids
                and not _realtek_catalog_row_is_companion_component(item[1])
            ]
        wdm_codec = [
            item for item in scored
            if _realtek_catalog_row_is_wdm_codec(item[1])
            and _looks_like_realtek_wdm_version(item[1].get("version") or "")
        ]
        if wdm_codec:
            kept = _realtek_wdm_mscatalog_codec_rows_to_keep(wdm_codec, ctx)
            kept_ids = {
                (item[1].get("update_id") or "").lower()
                for item in kept
            }
            scored = kept + [
                item for item in scored
                if (item[1].get("update_id") or "").lower() not in kept_ids
            ]

    scored = _prioritize_mscatalog_scored_rows(scored, ctx)

    scored.sort(key=lambda x: -x[0])
    offers: list[dict] = []
    for _, row, hwid_match in scored[:max_results]:
        title = (row.get("title") or "Driver update")[:120]
        ver = (row.get("version") or "").strip()
        uid = (row.get("update_id") or "").strip()
        url = _dc("_microsoft_catalog_url")(title)
        if uid:
            url = _dc("microsoft_catalog_view_url")({"update_id": uid, "url": ""}) or _dc(
                "_microsoft_catalog_url"
            )(title)
        tier = (row.get("catalog_tier") or "standard").lower()
        notes = (
            "Matched via Microsoft Update Catalog search (bundled MSCatalogLTS). "
            "Install manually when ready."
        )
        if tier == "preview":
            notes += " Preview/non-WHQL package — verify before installing."
        elif tier == "whql":
            notes += " WHQL-tagged catalog package."
        offers.append({
            "source": "microsoft",
            "source_label": "Microsoft (Update Catalog)",
            "title": title,
            "version": ver,
            "date": (row.get("date") or "").strip(),
            "url": url,
            "download_kind": "catalog",
            "update_id": uid,
            "instance_id": ctx.get("instance_id") or "",
            "notes": notes,
            "confidence": "high" if ver and hwid_match else ("medium" if ver else "low"),
            "catalog_tier": tier,
            "hwid_matched": hwid_match,
        })
    if vk == "realtek" and _realtek_device_component_role(ctx) == "wdm":
        filtered: list[dict] = []
        for offer in offers:
            probe = {"title": offer.get("title") or "", "version": offer.get("version") or ""}
            if _reject_realtek_catalog_row(probe, ctx):
                continue
            filtered.append(offer)
        offers = filtered
    return offers


def _gap_catalog_name_queries_for_ctx(ctx: dict) -> list[str]:
    """Non-HWID name queries for coverage-gap catalog fallback."""
    probe = dict(ctx)
    probe.pop("_batch_driver_check", None)
    out: list[str] = []
    for q in _catalog_search_queries_for_ctx(probe):
        qs = (q or "").strip()
        if not qs or _is_hwid_query(qs):
            continue
        if qs.lower() in _GENERIC_PNP_DEVICE_LABELS:
            continue
        if qs not in out:
            out.append(qs)
    return out


def _warm_gap_mscatalog_queries(
    queries: list[str], prog: Callable[[str], None]
) -> None:
    """Seed the per-scan cache for gap devices' name queries in one batch."""
    pending = [
        q for q in queries
        if q.strip().lower() not in _dc("_BATCH_MSCATALOG_QUERY_CACHE")
    ]
    if not pending:
        return
    include_preview = _dc("catalog_include_preview_updates")()
    if _dc("_gui_mscatalog_batched_parallel_enabled")() and _dc("_warm_mscatalog_parallel")(
        pending, include_preview, prog
    ):
        return
    for q in pending:
        _dc("_search_mscatalog_updates_cached")(q, limit=8, include_preview=include_preview)


def _augment_gap_devices_with_verified_catalog(
    results: list[dict],
    device_contexts: dict[str, dict],
    progress: Callable[[str], None] | None = None,
) -> None:
    """HWID-verified MSCatalog fallback for zero-offer batch devices."""
    if not _dc("_v6_catalog_enabled")() or _dc("is_quick_check_mode")():
        return
    if not _dc("_gui_gap_catalog_fallback_enabled")():
        return

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    gaps: list[tuple[dict, dict, list[str]]] = []
    for r in results:
        if r.get("offers"):
            continue
        dctx = device_contexts.get(r.get("device_name") or "")
        if not dctx:
            continue
        if "VEN_" not in (dctx.get("instance_id") or "").upper():
            continue
        if is_driver_scan_excluded_ctx(dctx):
            continue
        qs = _gap_catalog_name_queries_for_ctx(dctx)
        if qs:
            gaps.append((r, dctx, qs))
    if not gaps:
        return

    all_queries: list[str] = []
    seen: set[str] = set()
    for _r, _dctx, qs in gaps:
        for q in qs:
            k = q.strip().lower()
            if k and k not in seen:
                seen.add(k)
                all_queries.append(q)

    prog(
        f"Coverage check: verifying {len(gaps)} uncovered device(s) "
        f"against the Microsoft Update Catalog…"
    )
    try:
        _dc("ensure_mscatalog_module_ready")(check_online=False)
        _dc("_warm_gap_mscatalog_queries")(all_queries, prog)
    except Exception:  # noqa: BLE001
        return

    added = 0
    for i, (r, dctx, _qs) in enumerate(gaps, start=1):
        name = (r.get("device_name") or dctx.get("device_label") or "device")[:44]
        prog(f"Coverage check ({i}/{len(gaps)}): {name}…")
        vctx = dict(dctx)
        vctx.pop("_batch_driver_check", None)
        try:
            offers = _dc("fetch_microsoft_catalog_search_offers")(vctx, max_results=2)
        except Exception:  # noqa: BLE001
            continue
        verified = [o for o in offers if o.get("hwid_matched")]
        if not verified:
            continue
        for o in verified:
            note = (o.get("notes") or "").strip()
            o["notes"] = (
                (note + " ") if note else ""
            ) + "Surfaced by coverage-gap check (hardware-ID verified)."
        installed = r.get("installed_version") or "?"
        status = summarize_offer_status(verified)
        r["offers"] = verified
        r["status"] = status
        r["possible_coverage_gap"] = possible_coverage_gap(
            installed, verified, status=status, device_ctx=dctx
        )
        added += 1

    prog(
        f"Coverage check: added {added} hardware-verified catalog match(es)."
        if added
        else "Coverage check: no additional hardware-verified matches found."
    )


def fetch_microsoft_driver_offers(
    ctx: dict,
    max_results: int = 3,
    *,
    prefiltered_rows: list[dict] | None = None,
    allow_catalog_search: bool = True,
    include_informational: bool = False,
    system_ctx: dict | None = None,
) -> list[dict]:
    """Windows Update optional driver updates (COM), scored to this device."""
    if prefiltered_rows is not None:
        data = prefiltered_rows
        err = ""
    else:
        data, err = _dc("_get_cached_wu_driver_rows")(system_ctx)
    if not data:
        offers: list[dict] = []
        if err and include_informational:
            offers.append({
                "source": "microsoft",
                "source_label": "Microsoft (Windows Update)",
                "title": "Could not query Windows Update",
                "version": "",
                "date": "",
                "url": "ms-settings:windowsupdate-optionalupdates",
                "download_kind": "uri",
                "update_id": "",
                "notes": err,
                "confidence": "low",
                "informational": True,
            })
        elif include_informational:
            offers.append({
                "source": "microsoft",
                "source_label": "Microsoft (Windows Update)",
                "title": "No optional driver updates pending",
                "version": "",
                "date": "",
                "url": "ms-settings:windowsupdate-optionalupdates",
                "download_kind": "uri",
                "update_id": "",
                "notes": (
                    "Windows Update reports no pending optional driver packages. "
                    "See Microsoft (Windows driver catalog) for the latest catalog version."
                ),
                "confidence": "medium",
                "informational": True,
            })
        if allow_catalog_search:
            offers.extend(_dc("fetch_microsoft_catalog_search_offers")(ctx))
        for extra in _dc("fetch_microsoft_driver_store_offers")(ctx, max_results=1):
            if _is_informational_catalog_offer(extra) and not include_informational:
                continue
            offers.append(extra)
            break
        return offers

    if prefiltered_rows is not None:
        scored_rows = list(data)[:max_results]
    else:
        scored_rows = _prefilter_wu_rows_for_ctx(data, ctx, max_results=max_results)
    offers = []
    for row in scored_rows:
        ver = (row.get("Version") or "").strip()
        title = (row.get("Title") or "Driver update")[:120]
        offers.append({
            "source": "microsoft",
            "source_label": "Microsoft (Windows Update)",
            "title": title,
            "version": ver,
            "date": (row.get("Date") or "").strip(),
            "url": _dc("_microsoft_catalog_url")(title),
            "download_kind": "catalog",
            "update_id": (row.get("UpdateId") or "").strip(),
            "instance_id": ctx.get("instance_id") or "",
            "wu_offered": True,
            "notes": "Opens Microsoft Update Catalog to download the package; install manually when ready.",
            "confidence": "high" if ver else "medium",
        })
    if not offers and allow_catalog_search and include_informational:
        vk = (ctx.get("vendor_key") or "").strip()
        label = (ctx.get("device_label") or "").strip()
        search_hint = label
        if vk and vk.lower() not in label.lower():
            search_hint = f"{vk} {label}".strip()
        cat_url = _dc("_microsoft_catalog_url")(search_hint[:80] if search_hint else "driver")
        offers.append({
            "source": "microsoft",
            "source_label": "Microsoft (Update Catalog)",
            "title": f"Search catalog: {search_hint[:60]}".strip(),
            "version": "",
            "date": "",
            "url": cat_url,
            "download_kind": "catalog",
            "update_id": "",
            "instance_id": ctx.get("instance_id") or "",
            "notes": "Opens Microsoft Update Catalog — search using the resolved device/vendor name.",
            "confidence": "medium",
            "informational": True,
        })
    for extra in _dc("fetch_microsoft_driver_store_offers")(ctx, max_results=1):
        if _is_informational_catalog_offer(extra) and not include_informational:
            continue
        ev = (extra.get("version") or "").strip()
        if not ev:
            continue
        if any((o.get("version") or "").strip() == ev for o in offers):
            continue
        offers.append(extra)
        break
    if allow_catalog_search:
        for cat in _dc("fetch_microsoft_catalog_search_offers")(ctx, max_results=2):
            ev = (cat.get("version") or "").strip()
            uid = (cat.get("update_id") or "").strip()
            if uid and any((o.get("update_id") or "").strip().lower() == uid.lower() for o in offers):
                continue
            if ev and any((o.get("version") or "").strip() == ev for o in offers):
                continue
            offers.append(cat)
    return offers


__all__ = [
    "_augment_gap_devices_with_verified_catalog",
    "_gap_catalog_name_queries_for_ctx",
    "_merge_wu_rows_by_update_id",
    "_warm_gap_mscatalog_queries",
    "fetch_microsoft_catalog_search_offers",
    "fetch_microsoft_driver_offers",
    "fetch_microsoft_driver_store_offers",
]
