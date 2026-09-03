"""Culprit device matching and crash attribution context (extracted from bsod_crash_report)."""

from __future__ import annotations

import re

from bsod_hardware_wmi import (
    CHIPSET_DEVICE_AMD,
    CHIPSET_DEVICE_INTEL,
    _extract_vendor_from_string,
    chipset_driver_catalog_entries,
)


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


_PLATFORM_CPU_MODULES = frozenset({"authenticamd", "genuineintel", "centaurhauls"})


POSSIBLE_DRIVERS = {
    "authenticamd": (
        ["BIOS/UEFI (CPU microcode)", "AMD Chipset Driver (chipset software from amd.com)", "amd_sata.sys", "amd_xhci.sys"],
        ["AMD Radeon (amdkmdag.sys)", "NVMe/SSD driver", "Other PCIe card driver"],
        ["BIOS then AMD Chipset then GPU (if present) then storage (NVMe/SATA if present)"],
    ),
    "genuineintel": (
        ["BIOS/UEFI (CPU microcode)", "Intel Chipset Driver", "Intel ME drivers", "iastor.sys (Intel RST)"],
        ["Intel GPU (igdkmd64.sys)", "NVMe/SSD driver", "Other PCIe card driver"],
        ["BIOS then Intel Chipset then GPU (if present) then storage (NVMe/SATA if present)"],
    ),
    "ntoskrnl": (
        ["Kernel fault usually caused by a driver - check loaded drivers in dump"],
        ["Often GPU or storage driver - update graphics and storage drivers"],
        ["Update GPU, storage, network, chipset drivers; check antivirus; run sfc /scannow"],
    ),
    "hal": (
        ["HAL fault usually from chipset or firmware - update BIOS and chipset drivers"],
        ["Sometimes PCIe device - update GPU or other add-in card drivers"],
        ["Update BIOS, chipset drivers, GPU driver"],
    ),
    "ndis": (
        ["Your NIC or WiFi driver - check Device Manager > Network adapters for the actual driver name"],
        [],
        ["Update network adapter driver from PC/NIC manufacturer - ndis is the framework, not the culprit"],
    ),
    "netio": (
        ["Network driver (NIC, WiFi, VPN) - check Device Manager > Network adapters"],
        [],
        ["Update network driver; temporarily disable VPN/antivirus to test"],
    ),
    "dxgkrnl": (
        [],
        ["GPU driver - update NVIDIA/AMD/Intel graphics from vendor site"],
        ["Update GPU driver - dxgkrnl is DirectX kernel, GPU driver is the likely cause"],
    ),
    "win32k": (
        [],
        ["GPU driver - update graphics driver"],
        ["Update GPU driver - often display driver related"],
    ),
    "storport": (
        ["Storage miniport - check which disk controller; update chipset or storage driver"],
        ["NVMe driver or SSD firmware - update from drive manufacturer"],
        ["Update chipset driver, NVMe/SATA driver, or SSD firmware"],
    ),
}

DRIVER_VENDOR_PREFIX = {
    # Longer / more specific prefixes first (lookup sorts by length descending).
    "mediatek": "MediaTek",
    "realtek": "Realtek",
    "qualcomm": "Qualcomm",
    "broadcom": "Broadcom",
    "marvell": "Marvell",
    "steelseries": "SteelSeries",
    "synaptics": "Synaptics",
    "logitech": "Logitech",
    "killer": "Killer",
    "samsung": "Samsung",
    "liteon": "Lite-On",
    "asmedia": "ASMedia",
    "creative": "Creative",
    "conexant": "Conexant",
    "goodix": "Goodix",
    "corsair": "Corsair",
    "elgato": "Elgato",
    "kionix": "Kionix",
    "razer": "Razer",
    "nvidia": "NVIDIA",
    "nv": "NVIDIA",
    "amd": "AMD",
    "ati": "AMD",
    "intel": "Intel",
    "rtwlane": "Realtek",
    "rtwlan": "Realtek",
    "rtw": "Realtek",
    "rtl": "Realtek",
    "rtk": "Realtek",
    "qca": "Qualcomm",
    "atheros": "Qualcomm",
    "athw": "Qualcomm",
    "ath": "Qualcomm",
    "bcmwl": "Broadcom",
    "bcm": "Broadcom",
    "mtkwl": "MediaTek",
    "mt7921": "MediaTek",
    "mtk": "MediaTek",
    "mt79": "MediaTek",
    "asmt": "ASMedia",
    "e1d65": "Intel",
    "e1i65": "Intel",
    "e2f68": "Intel",
    "netwtw": "Intel",
    "igdkmd": "Intel",
    "igfx": "Intel",
}

