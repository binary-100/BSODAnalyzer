"""Cross-scheme driver version identity for compare and coverage-gap logic.

Maps equivalent version strings across OEM, vendor-site, and Windows inbox
numbering (e.g. Realtek NIC 1125.30.50.508 ↔ Realtek.com 11.030.50).
"""

from __future__ import annotations

import re
from typing import Any


def parse_version(version: str) -> tuple[int, ...]:
    """Normalize dotted version strings for segment comparison."""
    if not version:
        return ()
    s = str(version).strip()
    m = re.search(r"(\d+(?:\.\d+){1,6})", s)
    if not m:
        return ()
    parts: list[int] = []
    for p in m.group(1).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


def _looks_like_realtek_nic_oem_version(version: str) -> bool:
    parts = parse_version(version)
    if len(parts) < 2:
        return False
    if parts[0] >= 1000:
        return True
    return len(parts) >= 4 and parts[0] >= 100


def _realtek_nic_oem_build_suffix(version: str) -> tuple[int, ...]:
    parts = parse_version(version)
    if len(parts) < 2:
        return ()
    return parts[1:]


def _realtek_nic_public_build_suffix(version: str) -> tuple[int, ...]:
    parts = parse_version(version)
    if len(parts) == 3 and parts[0] < 1000:
        return tuple(parts[1:])
    return ()


def _suffixes_match_prefix(oem_tail: tuple[int, ...], pub_tail: tuple[int, ...]) -> bool:
    if not oem_tail or not pub_tail:
        return False
    if oem_tail == pub_tail:
        return True
    return oem_tail[: len(pub_tail)] == pub_tail


def realtek_nic_versions_equivalent(installed: str, candidate: str) -> bool:
    """True when Realtek.com 11.x.y matches OEM 1125.x.y.z (shared build suffix)."""
    inst = (installed or "").strip()
    cand = (candidate or "").strip()
    if not inst or not cand:
        return False
    oem_tail = (
        _realtek_nic_oem_build_suffix(inst)
        if _looks_like_realtek_nic_oem_version(inst)
        else ()
    )
    pub_tail = _realtek_nic_public_build_suffix(cand)
    if _suffixes_match_prefix(oem_tail, pub_tail):
        return True
    oem_tail_c = (
        _realtek_nic_oem_build_suffix(cand)
        if _looks_like_realtek_nic_oem_version(cand)
        else ()
    )
    pub_tail_i = _realtek_nic_public_build_suffix(inst)
    return _suffixes_match_prefix(oem_tail_c, pub_tail_i)


def realtek_nic_equivalence_note(installed: str, candidate: str) -> str:
    return (
        f"Realtek.com package {candidate} matches installed OEM build {installed} "
        "(same driver — Realtek.com uses 11.x.y vs Dell/OEM 1125.x.y.z numbering)."
    )


def _ctx_vendor_key(device_ctx: dict | None) -> str:
    return ((device_ctx or {}).get("vendor_key") or "").strip().lower()


def _ctx_pnp_class(device_ctx: dict | None) -> str:
    return ((device_ctx or {}).get("pnp_class") or "").strip().lower()


def versions_equivalent(
    installed: str,
    candidate: str,
    *,
    device_ctx: dict | None = None,
    vendor_key: str = "",
    pnp_class: str = "",
) -> tuple[bool, str]:
    """Return (equivalent, note) when two version strings name the same driver build."""
    inst = (installed or "").strip()
    cand = (candidate or "").strip()
    if not inst or not cand:
        return False, ""
    vk = vendor_key.lower() or _ctx_vendor_key(device_ctx)
    pnp = pnp_class.lower() or _ctx_pnp_class(device_ctx)
    if vk == "realtek" and pnp == "net":
        if realtek_nic_versions_equivalent(inst, cand):
            return True, realtek_nic_equivalence_note(inst, cand)
    return False, ""


def catalog_offer_matches_installed(
    installed: str,
    catalog_version: str,
    *,
    device_ctx: dict | None = None,
    numeric_same=None,
) -> bool:
    """True when a catalog version string represents the same build as installed.

    ``numeric_same`` should be compare_versions(installed, catalog_version) == "same"
    when the caller already computed it (avoids importing driver_catalog here).
    """
    if numeric_same is True:
        return True
    eq, _note = versions_equivalent(installed, catalog_version, device_ctx=device_ctx)
    return eq
