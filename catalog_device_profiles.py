"""Dual-version device profiles for GPU, chipset, audio, and network rows (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_scoring import (
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    _looks_like_amd_display_driver_version,
    _looks_like_intel_chipset_package_version,
    _looks_like_nvidia_branch_version,
    _looks_like_nvidia_internal_version,
    _looks_like_realtek_apo_version,
    _looks_like_realtek_nic_driver_version,
    _looks_like_realtek_wdm_version,
    _realtek_net_version_major,
    parse_driver_version,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_CHIPSET_COMPONENT_ORDER_AMD = {
    "PSP": 0,
    "SMBus": 1,
    "GPIO": 2,
    "I2C": 3,
    "MicroPEP": 4,
    "PPM": 5,
    "USB3": 6,
    "SATA": 7,
    "Other": 99,
}

_CHIPSET_COMPONENT_ORDER_INTEL = {
    "Chipset INF": 0,
    "Serial IO": 1,
    "SMBus": 2,
    "MEI": 3,
    "Other": 99,
}

def _device_vendor_key_from_dev(dev: dict) -> str:
    vk = (dev.get("vendor_key") or "").lower().strip()
    if vk:
        return vk
    blob = (
        f"{dev.get('name') or ''} {dev.get('manufacturer') or ''} "
        f"{dev.get('display_name') or ''}"
    ).lower()
    if any(k in blob for k in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
        return "nvidia"
    if any(k in blob for k in ("amd", "radeon", "ati")):
        return "amd"
    return ""

def _gpu_dual_version_applicable(dev: dict) -> bool:
    pnp = (dev.get("device_class") or dev.get("pnp_class") or "").lower()
    if pnp != "display":
        return False
    vk = _device_vendor_key_from_dev(dev)
    if vk not in ("amd", "nvidia"):
        return False
    windows = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    if not windows or windows == "?":
        return False
    return (
        _looks_like_amd_display_driver_version(windows)
        or _looks_like_nvidia_internal_version(windows)
    )

def _best_catalog_offer_for_gpu_profile(
    offers: list | None,
    vendor: str,
) -> dict | None:
    for offer in offers or []:
        if (offer.get("vs_installed") or "").lower() == "newer":
            src = (offer.get("source_label") or offer.get("source") or "").lower()
            if vendor == "amd" and "amd" in src:
                return offer
            if vendor == "nvidia" and "nvidia" in src:
                return offer
    for offer in offers or []:
        src = (offer.get("source_label") or offer.get("source") or "").lower()
        if vendor == "amd" and "amd" in src and _dc('_offer_version_from_fields')(offer):
            return offer
        if vendor == "nvidia" and "nvidia" in src and _dc('_offer_version_from_fields')(offer):
            return offer
    return None

def build_gpu_version_profile(
    dev: dict,
    offers: list | None = None,
) -> dict | None:
    """Dual Windows vs manufacturer version strings for AMD/NVIDIA display GPUs."""
    if not _gpu_dual_version_applicable(dev):
        return None
    vendor = _device_vendor_key_from_dev(dev)
    windows_inst = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    if vendor == "amd":
        mfr_label = "Adrenalin (AMD Software)"
        mfr_inst = _dc("_load_amd_adrenalin_installed_version")()
    else:
        mfr_label = "NVIDIA branch (Game Ready)"
        mfr_inst = _dc("_load_nvidia_branch_installed_version")()
    profile = {
        "vendor": vendor,
        "windows_label": "Windows (Device Manager)",
        "mfr_label": mfr_label,
        "windows_installed": windows_inst,
        "mfr_installed": mfr_inst,
        "windows_available": "",
        "mfr_available": "",
    }
    best = _best_catalog_offer_for_gpu_profile(offers, vendor)
    if best:
        ver = (_dc('_offer_version_from_fields')(best) or best.get("version") or "").strip()
        win_avail = (best.get("windows_display_version") or "").strip()
        if vendor == "amd" and _looks_like_amd_adrenalin_version(ver):
            profile["mfr_available"] = ver
            if _looks_like_amd_display_driver_version(win_avail):
                profile["windows_available"] = win_avail
        elif vendor == "nvidia":
            if _looks_like_nvidia_branch_version(ver):
                profile["mfr_available"] = ver
            if _looks_like_nvidia_internal_version(win_avail):
                profile["windows_available"] = win_avail
    if not profile["mfr_available"]:
        av = (dev.get("_available_version") or "").strip()
        if vendor == "amd" and _looks_like_amd_adrenalin_version(av):
            profile["mfr_available"] = av
        elif vendor == "nvidia" and _looks_like_nvidia_branch_version(av):
            profile["mfr_available"] = av
    return profile

def attach_gpu_version_profile(dev: dict, offers: list | None = None) -> None:
    profile = build_gpu_version_profile(dev, offers=offers)
    if profile:
        dev["_gpu_version_profile"] = profile
    else:
        dev.pop("_gpu_version_profile", None)

def format_gpu_installed_table_cell(profile: dict) -> tuple[str, str]:
    """Table Installed column: compact two-line text plus explanatory tooltip."""
    lines = [profile["windows_installed"]]
    tooltip = [f"{profile['windows_label']}: {profile['windows_installed']}"]
    mfr_inst = (profile.get("mfr_installed") or "").strip()
    if mfr_inst:
        short = "Adrenalin" if profile.get("vendor") == "amd" else "GRD branch"
        lines.append(f"{short} {mfr_inst}")
        tooltip.append(f"{profile['mfr_label']}: {mfr_inst}")
    return "\n".join(lines), "\n".join(tooltip)

def format_gpu_version_subtitle(profile: dict) -> str:
    """Detail header: labeled installed → available lines for each scheme."""
    blocks: list[str] = []
    win_line = profile["windows_installed"]
    win_avail = (profile.get("windows_available") or "").strip()
    if win_avail:
        win_line = f"{win_line} → {win_avail}"
    blocks.append(f"{profile['windows_label']}: {win_line}")
    mfr_inst = (profile.get("mfr_installed") or "").strip()
    mfr_avail = (profile.get("mfr_available") or "").strip()
    if mfr_inst or mfr_avail:
        mfr_line = mfr_inst or "?"
        if mfr_avail:
            mfr_line = f"{mfr_line} → {mfr_avail}"
        blocks.append(f"{profile['mfr_label']}: {mfr_line}")
    return "\n".join(blocks)

def _chipset_component_short_label(display_name: str, vendor: str) -> str:
    """Installer-style short label for a chipset bundle component row."""
    blob = (display_name or "").lower()
    if vendor == "amd":
        if "psp" in blob or "platform security" in blob:
            return "PSP"
        if "smbus" in blob:
            return "SMBus"
        if "gpio" in blob:
            return "GPIO"
        if "i2c" in blob:
            return "I2C"
        if "micropep" in blob or "micro pep" in blob:
            return "MicroPEP"
        if "provisioning" in blob or "ppm" in blob:
            return "PPM"
        if "usb 3" in blob or "usb3" in blob or "usb4" in blob:
            return "USB3"
        if "sata" in blob:
            return "SATA"
        return "Other"
    if "serial io" in blob:
        return "Serial IO"
    if "smbus" in blob:
        return "SMBus"
    if "management engine" in blob and "interface" not in blob:
        return "MEI"
    if "chipset" in blob:
        return "Chipset INF"
    return "Other"

def _collect_chipset_bundle_components(
    vendor: str,
    inventory: list | None,
) -> list[dict]:
    """Per-INF versions installed from the active AMD/Intel chipset bundle."""
    order = _CHIPSET_COMPONENT_ORDER_AMD if vendor == "amd" else _CHIPSET_COMPONENT_ORDER_INTEL
    components: list[dict] = []
    seen: set[str] = set()
    for row in inventory or []:
        display = (row.get("display_name") or row.get("name") or "").strip()
        if not display:
            continue
        ctx = {
            "device_label": display.lower(),
            "vendor_key": vendor,
        }
        if vendor == "amd":
            if not _dc('_device_is_amd_chipset_plumbing')(ctx):
                continue
        elif vendor == "intel":
            if not _dc('_device_is_intel_chipset_plumbing')(ctx) or _dc('_device_is_intel_me_device')(ctx):
                continue
        else:
            continue
        ver = (row.get("version") or "").strip()
        if not ver or ver in ("?", "—", "N/A", "n/a"):
            continue
        if _dc('_looks_like_chipset_package_version')(ver, vendor):
            continue
        short = _chipset_component_short_label(display, vendor)
        dedupe = short if short != "Other" else display.lower()
        if vendor == "amd" and short == "USB3":
            blob_l = display.lower()
            if "amd" not in blob_l and ver.startswith("10.0."):
                continue
        if dedupe in seen:
            continue
        seen.add(dedupe)
        components.append({
            "label": short,
            "device_name": display,
            "version": ver,
        })
    components.sort(key=lambda c: (order.get(c["label"], 99), c["label"]))
    return components

def _chipset_platform_profile_applicable(dev: dict) -> bool:
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"
    name = (dev.get("name") or dev.get("device_name") or "").strip()
    return name in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL)

def build_chipset_platform_version_profile(
    dev: dict,
    offers: list | None = None,
    inventory: list | None = None,
) -> dict | None:
    """Suite package + bundled component INF versions for synthetic platform rows."""
    if not _chipset_platform_profile_applicable(dev):
        return None
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
    name = (dev.get("name") or dev.get("device_name") or "").strip()
    vendor = "amd" if name == CHIPSET_DEVICE_AMD else "intel"
    mfr_label, _short = _chipset_profile_labels(vendor)
    suite_inst = _dc('_load_chipset_suite_installed_version')(vendor)
    if not suite_inst:
        suite_inst = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    profile: dict = {
        "vendor": vendor,
        "profile_kind": "chipset_platform",
        "mfr_label": mfr_label,
        "suite_installed": suite_inst or "?",
        "suite_available": "",
        "components": _collect_chipset_bundle_components(vendor, inventory),
    }
    for offer in offers or []:
        ver = (_dc('_offer_version_from_fields')(offer) or offer.get("version") or "").strip()
        if _dc('_looks_like_chipset_package_version')(ver, vendor):
            profile["suite_available"] = ver
            break
    if not profile["suite_available"]:
        av = (dev.get("_available_version") or "").strip()
        if _dc('_looks_like_chipset_package_version')(av, vendor):
            profile["suite_available"] = av
    return profile

def attach_chipset_platform_version_profile(
    dev: dict,
    offers: list | None = None,
    inventory: list | None = None,
) -> None:
    profile = build_chipset_platform_version_profile(dev, offers=offers, inventory=inventory)
    if profile:
        dev["_chipset_platform_version_profile"] = profile
    else:
        dev.pop("_chipset_platform_version_profile", None)

def format_chipset_platform_installed_table_cell(profile: dict) -> tuple[str, str]:
    """Platform row Installed column: suite version + component count."""
    suite = (profile.get("suite_installed") or "?").strip()
    components = profile.get("components") or []
    lines = [suite]
    tooltip = [f"{profile.get('mfr_label') or 'Chipset suite'}: {suite}"]
    if components:
        summary = ", ".join(f"{c['label']} {c['version']}" for c in components[:4])
        if len(components) > 4:
            summary += f", +{len(components) - 4} more"
        lines.append(f"{len(components)} components")
        tooltip.append("Bundle components (Device Manager INF versions):")
        for c in components:
            tooltip.append(f"  {c.get('device_name') or c['label']}: {c['version']}")
    else:
        lines.append("Component INFs not scanned yet")
        tooltip.append(
            "Run a driver scan to list PSP/SMBus/GPIO/I2C component versions "
            "installed by the chipset bundle."
        )
    return "\n".join(lines), "\n".join(tooltip)

def format_chipset_platform_version_subtitle(profile: dict) -> str:
    """Detail pane for AMD/Intel Chipset / Platform drivers synthetic row."""
    blocks: list[str] = []
    suite = (profile.get("suite_installed") or "?").strip()
    avail = (profile.get("suite_available") or "").strip()
    suite_line = suite
    if avail and avail != suite:
        suite_line = f"{suite} → {avail}"
    blocks.append(f"{profile.get('mfr_label') or 'Chipset suite'}: {suite_line}")
    components = profile.get("components") or []
    if components:
        blocks.append("Bundle components (Windows INF versions — not the suite number):")
        for c in components:
            blocks.append(f"  • {c.get('device_name') or c['label']}: {c['version']}")
    else:
        blocks.append(
            "Bundle components: not listed yet — rescan drivers after installing the suite."
        )
    row_hint = (
        "Intel Chipset / Platform drivers"
        if (profile.get("vendor") or "") == "intel"
        else "AMD Chipset / Platform drivers"
    )
    blocks.append(
        f"The WHQL suite number (e.g. 8.07.x) is the package AMD/Intel publishes; "
        f"Device Manager shows per-driver INF versions (e.g. PSP 5.46, GPIO 2.2). "
        f"Compare suite updates on this {row_hint} row — not component INF strings."
    )
    return "\n".join(blocks)

def _chipset_dual_version_applicable(dev: dict) -> bool:
    """Dual-line version display for AMD/Intel platform plumbing (not synthetic suite rows)."""
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"
    name = (dev.get("name") or dev.get("device_name") or "").strip()
    if name in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL):
        return False
    ctx = {
        "device_label": (dev.get("display_name") or dev.get("name") or "").lower(),
        "vendor_key": (dev.get("vendor_key") or "").lower(),
    }
    vendor = ""
    if _dc('_ctx_is_amd_device')(ctx) and _dc('_device_is_amd_chipset_plumbing')(ctx):
        vendor = "amd"
    elif _dc('_ctx_is_intel_device')(ctx) and _dc('_device_is_intel_chipset_plumbing')(ctx):
        if _dc('_device_is_intel_me_device')(ctx):
            return False
        vendor = "intel"
    if not vendor:
        return False
    windows = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    if not windows or windows == "?":
        return False
    if _dc('_looks_like_chipset_package_version')(windows, vendor):
        return False
    return bool(_dc('_load_chipset_suite_installed_version')(vendor))

def _chipset_profile_labels(vendor: str) -> tuple[str, str]:
    if vendor == "intel":
        return "Intel Chipset INF", "Chipset"
    return "AMD Chipset Software", "Chipset"

def build_chipset_version_profile(
    dev: dict,
    offers: list | None = None,
) -> dict | None:
    """Dual Windows component INF vs chipset suite versions (AMD or Intel)."""
    if not _chipset_dual_version_applicable(dev):
        return None
    ctx = {
        "device_label": (dev.get("display_name") or dev.get("name") or "").lower(),
        "vendor_key": (dev.get("vendor_key") or "").lower(),
    }
    if _dc('_ctx_is_intel_device')(ctx) and _dc('_device_is_intel_chipset_plumbing')(ctx):
        vendor = "intel"
    else:
        vendor = "amd"
    mfr_label, _short = _chipset_profile_labels(vendor)
    windows_inst = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    profile = {
        "vendor": vendor,
        "windows_label": "Windows (Device Manager)",
        "mfr_label": mfr_label,
        "windows_installed": windows_inst,
        "mfr_installed": _dc('_load_chipset_suite_installed_version')(vendor),
        "windows_available": "",
        "mfr_available": "",
    }
    for offer in offers or []:
        ver = (_dc('_offer_version_from_fields')(offer) or offer.get("version") or "").strip()
        if _dc('_looks_like_chipset_package_version')(ver, vendor):
            profile["mfr_available"] = ver
            break
    if not profile["mfr_available"]:
        av = (dev.get("_available_version") or "").strip()
        if _dc('_looks_like_chipset_package_version')(av, vendor):
            profile["mfr_available"] = av
    return profile

def attach_chipset_version_profile(dev: dict, offers: list | None = None) -> None:
    profile = build_chipset_version_profile(dev, offers=offers)
    if profile:
        dev["_chipset_version_profile"] = profile
    else:
        dev.pop("_chipset_version_profile", None)

def format_chipset_installed_table_cell(profile: dict) -> tuple[str, str]:
    """Table Installed column: component INF version + chipset suite version."""
    lines = [profile["windows_installed"]]
    tooltip = [f"{profile['windows_label']}: {profile['windows_installed']}"]
    suite_inst = (profile.get("mfr_installed") or "").strip()
    if suite_inst:
        lines.append(f"Chipset {suite_inst}")
        tooltip.append(f"{profile['mfr_label']}: {suite_inst}")
    return "\n".join(lines), "\n".join(tooltip)

def format_chipset_version_subtitle(profile: dict) -> str:
    """Detail header for AMD/Intel platform plumbing rows."""
    blocks: list[str] = []
    win_line = profile["windows_installed"]
    blocks.append(f"{profile['windows_label']}: {win_line}")
    suite_inst = (profile.get("mfr_installed") or "").strip()
    suite_avail = (profile.get("mfr_available") or "").strip()
    if suite_inst or suite_avail:
        suite_line = suite_inst or "?"
        if suite_avail and suite_avail != suite_inst:
            suite_line = f"{suite_line} → {suite_avail}"
        blocks.append(f"{profile['mfr_label']}: {suite_line}")
    vendor = (profile.get("vendor") or "amd").lower()
    row_hint = (
        "Intel Chipset / Platform drivers"
        if vendor == "intel"
        else "AMD Chipset / Platform drivers"
    )
    blocks.append(
        "Component INF versions are not comparable to the chipset suite number — "
        f"use {row_hint} for suite updates."
    )
    return "\n".join(blocks)

def _dev_to_profile_ctx(dev: dict) -> dict:
    return {
        "device_label": (dev.get("display_name") or dev.get("name") or "").lower(),
        "vendor_key": (dev.get("vendor_key") or "").lower(),
        "primary_version": (dev.get("_installed_at_scan") or dev.get("version") or "").strip(),
        "pnp_class": (dev.get("device_class") or dev.get("pnp_class") or "").lower(),
    }

def _looks_like_realtek_legacy_hda_version(version: str) -> bool:
    v = (version or "").strip()
    if re.match(r"R\d", v, re.I):
        return True
    parts = parse_driver_version(v)
    return bool(parts and parts[0] < 6)

def _realtek_audio_companion_version(
    dev: dict,
    inventory: list | None = None,
) -> tuple[str, str]:
    """Find paired WDM codec, Effects/APO, or legacy HDA/UAD version from inventory."""
    ctx = _dev_to_profile_ctx(dev)
    role = _dc('_realtek_device_component_role')(ctx)
    want = ""
    if _looks_like_realtek_legacy_hda_version(ctx["primary_version"]):
        want = "uad_wdm"
    elif role == "wdm":
        want = "apo"
    elif role == "apo":
        want = "wdm"
    if not want:
        return "", ""
    for row in inventory or []:
        label = f"{row.get('display_name') or ''} {row.get('name') or ''}".lower()
        if "realtek" not in label:
            continue
        ver = (row.get("version") or "").strip()
        if not ver or ver == "?":
            continue
        row_ctx = _dev_to_profile_ctx(row)
        row_role = _dc('_realtek_device_component_role')(row_ctx)
        if want == "apo" and row_role == "apo" and _looks_like_realtek_apo_version(ver):
            return ver, "apo"
        if want == "wdm" and row_role == "wdm" and _looks_like_realtek_wdm_version(ver):
            return ver, "wdm"
        if want == "uad_wdm" and row_role == "wdm" and _looks_like_realtek_wdm_version(ver):
            return ver, "uad_wdm"
    return "", ""

def _realtek_dual_version_applicable(
    dev: dict,
    inventory: list | None = None,
) -> bool:
    ctx = _dev_to_profile_ctx(dev)
    if (ctx.get("vendor_key") or "") != "realtek" and "realtek" not in ctx["device_label"]:
        return False
    windows = ctx["primary_version"]
    if not windows or windows == "?":
        return False
    if _looks_like_realtek_legacy_hda_version(windows):
        return bool(_realtek_audio_companion_version(dev, inventory=inventory)[0])
    role = _dc('_realtek_device_component_role')(ctx)
    if role == "wdm" and _looks_like_realtek_wdm_version(windows):
        return bool(_realtek_audio_companion_version(dev, inventory=inventory)[0])
    if role == "apo" and _looks_like_realtek_apo_version(windows):
        return bool(_realtek_audio_companion_version(dev, inventory=inventory)[0])
    return False

def build_realtek_audio_version_profile(
    dev: dict,
    offers: list | None = None,
    inventory: list | None = None,
) -> dict | None:
    """Dual WDM codec (6.0.x) vs Effects/APO (13.x) Realtek audio stack versions."""
    if not _realtek_dual_version_applicable(dev, inventory=inventory):
        return None
    ctx = _dev_to_profile_ctx(dev)
    role = _dc('_realtek_device_component_role')(ctx)
    windows_inst = ctx["primary_version"]
    companion, companion_role = _realtek_audio_companion_version(dev, inventory=inventory)
    if role == "wdm" and _looks_like_realtek_wdm_version(windows_inst):
        windows_label = "Windows (WDM codec)"
        mfr_label = "Realtek Audio Effects (APO)"
        mfr_inst = companion if companion_role == "apo" else ""
        audio_role = "wdm"
    elif role == "apo":
        windows_label = "Windows (Effects / APO)"
        mfr_label = "Realtek Audio (WDM codec)"
        mfr_inst = companion if companion_role == "wdm" else ""
        audio_role = "apo"
    elif _looks_like_realtek_legacy_hda_version(windows_inst):
        windows_label = "Windows (Legacy HDA)"
        mfr_label = "Realtek Audio (UAD WDM)"
        mfr_inst = companion if companion_role == "uad_wdm" else ""
        audio_role = "hda_legacy"
    else:
        return None
    profile = {
        "vendor": "realtek",
        "role": audio_role,
        "windows_label": windows_label,
        "mfr_label": mfr_label,
        "windows_installed": windows_inst,
        "mfr_installed": mfr_inst,
        "windows_available": "",
        "mfr_available": "",
    }
    for offer in offers or []:
        ver = (_dc('_offer_version_from_fields')(offer) or offer.get("version") or "").strip()
        if audio_role == "wdm" and _looks_like_realtek_apo_version(ver):
            profile["mfr_available"] = ver
            break
        if audio_role == "apo" and _looks_like_realtek_wdm_version(ver):
            profile["mfr_available"] = ver
            break
        if audio_role == "hda_legacy" and _looks_like_realtek_wdm_version(ver):
            profile["mfr_available"] = ver
            break
    return profile

def attach_realtek_audio_version_profile(
    dev: dict,
    offers: list | None = None,
    inventory: list | None = None,
) -> None:
    profile = build_realtek_audio_version_profile(
        dev, offers=offers, inventory=inventory
    )
    if profile:
        dev["_realtek_audio_version_profile"] = profile
    else:
        dev.pop("_realtek_audio_version_profile", None)

def format_realtek_audio_installed_table_cell(profile: dict) -> tuple[str, str]:
    lines = [profile["windows_installed"]]
    tooltip = [f"{profile['windows_label']}: {profile['windows_installed']}"]
    companion = (profile.get("mfr_installed") or "").strip()
    if companion:
        short = {
            "wdm": "Effects",
            "apo": "WDM",
            "hda_legacy": "UAD",
        }.get(profile.get("role") or "", "Pair")
        lines.append(f"{short} {companion}")
        tooltip.append(f"{profile['mfr_label']}: {companion}")
    return "\n".join(lines), "\n".join(tooltip)

def format_realtek_audio_version_subtitle(profile: dict) -> str:
    blocks: list[str] = []
    blocks.append(f"{profile['windows_label']}: {profile['windows_installed']}")
    companion = (profile.get("mfr_installed") or "").strip()
    companion_avail = (profile.get("mfr_available") or "").strip()
    if companion or companion_avail:
        line = companion or "?"
        if companion_avail and companion_avail != companion:
            line = f"{line} → {companion_avail}"
        blocks.append(f"{profile['mfr_label']}: {line}")
    blocks.append(
        "Realtek audio stacks use different version numbers for legacy HDA (R2.x / pre-6.0), "
        "UAD WDM codecs (6.0.x), and Effects/APO components (13.x) — compare all installed lines."
    )
    return "\n".join(blocks)

def _format_dual_version_installed_cell(
    profile: dict,
    *,
    short_mfr: str = "",
) -> tuple[str, str]:
    lines = [profile["windows_installed"]]
    tooltip = [f"{profile['windows_label']}: {profile['windows_installed']}"]
    mfr_inst = (profile.get("mfr_installed") or "").strip()
    if mfr_inst:
        lines.append(f"{short_mfr} {mfr_inst}".strip() if short_mfr else mfr_inst)
        tooltip.append(f"{profile['mfr_label']}: {mfr_inst}")
    return "\n".join(lines), "\n".join(tooltip)

def _format_dual_version_subtitle(
    profile: dict,
    *,
    note: str = "",
) -> str:
    blocks: list[str] = []
    win_line = profile["windows_installed"]
    win_avail = (profile.get("windows_available") or "").strip()
    if win_avail:
        win_line = f"{win_line} → {win_avail}"
    blocks.append(f"{profile['windows_label']}: {win_line}")
    mfr_inst = (profile.get("mfr_installed") or "").strip()
    mfr_avail = (profile.get("mfr_available") or "").strip()
    if mfr_inst or mfr_avail:
        mfr_line = mfr_inst or "?"
        if mfr_avail and mfr_avail != mfr_inst:
            mfr_line = f"{mfr_line} → {mfr_avail}"
        blocks.append(f"{profile['mfr_label']}: {mfr_line}")
    if note:
        blocks.append(note)
    return "\n".join(blocks)

def _looks_like_intel_me_component_version(version: str) -> bool:
    parts = parse_driver_version(version)
    if not parts:
        return False
    return parts[0] >= 2000 or (parts[0] >= 10 and parts[0] < 100 and len(parts) >= 2)

def _format_realtek_nic_build_suffix(version: str) -> str:
    tail = _dc('_realtek_nic_version_tail')(version)
    if not tail:
        return ""
    return ".".join(str(p) for p in tail)

def _load_intel_me_installed_version() -> str:
    pkg = _dc('_load_installed_package_versions')()
    ver = (pkg.get("intel_me") or "").strip()
    if ver and not _looks_like_intel_chipset_package_version(ver):
        return ver
    return ""

def _load_intel_wireless_installed_version() -> str:
    return (_dc('_load_installed_package_versions')().get("intel_wireless") or "").strip()

def _load_killer_suite_installed_version() -> str:
    return (_dc('_load_installed_package_versions')().get("killer_suite") or "").strip()

def _load_broadcom_ethernet_installed_version() -> str:
    return (_dc('_load_installed_package_versions')().get("broadcom_ethernet") or "").strip()

def _load_qualcomm_wireless_installed_version() -> str:
    return (_dc('_load_installed_package_versions')().get("qualcomm_wireless") or "").strip()

def _load_realtek_ethernet_installed_version() -> str:
    return (_dc('_load_installed_package_versions')().get("realtek_ethernet") or "").strip()

def _network_dual_version_kind(dev: dict) -> str:
    ctx = _dev_to_profile_ctx(dev)
    pnp = ctx["pnp_class"]
    label = ctx["device_label"]
    vk = ctx["vendor_key"]
    if "killer" in label or vk == "killer":
        return "killer"
    if "broadcom" in label or vk == "broadcom":
        return "broadcom"
    if "qualcomm" in label or vk == "qualcomm":
        return "qualcomm"
    if _dc('_ctx_is_intel_device')(ctx) and (
        pnp in ("net", "bluetooth")
        or any(k in label for k in ("wi-fi", "wi fi", "wireless", "wifi", "ax2", "ax20"))
    ):
        return "intel_wireless"
    if (
        "realtek" in label
        or vk == "realtek"
    ) and (
        pnp == "net"
        or any(k in label for k in ("ethernet", "gbe", "2.5g", "gaming 2.5"))
    ):
        return "realtek_nic"
    return ""

def _intel_me_dual_version_applicable(dev: dict) -> bool:
    ctx = _dev_to_profile_ctx(dev)
    if not _dc('_ctx_is_intel_device')(ctx) or not _dc('_device_is_intel_me_device')(ctx):
        return False
    windows = ctx["primary_version"]
    if not windows or windows == "?":
        return False
    if _looks_like_intel_chipset_package_version(windows):
        return False
    return bool(_dc("_load_intel_me_installed_version")()) or _looks_like_intel_me_component_version(
        windows
    )

def build_intel_me_version_profile(
    dev: dict,
    offers: list | None = None,
) -> dict | None:
    if not _intel_me_dual_version_applicable(dev):
        return None
    windows_inst = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    profile = {
        "vendor": "intel",
        "kind": "intel_me",
        "windows_label": "Windows (Device Manager)",
        "mfr_label": "Intel ME Components",
        "windows_installed": windows_inst,
        "mfr_installed": _dc("_load_intel_me_installed_version")(),
        "windows_available": "",
        "mfr_available": "",
    }
    for offer in offers or []:
        ver = (_dc('_offer_version_from_fields')(offer) or offer.get("version") or "").strip()
        if ver and _looks_like_intel_me_component_version(ver):
            profile["mfr_available"] = ver
            break
    return profile

def attach_intel_me_version_profile(dev: dict, offers: list | None = None) -> None:
    profile = build_intel_me_version_profile(dev, offers=offers)
    if profile:
        dev["_intel_me_version_profile"] = profile
    else:
        dev.pop("_intel_me_version_profile", None)

def format_intel_me_installed_table_cell(profile: dict) -> tuple[str, str]:
    return _format_dual_version_installed_cell(profile, short_mfr="ME pkg")

def format_intel_me_version_subtitle(profile: dict) -> str:
    return _format_dual_version_subtitle(
        profile,
        note=(
            "Intel ME interface drivers use per-component INF versions — compare against "
            "Intel ME Components / chipset platform packages for suite updates."
        ),
    )

def _network_dual_version_applicable(dev: dict) -> bool:
    kind = _network_dual_version_kind(dev)
    if not kind:
        return False
    windows = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    if not windows or windows == "?":
        return False
    if kind == "realtek_nic":
        return bool(
            _looks_like_realtek_nic_driver_version(windows)
            or _format_realtek_nic_build_suffix(windows)
            or _dc("_load_realtek_ethernet_installed_version")()
        )
    if kind == "intel_wireless":
        return bool(_dc("_load_intel_wireless_installed_version")())
    if kind == "killer":
        return bool(_dc("_load_killer_suite_installed_version")()) or bool(
            parse_driver_version(windows)
        )
    if kind == "broadcom":
        return bool(_dc("_load_broadcom_ethernet_installed_version")()) or bool(
            parse_driver_version(windows)
        )
    if kind == "qualcomm":
        return bool(_dc("_load_qualcomm_wireless_installed_version")()) or bool(
            parse_driver_version(windows)
        )
    return False

def build_network_version_profile(
    dev: dict,
    offers: list | None = None,
) -> dict | None:
    kind = _network_dual_version_kind(dev)
    if not _network_dual_version_applicable(dev):
        return None
    windows_inst = (dev.get("_installed_at_scan") or dev.get("version") or "").strip()
    profile: dict = {
        "vendor": kind,
        "kind": kind,
        "windows_label": "Windows (Device Manager)",
        "mfr_label": "",
        "windows_installed": windows_inst,
        "mfr_installed": "",
        "windows_available": "",
        "mfr_available": "",
    }
    if kind == "realtek_nic":
        pkg = _dc("_load_realtek_ethernet_installed_version")()
        suffix = _format_realtek_nic_build_suffix(windows_inst)
        family = _realtek_net_version_major(windows_inst)
        profile["mfr_label"] = "Realtek Ethernet Driver package"
        if pkg:
            profile["mfr_installed"] = pkg
        elif suffix:
            profile["mfr_label"] = "Realtek NIC OEM family / build suffix"
            profile["mfr_installed"] = (
                f"family {family} · build {suffix}" if family else f"build {suffix}"
            )
        else:
            return None
    elif kind == "intel_wireless":
        suite = _dc("_load_intel_wireless_installed_version")()
        if not suite:
            return None
        profile["mfr_label"] = "Intel PROSet / Wireless package"
        profile["mfr_installed"] = suite
    elif kind == "killer":
        profile["mfr_label"] = "Killer Performance Suite"
        profile["mfr_installed"] = _dc("_load_killer_suite_installed_version")()
        if not profile["mfr_installed"]:
            return None
    elif kind == "broadcom":
        profile["mfr_label"] = "Broadcom NetXtreme package"
        profile["mfr_installed"] = _dc("_load_broadcom_ethernet_installed_version")()
        if not profile["mfr_installed"]:
            return None
    elif kind == "qualcomm":
        suite = _dc("_load_qualcomm_wireless_installed_version")()
        if not suite:
            return None
        profile["mfr_label"] = "Qualcomm wireless package"
        profile["mfr_installed"] = suite
    for offer in offers or []:
        ver = (_dc('_offer_version_from_fields')(offer) or offer.get("version") or "").strip()
        if not ver:
            continue
        src = (offer.get("source_label") or offer.get("source") or "").lower()
        if kind == "realtek_nic" and "realtek" in src:
            profile["mfr_available"] = ver
            break
        if kind == "intel_wireless" and "intel" in src:
            profile["mfr_available"] = ver
            break
        if kind == "killer" and "killer" in src:
            profile["mfr_available"] = ver
            break
    return profile

def attach_network_version_profile(dev: dict, offers: list | None = None) -> None:
    profile = build_network_version_profile(dev, offers=offers)
    if profile:
        dev["_network_version_profile"] = profile
    else:
        dev.pop("_network_version_profile", None)

def format_network_installed_table_cell(profile: dict) -> tuple[str, str]:
    kind = (profile.get("kind") or "").lower()
    short = {
        "realtek_nic": "Package",
        "intel_wireless": "PROSet",
        "killer": "Killer",
        "broadcom": "Broadcom",
        "qualcomm": "QCA pkg",
    }.get(kind, "Package")
    mfr = (profile.get("mfr_installed") or "").strip()
    if mfr == "—":
        return profile["windows_installed"], profile["windows_label"]
    return _format_dual_version_installed_cell(profile, short_mfr=short)

def format_network_version_subtitle(profile: dict) -> str:
    notes = {
        "realtek_nic": (
            "Realtek gaming/2.5GbE drivers use an OEM family prefix (e.g. 1125 vs 1168) "
            "plus a shared build suffix — compare suffix lines across Dell/MS catalog offers."
        ),
        "intel_wireless": (
            "Intel Wi‑Fi/Bluetooth INF versions differ from PROSet / Connectivity Performance "
            "suite numbers — use both when checking for wireless updates."
        ),
        "killer": (
            "Killer NDIS driver versions differ from Killer Performance Suite — compare both."
        ),
        "broadcom": (
            "Broadcom NetXtreme driver INF versions differ from Broadcom setup package numbers."
        ),
        "qualcomm": (
            "Qualcomm consumer Wi‑Fi drivers are usually OEM-specific; suite packages rarely "
            "appear in Add/Remove Programs."
        ),
    }
    return _format_dual_version_subtitle(
        profile,
        note=notes.get((profile.get("kind") or "").lower(), ""),
    )

def attach_all_dual_version_profiles(
    dev: dict,
    offers: list | None = None,
    inventory: list | None = None,
) -> None:
    """Attach every applicable dual-version profile to one device row."""
    attach_chipset_platform_version_profile(dev, offers=offers, inventory=inventory)
    attach_gpu_version_profile(dev, offers=offers)
    attach_intel_me_version_profile(dev, offers=offers)
    attach_chipset_version_profile(dev, offers=offers)
    attach_realtek_audio_version_profile(dev, offers=offers, inventory=inventory)
    attach_network_version_profile(dev, offers=offers)

def pick_dual_version_profile(dev: dict) -> tuple[str, dict] | tuple[None, None]:
    """Return (key, profile) for the highest-priority dual-version display."""
    for key in (
        "_chipset_platform_version_profile",
        "_gpu_version_profile",
        "_intel_me_version_profile",
        "_chipset_version_profile",
        "_realtek_audio_version_profile",
        "_network_version_profile",
    ):
        profile = dev.get(key)
        if profile:
            return key, profile
    return None, None

def format_dual_version_installed_for_dev(dev: dict) -> tuple[str, str]:
    key, profile = pick_dual_version_profile(dev)
    if not profile:
        ver = (dev.get("version") or "").strip() or "?"
        return ver, ver if ver != "?" else ""
    formatters = {
        "_chipset_platform_version_profile": format_chipset_platform_installed_table_cell,
        "_gpu_version_profile": format_gpu_installed_table_cell,
        "_intel_me_version_profile": format_intel_me_installed_table_cell,
        "_chipset_version_profile": format_chipset_installed_table_cell,
        "_realtek_audio_version_profile": format_realtek_audio_installed_table_cell,
        "_network_version_profile": format_network_installed_table_cell,
    }
    fn = formatters.get(key or "")
    return fn(profile) if fn else (profile.get("windows_installed") or "?", "")

def format_dual_version_subtitle_for_dev(
    dev: dict,
    offers: list | None = None,
) -> str:
    key, profile = pick_dual_version_profile(dev)
    if not profile:
        return ""
    formatters = {
        "_chipset_platform_version_profile": format_chipset_platform_version_subtitle,
        "_gpu_version_profile": format_gpu_version_subtitle,
        "_intel_me_version_profile": format_intel_me_version_subtitle,
        "_chipset_version_profile": format_chipset_version_subtitle,
        "_realtek_audio_version_profile": format_realtek_audio_version_subtitle,
        "_network_version_profile": format_network_version_subtitle,
    }
    fn = formatters.get(key or "")
    return fn(profile) if fn else ""
