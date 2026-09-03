"""Device context classification, builders, and driver-scan scope (from driver_catalog)."""

from __future__ import annotations

import re

from catalog_scoring import _looks_like_realtek_wdm_version

_DRIVER_SCAN_EXCLUDED_PNP_CLASSES = frozenset({"firmware"})

_AMD_CHIPSET_PLUMBING_NAME_PARTS = (
    "gpio controller",
    "gpio2",
    "gpio3",
    "i2c controller",
    "i2c device",
    " amd i2c",
    "micro pep",
    "micropep",
    "provisioning package",
    "provisioning packages",
    "provisioning file",
    "ppm provisioning",
    "smbus controller",
    "smbus compatible",
    "smbus",
    "platform security",
    "psp platform",
    "psp 11",
    "psp device",
    "fch",
    "clock pll",
    "iommu",
    "usb 3.10",
    "usb3 root",
    "usb4 root",
)



_AMD_MEDIA_NAME_PARTS = (
    "audio device",
    "audio coprocessor",
    "streaming audio",
    "hdmi audio",
    "high definition audio device",
)
def _ctx_device_label(ctx: dict) -> str:
    for key in ("device_label", "target_device_name", "display_name"):
        val = (ctx.get(key) or "").strip()
        if val:
            return val.lower()
    for row in ctx.get("installed_rows") or []:
        val = (row.get("display_name") or row.get("name") or "").strip()
        if val:
            return val.lower()
    return ""


def _ctx_is_amd_device(ctx: dict) -> bool:
    vk = (ctx.get("vendor_key") or "").lower()
    label = _ctx_device_label(ctx)
    return vk == "amd" or label.startswith("amd") or " amd " in f" {label} "


def _device_is_amd_chipset_plumbing(ctx: dict) -> bool:
    label = _ctx_device_label(ctx)
    return any(part in label for part in _AMD_CHIPSET_PLUMBING_NAME_PARTS)


_INTEL_CHIPSET_PLUMBING_NAME_PARTS = (
    "serial io",
    "management engine",
    "intel smbus",
    "dynamic platform",
    "innovation platform",
    "intel pmt",
    "platform monitoring",
    "host bridge",
    "lpc controller",
    "lpc ec",
    "thermal subsystem",
    "gna scouting",
    "gaussian",
    "chipset device",
    "intel chipset",
    "chipset family",
    "sata ahci",
    "pci express root port",
    "power engine",
    "intel smbus",
)


def _ctx_is_intel_device(ctx: dict) -> bool:
    vk = (ctx.get("vendor_key") or "").lower()
    label = _ctx_device_label(ctx)
    return vk == "intel" or label.startswith("intel") or " intel " in f" {label} "


def _device_is_intel_chipset_plumbing(ctx: dict) -> bool:
    label = _ctx_device_label(ctx)
    return any(part in label for part in _INTEL_CHIPSET_PLUMBING_NAME_PARTS)


def _intel_driver_hint_from_ctx(ctx: dict) -> str | None:
    """Intel download-page hint — None when manufacturer scrape must not run."""
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"

    name = (ctx.get("device_name") or ctx.get("device_label") or "").strip()
    if name == CHIPSET_DEVICE_INTEL or ctx.get("hw_category") == "chipset":
        return "chipset"
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp == "display" or ctx.get("hw_category") == "gpu":
        return "graphics"
    if pnp == "net":
        label = _ctx_device_label(ctx)
        if any(k in label for k in ("wi-fi", "wifi", "wireless", "wlan")):
            return "wifi"
    if _device_is_intel_chipset_plumbing(ctx):
        return "chipset"
    return None


def _device_is_intel_me_device(ctx: dict) -> bool:
    label = _ctx_device_label(ctx)
    return "management engine" in label or label.startswith("intel(r) me ")


def _device_is_chipset_plumbing(ctx: dict) -> bool:
    return _device_is_amd_chipset_plumbing(ctx) or _device_is_intel_chipset_plumbing(ctx)


def _ctx_is_chipset_component_plumbing(ctx: dict) -> bool:
    """Per-INF chipset function row — not the synthetic platform summary row."""
    if ctx.get("hw_category") == "chipset":
        return False
    if _ctx_is_intel_chipset_platform_row(ctx):
        return False
    if _ctx_is_amd_chipset_platform_row(ctx):
        return False
    return _device_is_chipset_plumbing(ctx)


