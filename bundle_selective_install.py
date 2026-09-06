"""Manifest-guided selective install — map bundle components to extract paths.

Uses the same component labels as ``bundle_verification`` (AMD DevID.xml / Info.xml
installer tags, Intel INF names, Dell DUP inner_versions PCI match).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from amd_chipset_manifest import TAG_FRIENDLY, parse_devid_tags, parse_info_products
from bundle_verification import component_label_from_text
from intel_chipset_manifest import intel_inf_name_to_label

_DEVID_XML_RE = re.compile(rb"<Products\b[\s\S]*?</Products>", re.I)
_INFO_XML_RE = re.compile(rb"<Products\b[\s\S]*?</Products>", re.I)
_DUP_NS = "{openmanage/cm/dm}"


def component_label_for_device_ctx(device_ctx: dict | None) -> str:
    """Stable bundle label for the device selected for install."""
    labels = candidate_component_labels(device_ctx)
    return labels[0] if labels else ""


def candidate_component_labels(device_ctx: dict | None) -> list[str]:
    """Ordered bundle labels — most specific first (avoids I2C swallowing Serial IO, etc.)."""
    if not device_ctx:
        return []
    role = (device_ctx.get("catalog_role") or "").lower()
    if role == "gpu_companion":
        return ["NPCF"]
    blob = ""
    for key in ("target_device_name", "device_label", "display_name"):
        val = (device_ctx.get(key) or "").strip()
        if val:
            blob = val.lower()
            break
    if not blob:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        lab = (label or "").strip()
        if lab and lab not in seen and lab != "Other":
            seen.add(lab)
            out.append(lab)

    vk = (device_ctx.get("vendor_key") or "").lower()
    try:
        from catalog_device_context import (
            _device_is_amd_chipset_plumbing,
            _device_is_intel_chipset_plumbing,
        )
    except ImportError:
        _device_is_amd_chipset_plumbing = lambda _c: False  # noqa: E731
        _device_is_intel_chipset_plumbing = lambda _c: False  # noqa: E731

    if vk == "intel" and _device_is_intel_chipset_plumbing(device_ctx):
        for part, label in (
            ("serial io", "Serial IO"),
            ("management engine", "MEI"),
            ("intel smbus", "SMBus"),
            ("sata ahci", "SATA"),
            ("chipset", "Chipset INF"),
        ):
            if part in blob:
                _add(label)
    elif vk == "amd" and _device_is_amd_chipset_plumbing(device_ctx):
        for part, label in (
            ("smbus", "SMBus"),
            ("platform security", "PSP"),
            ("psp", "PSP"),
            ("gpio", "GPIO"),
            ("i2c", "I2C"),
            ("micro pep", "MicroPEP"),
            ("micropep", "MicroPEP"),
            ("provisioning", "PPM"),
            ("ppm", "PPM"),
        ):
            if part in blob:
                _add(label)

    _add(component_label_from_text(blob))
    return out


def _read_xml_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _find_named_xml(root: Path, name: str) -> bytes | None:
    target = name.lower()
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() == target:
            raw = _read_xml_bytes(path)
            if raw:
                return raw
    return None


def _find_embedded_xml(root: Path, pattern: re.Pattern[bytes]) -> bytes | None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in (".xml", ".exe", ".bin", ""):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            m = pattern.search(data)
            if m:
                return m.group(0)
    return None


def _devid_hwid_matches(devid: str, device_ctx: dict) -> bool:
    devid_u = (devid or "").strip().upper().rstrip("\\")
    if not devid_u:
        return False
    inst = (device_ctx.get("instance_id") or "").strip().upper()
    if inst and (inst.startswith(devid_u) or devid_u in inst):
        return True
    tokens = [str(t).upper() for t in (device_ctx.get("pci_tokens") or [])]
    ven = next((t[4:] for t in tokens if t.startswith("VEN_")), "")
    dev = next((t[4:] for t in tokens if t.startswith("DEV_")), "")
    if ven and dev and f"VEN_{ven}&DEV_{dev}" in devid_u.replace("\\\\", "\\"):
        return True
    return False


def amd_install_tag_for_device(device_ctx: dict, devid_xml: bytes | str) -> str:
    """Return AMD DevID.xml install tag (e.g. ``/SETSMBUS``) for *device_ctx*."""
    tags = parse_devid_tags(devid_xml)
    for row in tags:
        tag = (row.get("tag") or "").strip()
        for devid in row.get("devids") or []:
            if _devid_hwid_matches(devid, device_ctx):
                return tag
    label = component_label_for_device_ctx(device_ctx)
    if label:
        return amd_install_tag_for_label(label)
    return ""


def amd_install_tag_for_label(label: str) -> str:
    """Map a bundle short label to an AMD ``/SET*`` install tag."""
    lab = (label or "").strip().lower()
    if not lab:
        return ""
    for tag, friendly in TAG_FRIENDLY.items():
        if lab in friendly.lower() or lab in tag.lower().lstrip("/"):
            return tag
    aliases = {
        "smbus": "/SETSMBUS",
        "psp": "/SETPSP",
        "gpio": "/SETGPIO2",
        "i2c": "/SETI2C",
        "micropep": "/SETUPEP",
        "ppm": "/SETPPM",
    }
    return aliases.get(lab, "")


def amd_install_tag_from_info_xml(label: str, info_xml: bytes | str) -> str:
    """Resolve AMD Info.xml ``Installer`` tag for a component label."""
    lab = (label or "").strip().lower()
    if not lab:
        return ""
    for row in parse_info_products(info_xml, os_filter=""):
        name = (row.get("name") or "").strip()
        if component_label_from_text(name).lower() == lab or lab in name.lower():
            tag = (row.get("installer") or "").strip()
            if tag:
                return tag if tag.startswith("/") else f"/{tag}"
    return ""


def _find_dirs_for_install_tag(root: str, tag: str) -> list[str]:
    """Directories under *root* whose path matches an AMD ``/SET*`` install tag."""
    needle = (tag or "").strip().lstrip("/").upper()
    if not needle or not root:
        return []
    root_path = Path(root)
    if not root_path.exists():
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for dirpath, _dirs, files in os.walk(root_path):
        infs = [f for f in files if f.lower().endswith(".inf")]
        if not infs:
            continue
        norm = str(Path(dirpath).resolve())
        if norm in seen:
            continue
        rel_u = dirpath.replace(str(root_path), "").upper()
        score = 0
        if needle in rel_u:
            score += 100
        leaf = Path(dirpath).name.upper()
        if leaf == needle or needle in leaf:
            score += 200
        if score <= 0:
            continue
        seen.add(norm)
        depth = rel_u.count(os.sep)
        hits.append((score, depth, norm))
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [path for _score, _depth, path in hits]


def _find_intel_inf_dirs_for_label(root: str, label: str) -> list[str]:
    lab = (label or "").strip()
    if not lab or not root:
        return []
    root_path = Path(root)
    if not root_path.exists():
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for dirpath, _dirs, files in os.walk(root_path):
        infs = [f for f in files if f.lower().endswith(".inf")]
        if not infs:
            continue
        best = 0
        for inf_name in infs:
            inf_path = Path(dirpath) / inf_name
            try:
                text = inf_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if intel_inf_name_to_label(inf_name, text) == lab:
                best = max(best, 300)
            elif lab.lower() in inf_name.lower():
                best = max(best, 150)
        if best <= 0:
            continue
        norm = str(Path(dirpath).resolve())
        if norm in seen:
            continue
        seen.add(norm)
        depth = dirpath.replace(str(root_path), "").count(os.sep)
        hits.append((best, depth, norm))
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [path for _score, _depth, path in hits]


def _dup_component_name_tokens(inner_entry: dict) -> list[str]:
    name = (
        inner_entry.get("component_name")
        or inner_entry.get("name")
        or inner_entry.get("title")
        or ""
    ).strip()
    if not name:
        return []
    parts = re.split(r"[\W_]+", name.lower())
    return [p for p in parts if len(p) >= 4][:6]


def _find_dirs_for_name_tokens(root: str, tokens: list[str]) -> list[str]:
    if not tokens or not root:
        return []
    root_path = Path(root)
    if not root_path.exists():
        return []
    hits: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for dirpath, _dirs, files in os.walk(root_path):
        infs = [f for f in files if f.lower().endswith(".inf")]
        if not infs:
            continue
        rel_u = dirpath.replace(str(root_path), "").lower()
        score = sum(1 for tok in tokens if tok in rel_u)
        if score <= 0:
            continue
        norm = str(Path(dirpath).resolve())
        if norm in seen:
            continue
        seen.add(norm)
        depth = rel_u.count(os.sep)
        hits.append((score, depth, norm))
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [path for _score, _depth, path in hits]


def _matched_inner_entry(offer: dict, device_ctx: dict) -> dict | None:
    try:
        import oem_effective_version as oev
    except ImportError:
        return None
    inner = offer.get("inner_versions") or offer.get("offer_inner_versions") or []
    if not isinstance(inner, list):
        return None
    for entry in inner:
        if not isinstance(entry, dict):
            continue
        for pci in entry.get("pci") or []:
            if isinstance(pci, dict) and oev.pci_entry_matches_ctx(pci, device_ctx):
                return entry
        prefix = (entry.get("instance_id_prefix") or "").upper()
        inst = (device_ctx.get("instance_id") or "").upper()
        if prefix and inst.startswith(prefix.replace("\\\\", "\\")):
            return entry
    ver, _ = oev.pick_inner_version_for_ctx(inner, device_ctx)
    if ver:
        for entry in inner:
            if (entry.get("version") or "").strip() == ver:
                return entry
    return None


def _parse_package_dup_manifest(root: Path) -> list[dict]:
    rows: list[dict] = []
    for path in root.rglob("*.xml"):
        if not path.is_file():
            continue
        low = path.name.lower()
        if not (low.startswith("dell_") or low.startswith("alienware_") or "manifest" in low):
            continue
        try:
            text = path.read_text(encoding="utf-16", errors="replace")
            if not text.strip():
                text = path.read_text(encoding="utf-8", errors="replace")
            root_el = ET.fromstring(text)
        except (OSError, ET.ParseError):
            continue
        try:
            from catalog_oem_live import parse_dell_software_manifest_root
        except ImportError:
            continue
        rows.extend(parse_dell_software_manifest_root(root_el))
    return rows


def find_manifest_guided_inf_dirs(
    extract_root: str,
    device_ctx: dict | None,
    offer: dict | None = None,
) -> list[str]:
    """
    Locate INF directories for one bundle component using manifest metadata.

    Returns ordered directory paths (best first). Empty list → caller uses HWID scan.
    """
    if not extract_root or not device_ctx:
        return []
    offer = offer or {}
    root = Path(extract_root)
    vk = (device_ctx.get("vendor_key") or "").lower()
    hw = (device_ctx.get("hw_category") or "").lower()

    try:
        from catalog_device_context import (
            _device_is_amd_chipset_plumbing,
            _device_is_intel_chipset_plumbing,
        )
    except ImportError:
        _device_is_amd_chipset_plumbing = lambda _c: False  # noqa: E731
        _device_is_intel_chipset_plumbing = lambda _c: False  # noqa: E731

    is_amd_chipset = vk == "amd" and (
        hw == "chipset" or _device_is_amd_chipset_plumbing(device_ctx)
    )
    is_intel_chipset = vk == "intel" and _device_is_intel_chipset_plumbing(device_ctx)

    if is_intel_chipset:
        for lab in candidate_component_labels(device_ctx):
            dirs = _find_intel_inf_dirs_for_label(extract_root, lab)
            if dirs:
                return dirs

    if is_amd_chipset:
        for lab in candidate_component_labels(device_ctx):
            devid_raw = _find_named_xml(root, "DevID.xml") or _find_embedded_xml(
                root, _DEVID_XML_RE
            )
            tag = ""
            if devid_raw:
                tag = amd_install_tag_for_device(device_ctx, devid_raw)
            if not tag:
                info_raw = _find_named_xml(root, "Info.xml") or _find_embedded_xml(
                    root, _INFO_XML_RE
                )
                if info_raw:
                    tag = amd_install_tag_from_info_xml(lab, info_raw)
            if not tag:
                tag = amd_install_tag_for_label(lab)
            if tag:
                dirs = _find_dirs_for_install_tag(extract_root, tag)
                if dirs:
                    return dirs

    inner = _matched_inner_entry(offer, device_ctx)
    if inner:
        tokens = _dup_component_name_tokens(inner)
        if tokens:
            dirs = _find_dirs_for_name_tokens(extract_root, tokens)
            if dirs:
                return dirs

    if offer.get("inner_versions") or offer.get("bundle_components"):
        for row in _parse_package_dup_manifest(root):
            title = (row.get("title") or "").lower()
            dev_label = _ctx_label_blob(device_ctx)
            if title and dev_label and title in dev_label:
                rel = (row.get("url") or "").split("/")[-1].lower()
                stem = rel.replace(".exe", "").replace(".cab", "")
                if stem:
                    dirs = _find_dirs_for_name_tokens(extract_root, [stem[:12]])
                    if dirs:
                        return dirs

    bundle = offer.get("bundle_components") or []
    candidates = candidate_component_labels(device_ctx)
    if candidates and isinstance(bundle, list):
        for lab in candidates:
            for comp in bundle:
                if not isinstance(comp, dict):
                    continue
                if (comp.get("label") or "").strip() != lab:
                    continue
                hint = (comp.get("device_name") or comp.get("name") or "").strip()
                if hint:
                    tokens = [t for t in re.split(r"[\W_]+", hint.lower()) if len(t) >= 4][:4]
                    dirs = _find_dirs_for_name_tokens(extract_root, tokens)
                    if dirs:
                        return dirs

    return []


def _ctx_label_blob(device_ctx: dict) -> str:
    parts = []
    for key in ("target_device_name", "device_label", "display_name"):
        val = (device_ctx.get(key) or "").strip().lower()
        if val:
            parts.append(val)
    return " ".join(parts)


__all__ = [
    "amd_install_tag_for_device",
    "amd_install_tag_for_label",
    "amd_install_tag_from_info_xml",
    "candidate_component_labels",
    "component_label_for_device_ctx",
    "find_manifest_guided_inf_dirs",
]
