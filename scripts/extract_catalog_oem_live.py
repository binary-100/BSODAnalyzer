"""One-shot: move live OEM fetch helpers from driver_catalog.py to catalog_oem_live.py."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "driver_catalog.py"
OEM = ROOT / "catalog_oem_live.py"

NAMES = {
    "clear_oem_cache",
    "_warm_oem_session_cache",
    "_oem_row_cache_key",
    "_cached_oem_rows",
    "_oem_live_row_warmers",
    "_system_has_msi_oem",
    "_system_has_gigabyte_oem",
    "_is_dell_driver_details_url",
    "_resolve_dell_driver_download_url",
    "_fetch_live_oem_offers",
    "_dell_service_tag",
    "_dell_dup_catalog_paths",
    "_dell_dup_display_text",
    "parse_dell_software_manifest_root",
    "_parse_dell_dup_manifest",
    "_merge_enterprise_oem_rows",
    "_get_dell_oem_rows_from_local_dup",
    "_get_dell_oem_rows_from_api",
    "_oem_search_keywords",
    "_oem_pnp_category_hints",
    "_oem_row_match_score",
    "_oem_row_eligible_for_ctx",
    "_is_generic_oem_support_row",
    "_score_oem_driver_entry",
    "_score_oem_row_for_ctx",
    "_normalize_oem_driver_row_dict",
    "_iter_oem_driver_leaf_dicts",
    "_normalize_oem_driver_rows",
    "_oem_pick_rows_for_ctx",
    "_oem_offers_from_rows",
    "system_has_oem_driver_catalog",
    "_oem_catalog_sources",
    "_oem_rows_to_catalog_offers",
    "fetch_oem_catalog_for_system",
    "_fetch_dell_oem_rows_live",
    "_merge_dell_dup_inner_versions_into_rows",
    "get_dell_oem_rows",
    "fetch_dell_oem_offers",
    "_fetch_lenovo_oem_rows_live",
    "get_lenovo_oem_rows",
    "fetch_lenovo_oem_offers",
    "_manufacturer_matches",
    "_windows_osid",
    "_oem_model_candidates",
    "_slug_for_oem_api",
    "_oem_model_slug_variants",
    "_gigabyte_support_page_urls",
    "_parse_hp_wcc_driver_details",
    "_hp_typeahead_product_hints",
    "_hp_wcc_product_specs",
    "_hp_pick_windows_os_tms_id",
    "_hp_product_number_from_model",
    "_hp_fetch_wcc_driver_rows",
    "_parse_asus_driver_json",
    "_fetch_asus_oem_rows_live",
    "get_asus_oem_rows",
    "fetch_asus_oem_offers",
    "_parse_msi_driver_json",
    "_fetch_msi_oem_rows_live",
    "get_msi_oem_rows",
    "fetch_msi_oem_offers",
    "_gigabyte_support_slug",
    "_parse_gigabyte_support_html",
    "_fetch_gigabyte_oem_rows_live",
    "get_gigabyte_oem_rows",
    "_parse_gigabyte_bios_html",
    "get_gigabyte_bios_rows",
    "_walk_json_for_bios_rows",
    "_extract_json_blobs_from_html",
    "_parse_acer_bios_html",
    "get_acer_bios_rows",
    "fetch_gigabyte_oem_offers",
    "_parse_acer_driver_html",
    "_fetch_acer_oem_rows_live",
    "get_acer_oem_rows",
    "fetch_acer_oem_offers",
    "_fetch_hp_oem_rows_live",
    "get_hp_oem_rows",
    "fetch_hp_oem_offers",
}

ASSIGN_NAMES = {
    "_DELL_SERVICE_TAG_PS_CACHE",
    "_DELL_DUP_NS",
    "_KNOWN_OEM_PC_MAKERS",
    "_DELL_DRIVER_ID_RE",
    "_DELL_FILE_LOCATION_RE",
    "_DELL_DL_DIRECT_RE",
}

MODULE_HEADER = '''\
"""Live OEM API fetch and row cache (extracted from driver_catalog)."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import oem_effective_version as oev
from catalog_scoring import (
    compare_versions,
    extract_version_from_text,
    parse_driver_version,
)

_HTTP_TIMEOUT = 22
_OEM_MIN_MATCH_SCORE = 5


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

