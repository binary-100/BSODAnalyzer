"""Discover secondary-tier firmware devices (USB peripherals, Windows FIRMWARE class)."""

from __future__ import annotations

import re
from typing import Any

import device_enrichment as de
import firmware_peripheral_installed as fpinst
import firmware_peripheral_vendors as fpv

_USB_VID_PID_RE = re.compile(r"VID[_&]([0-9A-F]{4}).*?PID[_&]([0-9A-F]{4})", re.I)
_FIRMWARE_NAME_RE = re.compile(r"\bfirmware\b", re.I)

_PERIPHERAL_FW_VENDORS = frozenset({
    "razer", "logitech", "corsair", "steelseries", "keychron", "elgato",
    "hyperx", "asus", "msi", "dell", "alienware", "hp", "lenovo", "apple",
    "microsoft", "tplink", "netgear", "samsung", "wd", "sandisk", "crucial",
    "kingston", "royal kludge", "a4tech", "sony",
})

_GENERIC_HID_NAMES = frozenset({
    "hid keyboard device",
    "hid-compliant mouse",
    "usb input device",
    "hid-compliant consumer control device",
    "hid-compliant system controller",
    "hid-compliant vendor-defined device",
    "usb composite device",
})

_USELESS_INSTALLED = frozenset({"", "—", "-", "?", "0", "not reported"})
_LOGITECH_USB_ALIASES: tuple[tuple[str, str], ...] = (
    ("046d:c081", "046d:c232"),  # G900 USB HID + G HUB virtual keyboard
)

_INSTALLED_SOURCE_RANK = {
    "user_confirmed": 5,
    "pnp_firmware_property": 4,
    "vendor_app_cache": 3,
    "driver_version": 2,
    "hid_driver": 1,
}


def usb_vid_pid(device_id: str) -> tuple[str, str]:
    m = _USB_VID_PID_RE.search(device_id or "")
    if not m:
        return "", ""
    return m.group(1).upper(), m.group(2).upper()


def _infer_vendor(name: str, pnp_class: str, device_id: str) -> str:
    return (de.infer_vendor_key(name, pnp_class, device_id) or "").strip().lower()


def _driver_version_for(name: str, driver_rows: list[dict]) -> str:
    name_l = (name or "").lower()
    for row in driver_rows or []:
        if (row.get("name") or row.get("DeviceName") or "").lower() == name_l:
            return (row.get("version") or row.get("DriverVersion") or "").strip()
    return ""


def resolve_peripheral_display_name(
    ent: dict,
    *,
    id_to_name: dict[str, str] | None = None,
) -> str:
    """Prefer USB parent / product hint over generic HID label (Phase A)."""
    device_id = (ent.get("device_id") or ent.get("DeviceID") or "").strip()
    name = (ent.get("name") or ent.get("Name") or "").strip()
    hint = fpv.product_hint(device_id, name)
    if hint and hint.product_name:
        return hint.product_name

    parent_name = (ent.get("parent_device_name") or "").strip()
    if parent_name and parent_name.lower() not in _GENERIC_HID_NAMES:
        return parent_name

    if id_to_name and device_id:
        parent_id = (ent.get("parent_device_id") or ent.get("Parent") or "").strip()
        if parent_id:
            walked = id_to_name.get(de.normalize_pnp_id(parent_id), "")
            if walked and walked.lower() not in _GENERIC_HID_NAMES:
                return walked

    if name and name.lower() not in _GENERIC_HID_NAMES:
        return name

    vid, pid = usb_vid_pid(device_id)
    vendor = _infer_vendor(name, ent.get("pnp_class") or ent.get("PNPClass") or "", device_id)
    if vendor and vid and pid:
        return f"{vendor.title()} USB ({vid}:{pid})"
    return name or "USB peripheral"


def _walk_parent_chain(device_id: str, id_to_name: dict[str, str]) -> tuple[str, str]:
    """Return (parent_id, parent_name) walking up one level from id_to_name map."""
    from device_enrichment import normalize_pnp_id

    current = normalize_pnp_id(device_id)
    # Parent should already be on row; this is fallback when only map available.
    return "", id_to_name.get(current, "")


