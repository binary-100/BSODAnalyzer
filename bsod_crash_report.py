"""Crash analysis, recommendations, and text/GUI report formatting."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Callable

import device_enrichment as de
import log_read_windows as lrw

from bsod_events import compute_crash_timeline
from bsod_hardware_wmi import (
    CHIPSET_DEVICE_AMD,
    CHIPSET_DEVICE_INTEL,
    _common_devices_from_rows,
    _extract_vendor_from_string,
    _parse_json_date,
    chipset_driver_catalog_entries,
)
from bsod_minidump import (
    _DUMP_EVENT_MATCH_HOURS,
    analyze_minidump_with_cdb,
    assess_minidump_prerequisites,
    build_capture_readiness,
    minidump_capture_action_step,
)
from bsod_runtime import run_powershell

from crash_report_events import (
    decode_exception_code as _decode_exception_code,
    group_events_by_incident as _group_events_by_incident,
    parse_p1 as _parse_p1,
)

from crash_report_timeline import (
    _dump_matches_event_time,
    _dump_matches_recent_events,
    _event41_stop_verified,
    _incident_group_for_event,
    _parse_event_time,
    _stop_from_event,
    _usable_bugcheck_events,
    _verified_stop_for_incident,
    build_incident_timeline,
    resolve_crash_code,
)

from crash_report_culprit import (
    CRASH_SYNTH_DEVICE_PREFIX,
    DRIVER_TO_HARDWARE,
    DRIVER_VENDOR_PREFIX,
    POSSIBLE_DRIVERS,
    build_culprit_system_callout,
    crash_synthetic_device_key,
    device_inventory_for_matching,
    find_culprit_devices,
    has_crash_faulting_driver,
    is_crash_synthetic_device_key,
    is_kernel_shim_fault_module,
    is_platform_chipset_device_key,
    lookup_inventory_row,
    platform_chipset_crash_attention,
    refresh_model_culprit_fields,
    resolve_crash_culprit_context,
    _culprit_info_row_is_placeholder,
    _driver_name_from_recommendation,
    _filter_possible_drivers_list,
    _infer_driver_vendor,
    _recommendation_applies_to_system,
)

from crash_report_fix_plan import (
    FIX_BOOT_RECOVERY,
    FIX_CPU_PLATFORM,
    FIX_DRIVER_IRQL,
    FIX_GRAPHICS,
    FIX_MEMORY,
    FIX_NAMED_DRIVER,
    FIX_STORAGE,
    FIX_THERMAL,
    FIX_UNCERTAIN,
    FIX_WHEA_COMPONENT,
    build_boot_failure_playbook_steps,
    build_crash_fix_plan,
    build_platform_update_options,
    derive_report_fix_focus,
    _describe_action_plan_link_basis,
    _merge_update_options,
    _needs_platform_driver_links,
    _GPU_DRIVER_FRAGMENTS,
)

from crash_report_format import (
    _ANALYSIS_TASK_LABELS,
    _MAX_LINE_LEN,
    _REPORT_WIDTH,
    _analysis_gap_message,
    _build_recommendations,
    _build_summary,
    _friendly_driver_label,
    _quick_answer_lines,
    _section_header,
    _severity_for_display,
    _wrap_text,
    _wrap_with_prefix,
    build_display_model,
    build_report_derivations,
    format_minidump_summary_line,
    format_output,
    format_output_from_fmt_args,
    minidump_without_bugcheck_gap,
)

_WHEA_NEAR_CRASH_WINDOW_MIN = 10

_THERMAL_NEAR_CRASH_WINDOW_MIN = 10

_RELIABILITY_NEAR_CRASH_WINDOW_MIN = 15

_INCIDENT_WHEA_WINDOW_MIN = 2

from crash_report_narrative import (
    boot_events_near_crash,
    build_crash_confidence_summary,
    build_event_log_coverage_summary,
    build_hardware_findings_from_logs,
    infer_likely_cause_type,
    _analysis_confidence_label,
    _build_definitive_cause,
    _build_plain_english_summary,
    _match_event_to_crash,
    _plain_english_from_repair_narrative,
    _reliability_events_near_crash,
    _summarize_livekernel_message,
    _user_friendly_stop_summary,
)





def _ba(name: str):
    """Lazy bsod_analyzer lookup — avoids import cycles during module load."""
    import bsod_analyzer as ba

    return getattr(ba, name)


BUGCHECK_CODES = {
    0x0000000A: ("IRQL_NOT_LESS_OR_EQUAL", "Driver or software accessed invalid memory at wrong IRQL. Often: bad drivers, memory corruption."),
    0x0000000D: ("INVALID_DATA_ACCESS_TRAP", "Kernel-mode driver accessed invalid memory. Driver or hardware issue."),
    0x0000001A: ("MEMORY_MANAGEMENT", "Severe memory management error. Often: faulty RAM, corrupt drivers."),
    0x0000001E: ("KMODE_EXCEPTION_NOT_HANDLED", "Kernel-mode exception. Usually: buggy driver, hardware failure."),
    0x0000003B: ("SYSTEM_SERVICE_EXCEPTION", "Exception in system service. Often: driver, antivirus, or compatibility issue."),
    0x00000044: ("MULTIPLE_IRP_COMPLETE_REQUESTS", "Driver bug - completed same request twice. Update or rollback drivers."),
    0x00000050: ("PAGE_FAULT_IN_NONPAGED_AREA", "Invalid memory access. Often: bad RAM, faulty driver, corrupt system file."),
    0x0000007A: ("KERNEL_DATA_INPAGE_ERROR", "Could not read from paging file. Often: bad disk, faulty RAM, disk controller."),
    0x0000007B: ("INACCESSIBLE_BOOT_DEVICE", "Could not access boot disk. Often: driver issue, disk failure, BIOS/SATA mode."),
    0x0000007E: ("SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", "System thread threw unhandled exception. Usually: driver problem."),
    0x0000007F: ("UNEXPECTED_KERNEL_MODE_TRAP", "Unexpected trap. Often: faulty hardware (CPU, RAM), overclocking."),
    0x0000008E: ("KERNEL_MODE_EXCEPTION_NOT_HANDLED", "Kernel exception. Similar to 0x1E - driver or hardware."),
    0x0000009C: ("MACHINE_CHECK_EXCEPTION", "CPU detected hardware error. Often: overheating, faulty CPU/RAM, overclocking."),
    0x0000009F: ("DRIVER_POWER_STATE_FAILURE", "Driver power state mismatch. Often: buggy driver, sleep/hibernate issue."),
    0x000000BE: ("ATTEMPTED_WRITE_TO_READONLY_MEMORY", "Driver wrote to read-only memory. Driver bug."),
    0x000000C2: ("BAD_POOL_CALLER", "Invalid memory pool operation. Often: driver bug, memory corruption."),
    0x000000C4: ("DRIVER_VERIFIER_DETECTED_VIOLATION", "Driver Verifier caught driver bug. Indicates problematic driver."),
    0x000000C5: ("DRIVER_CORRUPTED_EXPOOL", "Driver corrupted pool memory. Driver bug or memory issue."),
    0x000000CA: ("PNP_DETECTED_FATAL_ERROR", "Plug and Play fatal error. Driver or hardware detection issue."),
    0x000000CB: ("DRIVER_LEFT_LOCKED_PAGES_IN_PROCESS", "Driver left locked pages. Driver bug."),
    0x000000CE: ("DRIVER_UNLOADED_WITHOUT_CANCELLING_PENDING_OPERATIONS", "Driver unloaded improperly. Driver bug."),
    0x000000D1: ("DRIVER_IRQL_NOT_LESS_OR_EQUAL", "Driver accessed paged memory at high IRQL. Very common - update/rollback drivers."),
    0x000000D8: ("DRIVER_USED_EXCESSIVE_PTES", "Driver used too many page table entries. Driver or memory leak."),
    0x000000EA: ("THREAD_STUCK_IN_DEVICE_DRIVER", "Display driver hung. Often: graphics driver, GPU hardware."),
    0x000000ED: ("UNMOUNTABLE_BOOT_VOLUME", "Could not mount boot volume. Disk or file system corruption."),
    0x000000EF: ("CRITICAL_PROCESS_DIED", "Critical system process terminated. Often: malware, driver, or system file corruption."),
    0x000000F4: ("CRITICAL_OBJECT_TERMINATION", "Critical object was deleted. System process or driver issue."),
    0x000000F7: ("DRIVER_OVERRAN_STACK_BUFFER", "Driver stack overflow. Driver bug - security concern."),
    0x000000FE: ("BUGCODE_USB_DRIVER", "USB driver bug. USB device or driver issue."),
    0x00000109: ("CRITICAL_STRUCTURE_CORRUPTION", "Critical kernel structure corrupted. Often: faulty RAM, driver."),
    0x0000010E: ("VIDEO_MEMORY_MANAGEMENT_INTERNAL", "Graphics driver memory error. Update GPU drivers."),
    0x00000124: ("WHEA_UNCORRECTABLE_ERROR", "Hardware error (WHEA). CPU, GPU, RAM, or motherboard issue."),
    0x00000127: ("POOL_CORRUPTION_IN_FILE_AREA", "Pool corruption. Driver or memory issue."),
    0x00000133: ("DPC_WATCHDOG_VIOLATION", "DPC ran too long. Often: driver (network/storage/audio) or firmware."),
    0x00000139: ("KERNEL_SECURITY_CHECK_FAILURE", "Kernel security violation. Often: driver bug, memory corruption."),
    0x00000154: ("UNEXPECTED_STORE_EXCEPTION", "Storage stack bug or corruption. Often: storage/NVMe driver, filter driver, disk/file-system issue, or fast-startup resume glitch."),
    0x0000014E: ("PAGE_FAULT_IN_NONPAGED_AREA", "Same as 0x50 - invalid memory access."),
    0xC000009A: ("STATUS_INSUFFICIENT_RESOURCES", "System ran out of resources. Memory leak or too many handles."),
}

WHEA_P1_SOURCE = {
    0x0: "CPU (machine check exception - CPU core, cache, or memory controller)",
    0x1: "CPU (corrected machine check)",
    0x2: "Platform (corrected platform error)",
    0x3: "NMI (nonmaskable interrupt - hardware alarm)",
    0x4: "PCI Express device (GPU, NVMe SSD, or other PCIe card)",
    0x5: "Generic hardware",
    0x6: "Initialization error",
    0x7: "Boot error",
    0x10: "Device driver (specific driver reported the error)",
}

GENERIC_FAULT_MODULE_DEVICE = {
    # CPU / vendor identifiers (not updateable drivers)
    "authenticamd": ("AMD CPU / chipset", "CPU microcode (BIOS/UEFI update), AMD chipset drivers, or CPU/cooling hardware"),
    "genuineintel": ("Intel CPU / chipset", "CPU microcode (BIOS/UEFI update), Intel chipset drivers, or CPU/cooling hardware"),
    "centaurhauls": ("VIA/Centaur CPU", "CPU microcode or chipset drivers"),
    "rdyboost": (
        "ReadyBoost (Windows cache helper)",
        "This name often appears in hardware crashes but the fix is usually chipset drivers, BIOS, or storage — not ReadyBoost itself",
    ),
    # Windows kernel / core (usually triggered by driver or hardware)
    "ntoskrnl": ("Windows kernel", "Usually triggered by a driver or hardware - the kernel itself is not the cause"),
    "ntkrnlmp": ("Windows kernel", "Usually triggered by a driver or hardware"),
    "hal": ("Hardware abstraction layer", "Usually triggered by a driver or hardware - HAL bridges OS and hardware"),
    "win32k": ("Windows graphics subsystem", "Often GPU driver or display hardware related"),
    "win32kbase": ("Windows graphics base", "Often GPU driver or display hardware related"),
    "win32kfull": ("Windows graphics", "Often GPU driver or display hardware related"),
    "ci": ("Code Integrity", "Usually triggered by corrupt driver or malware - not CI itself"),
    "cng": ("Cryptographic Next Gen", "Usually triggered by another driver"),
    "fltmgr": ("File system filter manager", "Often storage driver, antivirus, or backup software"),
    "ksecdd": ("Kernel Security", "Usually triggered by another driver"),
    "msrpc": ("Microsoft RPC", "Usually triggered by service or driver"),
    "clipsp": ("Clipboard", "Usually triggered by another component"),
    "netio": ("Network I/O", "Often network driver (NIC, WiFi, VPN)"),
    "tcpip": ("TCP/IP stack", "Often network driver or firewall"),
    "afd": ("Ancillary Function Driver", "Sockets - often network or security software"),
    "ndis": ("Network Driver Interface", "Update the actual NIC/WiFi driver - ndis is the framework"),
    # Graphics - NVIDIA
    "nvlddmkm": ("NVIDIA GPU driver", "Update or rollback NVIDIA graphics driver from nvidia.com"),
    "nvlddmkm.sys": ("NVIDIA GPU driver", "Update or rollback NVIDIA graphics driver from nvidia.com"),
    # Graphics - AMD
    "amdkmdag": ("AMD GPU driver", "Update or rollback AMD Radeon driver from amd.com"),
    "amdkmdap": ("AMD GPU driver", "Update or rollback AMD Radeon driver from amd.com"),
    "atikmdag": ("AMD GPU driver (legacy)", "Update or rollback AMD graphics driver"),
    "atikmpag": ("AMD GPU driver (legacy)", "Update or rollback AMD graphics driver"),
    # Graphics - Intel
    "igdkmd64": ("Intel GPU driver", "Update Intel graphics from intel.com or OEM"),
    "igdkmdn64": ("Intel GPU driver", "Update Intel graphics from intel.com or OEM"),
    "igfx": ("Intel graphics", "Update Intel graphics driver"),
    # Graphics - DirectX / display
    "dxgkrnl": ("DirectX graphics kernel", "Often GPU driver - update NVIDIA/AMD/Intel graphics"),
    "dxgmms2": ("DirectX graphics", "Often GPU driver - update graphics driver"),
    "watchdog": ("Display watchdog", "GPU driver hung - update or rollback graphics driver"),
    # Storage - generic
    "storport": ("Storage port driver", "Often NVMe/SATA driver or disk firmware - update chipset/storage drivers"),
    "stornvme": ("NVMe storage", "Update NVMe/Samsung/Intel storage driver or SSD firmware"),
    "storahci": ("SATA AHCI", "Update chipset/SATA driver"),
    "nvme": ("NVMe", "Update NVMe driver or SSD firmware"),
    "ntfs": ("NTFS file system", "Often storage driver, disk, or RAM - not NTFS itself"),
    "volmgr": ("Volume manager", "Often storage driver or disk"),
    "volmgrx": ("Volume manager", "Often storage driver or disk"),
    "partmgr": ("Partition manager", "Often storage driver"),
    "disk": ("Disk driver", "Update storage/SATA/NVMe driver"),
    "fvevol": ("BitLocker volume", "Often storage driver or TPM"),
    # Storage - Intel
    "iastor": ("Intel RST storage", "Update Intel Rapid Storage driver"),
    "iastoravc": ("Intel RST", "Update Intel Rapid Storage driver"),
    # Storage - AMD
    "amd_sata": ("AMD SATA", "Update AMD chipset driver"),
    "amd_xhci": ("AMD USB/xHCI", "Update AMD chipset driver"),
    # Network - Intel
    "e1i": ("Intel Ethernet", "Update Intel LAN driver"),
    "e1iexpress": ("Intel Ethernet", "Update Intel LAN driver"),
    "i40e": ("Intel 40Gb Ethernet", "Update Intel network driver"),
    "ixn": ("Intel network", "Update Intel network driver"),
    # Network - Realtek
    "rt64": ("Realtek Ethernet", "Update Realtek LAN driver"),
    "rtwlane": ("Realtek WiFi", "Update Realtek WiFi driver"),
    "rt640x64": ("Realtek", "Update Realtek driver"),
    "rtvlan": ("Realtek", "Update Realtek driver"),
    # Network - Qualcomm/Atheros
    "qcamain": ("Qualcomm WiFi", "Update Qualcomm/Atheros WiFi driver"),
    "athr": ("Qualcomm/Atheros WiFi", "Update WiFi driver"),
    "athw": ("Qualcomm/Atheros WiFi", "Update WiFi driver"),
    # Network - other
    "mlx4": ("Mellanox network", "Update Mellanox driver"),
    "mellanox": ("Mellanox network", "Update Mellanox driver"),
    "killer": ("Killer network", "Update Killer/Intel network driver"),
    # USB
    "usbccgp": ("USB generic parent", "Often USB device or controller driver"),
    "ucx01000": ("USB host controller", "Update chipset/USB driver"),
    "asmt": ("ASMedia USB", "Update ASMedia USB driver"),
    "usbhub": ("USB hub", "Often USB device driver"),
    # ACPI / firmware
    "acpi": ("ACPI driver", "Update BIOS/UEFI or chipset driver"),
    "wmilib": ("WMI", "Usually triggered by another driver"),
    "iqvw64e": ("Intel driver", "Intel ME/firmware - update BIOS and Intel drivers"),
    # Antivirus / security (often need update or disable to test)
    "klif": ("Kaspersky", "Update Kaspersky or temporarily disable to test"),
    "kldisk": ("Kaspersky", "Update Kaspersky or temporarily disable to test"),
    "mfeavfk": ("McAfee", "Update McAfee or temporarily disable to test"),
    "mfewfpk": ("McAfee", "Update McAfee or temporarily disable to test"),
    "asw": ("Avast", "Update Avast or temporarily disable to test"),
    "bddev": ("Bitdefender", "Update Bitdefender or temporarily disable to test"),
    "cbk7": ("Carbon Black", "Update or temporarily disable to test"),
    # Server / SMB
    "srvnet": ("SMB network", "Update network driver or disable SMB features to test"),
    "srv": ("SMB server", "Update network driver or SMB-related software"),
    # WDF (driver framework - real fault is usually in a miniport)
    "wdf": ("Windows Driver Framework", "The actual fault is in a child driver - check other modules in dump"),
    "wdf01000": ("Windows Driver Framework", "The actual fault is in a child driver"),
}


_PLATFORM_CPU_MODULES = frozenset({"authenticamd", "genuineintel", "centaurhauls"})

_MISLEADING_FAULT_MODULES = frozenset({
    "rdyboost", "readyboost", "ntoskrnl", "ntkrnlmp", "hal", "watchdog",
})

_KERNEL_SHIM_MODULES = frozenset({
    "ntoskrnl", "ntkrnlmp", "hal", "win32k", "win32kbase", "win32kfull",
    "dxgkrnl", "dxgmms2", "watchdog", "fltmgr", "ndis", "netio", "tcpip", "afd",
    "ci", "cng", "msrpc", "clipsp", "volmgr", "volmgrx", "partmgr", "disk", "ntfs",
})

_HARDWARE_LEAN_STOP_CODES = frozenset({0x7F, 0x9C, 0x124})

_OEM_SUPPORT_URLS = {
    "dell": "https://www.dell.com/support/home",
    "alienware": "https://www.dell.com/support/home",
    "hp": "https://support.hp.com/us-en/drivers",
    "hewlett-packard": "https://support.hp.com/us-en/drivers",
    "lenovo": "https://support.lenovo.com/us/en/solutions/ht003013",
    "asus": "https://www.asus.com/support/download-center/",
    "acer": "https://www.acer.com/us-en/support",
    "msi": "https://www.msi.com/support/download",
    "microsoft": "https://support.microsoft.com/windows",
    "gigabyte": "https://www.gigabyte.com/Support",
}

_VENDOR_DRIVER_URLS = {
    "nvidia": ("https://www.nvidia.com/en-us/drivers/", "NVIDIA driver downloads"),
    "amd": ("https://www.amd.com/en/support/download/drivers.html", "AMD driver downloads (pick Graphics or Chipset)"),
    "intel": ("https://www.intel.com/content/www/us/en/download-center/home.html", "Intel driver & support assistant"),
    "realtek": ("https://www.realtek.com/Download", "Realtek driver downloads"),
    "mediatek": ("https://www.mediatek.com/products/smartphones-2/mediatek-helio-wifi-6", "MediaTek Wi-Fi drivers (or use OEM site)"),
    "qualcomm": ("https://www.qualcomm.com/support", "Qualcomm / OEM Wi-Fi drivers"),
    "broadcom": ("https://www.broadcom.com/support", "Broadcom drivers (often via OEM)"),
    "killer": ("https://www.intel.com/content/www/us/en/download-center/home.html", "Killer networking (Intel)"),
    "lg": ("https://www.lg.com/us/support/software-firmware-drivers", "LG drivers & software"),
    "benq": ("https://www.benq.com/en-us/support/downloads.html", "BenQ drivers & software"),
    "viewsonic": ("https://www.viewsonic.com/us/support/downloads", "ViewSonic downloads"),
    "philips": ("https://www.philips.com/c-w/support-home.html", "Philips support"),
    "samsung": ("https://www.samsung.com/us/support/downloads/", "Samsung drivers & software"),
    "logitech": ("https://www.logitech.com/en-us/software", "Logitech software & drivers"),
    "tplink": ("https://www.tp-link.com/us/support/download/", "TP-Link downloads"),
    "netgear": ("https://www.netgear.com/support/download/", "NETGEAR downloads"),
    "marvell": ("https://www.marvell.com/support/downloads.html", "Marvell drivers & downloads"),
    "synaptics": ("https://www.synaptics.com/products/touchpad-driver", "Synaptics touchpad drivers"),
    "elan": ("http://www.emtouch.elan.com/Download%20Driver.html", "ELAN touchpad drivers"),
    "dell": ("https://www.dell.com/support/home/en-us/drivers", "Dell drivers & downloads"),
    "hp": ("https://support.hp.com/us-en/drivers", "HP drivers & downloads"),
    "lenovo": ("https://pcsupport.lenovo.com/us/en/products", "Lenovo drivers & downloads"),
    "acer": ("https://www.acer.com/us-en/support", "Acer drivers & downloads"),
    "asus": ("https://www.asus.com/support/download-center/", "ASUS drivers & downloads"),
}

_AMD_CHIPSET_DRIVER_URL = "https://www.amd.com/en/support/download/drivers.html"

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

def get_wmi_monitor_edid_by_device_id() -> dict[str, dict]:
    """
    Read monitor EDID labels from WMI (root\\wmi\\WmiMonitorID).
    Keys are upper-case DeviceID fragments (e.g. DISPLAY\\\\LGD1234) for matching PnP rows.
    """
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$rows = @()
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue | ForEach-Object {
  $mfr = -join ($_.ManufacturerName | ForEach-Object { [char]$_ })
  $prod = -join ($_.ProductCodeID | ForEach-Object { [char]$_ })
  $rows += [PSCustomObject]@{
    InstanceName = [string]$_.InstanceName
    ManufacturerCode = ($mfr -replace '\s+$','').Trim()
    ProductCode = ($prod -replace '\s+$','').Trim()
  }
}
$rows | ConvertTo-Json -Compress
"""
    ok, out = run_powershell(ps, timeout=30)
    result: dict[str, dict] = {}
    if not ok or not out:
        return result
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for row in data:
            inst = (row.get("InstanceName") or "").upper()
            code = (row.get("ManufacturerCode") or "").strip().upper()
            prod = (row.get("ProductCode") or "").strip()
            brand = _EDID_MONITOR_MANUFACTURER.get(code, code)
            if not inst:
                continue
            # InstanceName like DISPLAY\LGD1234\5&... — match PnP DeviceID substring
            parts = inst.split("\\")
            key = ""
            if len(parts) >= 2:
                key = f"MONITOR\\{parts[1]}".upper()
            if not key:
                key = inst
            result[key] = {
                "edid_manufacturer_code": code,
                "brand": brand,
                "product_code": prod,
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return result

def _monitor_edid_for_pnp_device(device_id: str, edid_map: dict[str, dict]) -> dict | None:
    if not device_id or not edid_map:
        return None
    dev_upper = device_id.upper()
    for key, info in edid_map.items():
        if key in dev_upper:
            return info
    return None

def resolve_device_display_label(
    name: str,
    pnp_class: str = "",
    manufacturer: str = "",
    *,
    device_id: str = "",
    edid_map: dict[str, dict] | None = None,
    disk_model: str = "",
) -> str:
    """Friendly label when Windows uses a generic PnP name. Delegates to device_enrichment."""
    edid_brand, edid_prod = "", ""
    if edid_map and device_id and (pnp_class or "").lower() == "monitor":
        info = _monitor_edid_for_pnp_device(device_id, edid_map)
        if info:
            edid_brand = (info.get("brand") or "").strip()
            edid_prod = (info.get("product_code") or "").strip()
    vk = de.infer_vendor_key(
        name, pnp_class, manufacturer, device_id,
        edid_brand=edid_brand, disk_model=disk_model,
        known_vendor_fn=_extract_vendor_from_string,
    )
    return de.format_display_label(
        name, pnp_class, manufacturer, device_id,
        edid_brand=edid_brand, edid_product=edid_prod, disk_model=disk_model,
        vendor_key=vk,
    )

def build_hardware_enrichment_bundle(
    pnp_list: list[dict],
    *,
    monitor_edid: dict[str, dict] | None = None,
    disk_rows: list[dict] | None = None,
) -> dict:
    """
    PnP enrichment index + disk WMI fragments for one hardware scan pass.
    Keys: pnp_enrichment (by device name), disk_by_pnp_fragment, disk_rows.
    """
    if disk_rows is None:
        disk_rows = de.get_disk_drives_from_wmi(run_powershell)
    disk_frag = de.disk_models_by_pnp_fragment(disk_rows)
    pnp_index = de.build_pnp_enrichment_index(
        pnp_list,
        monitor_edid=monitor_edid,
        disk_by_pnp_fragment=disk_frag,
        known_vendor_fn=_extract_vendor_from_string,
    )
    return {
        "pnp_enrichment": pnp_index,
        "disk_by_pnp_fragment": disk_frag,
        "disk_rows": disk_rows,
        "monitor_edid": monitor_edid or {},
    }

def enrich_bios_driver_info(
    bios_driver_info: dict | None,
    pnp_index: dict[str, dict],
) -> dict:
    """Add display_name / vendor_key to signed-driver inventory rows."""
    bio = dict(bios_driver_info or {})
    inv = list(bio.get("device_inventory") or [])
    if inv:
        inv = de.enrich_driver_inventory_rows(
            inv, pnp_index, known_vendor_fn=_extract_vendor_from_string, parallel=True
        )
        bio["device_inventory"] = inv
        bio["drivers"] = _common_devices_from_rows(inv)
    all_d = bio.get("all_drivers")
    if all_d:
        bio["all_drivers"] = de.enrich_driver_inventory_rows(
            list(all_d),
            pnp_index,
            known_vendor_fn=_extract_vendor_from_string,
            parallel=True,
        )
    return bio

def _find_pnp_entity_by_device_name(pnp_list: list, device_name: str) -> dict | None:
    """Best-match Win32_PnPEntity row for a display name from our inventory."""
    if not pnp_list or not device_name:
        return None
    target = device_name.strip().lower()
    for row in pnp_list:
        if (row.get("Name") or "").strip().lower() == target:
            return row
    if target == "realtek audio":
        for alias in ("realtek(r) audio", "realtek (r) audio"):
            for row in pnp_list:
                if (row.get("Name") or "").strip().lower() == alias:
                    return row
    for row in pnp_list:
        name = (row.get("Name") or "").strip().lower()
        if target in name:
            suffix = name[len(target):].strip()
            if suffix and not suffix.startswith("("):
                continue
            return row
        if name in target:
            return row
    return None

def _system_manufacturer_oem_url(system_ctx: dict | None) -> str | None:
    """OEM support page from Win32_ComputerSystem manufacturer, if known."""
    mfr = ""
    if system_ctx:
        mfr = (system_ctx.get("system_manufacturer") or "").strip().lower()
    if not mfr:
        return None
    for key, url in _OEM_SUPPORT_URLS.items():
        if key in mfr:
            return url
    return None

def _action_plan_link_tier(opt: dict) -> int:
    """Sort order: 0=device manufacturer, 1=OEM/BIOS, 2=Microsoft, 3=utilities."""
    oid = (opt.get("id") or "").lower()
    if (
        oid.startswith("vendor_")
        or oid.startswith(("amd_chipset", "intel_chipset", "gpu_"))
        or oid in ("whea_component_search", "storage_nvme_search")
    ):
        return 0
    if oid.startswith(("oem", "bios")):
        return 1
    if oid.startswith("wu_"):
        return 2
    return 3

def sort_action_plan_update_options(options: list[dict]) -> list[dict]:
    """Manufacturer → OEM → Microsoft → utilities (stable within each tier)."""
    return sorted(
        enumerate(options),
        key=lambda item: (_action_plan_link_tier(item[1]), item[0]),
    )

def _system_ctx_with_service_tag(
    system_ctx: dict | None,
    bios_driver_info: dict | None,
) -> dict:
    """Ensure Dell/Alienware service-tag driver URLs work right after Run Analysis."""
    ctx = dict(system_ctx or {})
    if _service_tag_from_ctx(ctx):
        return ctx
    bios = (bios_driver_info or {}).get("bios") or {}
    tag = (bios.get("serial_number") or "").strip()
    if _valid_pc_service_tag(tag):
        ctx["service_tag"] = tag
    return ctx

def build_driver_update_options(
    driver: str | None,
    pnp_list: list | None,
    system_ctx: dict | None,
    bios_driver_info: dict | None,
    inventory: list | None,
) -> list[dict]:
    """User-triggered driver update links: device vendor first, then OEM, then Microsoft.

    Does not silently install drivers — each option explains why it is suggested.
    """
    system_ctx = _system_ctx_with_service_tag(system_ctx, bios_driver_info)
    if not driver:
        return []
    drv_base = driver.lower().replace(".sys", "").replace(".dll", "").strip()
    if drv_base in _PLATFORM_CPU_MODULES or drv_base in _KERNEL_SHIM_MODULES:
        return []

    manufacturer: list[dict] = []
    oem_opts: list[dict] = []
    microsoft: list[dict] = []
    utilities: list[dict] = []

    culprit_names = sorted(find_culprit_devices(inventory or [], driver))
    pnp_entity = None
    for name in culprit_names:
        pnp_entity = _find_pnp_entity_by_device_name(pnp_list or [], name)
        if pnp_entity:
            break

    instance_id = (pnp_entity or {}).get("DeviceID") or ""
    device_label = culprit_names[0] if culprit_names else (pnp_entity or {}).get("Name") or driver

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

    if vendor_key == "amd" and hw and hw[1][0] == "chipset":
        manufacturer.append({
            "id": "vendor_amd_chipset",
            "label": "Open AMD chipset driver download",
            "reason": "Chipset/platform drivers from the device manufacturer — usually newer than Windows Optional Updates.",
            "kind": "url",
            "url": _AMD_CHIPSET_DRIVER_URL,
        })
    elif vendor_key and vendor_key in _VENDOR_DRIVER_URLS:
        url, title = _VENDOR_DRIVER_URLS[vendor_key]
        manufacturer.append({
            "id": f"vendor_{vendor_key}",
            "label": title,
            "reason": (
                f"Direct download from the device manufacturer for '{driver}' — "
                "often the newest build for crash-related fixes."
            ),
            "kind": "url",
            "url": url,
        })

    oem_url = _pc_support_drivers_url(system_ctx)
    if oem_url:
        mfr = (system_ctx or {}).get("system_manufacturer") or "your PC maker"
        oem_opts.append({
            "id": "oem",
            "label": f"Open {mfr} support / drivers",
            "reason": "Your PC maker's driver pack for this exact model (after trying the device manufacturer).",
            "kind": "url",
            "url": oem_url,
        })

    if instance_id:
        inst_ps = instance_id.replace("'", "''")
        microsoft.append({
            "id": "wu_driver",
            "label": "Search Windows Update for this driver",
            "reason": (
                f"Microsoft's catalog for {device_label} — often the most WHQL-stable, "
                "but may be older than the manufacturer package."
            ),
            "kind": "powershell",
            "command": (
                f"$id='{inst_ps}'; "
                "try { Update-Driver -InstanceId $id -Online -ErrorAction Stop; 'Driver update initiated via Windows Update.' } "
                "catch { if ($_.Exception.Message -match 'Update-Driver') "
                "{ 'Update-Driver is not available on this system. Use Optional Updates in Settings instead.' } "
                "else { $_.Exception.Message } }"
            ),
        })
    microsoft.append({
        "id": "wu_optional",
        "label": "Open Windows Update (optional updates)",
        "reason": "Optional driver updates from Microsoft — stable, but try the manufacturer link first for the newest driver.",
        "kind": "uri",
        "uri": "ms-settings:windowsupdate-optionalupdates",
    })

    utilities.append({
        "id": "devmgmt",
        "label": "Open Device Manager",
        "reason": "Right-click the device → Update driver → Search automatically or Browse.",
        "kind": "command",
        "command": "devmgmt.msc",
    })

    options = manufacturer + oem_opts + microsoft + utilities
    return [opt for _, opt in sort_action_plan_update_options(options)][:8]

def _crash_report_context(
    events: list,
    windbg_analysis: dict | None,
    whea_events: list | None,
    thermal_events: list | None,
) -> dict:
    """Structured fields from this crash's logs/dump used to pick Action Plan links."""
    crash_times = [e["time"] for e in events if e.get("time")]
    bugchecks = _usable_bugcheck_events(events)
    latest = bugchecks[0] if bugchecks else None
    p1 = None
    p1_int = None
    if latest:
        p1 = latest.get("p1") or (windbg_analysis or {}).get("bugcheck_p1")
        if p1 is not None:
            p1_int = _parse_p1(str(p1))
    whea_component = None
    for we in whea_events or []:
        if we.get("component") and _match_event_to_crash(
            we["time"], crash_times, _WHEA_NEAR_CRASH_WINDOW_MIN
        ):
            whea_component = (we.get("component") or "").strip()
            break
    thermal_near = any(
        _match_event_to_crash(te.get("time", ""), crash_times, _THERMAL_NEAR_CRASH_WINDOW_MIN)
        for te in (thermal_events or [])[:5]
    )
    p1_source_label = ""
    if p1_int is not None and p1_int in WHEA_P1_SOURCE:
        p1_source_label = WHEA_P1_SOURCE[p1_int]
    return {
        "p1_int": p1_int,
        "whea_component": whea_component,
        "thermal_near": thermal_near,
        "p1_source_label": p1_source_label,
        "crash_times": crash_times,
    }

def _is_usable_system_model(model: str) -> bool:
    if not model or len(model.strip()) < 3:
        return False
    low = model.lower().strip()
    junk = (
        "to be filled", "default string", "system product", "not available",
        "oem", "undefined", "all series", "desktop", "laptop",
    )
    return not any(j in low for j in junk)

def _is_placeholder_service_tag(tag: str) -> bool:
    t = (tag or "").strip().upper()
    if not t or len(t) < 5:
        return True
    if t in (
        "NONE",
        "DEFAULT",
        "NOT AVAILABLE",
        "NOT SPECIFIED",
        "UNKNOWN",
        "SYSTEM SERIAL NUMBER",
        "SYSTEM SERIAL",
        "DEFAULT STRING",
        "TO BE FILLED BY O.E.M.",
        "TO BE FILLED BY OEM",
        "TO BE FILLED",
        "O.E.M.",
        "OEM",
        "123456789",
        "0123456789",
        "XXXXXXXX",
    ):
        return True
    junk_fragments = (
        "TO BE FILLED",
        "DEFAULT STRING",
        "SYSTEM SERIAL",
        "NOT AVAILABLE",
        "NOT SPECIFIED",
    )
    return any(frag in t for frag in junk_fragments)


def _valid_pc_service_tag(tag: str) -> bool:
    return not _is_placeholder_service_tag(tag)

def _service_tag_from_ctx(ctx: dict) -> str:
    tag = (ctx.get("service_tag") or "").strip()
    return tag if _valid_pc_service_tag(tag) else ""

def _pc_support_drivers_url(system_ctx: dict | None) -> str | None:
    """Direct PC-maker driver download page (service tag / model), not a web search."""
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").strip().lower()
    tag = _service_tag_from_ctx(ctx)
    if "dell" in mfr or "alienware" in mfr:
        if tag:
            return (
                "https://www.dell.com/support/home/en-us/product-support/"
                f"servicetag/{urllib.parse.quote(tag)}/drivers"
            )
        return _VENDOR_DRIVER_URLS["dell"][0]
    if any(x in mfr for x in ("lenovo", "thinkpad", "ideapad")):
        mtm = re.sub(
            r"[^A-Z0-9]",
            "",
            (
                (ctx.get("machine_type") or ctx.get("baseboard_product") or "")
            ).upper(),
        )
        if len(mtm) >= 10:
            return f"https://pcsupport.lenovo.com/us/en/products/{mtm[:10]}/downloads"
        if len(mtm) >= 7:
            return f"https://pcsupport.lenovo.com/us/en/products/{mtm[:7]}/downloads"
        if tag:
            return f"https://pcsupport.lenovo.com/us/en/solutions/serial/{urllib.parse.quote(tag)}"
        return _VENDOR_DRIVER_URLS["lenovo"][0]
    if "hp" in mfr or "hewlett" in mfr:
        if tag:
            return (
                "https://support.hp.com/us-en/product?"
                f"serialNumber={urllib.parse.quote(tag)}"
            )
        return _VENDOR_DRIVER_URLS["hp"][0]
    if "asus" in mfr:
        board = (ctx.get("baseboard_product") or "").strip()
        if board and _is_usable_system_model(board):
            return (
                "https://www.asus.com/support/download-center/?keyword="
                + urllib.parse.quote(board)
            )
        model = (ctx.get("system_model") or "").strip()
        if _is_usable_system_model(model):
            return (
                "https://www.asus.com/support/download-center/?keyword="
                + urllib.parse.quote(model)
            )
        return _VENDOR_DRIVER_URLS["asus"][0]
    url = _system_manufacturer_oem_url(ctx)
    if url:
        return url
    return None

def _oem_model_support_url(system_ctx: dict | None) -> str | None:
    """Model-specific OEM driver page when WMI reports manufacturer (and often service tag)."""
    return _pc_support_drivers_url(system_ctx)

def _pc_support_bios_url(system_ctx: dict | None) -> str:
    """BIOS/UEFI updates on the PC maker site (same portal as drivers when possible)."""
    url = _pc_support_drivers_url(system_ctx)
    if url:
        return url
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "PC manufacturer").strip()
    generic = _system_manufacturer_oem_url(ctx)
    if generic:
        return generic
    return _VENDOR_DRIVER_URLS.get("dell", (_AMD_CHIPSET_DRIVER_URL,))[0]

