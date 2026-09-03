"""WMI hardware profile, driver inventory, and device lists."""

from __future__ import annotations

import json
import os
import re
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

import device_enrichment as de
from bsod_runtime import run_powershell
import bsod_runtime as rt

CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"

# DEVPKEY_Device_Parent is queried for these classes during hardware scan (PS 5.1
# cannot bulk-fetch parents; ~20 SWC/APO nodes ≈ few seconds vs minutes for all PnP).
_PNP_PARENT_LOOKUP_CLASSES = frozenset(
    {"softwarecomponent", "audioprocessingobject", "softwaredevice"}
)


def amd_chipset_applicable(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    return bool(ctx.get("has_amd_chipset") or ctx.get("cpu_vendor") == "amd")


def intel_chipset_applicable(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    return bool(ctx.get("has_intel_chipset") or ctx.get("cpu_vendor") == "intel")


def nvidia_driver_lookup_applicable(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    if (ctx.get("gpu_vendor") or "").lower() == "nvidia":
        return True
    present = ctx.get("gpu_vendors_present") or set()
    if isinstance(present, (list, tuple)):
        present = set(present)
    return "nvidia" in present


def amd_driver_lookup_applicable(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    if amd_chipset_applicable(ctx):
        return True
    if (ctx.get("gpu_vendor") or "").lower() == "amd":
        return True
    gpus = ctx.get("gpu_vendors_present") or set()
    if isinstance(gpus, (list, tuple)):
        gpus = set(gpus)
    if "amd" in gpus:
        return True
    return vendor_present_in_hardware(ctx, "amd")


def _hardware_vendors_map(ctx: dict) -> dict[str, set[str]]:
    raw = ctx.get("hardware_vendors") or {}
    out: dict[str, set[str]] = {}
    for category, vendors in raw.items():
        if isinstance(vendors, (list, tuple, set)):
            out[str(category)] = {str(v).lower() for v in vendors if v}
        elif vendors:
            out[str(category)] = {str(vendors).lower()}
    return out


def vendor_present_in_hardware(system_ctx: dict | None, vendor: str) -> bool:
    """True when WMI inventory recorded this vendor on any hardware category."""
    needle = (vendor or "").lower().strip()
    if not needle:
        return False
    for vendors in _hardware_vendors_map(system_ctx or {}).values():
        if needle in vendors:
            return True
    return False


def catalog_hardware_context_confident(system_ctx: dict | None) -> bool:
    """Enough platform context to safely skip absent vendors during catalog Search."""
    ctx = system_ctx or {}
    if ctx.get("cpu_vendor") or ctx.get("gpu_vendor"):
        return True
    return bool(_hardware_vendors_map(ctx))


def intel_driver_lookup_applicable(system_ctx: dict | None) -> bool:
    """Intel lookups apply when this PC has Intel chipset, GPU, network, or other Intel hardware."""
    ctx = system_ctx or {}
    if intel_chipset_applicable(ctx):
        return True
    if (ctx.get("gpu_vendor") or "").lower() == "intel":
        return True
    gpus = ctx.get("gpu_vendors_present") or set()
    if isinstance(gpus, (list, tuple)):
        gpus = set(gpus)
    if "intel" in gpus:
        return True
    hv = ctx.get("hardware_vendors") or {}
    net = hv.get("network") or set()
    if isinstance(net, (list, tuple)):
        net = set(net)
    if "intel" in net:
        return True
    return vendor_present_in_hardware(ctx, "intel")


def realtek_driver_lookup_applicable(system_ctx: dict | None) -> bool:
    ctx = system_ctx or {}
    if vendor_present_in_hardware(ctx, "realtek"):
        return True
    hv = _hardware_vendors_map(ctx)
    return "realtek" in hv.get("audio", set()) or "realtek" in hv.get("network", set())


def network_vendor_driver_lookup_applicable(
    vendor_key: str,
    system_ctx: dict | None,
) -> bool:
    vk = (vendor_key or "").lower().strip()
    if not vk:
        return False
    return vendor_present_in_hardware(system_ctx, vk)


def quick_chipset_system_ctx() -> dict:
    """One lightweight WMI pass — enough to gate chipset/vendor probes."""
    try:
        bundle = get_report_storage_wmi_bundle()
        if bundle:
            return get_storage_and_system_context(wmi_bundle=bundle)
    except Exception:  # noqa: BLE001
        pass
    return {}


def _parse_json_date(s: str) -> str:
    """Convert /Date(ms)/ or Unix ms to readable date; return original if not parseable."""
    if not s or not isinstance(s, str):
        return s or ""
    m = re.search(r"/Date\((\d+)\)/", s)
    if m:
        try:
            ms = int(m.group(1))
            if ms < 1e12:
                ms *= 1000
            dt = datetime.fromtimestamp(ms / 1000.0)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    return s

_EDID_MONITOR_MANUFACTURER = {
    "GSM": "LG",
    "LGD": "LG",
    "GGL": "LG",
    "SAM": "Samsung",
    "SEC": "Samsung",
    "DEL": "Dell",
    "HWP": "HP",
    "HPQ": "HP",
    "LEN": "Lenovo",
    "ACR": "Acer",
    "ACI": "ASUS",
    "AUS": "ASUS",
    "BNQ": "BenQ",
    "VSC": "ViewSonic",
    "PHL": "Philips",
    "NEC": "NEC",
    "IVM": "Iiyama",
    "MSI": "MSI",
    "GIG": "Gigabyte",
}


def _chipset_installed_version(
    vendor_key: str,
    ctx: dict,
    inventory: list | None = None,
) -> str:
    try:
        import driver_catalog as dc
        return dc._resolve_chipset_installed_version(vendor_key, inventory, ctx)
    except ImportError:
        return "?"


def chipset_driver_catalog_entries(
    system_ctx: dict | None,
    *,
    inventory: list | None = None,
) -> list[dict]:
    """Synthetic rows for AMD/Intel chipset platform driver checks on the Drivers tab."""
    ctx = system_ctx or {}
    entries: list[dict] = []
    if amd_chipset_applicable(ctx):
        entries.append({
            "name": CHIPSET_DEVICE_AMD,
            "display_name": "AMD Chipset / Platform drivers",
            "driver": "AMD Chipset",
            "version": _chipset_installed_version("amd", ctx, inventory),
            "date": "",
            "_reasons": ["Platform (chipset)"],
        })
    if intel_chipset_applicable(ctx):
        entries.append({
            "name": CHIPSET_DEVICE_INTEL,
            "display_name": "Intel Chipset / Platform drivers",
            "driver": "Intel Chipset",
            "version": _chipset_installed_version("intel", ctx, inventory),
            "date": "",
            "_reasons": ["Platform (chipset)"],
        })
    return entries


def get_present_system_drivers() -> set[str]:
    """Return set of driver base names (lowercase, no .sys) actually present on this system (from PnP)."""
    seen = set()
    ps = r"""
    Get-CimInstance -ClassName Win32_PnPSignedDriver -ErrorAction SilentlyContinue | ForEach-Object { $_.DriverName } | Where-Object { $_ -match '\.sys$' }
    """
    ok, out = run_powershell(ps)
    if not ok or not out:
        return seen
    for line in (out or "").strip().splitlines():
        line = line.strip().strip('"')
        if not line.lower().endswith(".sys"):
            continue
        base = os.path.basename(line).replace(".sys", "").lower()
        if base:
            seen.add(base)
    return seen


# Known vendor names for normalization (maps variations to canonical name)
KNOWN_VENDORS = {
    # CPU/Chipset
    "amd": "amd", "authenticamd": "amd", "advanced micro devices": "amd", "ryzen": "amd", "epyc": "amd", "threadripper": "amd", "radeon": "amd",
    "intel": "intel", "genuineintel": "intel", "core": "intel", "xeon": "intel", "pentium": "intel", "celeron": "intel", "iris": "intel", "arc": "intel",
    # GPU
    "nvidia": "nvidia", "geforce": "nvidia", "quadro": "nvidia", "rtx": "nvidia", "gtx": "nvidia", "tesla": "nvidia",
    # Network/Wireless
    "realtek": "realtek", "rtl": "realtek",
    "broadcom": "broadcom", "bcm": "broadcom",
    "qualcomm": "qualcomm", "atheros": "qualcomm", "qca": "qualcomm",
    "marvell": "marvell", "yukon": "marvell",
    "mediatek": "mediatek", "mtk": "mediatek", "ralink": "mediatek",
    "killer": "killer",
    "tp-link": "tplink", "tplink": "tplink",
    "asus": "asus",
    "d-link": "dlink", "dlink": "dlink",
    "netgear": "netgear",
    "linksys": "linksys",
    "cisco": "cisco",
    # Audio
    "creative": "creative", "sound blaster": "creative", "soundblaster": "creative",
    "conexant": "conexant",
    "synaptics": "synaptics",
    "cirrus": "cirrus", "cirrus logic": "cirrus",
    "c-media": "cmedia", "cmedia": "cmedia",
    "via": "via",
    "focusrite": "focusrite",
    "steinberg": "steinberg",
    "yamaha": "yamaha",
    "behringer": "behringer",
    # USB/Controllers
    "asmedia": "asmedia", "asmt": "asmedia",
    "renesas": "renesas",
    "fresco": "fresco", "fresco logic": "fresco",
    "texas instruments": "ti", "ti ": "ti",
    "nec": "nec",
    "etron": "etron",
    "genesys": "genesys",
    # Storage
    "samsung": "samsung",
    "western digital": "wd", "wd ": "wd", "sandisk": "wd",
    "seagate": "seagate",
    "toshiba": "toshiba", "kioxia": "toshiba",
    "crucial": "crucial", "micron": "crucial",
    "kingston": "kingston",
    "sk hynix": "hynix", "hynix": "hynix",
    "phison": "phison",
    "silicon motion": "silicon motion", "smi ": "silicon motion",
    "jmicron": "jmicron",
    # Webcams/Imaging
    "logitech": "logitech", "logi": "logitech",
    "microsoft": "microsoft",
    "chicony": "chicony",
    "sunplus": "sunplus",
    "sonix": "sonix",
    "omnivision": "omnivision",
    "bison": "bison",
    "quanta": "quanta",
    "lite-on": "lite-on", "liteon": "lite-on",
    # Fingerprint/Biometric
    "goodix": "goodix",
    "elan": "elan",
    "validity": "validity",
    "authentec": "authentec",
    "upek": "upek",
    "fingerprint cards": "fpc", "fpc": "fpc",
    # Card readers
    "alcor": "alcor",
    "o2micro": "o2micro", "o2 micro": "o2micro",
    "bayhub": "bayhub",
    # Thunderbolt
    "thunderbolt": "thunderbolt",
    # Sensors
    "bosch": "bosch",
    "stmicroelectronics": "st", "stm": "st",
    "kionix": "kionix",
    "invensense": "invensense",
    # Other
    "dell": "dell", "alienware": "dell",
    "hp": "hp", "hewlett": "hp",
    "lenovo": "lenovo",
    "acer": "acer",
    "msi": "msi",
    "gigabyte": "gigabyte",
    "asrock": "asrock",
    "lg": "lg",
    "lg electronics": "lg",
    "goldstar": "lg",
    "lucky goldstar": "lg",
    "lg display": "lg",
    "benq": "benq",
    "viewsonic": "viewsonic",
    "philips": "philips",
    "aoc": "aoc",
    "iiyama": "iiyama",
    "sharp": "sharp",
    "hisense": "hisense",
    "tcl": "tcl",
    "huawei": "huawei",
    "xiaomi": "xiaomi",
    "oppo": "oppo",
    "oneplus": "oneplus",
    "motorola": "motorola",
    "google": "google",
    "apple": "apple",
    "sony": "sony",
    "panasonic": "panasonic",
    "jbl": "jbl",
    "harman": "harman",
    "wacom": "wacom",
    "zyxel": "zyxel",
    "ubiquiti": "ubiquiti",
    "elgato": "elgato",
    "corsair": "corsair",
    "razer": "razer",
    "steelseries": "steelseries",
}


def _vendor_pattern_matches(text_lower: str, pattern: str) -> bool:
    """Avoid short keys like 'logi' matching inside 'Techno**logi**es'."""
    if not pattern:
        return False
    if len(pattern) <= 4:
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])",
                text_lower,
            )
        )
    return pattern in text_lower