def _usb_key_for_row(row: dict) -> str:
    vid = (row.get("vid") or "").strip().lower()
    pid = (row.get("pid") or "").strip().lower()
    if vid and pid:
        return f"{vid}:{pid}"
    device_id = row.get("device_id") or ""
    v, p = usb_vid_pid(device_id)
    return f"{v.lower()}:{p.lower()}" if v and p else ""


def _installed_rank(row: dict) -> int:
    src = (row.get("installed_source") or "").strip()
    base = _INSTALLED_SOURCE_RANK.get(src, 0)
    inst = (row.get("installed") or "").strip().lower()
    if inst in _USELESS_INSTALLED:
        return 0
    return base


def _merge_logitech_firmware_aliases(candidates: list[dict]) -> None:
    """Share stronger installed firmware between paired Logitech USB identities."""
    by_usb = {
        _usb_key_for_row(c): c
        for c in candidates
        if c.get("category") == "usb_peripheral" and _usb_key_for_row(c)
    }
    for left, right in _LOGITECH_USB_ALIASES:
        a = by_usb.get(left)
        b = by_usb.get(right)
        if not a or not b:
            continue
        donor, recv = (a, b) if _installed_rank(a) >= _installed_rank(b) else (b, a)
        if _installed_rank(donor) <= _installed_rank(recv):
            continue
        inst = (donor.get("installed") or "").strip()
        if inst.lower() in _USELESS_INSTALLED:
            continue
        recv["installed"] = inst
        recv["installed_source"] = donor.get("installed_source") or ""
        recv["installed_detail"] = donor.get("installed_detail") or ""


def _drop_redundant_logitech_virtual_rows(candidates: list[dict]) -> list[dict]:
    by_usb = {
        _usb_key_for_row(c): c
        for c in candidates
        if c.get("category") == "usb_peripheral" and _usb_key_for_row(c)
    }
    drop: set[str] = set()
    for physical, virtual in _LOGITECH_USB_ALIASES:
        if physical in by_usb and virtual in by_usb:
            drop.add(virtual)
    if not drop:
        return candidates
    return [c for c in candidates if _usb_key_for_row(c) not in drop]


def _winfw_is_useless(row: dict) -> bool:
    inst = (row.get("installed") or "").strip().lower()
    if inst in _USELESS_INSTALLED:
        return True
    resolved = (row.get("resolved_name") or row.get("component") or "").lower()
    if "microsoft uefi-compliant system" in resolved and inst in _USELESS_INSTALLED:
        return True
    return False