def _bios_support_search_url(system_ctx: dict | None) -> str:
    return _pc_support_bios_url(system_ctx)

def _installed_bios_summary(bios_driver_info: dict | None) -> str:
    bios = (bios_driver_info or {}).get("bios") or {}
    ver = (bios.get("version") or "").strip()
    if not ver:
        return ""
    date = _parse_json_date(bios.get("date", ""))
    return f"Installed BIOS on this PC: {ver}" + (f" ({date})" if date else "") + "."

def get_culprit_device_driver_info(driver: str | None, inventory: list | None) -> list[dict]:
    """Installed signed-driver rows on this PC for devices tied to the faulting module.

    Data comes from Win32_PnPSignedDriver (same source as the System tab) — not from vendor
    download pages. We do not fetch latest-available versions from the internet.
    """
    if not driver:
        return []
    names = sorted(find_culprit_devices(inventory or [], driver))
    rows = []
    for name in names:
        d = lookup_inventory_row(inventory, name)
        if d:
            rows.append({
                "name": (d.get("name") or name).strip(),
                "version": (d.get("version") or "").strip() or "?",
                "date": _parse_json_date(d.get("date", "")),
                "device_class": (d.get("device_class") or "").strip(),
            })
    if not rows:
        rows.append({
            "name": f"Device for module {driver}",
            "version": "(not matched in driver inventory — use update links below)",
            "date": "",
            "device_class": "",
        })
    return rows