def _extract_vendor_from_string(text: str) -> str | None:
    """
    Smart vendor extraction: tries known vendors first, then extracts first meaningful word.
    Returns normalized vendor name or None if no vendor found.
    """
    if not text:
        return None
    text_lower = text.lower()
    
    # First try known vendors (longer patterns first to prefer "logitech" over "logi").
    for vendor_pattern, canonical in sorted(
        KNOWN_VENDORS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if _vendor_pattern_matches(text_lower, vendor_pattern):
            return canonical
    
    # If no known vendor found, try to extract the first meaningful word as vendor
    # Skip common generic words and device type words that are NOT vendor names
    skip_words = {
        # Generic/Windows terms
        "standard", "generic", "microsoft", "windows", "usb", "pci", "pcie", "hd", "high",
        "definition", "audio", "video", "controller", "device", "devices", "adapter", "interface",
        "host", "hub", "root", "composite", "virtual", "remote", "basic", "compatible",
        "serial", "bus", "port", "bridge", "system", "acpi", "compliant", "express",
        "integrated", "embedded", "onboard", "built-in", "internal", "external",
        # Device type words (not vendors)
        "bluetooth", "wifi", "wireless", "ethernet", "network", "lan", "wlan", "camera",
        "webcam", "microphone", "speaker", "headphone", "headset", "monitor", "display",
        "keyboard", "mouse", "touchpad", "trackpad", "fingerprint", "biometric", "sensor",
        "accelerometer", "gyroscope", "card", "reader", "storage", "disk", "drive", "ssd",
        "nvme", "sata", "ahci", "raid", "printer", "scanner", "game", "gaming", "input",
        "output", "multimedia", "media", "sound", "hdmi", "displayport", "thunderbolt",
        "type", "version", "gen", "mini", "micro", "nano", "pro", "plus", "max", "ultra",
        # Common words that slip through
        "extension", "enumerator", "miniport", "filter", "service", "driver", "function",
        "endpoint", "redirect", "virtual", "software", "hardware", "physical", "logical",
        # Additional non-vendor words seen in testing
        "dfu", "peripheral", "gsound", "ven", "dev", "subsys", "rev", "class", "subclass",
        "protocol", "iproduct", "imanufacturer", "iserial", "configuration", "descriptors",
        "image", "capture", "streaming", "processing", "rendering", "playback", "recording",
        "composite", "aggregate", "collection", "multi", "dual", "single", "primary", "secondary",
        "upstream", "downstream", "inbound", "outbound", "incoming", "outgoing", "local", "remote",
        # Windows internal device names/prefixes
        "bthenum", "bthhfenum", "swdenum", "wudfwpdmtp", "wpdbusenum", "usbprint", "usbscan",
        "winusb", "usbccgp", "usbhub", "usbstor", "usbvideo", "hidusb", "hidbatt", "hidclass",
        "control", "panel", "wdf", "umdf", "kmdf", "wdm", "acpidev", "pnpmanager",
        "ndis", "tcpip", "netbt", "afd", "volsnap", "fltmgr", "volmgr", "partmgr",
        "classpnp", "storport", "scsiport", "atapi", "ataport", "msahci", "storahci",
        "i8042prt", "kbdhid", "mouhid", "mouclass", "kbdclass", "termdd", "rdpdr",
    }
    
    # Split by common delimiters and find first non-generic word
    words = re.split(r'[\s\-_®™\(\)\[\]/\\,\.&]+', text_lower)
    for word in words:
        word = word.strip().rstrip('}').lstrip('{')
        if len(word) < 3 or word in skip_words or word.isdigit():
            continue
        # Skip hex-looking strings (device IDs like a1ff, ff96c9330e15, vid_046d, etc.)
        if re.match(r'^[0-9a-f]+$', word) and len(word) >= 4:
            continue  # Looks like hex
        if re.match(r'^(vid|pid|ven|dev|subsys|rev|pnp|acpi|hid|usb)_?[0-9a-f]*$', word, re.IGNORECASE):
            continue  # Device ID pattern
        if re.match(r'^(pnp|acpi|hid)[0-9a-f]{3,}$', word, re.IGNORECASE):
            continue  # ACPI/PnP device ID like pnp0800, acpi0001
        if len(word) <= 4 and any(c.isdigit() for c in word):
            continue  # Short string with numbers - likely ID fragment
        # Check if it looks like a vendor name (starts with letter, reasonably short)
        if word[0].isalpha() and len(word) <= 20:
            return word
    
    return None


def attach_pnp_device_parents(pnp_list: list[dict]) -> None:
    """
    Fill Parent on PnP rows using Windows DEVPKEY_Device_Parent (in-place).

    With PowerShell 7+, queries all PnP rows in parallel. On Windows PowerShell 5.1,
    only SoftwareComponent / AudioProcessingObject / SoftwareDevice (scan time).
    Enrichment shows a parent note only when Parent resolves within the same pnp_list.
    """
    if not pnp_list:
        return
    use_pwsh = rt.powershell7_available()
    targets: list[tuple[int, str]] = []
    for idx, row in enumerate(pnp_list):
        if not isinstance(row, dict):
            continue
        if row.get("Parent") or row.get("parent"):
            continue
        pnp_class = (row.get("PNPClass") or row.get("pnp_class") or "").strip().lower()
        if not use_pwsh and pnp_class not in _PNP_PARENT_LOOKUP_CLASSES:
            continue
        device_id = (row.get("DeviceID") or row.get("device_id") or "").strip()
        if device_id:
            targets.append((idx, device_id))
    if not targets:
        return
    payload = base64.b64encode(
        json.dumps([device_id for _, device_id in targets]).encode("utf-8")
    ).decode("ascii")
    ps = rt.build_pnp_parent_lookup_script(payload, parallel=use_pwsh)
    timeout = max(30, 8 + len(targets) // (4 if use_pwsh else 2))
    ok, out = run_powershell(ps, timeout=timeout, prefer_pwsh=use_pwsh)
    if not ok or not out:
        return
    try:
        mapping = json.loads(out)
    except json.JSONDecodeError:
        return
    if isinstance(mapping, str):
        return
    if not isinstance(mapping, dict):
        return
    for idx, device_id in targets:
        parent = mapping.get(device_id)
        if parent:
            pnp_list[idx]["Parent"] = str(parent).strip()


def get_pnp_entities_for_analysis() -> list[dict]:
    """
    Single PnP query used for hardware context, driver problems, and generic drivers.
    Returns list of dicts: Name, PNPClass, Manufacturer, DeviceID, ConfigManagerErrorCode.
    Reusing this list avoids 2 extra PowerShell rounds in run_analysis.
    """
    result = []
    ps = r"""
    Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $null } |
    Select-Object -First 350 Name, PNPClass, Manufacturer, DeviceID, ConfigManagerErrorCode |
    ForEach-Object { [PSCustomObject]@{ Name=($_.Name -replace '\s+',' ').Trim(); PNPClass=($_.PNPClass -replace '\s+',' ').Trim(); Manufacturer=($_.Manufacturer -replace '\s+',' ').Trim(); DeviceID=($_.DeviceID -replace '\s+',' ').Trim(); ConfigManagerErrorCode=[int]$_.ConfigManagerErrorCode } } |
    ConvertTo-Json -Depth 1
    """
    ok, out = run_powershell(ps)
    if not ok or not out:
        return result
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for d in data:
            result.append({
                "Name": (d.get("Name") or "").strip(),
                "PNPClass": (d.get("PNPClass") or "").strip(),
                "Manufacturer": (d.get("Manufacturer") or "").strip(),
                "DeviceID": (d.get("DeviceID") or "").strip(),
                "ConfigManagerErrorCode": int(d.get("ConfigManagerErrorCode", 0)),
            })
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    attach_pnp_device_parents(result)
    return result


def _signed_driver_filter_ps_where() -> str:
    return (
        "$_.DeviceName -and ("
        "$_.DeviceClass -in @('Display','Net','Bluetooth','Media','SCSIAdapter',"
        "'DiskDrive','Volume','Processor','Monitor','Keyboard','Mouse','Camera',"
        "'Battery','Firmware','PrintQueue','USB','System','Computer') -or "
        "$_.DeviceName -match "
        "'NVIDIA|AMD|Intel|GeForce|Radeon|Realtek|MediaTek|Qualcomm|Broadcom|Marvell|"
        "Killer|GPIO|SMBus|Chipset|PCI Express|Crash Defender|Storage Controller|"
        "NVMe|Ethernet|Wi-?Fi|Wireless|Graphics|Audio|Processor'"
        ")"
    )


def _storage_flags_from_disk_rows(disk_rows: list[dict]) -> tuple[bool, bool]:
    has_sata, has_nvme = False, False
    for d in disk_rows:
        if not isinstance(d, dict):
            continue
        it = (d.get("InterfaceType") or "").upper()
        model = (d.get("Model") or "").lower()
        if it == "IDE" or "sata" in model:
            has_sata = True
        if "nvme" in model or it == "SCSI":
            has_nvme = True
    return has_sata, has_nvme


def _ssd_firmware_from_disk_wmi(
    disks: list[dict],
    physical_disks: list[dict],
) -> list[dict]:
    """Build SSD firmware inventory from WMI rows (same shape as get_ssd_firmware_inventory)."""
    drives: list[dict] = []
    seen: set[str] = set()
    for d in disks:
        if not isinstance(d, dict):
            continue
        model = (d.get("Model") or "").strip()
        if not model:
            continue
        key = model + "|" + (d.get("SerialNumber") or "").strip()
        if key in seen:
            continue
        seen.add(key)
        drives.append({
            "model": model,
            "firmware_revision": (d.get("FirmwareRevision") or "").strip(),
            "serial_number": (d.get("SerialNumber") or "").strip(),
            "interface_type": (d.get("InterfaceType") or "").strip(),
            "size_gb": d.get("SizeGB") or 0,
            "vendor_key": _extract_vendor_from_string(model) or "",
        })
    for pd in physical_disks:
        if not isinstance(pd, dict):
            continue
        model = (pd.get("Model") or pd.get("FriendlyName") or "").strip()
        if not model:
            continue
        key = model + "|" + (pd.get("SerialNumber") or "").strip()
        if key in seen:
            continue
        seen.add(key)
        drives.append({
            "model": model,
            "firmware_revision": (pd.get("FirmwareRevision") or pd.get("FirmwareVersion") or "").strip(),
            "serial_number": (pd.get("SerialNumber") or "").strip(),
            "interface_type": (pd.get("InterfaceType") or "SSD").strip(),
            "size_gb": pd.get("SizeGB") or 0,
            "vendor_key": _extract_vendor_from_string(model) or "",
        })
    return drives


def get_hardware_profile_wmi_bundle() -> dict | None:
    """
    One PowerShell round-trip for Drivers-tab hardware scan (PnP, BIOS, drivers, disks, GPU, etc.).
    Returns parsed snapshot dict, or None on failure (caller may fall back to separate queries).
    """
    driver_where = _signed_driver_filter_ps_where()
    ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
$pnp = @(Get-CimInstance Win32_PnPEntity -EA 0 | Where-Object {{ $_.Name }} |
  Select-Object -First 350 Name, PNPClass, Manufacturer, DeviceID, ConfigManagerErrorCode |
  ForEach-Object {{ [PSCustomObject]@{{
    Name=($_.Name -replace '\\s+',' ').Trim()
    PNPClass=($_.PNPClass -replace '\\s+',' ').Trim()
    Manufacturer=($_.Manufacturer -replace '\\s+',' ').Trim()
    DeviceID=($_.DeviceID -replace '\\s+',' ').Trim()
    ConfigManagerErrorCode=[int]$_.ConfigManagerErrorCode
  }} }})
$bios = Get-CimInstance Win32_BIOS -EA 0 | Select-Object -First 1 Manufacturer, SMBIOSBIOSVersion, ReleaseDate, SerialNumber
$signed = @(Get-CimInstance Win32_PnPSignedDriver -EA 0)
$present = @($signed | Where-Object {{ $_.DriverName -match '\\.sys$' }} |
  ForEach-Object {{ ($_.DriverName -replace '\\.sys$','').ToLower() }} | Select-Object -Unique)
$drivers = @($signed | Where-Object {{ {driver_where} }} |
  Select-Object DeviceName, DriverVersion, DriverDate, DeviceClass)
$disks = @(Get-CimInstance Win32_DiskDrive -EA 0 | Select-Object -First 12 Model, InterfaceType, PNPDeviceID)
$gpu = @(Get-CimInstance Win32_VideoController -EA 0 |
  Where-Object {{ $_.Name -notlike '*Microsoft*' -and $_.Name -notlike '*Remote*' }} |
  Select-Object -First 4 Name, VideoProcessor, AdapterCompatibility)
$cpu = Get-CimInstance Win32_Processor -EA 0 | Select-Object -First 1 Manufacturer, Name
$sys = Get-CimInstance Win32_ComputerSystem -EA 0 | Select-Object -First 1 Manufacturer, Model
$product = Get-CimInstance Win32_ComputerSystemProduct -EA 0 | Select-Object -First 1 UUID
$monitors = @(Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorID -EA 0 | ForEach-Object {{
  $mfr = -join ($_.ManufacturerName | ForEach-Object {{ [char]$_ }})
  $prod = -join ($_.ProductCodeID | ForEach-Object {{ [char]$_ }})
  [PSCustomObject]@{{
    InstanceName=[string]$_.InstanceName
    ManufacturerCode=($mfr -replace '\\s+$','').Trim()
    ProductCode=($prod -replace '\\s+$','').Trim()
  }}
}})
[PSCustomObject]@{{
  Pnp=$pnp
  Bios=$bios
  Drivers=$drivers
  PresentDrivers=$present
  Disks=$disks
  Gpu=$gpu
  Processor=$cpu
  ComputerSystem=$sys
  Product=$product
  Monitors=$monitors
}} | ConvertTo-Json -Depth 5 -Compress
"""
    ok, out = run_powershell(ps, timeout=75)
    if not ok or not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    return _parse_hardware_profile_wmi_bundle(data)


def _parse_hardware_profile_wmi_bundle(data: dict) -> dict:
    """Normalize combined WMI JSON into gather_hardware_profile building blocks."""
    pnp_list: list[dict] = []
    for d in data.get("Pnp") or []:
        if not isinstance(d, dict):
            continue
        pnp_list.append({
            "Name": (d.get("Name") or "").strip(),
            "PNPClass": (d.get("PNPClass") or "").strip(),
            "Manufacturer": (d.get("Manufacturer") or "").strip(),
            "DeviceID": (d.get("DeviceID") or "").strip(),
            "ConfigManagerErrorCode": int(d.get("ConfigManagerErrorCode", 0)),
        })

    attach_pnp_device_parents(pnp_list)

    bios, rows = _parse_signed_driver_cim({
        "Bios": data.get("Bios"),
        "Drivers": data.get("Drivers"),
    })
    bios_driver_info = {
        "bios": bios,
        "drivers": _common_devices_from_rows(rows),
        "all_drivers": [],
        "device_inventory": rows,
    }

    present = {
        str(x).strip().lower()
        for x in (data.get("PresentDrivers") or [])
        if str(x).strip()
    }

    disk_rows = []
    for d in data.get("Disks") or []:
        if isinstance(d, dict):
            disk_rows.append({
                "Model": d.get("Model"),
                "InterfaceType": d.get("InterfaceType"),
                "PNPDeviceID": d.get("PNPDeviceID"),
            })

    monitor_edid: dict[str, dict] = {}
    for row in data.get("Monitors") or []:
        if not isinstance(row, dict):
            continue
        inst = (row.get("InstanceName") or "").upper()
        code = (row.get("ManufacturerCode") or "").strip().upper()
        prod = (row.get("ProductCode") or "").strip()
        brand = _EDID_MONITOR_MANUFACTURER.get(code, code)
        if not inst:
            continue
        parts = inst.split("\\")
        key = f"MONITOR\\{parts[1]}".upper() if len(parts) >= 2 else inst
        monitor_edid[key] = {
            "edid_manufacturer_code": code,
            "brand": brand,
            "product_code": prod,
        }

    has_sata, has_nvme = _storage_flags_from_disk_rows(data.get("Disks") or [])

    gpu_vendor = None
    gpu_vendors_present: set[str] = set()
    gpu_data = data.get("Gpu")
    if isinstance(gpu_data, dict):
        gpu_data = [gpu_data]
    for d in gpu_data or []:
        if not isinstance(d, dict):
            continue
        combined = (
            f"{d.get('Name', '')} {d.get('VideoProcessor', '')} "
            f"{d.get('AdapterCompatibility', '')}"
        ).lower()
        vendor = _extract_vendor_from_string(combined)
        if vendor in ("nvidia", "geforce", "quadro", "rtx", "gtx"):
            vendor = "nvidia"
        elif vendor in ("amd", "radeon", "ati"):
            vendor = "amd"
        elif vendor in ("intel", "iris", "arc", "uhd"):
            vendor = "intel"
        if vendor:
            gpu_vendors_present.add(vendor)
            if not gpu_vendor and vendor in ("nvidia", "amd", "intel"):
                gpu_vendor = vendor

    has_amd_chipset = False
    has_intel_chipset = False
    cpu_vendor = None
    cpu_data = data.get("Processor")
    if isinstance(cpu_data, list) and cpu_data:
        cpu_data = cpu_data[0]
    if isinstance(cpu_data, dict):
        combined = f"{cpu_data.get('Manufacturer', '')} {cpu_data.get('Name', '')}".lower()
        vendor = _extract_vendor_from_string(combined)
        if vendor in ("amd", "ryzen", "epyc", "threadripper"):
            has_amd_chipset = True
            cpu_vendor = "amd"
        elif vendor in ("intel", "core", "xeon", "pentium", "celeron"):
            has_intel_chipset = True
            cpu_vendor = "intel"

    system_manufacturer = ""
    system_model = ""
    sys_data = data.get("ComputerSystem")
    if isinstance(sys_data, list) and sys_data:
        sys_data = sys_data[0]
    if isinstance(sys_data, dict):
        system_manufacturer = (sys_data.get("Manufacturer") or "").strip()
        system_model = (sys_data.get("Model") or "").strip()

    system_product_uuid = ""
    prod_data = data.get("Product")
    if isinstance(prod_data, list) and prod_data:
        prod_data = prod_data[0]
    if isinstance(prod_data, dict):
        system_product_uuid = (prod_data.get("UUID") or "").strip()

    return {
        "pnp_list": pnp_list,
        "bios_driver_info": bios_driver_info,
        "monitor_edid": monitor_edid,
        "disk_rows": disk_rows,
        "ssd_firmware": [],
        "present_drivers": present,
        "has_sata": has_sata,
        "has_nvme": has_nvme,
        "gpu_vendor": gpu_vendor,
        "gpu_vendors_present": gpu_vendors_present,
        "has_amd_chipset": has_amd_chipset,
        "has_intel_chipset": has_intel_chipset,
        "cpu_vendor": cpu_vendor,
        "system_manufacturer": system_manufacturer,
        "system_model": system_model,
        "system_product_uuid": system_product_uuid,
    }


def get_report_storage_wmi_bundle() -> dict | None:
    """
    One WMI pass for Run Analysis storage/system context (no PnP/BIOS — those come from group 1/2).
    Returns a wmi_bundle-shaped dict for get_storage_and_system_context(), or None on failure.
    """
    ps = """
$ErrorActionPreference = 'SilentlyContinue'
$signed = @(Get-CimInstance Win32_PnPSignedDriver -EA 0)
$present = @($signed | Where-Object { $_.DriverName -match '\\.sys$' } |
  ForEach-Object { ($_.DriverName -replace '\\.sys$','').ToLower() } | Select-Object -Unique)
$disks = @(Get-CimInstance Win32_DiskDrive -EA 0 | Select-Object -First 12 Model, InterfaceType, PNPDeviceID)
$gpu = @(Get-CimInstance Win32_VideoController -EA 0 |
  Where-Object { $_.Name -notlike '*Microsoft*' -and $_.Name -notlike '*Remote*' } |
  Select-Object -First 4 Name, VideoProcessor, AdapterCompatibility)
$cpu = Get-CimInstance Win32_Processor -EA 0 | Select-Object -First 1 Manufacturer, Name
$sys = Get-CimInstance Win32_ComputerSystem -EA 0 | Select-Object -First 1 Manufacturer, Model
$product = Get-CimInstance Win32_ComputerSystemProduct -EA 0 | Select-Object -First 1 UUID
$monitors = @(Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorID -EA 0 | ForEach-Object {{
  $mfr = -join ($_.ManufacturerName | ForEach-Object {{ [char]$_ }})
  $prod = -join ($_.ProductCodeID | ForEach-Object {{ [char]$_ }})
  [PSCustomObject]@{{
    InstanceName=[string]$_.InstanceName
    ManufacturerCode=($mfr -replace '\\s+$','').Trim()
    ProductCode=($prod -replace '\\s+$','').Trim()
  }}
}})
[PSCustomObject]@{{
  Pnp=@()
  PresentDrivers=$present
  Disks=$disks
  Gpu=$gpu
  Processor=$cpu
  ComputerSystem=$sys
  Product=$product
  Monitors=$monitors
}} | ConvertTo-Json -Depth 5 -Compress
"""
    ok, out = run_powershell(ps, timeout=45)
    if not ok or not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    parsed = _parse_hardware_profile_wmi_bundle({
        "Pnp": [],
        "Drivers": [],
        "PresentDrivers": data.get("PresentDrivers"),
        "Disks": data.get("Disks"),
        "Gpu": data.get("Gpu"),
        "Processor": data.get("Processor"),
        "ComputerSystem": data.get("ComputerSystem"),
        "Product": data.get("Product"),
        "Monitors": data.get("Monitors"),
    })
    return {
        "present_drivers": parsed.get("present_drivers") or set(),
        "has_sata": parsed.get("has_sata"),
        "has_nvme": parsed.get("has_nvme"),
        "gpu_vendor": parsed.get("gpu_vendor"),
        "gpu_vendors_present": parsed.get("gpu_vendors_present") or set(),
        "has_amd_chipset": parsed.get("has_amd_chipset"),
        "has_intel_chipset": parsed.get("has_intel_chipset"),
        "cpu_vendor": parsed.get("cpu_vendor"),
        "system_manufacturer": parsed.get("system_manufacturer"),
        "system_model": parsed.get("system_model"),
        "system_product_uuid": parsed.get("system_product_uuid"),
        "monitor_edid": parsed.get("monitor_edid") or {},
        "disk_rows": parsed.get("disk_rows") or [],
    }


def get_storage_and_system_context(
    pnp_list: list[dict] | None = None,
    *,
    wmi_bundle: dict | None = None,
) -> dict:
    """
    Detect ALL hardware types first using smart vendor extraction.
    If pnp_list is provided (from get_pnp_entities_for_analysis), reuse it; else query PnP once.
    When wmi_bundle is from get_hardware_profile_wmi_bundle(), skip extra PowerShell queries.
    Returns comprehensive hardware context for filtering recommendations.
    """
    if wmi_bundle:
        present = set(wmi_bundle.get("present_drivers") or [])
    else:
        present = get_present_system_drivers()
    
    # === ALL HARDWARE CATEGORIES ===
    hardware_vendors = {
        "network": set(),           # Network adapters (Ethernet, WiFi)
        "audio": set(),             # Audio devices
        "bluetooth": set(),         # Bluetooth adapters
        "usb_controller": set(),    # USB host controllers
        "storage_controller": set(),# SATA, NVMe, RAID controllers
        "webcam": set(),            # Cameras/imaging devices
        "fingerprint": set(),       # Biometric/fingerprint readers
        "card_reader": set(),       # SD/memory card readers
        "thunderbolt": set(),       # Thunderbolt controllers
        "sensor": set(),            # Accelerometers, gyros, etc.
        "input": set(),             # Keyboards, mice, touchpads, game controllers
        "printer": set(),           # Printers
        "display": set(),           # Monitors (for detection, not GPU)
        "other": set(),             # Catch-all for other devices
    }
    
    # Map PNPClass to our categories
    CLASS_TO_CATEGORY = {
        "net": "network", "netclient": "network", "nettrans": "network", "netservice": "network",
        "media": "audio", "audioaccel": "audio", "audioendpoint": "audio", "sound": "audio",
        "bluetooth": "bluetooth",
        "usb": "usb_controller",
        "scsiadapter": "storage_controller", "hdc": "storage_controller", "diskdrive": "storage_controller",
        "image": "webcam", "camera": "webcam",
        "biometric": "fingerprint",
        "smartcardreader": "card_reader", "mtd": "card_reader",
        "sensor": "sensor",
        "keyboard": "input", "mouse": "input", "hidclass": "input",
        "printer": "printer", "printqueue": "printer",
        "monitor": "display",
    }
    
    # Use provided PnP list or run one query (avoids duplicate PnP calls when caller passes pnp_list)
    if pnp_list:
        data = pnp_list
    else:
        data = []
        ps_all_hw = r"""
        Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne $null } |
        Select-Object -First 350 Name, PNPClass, Manufacturer, DeviceID | ConvertTo-Json -Depth 1
        """
        ok, out = run_powershell(ps_all_hw)
        if ok and out:
            try:
                parsed = json.loads(out)
                data = [parsed] if isinstance(parsed, dict) else parsed
            except json.JSONDecodeError:
                pass
    
    for d in data:
        name = (d.get("Name") or "").strip() if isinstance(d.get("Name"), str) else ""
        pnp_class = (d.get("PNPClass") or "").lower()
        manufacturer = d.get("Manufacturer") or ""
        device_id = d.get("DeviceID") or ""

        # Determine category from PNPClass
        category = CLASS_TO_CATEGORY.get(pnp_class)

        # Additional category detection from device name/ID
        name_lower = name.lower()
        device_id_lower = device_id.lower()
        if not category:
            if "bluetooth" in name_lower:
                category = "bluetooth"
            elif "wifi" in name_lower or "wireless" in name_lower or "wlan" in name_lower or "wi-fi" in name_lower:
                category = "network"
            elif "ethernet" in name_lower or "lan " in name_lower or " nic" in name_lower:
                category = "network"
            elif "audio" in name_lower or "sound" in name_lower or "speaker" in name_lower or "microphone" in name_lower:
                category = "audio"
            elif "webcam" in name_lower or "camera" in name_lower or "imaging" in name_lower:
                category = "webcam"
            elif "fingerprint" in name_lower or "biometric" in name_lower:
                category = "fingerprint"
            elif "card reader" in name_lower or "cardreader" in name_lower or "sd host" in name_lower or "mmc" in name_lower:
                category = "card_reader"
            elif "thunderbolt" in name_lower:
                category = "thunderbolt"
            elif "sensor" in name_lower or "accelerometer" in name_lower or "gyro" in name_lower:
                category = "sensor"
            elif "nvme" in name_lower or "sata" in name_lower or "ahci" in name_lower or "raid" in name_lower:
                category = "storage_controller"
            elif "usb" in name_lower and ("controller" in name_lower or "host" in name_lower or "xhci" in name_lower or "ehci" in name_lower):
                category = "usb_controller"
            elif "keyboard" in name_lower or "mouse" in name_lower or "touchpad" in name_lower or "trackpad" in name_lower:
                category = "input"
            elif "printer" in name_lower:
                category = "printer"
            elif pnp_class == "monitor" or "monitor" in name_lower:
                category = "display"

        if not category:
            continue  # Skip devices we can't categorize

        # Extract vendor from name, manufacturer, or device ID
        combined_text = f"{name} {manufacturer} {device_id}"
        vendor = _extract_vendor_from_string(combined_text)

        if vendor and category in hardware_vendors:
            hardware_vendors[category].add(vendor)
    
    # === STORAGE TYPE: Check ACTUAL drives (not just driver presence) ===
    if wmi_bundle:
        has_sata = bool(wmi_bundle.get("has_sata"))
        has_nvme = bool(wmi_bundle.get("has_nvme"))
    else:
        has_sata = False
        has_nvme = False
        ps_disk = r"""
    Get-CimInstance -ClassName Win32_DiskDrive -ErrorAction SilentlyContinue | Select-Object -First 10 InterfaceType, Model | ConvertTo-Json
    """
        ok, out = run_powershell(ps_disk)
        if ok and out:
            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    data = [data]
                has_sata, has_nvme = _storage_flags_from_disk_rows(data)
            except json.JSONDecodeError:
                pass
    # Fallback: If Win32_DiskDrive query failed, check for storage drivers
    if not has_sata and not has_nvme:
        sata_drivers = {"amd_sata", "storahci", "iastor", "iastoravc", "msahci"}
        nvme_drivers = {"stornvme", "nvme", "iaStorAVC"}
        has_sata = bool(present & sata_drivers)
        has_nvme = bool(present & nvme_drivers) or "stornvme" in present
    
    # === GPU: Check ACTUAL hardware first ===
    if wmi_bundle:
        gpu_vendor = wmi_bundle.get("gpu_vendor")
        gpu_vendors_present = set(wmi_bundle.get("gpu_vendors_present") or [])
    else:
        gpu_vendor = None
        gpu_vendors_present = set()
        ps_gpu = r"""
    Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue | 
    Where-Object { $_.Name -notlike '*Microsoft*' -and $_.Name -notlike '*Remote*' } | 
    Select-Object -First 4 Name, VideoProcessor, AdapterCompatibility | ConvertTo-Json
    """
        ok, out = run_powershell(ps_gpu)
        if ok and out:
            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    data = [data]
                for d in data:
                    combined = f"{d.get('Name', '')} {d.get('VideoProcessor', '')} {d.get('AdapterCompatibility', '')}".lower()
                    vendor = _extract_vendor_from_string(combined)
                    if vendor in ("nvidia", "geforce", "quadro", "rtx", "gtx"):
                        vendor = "nvidia"
                    elif vendor in ("amd", "radeon", "ati"):
                        vendor = "amd"
                    elif vendor in ("intel", "iris", "arc", "uhd"):
                        vendor = "intel"
                    if vendor:
                        gpu_vendors_present.add(vendor)
                        if not gpu_vendor and vendor in ("nvidia", "amd", "intel"):
                            gpu_vendor = vendor
            except json.JSONDecodeError:
                pass
    # Fallback: If Win32_VideoController query failed, check GPU drivers
    if not gpu_vendor:
        if "nvlddmkm" in present:
            gpu_vendor = "nvidia"
            gpu_vendors_present.add("nvidia")
        elif "amdkmdag" in present or "amdkmdap" in present or "atikmdag" in present:
            gpu_vendor = "amd"
            gpu_vendors_present.add("amd")
        elif "igdkmd64" in present or "igdkmdn64" in present:
            gpu_vendor = "intel"
            gpu_vendors_present.add("intel")
    
    # === CHIPSET/CPU: Check ACTUAL hardware first ===
    if wmi_bundle:
        has_amd_chipset = bool(wmi_bundle.get("has_amd_chipset"))
        has_intel_chipset = bool(wmi_bundle.get("has_intel_chipset"))
        cpu_vendor = wmi_bundle.get("cpu_vendor")
    else:
        has_amd_chipset = False
        has_intel_chipset = False
        cpu_vendor = None
        ps_chipset = r"""
    Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1 Manufacturer, Name | ConvertTo-Json
    """
        ok, out = run_powershell(ps_chipset)
        if ok and out:
            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    data = [data]
                for d in data:
                    combined = f"{d.get('Manufacturer', '')} {d.get('Name', '')}".lower()
                    vendor = _extract_vendor_from_string(combined)
                    if vendor in ("amd", "ryzen", "epyc", "threadripper"):
                        has_amd_chipset = True
                        cpu_vendor = "amd"
                    elif vendor in ("intel", "core", "xeon", "pentium", "celeron"):
                        has_intel_chipset = True
                        cpu_vendor = "intel"
                    break
            except json.JSONDecodeError:
                pass
    # Fallback: If Win32_Processor query failed, check chipset drivers
    if not has_amd_chipset and not has_intel_chipset:
        has_amd_chipset = bool(present & {"amd_sata", "amd_xhci", "amdsfd", "amdppm", "amdgpio2", "amd_i2c"})
        has_intel_chipset = bool(present & {"iastor", "iastoravc", "iaioi2c", "iqvw64e"})
        cpu_vendor = "amd" if has_amd_chipset else ("intel" if has_intel_chipset else None)
    
    system_product_uuid = ""
    if wmi_bundle:
        system_manufacturer = (wmi_bundle.get("system_manufacturer") or "").strip()
        system_model = (wmi_bundle.get("system_model") or "").strip()
        system_product_uuid = (wmi_bundle.get("system_product_uuid") or "").strip()
    else:
        system_manufacturer = ""
        system_model = ""
        ps_mfr = r"""
    Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue |
    Select-Object -First 1 Manufacturer, Model | ConvertTo-Json
    """
        ok_mfr, out_mfr = run_powershell(ps_mfr)
        if ok_mfr and out_mfr:
            try:
                mfr_data = json.loads(out_mfr)
                if isinstance(mfr_data, list) and mfr_data:
                    mfr_data = mfr_data[0]
                if isinstance(mfr_data, dict):
                    system_manufacturer = (mfr_data.get("Manufacturer") or "").strip()
                    system_model = (mfr_data.get("Model") or "").strip()
            except json.JSONDecodeError:
                pass

    return {
        "has_sata": has_sata,
        "has_nvme": has_nvme,
        "has_amd_chipset": has_amd_chipset,
        "has_intel_chipset": has_intel_chipset,
        "cpu_vendor": cpu_vendor,
        "gpu_vendor": gpu_vendor,
        "gpu_vendors_present": gpu_vendors_present,
        "hardware_vendors": hardware_vendors,  # All categories with auto-extracted vendors
        "present_drivers": present,
        "system_manufacturer": system_manufacturer,
        "system_model": system_model,
        "system_product_uuid": system_product_uuid,
    }


# ConfigManagerErrorCode: devices with non-zero have a problem (missing driver, failed, etc.)
DEVICE_ERROR_CODES = {
    0: None,
    1: "Device not configured correctly",
    3: "Driver for this device might be corrupted or missing",
    10: "Device cannot start (driver or resource issue)",
    12: "Device cannot find enough free resources",
    14: "Device cannot work properly until restart",
    18: "Reinstall the drivers",
    22: "Device is disabled",
    24: "Device does not exist or not working properly",
    28: "Drivers for this device are not installed",
    29: "Device is disabled (firmware did not allocate resources)",
    31: "Device is not working properly (Windows cannot load driver)",
    32: "Driver (service) for this device has been disabled",
    33: "Driver (service) for this device has been disabled",
    34: "Device cannot start (multiple drivers)",
    38: "Device cannot start (driver may be missing)",
    40: "Windows cannot access hardware (registry problem)",
    43: "Windows stopped this device (reported a problem)",
    44: "Device was stopped",
    47: "Device cannot be used (configuration incomplete)",
    48: "Drivers for this device are blocked",
    49: "Windows cannot start (registry too large or driver problem)",
    52: "Cannot verify driver signature",
}


def get_devices_with_driver_problems(
    pnp_list: list[dict] | None = None,
    pnp_enrichment: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Return list of PnP devices that have a driver problem (missing, failed, disabled).
    If pnp_list from get_pnp_entities_for_analysis() is provided, filter in Python (no extra PowerShell).
    Each item: { "name", "display_name", "error_code", "error_meaning", ... }.
    """
    # Lazy: bsod_crash_report imports this module, so a top-level import would cycle.
    from bsod_crash_report import resolve_device_display_label

    result = []
    if pnp_list:
        for d in pnp_list:
            name = (d.get("Name") or "").strip()
            code = int(d.get("ConfigManagerErrorCode", 0))
            if not name or code == 0:
                continue
            meaning = DEVICE_ERROR_CODES.get(code, f"Device problem (code {code})")
            entry = {"name": name, "error_code": code, "error_meaning": meaning}
            enr = (pnp_enrichment or {}).get(name)
            if not enr and pnp_enrichment:
                lu = de.PnpEnrichmentLookup.from_index(pnp_enrichment)
                enr = de._match_pnp_enrichment(name, pnp_enrichment, lookup=lu)
            if enr:
                entry = de.merge_enrichment_into_device(entry, enr)
            else:
                entry["display_name"] = resolve_device_display_label(
                    name,
                    (d.get("PNPClass") or ""),
                    (d.get("Manufacturer") or ""),
                    device_id=(d.get("DeviceID") or ""),
                )
            result.append(entry)
            if len(result) >= 30:
                break
        return result
    ps = r"""
    Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | Select-Object -First 30 Name, ConfigManagerErrorCode | ForEach-Object {
        [PSCustomObject]@{ Name=$_.Name; ConfigManagerErrorCode=[int]$_.ConfigManagerErrorCode }
    } | ConvertTo-Json
    """
    ok, out = run_powershell(ps)
    if not ok or not out:
        return result
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for d in data:
            name = (d.get("Name") or "").strip()
            code = int(d.get("ConfigManagerErrorCode", 0))
            if not name or code == 0:
                continue
            meaning = DEVICE_ERROR_CODES.get(code, f"Device problem (code {code})")
            result.append({"name": name, "error_code": code, "error_meaning": meaning})
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return result


# Device classes we do not flag as "may need driver" (system/ACPI devices that are supposed to have no user driver)
GENERIC_DRIVER_IGNORE_CLASSES = {
    "extension", "firmware", "system", "softwaredevice", "volume", "multifunction",
}
# Name patterns that suggest a generic driver (device may need vendor-specific driver).
# Excludes PCIe root ports / host bridges (no user driver needed).
GENERIC_DRIVER_NAME_PATTERNS = (
    "unknown device",
    "pci device",
    "sm bus controller",
    "standard sata ahci controller",
    "standard nvme controller",
    "standard nvm express controller",
    "standard disk drive",
    "standard floppy disk controller",
    "standard openhcd usb host controller",
    "standard enhanced pci to usb host controller",
    "standard ps/2 keyboard",
    "standard ps/2 mouse",
    "universal serial bus (usb) controller",
    "usb composite device",
    "usb root hub",
    "base system device",
    "unknown pci device",
    "pci standard host cpu bridge",
    "pci-to-pci bridge",
    "high definition audio device",
    "system timer",
    "system speaker",
    "motherboard resources",
    "microsoft basic display adapter",
    "microsoft basic render driver",
    "video controller (vga compatible)",
    "generic pnp monitor",
    "generic bluetooth adapter",
    "generic usb hub",
    "ethernet controller",  # paired with vendor check in _device_uses_generic_driver
    "raid controller",
    "scsi raid",
    "storage controller",
    "memory controller",
    "communications controller",
)

# Signed-driver / device-name hints (vendor driver usually names the chip).
_GENERIC_DRIVER_INVENTORY_HINTS = (
    "standard ",
    "generic ",
    "microsoft ",
    " (standard)",
    "basic display",
    "basic render",
    "ehci ",
    "ohci ",
    "uhci ",
)


def _device_name_has_oem_vendor(name: str) -> bool:
    """True when the device name already identifies a vendor (not a plain generic label)."""
    n = (name or "").lower()
    if any(
        tok in n
        for tok in (
            "amd ", "amd-", "advanced micro", "nvidia", "geforce", "radeon",
            "intel(r)", "intel ", "realtek", "qualcomm", "mediatek", "broadcom",
            "killer ", "marvell", "atheros", "tplink", "tp-link", "lg electronics",
            "samsung", "dell ", "lenovo", "hp ", "asus", "acer ", "logitech",
        )
    ):
        return True
    if "high definition audio" in n and any(
        x in n for x in ("amd", "realtek", "nvidia", "intel", "creative", "conexant")
    ):
        return True
    return False


def _generic_pattern_matches(name_lower: str, pattern: str) -> bool:
    if pattern not in name_lower:
        return False
    if pattern == "high definition audio device" and _device_name_has_oem_vendor(name_lower):
        return False
    if pattern == "ethernet controller" and _device_name_has_oem_vendor(name_lower):
        return False
    return True


def _device_uses_generic_driver(
    name: str,
    pnp_class: str,
    inventory_row: dict | None = None,
) -> bool:
    """True if PnP name or signed-driver row looks like a generic/Microsoft driver."""
    name_lower = (name or "").lower()
    if any(_generic_pattern_matches(name_lower, p) for p in GENERIC_DRIVER_NAME_PATTERNS):
        return True
    if inventory_row:
        inv_name = (inventory_row.get("name") or "").lower()
        if any(h in inv_name for h in _GENERIC_DRIVER_INVENTORY_HINTS):
            return True
        ver = (inventory_row.get("version") or "").lower()
        if ver in ("", "?", "0.0.0.0", "10.0.0.0") and pnp_class in (
            "net", "display", "media", "usb", "bluetooth", "scsiadapter",
        ):
            return True
    # Network/display: only flag when signed-driver row also looks generic (reduces false positives)
    if pnp_class in ("net", "display") and inventory_row:
        inv_name = (inventory_row.get("name") or "").lower()
        if any(h in inv_name for h in _GENERIC_DRIVER_INVENTORY_HINTS):
            if not any(
                v in name_lower
                for v in (
                    "intel", "realtek", "killer", "broadcom", "qualcomm", "mediatek",
                    "nvidia", "radeon", "amd", "marvell", "atheros", "tplink", "tp-link",
                )
            ):
                return True
    return False


def get_devices_with_generic_driver(
    pnp_list: list[dict] | None = None,
    inventory: list[dict] | None = None,
    edid_map: dict[str, dict] | None = None,
    pnp_enrichment: dict[str, dict] | None = None,
    disk_by_pnp_fragment: dict[str, str] | None = None,
) -> list[dict]:
    """
    Return devices that have a *generic* driver (Code 0 = working) but may need a vendor driver.
    If pnp_list from get_pnp_entities_for_analysis() is provided, filter in Python (no extra PowerShell).
    Excludes device classes in GENERIC_DRIVER_IGNORE_CLASSES to avoid false positives (ACPI, etc.).
    Each item: { "name", "pnp_class", "driver" (signed name if known), "version", "date" }.
    """
    inv_by_name = {(d.get("name") or ""): d for d in (inventory or [])}
    result = []
    if pnp_list:
        for d in pnp_list:
            if int(d.get("ConfigManagerErrorCode", 0)) != 0:
                continue
            name = (d.get("Name") or "").strip()
            pnp_class = (d.get("PNPClass") or "").strip().lower()
            if not name:
                continue
            if pnp_class and any(pnp_class.startswith(c) for c in GENERIC_DRIVER_IGNORE_CLASSES):
                continue
            row = inv_by_name.get(name)
            if not _device_uses_generic_driver(name, pnp_class, row):
                continue
            enr = (pnp_enrichment or {}).get(name)
            if not enr:
                enr = de.enrich_pnp_device(
                    d,
                    monitor_edid=edid_map,
                    disk_by_pnp_fragment=disk_by_pnp_fragment,
                    known_vendor_fn=_extract_vendor_from_string,
                )
            entry = {
                "name": name,
                "display_name": enr.get("display_name") or name,
                "manufacturer": enr.get("manufacturer") or "",
                "pnp_class": d.get("PNPClass") or "",
                "device_id": enr.get("device_id") or "",
                "vendor_key": enr.get("vendor_key") or "",
            }
            if row:
                entry["driver"] = (row.get("name") or name)
                entry["version"] = (row.get("version") or "").strip() or "?"
                entry["date"] = _parse_json_date(row.get("date", ""))
            result.append(entry)
            if len(result) >= 40:
                break
        return result
    ps = r"""
    Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.ConfigManagerErrorCode -eq 0 } | Select-Object -First 200 Name, PNPClass | ForEach-Object {
        [PSCustomObject]@{ Name=($_.Name -replace '\s+', ' ').Trim(); PNPClass=($_.PNPClass -replace '\s+', ' ').Trim() }
    } | ConvertTo-Json
    """
    ok, out = run_powershell(ps)
    if not ok or not out:
        return result
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for d in data:
            name = (d.get("Name") or "").strip()
            pnp_class = (d.get("PNPClass") or "").strip().lower()
            if not name:
                continue
            if pnp_class and any(pnp_class.startswith(c) for c in GENERIC_DRIVER_IGNORE_CLASSES):
                continue
            row = inv_by_name.get(name)
            if _device_uses_generic_driver(name, pnp_class, row):
                enr = de.enrich_pnp_device(
                    {"Name": name, "PNPClass": pnp_class, "Manufacturer": d.get("Manufacturer"), "DeviceID": d.get("DeviceID")},
                    monitor_edid=edid_map,
                    disk_by_pnp_fragment=disk_by_pnp_fragment,
                    known_vendor_fn=_extract_vendor_from_string,
                )
                entry = {
                    "name": name,
                    "display_name": enr.get("display_name") or name,
                    "manufacturer": enr.get("manufacturer") or "",
                    "pnp_class": d.get("PNPClass") or "",
                    "device_id": enr.get("device_id") or "",
                    "vendor_key": enr.get("vendor_key") or "",
                }
                if row:
                    entry["driver"] = (row.get("name") or name)
                    entry["version"] = (row.get("version") or "").strip() or "?"
                    entry["date"] = _parse_json_date(row.get("date", ""))
                result.append(entry)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return result[:40]


# Recognizable hardware device classes for the "most common devices" summary list.
# Internal plumbing (SYSTEM, SOFTWARECOMPONENT/DEVICE, HIDCLASS, AUDIOENDPOINT, etc.) is
# deliberately excluded here — it still appears in the full "All devices" list.
_COMMON_DEVICE_CLASSES = {
    "display", "net", "bluetooth", "media", "scsiadapter", "diskdrive",
    "volume", "processor", "monitor", "keyboard", "mouse", "camera",
    "battery", "firmware", "printqueue", "usb",
}
# A few discrete GPU/NIC names worth surfacing even if the OS reports a generic class.
_COMMON_DEVICE_RE = re.compile(
    r"NVIDIA GeForce|NVIDIA RTX|Radeon RX|Radeon Graphics|Intel\(R\) (?:Arc|Iris|UHD|HD Graphics)",
    re.IGNORECASE,
)


def _parse_signed_driver_cim(data: dict) -> tuple[dict, list]:
    """Parse Win32_PnPSignedDriver JSON -> (bios dict, device rows)."""
    bios = {}
    rows = []
    if not data:
        return bios, rows
    bios_data = data.get("Bios")
    if isinstance(bios_data, dict):
        bios = {
            "manufacturer": bios_data.get("Manufacturer", ""),
            "version": bios_data.get("SMBIOSBIOSVersion", ""),
            "date": bios_data.get("ReleaseDate", ""),
            "serial_number": (bios_data.get("SerialNumber") or "").strip(),
        }
    drivers_data = data.get("Drivers")
    if drivers_data is None:
        return bios, rows
    drivers_list = [drivers_data] if isinstance(drivers_data, dict) else drivers_data
    seen = set()
    for d in drivers_list:
        if not isinstance(d, dict):
            continue
        name = (d.get("DeviceName") or "").strip()
        version = (d.get("DriverVersion") or "").strip()
        if not name:
            continue
        key = (name.lower(), version)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "name": name,
            "version": version,
            "date": d.get("DriverDate", ""),
            "device_class": (d.get("DeviceClass") or "").strip(),
        })
    rows.sort(key=lambda x: ((x.get("device_class") or "").lower(), x["name"].lower()))
    return bios, rows