def _dedupe_winfw_rows(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        label = (row.get("resolved_name") or row.get("component") or row.get("key") or "").lower()
        prev = best.get(label)
        if prev is None or _installed_rank(row) > _installed_rank(prev):
            best[label] = row
    return list(best.values())


def filter_redundant_winfw_devices(
    candidates: list[dict],
    *,
    has_bios: bool = True,
) -> list[dict]:
    """Drop noisy Windows FIRMWARE-class rows when motherboard BIOS is already tracked."""
    if not has_bios:
        return candidates
    winfw = [c for c in candidates if c.get("category") == "windows_firmware"]
    if not winfw:
        return candidates
    other = [c for c in candidates if c.get("category") != "windows_firmware"]
    kept = [r for r in winfw if not _winfw_is_useless(r)]
    kept = _dedupe_winfw_rows(kept)
    if not kept:
        return other
    return other + kept


def finalize_secondary_firmware_devices(
    candidates: list[dict],
    *,
    has_bios: bool = True,
) -> list[dict]:
    """Merge vendor aliases, drop virtual duplicates, and hide redundant UEFI nodes."""
    rows = list(candidates or [])
    _merge_logitech_firmware_aliases(rows)
    rows = _drop_redundant_logitech_virtual_rows(rows)
    return filter_redundant_winfw_devices(rows, has_bios=has_bios)


def discover_secondary_firmware_devices(
    pnp_list: list[dict],
    driver_rows: list[dict] | None = None,
    *,
    query_pnp_firmware: bool = True,
    has_bios: bool = False,
) -> list[dict]:
    """
    Secondary-tier firmware candidates from an existing PnP snapshot.

    Returns normalized dicts suitable for GUI rows and catalog search.
    """
    id_to_name = de.build_pnp_id_to_name_map(pnp_list)
    seen_usb: set[tuple[str, str]] = set()
    seen_win_fw: set[str] = set()
    candidates: list[dict] = []
    firmware_query_ids: list[str] = []

    for ent in pnp_list or []:
        if not isinstance(ent, dict):
            continue
        name = (ent.get("Name") or ent.get("name") or "").strip()
        pnp_class = (ent.get("PNPClass") or ent.get("pnp_class") or "").strip()
        device_id = (ent.get("DeviceID") or ent.get("device_id") or "").strip()
        if not device_id:
            continue
        pnp_l = pnp_class.lower()
        name_l = name.lower()
        vendor = _infer_vendor(name, pnp_class, device_id)

        parent_fields = de.pnp_parent_fields_from_row(ent, id_to_name)
        row_base = {
            "device_id": device_id,
            "name": name,
            "pnp_class": pnp_class,
            "vendor_key": vendor,
            **parent_fields,
        }

        if pnp_l == "firmware" or name_l == "device firmware" or _FIRMWARE_NAME_RE.search(name):
            key = name_l[:80]
            if key in seen_win_fw:
                continue
            seen_win_fw.add(key)
            resolved = resolve_peripheral_display_name(row_base, id_to_name=id_to_name)
            candidates.append({
                **row_base,
                "category": "windows_firmware",
                "subcategory": "pnp_firmware_class",
                "tier": "secondary",
                "resolved_name": resolved,
                "component": f"System firmware — {resolved}",
                "key": f"winfw:{de.normalize_pnp_id(device_id)[:40]}",
                "driver_version": _driver_version_for(name, driver_rows or []),
            })
            firmware_query_ids.append(device_id)
            continue

        vid, pid = usb_vid_pid(device_id)
        if not vid or not pid:
            continue
        if not vendor and vid:
            vendor = (de._USB_VID_VENDORS.get(vid.upper()) or "").strip().lower()
            if vendor:
                row_base["vendor_key"] = vendor
        usb_key = (vid, pid)
        if usb_key in seen_usb:
            continue
        is_peripheral = pnp_l in ("keyboard", "mouse", "hidclass", "media", "camera")
        known_vendor = vendor in _PERIPHERAL_FW_VENDORS or vendor in fpv.VENDOR_SITE_REGISTRY
        if not (is_peripheral and (known_vendor or pnp_l in ("keyboard", "mouse"))):
            continue
        seen_usb.add(usb_key)
        resolved = resolve_peripheral_display_name(row_base, id_to_name=id_to_name)
        hint = fpv.product_hint(device_id, resolved)
        if hint and hint.vendor_key and not vendor:
            vendor = hint.vendor_key
            row_base["vendor_key"] = vendor
        sub = pnp_l or "usb"
        candidates.append({
            **row_base,
            "category": "usb_peripheral",
            "subcategory": sub,
            "tier": "secondary",
            "resolved_name": resolved,
            "product_name": hint.product_name if hint else resolved,
            "component": resolved,
            "key": f"peripheral:{vid.lower()}:{pid.lower()}",
            "driver_version": _driver_version_for(name, driver_rows or []),
            "vid": vid,
            "pid": pid,
        })
        firmware_query_ids.extend([device_id, parent_fields.get("parent_device_id", "")])

    pnp_fw: dict[str, str] = {}
    if query_pnp_firmware and firmware_query_ids:
        ids = list(dict.fromkeys(i for i in firmware_query_ids if i))
        try:
            pnp_fw = fpinst.lookup_pnp_firmware_versions(ids[:40])
        except Exception:
            pnp_fw = {}

    user_cache = fpinst.load_user_confirmed()
    for c in candidates:
        inst = fpinst.resolve_installed_firmware(
            {
                **c,
                "installed_version": c.get("driver_version") or "",
            },
            pnp_firmware=pnp_fw,
            user_cache=user_cache,
        )
        c.update(inst)

    return finalize_secondary_firmware_devices(candidates, has_bios=has_bios)


def device_for_key(key: str, devices: list[dict]) -> dict | None:
    k = (key or "").strip()
    for d in devices:
        if (d.get("key") or "") == k:
            return d
    return None
