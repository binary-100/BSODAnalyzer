"""Microsoft Update Catalog search query builders (from driver_catalog)."""

from __future__ import annotations

import re

from catalog_device_context import _device_is_intel_me_device
from catalog_oem_live import _oem_search_keywords
from catalog_realtek_queries import _realtek_uad_catalog_queries
from catalog_row_rejects import _GENERIC_PNP_DEVICE_LABELS


def _catalog_search_queries_for_ctx(ctx: dict) -> list[str]:
    """Build HWID- and name-based Microsoft Update Catalog search strings."""
    if ctx.get("catalog_skip_mscatalog"):
        return []
    queries: list[str] = []
    inst = (ctx.get("instance_id") or "").strip()
    if inst:
        queries.append(inst)
        u = inst.upper()
        ven = re.search(r"VEN_([0-9A-F]{4})", u)
        dev = re.search(r"DEV_([0-9A-F]{4})", u)
        sub = re.search(r"SUBSYS_([0-9A-F]{8})", u)
        rev = re.search(r"REV_([0-9A-F]{2})", u)
        if ven and dev:
            base = f"PCI\\VEN_{ven.group(1)}&DEV_{dev.group(1)}"
            queries.append(base)
            if sub:
                queries.append(f"{base}&SUBSYS_{sub.group(1)}")
            if rev:
                queries.append(f"{base}&REV_{rev.group(1)}")
    label = (ctx.get("device_label") or ctx.get("target_device_name") or "").strip()
    vk = (ctx.get("vendor_key") or "").strip()
    label_l = label.lower()
    if label and label_l not in _GENERIC_PNP_DEVICE_LABELS:
        queries.append(label)
    if vk and vk.lower() not in label.lower():
        vk_query = f"{vk} {label}".strip()
        if vk_query.lower() not in _GENERIC_PNP_DEVICE_LABELS:
            queries.append(vk_query)
    for kw in _oem_search_keywords(ctx)[:3]:
        if kw and kw not in queries:
            queries.append(kw)
    if (ctx.get("vendor_key") or "").lower() == "realtek":
        for q in _realtek_uad_catalog_queries(ctx):
            if q not in queries:
                queries.append(q)
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        q = q.strip()
        if not q or q in seen:
            continue
        seen.add(q)
        out.append(q[:120])
    cap = 10 if (ctx.get("vendor_key") or "").lower() == "realtek" else 5
    out = out[:cap]
    if ctx.get("_batch_driver_check"):
        return _batch_mscatalog_queries_for_ctx(ctx, out)
    return out


def _is_hwid_query(q: str) -> bool:
    """True for raw hardware-ID search strings (PCI\\…, HDAUDIO\\…, VEN_…).

    Thin wrapper over the canonical ``catalog_ps_module.is_hwid_search`` so the
    HWID definition lives in exactly one place.
    """
    import catalog_ps_module as cps

    return cps.is_hwid_search(q)


def _intel_mscatalog_queries(ctx: dict) -> list[str]:
    """Name-based MSCatalog searches for legacy Intel Wi‑Fi / BT / ME rows."""
    label = (ctx.get("device_label") or ctx.get("target_device_name") or "").strip()
    label_l = label.lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    queries: list[str] = []
    if pnp == "net" or any(k in label_l for k in ("wi-fi", "wifi", "wireless", "wlan")):
        queries.extend([
            "Intel Wireless WiFi",
            "Intel Wi-Fi driver",
            "Intel PROSet Wireless",
        ])
    elif pnp == "bluetooth" or "bluetooth" in label_l:
        queries.extend([
            "Intel Wireless Bluetooth",
            "Intel Bluetooth driver",
        ])
    elif _device_is_intel_me_device(ctx):
        queries.extend(["Intel Management Engine", "Intel ME driver"])
    if label and label_l not in _GENERIC_PNP_DEVICE_LABELS:
        queries.append(label)
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        qn = q.strip()
        if not qn or qn.lower() in seen:
            continue
        seen.add(qn.lower())
        out.append(qn[:120])
    return out[:4]


