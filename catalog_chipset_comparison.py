"""Chipset/platform comparison helpers (extracted from driver_catalog)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from catalog_device_context import (
    _ctx_is_amd_chipset_platform_row,
    _ctx_is_intel_chipset_platform_row,
    _device_is_amd_chipset_plumbing,
    _pci_tokens_from_id,
)
from catalog_device_profiles import build_chipset_platform_version_profile
from catalog_offer_pipeline import _finalize_catalog_offers
from catalog_scoring import (
    _looks_like_amd_chipset_package_version,
    _looks_like_intel_chipset_package_version,
    compare_versions,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def _looks_like_chipset_package_version(version: str, vendor: str) -> bool:
    if vendor == "intel":
        return _looks_like_intel_chipset_package_version(version)
    return _looks_like_amd_chipset_package_version(version)


def _load_chipset_suite_installed_version(vendor: str) -> str:
    if vendor == "intel":
        return _dc("_load_intel_chipset_suite_installed_version")()
    return _dc("_load_amd_chipset_suite_installed_version")()


def _resolve_chipset_installed_version(
    vendor_key: str,
    inventory: list | None,
    system_ctx: dict | None = None,
) -> str:
    """Best installed version for AMD/Intel chipset packages from driver inventory."""
    patterns_amd = (
        "amd chipset", "chipset drivers", "amd application compatibility",
        "amd psp", "amd smbus", "amd gpio", "amd ucm", "amd micropep",
        "amd usb 3.10", "amd sata", "amd pci",
    )
    patterns_intel = (
        "intel chipset", "intel dynamic platform", "intel serial io",
        "intel smbus", "intel management engine", "intel pmt",
        "intel innovation platform",
    )
    patterns = patterns_amd if vendor_key == "amd" else patterns_intel
    pkg_versions = _dc("_load_installed_package_versions")()
    pkg_key = "amd_chipset" if vendor_key == "amd" else "intel_chipset"
    pkg_ver = (pkg_versions.get(pkg_key) or "").strip()
    if pkg_ver:
        return pkg_ver
    best_ver = ""
    for row in inventory or []:
        name = (row.get("display_name") or row.get("name") or "").lower()
        ver = (row.get("version") or "").strip()
        if not ver or ver in ("?", "—", "N/A", "n/a"):
            continue
        if not any(p in name for p in patterns):
            continue
        if not best_ver or compare_versions(best_ver, ver) in ("newer", "unknown"):
            best_ver = ver
    return best_ver or "?"


def _build_chipset_catalog_context(
    vendor_key: str,
    label: str,
    installed: str,
    inventory: list | None,
    system_ctx: dict | None,
    *,
    device_name: str = "",
) -> dict:
    """Chipset pseudo-device ctx with a real PnP anchor when inventory provides one."""
    ctx: dict = {
        "device_label": label,
        "vendor_key": vendor_key,
        "hw_category": "chipset",
        "pnp_class": "system",
        "primary_version": installed,
        "target_device_name": device_name,
        "device_name": device_name,
    }
    patterns_amd = (
        "amd chipset", "chipset drivers", "amd smbus", "amd gpio", "amd pci",
        "amd psp", "amd ucm", "amd micropep", "amd usb 3.10", "amd sata",
    )
    patterns_intel = (
        "intel chipset", "intel dynamic platform", "intel serial io",
        "intel smbus", "intel management engine", "intel pmt",
        "intel innovation platform",
    )
    patterns = patterns_amd if vendor_key == "amd" else patterns_intel
    pci_inst = ""
    pci_name = ""
    pci_score = -1
    acpi_inst = ""
    acpi_name = ""
    _bad_anchor_prefixes = ("HDAUDIO\\", "DISPLAY\\", "MONITOR\\", "USB\\", "HID\\")

    def _anchor_score(inst_id: str, display: str) -> int:
        iu = inst_id.upper()
        if any(iu.startswith(p) for p in _bad_anchor_prefixes):
            return -1
        score = 0
        if vendor_key == "amd" and "VEN_1022" in iu:
            score += 20
        if vendor_key == "intel" and "VEN_8086" in iu:
            score += 20
        blob = display.lower()
        if "chipset" in blob or "smbus" in blob or "gpio" in blob:
            score += 8
        if "VEN_" in iu:
            score += 4
        return score

    for row in inventory or []:
        raw_name = (row.get("name") or "").strip()
        display = (row.get("display_name") or raw_name).strip()
        blob = f"{display} {raw_name}".lower()
        if vendor_key == "amd":
            if not any(p in blob for p in patterns) and not _device_is_amd_chipset_plumbing(
                {"device_label": display.lower()}
            ):
                continue
        elif not any(p in blob for p in patterns):
            continue
        inst = raw_name if "\\" in raw_name.upper() else ""
        if not inst:
            continue
        sc = _anchor_score(inst, display)
        if sc < 0:
            continue
        if "VEN_" in inst.upper():
            if sc > pci_score:
                pci_inst, pci_name, pci_score = inst, display, sc
            if sc >= 20:
                break
        elif not acpi_inst:
            acpi_inst, acpi_name = inst, display
    inst_id = pci_inst or acpi_inst
    anchor_name = pci_name or acpi_name
    if not inst_id:
        ven_token = "1022" if vendor_key == "amd" else "8086"
        for ent in (system_ctx or {}).get("pnp_list") or []:
            did = (ent.get("DeviceID") or ent.get("device_id") or "").strip()
            if not did or "\\" not in did:
                continue
            du = did.upper()
            if any(du.startswith(p) for p in _bad_anchor_prefixes):
                continue
            if f"VEN_{ven_token}" in du:
                inst_id = did
                anchor_name = (ent.get("Name") or ent.get("name") or label).strip()
                break
    if inst_id:
        ctx["instance_id"] = inst_id
        ctx["pci_tokens"] = _pci_tokens_from_id(inst_id)
    if anchor_name:
        ctx["device_label"] = anchor_name
    ctx["_catalog_system_ctx"] = dict(system_ctx or {})
    return ctx


def _catalog_system_ctx_from(ctx: dict, system_ctx: dict | None = None) -> dict:
    if system_ctx:
        return system_ctx
    stored = ctx.get("_catalog_system_ctx")
    return stored if isinstance(stored, dict) else {}


def _manufacturer_vendor_lookup_applicable(
    vendor_key: str,
    system_ctx: dict | None,
) -> bool:
    """PC-level gate: skip manufacturer HTTP when this vendor is absent from hardware."""
    from bsod_hardware_wmi import (
        amd_driver_lookup_applicable,
        catalog_hardware_context_confident,
        intel_driver_lookup_applicable,
        network_vendor_driver_lookup_applicable,
        nvidia_driver_lookup_applicable,
        realtek_driver_lookup_applicable,
        vendor_present_in_hardware,
    )
    from catalog_extended_fetch import _EXTENDED_VENDOR_KEYS
    from catalog_tier_policy import _NETWORK_VENDOR_KEYS

    vk = (vendor_key or "").lower().strip()
    if not vk:
        return False
    ctx = system_ctx or {}
    if not catalog_hardware_context_confident(ctx):
        return True
    if vk == "intel":
        return intel_driver_lookup_applicable(ctx)
    if vk == "amd":
        return amd_driver_lookup_applicable(ctx)
    if vk == "nvidia":
        return nvidia_driver_lookup_applicable(ctx)
    if vk == "realtek":
        return realtek_driver_lookup_applicable(ctx)
    if vk in _NETWORK_VENDOR_KEYS:
        return network_vendor_driver_lookup_applicable(vk, ctx)
    if vk in _EXTENDED_VENDOR_KEYS:
        return vendor_present_in_hardware(ctx, vk)
    return vendor_present_in_hardware(ctx, vk)


def chipset_ms_catalog_limitation_note(ctx: dict) -> str | None:
    """User-visible note when chipset rows lack a PnP anchor for Microsoft HWID matching."""
    if ctx.get("hw_category") != "chipset":
        return None
    if (ctx.get("instance_id") or "").strip():
        return None
    return (
        "Limited Microsoft Update matching — no chipset PnP anchor in device inventory. "
        "OEM and AMD/Intel vendor packages are still shown."
    )


def _chipset_platform_oem_offers(ctx: dict, system_ctx: dict | None) -> list[dict]:
    """OEM chipset suite packages for synthetic platform rows (title match, not HWID)."""
    if not (
        _ctx_is_amd_chipset_platform_row(ctx) or _ctx_is_intel_chipset_platform_row(ctx)
    ):
        return []
    try:
        import catalog_cache as ccat
    except ImportError:
        return []
    if not ccat or not ccat.should_use_disk_cache():
        return []
    offers, _blob = ccat.load_oem_offers(system_ctx)
    if not offers:
        return []
    vk = (ctx.get("vendor_key") or "").lower()
    out: list[dict] = []
    for row in offers:
        if (row.get("source") or "").lower() != "oem":
            continue
        title_l = (row.get("title") or "").lower()
        cat_l = (row.get("category") or "").lower()
        if "chipset" not in title_l and "chipset" not in cat_l:
            continue
        if vk == "amd" and "amd" not in title_l:
            continue
        if vk == "intel" and "intel" not in title_l:
            continue
        if not (row.get("version") or "").strip():
            continue
        out.append(dict(row))
    return out


def build_chipset_platform_comparison(
    device_name: str,
    system_ctx: dict | None,
    progress: Callable[[str], None] | None = None,
    inventory: list | None = None,
) -> dict:
    """AMD or Intel chipset / platform driver packages."""
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"

    label = "Chipset / platform drivers"
    if device_name == CHIPSET_DEVICE_AMD:
        label = "AMD Chipset / Platform drivers"
        vk = "amd"
    elif device_name == CHIPSET_DEVICE_INTEL:
        label = "Intel Chipset / Platform drivers"
        vk = "intel"
    else:
        vk = ""

    installed = _resolve_chipset_installed_version(vk, inventory, system_ctx)
    ctx = _build_chipset_catalog_context(
        vk,
        label,
        installed,
        inventory,
        system_ctx,
        device_name=device_name,
    )
    offers: list[dict] = []
    if vk == "amd":
        offers.extend(_dc("fetch_amd_driver_offers")(ctx))
        offers.append({
            "source": "vendor",
            "source_label": "AMD Chipset",
            "title": "AMD Chipset Drivers (official)",
            "version": "",
            "date": "",
            "url": _dc("_amd_drivers_download_url")(),
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": "Platform drivers (SATA, USB, power) — install after BIOS is current.",
            "confidence": "medium",
        })
    elif vk == "intel":
        offers.extend(_dc("fetch_intel_driver_offers")(ctx))
        offers.append({
            "source": "vendor",
            "source_label": "Intel Chipset",
            "title": "Intel Chipset INF / Platform drivers",
            "version": "",
            "date": "",
            "url": "https://www.intel.com/content/www/us/en/download-center/home.html",
            "download_kind": "url",
            "update_id": "",
            "instance_id": "",
            "notes": "Search for your chipset INF on Intel Download Center.",
            "confidence": "medium",
        })
    offers.extend(_dc("fetch_oem_driver_offers")(ctx, system_ctx))
    platform_oem = _chipset_platform_oem_offers(ctx, system_ctx)
    if platform_oem:
        seen = {(o.get("title"), o.get("version")) for o in offers}
        for row in platform_oem:
            key = (row.get("title"), row.get("version"))
            if key not in seen:
                offers.append(row)
                seen.add(key)
    catalog_note = chipset_ms_catalog_limitation_note(ctx)
    has_anchor = bool((ctx.get("instance_id") or "").strip())
    if has_anchor:
        ms_task = _dc("_microsoft_catalog_task")(
            ctx,
            system_ctx,
            allow_catalog_search=True,
            include_informational=False,
        )
        if ms_task:
            try:
                offers.extend(ms_task() or [])
            except Exception:  # noqa: BLE001
                pass
    offers = _finalize_catalog_offers(offers, installed, device_ctx=ctx)
    bundle_profile = build_chipset_platform_version_profile(
        {
            "name": device_name,
            "device_name": device_name,
            "version": installed,
            "_installed_at_scan": installed,
        },
        offers=offers,
        inventory=inventory,
    )
    if progress:
        progress(f"Chipset packages for {label}")
    result = {
        "context": ctx,
        "installed_version": installed,
        "installed_rows": [],
        "offers": offers,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "device_name": device_name,
        "catalog_note": catalog_note,
    }
    if bundle_profile:
        result["chipset_bundle_components"] = bundle_profile.get("components") or []
        result["chipset_suite_version"] = bundle_profile.get("suite_installed") or installed
    return result

__all__ = [
    "_build_chipset_catalog_context",
    "_chipset_platform_oem_offers",
    "_load_chipset_suite_installed_version",
    "_looks_like_chipset_package_version",
    "_resolve_chipset_installed_version",
    "build_chipset_platform_comparison",
    "chipset_ms_catalog_limitation_note",
]
