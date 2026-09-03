"""Extended/peripheral vendor fetch — Marvell, Synaptics, Elan, peripherals (extracted from driver_catalog)."""

from __future__ import annotations

import re
import urllib.parse

from catalog_scoring import parse_driver_version


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


EXTENDED_VENDOR_KEYS = frozenset({
    "marvell", "synaptics", "elan", "logitech", "samsung", "tplink", "netgear",
})
# Re-export alias used across driver_catalog and vendor cache.
_EXTENDED_VENDOR_KEYS = EXTENDED_VENDOR_KEYS

_MARVELL_SUPPORT = "https://www.marvell.com/support/downloads.html"
_MARVELL_DEV_HINT: dict[str, str] = {
    "9130": "storage", "9230": "storage", "9170": "storage", "9172": "storage",
    "9174": "storage", "9176": "storage", "9178": "storage", "9180": "storage",
    "9182": "storage", "9183": "storage", "9184": "storage", "9185": "storage",
    "4360": "network", "4361": "network", "4362": "network", "4363": "network",
    "4364": "network", "4365": "network", "4366": "network", "4367": "network",
    "4368": "network", "4369": "network", "4370": "network", "4371": "network",
    "4372": "network", "4373": "network", "4374": "network", "4375": "network",
    "4376": "network", "4377": "network", "4378": "network", "4379": "network",
    "437a": "network", "437b": "network", "437c": "network", "437d": "network",
    "437e": "network", "437f": "network", "4380": "network", "4381": "network",
    "4382": "network",
}


def _extended_vendor_cache_key(ctx: dict) -> str | None:
    vk = (ctx.get("vendor_key") or "").lower()
    if vk not in _EXTENDED_VENDOR_KEYS:
        return None
    label = (ctx.get("device_label") or "").lower()
    if vk == "marvell":
        return f"marvell:{_marvell_product_kind(ctx)}"
    if vk in ("synaptics", "elan"):
        return f"{vk}:input"
    model = _peripheral_model_hint(label)
    if vk in ("logitech", "samsung", "tplink", "netgear"):
        return f"{vk}:{model or 'generic'}"
    return f"{vk}:generic"