def _mediatek_mscatalog_queries(ctx: dict) -> list[str]:
    """Name-based MSCatalog searches when PCI HWID queries return no MediaTek rows."""
    label = (ctx.get("device_label") or ctx.get("target_device_name") or "").strip()
    label_l = label.lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    queries: list[str] = []
    if pnp == "net" or any(
        k in label_l for k in ("wi-fi", "wifi", "wireless", "wlan", "mt792", "mt790")
    ):
        queries.extend([
            "MediaTek, Inc. Driver Update",
            "MT7921 22H2",
            "MediaTek, Inc. - Net",
        ])
    if label and label_l not in _GENERIC_PNP_DEVICE_LABELS:
        queries.append(label)
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        qn = q.strip()
        if not qn or qn.lower() in seen:
            continue
        seen.add(qn.lower())
        out.append(qn[:120])
    return out[:4]


def _batch_mscatalog_queries_for_ctx(ctx: dict, queries: list[str]) -> list[str]:
    """Fewer MSCatalog PS searches during GUI batch scan (one HWID query when possible)."""
    vk = (ctx.get("vendor_key") or "").lower()
    if vk == "realtek":
        pnp = (ctx.get("pnp_class") or "").lower()
        if pnp == "net":
            return queries[:3]
        # Realtek audio codec/APO/SWC components are HDAUDIO, not PCI — a PCI HWID
        # query returns nothing. Critically, the packaged UAD/MEDIA build (e.g. the
        # newer 6.0.99xx.1 codec driver) is ONLY returned by the targeted UAD
        # searches ("Realtek Media <year>", "Realtek High Definition Audio Driver",
        # …) — NOT by the generic label/keyword searches ("Realtek Audio", "audio",
        # "sound"), which return unrelated rows. Taking the first few name queries
        # therefore fired 3 slow searches that could never match while dropping the
        # two that do, so the newer audio driver went missing. Prefer the UAD
        # queries (with the device label as a secondary) and drop the bare keywords.
        uad = _realtek_uad_catalog_queries(ctx)
        label = (ctx.get("device_label") or ctx.get("target_device_name") or "").strip()
        ordered: list[str] = []
        for q in uad + ([label] if label else []):
            q = (q or "").strip()
            if q and q not in ordered and not _is_hwid_query(q):
                ordered.append(q)
        if ordered:
            return ordered[:4]
        name_qs = [q for q in queries if not _is_hwid_query(q)]
        if name_qs:
            return name_qs[:3]
        return queries[:1]
    vk = (ctx.get("vendor_key") or "").lower()
    if vk == "intel":
        intel_q = _intel_mscatalog_queries(ctx)
        if intel_q:
            hwid_q = [q for q in queries if _is_hwid_query(q)]
            ordered: list[str] = []
            for q in hwid_q[:1] + intel_q:
                if q not in ordered:
                    ordered.append(q)
            return ordered[:4]
    if vk == "mediatek":
        mtk_q = _mediatek_mscatalog_queries(ctx)
        if mtk_q:
            hwid_q = [q for q in queries if _is_hwid_query(q)]
            ordered: list[str] = []
            for q in hwid_q[:1] + mtk_q:
                if q not in ordered:
                    ordered.append(q)
            return ordered[:4]
    inst = (ctx.get("instance_id") or "").strip().upper()
    if inst and "VEN_" in inst:
        ven = re.search(r"(VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4})", inst)
        if ven:
            base = f"PCI\\{ven.group(1)}"
            if base in queries:
                return [base]
            sub = re.search(
                r"(VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4}&SUBSYS_[0-9A-F]{8})",
                inst,
            )
            if sub:
                full = f"PCI\\{sub.group(1)}"
                return [full] if full in queries else [queries[0]]
        return [queries[0]]
    for q in queries:
        if q.strip():
            return [q.strip()]
    return queries[:1]

__all__ = [
    "_batch_mscatalog_queries_for_ctx",
    "_catalog_search_queries_for_ctx",
    "_intel_mscatalog_queries",
    "_is_hwid_query",
    "_mediatek_mscatalog_queries",
]