def _driver_name_from_recommendation(text: str) -> str | None:
    """Extract a .sys driver base name from a recommendation string, or None if none."""
    if not text:
        return None
    m = re.search(r"([a-zA-Z0-9_]+)\.sys", text, re.IGNORECASE)
    return m.group(1).lower() if m else None

DRIVER_TO_HARDWARE = {
    # Storage - SATA drivers
    "amd_sata": ("storage_controller", "sata"),
    "storahci": ("storage_controller", "sata"),
    "iastor": ("storage_controller", "sata"),
    "iastoravc": ("storage_controller", "sata"),
    "msahci": ("storage_controller", "sata"),
    # GPU - NVIDIA
    "nvlddmkm": ("gpu", "nvidia"),
    "nvwgf2umx": ("gpu", "nvidia"),
    # GPU - AMD
    "amdkmdag": ("gpu", "amd"),
    "amdkmdap": ("gpu", "amd"),
    "atikmdag": ("gpu", "amd"),
    "atikmpag": ("gpu", "amd"),
    # GPU - Intel
    "igdkmd64": ("gpu", "intel"),
    "igdkmdn64": ("gpu", "intel"),
    # Network - Intel
    "e1i65x64": ("network", "intel"),
    "e1d65x64": ("network", "intel"),
    "e1c62x64": ("network", "intel"),
    "iqvw64e": ("network", "intel"),
    "netwtw": ("network", "intel"),
    # Network - Realtek
    "rt640x64": ("network", "realtek"),
    "rtl8168": ("network", "realtek"),
    "rtl8125": ("network", "realtek"),
    "rtwlane": ("network", "realtek"),
    "rtwlane_": ("network", "realtek"),
    "rtwlan": ("network", "realtek"),
    "rtw88": ("network", "realtek"),
    "rtw89": ("network", "realtek"),
    "rtux64w": ("network", "realtek"),
    # Network - Broadcom
    "b57nd60a": ("network", "broadcom"),
    "bcmwl63a": ("network", "broadcom"),
    # Network - Qualcomm/Atheros/Killer
    "qca": ("network", "qualcomm"),
    "atheros": ("network", "qualcomm"),
    "killernetworkbfm": ("network", "killer"),
    "klnethub": ("network", "killer"),
    "qcamain10x64": ("network", "qualcomm"),
    # Network - Marvell
    "mrvlpcie8897": ("network", "marvell"),
    "yk62x64": ("network", "marvell"),
    # Network - MediaTek
    "mtkwl6ex": ("network", "mediatek"),
    "mtkwl6e": ("network", "mediatek"),
    "mt7921": ("network", "mediatek"),
    "mt7921au": ("network", "mediatek"),
    "mt76x": ("network", "mediatek"),
    # Audio - Realtek
    "rtkvhd64": ("audio", "realtek"),
    "rtkhdaud": ("audio", "realtek"),
    "rtaudio": ("audio", "realtek"),
    # Audio - Creative
    "ctaud2k": ("audio", "creative"),
    "ctoss2k": ("audio", "creative"),
    # Audio - Conexant/Synaptics
    "cxaudiofilter": ("audio", "conexant"),
    "synapdaudio": ("audio", "synaptics"),
    # USB - AMD
    "amd_xhci": ("usb_controller", "amd"),
    "amdxhc": ("usb_controller", "amd"),
    # Chipset / platform - AMD
    "amdpsp": ("chipset", "amd"),
    "amdgpio": ("chipset", "amd"),
    "amdgpio2": ("chipset", "amd"),
    "amdi2c": ("chipset", "amd"),
    "amdsmbus": ("chipset", "amd"),
    "amdppm": ("chipset", "amd"),
    "amdfendr": ("chipset", "amd"),
    "amdfend": ("chipset", "amd"),
    "amdfch": ("chipset", "amd"),
    "amd_bus": ("chipset", "amd"),
    "amdpcidev": ("chipset", "amd"),
    "amdpci": ("chipset", "amd"),
    # Chipset / platform - Intel
    "iaisp": ("chipset", "intel"),
    "intelpmt": ("chipset", "intel"),
    # USB - Intel
    "iusb3xhc": ("usb_controller", "intel"),
    # USB - ASMedia
    "asmtxhci": ("usb_controller", "asmedia"),
    "asmthub3": ("usb_controller", "asmedia"),
    # USB - Renesas
    "nusb3xhc": ("usb_controller", "renesas"),
    # USB - Fresco Logic
    "flxhcih": ("usb_controller", "fresco"),
    # Bluetooth - Intel
    "ibtusb": ("bluetooth", "intel"),
    "intelbtm": ("bluetooth", "intel"),
    # Bluetooth - Realtek
    "rtkbtfilter": ("bluetooth", "realtek"),
    "rtbth": ("bluetooth", "realtek"),
    # Bluetooth - Broadcom
    "bcmbtums": ("bluetooth", "broadcom"),
    "bthavrcptg": ("bluetooth", "broadcom"),
    # Bluetooth - Qualcomm
    "qcausbfilm": ("bluetooth", "qualcomm"),
    # Bluetooth - MediaTek
    "mtkbtfilter": ("bluetooth", "mediatek"),
    # Webcam
    "usbvideo": ("webcam", None),  # Generic USB video
    # Fingerprint
    "goodixfp": ("fingerprint", "goodix"),
    "wbf": ("fingerprint", None),  # Windows Biometric Framework
    "egismof": ("fingerprint", "egis"),
    # Thunderbolt
    "tbthcm": ("thunderbolt", "intel"),
    "nhi": ("thunderbolt", None),
    # Card reader
    "rtsuer": ("card_reader", "realtek"),
    "rtsuerhub": ("card_reader", "realtek"),
    "o2mdss": ("card_reader", "o2micro"),
    "alcor": ("card_reader", "alcor"),
    "bayhubsdw": ("card_reader", "bayhub"),
}