_LAZY_DC_FUNCS = (
    "_log_catalog_skip",
    "_run_catalog_ps",
    "_http_get",
    "_vendor_fetch_get",
    "catalog_user_agent",
    "_ctx_device_label",
    "_shared_catalog_row_rejects",
    "_nvidia_is_audio_or_usb_component",
    "_normalize_oem_date",
    "_v6_catalog_enabled",
    "_lru_cache_touch",
    "_lru_cache_set",
    "clear_vendor_scrape_cache",
)

_LAZY_DC_GLOBALS = (
    "_oem_session_cache_enabled",
    "_CATALOG_CACHE_LOCK",
    "_OEM_ROWS_CACHE",
    "_OEM_CACHE_TTL_SEC",
    "_OEM_CACHE_MAX_ENTRIES",
    "_quick_check_mode",
)


def _patch_lazy_refs(source: str) -> str:
    for name in _LAZY_DC_FUNCS:
        source = source.replace(f"{name}(", f"_dc('{name}')(")
    for name in _LAZY_DC_GLOBALS:
        source = re.sub(rf"\b{name}\b", f"_dc('{name}')", source)
    return source


RE_EXPORTS = """from catalog_oem_live import (
    clear_oem_cache,
    fetch_acer_oem_offers,
    fetch_asus_oem_offers,
    fetch_dell_oem_offers,
    fetch_gigabyte_oem_offers,
    fetch_hp_oem_offers,
    fetch_lenovo_oem_offers,
    fetch_msi_oem_offers,
    fetch_oem_catalog_for_system,
    get_acer_bios_rows,
    get_acer_oem_rows,
    get_asus_oem_rows,
    get_dell_oem_rows,
    get_gigabyte_bios_rows,
    get_gigabyte_oem_rows,
    get_hp_oem_rows,
    get_lenovo_oem_rows,
    get_msi_oem_rows,
    parse_dell_software_manifest_root,
    system_has_oem_driver_catalog,
    _cached_oem_rows,
    _dell_service_tag,
    _fetch_dell_oem_rows_live,
    _fetch_live_oem_offers,
    _get_dell_oem_rows_from_api,
    _get_dell_oem_rows_from_local_dup,
    _is_dell_driver_details_url,
    _manufacturer_matches,
    _merge_enterprise_oem_rows,
    _oem_live_row_warmers,
    _oem_offers_from_rows,
    _oem_row_cache_key,
    _oem_rows_to_catalog_offers,
    _parse_dell_dup_manifest,
    _resolve_dell_driver_download_url,
    _system_has_gigabyte_oem,
    _system_has_msi_oem,
    _warm_oem_session_cache,
    _DELL_DRIVER_ID_RE,
    _DELL_DL_DIRECT_RE,
    _DELL_FILE_LOCATION_RE,
)
"""


def main() -> int:
    src = CATALOG.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    extracted: list[tuple[int, str]] = []
    remove_ranges: list[tuple[int, int]] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name not in NAMES:
                continue
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            chunk = _patch_lazy_refs("".join(lines[start:end]))
            extracted.append((start, chunk))
            remove_ranges.append((start, end))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ASSIGN_NAMES:
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    extracted.append((start, "".join(lines[start:end]) + "\n"))
                    remove_ranges.append((start, end))

    found_funcs = {
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name in NAMES
    }
    missing = NAMES - found_funcs
    if missing:
        print(f"Missing defs: {sorted(missing)}", file=sys.stderr)
        return 1

    if OEM.is_file() and "def fetch_dell_oem_offers(" in OEM.read_text(encoding="utf-8"):
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extracted.sort(key=lambda x: x[0])
    body = "\n\n".join(c.rstrip() for _, c in extracted) + "\n"
    OEM.write_text(MODULE_HEADER + body, encoding="utf-8")

    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]
    CATALOG.write_text("".join(new_lines), encoding="utf-8")

    cat = CATALOG.read_text(encoding="utf-8")
    if "from catalog_oem_live import (" not in cat:
        anchor = "from catalog_offer_pipeline import ("
        idx = cat.find(anchor)
        if idx == -1:
            print("Could not find insert point for oem imports", file=sys.stderr)
            return 1
        cat = cat[:idx] + RE_EXPORTS + "\n" + cat[idx:]
        CATALOG.write_text(cat, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into catalog_oem_live.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