def _device_is_amd_media(ctx: dict) -> bool:
    label = _ctx_device_label(ctx)
    return any(part in label for part in _AMD_MEDIA_NAME_PARTS)


def _device_is_amd_audio(ctx: dict) -> bool:
    """AMD audio/co-processor/streaming rows — not Realtek codec targets."""
    if not _ctx_is_amd_device(ctx):
        return False
    label = _ctx_device_label(ctx)
    return _device_is_amd_media(ctx) or "audio" in label




def _nvidia_is_audio_or_usb_component(ctx: dict) -> bool:
    """HD Audio, Virtual Audio, USBC, etc. — not the display driver package."""
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx)
    vk = (ctx.get("vendor_key") or "").lower()
    if vk != "nvidia" and "nvidia" not in label:
        return False
    if pnp in ("media", "audio", "audioendpoint"):
        return True
    return any(
        k in label
        for k in (
            "virtual audio",
            "high definition audio",
            "hd audio",
            "usbc driver",
            "usb-c driver",
        )
    )


def _nvidia_is_audio_component(ctx: dict) -> bool:
    """NVIDIA HD / Virtual Audio — not GPU display or USBC."""
    if not _nvidia_is_audio_or_usb_component(ctx):
        return False
    label = _ctx_device_label(ctx)
    return not any(k in label for k in ("usbc driver", "usb-c driver"))


def _nvidia_gpu_driver_lookup_applicable(ctx: dict) -> bool:
    if _nvidia_is_audio_or_usb_component(ctx):
        return False
    pnp = (ctx.get("pnp_class") or "").lower()
    label = _ctx_device_label(ctx)
    vk = (ctx.get("vendor_key") or "").lower()
    if pnp == "display":
        return vk == "nvidia" or "nvidia" in label or "geforce" in label
    return False


def _nvidia_ctx_eligible(ctx: dict) -> bool:
    """True only for NVIDIA GPU display rows — not audio/USB companion devices."""
    return _nvidia_gpu_driver_lookup_applicable(ctx)










def _ctx_is_amd_chipset_platform_row(ctx: dict | None) -> bool:
    if not ctx:
        return False
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
    name = (ctx.get("device_name") or ctx.get("target_device_name") or ctx.get("device_label") or "").strip()
    return name == CHIPSET_DEVICE_AMD or (
        ctx.get("hw_category") == "chipset" and (ctx.get("vendor_key") or "").lower() == "amd"
        and name.lower().startswith("amd chipset")
    )


def _ctx_is_intel_chipset_platform_row(ctx: dict | None) -> bool:
    if not ctx:
        return False
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"
    name = (ctx.get("device_name") or ctx.get("device_label") or "").strip()
    return name == CHIPSET_DEVICE_INTEL or ctx.get("hw_category") == "chipset"

def is_driver_scan_excluded_ctx(ctx: dict) -> bool:
    """True for PnP firmware-class devices (Firmware tab owns these)."""
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp in _DRIVER_SCAN_EXCLUDED_PNP_CLASSES:
        return True
    for row in ctx.get("installed_rows") or []:
        if (row.get("device_class") or "").lower() in _DRIVER_SCAN_EXCLUDED_PNP_CLASSES:
            return True
    label = (
        ctx.get("device_label")
        or ctx.get("target_device_name")
        or ""
    ).strip().lower()
    if label == "device firmware":
        return True
    return _is_logitech_virtual_driver_noise(label)


def _is_logitech_virtual_driver_noise(label: str) -> bool:
    """G HUB virtual keyboard/bus rows duplicate the physical USB device."""
    low = (label or "").strip().lower()
    if not low or "logitech" not in low:
        return False
    return any(
        k in low
        for k in (
            "virtual keyboard",
            "virtual bus enumerator",
            "gaming virtual keyboard",
        )
    )


def is_driver_scan_excluded_device(dev: dict) -> bool:
    """True when a driver-list row should not participate in driver catalog scans."""
    if not dev:
        return False
    dc = (dev.get("device_class") or "").strip().lower()
    if dc in _DRIVER_SCAN_EXCLUDED_PNP_CLASSES:
        return True
    name = (dev.get("name") or dev.get("display_name") or "").strip().lower()
    if name == "device firmware":
        return True
    return _is_logitech_virtual_driver_noise(name)