def _recommendation_applies_to_system(item: str, present_drivers: set[str], ctx: dict) -> bool:
    """
    Return True if this recommendation item applies to the current system's ACTUAL HARDWARE.
    Uses smart vendor extraction to match recommendations to hardware that exists.
    """
    item_lower = item.lower()
    drv = _driver_name_from_recommendation(item)
    hardware_vendors = ctx.get("hardware_vendors", {})
    gpu_vendors = ctx.get("gpu_vendors_present", set())
    
    # If item mentions a specific .sys driver, check if that driver maps to hardware we have
    if drv:
        if drv not in present_drivers:
            return False  # Driver not on system - skip
        
        # Check hardware mapping for known drivers
        if drv in DRIVER_TO_HARDWARE:
            category, vendor = DRIVER_TO_HARDWARE[drv]
            
            if category == "storage_controller":
                if vendor == "sata" and not ctx.get("has_sata", True):
                    return False  # No SATA hardware
            elif category == "gpu":
                if vendor and vendor not in gpu_vendors:
                    return False  # That GPU vendor not present
            elif category in hardware_vendors and vendor:
                if vendor not in hardware_vendors.get(category, set()):
                    return False  # That vendor's hardware not present in this category
        
        # Handle partial driver name matches (e.g., "netwtw04" matches "netwtw")
        for drv_prefix, (category, vendor) in DRIVER_TO_HARDWARE.items():
            if drv.startswith(drv_prefix) or (len(drv) >= 5 and drv_prefix.startswith(drv[:5])):
                if category == "gpu":
                    if vendor and vendor not in gpu_vendors:
                        return False
                elif category in hardware_vendors and vendor:
                    if vendor not in hardware_vendors.get(category, set()):
                        return False
                break
    
    # Smart vendor detection from recommendation text (for recommendations without .sys)
    # Extract vendor from the recommendation text and check if that vendor's hardware exists
    if hardware_vendors:
        # Get all vendors mentioned in the recommendation
        text_vendor = _extract_vendor_from_string(item_lower) if '_extract_vendor_from_string' in dir() else None
        
        # Category-specific vendor checks using smart matching
        category_keywords = {
            "network": ["network", "wifi", "wireless", "ethernet", "lan", "nic", "adapter"],
            "audio": ["audio", "sound", "speaker", "realtek hd", "sound card"],
            "bluetooth": ["bluetooth", "bt "],
            "webcam": ["webcam", "camera"],
            "fingerprint": ["fingerprint", "biometric"],
            "card_reader": ["card reader", "sd card", "memory card"],
            "thunderbolt": ["thunderbolt", "tb3", "tb4"],
            "usb_controller": ["usb controller", "xhci", "ehci"],
        }
        
        for category, keywords in category_keywords.items():
            if any(kw in item_lower for kw in keywords):
                # This recommendation is about this category
                category_vendors = hardware_vendors.get(category, set())
                if category_vendors:
                    # We have detected vendors for this category - check if recommendation matches
                    rec_vendor = _extract_vendor_from_string(item_lower)
                    if rec_vendor and rec_vendor not in category_vendors:
                        # Recommendation mentions a specific vendor that's not in our hardware
                        return False
                break  # Only check one category per recommendation
    
    return True

