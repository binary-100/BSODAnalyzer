"""Discover devices on this PC that may have firmware updates (inventory only — no update checks)."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import device_enrichment as de
from bsod_hardware_wmi import get_bios_and_driver_versions, get_hardware_profile_wmi_bundle, get_ssd_firmware_inventory

# Vendors that commonly ship firmware via a desktop app (not Windows Update alone).
_PERIPHERAL_FW_VENDORS = frozenset({
    "razer", "logitech", "corsair", "steelseries", "keychron", "elgato",
    "hyperx", "asus", "msi", "dell", "alienware", "hp", "lenovo", "apple",
    "microsoft", "tplink", "netgear", "samsung", "wd", "sandisk", "crucial",
    "kingston", "royal kludge", "a4tech", "sony",
})

# Typical updater path notes (inventory — not a version check).
_UTILITY_HINTS: dict[str, str] = {
    "razer": "Razer Support articles (mysupport.razer.com) — Synapse optional",
    "logitech": "Logitech G HUB / Options+",
    "corsair": "CORSAIR iCUE",
    "steelseries": "SteelSeries GG",
    "samsung": "Samsung Magician",
    "wd": "WD Dashboard",
    "sandisk": "SanDisk Dashboard",
    "crucial": "Crucial Storage Executive",
    "kingston": "Kingston SSD Manager",
    "nvidia": "NVIDIA driver package (includes VBIOS)",
    "amd": "AMD driver package",
    "intel": "Intel driver / DSA",
    "realtek": "Realtek driver or OEM package",
    "mediatek": "OEM Wi‑Fi/BT driver package",
    "qualcomm": "OEM Killer/Qualcomm driver package",
    "broadcom": "OEM driver package",
    "tplink": "TP-Link utility",
    "netgear": "NETGEAR utility",
    "elgato": "Elgato software",
    "keychron": "Keychron/QMK tooling",
}

_USB_VID_PID_RE = re.compile(
    r"VID[_&]([0-9A-F]{4}).*?PID[_&]([0-9A-F]{4})", re.I
)
_FIRMWARE_NAME_RE = re.compile(r"\bfirmware\b", re.I)


def _usb_vid_pid(device_id: str) -> tuple[str, str]:
    m = _USB_VID_PID_RE.search(device_id or "")
    if not m:
        return "", ""
    return m.group(1).upper(), m.group(2).upper()


def _infer_vendor(name: str, pnp_class: str, device_id: str) -> str:
    vk = de.infer_vendor_key(name, pnp_class, device_id) or ""
    return vk.strip().lower()


def _driver_version_for(name: str, driver_rows: list[dict]) -> str:
    name_l = (name or "").lower()
    for row in driver_rows:
        if (row.get("name") or "").lower() == name_l:
            return (row.get("version") or "").strip()
    return ""


def _tier_for(category: str) -> str:
    if category in ("bios", "ssd"):
        return "primary"
    if category in ("windows_firmware", "usb_peripheral"):
        return "secondary"
    return "informational"


def _category_entity(
    ent: dict,
    *,
    category: str,
    subcategory: str = "",
    installed: str = "",
    notes: str = "",
) -> dict:
    name = (ent.get("Name") or ent.get("name") or "Unknown").strip()
    pnp = (ent.get("PNPClass") or ent.get("device_class") or "").strip()
    device_id = (ent.get("DeviceID") or ent.get("instance_id") or "").strip()
    vendor = _infer_vendor(name, pnp, device_id)
    return {
        "category": category,
        "subcategory": subcategory,
        "tier": _tier_for(category),
        "name": name,
        "pnp_class": pnp,
        "vendor_key": vendor,
        "device_id": device_id[:120],
        "installed_version": installed,
        "utility_hint": _UTILITY_HINTS.get(vendor, ""),
        "notes": notes,
    }


def discover_firmware_capable_devices() -> dict:
    prof = get_hardware_profile_wmi_bundle() or {}
    pnp_list = list(prof.get("pnp_list") or [])
    drv_info = get_bios_and_driver_versions(include_all=True)
    driver_rows = list(drv_info.get("all_drivers") or drv_info.get("device_inventory") or [])
    bios = (prof.get("bios_driver_info") or {}).get("bios") or drv_info.get("bios") or {}
    ssd_drives = get_ssd_firmware_inventory()

    candidates: list[dict] = []

    # Primary: BIOS
    candidates.append({
        "category": "bios",
        "subcategory": "motherboard",
        "tier": "primary",
        "name": f"Motherboard BIOS ({bios.get('manufacturer') or 'System'})",
        "pnp_class": "BIOS",
        "vendor_key": _infer_vendor(
            prof.get("system_manufacturer") or "", "system", ""
        ),
        "device_id": "",
        "installed_version": (bios.get("version") or "?").strip(),
        "utility_hint": "OEM support site / Dell Update / Alienware Update",
        "notes": "Already on Firmware tab.",
    })

    # Primary: SSDs
    for drive in ssd_drives:
        model = (drive.get("model") or "SSD").strip()
        candidates.append({
            "category": "ssd",
            "subcategory": "storage",
            "tier": "primary",
            "name": model,
            "pnp_class": "DiskDrive",
            "vendor_key": (drive.get("vendor_key") or "").strip().lower(),
            "device_id": (drive.get("serial_number") or "")[:40],
            "installed_version": (drive.get("firmware_revision") or "?").strip(),
            "utility_hint": _UTILITY_HINTS.get(
                (drive.get("vendor_key") or "").lower(), "Drive manufacturer utility"
            ),
            "notes": "Already on Firmware tab.",
        })

    seen_usb: set[tuple[str, str]] = set()
    seen_firmware_class: set[str] = set()
    seen_pcie_gpu_nic: set[str] = set()

    for ent in pnp_list:
        if not isinstance(ent, dict):
            continue
        name = (ent.get("Name") or "").strip()
        if not name:
            continue
        pnp = (ent.get("PNPClass") or "").strip()
        pnp_l = pnp.lower()
        device_id = (ent.get("DeviceID") or "").strip()
        name_l = name.lower()
        vendor = _infer_vendor(name, pnp, device_id)
        drv_ver = _driver_version_for(name, driver_rows)

        # Windows FIRMWARE class / explicit device firmware nodes
        if pnp_l == "firmware" or name_l == "device firmware" or _FIRMWARE_NAME_RE.search(name):
            key = name_l[:80]
            if key in seen_firmware_class:
                continue
            seen_firmware_class.add(key)
            candidates.append(
                _category_entity(
                    ent,
                    category="windows_firmware",
                    subcategory="pnp_firmware_class",
                    installed=drv_ver or "?",
                    notes="Excluded from Drivers tab; candidate for Firmware tab secondary tier.",
                )
            )
            continue

        # USB peripherals with vendors that commonly ship firmware tools
        vid, pid = _usb_vid_pid(device_id)
        if vid and pid:
            usb_key = (vid, pid)
            if usb_key in seen_usb:
                continue
            is_peripheral_class = pnp_l in (
                "keyboard", "mouse", "hidclass", "media", "camera"
            )
            known_vendor = vendor in _PERIPHERAL_FW_VENDORS
            if is_peripheral_class and (known_vendor or pnp_l in ("keyboard", "mouse")):
                seen_usb.add(usb_key)
                sub = pnp_l or "usb"
                note = (
                    "USB peripheral — check vendor support articles for standalone firmware "
                    "updaters (not always offered in desktop apps)."
                )
                if not known_vendor:
                    note += " Vendor utility unknown — verify manually."
                candidates.append(
                    _category_entity(
                        ent,
                        category="usb_peripheral",
                        subcategory=sub,
                        installed=drv_ver or "—",
                        notes=note,
                    )
                )
                continue

        # GPU / NIC / Bluetooth — firmware usually bundled with driver packages
        if pnp_l in ("display", "net", "bluetooth"):
            sig = f"{pnp_l}:{name_l[:60]}"
            if sig in seen_pcie_gpu_nic:
                continue
            if any(
                k in name_l
                for k in (
                    "nvidia", "geforce", "radeon", "intel", "realtek",
                    "killer", "qualcomm", "mediatek", "broadcom", "marvell",
                    "bluetooth", "wireless", "wi-fi", "wifi", "ethernet",
                )
            ):
                seen_pcie_gpu_nic.add(sig)
                cat = {"display": "gpu", "net": "network", "bluetooth": "bluetooth"}.get(
                    pnp_l, pnp_l
                )
                candidates.append(
                    _category_entity(
                        ent,
                        category="driver_bundled_firmware",
                        subcategory=cat,
                        installed=drv_ver or "?",
                        notes="Firmware/VBIOS often ships with the driver package — not separate MCU firmware.",
                    )
                )

    # Count by tier/category
    by_tier: dict[str, int] = defaultdict(int)
    by_category: dict[str, int] = defaultdict(int)
    for c in candidates:
        by_tier[c["tier"]] += 1
        by_category[c["category"]] += 1

    return {
        "system": {
            "manufacturer": prof.get("system_manufacturer") or "",
            "model": prof.get("system_model") or "",
        },
        "summary": {
            "total_candidates": len(candidates),
            "by_tier": dict(by_tier),
            "by_category": dict(by_category),
        },
        "candidates": candidates,
    }


def _print_report(data: dict) -> None:
    sys_info = data.get("system") or {}
    summary = data.get("summary") or {}
    print("=" * 70)
    print("BSOD Analyzer — firmware-capable device discovery (inventory only)")
    print("=" * 70)
    print(f"PC: {sys_info.get('manufacturer')} {sys_info.get('model')}")
    print(f"Total candidates: {summary.get('total_candidates', 0)}")
    print()
    print("By tier:")
    for tier, count in sorted((summary.get("by_tier") or {}).items()):
        print(f"  {tier}: {count}")
    print()
    print("By category:")
    for cat, count in sorted((summary.get("by_category") or {}).items()):
        print(f"  {cat}: {count}")
    print()

    order = ("primary", "secondary", "informational")
    tier_labels = {
        "primary": "PRIMARY (BIOS / SSD — Firmware tab today)",
        "secondary": "SECONDARY (good next targets for Firmware tab)",
        "informational": "INFORMATIONAL (driver-bundled / lower priority)",
    }
    by_tier_rows: dict[str, list[dict]] = defaultdict(list)
    for c in data.get("candidates") or []:
        by_tier_rows[c.get("tier") or "informational"].append(c)

    for tier in order:
        rows = by_tier_rows.get(tier) or []
        if not rows:
            continue
        print("-" * 70)
        print(tier_labels.get(tier, tier.upper()))
        print("-" * 70)
        for i, c in enumerate(rows, 1):
            print(f"{i}. [{c.get('category')}] {c.get('name')}")
            print(f"   Class: {c.get('pnp_class') or '—'}  Vendor: {c.get('vendor_key') or '—'}")
            print(f"   Installed: {c.get('installed_version') or '—'}")
            if c.get("utility_hint"):
                print(f"   Typical updater: {c.get('utility_hint')}")
            if c.get("notes"):
                print(f"   Note: {c.get('notes')}")
            print()


def main() -> int:
    data = discover_firmware_capable_devices()
    _print_report(data)
    out = ROOT / "live_firmware_device_discovery.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Full JSON: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
