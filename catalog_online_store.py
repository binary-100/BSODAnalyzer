"""Online driver store load gate and storage matching (extracted from driver_catalog)."""

from __future__ import annotations

import re
from typing import Callable

from catalog_mscatalog_session import (
    _get_cached_online_driver_store_rows,
    _peek_online_driver_store_cache,
    _should_skip_online_driver_store,
)
from catalog_scoring import compare_firmware_versions


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def ensure_online_driver_store_loaded(
    progress: Callable[[str], None] | None = None,
) -> tuple[list[dict], str]:
    """Load Get-WindowsDriver -Online cache (shared by all driver/firmware scans)."""
    cached = _peek_online_driver_store_cache()
    if cached:
        return cached, ""
    if _should_skip_online_driver_store():
        return [], ""
    if progress:
        progress("Loading Windows online driver catalog (first check may take 1–2 min)…")
    rows, err = _get_cached_online_driver_store_rows()
    if progress:
        if rows:
            progress(
                f"Windows online driver catalog ready ({len(rows)} package(s))."
            )
        elif err:
            progress(f"Windows online driver catalog unavailable: {err[:100]}")
    return rows, err
def fetch_storage_driver_store_offers(
    model: str,
    installed: str,
    vendor_key: str = "",
) -> list[dict]:
    """Match SSD/storage models against Get-WindowsDriver -Online rows."""
    if _should_skip_online_driver_store():
        return []
    rows, _err = _get_cached_online_driver_store_rows()
    if not rows:
        return []
    tokens = [t for t in re.split(r"[^a-z0-9]+", (model or "").lower()) if len(t) >= 4][:6]
    scored: list[tuple[int, dict]] = []
    vk = (vendor_key or "").lower()
    for row in rows:
        ver = (row.get("Version") or "").strip()
        if not ver:
            continue
        cls = (row.get("ClassName") or "").lower()
        if cls not in ("scsiadapter", "hdc", "diskdrive", ""):
            continue
        desc = (
            (row.get("HardwareDescription") or "")
            + " "
            + (row.get("ProviderName") or "")
        ).lower()
        if not any(k in desc for k in ("ssd", "nvme", "storage", "solid state", "disk")):
            if not tokens:
                continue
        score = 4
        if vk and vk in desc:
            score += 6
        for tok in tokens:
            if tok in desc:
                score += 5
        if score < 10:
            continue
        scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    offers: list[dict] = []
    for _, row in scored[:2]:
        ver = (row.get("Version") or "").strip()
        title = (row.get("HardwareDescription") or model or "Storage")[:120]
        offers.append({
            "source": "microsoft",
            "source_label": "Microsoft (Windows driver catalog)",
            "title": title,
            "version": ver,
            "date": (row.get("Date") or "").strip(),
            "url": "ms-settings:windowsupdate-optionalupdates",
            "download_kind": "uri",
            "update_id": "",
            "notes": (
                "Storage-related package in Microsoft's online driver catalog. "
                "Verify model before installing firmware or storage drivers."
            ),
            "confidence": "medium",
            "installed_model": model,
            "installed_firmware": installed,
            "kind": "ssd",
            "vs_installed": compare_firmware_versions(installed, ver, title=title),
        })
    return offers