def _pnp_row_for_device_id(pnp_list: list | None, device_id: str) -> dict | None:
    if not pnp_list or not device_id:
        return None
    norm = device_id.strip().upper().replace("\\\\", "\\")
    for row in pnp_list:
        did = (row.get("DeviceID") or row.get("device_id") or "").strip()
        if did.upper().replace("\\\\", "\\") == norm:
            return row
    return None


def _walk_pnp_to_realtek_hdaudio(pnp_list: list | None, start_id: str) -> str:
    """Follow DEVPKEY_Device_Parent links to the Realtek HDAUDIO codec node."""
    current = (start_id or "").strip()
    seen: set[str] = set()
    for _ in range(12):
        if not current:
            break
        key = current.upper()
        if key in seen:
            break
        seen.add(key)
        if "HDAUDIO" in key and "VEN_10EC" in key:
            return current
        row = _pnp_row_for_device_id(pnp_list, current)
        parent = (row.get("Parent") or row.get("parent") or "").strip() if row else ""
        if not parent:
            break
        current = parent
    return ""


def _realtek_catalog_name_aliases(name: str) -> list[str]:
    """Names to try for this device: its own label first, then known Win32_PnPEntity spellings.

    `seen` starts empty on purpose. Pre-seeding it with the device's own name made the
    loop below discard `n` on its first iteration, so callers only ever looked up the
    "(R)" spellings — a device Windows reports as plain "Realtek Audio" never matched
    pnp_enrichment and never inherited its parent HDAUDIO hardware ID.
    """
    n = (name or "").strip()
    out: list[str] = []
    if n.lower() == "realtek audio":
        out.extend(["Realtek(R) Audio", "Realtek (R) Audio"])
    seen: set[str] = set()
    aliases: list[str] = []
    for item in [n, *out]:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            aliases.append(item.strip())
    return aliases


def _apply_realtek_parent_hwid_ctx(
    ctx: dict,
    pnp_list: list | None,
    system_ctx: dict | None,
) -> None:
    """UAD codec/function rows may lack DeviceID — inherit parent HDAUDIO VEN_10EC."""
    from bsod_crash_report import _find_pnp_entity_by_device_name
    from catalog_row_rejects import _realtek_device_component_role
    if (ctx.get("vendor_key") or "").lower() != "realtek":
        return
    if _realtek_device_component_role(ctx) != "wdm":
        return
    inst = (ctx.get("instance_id") or "").upper()
    if "VEN_10EC" in inst and "HDAUDIO" in inst:
        return
    name = (ctx.get("target_device_name") or ctx.get("device_label") or "").strip()
    codec_id = ""
    for alias in _realtek_catalog_name_aliases(name):
        if system_ctx:
            pnp_enr = (system_ctx.get("pnp_enrichment") or {}).get(alias) or {}
            parent_id = (pnp_enr.get("parent_device_id") or pnp_enr.get("device_id") or "").strip()
            codec_id = _walk_pnp_to_realtek_hdaudio(pnp_list, parent_id) or (
                parent_id if "VEN_10EC" in parent_id.upper() else ""
            )
            if codec_id:
                break
        if pnp_list:
            try:
                import device_enrichment as de
                lu = de.pnp_lookup_from_ctx({"pnp_list": pnp_list})
                hit = lu.get(alias.lower()) if lu else None
            except ImportError:
                hit = None
            if hit:
                seed = (hit.get("parent_device_id") or hit.get("device_id") or "").strip()
                codec_id = _walk_pnp_to_realtek_hdaudio(pnp_list, seed) or (
                    seed if "VEN_10EC" in seed.upper() else ""
                )
                if codec_id:
                    break
    if not codec_id and pnp_list and name:
        entity = _find_pnp_entity_by_device_name(pnp_list, name)
        if entity:
            seed = (entity.get("DeviceID") or "").strip()
            parent = (entity.get("Parent") or entity.get("parent") or "").strip()
            codec_id = (
                _walk_pnp_to_realtek_hdaudio(pnp_list, seed)
                or _walk_pnp_to_realtek_hdaudio(pnp_list, parent)
            )
    if not codec_id and pnp_list:
        for alias in _realtek_catalog_name_aliases(name):
            entity = _find_pnp_entity_by_device_name(pnp_list, alias)
            if entity:
                seed = (entity.get("device_id") or entity.get("DeviceID") or "").strip()
                codec_id = _walk_pnp_to_realtek_hdaudio(pnp_list, seed) or seed
                if codec_id and "VEN_10EC" in codec_id.upper():
                    break
                codec_id = ""
    if not codec_id:
        return
    ctx["instance_id"] = codec_id
    ctx["pci_tokens"] = _pci_tokens_from_id(codec_id)