def run_driver_update_option(option: dict) -> tuple[bool, str]:
    """Run a user-selected driver update path from build_driver_update_options()."""
    kind = option.get("kind")
    label = option.get("label", "Update")
    try:
        if kind == "url":
            import webbrowser
            webbrowser.open(option["url"])
            return True, f"Opened {label} in your browser."
        if kind == "uri":
            if sys.platform == "win32":
                os.startfile(option["uri"])  # type: ignore[attr-defined]
                return True, f"Opened {label}."
            return False, "Settings links are only supported on Windows."
        if kind == "command":
            if sys.platform == "win32":
                subprocess.Popen(
                    ["cmd", "/c", "start", "", option["command"]],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return True, f"Opened {label}."
            return False, "This action is only supported on Windows."
        if kind == "powershell":
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", option["command"]],
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if proc.returncode == 0 and out:
                return True, out[:500]
            if proc.returncode == 0:
                return True, f"{label} completed."
            return False, out[:500] or f"{label} failed (exit {proc.returncode})."
    except subprocess.TimeoutExpired:
        return False, f"{label} timed out — try Windows Update in Settings instead."
    except OSError as e:
        return False, str(e)
    return False, "Unknown update action."

def get_faulting_device_explanation(faulting_driver: str | None, code_val: int | None,
                                    p1_str: str | None, whea_component: str | None) -> str:
    """
    Return a clear device/driver explanation for any faulting module.
    Handles vendor IDs, kernel components, known drivers, and provides fallback for unmapped drivers.
    """
    parts = []
    drv_lower = (faulting_driver or "").strip().lower()
    drv_base = drv_lower.replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()

    # WHEA 0x124: use Parameter 1 for hardware source (most precise)
    if code_val == 0x124 and p1_str is not None:
        p1 = _parse_p1(str(p1_str))
        if p1 is not None and p1 in WHEA_P1_SOURCE:
            parts.append(f"Hardware source: {WHEA_P1_SOURCE[p1]}")
        if whea_component:
            parts.append(f"WHEA component: {whea_component}")

    # Check explicit mapping first
    if drv_base:
        for key, (device, action) in GENERIC_FAULT_MODULE_DEVICE.items():
            if key in drv_base or drv_base == key:
                parts.append(f"Module '{faulting_driver}' = {device}")
                parts.append(f"Action: {action}")
                # Add possible specific drivers when it's a broad category (vendor ID, framework, kernel)
                if key in POSSIBLE_DRIVERS:
                    p1 = _parse_p1(str(p1_str)) if p1_str is not None else None
                    cpu_list, pcie_list, fallback_list = POSSIBLE_DRIVERS[key]
                    if code_val == 0x124 and p1 == 0x4 and pcie_list:
                        parts.append("Possible specific drivers: " + "; ".join(pcie_list))
                    elif code_val == 0x124 and p1 in (0x0, 0x1, None) and cpu_list:
                        parts.append("Possible specific drivers: " + "; ".join(cpu_list))
                    elif fallback_list:
                        parts.append("Possible specific drivers: " + "; ".join(fallback_list))
                return "\n  ".join(parts) if parts else (faulting_driver or "")

    # Fallback for unmapped drivers: infer vendor and provide generic guidance
    if faulting_driver:
        vendor = _infer_driver_vendor(drv_base)
        if vendor:
            parts.append(f"Driver '{faulting_driver}' = {vendor} device/driver")
        else:
            parts.append(f"Driver '{faulting_driver}' = Third-party kernel driver")
        parts.append("Action: Update or rollback from device manufacturer; identify vendor from filename.")
        return "\n  ".join(parts)

    return "\n  ".join(parts) if parts else ""

def get_bugcheck_info(code: int) -> tuple:
    """Return (name, description) for a bugcheck code."""
    code_normalized = code & 0xFFFFFFFF
    if code_normalized in BUGCHECK_CODES:
        return BUGCHECK_CODES[code_normalized]
    return (f"0x{code:08X}", "Unknown stop code - analyze minidump with WinDbg for details.")


def newest_minidump_analysis(
    analyses: list[dict], dumps_in_order: list[dict]
) -> dict | None:
    """Pick analysis for the newest dump (first entry in dumps_in_order)."""
    if not analyses:
        return None
    by_dump: dict[str, dict] = {}
    for a in analyses:
        key = (a.get("dump_file") or "").strip().lower()
        if key and key not in by_dump:
            by_dump[key] = a
    for d in dumps_in_order:
        name = (d.get("name") or "").strip().lower()
        if name and name in by_dump:
            return dict(by_dump[name])
    for d in dumps_in_order:
        name = (d.get("name") or "").strip().lower()
        if not name:
            continue
        for a in analyses:
            if (a.get("dump_file") or "").strip().lower() == name:
                return dict(a)
    return None

def analyze_recent_minidumps(kernel_dumps: list, cdb_path: str | None, max_dumps: int = 3,
                             progress_cb=None) -> dict | None:
    """Analyze up to max_dumps recent minidumps; merge results and detect recurring faulting driver.

    progress_cb(completed, total): optional callback after each dump finishes (not at start).
    """
    if not kernel_dumps or not cdb_path:
        return None
    analyses = []
    dumps_to_analyze = kernel_dumps[:max_dumps]
    total = len(dumps_to_analyze)

    def _analyze_one(dump_info: dict) -> dict | None:
        return analyze_minidump_with_cdb(dump_info["path"], cdb_path)

    # Run CDB on multiple dumps in parallel to reduce wall-clock time.
    completed = 0
    with ThreadPoolExecutor(max_workers=min(3, total)) as executor:
        future_map = {
            executor.submit(_analyze_one, d): d for d in dumps_to_analyze
        }
        for fut in as_completed(future_map):
            d = future_map[fut]
            try:
                a = fut.result()
            except Exception:
                a = None
            completed += 1
            if progress_cb:
                try:
                    progress_cb(completed, total)
                except Exception:
                    pass  # user progress callback; must not abort minidump analysis

            if a:
                a["dump_file"] = d.get("name", "")
                a["dump_time"] = d.get("time", "")
                analyses.append(a)
    if not analyses:
        return None
    latest = newest_minidump_analysis(analyses, dumps_to_analyze)
    if not latest:
        return None
    newest_name = (dumps_to_analyze[0].get("name") or "").strip() if dumps_to_analyze else ""
    source_name = (latest.get("dump_file") or "").strip()
    if newest_name and source_name:
        latest["analysis_source_dump"] = source_name
        latest["newest_dump_mismatch"] = (
            newest_name.lower() != source_name.lower()
        )
    driver_counts: dict[str, int] = {}
    for a in analyses:
        drv = a.get("faulting_driver")
        if drv:
            key = drv.lower()
            driver_counts[key] = driver_counts.get(key, 0) + 1
    recurring = None
    recurring_count = 0
    if driver_counts:
        best_key, recurring_count = max(driver_counts.items(), key=lambda x: x[1])
        if recurring_count >= 2:
            for a in analyses:
                fd = a.get("faulting_driver") or ""
                if fd.lower().replace(".sys", "") == best_key.replace(".sys", ""):
                    recurring = fd
                    break
            if not recurring:
                recurring = best_key if best_key.endswith((".sys", ".dll")) else best_key + ".sys"
    latest["dumps_analyzed"] = len(analyses)
    latest["dumps_failed"] = max(0, total - len(analyses))
    latest["recurring_faulting_driver"] = recurring
    latest["recurring_count"] = recurring_count
    latest["all_analyses"] = analyses
    return latest

def merge_verification_action_steps(
    driver_verification: dict | None,
    recommendations: list[str],
    *,
    faulting_driver: str | None = None,
) -> list[str]:
    """Prepend crash-linked verification steps to the Action Plan list."""
    steps: list[str] = []
    try:
        import driver_verification as drvver

        steps = drvver.verification_action_plan_steps(driver_verification)
    except Exception:
        steps = list((driver_verification or {}).get("action_plan_steps") or [])
    if not steps:
        return sanitize_action_plan_steps(list(recommendations or []), faulting_driver)
    seen: set[str] = set()
    merged: list[str] = []
    for step in steps + list(recommendations or []):
        key = step.strip().lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(step)
    return sanitize_action_plan_steps(merged, faulting_driver)


def sanitize_action_plan_steps(
    steps: list[str],
    faulting_driver: str | None = None,
) -> list[str]:
    """Drop misleading kernel-driver update rows and near-duplicate steps."""
    from crash_report_culprit import is_kernel_shim_fault_module

    driver = faulting_driver
    if not driver:
        for step in steps:
            if "roll back ntoskrnl" in step.lower():
                driver = "ntoskrnl.exe"
                break
    kernel_shim = is_kernel_shim_fault_module(driver)
    out: list[str] = []
    seen: set[str] = set()
    for step in steps:
        text = (step or "").strip()
        if not text:
            continue
        low = text.lower()
        if kernel_shim and (
            "update or roll back ntoskrnl" in low
            or (low.startswith("update or roll back") and "ntoskrnl" in low)
            or low.startswith("driver fault: ntoskrnl")
        ):
            continue
        if kernel_shim and "kernel stack fault" in low and any(
            "kernel stack fault" in s.lower() for s in out
        ):
            continue
        key = low
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out

def _detected_cpu_platform_label(system_ctx: dict | None) -> str:
    ctx = system_ctx or {}
    if ctx.get("has_amd_chipset") or ctx.get("cpu_vendor") == "amd":
        return "AMD CPU / chipset platform"
    if ctx.get("has_intel_chipset") or ctx.get("cpu_vendor") == "intel":
        return "Intel CPU / chipset platform"
    return "CPU / chipset platform"

