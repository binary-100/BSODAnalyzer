"""Repair lazy-patch syntax errors in extracted catalog slice modules."""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]

MODULES = [
    "catalog_download.py",
    "catalog_system_actions.py",
    "catalog_vendor_offers.py",
    "catalog_oem_offers.py",
    "catalog_ps_context.py",
    "catalog_scan_summary.py",
    "catalog_online_store.py",
    "catalog_device_comparison.py",
]

# name -> names to rewrite as _dc("name")(...) inside that module (call sites only)
LAZY_BY_MODULE: dict[str, tuple[str, ...]] = {
    "catalog_download.py": ("resolve_vendor_package_download_url", "_offer_download_kind"),
    "catalog_system_actions.py": ("run_powershell",),
    "catalog_vendor_offers.py": (
        "_VENDOR_DRIVER_URLS",
        "_manufacturer_vendor_lookup_applicable",
        "_catalog_system_ctx_from",
    ),
    "catalog_oem_offers.py": (
        "fetch_oem_catalog_for_system",
        "system_has_oem_driver_catalog",
        "_system_manufacturer_oem_url",
        "_fetch_live_oem_offers",
    ),
    "catalog_ps_context.py": (),
    "catalog_scan_summary.py": ("_v6_catalog_enabled", "_offer_version_from_fields"),
    "catalog_online_store.py": (),
    "catalog_device_comparison.py": (
        "_log_catalog_skip",
        "fetch_nvidia_driver_offer",
        "fetch_amd_driver_offers",
        "fetch_intel_driver_offers",
        "fetch_realtek_driver_offers",
        "fetch_network_vendor_offers",
        "fetch_extended_vendor_offers",
        "fetch_generic_vendor_offer",
        "fetch_oem_driver_offers",
        "fetch_microsoft_driver_offers",
        "fetch_microsoft_catalog_search_offers",
        "_amd_vendor_version_lookup_applicable",
        "_resolve_primary_installed_version",
        "_v6_catalog_enabled",
        "_EXTENDED_VENDOR_KEYS",
        "_VENDOR_DRIVER_URLS",
        "_catalog_system_ctx_from",
        "_manufacturer_vendor_lookup_applicable",
    ),
}


def fix_defs(text: str) -> str:
    return re.sub(r'def _dc\("([^"]+)"\)\(', r"def \1(", text)


def patch_calls(text: str, names: tuple[str, ...]) -> str:
    if not names:
        return text
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("def ", "async def ")):
            out.append(line)
            continue
        new_line = line
        for name in sorted(names, key=len, reverse=True):
            new_line = re.sub(
                rf"(?<![\w.\"]){re.escape(name)}\(",
                f'_dc("{name}")(',
                new_line,
            )
        out.append(new_line)
    return "".join(out)


def main() -> None:
    for fname in MODULES:
        path = APP / fname
        text = path.read_text(encoding="utf-8")
        text = fix_defs(text)
        text = patch_calls(text, LAZY_BY_MODULE.get(fname, ()))
        path.write_text(text, encoding="utf-8")
        print(f"repaired {fname}")


if __name__ == "__main__":
    main()