def _pci_tokens_from_id(device_id: str) -> list[str]:
    if not device_id:
        return []
    u = device_id.upper()
    tokens = []
    for key in ("VEN_", "DEV_", "SUBSYS_", "REV_"):
        m = re.search(rf"{key}([0-9A-F]+)", u)
        if m:
            tokens.append(f"{key}{m.group(1)}")
    return tokens


def get_device_context(
    driver: str | None,
    pnp_list: list | None,
    inventory: list | None,
    system_ctx: dict | None,
) -> dict:
    """PnP instance, hardware IDs, GPU rows, OEM tag — for catalog queries."""
    from bsod_crash_report import (
        DRIVER_TO_HARDWARE,
        _find_pnp_entity_by_device_name,
        _infer_driver_vendor,
        find_culprit_devices,
        lookup_inventory_row,
    )
    culprit_names = sorted(find_culprit_devices(inventory or [], driver))
    pnp_entity = None
    for name in culprit_names:
        pnp_entity = _find_pnp_entity_by_device_name(pnp_list or [], name)
        if pnp_entity:
            break

    instance_id = (pnp_entity or {}).get("DeviceID") or ""
    device_label = culprit_names[0] if culprit_names else (pnp_entity or {}).get("Name") or driver or ""
    pci_tokens = _pci_tokens_from_id(instance_id)

    drv_base = (driver or "").lower().replace(".sys", "").replace(".dll", "").strip()
    vendor_key = None
    hw = None
    for key, entry in DRIVER_TO_HARDWARE.items():
        if key in drv_base or drv_base == key:
            if hw is None or len(key) > len(hw[0]):
                hw = (key, entry)
    if hw:
        vendor_key = hw[1][1]
    if not vendor_key:
        vendor_key = (_infer_driver_vendor(drv_base) or "").split(" (")[0].split("/")[0].strip().lower()

    installed_rows = []
    for name in culprit_names:
        d = lookup_inventory_row(inventory, name)
        if d:
            installed_rows.append({
                "name": name,
                "version": (d.get("version") or "").strip() or "?",
                "date": (d.get("date") or ""),
                "device_class": (d.get("device_class") or "").strip(),
            })

    pnp_class = _infer_pnp_class_for_device(
        device_label,
        vendor_key or "",
        (pnp_entity or {}).get("PNPClass") or "",
        hw[1][0] if hw else "",
    )
    primary_version = _resolve_primary_installed_version(
        {
            "primary_version": installed_rows[0]["version"] if installed_rows else "",
            "instance_id": instance_id,
            "vendor_key": vendor_key or "",
            "device_label": device_label,
            "pnp_class": pnp_class,
            "target_device_name": culprit_names[0] if culprit_names else device_label,
        },
        system_ctx,
    )
    if installed_rows:
        installed_rows[0]["version"] = primary_version

    return {
        "driver": driver,
        "device_label": device_label,
        "culprit_names": culprit_names,
        "instance_id": instance_id,
        "pci_tokens": pci_tokens,
        "pnp_class": pnp_class,
        "vendor_key": vendor_key,
        "hw_category": hw[1][0] if hw else "",
        "installed_rows": installed_rows,
        "primary_version": primary_version,
        "system_manufacturer": (system_ctx or {}).get("system_manufacturer") or "",
        "system_model": (system_ctx or {}).get("system_model") or "",
        "service_tag": (system_ctx or {}).get("service_tag") or "",
        "video_controllers": (system_ctx or {}).get("video_controllers") or [],
    }


_PNP_CLASS_HW_HINTS = {
    "display": "gpu",
    "monitor": "display",
    "net": "network",
    "media": "audio",
    "bluetooth": "bluetooth",
    "camera": "webcam",
    "scsiadapter": "storage_controller",
    "diskdrive": "storage_controller",
    "usb": "usb_controller",
    "securitydevices": "fingerprint",
}


