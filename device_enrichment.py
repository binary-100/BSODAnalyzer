"""
Resolve friendly device labels and vendor keys from PnP data, USB VID, PCI VEN, EDID, and disk WMI.
Used across System/Drivers tabs and driver catalog lookup.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

_USB_VID_VENDORS: dict[str, str] = {
    k.lower(): v for k, v in {
        "046D": "logitech", "045E": "microsoft", "04F2": "chicony", "04D9": "holtek",
        "05AC": "apple", "0B05": "asus", "0CF3": "qualcomm", "0E8D": "mediatek",
        "0BDA": "realtek", "10DE": "nvidia", "1002": "amd", "8086": "intel",
        "8087": "intel", "0951": "kingston", "0781": "sandisk", "058F": "alcor",
        "0BC2": "seagate", "1058": "wd", "174C": "asmedia", "1B1C": "corsair",
        "1532": "razer", "2516": "thermaltake", "1BCF": "sunplus", "5986": "bison",
        "13D3": "azurewave", "0489": "foxconn", "04CA": "lite-on", "0930": "toshiba",
        "0424": "microchip", "05E3": "genesys", "17EF": "lenovo", "03F0": "hp",
        "413C": "dell", "18D1": "google", "0A5C": "broadcom", "1286": "marvell",
        "2357": "tplink", "2352": "fresco", "10C4": "silicon labs", "0403": "ftdi",
        "067B": "prolific", "04E8": "samsung", "054C": "sony", "2B7E": "elgato",
        "2717": "xiaomi", "2E95": "xiaomi", "1E71": "nvidia", "3434": "keychron",
        "320F": "royal kludge", "25A7": "a4tech", "1A86": "wch", "2109": "via",
        "1038": "steelseries", "1A40": "termius", "152D": "jmicron", "14CD": "jmicron",
        "1B96": "wd", "0B97": "hp", "048D": "ite", "3277": "xiaomi",
        "2B54": "azurewave", "0CF2": "ene", "22D9": "oppo", "2A70": "oneplus",
        "05C6": "qualcomm", "0BB4": "htc", "2C7C": "mercury", "1BBB": "tcl",
        "04BB": "iwatsu", "18F8": "soundgraph", "0E0F": "vmware", "203A": "parallels",
        "1D5C": "fresco", "0B95": "asus",
    }.items()
}

_PCI_VEN_VENDORS: dict[str, str] = {
    k.lower(): v for k, v in {
        "10DE": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel", "8087": "intel",
        "14E4": "broadcom", "10EC": "realtek", "1969": "qualcomm", "168C": "qualcomm",
        "11AB": "marvell", "15B3": "mellanox", "19E5": "huawei", "1D6A": "google",
        "1AE0": "google", "1B21": "asmedia", "1B73": "fresco", "1B85": "ocz",
        "144D": "samsung", "1179": "toshiba", "15AD": "vmware", "1AF4": "amazon",
        "1B36": "qemu", "1B4B": "marvell", "1C5C": "hynix", "1C5F": "memblaze",
        "1E49": "corsair", "1E4B": "maxio", "14C3": "mediatek", "17CB": "qualcomm",
        "1AE9": "cavium", "1D79": "transcend", "1E0F": "kioxia", "1B96": "wd",
        "1C58": "sandisk", "1BB1": "seagate", "1C0F": "micron", "1D94": "chengdu",
        "1E36": "shannon", "1234": "qemu", "1A03": "aspeed", "10B5": "plx",
        "1B4C": "galaxy", "1D0F": "amazon", "1B73": "fresco",
    }.items()
}

_USB_VID_RE = re.compile(r"VID[_&]([0-9A-Fa-f]{4})", re.I)
_PCI_VEN_RE = re.compile(r"VEN[_&]([0-9A-Fa-f]{4})", re.I)
_PCI_DEV_RE = re.compile(r"DEV[_&]([0-9A-Fa-f]{4})", re.I)
_GENERIC_NAME_MARKERS = (
    "generic", "unknown", "standard ", "base system", "pci device",
    "high definition audio device", "usb composite", "usb root hub",
    "ethernet controller", "bluetooth", "monitor", "hub",
)


def parse_hardware_ids(device_id: str) -> dict[str, str]:
    dev = (device_id or "").upper()
    out: dict[str, str] = {}
    m = _USB_VID_RE.search(dev)
    if m:
        out["usb_vid"] = m.group(1).lower()
    m = _PCI_VEN_RE.search(dev)
    if m:
        out["pci_ven"] = m.group(1).lower()
    m = _PCI_DEV_RE.search(dev)
    if m:
        out["pci_dev"] = m.group(1).lower()
    return out


def vendor_from_hardware_ids(hw: dict[str, str]) -> str | None:
    vid = hw.get("usb_vid") or ""
    if vid and vid in _USB_VID_VENDORS:
        return _USB_VID_VENDORS[vid] or None
    ven = hw.get("pci_ven") or ""
    if ven and ven in _PCI_VEN_VENDORS:
        return _PCI_VEN_VENDORS[ven]
    return None


def is_likely_generic_name(name: str) -> bool:
    n = (name or "").lower()
    return any(m in n for m in _GENERIC_NAME_MARKERS)


def infer_vendor_key(
    name: str,
    pnp_class: str = "",
    manufacturer: str = "",
    device_id: str = "",
    *,
    edid_brand: str = "",
    disk_model: str = "",
    known_vendor_fn: Callable[[str], str | None] | None = None,
) -> str | None:
    if known_vendor_fn:
        for text in (edid_brand, manufacturer, disk_model, name):
            if text:
                v = known_vendor_fn(text)
                if v:
                    return v.lower()
    v = vendor_from_hardware_ids(parse_hardware_ids(device_id))
    if v:
        return v
    if known_vendor_fn:
        v = known_vendor_fn(f"{manufacturer} {name} {pnp_class} {device_id}")
        if v:
            return v.lower()
    return None


def _pnp_class_is_monitor(pnp_class: str) -> bool:
    return (pnp_class or "").strip().lower() == "monitor"


def _pnp_class_is_disk(pnp_class: str) -> bool:
    return (pnp_class or "").strip().lower() in ("diskdrive", "scsiadapter", "hdc")


def _manufacturer_for_display(
    manufacturer: str,
    name: str,
    pnp_class: str = "",
    *,
    edid_brand: str = "",
    vendor_key: str | None = None,
) -> str:
    """Avoid prefixing with 'Microsoft' when the device name already names the real vendor."""
    mfr = (manufacturer or "").strip()
    name_lower = (name or "").lower()
    pnp_lower = (pnp_class or "").lower()
    if mfr.lower() == "microsoft":
        if any(
            tok in name_lower
            for tok in (
                "amd", "nvidia", "intel", "realtek", "qualcomm", "mediatek",
                "broadcom", "killer", "marvell", "atheros", "lg ", "samsung",
            )
        ):
            return ""
        if pnp_lower in ("media", "audioendpoint", "sound", "display"):
            return ""
    if not mfr and edid_brand and _pnp_class_is_monitor(pnp_class):
        return edid_brand
    if not mfr and vendor_key:
        return vendor_key.replace("_", " ").title()
    return mfr


def format_display_label(
    name: str,
    pnp_class: str = "",
    manufacturer: str = "",
    device_id: str = "",
    *,
    edid_brand: str = "",
    edid_product: str = "",
    disk_model: str = "",
    vendor_key: str | None = None,
) -> str:
    name = (name or "").strip()
    pnp_lower = (pnp_class or "").lower()
    name_lower = name.lower()
    mfr = _manufacturer_for_display(
        manufacturer, name, pnp_class, edid_brand=edid_brand, vendor_key=vendor_key
    )

    if (
        _pnp_class_is_monitor(pnp_class)
        and edid_brand
        and edid_product
        and edid_brand.lower() not in name_lower
    ):
        return f"{edid_brand} {edid_product} ({name})".strip()

    if (
        _pnp_class_is_disk(pnp_class)
        and disk_model
        and is_likely_generic_name(name)
        and disk_model.lower() not in name_lower
    ):
        return f"{disk_model} ({name})".strip()

    hw = parse_hardware_ids(device_id)
    vid = hw.get("usb_vid")
    if is_likely_generic_name(name) and vid and vid in _USB_VID_VENDORS:
        vname = _USB_VID_VENDORS[vid].title()
        if vname and vname.lower() not in name_lower:
            return f"{vname} — {name}"

    ven = hw.get("pci_ven")
    if is_likely_generic_name(name) and ven and ven in _PCI_VEN_VENDORS:
        vname = _PCI_VEN_VENDORS[ven].title()
        if vname and vname.lower() not in name_lower:
            return f"{vname} — {name}"

    enrich_classes = (
        "monitor", "usb", "bluetooth", "net", "media", "hdc", "scsiadapter",
        "diskdrive", "camera", "image", "printer", "printqueue",
    )
    if mfr and (
        is_likely_generic_name(name)
        or (mfr.lower() not in name_lower and pnp_lower in enrich_classes)
    ):
        return f"{mfr} — {name}"
    return name


def _edid_for_device(
    device_id: str,
    monitor_edid: dict[str, dict] | None,
    pnp_class: str = "",
) -> tuple[str, str]:
    if not _pnp_class_is_monitor(pnp_class) or not monitor_edid or not device_id:
        return "", ""
    dev_upper = device_id.upper()
    if "MONITOR\\" not in dev_upper:
        return "", ""
    for key, info in monitor_edid.items():
        if not key.startswith("MONITOR\\"):
            continue
        if key in dev_upper:
            return (
                (info.get("brand") or "").strip(),
                (info.get("product_code") or "").strip(),
            )
    return "", ""


def _disk_model_for_device(
    device_id: str,
    disk_fragments: dict[str, str] | None,
    pnp_class: str = "",
) -> str:
    if not _pnp_class_is_disk(pnp_class) or not disk_fragments or not device_id:
        return ""
    dev_upper = device_id.upper()
    for frag, model in disk_fragments.items():
        if len(frag) < 10:
            continue
        if frag in dev_upper:
            return model
    return ""


def normalize_pnp_id(device_id: str) -> str:
    return (device_id or "").strip().upper()


def build_pnp_id_to_name_map(pnp_list: list[dict]) -> dict[str, str]:
    """Map PnP instance ID -> friendly name from the same scan snapshot."""
    out: dict[str, str] = {}
    for row in pnp_list or []:
        if not isinstance(row, dict):
            continue
        did = normalize_pnp_id(row.get("DeviceID") or row.get("device_id") or "")
        name = (row.get("Name") or row.get("name") or "").strip()
        if did and name:
            out[did] = name
    return out


def pnp_parent_fields_from_row(
    pnp_row: dict,
    id_to_name: dict[str, str],
) -> dict[str, str]:
    """
    Verified Windows parent link only — no name guessing.

    Returns parent_device_id/name when DEVPKEY_Device_Parent resolves to another
    device in the same pnp_list snapshot.
    """
    parent_id = (pnp_row.get("Parent") or pnp_row.get("parent") or "").strip()
    if not parent_id:
        return {}
    child_name = (pnp_row.get("Name") or pnp_row.get("name") or "").strip()
    parent_name = id_to_name.get(normalize_pnp_id(parent_id))
    if not parent_name or parent_name == child_name:
        return {}
    return {
        "parent_device_id": parent_id,
        "parent_device_name": parent_name,
    }


def enrich_pnp_device(
    pnp_row: dict,
    *,
    monitor_edid: dict[str, dict] | None = None,
    disk_by_pnp_fragment: dict[str, str] | None = None,
    known_vendor_fn: Callable[[str], str | None] | None = None,
    pnp_id_to_name: dict[str, str] | None = None,
) -> dict[str, Any]:
    name = (pnp_row.get("Name") or "").strip()
    pnp_class = (pnp_row.get("PNPClass") or "").strip()
    mfr = (pnp_row.get("Manufacturer") or "").strip()
    device_id = (pnp_row.get("DeviceID") or "").strip()
    edid_brand, edid_product = _edid_for_device(device_id, monitor_edid, pnp_class)
    disk_model = _disk_model_for_device(device_id, disk_by_pnp_fragment, pnp_class)
    vendor_key = infer_vendor_key(
        name, pnp_class, mfr, device_id,
        edid_brand=edid_brand, disk_model=disk_model, known_vendor_fn=known_vendor_fn,
    )
    display_name = format_display_label(
        name, pnp_class, mfr, device_id,
        edid_brand=edid_brand, edid_product=edid_product, disk_model=disk_model,
        vendor_key=vendor_key,
    )
    hw = parse_hardware_ids(device_id)
    out: dict[str, Any] = {
        "name": name,
        "display_name": display_name,
        "manufacturer": mfr,
        "pnp_class": pnp_class,
        "device_id": device_id,
        "config_manager_error_code": int(pnp_row.get("ConfigManagerErrorCode", 0)),
        "vendor_key": vendor_key or "",
        "usb_vid": hw.get("usb_vid", ""),
        "pci_ven": hw.get("pci_ven", ""),
        "pci_dev": hw.get("pci_dev", ""),
        "disk_model": disk_model,
        "edid_brand": edid_brand,
    }
    if pnp_id_to_name:
        out.update(pnp_parent_fields_from_row(pnp_row, pnp_id_to_name))
    return out


def _enrich_pnp_chunk(
    chunk: list[dict],
    *,
    monitor_edid: dict[str, dict] | None,
    disk_by_pnp_fragment: dict[str, str] | None,
    known_vendor_fn: Callable[[str], str | None] | None,
    pnp_id_to_name: dict[str, str] | None = None,
) -> dict[str, dict]:
    partial: dict[str, dict] = {}
    for row in chunk:
        name = (row.get("Name") or "").strip()
        if not name or name in partial:
            continue
        partial[name] = enrich_pnp_device(
            row,
            monitor_edid=monitor_edid,
            disk_by_pnp_fragment=disk_by_pnp_fragment,
            known_vendor_fn=known_vendor_fn,
            pnp_id_to_name=pnp_id_to_name,
        )
    return partial


def _name_tokens(name: str) -> list[str]:
    parts = re.split(r"[^a-z0-9]+", (name or "").lower())
    return [p for p in parts if len(p) >= 4]


class PnpEnrichmentLookup:
    """Fast name/display/token indexes for matching driver rows to PnP enrichment."""

    __slots__ = ("_by_name", "_by_lower", "_by_display_lower", "_token_keys")

    def __init__(self, index: dict[str, dict]) -> None:
        self._by_name = index
        self._by_lower: dict[str, dict] = {}
        self._by_display_lower: dict[str, dict] = {}
        self._token_keys: dict[str, set[str]] = {}
        for name, data in index.items():
            nl = name.lower()
            if nl not in self._by_lower:
                self._by_lower[nl] = data
            dn = (data.get("display_name") or "").strip().lower()
            if dn and dn not in self._by_display_lower:
                self._by_display_lower[dn] = data
            for token in _name_tokens(name):
                self._token_keys.setdefault(token, set()).add(name)
            if dn:
                for token in _name_tokens(dn):
                    self._token_keys.setdefault(token, set()).add(name)

    @classmethod
    def from_index(cls, index: dict[str, dict] | None) -> PnpEnrichmentLookup | None:
        if not index:
            return None
        return cls(index)

    def match(self, name: str) -> dict | None:
        if not name:
            return None
        hit = self._by_name.get(name)
        if hit:
            return hit
        nl = name.lower()
        hit = self._by_lower.get(nl)
        if hit:
            return hit
        hit = self._by_display_lower.get(nl)
        if hit:
            return hit
        tokens = _name_tokens(name)
        if tokens:
            candidate_keys: set[str] | None = None
            for token in tokens:
                keys = self._token_keys.get(token)
                if not keys:
                    continue
                if candidate_keys is None:
                    candidate_keys = set(keys)
                else:
                    candidate_keys &= keys
                if not candidate_keys:
                    break
            if candidate_keys:
                for key in candidate_keys:
                    pl = key.lower()
                    if nl == pl or nl in pl or pl in nl:
                        return self._by_name[key]
        for pname, pdata in self._by_name.items():
            pl = pname.lower()
            if nl == pl or nl in pl or pl in nl:
                return pdata
        return None


def pnp_lookup_from_ctx(system_ctx: dict | None) -> PnpEnrichmentLookup | None:
    """Reuse or build a session lookup from hardware profile context."""
    if not system_ctx:
        return None
    lu = system_ctx.get("_pnp_enrichment_lu")
    if isinstance(lu, PnpEnrichmentLookup):
        return lu
    idx = system_ctx.get("pnp_enrichment") or {}
    if not idx:
        return None
    lu = PnpEnrichmentLookup.from_index(idx)
    if lu is not None:
        system_ctx["_pnp_enrichment_lu"] = lu
    return lu


def build_pnp_enrichment_index(
    pnp_list: list[dict],
    *,
    monitor_edid: dict[str, dict] | None = None,
    disk_by_pnp_fragment: dict[str, str] | None = None,
    known_vendor_fn: Callable[[str], str | None] | None = None,
    parallel: bool = True,
) -> dict[str, dict]:
    rows = list(pnp_list or [])
    if not rows:
        return {}
    pnp_id_to_name = build_pnp_id_to_name_map(rows)
    if not parallel or len(rows) < 60:
        return _enrich_pnp_chunk(
            rows,
            monitor_edid=monitor_edid,
            disk_by_pnp_fragment=disk_by_pnp_fragment,
            known_vendor_fn=known_vendor_fn,
            pnp_id_to_name=pnp_id_to_name,
        )
    workers = min(6, max(2, (len(rows) + 49) // 50))
    chunk_size = max(1, (len(rows) + workers - 1) // workers)
    chunks = [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]
    index: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(
                _enrich_pnp_chunk,
                ch,
                monitor_edid=monitor_edid,
                disk_by_pnp_fragment=disk_by_pnp_fragment,
                known_vendor_fn=known_vendor_fn,
                pnp_id_to_name=pnp_id_to_name,
            )
            for ch in chunks
        ]
        for fut in as_completed(futures):
            index.update(fut.result())
    return index


def merge_enrichment_into_device(base: dict, enrichment: dict | None) -> dict:
    out = dict(base)
    if not enrichment:
        return out
    for key in (
        "display_name", "manufacturer", "pnp_class", "device_id",
        "vendor_key", "usb_vid", "pci_ven", "pci_dev", "disk_model",
        "parent_device_id", "parent_device_name",
    ):
        val = enrichment.get(key)
        if val:
            out[key] = val
    return out


def _match_pnp_enrichment(
    name: str,
    pnp_index: dict[str, dict],
    lookup: PnpEnrichmentLookup | None = None,
) -> dict | None:
    if not name or not pnp_index:
        return None
    if lookup is not None:
        return lookup.match(name)
    if len(pnp_index) >= 60:
        return PnpEnrichmentLookup(pnp_index).match(name)
    hit = pnp_index.get(name)
    if hit:
        return hit
    nl = name.lower()
    for pname, pdata in pnp_index.items():
        pl = pname.lower()
        if nl == pl or nl in pl or pl in nl:
            return pdata
    return None


def _enrich_driver_row(
    row: dict,
    pnp_index: dict[str, dict],
    *,
    known_vendor_fn: Callable[[str], str | None] | None,
    lookup: PnpEnrichmentLookup | None = None,
) -> dict:
    name = (row.get("name") or "").strip()
    hit = _match_pnp_enrichment(name, pnp_index, lookup=lookup)
    if hit:
        return merge_enrichment_into_device(row, hit)
    pnp_class = (row.get("device_class") or "").strip()
    vk = infer_vendor_key(name, pnp_class, "", known_vendor_fn=known_vendor_fn)
    merged = dict(row)
    merged["display_name"] = format_display_label(name, pnp_class, vendor_key=vk)
    if vk:
        merged["vendor_key"] = vk
    return merged


def enrich_driver_inventory_rows(
    rows: list[dict],
    pnp_index: dict[str, dict],
    *,
    known_vendor_fn: Callable[[str], str | None] | None = None,
    parallel: bool = True,
) -> list[dict]:
    items = list(rows or [])
    if not items:
        return []
    lookup = PnpEnrichmentLookup.from_index(pnp_index) if len(pnp_index) >= 60 else None
    if not parallel or len(items) < 100:
        enriched = [
            _enrich_driver_row(
                r, pnp_index, known_vendor_fn=known_vendor_fn, lookup=lookup,
            )
            for r in items
        ]
    else:
        workers = min(8, max(2, (len(items) + 99) // 100))
        chunk_size = max(1, (len(items) + workers - 1) // workers)
        chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
        out: list[dict | None] = [None] * len(items)
        ordered_chunks: list[tuple[int, list[dict]]] = []
        pos = 0
        for ch in chunks:
            ordered_chunks.append((pos, ch))
            pos += len(ch)

        def _run_chunk(start: int, chunk: list[dict]) -> tuple[int, list[dict]]:
            return start, [
                _enrich_driver_row(
                    r, pnp_index, known_vendor_fn=known_vendor_fn, lookup=lookup,
                )
                for r in chunk
            ]

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_run_chunk, start, ch) for start, ch in ordered_chunks]
            for fut in as_completed(futures):
                start, enriched_chunk = fut.result()
                for i, row in enumerate(enriched_chunk):
                    out[start + i] = row
        enriched = [r for r in out if r is not None]

    try:
        import catalog_device_roles as cdr

        return cdr.apply_catalog_roles_to_inventory(enriched)
    except ImportError:
        return enriched


def get_disk_drives_from_wmi(run_powershell_fn) -> list[dict]:
    """Win32_DiskDrive rows via injected run_powershell (avoids circular import)."""
    ps = r"""
Get-CimInstance Win32_DiskDrive -ErrorAction SilentlyContinue |
  Select-Object Model, InterfaceType, PNPDeviceID |
  ConvertTo-Json -Compress
"""
    ok, out = run_powershell_fn(ps, timeout=25)
    if not ok or not out:
        return []
    try:
        import json
        data = json.loads(out)
        return [data] if isinstance(data, dict) else list(data)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []


def disk_models_by_pnp_fragment(disk_rows: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in disk_rows or []:
        pnp_id = (d.get("PNPDeviceID") or d.get("DeviceID") or "").strip()
        model = (d.get("Model") or "").strip()
        if not pnp_id or not model:
            continue
        parts = pnp_id.upper().split("\\")
        for part in parts:
            if len(part) >= 10:
                out[part] = model
    return out
