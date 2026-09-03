"""Vendor scrape version cache, cache keys, and batch warm (extracted from driver_catalog)."""

from __future__ import annotations

import re
import threading
import time
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from catalog_device_context import (
    _ctx_device_label,
    _intel_driver_hint_from_ctx,
    _nvidia_ctx_eligible,
)
from catalog_lru_cache import _lru_cache_set, _lru_cache_touch
from catalog_mscatalog_session import _v6_catalog_enabled, is_quick_check_mode
from catalog_scoring import parse_driver_version
from catalog_tier_policy import _NETWORK_VENDOR_KEYS


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_VENDOR_SCRAPE_CACHE: OrderedDict[str, tuple[object, float]] = OrderedDict()
_VENDOR_SCRAPE_TTL_SEC = 900.0
_VENDOR_SCRAPE_MAX_ENTRIES = 128
_VENDOR_SCRAPE_CACHE_LOCK = threading.Lock()


def clear_vendor_scrape_cache() -> None:
    with _VENDOR_SCRAPE_CACHE_LOCK:
        _VENDOR_SCRAPE_CACHE.clear()


def _vendor_scrape_cache_get(key: str):
    with _VENDOR_SCRAPE_CACHE_LOCK:
        hit = _VENDOR_SCRAPE_CACHE.get(key)
        if not hit:
            return None
        val, at = hit
        if (time.monotonic() - at) > _VENDOR_SCRAPE_TTL_SEC:
            _VENDOR_SCRAPE_CACHE.pop(key, None)
            return None
        _lru_cache_touch(_VENDOR_SCRAPE_CACHE, key)
        return val


def _vendor_scrape_cache_set(key: str, val: object) -> None:
    with _VENDOR_SCRAPE_CACHE_LOCK:
        _lru_cache_set(
            _VENDOR_SCRAPE_CACHE,
            key,
            (val, time.monotonic()),
            max_entries=_VENDOR_SCRAPE_MAX_ENTRIES,
        )


def _nvidia_pnp_id_from_ctx(ctx: dict) -> str:
    vc_list = ctx.get("video_controllers") or []
    for vc in vc_list:
        pnp = (vc.get("pnp_device_id") or "").strip()
        if "VEN_10DE" in pnp.upper():
            return pnp
    if ctx.get("pci_tokens"):
        ven = next((t for t in ctx["pci_tokens"] if t.startswith("VEN_")), "")
        dev = next((t for t in ctx["pci_tokens"] if t.startswith("DEV_")), "")
        if ven == "VEN_10DE" and dev:
            return f"PCI\\{ven}&{dev}"
    inst = (ctx.get("instance_id") or "").strip()
    if inst and "VEN_10DE" in inst.upper():
        return inst
    return ""


def _nvidia_vendor_cache_key(ctx: dict) -> str:
    pnp_id = _nvidia_pnp_id_from_ctx(ctx)
    if not pnp_id:
        label = re.sub(r"[^a-z0-9]+", "_", (ctx.get("device_label") or "unknown").lower())[:48]
        return f"nvidia:no-hwid:{label}"
    return f"nvidia:{urllib.parse.quote(pnp_id, safe='')}"


def _amd_vendor_cache_key(ctx: dict) -> str:
    if ctx.get("hw_category") == "chipset":
        return "amd:chipset"
    parts = ["amd", "graphics"]
    family = _dc("_amd_gpu_family_hint")(ctx)
    if family:
        parts.append(re.sub(r"[^a-z0-9]+", "_", family.lower())[:32])
    inst = (ctx.get("instance_id") or "").upper()
    dev = re.search(r"DEV_([0-9A-F]{4})", inst)
    sub = re.search(r"SUBSYS_([0-9A-F]{8})", inst)
    if dev:
        parts.append(dev.group(1).lower())
    if sub:
        parts.append(sub.group(1).lower())
    leaf = _dc("_amd_graphics_product_url")(ctx)
    if leaf:
        slug = leaf.rsplit("/", 1)[-1].replace(".html", "")[:40]
        parts.append(slug)
    if len(parts) == 2:
        label = re.sub(r"[^a-z0-9]+", "_", (ctx.get("device_label") or "generic").lower())[:32]
        parts.append(label)
    return ":".join(parts)