def _infer_vendor_from_device_name(device_name: str, pnp_class: str) -> str | None:
    """Vendor keyword for OEM/catalog lookup from device display name and class."""
    combined = f"{device_name} {pnp_class}"
    from bsod_hardware_wmi import _extract_vendor_from_string

    vendor = _extract_vendor_from_string(combined)
    if vendor:
        return vendor.lower()
    name_lower = (device_name or "").lower()
    if "nvidia" in name_lower or "geforce" in name_lower:
        return "nvidia"
    if "amd" in name_lower or "radeon" in name_lower:
        return "amd"
    if "intel" in name_lower and "intelligo" not in name_lower:
        return "intel"
    if "lg" in name_lower and "logitech" not in name_lower:
        return "lg"
    if "realtek" in name_lower:
        return "realtek"
    if "broadcom" in name_lower or "killer" in name_lower:
        return "broadcom" if "broadcom" in name_lower else "killer"
    if "mediatek" in name_lower:
        return "mediatek"
    if "qualcomm" in name_lower:
        return "qualcomm"
    if "microsoft basic display" in name_lower:
        return "intel"
    return None


def get_device_context_for_name(
    device_name: str,
    pnp_list: list | None,
    inventory: list | None,
    system_ctx: dict | None,
) -> dict:
    """Catalog context for a specific PnP device (generic drivers tab — no crash module)."""
    from bsod_hardware_wmi import _extract_vendor_from_string
    from bsod_crash_report import (
        _find_pnp_entity_by_device_name,
        lookup_inventory_row,
    )
    name = (device_name or "").strip()
    pnp_entity = _find_pnp_entity_by_device_name(pnp_list or [], name)
    instance_id = (pnp_entity or {}).get("DeviceID") or ""
    pnp_class = ((pnp_entity or {}).get("PNPClass") or "").strip()
    pnp_mfr = ((pnp_entity or {}).get("Manufacturer") or "").strip()
    pci_tokens = _pci_tokens_from_id(instance_id)
    vendor_key = None
    if pnp_mfr:
        vendor_key = (_extract_vendor_from_string(pnp_mfr) or "").lower() or None
    if not vendor_key:
        vendor_key = _infer_vendor_from_device_name(name, pnp_class)
    if not vendor_key and system_ctx:
        pnp_enr = (system_ctx.get("pnp_enrichment") or {}).get(name)
        if not pnp_enr:
            try:
                import device_enrichment as de
                lu = de.pnp_lookup_from_ctx(system_ctx)
                pnp_enr = de._match_pnp_enrichment(
                    name,
                    system_ctx.get("pnp_enrichment") or {},
                    lookup=lu,
                )
            except ImportError:
                pnp_enr = None
        if pnp_enr and pnp_enr.get("vendor_key"):
            vendor_key = pnp_enr.get("vendor_key")
    if not vendor_key:
        try:
            import device_enrichment as de
            vendor_key = de.infer_vendor_key(
                name,
                pnp_class,
                pnp_mfr,
                instance_id,
                edid_brand="",
                disk_model="",
                known_vendor_fn=_extract_vendor_from_string,
            )
        except ImportError:
            pass
    hw_category = _PNP_CLASS_HW_HINTS.get(pnp_class.lower(), "")
    pnp_class = _infer_pnp_class_for_device(
        name, vendor_key or "", pnp_class, hw_category
    )
    hw_category = _PNP_CLASS_HW_HINTS.get(pnp_class.lower(), hw_category)

    d = lookup_inventory_row(inventory, name)
    installed_rows = []
    if d:
        installed_rows.append({
            "name": name,
            "version": (d.get("version") or "").strip() or "?",
            "date": (d.get("date") or ""),
            "device_class": (d.get("device_class") or pnp_class).strip(),
        })
    elif name:
        installed_rows.append({
            "name": name,
            "version": "?",
            "date": "",
            "device_class": pnp_class,
        })

    primary_version = installed_rows[0]["version"] if installed_rows else "?"

    display_label = name
    if system_ctx:
        pnp_enr = (system_ctx.get("pnp_enrichment") or {}).get(name)
        if not pnp_enr:
            try:
                import device_enrichment as de
                lu = de.pnp_lookup_from_ctx(system_ctx)
                pnp_enr = de._match_pnp_enrichment(
                    name,
                    system_ctx.get("pnp_enrichment") or {},
                    lookup=lu,
                )
            except ImportError:
                pnp_enr = None
        if pnp_enr and pnp_enr.get("display_name"):
            enriched = pnp_enr["display_name"]
            if (
                _looks_like_realtek_wdm_version(primary_version)
                and (
                    "effects component" in enriched.lower()
                    or "universal service" in enriched.lower()
                )
                and "realtek" in name.lower()
            ):
                display_label = name
            else:
                display_label = enriched

    primary_version = _resolve_primary_installed_version(
        {
            "primary_version": primary_version,
            "instance_id": instance_id,
            "vendor_key": vendor_key or "",
            "device_label": display_label,
            "pnp_class": pnp_class,
            "target_device_name": name,
        },
        system_ctx,
    )
    if installed_rows:
        installed_rows[0]["version"] = primary_version

    parent_device_id = ""
    parent_device_name = ""
    catalog_role = ""
    catalog_has_swc_child = False
    catalog_skip_mscatalog = False
    if d:
        parent_device_id = (d.get("parent_device_id") or "").strip()
        parent_device_name = (d.get("parent_device_name") or "").strip()
        catalog_role = (d.get("catalog_role") or "").strip()
        catalog_has_swc_child = bool(d.get("catalog_has_swc_child"))
        catalog_skip_mscatalog = bool(d.get("catalog_skip_mscatalog"))

    out = {
        "driver": "",
        "device_label": display_label,
        "culprit_names": [name] if name else [],
        "instance_id": instance_id,
        "pci_tokens": pci_tokens,
        "pnp_class": pnp_class,
        "vendor_key": vendor_key or "",
        "hw_category": hw_category,
        "installed_rows": installed_rows,
        "primary_version": primary_version,
        "system_manufacturer": (system_ctx or {}).get("system_manufacturer") or "",
        "system_model": (system_ctx or {}).get("system_model") or "",
        "service_tag": (system_ctx or {}).get("service_tag") or "",
        "video_controllers": (system_ctx or {}).get("video_controllers") or [],
        "target_device_name": name,
        "display_name": display_label,
        "pnp_manufacturer": pnp_mfr,
        "parent_device_id": parent_device_id,
        "parent_device_name": parent_device_name,
        "catalog_role": catalog_role,
        "catalog_has_swc_child": catalog_has_swc_child,
        "catalog_skip_mscatalog": catalog_skip_mscatalog,
    }
    _apply_realtek_parent_hwid_ctx(out, pnp_list, system_ctx)
    return out
