"""Catalog-facing device roles derived from enriched driver inventory (both load paths).

Accuracy contract for ``catalog_skip_mscatalog`` (6.5.6+):
- **monitor_edid + SWC child:** MSCatalog is skipped on the inbox EDID monitor row only.
  The SoftwareComponent child still runs full MSCatalog/WU/OEM. Parent rows were a
  duplicate/false-positive source (see ``swc_driver_update_on_monitor`` reject).
- **dell_internal:** DellUtils / DellInstrumentation — no legitimate MSCatalog driver
  packages; skipping removes noise only.

These skips **save wall time** without removing coverage from the device that actually
needs the update. They are not P2b-style deferral (which can miss updates if too broad).
"""

from __future__ import annotations

import re

_ROLE_SOFTWARECOMPONENT = "softwarecomponent"
_ROLE_MONITOR_EDID = "monitor_edid"
_ROLE_DELL_INTERNAL = "dell_internal"
_ROLE_GPU_COMPANION = "gpu_companion"
_ROLE_PRIMARY_DISPLAY = "primary_display"
_ROLE_STANDARD = "standard"

_INBOX_MONITOR_VERSIONS = frozenset({"", "?", "—", "1.0.0.0", "0.0.0.0"})
_DELL_INTERNAL_PNP = frozenset({"dellutils", "dellinstrumentation"})
_NPCF_MARKERS = ("nvda0820", "platform controllers and framework", "npcf")


def _row_name(row: dict) -> str:
    return (row.get("name") or row.get("device_name") or "").strip()


def _row_pnp_class(row: dict) -> str:
    return (
        (row.get("pnp_class") or row.get("device_class") or "")
        .strip()
        .lower()
    )


def _row_version(row: dict) -> str:
    return (row.get("version") or "").strip()


def _normalize_id(value: str) -> str:
    return (value or "").strip().upper()


def derive_catalog_device_role(row: dict) -> str:
    """Single-row role hint before parent/child index is applied."""
    pnp = _row_pnp_class(row)
    name_l = _row_name(row).lower()
    inst = _normalize_id(row.get("device_id") or row.get("instance_id") or "")
    vk = (row.get("vendor_key") or "").lower()

    if pnp in _DELL_INTERNAL_PNP or "dellutils" in name_l or "dellinstrumentation" in name_l:
        return _ROLE_DELL_INTERNAL
    if pnp == "softwarecomponent" or "softwarecomponent" in pnp:
        return _ROLE_SOFTWARECOMPONENT
    if any(m in inst for m in ("\\NVDA0820\\", "ACPI\\NVDA0820")) or any(
        m in name_l for m in _NPCF_MARKERS
    ):
        return _ROLE_GPU_COMPANION
    if pnp == "display" and vk in ("nvidia", "amd", "intel"):
        return _ROLE_PRIMARY_DISPLAY
    if pnp == "monitor" or (row.get("device_class") or "").upper() == "MONITOR":
        if _row_version(row).lower() in _INBOX_MONITOR_VERSIONS:
            return _ROLE_MONITOR_EDID
    return _ROLE_STANDARD


def apply_catalog_roles_to_inventory(rows: list[dict]) -> list[dict]:
    """
    Attach catalog_role and parent/child hints to every inventory row.

    Called at the end of enrich_driver_inventory_rows so Run Analysis and
    Load Devices share the same derived metadata.
    """
    items = [dict(r) for r in (rows or []) if isinstance(r, dict)]
    if not items:
        return []

    by_name: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for row in items:
        name = _row_name(row)
        if name:
            by_name[name.lower()] = row
        dev_id = _normalize_id(row.get("device_id") or row.get("instance_id") or "")
        if dev_id:
            by_id[dev_id] = row

    children_by_parent_id: dict[str, list[str]] = {}
    children_by_parent_name: dict[str, list[str]] = {}
    for row in items:
        name = _row_name(row)
        if not name:
            continue
        parent_id = _normalize_id(row.get("parent_device_id") or "")
        parent_name = (row.get("parent_device_name") or "").strip().lower()
        if parent_id:
            children_by_parent_id.setdefault(parent_id, []).append(name)
        if parent_name:
            children_by_parent_name.setdefault(parent_name, []).append(name)

    out: list[dict] = []
    for row in items:
        merged = dict(row)
        role = derive_catalog_device_role(merged)
        merged["catalog_role"] = role

        name = _row_name(merged)
        name_l = name.lower()
        child_names = list(children_by_parent_name.get(name_l) or [])
        dev_id = _normalize_id(merged.get("device_id") or merged.get("instance_id") or "")
        if dev_id:
            for ch in children_by_parent_id.get(dev_id, []):
                if ch not in child_names:
                    child_names.append(ch)

        swc_children = [
            ch
            for ch in child_names
            if derive_catalog_device_role(by_name.get(ch.lower()) or {}) == _ROLE_SOFTWARECOMPONENT
        ]
        merged["catalog_child_names"] = child_names
        merged["catalog_has_swc_child"] = bool(swc_children)

        skip_mscatalog = False
        if role == _ROLE_MONITOR_EDID and merged.get("catalog_has_swc_child"):
            skip_mscatalog = True
        if role == _ROLE_DELL_INTERNAL:
            skip_mscatalog = True
        merged["catalog_skip_mscatalog"] = skip_mscatalog
        out.append(merged)

    return out


def wu_parent_child_preference(
    title: str,
    candidate_a: str,
    ctx_a: dict,
    candidate_b: str,
    ctx_b: dict,
) -> str:
    """
    Tie-break two devices for the same WU package — prefer SWC child over monitor parent.
    Returns the winning device name.
    """
    title_l = (title or "").lower()
    is_swc_pkg = "softwarecomponent" in title_l or "audioprocessingobject" in title_l
    if not is_swc_pkg:
        return candidate_a

    role_a = (ctx_a.get("catalog_role") or "").lower()
    role_b = (ctx_b.get("catalog_role") or "").lower()
    if role_a == _ROLE_SOFTWARECOMPONENT and role_b != _ROLE_SOFTWARECOMPONENT:
        return candidate_a
    if role_b == _ROLE_SOFTWARECOMPONENT and role_a != _ROLE_SOFTWARECOMPONENT:
        return candidate_b

    parent_a = (ctx_a.get("parent_device_name") or "").strip().lower()
    parent_b = (ctx_b.get("parent_device_name") or "").strip().lower()
    name_a = (ctx_a.get("target_device_name") or ctx_a.get("device_label") or "").strip().lower()
    name_b = (ctx_b.get("target_device_name") or ctx_b.get("device_label") or "").strip().lower()
    if parent_a == name_b:
        return candidate_a
    if parent_b == name_a:
        return candidate_b
    return candidate_a


__all__ = [
    "apply_catalog_roles_to_inventory",
    "derive_catalog_device_role",
    "wu_parent_child_preference",
]