def _warm_vendor_scrapes_for_contexts(
    contexts: list[dict],
    progress: Callable[[str], None] | None = None,
) -> None:
    """Populate vendor version caches once per batch (AMD/Intel/NVIDIA/Realtek/…)."""
    if is_quick_check_mode():
        return

    def prog(msg: str) -> None:
        if progress:
            progress(msg)
    seen: set[str] = set()
    jobs: list[tuple[str, dict, str]] = []
    extended_keys = _dc("_EXTENDED_VENDOR_KEYS")

    def add(vk: str, ctx: dict) -> None:
        if vk == "amd":
            key = _amd_vendor_cache_key(ctx)
        elif vk == "intel":
            hint = _intel_driver_hint_from_ctx(ctx)
            if not hint:
                return
            if hint == "graphics":
                import gpu_vendor_maps as gvm

                bucket = gvm.intel_graphics_bucket_id(
                    _ctx_device_label(ctx),
                    instance_id=(ctx.get("instance_id") or ""),
                )
                key = gvm.intel_graphics_cache_key(bucket)
            else:
                key = f"intel:{hint}"
        elif vk == "nvidia":
            key = _nvidia_vendor_cache_key(ctx)
        elif vk == "realtek" and _v6_catalog_enabled():
            cate, _hint = _dc("_realtek_cate_id_for_ctx")(ctx)
            if cate:
                key = f"realtek:{cate}"
            else:
                return
        elif vk in _NETWORK_VENDOR_KEYS and _v6_catalog_enabled():
            key = _dc("_network_vendor_cache_key")(ctx)
            if not key:
                return
        elif vk in extended_keys and _v6_catalog_enabled():
            key = _dc("_extended_vendor_cache_key")(ctx)
            if not key:
                return
        else:
            return
        if key in seen or _vendor_scrape_cache_get(key) is not None:
            return
        seen.add(key)
        jobs.append((vk, ctx, key))

    for ctx in contexts:
        if _nvidia_ctx_eligible(ctx):
            add("nvidia", ctx)
            continue
        vk = (ctx.get("vendor_key") or "").lower()
        if vk in ("amd", "intel") or (
            vk == "realtek" and _v6_catalog_enabled()
        ) or (vk in _NETWORK_VENDOR_KEYS and _v6_catalog_enabled()) or (
            vk in extended_keys and _v6_catalog_enabled()
        ):
            add(vk, ctx)

    if not jobs:
        return

    prog(
        f"Manufacturer sources: pre-warming {len(jobs)} vendor lookup(s) "
        f"(AMD/Intel/NVIDIA/Realtek/…)…"
    )

    def _warm_one(vk: str, ctx: dict, key: str) -> None:
        if vk == "amd":
            ver, _ = _dc("_scrape_amd_driver_version")(ctx)
            _vendor_scrape_cache_set(key, (ver, ""))
        elif vk == "intel":
            hint = _intel_driver_hint_from_ctx(ctx)
            if not hint:
                return
            ver, date, page_url, direct_url = _dc("_intel_scrape_result_parts")(
                _dc("_scrape_intel_driver_version")(hint, ctx=ctx)
            )
            if hint == "graphics":
                import gpu_vendor_maps as gvm

                bucket = gvm.intel_graphics_bucket_id(
                    _ctx_device_label(ctx),
                    instance_id=(ctx.get("instance_id") or ""),
                )
                key = gvm.intel_graphics_cache_key(bucket)
            else:
                key = f"intel:{hint}"
            _vendor_scrape_cache_set(key, (ver, date, page_url, direct_url))
        elif vk == "nvidia":
            _dc("fetch_nvidia_driver_offer")(ctx)
        elif vk == "realtek":
            cate, _hint = _dc("_realtek_cate_id_for_ctx")(ctx)
            if cate:
                rows = _dc("_scrape_realtek_category_rows")(cate)
                if rows:
                    best = max(
                        rows,
                        key=lambda r: parse_driver_version(r.get("version") or "") or (),
                    )
                    _vendor_scrape_cache_set(
                        f"realtek:{cate}",
                        (best.get("version") or "", best.get("date") or "", best),
                    )
        elif vk in _NETWORK_VENDOR_KEYS:
            offers = _dc("fetch_network_vendor_offers")(ctx)
            cache_key = _dc("_network_vendor_cache_key")(ctx)
            if cache_key and offers:
                best = offers[0]
                _vendor_scrape_cache_set(
                    cache_key,
                    (best.get("version") or "", best.get("date") or "", best),
                )
        elif vk in extended_keys:
            offers = _dc("fetch_extended_vendor_offers")(ctx)
            cache_key = _dc("_extended_vendor_cache_key")(ctx)
            if cache_key and offers:
                best = offers[0]
                _vendor_scrape_cache_set(
                    cache_key,
                    (best.get("version") or "", best.get("date") or "", best),
                )

    with ThreadPoolExecutor(max_workers=min(3, len(jobs))) as ex:
        futs = [ex.submit(_warm_one, vk, ctx, key) for vk, ctx, key in jobs]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as exc:
                _dc("_log_catalog_skip")("vendor warm task", exc)


__all__ = [
    "_VENDOR_SCRAPE_CACHE",
    "_VENDOR_SCRAPE_MAX_ENTRIES",
    "_VENDOR_SCRAPE_TTL_SEC",
    "_amd_vendor_cache_key",
    "_nvidia_pnp_id_from_ctx",
    "_nvidia_vendor_cache_key",
    "_vendor_scrape_cache_get",
    "_vendor_scrape_cache_set",
    "_warm_vendor_scrapes_for_contexts",
    "clear_vendor_scrape_cache",
]