def _marvell_product_kind(ctx: dict) -> str:
    label = (ctx.get("device_label") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    inst = (ctx.get("instance_id") or "").upper()
    dev_m = re.search(r"DEV_([0-9A-F]{4})", inst)
    if dev_m:
        kind = _MARVELL_DEV_HINT.get(dev_m.group(1).lower())
        if kind:
            return kind
    if pnp in ("hdc", "scsi") or any(k in label for k in ("nvme", "raid", "sata", "9215", "9230")):
        return "storage"
    if pnp == "net" or any(k in label for k in ("yukon", "fastlinq", "avastar", "ethernet")):
        return "network"
    return "generic"


def _peripheral_model_hint(label: str) -> str:
    text = label or ""
    for pat in (
        r"\b(Archer\s*[A-Z0-9-]+|TL-WN[A-Z0-9-]+|TX[A-Z0-9-]+|Deco\s*[A-Z0-9-]+)\b",
        r"\b(MX[\s-]?\w+|G\d{3,4}|PRO\s*\w+|Hero\s*\w*|Lightspeed)\b",
        r"\b(SLC\d{2,4}|SP\d{3,4}|LC\d{2,4}|Odyssey\s*[A-Z0-9-]+)\b",
        r"\b(R\d{2,4}|Nighthawk\s*[A-Z0-9-]+|Orbi\s*[A-Z0-9-]+)\b",
    ):
        m = re.search(pat, text, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _peripheral_support_url(vendor_key: str, label: str) -> tuple[str, str]:
    vk = vendor_key.lower()
    model = _peripheral_model_hint(label)
    default_url, default_title = _dc("_VENDOR_DRIVER_URLS").get(
        vk, ("", f"{vk.title()} support"),
    )
    if vk == "tplink" and model:
        q = urllib.parse.quote(model)
        return (
            f"https://www.tp-link.com/us/search/?q={q}",
            f"TP-Link {model} — downloads",
        )
    if vk == "netgear" and model:
        q = urllib.parse.quote(model)
        return (
            f"https://www.netgear.com/support/search/?q={q}",
            f"NETGEAR {model} — support",
        )
    if vk == "logitech" and model:
        q = urllib.parse.quote(model)
        return (
            f"https://support.logi.com/hc/en-us/search?query={q}",
            f"Logitech {model} — software",
        )
    if vk == "samsung" and model:
        q = urllib.parse.quote(model)
        return (
            f"https://www.samsung.com/us/search/?searchterm={q}",
            f"Samsung {model} — support",
        )
    return default_url, default_title


def _scrape_marvell_support_versions(kind: str) -> list[dict]:
    from catalog_mscatalog_session import is_quick_check_mode

    if is_quick_check_mode():
        return []
    ok, html = _dc("_vendor_http_get_robust")(_MARVELL_SUPPORT, referer="https://www.marvell.com/")
    if not ok:
        return []
    import vendor_extractors as vex

    keywords = (
        ("storage", ("nvme", "raid", "sata", "hba", "9215", "9230")),
        ("network", ("yukon", "avastar", "ethernet", "fastlinq", "nic")),
    )
    keys = next((kws for tag, kws in keywords if tag == kind), ("marvell",))
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in vex.extract_bundled_rows("marvell", html or ""):
        title = (r.get("title") or "")[:120]
        ver = (r.get("version") or "").strip()
        tl = title.lower()
        if not any(k in tl for k in keys):
            continue
        key = (title, ver)
        if key in seen or not ver:
            continue
        seen.add(key)
        rows.append({"title": title, "version": ver, "url": _MARVELL_SUPPORT})
    return rows


def fetch_marvell_driver_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "marvell":
        return []
    kind = _marvell_product_kind(ctx)
    rows = _dc("_scrape_marvell_support_versions")(kind)
    if rows:
        best = max(rows, key=lambda r: parse_driver_version(r.get("version") or "") or ())
        return [_dc("_vendor_offer_row")(
            vendor_key="marvell",
            title=best.get("title") or f"Marvell {kind} driver",
            version=best.get("version") or "",
            url=best.get("url") or _MARVELL_SUPPORT,
            notes=(
                f"Marvell {kind} package from Marvell support downloads. "
                "Many Marvell NIC/storage drivers also appear in Microsoft Update Catalog — compare above."
            ),
            confidence="medium" if best.get("version") else "low",
        )]
    url, title = _dc("_VENDOR_DRIVER_URLS").get("marvell", (_MARVELL_SUPPORT, "Marvell drivers"))
    return [_dc("_vendor_offer_row")(
        vendor_key="marvell",
        title=f"{title} ({kind})",
        url=url,
        notes=(
            "Marvell does not expose a stable public API. Use Microsoft Update Catalog "
            "HWID results first, then Marvell or your PC maker for Yukon/FastLinQ "
            "Ethernet or storage HBA packages."
        ),
        confidence="low",
    )]


def fetch_synaptics_driver_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "synaptics":
        return []
    url, title = _dc("_VENDOR_DRIVER_URLS").get(
        "synaptics",
        ("https://www.synaptics.com/products/touchpad-driver", "Synaptics touchpad"),
    )
    label = (ctx.get("device_label") or "").lower()
    if "clickpad" in label or "touchpad" in label:
        title = "Synaptics ClickPad / touchpad driver"
    return [_dc("_vendor_offer_row")(
        vendor_key="synaptics",
        title=title,
        url=url,
        notes=(
            "Synaptics touchpad drivers are usually shipped via laptop OEM packages. "
            "Compare Microsoft catalog and your PC maker's site; Synaptics.com hosts "
            "reference packages for some models only."
        ),
        confidence="low",
    )]


def fetch_elan_driver_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "elan":
        return []
    url, title = _dc("_VENDOR_DRIVER_URLS").get(
        "elan",
        ("http://www.emtouch.elan.com/Download%20Driver.html", "ELAN touchpad"),
    )
    return [_dc("_vendor_offer_row")(
        vendor_key="elan",
        title=title,
        url=url,
        notes=(
            "ELAN touchpad drivers are typically OEM-specific. Use your laptop maker's "
            "support site or Microsoft Update Catalog; ELAN's portal lists generic packages."
        ),
        confidence="low",
    )]


def fetch_logitech_driver_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "logitech":
        return []
    label = ctx.get("device_label") or ctx.get("device_name") or ""
    if _dc("_is_logitech_virtual_driver_noise")(label):
        return []
    url, title = _peripheral_support_url("logitech", label)
    return [_dc("_vendor_offer_row")(
        vendor_key="logitech",
        title=title,
        url=url,
        notes=(
            "Logitech ships drivers through Logi Options+ / G HUB per product line. "
            "Open the product-specific support page — version compare is often N/A "
            "(utility-managed updates)."
        ),
        confidence="low",
    )]


def fetch_samsung_peripheral_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "samsung":
        return []
    label = ctx.get("device_label") or ""
    url, title = _peripheral_support_url("samsung", label)
    return [_dc("_vendor_offer_row")(
        vendor_key="samsung",
        title=title,
        url=url,
        notes=(
            "Samsung monitors, printers, and accessories use product-specific support pages. "
            "Compare Windows Update optional drivers when available."
        ),
        confidence="low",
    )]


def fetch_tplink_driver_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "tplink":
        return []
    label = ctx.get("device_label") or ""
    url, title = _peripheral_support_url("tplink", label)
    return [_dc("_vendor_offer_row")(
        vendor_key="tplink",
        title=title,
        url=url,
        notes=(
            "TP-Link USB Wi‑Fi and Ethernet adapters publish drivers on tp-link.com by model. "
            "Search Microsoft Update Catalog by HWID when the model page has no Windows 11 package."
        ),
        confidence="low",
    )]


def fetch_netgear_driver_offers(ctx: dict) -> list[dict]:
    if not _dc("_v6_catalog_enabled")() or (ctx.get("vendor_key") or "").lower() != "netgear":
        return []
    label = ctx.get("device_label") or ""
    url, title = _peripheral_support_url("netgear", label)
    return [_dc("_vendor_offer_row")(
        vendor_key="netgear",
        title=title,
        url=url,
        notes=(
            "NETGEAR USB Wi‑Fi adapters use product support pages. "
            "Many are end-of-life — Microsoft catalog or OEM inbox driver may be newest."
        ),
        confidence="low",
    )]


def fetch_extended_vendor_offers(ctx: dict) -> list[dict]:
    """Batch 6 vendor scrapers (v6): Marvell, Synaptics/Elan, peripherals."""
    if not _dc("_v6_catalog_enabled")():
        return []
    vk = (ctx.get("vendor_key") or "").lower()
    if not _dc("_manufacturer_vendor_lookup_applicable")(
        vk, _dc("_catalog_system_ctx_from")(ctx)
    ):
        return []
    dispatch = {
        "marvell": lambda c: _dc("fetch_marvell_driver_offers")(c),
        "synaptics": lambda c: _dc("fetch_synaptics_driver_offers")(c),
        "elan": lambda c: _dc("fetch_elan_driver_offers")(c),
        "logitech": lambda c: _dc("fetch_logitech_driver_offers")(c),
        "samsung": lambda c: _dc("fetch_samsung_peripheral_offers")(c),
        "tplink": lambda c: _dc("fetch_tplink_driver_offers")(c),
        "netgear": lambda c: _dc("fetch_netgear_driver_offers")(c),
    }
    fn = dispatch.get(vk)
    if not fn:
        return []
    cache_key = _dc("_extended_vendor_cache_key")(ctx)
    if cache_key:
        cached = _dc("_vendor_scrape_cache_get")(cache_key)
        if cached and isinstance(cached, tuple) and len(cached) >= 3:
            best = cached[2]
            if isinstance(best, dict) and (best.get("title") or best.get("url")):
                return [dict(best)]
    offers = fn(ctx)
    if cache_key and offers:
        best = offers[0]
        _dc("_vendor_scrape_cache_set")(
            cache_key,
            (best.get("version") or "", best.get("date") or "", best),
        )
    return offers