def _infer_pnp_class_for_device(
    name: str,
    vendor_key: str,
    pnp_class: str,
    hw_category: str,
) -> str:
    """Infer PnP class when hardware scan did not attach a PnP entity."""
    if (pnp_class or "").strip():
        return pnp_class.strip()
    nl = (name or "").lower()
    hc = (hw_category or "").lower()
    vk = (vendor_key or "").lower()
    if hc == "gpu" or vk in ("nvidia", "amd", "intel") and any(
        k in nl for k in ("geforce", "radeon", "graphics", "gpu", "display")
    ):
        return "display"
    if "bluetooth" in nl:
        return "bluetooth"
    if hc == "network" or any(
        k in nl for k in ("wi-fi", "wifi", "wireless", "ethernet", " wlan", "network")
    ):
        return "net"
    if hc == "audio" or any(
        k in nl for k in ("audio", "sound", "speaker", "microphone", "realtek audio")
    ):
        return "media"
    if hc == "webcam" or "camera" in nl or "webcam" in nl:
        return "camera"
    if hc == "storage_controller" or any(
        k in nl for k in ("nvme", "ssd", "sata", "storage controller")
    ):
        return "scsiadapter"
    if "usb" in nl and "controller" in nl:
        return "usb"
    return pnp_class


def _lookup_pnpsigned_version_from_index(
    ctx: dict, index: dict[str, str] | None
) -> str:
    if not index:
        return ""
    label = (ctx.get("device_label") or "").strip()
    target = (ctx.get("target_device_name") or label).strip()
    if not target:
        return ""
    tl = target.lower()
    if tl in index:
        return index[tl]
    vk = (ctx.get("vendor_key") or "").lower()
    best = ""
    best_score = 0
    for dn, ver in index.items():
        if tl == dn or tl in dn or dn in tl:
            score = 14 if tl == dn else 10
        else:
            tokens = [t for t in re.split(r"[^a-z0-9]+", tl) if len(t) >= 4]
            score = sum(3 for t in tokens[:5] if t in dn)
        if vk and vk in dn:
            score += 4
        if score > best_score:
            best_score = score
            best = ver
    return best if best_score >= 8 else ""