def _filter_possible_drivers_list(candidate_list: list[str], present_drivers: set[str], ctx: dict) -> list[str]:
    """Return only items that apply to this system's actual hardware (not just driver files)."""
    return [x for x in candidate_list if _recommendation_applies_to_system(x, present_drivers, ctx)]

def _infer_driver_vendor(drv_base: str) -> str | None:
    """Infer device/vendor from driver filename for unmapped drivers."""
    for prefix in sorted(DRIVER_VENDOR_PREFIX.keys(), key=len, reverse=True):
        if drv_base.startswith(prefix):
            return DRIVER_VENDOR_PREFIX[prefix]
    return None

_HW_CATEGORY_TO_CLASSES = {
    "gpu": ("display",),
    "network": ("net",),
    "audio": ("media",),
    "storage_controller": ("scsiadapter", "diskdrive", "volume"),
    "bluetooth": ("bluetooth",),
    "usb_controller": ("usb",),
    "chipset": ("system", "processor", "computer"),
    "webcam": ("camera",),
    "fingerprint": ("securitydevices",),
    "thunderbolt": ("usb",),
    "card_reader": ("usb",),
}

_AMD_GPU_DRIVER_FRAGMENTS = ("amdkmdag", "amdkmdap", "atikmdag", "atikmpag")

_AMD_CHIPSET_DRIVER_FRAGMENTS = (
    "amdpsp", "amdgpio", "amdi2c", "amdsmbus", "amdppm", "amdfch", "amdfend",
    "amd_bus", "amdpcidev", "amdpci", "amd_sata", "acpi",
)

_VENDOR_IN_NAME_RE = {
    "intel": re.compile(r"(?<![a-z])intel(?![a-z])", re.IGNORECASE),
}

_AMD_CHIPSET_DEVICE_RE = re.compile(
    r"gpio|smbus|chipset|pci express|crash defender|processor|fch|psp|platform|"
    r"sm bus|serial bus|i2c|power management",
    re.IGNORECASE,
)

_INTEL_CHIPSET_DRIVER_FRAGMENTS = ("iaisp", "intelpmt", "intelppm", "intelpep")

_STORAGE_FAULT_MODULES = frozenset({
    "ntfs", "storport", "stornvme", "storahci", "volmgr", "volmgrx", "partmgr",
    "disk", "fltmgr", "nvme", "iastor", "iastoravc", "amd_sata", "fvevol",
})

_NETWORK_FAULT_MODULES = frozenset({"ndis", "netio", "tcpip", "afd"})

