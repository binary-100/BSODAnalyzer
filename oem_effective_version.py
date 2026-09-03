"""OEM offer effective version — per-device inner version from bundled packages.

Dell/Alienware DUP XML exposes inner ``version`` per PCI ID under
``SupportedDCHDevices`` / ``SupportedDevices``. Other OEM JSON APIs may expose
similar nested structures; this module normalizes them into one compare slot.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

_PCI_PAIR_RE = re.compile(
    r"VEN[_&]([0-9A-F]{4}).*?DEV[_&]([0-9A-F]{4})",
    re.I,
)
_SUBSYS_RE = re.compile(r"SUBSYS[_&]([0-9A-F]{8})", re.I)

_INNER_CONTAINER_KEYS = (
    "supporteddchdevices",
    "supporteddevices",
    "supporteddevicelist",
    "devicessupported",
    "components",
    "componentlist",
    "drivercomponents",
    "devices",
)

_PCI_INFO_KEYS = (
    "pciinfo",
    "pci_info",
    "pci",
    "pcidevices",
    "hardwareids",
    "hardwareid",
    "hwids",
)


def pci_ids_from_ctx(ctx: dict | None) -> tuple[str, str, str, str]:
    """Return (vendor_id, device_id, sub_vendor_id, sub_device_id) from device context."""
    if not ctx:
        return "", "", "", ""
    tokens = [str(t).upper() for t in (ctx.get("pci_tokens") or [])]
    ven = next((t[4:] for t in tokens if t.startswith("VEN_")), "")
    dev = next((t[4:] for t in tokens if t.startswith("DEV_")), "")
    sub = next((t[7:] for t in tokens if t.startswith("SUBSYS_")), "")
    subv = sub[:4] if len(sub) >= 4 else ""
    subd = sub[4:8] if len(sub) >= 8 else ""
    if not ven or not dev:
        inst = (ctx.get("instance_id") or "").upper()
        m = _PCI_PAIR_RE.search(inst)
        if m:
            ven = ven or m.group(1).upper()
            dev = dev or m.group(2).upper()
        sm = _SUBSYS_RE.search(inst)
        if sm and len(sm.group(1)) >= 8:
            subv = subv or sm.group(1)[:4].upper()
            subd = subd or sm.group(1)[4:8].upper()
    return ven, dev, subv, subd


def _norm_pci_field(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("0X"):
        text = text[2:]
    return text


def pci_entry_matches_ctx(pci_entry: dict, ctx: dict | None) -> bool:
    """True when an inner PCI record targets this device."""
    ven, dev, subv, subd = pci_ids_from_ctx(ctx)
    if not ven or not dev:
        return False
    e_ven = _norm_pci_field(pci_entry.get("vendor_id") or pci_entry.get("vendorID"))
    e_dev = _norm_pci_field(pci_entry.get("device_id") or pci_entry.get("deviceID"))
    if e_ven and e_ven != ven:
        return False
    if e_dev and e_dev != dev:
        return False
    e_subv = _norm_pci_field(
        pci_entry.get("sub_vendor_id") or pci_entry.get("subVendorID")
    )
    e_subd = _norm_pci_field(
        pci_entry.get("sub_device_id") or pci_entry.get("subDeviceID")
    )
    if e_subv and subv and e_subv != subv:
        return False
    if e_subd and subd and e_subd != subd:
        return False
    prefix = (pci_entry.get("instance_id_prefix") or "").upper()
    if prefix:
        inst = (ctx.get("instance_id") or "").upper()
        if inst and not inst.startswith(prefix.replace("\\\\", "\\")):
            return False
    return True


def _pci_entries_from_value(value: Any) -> list[dict]:
    entries: list[dict] = []
    if isinstance(value, str):
        m = _PCI_PAIR_RE.search(value.upper())
        if m:
            entries.append({"vendor_id": m.group(1), "device_id": m.group(2)})
        return entries
    if isinstance(value, dict):
        if any(k in value for k in ("vendor_id", "vendorID", "device_id", "deviceID")):
            entries.append(
                {
                    "vendor_id": value.get("vendor_id") or value.get("vendorID") or "",
                    "device_id": value.get("device_id") or value.get("deviceID") or "",
                    "sub_vendor_id": value.get("sub_vendor_id")
                    or value.get("subVendorID")
                    or "",
                    "sub_device_id": value.get("sub_device_id")
                    or value.get("subDeviceID")
                    or "",
                }
            )
        return entries
    if isinstance(value, list):
        for item in value:
            entries.extend(_pci_entries_from_value(item))
    return entries


def _inner_record(version: str, pci_list: list[dict]) -> dict | None:
    ver = (version or "").strip()
    if not ver or not pci_list:
        return None
    return {"version": ver, "pci": pci_list}


def parse_dell_dup_component_inner_versions(
    comp: ET.Element,
    *,
    ns: str = "{openmanage/cm/dm}",
) -> list[dict]:
    """Extract per-PCI inner versions from one DUP SoftwareComponent element."""
    out: list[dict] = []
    for container_tag in ("SupportedDCHDevices", "SupportedDevices"):
        container = comp.find(f"{ns}{container_tag}")
        if container is None:
            continue
        for dev in container.findall(f"{ns}Device"):
            ver = (dev.get("version") or "").strip()
            if not ver:
                continue
            pci_list: list[dict] = []
            for pci in dev.findall(f"{ns}PCIInfo"):
                pci_list.append(
                    {
                        "vendor_id": pci.get("vendorID") or "",
                        "device_id": pci.get("deviceID") or "",
                        "sub_vendor_id": pci.get("subVendorID") or "",
                        "sub_device_id": pci.get("subDeviceID") or "",
                    }
                )
            rec = _inner_record(ver, pci_list)
            if rec:
                out.append(rec)
    return out


def _extract_inner_from_mapping(node: dict) -> list[dict]:
    """Best-effort nested JSON inner versions (Lenovo/HP/ASUS when metadata exists)."""
    out: list[dict] = []

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)
            return
        if not isinstance(obj, dict):
            return

        ver = (
            obj.get("version")
            or obj.get("Version")
            or obj.get("driverVersion")
            or obj.get("DriverVersion")
            or obj.get("componentVersion")
            or obj.get("ComponentVersion")
            or ""
        )
        ver = str(ver).strip()
        key_l = {str(k).lower(): k for k in obj.keys()}
        pci_list: list[dict] = []
        for tag in _PCI_INFO_KEYS:
            if tag in key_l:
                pci_list.extend(_pci_entries_from_value(obj[key_l[tag]]))
        if ver and pci_list:
            rec = _inner_record(ver, pci_list)
            if rec:
                out.append(rec)

        for tag in _INNER_CONTAINER_KEYS:
            if tag in key_l:
                walk(obj[key_l[tag]], depth + 1)

        for val in obj.values():
            if isinstance(val, (dict, list)):
                walk(val, depth + 1)

    walk(node)
    return _dedupe_inner_versions(out)


def _dedupe_inner_versions(items: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for item in items:
        ver = (item.get("version") or "").strip()
        pci_key = tuple(
            sorted(
                (
                    _norm_pci_field(p.get("vendor_id")),
                    _norm_pci_field(p.get("device_id")),
                    _norm_pci_field(p.get("sub_vendor_id")),
                    _norm_pci_field(p.get("sub_device_id")),
                )
                for p in (item.get("pci") or [])
            )
        )
        key = (ver, pci_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_oem_inner_versions_from_item(item: dict) -> list[dict]:
    """Normalize inner PCI versions from one OEM API object (any vendor)."""
    if not isinstance(item, dict):
        return []
    if item.get("inner_versions"):
        existing = item.get("inner_versions")
        if isinstance(existing, list):
            return _dedupe_inner_versions(existing)
    return _extract_inner_from_mapping(item)


def pick_inner_version_for_ctx(
    inner_versions: list[dict] | None,
    ctx: dict | None,
) -> tuple[str, str]:
    """Return (version, match_detail) for the best PCI/ACPI match, or ('', '')."""
    if not inner_versions or not ctx:
        return "", ""

    inst = (ctx.get("instance_id") or "").strip().upper()
    if inst:
        best_ver = ""
        best_detail = ""
        best_score = -1
        for entry in inner_versions:
            ver = (entry.get("version") or "").strip()
            if not ver:
                continue
            pci_list = entry.get("pci") or []
            if not isinstance(pci_list, list):
                continue
            for pci in pci_list:
                if not isinstance(pci, dict):
                    continue
                prefix = (pci.get("instance_id_prefix") or "").upper()
                if prefix and inst.startswith(prefix.replace("\\\\", "\\")):
                    score = 4
                    detail = f"{inst} → inner {ver} (ACPI/instance prefix match)"
                    if score > best_score:
                        best_score = score
                        best_ver = ver
                        best_detail = detail
                if pci_entry_matches_ctx(pci, ctx):
                    score = 3
                    detail = f"inner {ver} (PCI/HWID match in bundle metadata)"
                    if score > best_score:
                        best_score = score
                        best_ver = ver
                        best_detail = detail
        if best_ver:
            return best_ver, best_detail

    ven, dev, _, _ = pci_ids_from_ctx(ctx)
    if not ven or not dev:
        return "", ""

    best_ver = ""
    best_detail = ""
    best_score = -1
    for entry in inner_versions:
        ver = (entry.get("version") or "").strip()
        if not ver:
            continue
        pci_list = entry.get("pci") or []
        if not isinstance(pci_list, list):
            continue
        for pci in pci_list:
            if not isinstance(pci, dict):
                continue
            if not pci_entry_matches_ctx(pci, ctx):
                continue
            score = 2
            if _norm_pci_field(pci.get("sub_vendor_id")):
                score += 1
            if _norm_pci_field(pci.get("sub_device_id")):
                score += 1
            detail = (
                f"PCI {ven}:{dev} → inner {ver}"
                f" (bundle wrapper may differ)"
            )
            if score > best_score:
                best_score = score
                best_ver = ver
                best_detail = detail
    return best_ver, best_detail


def resolve_offer_effective_version(
    offer: dict,
    ctx: dict | None,
) -> tuple[str, str, str]:
    """
    Resolve compare version for this device.

    Returns (effective_version, method, note). Empty effective_version when
    no inner match — caller falls back to wrapper/catalog version.
    """
    if not offer or not ctx:
        return "", "", ""

    inner = offer.get("inner_versions") or offer.get("offer_inner_versions")
    if isinstance(inner, list) and inner:
        ver, detail = pick_inner_version_for_ctx(inner, ctx)
        if ver:
            oem = (offer.get("source_label") or offer.get("source") or "OEM").strip()
            return ver, "oem_inner_pci_version", f"{oem}: {detail}"
    return "", "", ""
