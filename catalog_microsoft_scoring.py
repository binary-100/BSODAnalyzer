"""Microsoft online store and MSCatalog row scoring (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_mscatalog_session import (
    _ONLINE_DRIVER_STORE_CLASS_BUCKETS,
    _PNP_TO_STORE_CLASSES,
    _get_cached_online_driver_store_rows,
)
from catalog_row_rejects import (
    _realtek_catalog_row_is_wdm_codec,
    _realtek_device_component_role,
)
from catalog_scoring import _looks_like_realtek_wdm_version, parse_driver_version


def _iter_online_store_rows_for_ctx(ctx: dict) -> list[dict]:
    rows, _err = _get_cached_online_driver_store_rows()
    if not rows:
        return []
    buckets = _ONLINE_DRIVER_STORE_CLASS_BUCKETS
    pnp = (ctx.get("pnp_class") or "").lower()
    if buckets and pnp in _PNP_TO_STORE_CLASSES:
        subset: list[dict] = []
        for cn in _PNP_TO_STORE_CLASSES[pnp]:
            subset.extend(buckets.get(cn, []))
        if subset:
            return subset
    return rows


def _version_plausible_for_ctx(version: str, ctx: dict) -> bool:
    parts = parse_driver_version(version)
    if not parts:
        return False
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp == "display" and vk in ("nvidia", "amd", "intel"):
        if vk == "nvidia" and parts[0] < 27:
            return False
        if vk == "amd" and parts[0] < 20:
            return False
        return len(parts) >= 3
    if pnp in ("net", "media", "bluetooth", "usb", "camera", "scsiadapter"):
        return len(parts) >= 2
    return len(parts) >= 2


def _score_online_driver_store_row(row: dict, ctx: dict) -> int:
    ver = (row.get("Version") or "").strip()
    if not ver or not _version_plausible_for_ctx(ver, ctx):
        return 0
    hw = (row.get("HardwareID") or "").upper()
    desc = (
        (row.get("HardwareDescription") or "")
        + " "
        + (row.get("ProviderName") or "")
    ).upper()
    score = 0
    pci = [t.upper() for t in ctx.get("pci_tokens") or []]
    for token in pci[:4]:
        if token and token in hw:
            score += 10
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    label = (ctx.get("device_label") or "").lower()
    provider = (row.get("ProviderName") or "").lower()
    cls = (row.get("ClassName") or "").lower()
    cls_map = {
        "display": ("display",),
        "net": ("net", "netclient", "nettrans", "netservice"),
        "media": ("media", "audio", "sound"),
        "bluetooth": ("bluetooth",),
        "camera": ("camera", "image"),
        "usb": ("usb", "usbcontroller"),
        "scsiadapter": ("scsiadapter", "hdc", "diskdrive"),
    }
    if pnp in cls_map and cls and cls not in cls_map[pnp]:
        return 0
    if not pnp and cls == "display" and any(
        k in label for k in ("geforce", "radeon", "graphics", "gpu")
    ):
        score += 10
    if vk and vk not in provider and vk not in desc.lower():
        score -= 8
    elif vk and vk in provider:
        score += 8
    if pnp == "display" and cls == "display":
        score += 8
        if vk and vk in provider:
            score += 6
    if pnp == "net" and cls in cls_map["net"]:
        score += 8
    if pnp == "media" and cls in cls_map["media"]:
        score += 8
    if pnp == "bluetooth" and cls in cls_map["bluetooth"]:
        score += 8
    if pnp == "scsiadapter" and cls in cls_map["scsiadapter"]:
        score += 8
    for word in label.split()[:5]:
        if len(word) > 3 and word.upper() in desc:
            score += 3
    return score


def _score_catalog_row_for_ctx(
    row: dict,
    ctx: dict,
    query: str,
    *,
    hwid_match: bool = False,
) -> int:
    title = (row.get("title") or "").lower()
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    score = 0
    if hwid_match:
        score += 24
    if vk and vk in title:
        score += 12
    if query and query.lower() in title:
        score += 8
    inst = (ctx.get("instance_id") or "").upper()
    if inst and "VEN_" in inst:
        ven = re.search(r"VEN_([0-9A-F]{4})", inst)
        dev = re.search(r"DEV_([0-9A-F]{4})", inst)
        if ven and ven.group(1).lower() in title.replace("ven_", ""):
            score += 10
        if dev and dev.group(1).lower() in title.replace("dev_", ""):
            score += 10
    if pnp == "net" and any(k in title for k in ("net", "network", "ethernet", "wireless", "wi-fi", "wlan")):
        score += 6
    if pnp in ("media", "audio") and any(k in title for k in ("audio", "sound", "media")):
        score += 6
    if pnp == "display" and any(k in title for k in ("display", "graphics", "video")):
        score += 6
    if (row.get("version") or "").strip():
        score += 4
    if "driver" in title or (row.get("classification") or "").lower() == "drivers":
        score += 4
    if vk == "realtek":
        role = _realtek_device_component_role(ctx)
        if role == "wdm":
            if _realtek_catalog_row_is_wdm_codec(row):
                score += 14
            if _looks_like_realtek_wdm_version(row.get("version") or ""):
                score += 6
        elif role == "apo" and "audioprocessingobject" in title:
            score += 12
        elif role == "swc" and "softwarecomponent" in title:
            score += 12
        elif role == "net" and any(k in title for k in ("ethernet", "pcie", "2.5gbe", "gbe")):
            score += 10
    return score


__all__ = [
    "_iter_online_store_rows_for_ctx",
    "_score_catalog_row_for_ctx",
    "_score_online_driver_store_row",
    "_version_plausible_for_ctx",
]