_VIRTUAL_NET_DEVICE_RE = re.compile(
    r"wan miniport|virtual adapter|wi-?fi direct|kernel debug|"
    r"bluetooth.*personal area|loopback|isatap|teredo|6to4|pseudo",
    re.IGNORECASE,
)

_GRAPHICS_FAULT_MODULES = frozenset({
    "win32k", "win32kbase", "win32kfull", "dxgkrnl", "dxgmms2", "watchdog",
})

_DRIVER_CLASS_HINTS = (
    (("nvlddmkm", "nvwgf2um", "atikmdag", "amdkmdag", "amdkmdap", "atikmpag",
      "igdkmd", "igfx", "igdkmd64"), "display"),
    (("rtkvhd", "rtkhda", "rtaudio", "nvhda", "hdaudio", "ctaud", "cxaudio"), "media"),
    (("netwtw", "rtwlan", "rtwlane", "rtw88", "rtw89", "rtl8168", "rtl8125", "rt640",
      "athw", "bcmwl", "qcamain", "mtkwl", "mt7921", "mt76x", "e1d65", "e1i65",
      "e2f68", "killernetwork", "klnethub", "mrvlpcie"), "net"),
    (("rtkbt", "ibtusb", "intelbtm", "bcmbt", "mtkbt", "qcausb"), "bluetooth"),
    (("nvme", "stornvme", "storahci", "iastor", "amdsata", "scsi"), "scsiadapter"),
)

def _is_amd_gpu_driver(drv_base: str) -> bool:
    return any(k in drv_base for k in _AMD_GPU_DRIVER_FRAGMENTS)

def _is_amd_chipset_driver(drv_base: str) -> bool:
    if drv_base in ("authenticamd", "genuineintel"):
        return drv_base == "authenticamd"
    return any(k in drv_base for k in _AMD_CHIPSET_DRIVER_FRAGMENTS)

def _is_intel_chipset_driver(drv_base: str) -> bool:
    return any(k in drv_base for k in _INTEL_CHIPSET_DRIVER_FRAGMENTS)

def _vendor_chipset_devices(devices: list, vendor_word: str) -> set:
    """AMD/Intel platform devices (GPIO, SMBus, processor, etc.) for chipset driver faults."""
    names = set()
    for d in devices:
        name = d.get("name", "") or ""
        if not _device_name_has_vendor(name, vendor_word):
            continue
        cls = (d.get("device_class", "") or "").lower()
        if cls in ("system", "processor", "computer") or _AMD_CHIPSET_DEVICE_RE.search(name):
            names.add(name)
    return names

def _driver_hardware_lookup(drv_base: str) -> tuple[str | None, tuple[str, ...] | None]:
    """Longest DRIVER_TO_HARDWARE key match -> (vendor keyword, device classes)."""
    best_key = None
    best_entry = None
    for key, entry in DRIVER_TO_HARDWARE.items():
        if key in drv_base or drv_base == key:
            if best_key is None or len(key) > len(best_key):
                best_key = key
                best_entry = entry
    if not best_entry:
        return None, None
    hw_cat, vendor = best_entry
    classes = _HW_CATEGORY_TO_CLASSES.get(hw_cat)
    return (vendor.lower() if vendor else None), classes

def _device_name_has_vendor(name: str, vendor_kw: str) -> bool:
    """True if device display name belongs to vendor_kw (not a substring false positive)."""
    if not name or not vendor_kw:
        return False
    vk = vendor_kw.lower()
    pat = _VENDOR_IN_NAME_RE.get(vk)
    if pat:
        return bool(pat.search(name))
    return vk in name.lower()

def _devices_matching(devices: list, vendor_kw: str | None,
                      classes: tuple[str, ...] | None) -> set:
    """Filter devices by optional vendor substring and device class(es)."""
    pool = devices
    if vendor_kw:
        pool = [d for d in pool if _device_name_has_vendor(d.get("name", "") or "", vendor_kw)]
    if classes:
        cls_set = {c.lower() for c in classes}
        scoped = [d for d in pool if (d.get("device_class", "") or "").lower() in cls_set]
        return {d.get("name", "") for d in scoped}
    if pool:
        return {d.get("name", "") for d in pool}
    return set()