def device_row_is_common_hardware(row: dict) -> bool:
    """True for user-facing hardware (GPU, NIC, storage, etc.), not internal PnP plumbing."""
    name = (row.get("display_name") or row.get("name") or "").strip()
    if not name:
        return False
    if name in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL):
        return True
    if (row.get("device_class") or "").lower() in _COMMON_DEVICE_CLASSES:
        return True
    return bool(_COMMON_DEVICE_RE.search(name))


def _common_devices_from_rows(rows: list) -> list:
    return [d for d in rows if device_row_is_common_hardware(d)]


def get_bios_and_driver_versions(include_all: bool = False) -> dict:
    """Get BIOS and device driver rows for the System tab.

    By default (include_all=False) only queries hardware-relevant devices so analysis
    stays fast; the full list is loaded on demand via get_all_installed_driver_devices().
    """
    result = {"bios": {}, "drivers": [], "all_drivers": [], "device_inventory": []}
    if include_all:
        driver_where = "$_.DeviceName"
    else:
        driver_where = (
            "$_.DeviceName -and ("
            "$_.DeviceClass -in @('Display','Net','Bluetooth','Media','SCSIAdapter',"
            "'DiskDrive','Volume','Processor','Monitor','Keyboard','Mouse','Camera',"
            "'Battery','Firmware','PrintQueue','USB','System','Computer') -or "
            "$_.DeviceName -match "
            "'NVIDIA|AMD|Intel|GeForce|Radeon|Realtek|MediaTek|Qualcomm|Broadcom|Marvell|"
            "Killer|GPIO|SMBus|Chipset|PCI Express|Crash Defender|Storage Controller|"
            "NVMe|Ethernet|Wi-?Fi|Wireless|Graphics|Audio|Processor'"
            ")"
        )
    ps_combined = f"""
    $bios = Get-CimInstance -ClassName Win32_BIOS -ErrorAction SilentlyContinue | Select-Object -First 1 Manufacturer, SMBIOSBIOSVersion, ReleaseDate, SerialNumber
    $drivers = Get-CimInstance -ClassName Win32_PnPSignedDriver -ErrorAction SilentlyContinue | Where-Object {{ {driver_where} }} | Select-Object DeviceName, DriverVersion, DriverDate, DeviceClass
    [PSCustomObject]@{{
        Bios = if ($bios) {{ [PSCustomObject]@{{ Manufacturer=$bios.Manufacturer; SMBIOSBIOSVersion=$bios.SMBIOSBIOSVersion; ReleaseDate=$bios.ReleaseDate; SerialNumber=$bios.SerialNumber }} }} else {{ $null }}
        Drivers = @($drivers | ForEach-Object {{ [PSCustomObject]@{{ DeviceName=$_.DeviceName; DriverVersion=$_.DriverVersion; DriverDate=$_.DriverDate; DeviceClass=$_.DeviceClass }} }})
    }} | ConvertTo-Json -Depth 3
    """
    ok, out = run_powershell(ps_combined)
    if not ok or not out:
        return result
    try:
        data = json.loads(out)
        bios, rows = _parse_signed_driver_cim(data)
        result["bios"] = bios
        result["device_inventory"] = rows
        result["drivers"] = _common_devices_from_rows(rows)
        if include_all:
            result["all_drivers"] = rows
    except json.JSONDecodeError:
        pass
    return result


