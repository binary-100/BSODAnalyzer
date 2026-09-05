"""Intel Chipset INF utility package metadata — per-INF DriverVer → bundle components."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from bundle_verification import component_label_from_text

_DRIVERVER_RE = re.compile(
    r"^\s*DriverVer\s*=\s*(?:[\d/]+,\s*)?([\d.]+)",
    re.I | re.M,
)


def parse_inf_driver_version(inf_text: str) -> str:
    """Extract numeric driver version from an INF ``DriverVer`` line."""
    if not inf_text:
        return ""
    m = _DRIVERVER_RE.search(inf_text)
    return (m.group(1) or "").strip() if m else ""


def is_intel_component_inf_version(version: str) -> bool:
    """True for plumbing INF builds — excludes suite wrapper INFs (large 10.1.xxxxx builds)."""
    try:
        from catalog_scoring import (
            _intel_chipset_suite_build,
            _looks_like_intel_chipset_package_version,
        )
    except ImportError:
        return True
    if not _looks_like_intel_chipset_package_version(version):
        return True
    build = _intel_chipset_suite_build(version)
    if build is None:
        return True
    return build < 1000


def intel_inf_name_to_label(inf_name: str, inf_text: str = "") -> str:
    """Map an Intel chipset INF filename/content to a stable short label."""
    stem = Path(inf_name or "").stem.lower().replace("_", " ")
    blob = f"{stem} {(inf_text or '')[:1500]}".lower()
    if "heci" in stem or "management engine interface" in blob:
        return "MEI"
    if "serialio" in stem.replace(" ", "") or "serial io" in blob:
        return "Serial IO"
    if "smbus" in stem:
        return "SMBus"
    if "chipset" in stem and "inf" in stem:
        return "Chipset INF"
    return component_label_from_text(blob, default="Other")


def intel_infs_to_bundle_components(
    inf_entries: list[tuple[str, str]],
) -> list[dict]:
    """Normalize Intel chipset INF rows to bundle component dicts."""
    try:
        from catalog_scoring import compare_versions
    except ImportError:
        compare_versions = None  # type: ignore[assignment]

    by_label: dict[str, dict] = {}
    for inf_name, text in inf_entries or []:
        if not text:
            continue
        ver = parse_inf_driver_version(text)
        if not ver or not is_intel_component_inf_version(ver):
            continue
        label = intel_inf_name_to_label(inf_name, text)
        if label == "Other":
            continue
        row = {
            "label": label,
            "device_name": Path(inf_name).name or label,
            "version": ver,
        }
        prev = by_label.get(label)
        if not prev:
            by_label[label] = row
            continue
        if compare_versions and compare_versions(prev["version"], ver) == "older":
            by_label[label] = row
    return list(by_label.values())


def read_infs_from_zip(path: Path) -> list[tuple[str, str]]:
    """Read ``*.inf`` members from a zip package."""
    if not path.is_file() or not zipfile.is_zipfile(path):
        return []
    out: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".inf"):
                    continue
                try:
                    text = zf.read(name).decode("utf-8", errors="replace")
                except (OSError, KeyError, UnicodeError):
                    continue
                out.append((name, text))
    except (OSError, zipfile.BadZipFile):
        return []
    return out


__all__ = [
    "intel_inf_name_to_label",
    "intel_infs_to_bundle_components",
    "is_intel_component_inf_version",
    "parse_inf_driver_version",
    "read_infs_from_zip",
]