def find_culprit_devices(devices: list, faulting_driver: str | None) -> set:
    """Names of devices in `devices` whose driver is implicated by `faulting_driver`.

    Resolution order: known driver->hardware map, storage/network/graphics stack modules,
    then vendor prefix + class hints. Returns empty when no physical device can be tied
    (e.g. unmapped third-party .sys with no vendor in the device list).
    """
    if not faulting_driver or not devices:
        return set()
    base = faulting_driver.lower().replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()
    if not base:
        return set()

    vendor_kw, classes = _driver_hardware_lookup(base)
    if vendor_kw is not None or classes:
        matched = _devices_matching(devices, vendor_kw, classes)
        if matched:
            return matched
        # Chipset drivers often map to SYSTEM-class devices; broaden within vendor.
        if classes and "system" in classes and vendor_kw:
            chipset = _vendor_chipset_devices(devices, vendor_kw)
            if chipset:
                return chipset

    if _is_amd_chipset_driver(base):
        matched = _vendor_chipset_devices(devices, "amd")
        if matched:
            return matched

    if _is_intel_chipset_driver(base):
        matched = _vendor_chipset_devices(devices, "intel")
        if matched:
            return matched

    if base in _STORAGE_FAULT_MODULES:
        matched = _devices_matching(devices, None, _HW_CATEGORY_TO_CLASSES["storage_controller"])
        if matched:
            return matched

    if base in _NETWORK_FAULT_MODULES:
        net_devs = [
            d for d in devices
            if (d.get("device_class", "") or "").lower() == "net"
            and not _VIRTUAL_NET_DEVICE_RE.search(d.get("name", "") or "")
        ]
        if net_devs:
            return {d.get("name", "") for d in net_devs}

    if base in _GRAPHICS_FAULT_MODULES:
        matched = _devices_matching(devices, None, _HW_CATEGORY_TO_CLASSES["gpu"])
        if matched:
            return matched

    vendor = _infer_driver_vendor(base)
    if not vendor:
        return set()
    vendor_word = vendor.split(" (")[0].split("/")[0].strip().lower()
    if not vendor_word:
        return set()
    if vendor_word == "amd" and _is_amd_chipset_driver(base):
        matched = _vendor_chipset_devices(devices, "amd")
        if matched:
            return matched
    if vendor_word == "intel" and _is_intel_chipset_driver(base):
        matched = _vendor_chipset_devices(devices, "intel")
        if matched:
            return matched
    class_hint = None
    for keys, cls in _DRIVER_CLASS_HINTS:
        if any(k in base for k in keys):
            class_hint = (cls,)
            break
    if class_hint:
        matched = _devices_matching(devices, vendor_word, class_hint)
        if matched:
            return matched

    signed_matches: set[str] = set()
    for d in devices:
        dn = (d.get("name") or "").strip()
        if not dn:
            continue
        signed = (d.get("driver") or "").lower().replace(".sys", "").replace(".dll", "")
        if signed and base and (base == signed or base in signed or signed in base):
            signed_matches.add(dn)
    if signed_matches:
        return signed_matches

    return set()

CRASH_SYNTH_DEVICE_PREFIX = "__crash__"

def crash_synthetic_device_key(driver: str | None) -> str:
    """Stable list key when no PnP row matches the faulting module yet."""
    base = (driver or "").strip().lower().replace(".sys", "").replace(".dll", "")
    return f"{CRASH_SYNTH_DEVICE_PREFIX}{base or 'module'}"

def is_crash_synthetic_device_key(name: str | None) -> bool:
    return bool(name) and str(name).startswith(CRASH_SYNTH_DEVICE_PREFIX)

def is_platform_chipset_device_key(name: str | None) -> bool:
    """Synthetic AMD/Intel platform rows — not useful in bulk hardware update scans."""
    n = (name or "").strip()
    return n in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL)