_DRIVER_INVENTORY_CLASS_SHARDS: tuple[tuple[str, ...], ...] = (
    ("Display", "Monitor", "Media", "Camera", "Keyboard", "Mouse", "AudioEndpoint"),
    ("Net", "Bluetooth", "USB", "PrintQueue", "Ports"),
    ("DiskDrive", "Volume", "SCSIAdapter", "Processor", "Firmware", "Battery"),
    ("System", "Computer", "HIDClass", "SecurityDevices", "Biometric", "SmartCardReader"),
    ("SoftwareDevice", "WPD", "Sensor", "SDHost", "LegacyDriver", "MTD", "CDROM"),
)


def _ps_signed_drivers_shard(classes: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{c}'" for c in classes)
    return f"""
$drivers = @(Get-CimInstance Win32_PnPSignedDriver -EA 0 | Where-Object {{
  $_.DeviceName -and ($_.DeviceClass -in @({quoted}))
}} | Select-Object DeviceName, DriverVersion, DriverDate, DeviceClass)
@{{ Drivers = @($drivers) }} | ConvertTo-Json -Depth 4 -Compress
"""


def _ps_signed_drivers_catchall(excluded_classes: frozenset[str]) -> str:
    quoted = ",".join(f"'{c}'" for c in sorted(excluded_classes))
    return f"""
$ex = @({quoted})
$drivers = @(Get-CimInstance Win32_PnPSignedDriver -EA 0 | Where-Object {{
  $_.DeviceName -and (
    -not $_.DeviceClass -or ($_.DeviceClass -notin $ex)
  )
}} | Select-Object DeviceName, DriverVersion, DriverDate, DeviceClass)
@{{ Drivers = @($drivers) }} | ConvertTo-Json -Depth 4 -Compress
"""


def _fetch_signed_driver_shard(
    classes: tuple[str, ...] | None,
    *,
    catchall_excluded: frozenset[str] | None = None,
) -> list[dict]:
    if catchall_excluded is not None:
        ps = _ps_signed_drivers_catchall(catchall_excluded)
    elif classes:
        ps = _ps_signed_drivers_shard(classes)
    else:
        return []
    ok, out = run_powershell(ps, timeout=55)
    if not ok or not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    _, rows = _parse_signed_driver_cim(data if isinstance(data, dict) else {"Drivers": data})
    return rows


def _merge_driver_inventory_rows(parts: list[list[dict]]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for rows in parts:
        for r in rows:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            key = (name.lower(), (r.get("version") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
    merged.sort(key=lambda x: ((x.get("device_class") or "").lower(), x["name"].lower()))
    return merged


def _fetch_all_signed_driver_rows_parallel(
    progress_cb: Callable[[str], None] | None = None,
) -> list[dict]:
    """Query Win32_PnPSignedDriver in parallel class shards, then merge."""

    def prog(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    excluded: set[str] = set()
    for shard in _DRIVER_INVENTORY_CLASS_SHARDS:
        excluded.update(shard)
    tasks: list[tuple[str, tuple[str, ...] | None, frozenset[str] | None]] = [
        (f"class shard {i + 1}/{len(_DRIVER_INVENTORY_CLASS_SHARDS)}", s, None)
        for i, s in enumerate(_DRIVER_INVENTORY_CLASS_SHARDS)
    ]
    tasks.append(("remaining drivers", None, frozenset(excluded)))

    parts: list[list[dict]] = []
    workers = min(6, len(tasks))
    prog(f"Reading driver inventory ({len(tasks)} parallel queries)…")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {}
        for label, classes, catchall in tasks:
            if catchall is not None:
                fut = ex.submit(_fetch_signed_driver_shard, None, catchall_excluded=catchall)
            else:
                fut = ex.submit(_fetch_signed_driver_shard, classes or ())
            futures[fut] = label
        done = 0
        for fut in as_completed(futures):
            done += 1
            label = futures[fut]
            try:
                parts.append(fut.result())
                prog(f"Driver inventory {done}/{len(tasks)} ({label})…")
            except Exception:  # noqa: BLE001
                parts.append([])
                prog(f"Driver inventory {done}/{len(tasks)} ({label} failed)…")
    merged = _merge_driver_inventory_rows(parts)
    if not merged:
        prog("Parallel inventory empty — retrying single query…")
        info = get_bios_and_driver_versions(include_all=True)
        return info.get("all_drivers") or []
    prog(f"Driver inventory complete ({len(merged)} device(s)).")
    return merged


def _fetch_all_signed_driver_rows_sequential(
    progress_cb: Callable[[str], None] | None = None,
) -> list[dict]:
    """Single-threaded WMI inventory (stable inside Qt worker threads / frozen GUI)."""

    def prog(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    excluded: set[str] = set()
    for shard in _DRIVER_INVENTORY_CLASS_SHARDS:
        excluded.update(shard)
    tasks: list[tuple[str, tuple[str, ...] | None, frozenset[str] | None]] = [
        (f"class shard {i + 1}/{len(_DRIVER_INVENTORY_CLASS_SHARDS)}", s, None)
        for i, s in enumerate(_DRIVER_INVENTORY_CLASS_SHARDS)
    ]
    tasks.append(("remaining drivers", None, frozenset(excluded)))
    parts: list[list[dict]] = []
    prog(f"Reading driver inventory (0/{len(tasks)} queries)…")
    for done, (label, classes, catchall) in enumerate(tasks, start=1):
        try:
            if catchall is not None:
                parts.append(_fetch_signed_driver_shard(None, catchall_excluded=catchall))
            else:
                parts.append(_fetch_signed_driver_shard(classes or ()))
            prog(f"Driver inventory {done}/{len(tasks)} ({label})…")
        except Exception:  # noqa: BLE001
            parts.append([])
            prog(f"Driver inventory {done}/{len(tasks)} ({label} failed)…")
    merged = _merge_driver_inventory_rows(parts)
    if not merged:
        prog("Inventory empty — retrying single query…")
        info = get_bios_and_driver_versions(include_all=True)
        return info.get("all_drivers") or []
    prog(f"Driver inventory complete ({len(merged)} device(s)).")
    return merged


def get_all_installed_driver_devices(
    progress_cb: Callable[[str], None] | None = None,
    *,
    sequential: bool = False,
) -> list:
    """Full signed-driver inventory; parallel or sequential WMI shards."""
    if sequential:
        return _fetch_all_signed_driver_rows_sequential(progress_cb)
    return _fetch_all_signed_driver_rows_parallel(progress_cb)


def get_ssd_firmware_inventory() -> list[dict]:
    """
    Physical drives with firmware revision from WMI (for Firmware tab SSD compare).
    Each item: model, firmware_revision, serial_number, interface_type, size_gb,
    vendor_key, storage_class, include_firmware.
    """
    ps = r"""
    $rows = [System.Collections.ArrayList]@()
    $seen = @{}
    $physical = @{}
    foreach ($pd in Get-CimInstance -Namespace root\Microsoft\Windows\Storage -ClassName MSFT_PhysicalDisk -ErrorAction SilentlyContinue) {
        $sn = ($pd.SerialNumber -as [string]).Trim()
        if ($sn) { $physical[$sn] = $pd }
    }
    foreach ($d in Get-CimInstance Win32_DiskDrive -ErrorAction SilentlyContinue) {
        $model = ($d.Model -as [string]).Trim()
        if (-not $model) { continue }
        $serial = ($d.SerialNumber -as [string]).Trim()
        $key = $model + '|' + $serial
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $iface = ($d.InterfaceType -as [string]).Trim()
        $mediaType = $null
        $busType = $null
        if ($serial -and $physical.ContainsKey($serial)) {
            $pd = $physical[$serial]
            $mediaType = $pd.MediaType
            $busType = $pd.BusType
        }
        [void]$rows.Add([PSCustomObject]@{
            Model = $model
            FirmwareRevision = ($d.FirmwareRevision -as [string]).Trim()
            SerialNumber = $serial
            InterfaceType = $iface
            SizeGB = if ($d.Size) { [math]::Round($d.Size / 1GB, 1) } else { 0 }
            MediaType = $mediaType
            BusType = $busType
        })
    }
    foreach ($pd in Get-CimInstance -Namespace root\Microsoft\Windows\Storage -ClassName MSFT_PhysicalDisk -ErrorAction SilentlyContinue) {
        if ($pd.MediaType -ne 4) { continue }
        $model = ($pd.FriendlyName -as [string]).Trim()
        if (-not $model) { continue }
        $serial = ($pd.SerialNumber -as [string]).Trim()
        $key = $model + '|' + $serial
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        [void]$rows.Add([PSCustomObject]@{
            Model = $model
            FirmwareRevision = ($pd.FirmwareVersion -as [string]).Trim()
            SerialNumber = $serial
            InterfaceType = 'SSD'
            SizeGB = if ($pd.Size) { [math]::Round($pd.Size / 1GB, 1) } else { 0 }
            MediaType = $pd.MediaType
            BusType = $pd.BusType
        })
    }
    $rows | ConvertTo-Json
    """
    ok, out = run_powershell(ps)
    if not ok or not out:
        return []
    drives: list[dict] = []
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for d in data:
            model = (d.get("Model") or "").strip()
            if not model:
                continue
            drives.append({
                "model": model,
                "firmware_revision": (d.get("FirmwareRevision") or "").strip() or "?",
                "serial_number": (d.get("SerialNumber") or "").strip(),
                "interface_type": (d.get("InterfaceType") or "").strip(),
                "size_gb": d.get("SizeGB") or 0,
                "vendor_key": _infer_ssd_vendor_from_model(model),
                "storage_class": _classify_storage_drive(
                    model,
                    (d.get("InterfaceType") or "").strip(),
                    d.get("SizeGB") or 0,
                    media_type=d.get("MediaType"),
                    bus_type=d.get("BusType"),
                ),
            })
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return [d for d in drives if d.get("storage_class") != "usb_removable"]


def _classify_storage_drive(
    model: str,
    interface_type: str,
    size_gb: float,
    *,
    media_type: int | None = None,
    bus_type: int | None = None,
) -> str:
    """Classify physical storage for firmware tab filtering and export diagnostics."""
    m = (model or "").lower()
    iface = (interface_type or "").lower()
    # BusType 7 = USB (MSFT_PhysicalDisk)
    if bus_type == 7 or "usb" in iface:
        if size_gb and size_gb <= 256 and any(
            k in m for k in ("ultra", "cruzer", "datatraveler", "flash drive", "thumb")
        ):
            return "usb_removable"
        return "usb_storage"
    if "lx00" in m or "sshd" in m or "solid state hybrid" in m:
        return "hybrid_hdd"
    if media_type == 4 or iface == "ssd" or "nvme" in m:
        return "nvme_ssd" if "nvme" in m else "ssd"
    if media_type == 3:
        return "hdd"
    return "fixed_disk"


def _infer_ssd_vendor_from_model(model: str) -> str:
    m = (model or "").lower()
    for needle, key in (
        ("samsung", "samsung"),
        ("wdc ", "wd"),
        ("wd ", "wd"),
        ("western digital", "wd"),
        ("sandisk", "sandisk"),
        ("crucial", "crucial"),
        ("micron", "micron"),
        ("intel", "intel"),
        ("kingston", "kingston"),
        ("kioxia", "kioxia"),
        ("toshiba", "toshiba"),
        ("seagate", "seagate"),
        ("sk hynix", "skhynix"),
        ("hynix", "skhynix"),
        ("phison", "phison"),
        ("silicon power", "siliconpower"),
        ("adata", "adata"),
        ("teamgroup", "teamgroup"),
        ("corsair", "corsair"),
    ):
        if needle in m:
            return key
    return ""