def _version_from_pnpsigned_inventory(ctx: dict) -> str:
    label = (ctx.get("device_label") or "").strip()
    target = (ctx.get("target_device_name") or label).strip()
    if not target:
        return ""
    idx = ctx.get("_pnpsigned_version_index")
    if isinstance(idx, dict):
        hit = _lookup_pnpsigned_version_from_index(ctx, idx)
        if hit:
            return hit
    tl = target.lower()
    vk = (ctx.get("vendor_key") or "").lower()
    best = ""
    best_score = 0
    import driver_catalog as _dc_catalog

    for row in _dc_catalog._get_pnpsigned_driver_rows():
        dn = (row.get("DeviceName") or "").strip()
        if not dn:
            continue
        ver = (row.get("DriverVersion") or "").strip()
        if not ver:
            continue
        dnl = dn.lower()
        mfr = (row.get("Manufacturer") or "").lower()
        score = 0
        if tl == dnl:
            score = 20
        elif tl in dnl or dnl in tl:
            score = 14
        else:
            tokens = [t for t in re.split(r"[^a-z0-9]+", tl) if len(t) >= 4]
            score = sum(3 for t in tokens[:5] if t in dnl)
        if vk and vk in mfr:
            score += 4
        if score > best_score:
            best_score = score
            best = ver
    return best if best_score >= 8 else ""


def _resolve_primary_installed_version(ctx: dict, system_ctx: dict | None) -> str:
    """Prefer WMI inventory; fall back to PnP signed drivers and video controllers."""
    idx = ctx.get("_pnpsigned_version_index") or (system_ctx or {}).get(
        "_pnpsigned_version_index"
    )
    if isinstance(idx, dict):
        hit = _lookup_pnpsigned_version_from_index(ctx, idx)
        if hit:
            return hit
    inst = (ctx.get("primary_version") or "").strip()
    if inst and inst not in ("?", "—", "N/A", "unknown"):
        return inst
    pnp_id = (ctx.get("instance_id") or "").upper()
    vk = (ctx.get("vendor_key") or "").lower()
    label = (ctx.get("device_label") or "").lower()
    pnp_class = (ctx.get("pnp_class") or "").lower()
    vcs = (ctx.get("video_controllers") or []) or (
        (system_ctx or {}).get("video_controllers") or []
    )
    for vc in vcs:
        if not isinstance(vc, dict):
            continue
        ver = (vc.get("driver_version") or "").strip()
        if not ver:
            continue
        vc_pnp = (vc.get("pnp_device_id") or "").upper()
        vc_name = (vc.get("name") or "").lower()
        if pnp_id and vc_pnp and (pnp_id[:28] in vc_pnp or vc_pnp[:28] in pnp_id):
            return ver
        if pnp_class == "display" and vk == "nvidia" and "nvidia" in vc_name:
            return ver
        if pnp_class == "display" and vk == "amd" and (
            "amd" in vc_name or "radeon" in vc_name
        ):
            return ver
        if label and vc_name and (label in vc_name or vc_name in label):
            return ver
    pnpsigned = _version_from_pnpsigned_inventory(ctx)
    if pnpsigned:
        return pnpsigned
    return inst or "?"

__all__ = [
    "_DRIVER_SCAN_EXCLUDED_PNP_CLASSES",
    "_ctx_device_label",
    "_ctx_is_amd_device",
    "_device_is_amd_chipset_plumbing",
    "_ctx_is_intel_device",
    "_device_is_intel_chipset_plumbing",
    "_intel_driver_hint_from_ctx",
    "_device_is_intel_me_device",
    "_device_is_chipset_plumbing",
    "_ctx_is_chipset_component_plumbing",
    "_device_is_amd_media",
    "_device_is_amd_audio",
    "_nvidia_is_audio_or_usb_component",
    "_nvidia_is_audio_component",
    "_nvidia_gpu_driver_lookup_applicable",
    "_nvidia_ctx_eligible",
    "_ctx_is_amd_chipset_platform_row",
    "_ctx_is_intel_chipset_platform_row",
    "is_driver_scan_excluded_ctx",
    "is_driver_scan_excluded_device",
    "_pci_tokens_from_id",
    "_infer_vendor_from_device_name",
    "_infer_pnp_class_for_device",
    "_lookup_pnpsigned_version_from_index",
    "_version_from_pnpsigned_inventory",
    "_resolve_primary_installed_version",
    "_apply_realtek_parent_hwid_ctx",
    "get_device_context",
    "get_device_context_for_name",
]