def has_crash_faulting_driver(driver: str | None) -> bool:
    """True when minidump/logs named an actionable faulting driver (not CPU id or kernel shim)."""
    base = (driver or "").strip().lower().replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()
    if not base:
        return False
    if is_kernel_shim_fault_module(driver):
        return False
    return base not in _PLATFORM_CPU_MODULES


def is_kernel_shim_fault_module(driver: str | None) -> bool:
    """True for ntoskrnl/hal/ndis-style modules — not a catalog row to update."""
    base = (driver or "").strip().lower().replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()
    if not base:
        return False
    return base in _bc("_MISLEADING_FAULT_MODULES") or base in _bc("_KERNEL_SHIM_MODULES")

def device_inventory_for_matching(bios_driver_info: dict | None) -> list:
    """Device list used for culprit matching (full list if loaded, else filtered inventory)."""
    if not bios_driver_info:
        return []
    return (
        bios_driver_info.get("all_drivers")
        or bios_driver_info.get("device_inventory")
        or bios_driver_info.get("drivers")
        or []
    )

def lookup_inventory_row(inventory: list | None, device_name: str) -> dict | None:
    """Match signed-driver inventory by name or display_name (case-insensitive)."""
    name = (device_name or "").strip()
    if not name or not inventory:
        return None
    nl = name.lower()
    by_name: dict[str, dict] = {}
    by_display: dict[str, dict] = {}
    for d in inventory:
        if not isinstance(d, dict):
            continue
        n = (d.get("name") or "").strip()
        if n:
            by_name[n.lower()] = d
        disp = (d.get("display_name") or "").strip()
        if disp:
            by_display[disp.lower()] = d
    if nl in by_name:
        return dict(by_name[nl])
    if nl in by_display:
        return dict(by_display[nl])
    for key, d in by_name.items():
        if nl in key or key in nl:
            return dict(d)
    return None

def _culprit_info_row_is_placeholder(row: dict | None) -> bool:
    name = ((row or {}).get("name") or "").strip()
    if not name:
        return True
    if name.startswith("Device for module"):
        return True
    return "not matched" in name.lower()

def platform_chipset_crash_attention(
    driver: str | None,
    *,
    system_ctx: dict | None = None,
    code_val: int | None = None,
    cause_type: dict | None = None,
    fix_plan: dict | None = None,
    has_crash_context: bool = True,
) -> bool:
    """True when crash logs implicate platform/chipset rather than a named .sys module."""
    if has_crash_faulting_driver(driver):
        return False
    if not has_crash_context:
        return False
    ctx = system_ctx or {}
    label = (cause_type or {}).get("label") or ""
    if code_val in (0x124, 0x7F, 0x9C):
        return True
    if any(k in label for k in ("Platform", "WHEA", "Hardware", "thermal")):
        return True
    ff = (fix_plan or {}).get("focus") or ""
    if ff in (_bc("FIX_CPU_PLATFORM"), _bc("FIX_WHEA_COMPONENT"), _bc("FIX_UNCERTAIN")):
        return True
    return bool(ctx.get("has_amd_chipset") or ctx.get("has_intel_chipset"))

def resolve_crash_culprit_context(
    driver: str | None,
    bios_driver_info: dict | None,
    *,
    code_val: int | None = None,
    system_ctx: dict | None = None,
    cause_type: dict | None = None,
    fix_plan: dict | None = None,
    has_crash_context: bool = True,
) -> dict:
    """Single source for culprit_driver_info, culprit_callout, and device name keys."""
    inventory = device_inventory_for_matching(bios_driver_info)
    common_devices = (bios_driver_info or {}).get("drivers") or []
    ctx = system_ctx or {}

    empty: dict = {
        "culprit_driver_info": [],
        "culprit_callout": None,
        "culprit_device_names": set(),
        "platform_chipset": False,
    }

    if platform_chipset_crash_attention(
        driver,
        system_ctx=ctx,
        code_val=code_val,
        cause_type=cause_type,
        fix_plan=fix_plan,
        has_crash_context=has_crash_context,
    ):
        names: set[str] = set()
        for d in chipset_driver_catalog_entries(ctx):
            n = (d.get("name") or "").strip().lower()
            if n:
                names.add(n)
        empty["platform_chipset"] = True
        empty["culprit_device_names"] = names
        return empty

    if not has_crash_faulting_driver(driver):
        return empty

    culprit_driver_info = _bc("get_culprit_device_driver_info")(driver, inventory)
    culprit_callout = build_culprit_system_callout(
        driver, common_devices, inventory, code_val
    )

    names = {
        n.strip().lower()
        for n in find_culprit_devices(inventory, driver)
        if n and n.strip()
    }
    for info in culprit_driver_info:
        if not _culprit_info_row_is_placeholder(info):
            key = (info.get("name") or "").strip().lower()
            if key:
                names.add(key)
    if culprit_callout:
        for raw in culprit_callout.get("devices") or []:
            key = str(raw or "").strip().lower()
            if key:
                names.add(key)
    if not names and not is_kernel_shim_fault_module(driver):
        names.add(crash_synthetic_device_key(driver).lower())

    return {
        "culprit_driver_info": culprit_driver_info,
        "culprit_callout": culprit_callout,
        "culprit_device_names": names,
        "platform_chipset": False,
    }

def refresh_model_culprit_fields(
    model: dict,
    bios_driver_info: dict | None,
    *,
    system_ctx: dict | None = None,
) -> bool:
    """Reconcile culprit fields after inventory grows; returns True if display fields changed."""
    driver = model.get("driver")
    resolved = resolve_crash_culprit_context(
        driver,
        bios_driver_info,
        code_val=model.get("stop_code_val"),
        system_ctx=system_ctx or model.get("system_ctx"),
        cause_type=model.get("cause_type"),
        fix_plan=model.get("fix_plan"),
        has_crash_context=True,
    )
    old_info = model.get("culprit_driver_info")
    old_callout = model.get("culprit_callout")
    old_names = model.get("culprit_device_names")
    model["culprit_driver_info"] = resolved["culprit_driver_info"]
    model["culprit_callout"] = resolved["culprit_callout"]
    model["culprit_device_names"] = sorted(resolved["culprit_device_names"])
    changed = (
        old_info != resolved["culprit_driver_info"]
        or old_callout != resolved["culprit_callout"]
        or old_names != model["culprit_device_names"]
    )
    ct = model.get("cause_type") or {}
    if ct.get("driver_actionable") and driver:
        pnp_list = ((system_ctx or model.get("system_ctx") or {}).get("pnp_list")) or []
        inv = device_inventory_for_matching(bios_driver_info)
        new_opts = _bc("build_driver_update_options")(
            driver,
            pnp_list,
            system_ctx or model.get("system_ctx") or {},
            bios_driver_info or {},
            inv,
        )
        if new_opts != model.get("driver_update_options"):
            model["driver_update_options"] = new_opts
            changed = True
    return changed

def build_culprit_system_callout(
    faulting_driver: str | None,
    common_devices: list,
    inventory: list,
    code_val: int | None = None,
) -> dict | None:
    """Banner data when crash-related devices are not in the Common devices list."""
    if not faulting_driver:
        return None
    culprits = find_culprit_devices(inventory, faulting_driver)
    common_names = {d.get("name") for d in common_devices if d.get("name")}
    outside = sorted(n for n in culprits if n not in common_names)
    if not outside:
        return None
    base = faulting_driver.lower().replace(".sys", "").replace(".dll", "").strip()
    if _is_amd_chipset_driver(base):
        summary = "Update the AMD Chipset Driver package from amd.com (includes GPIO, SMBus, PSP, and related platform drivers)."
    elif _is_intel_chipset_driver(base):
        summary = "Update Intel chipset drivers from your PC or motherboard vendor, or Intel's download center."
    else:
        explanation = _bc("get_faulting_device_explanation")(faulting_driver, code_val, None, None)
        summary = ""
        if explanation:
            for line in explanation.split("\n"):
                line = line.strip()
                if line.startswith("Action:"):
                    summary = line.replace("Action:", "").strip()
                    break
            if not summary:
                summary = explanation.split("\n")[0].strip()
    return {
        "driver": faulting_driver,
        "devices": outside,
        "summary": summary,
    }
