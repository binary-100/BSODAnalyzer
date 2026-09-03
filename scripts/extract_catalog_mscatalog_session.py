"""One-shot: move MSCatalog session / GUI warm helpers from driver_catalog.py."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "driver_catalog.py"
SESSION = ROOT / "catalog_mscatalog_session.py"

NAMES = {
    "_cap_session_rows",
    "peek_session_rows_truncated",
    "set_gui_application_mode",
    "set_gui_catalog_session",
    "_gui_catalog_session_active",
    "_gui_catalog_mode",
    "_gui_online_store_warm_active",
    "_gui_catalog_parallel_workers",
    "_gui_batched_online_store_enabled",
    "_gui_batched_online_store_include_all",
    "_gui_mscatalog_prewarm_enabled",
    "_gui_mscatalog_batched_parallel_enabled",
    "_gui_mscatalog_parallel_throttle",
    "_gui_mscatalog_parallel_chunk",
    "_peek_online_driver_store_cache",
    "_unique_hwids_from_device_contexts",
    "_device_contexts_missing_hwid",
    "begin_batch_mscatalog_query_cache",
    "clear_batch_mscatalog_query_cache",
    "clear_install_probe_cache",
    "_lazy_load_online_driver_store_all",
    "warm_batched_microsoft_online_store",
    "_unique_mscatalog_queries_from_device_contexts",
    "warm_batched_mscatalog_queries",
    "_warm_mscatalog_parallel",
    "_should_skip_online_driver_store",
    "_allow_per_hwid_online_store",
    "_online_store_hwid_candidates",
    "configure_catalog",
    "catalog_include_preview_updates",
    "is_quick_check_mode",
    "clear_wu_driver_cache",
    "set_mscatalog_startup_notice",
    "consume_mscatalog_startup_notice",
    "_fetch_online_driver_store_rows_uncached",
    "_rebuild_online_store_class_buckets",
    "_get_cached_online_driver_store_rows",
    "_parse_online_driver_store_hwid_batch_json",
    "_fetch_online_driver_store_for_hwids_batch",
    "_fetch_online_driver_store_for_hwid",
    "_get_cached_online_driver_store_for_ctx",
    "_fetch_wu_driver_rows_uncached",
    "fetch_wu_driver_rows_deep",
    "_get_cached_wu_driver_rows",
    "app_set_allows_persist",
    "persist_session_catalog_cache",
    "oem_session_warmed_vendor_tags",
    "oem_offers_from_session_cache",
    "_v6_catalog_enabled",
    "ensure_mscatalog_module_ready",
    "_search_mscatalog_updates_cached",
    "_gui_gap_catalog_fallback_enabled",
}

NAMES.discard("warm_bscatalog_queries")  # no-op safety

ASSIGN_NAMES = {
    "_WU_DRIVER_ROWS_CACHE",
    "_WU_DRIVER_CACHE_AT",
    "_WU_DRIVER_CACHE_TTL_SEC",
    "_SESSION_ROWS_CAP",
    "_last_session_rows_truncated",
    "_last_session_rows_original_count",
    "_ONLINE_DRIVER_STORE_CACHE",
    "_ONLINE_DRIVER_STORE_CACHE_AT",
    "_ONLINE_DRIVER_STORE_CACHE_TTL_SEC",
    "_ONLINE_DRIVER_STORE_LOCK",
    "_ONLINE_DRIVER_STORE_CLASS_BUCKETS",
    "_PNP_TO_STORE_CLASSES",
    "_PNPSIGNED_DRIVER_CACHE",
    "_PNPSIGNED_DRIVER_CACHE_AT",
    "_PNPSIGNED_DRIVER_CACHE_TTL_SEC",
    "_quick_check_mode",
    "_catalog_include_preview",
    "_GUI_BATCH_MAX_WORKERS",
    "_GUI_DEVICE_SCAN_BATCH_SIZE",
    "_GUI_ONLINE_HWID_WARM_BATCH_SIZE",
    "_GUI_BATCH_INTER_PAUSE_SEC",
    "_GUI_APPLICATION_MODE",
    "_GUI_ONLINE_WARM_DEPTH",
    "_GUI_ONLINE_WARM_LOCK",
    "_ONLINE_HWID_STORE_CACHE",
    "_ONLINE_HWID_STORE_CACHE_TTL_SEC",
    "_ONLINE_HWID_STORE_CACHE_MAX",
    "_ONLINE_STORE_ALL_TIMEOUT_SEC",
    "_ONLINE_STORE_ALL_LOAD_LOCK",
    "_BATCH_MSCATALOG_QUERY_CACHE",
    "_BATCH_MSCATALOG_LOCK",
    "_INSTALL_PROBE_CACHE",
    "_GUI_CATALOG_SESSION_DEPTH",
    "_GUI_CATALOG_SESSION_LOCK",
    "_MSCATALOG_STARTUP_NOTICE",
    "_WU_DRIVER_SEARCH_CRITERIA",
    "_OEM_TAG_LABELS",
}

MODULE_HEADER = '''\
"""GUI catalog session flags, MSCatalog batch cache, and online/WU store warm (extracted)."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from collections import OrderedDict
from typing import Callable


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

_LAZY_DC_FUNCS = (
    "_log_catalog_skip",
    "_run_catalog_ps",
    "_lru_cache_touch",
    "_lru_cache_set",
    "clear_vendor_scrape_cache",
    "_is_primary_gpu_display_manufacturer_authoritative",
    "_catalog_search_queries_for_ctx",
    "_oem_live_row_warmers",
    "_oem_row_cache_key",
    "_oem_rows_to_catalog_offers",
    "_dell_service_tag",
)

_LAZY_DC_GLOBALS = (
    "_oem_session_cache_enabled",
    "_CATALOG_CACHE_LOCK",
    "_OEM_ROWS_CACHE",
    "_OEM_CACHE_TTL_SEC",
    "_VENDOR_SCRAPE_CACHE",
)


def _patch_lazy_refs(source: str) -> str:
    for name in _LAZY_DC_FUNCS:
        source = source.replace(f"{name}(", f"_dc('{name}')(")
    for name in _LAZY_DC_GLOBALS:
        source = re.sub(rf"\b{name}\b", f"_dc('{name}')", source)
    return source


RE_EXPORTS = """from catalog_mscatalog_session import (
    app_set_allows_persist,
    begin_batch_mscatalog_query_cache,
    catalog_include_preview_updates,
    clear_batch_mscatalog_query_cache,
    clear_install_probe_cache,
    clear_wu_driver_cache,
    configure_catalog,
    consume_mscatalog_startup_notice,
    ensure_mscatalog_module_ready,
    fetch_wu_driver_rows_deep,
    is_quick_check_mode,
    oem_offers_from_session_cache,
    oem_session_warmed_vendor_tags,
    peek_session_rows_truncated,
    persist_session_catalog_cache,
    set_gui_application_mode,
    set_gui_catalog_session,
    set_mscatalog_startup_notice,
    warm_batched_microsoft_online_store,
    warm_batched_mscatalog_queries,
    _allow_per_hwid_online_store,
    _cap_session_rows,
    _fetch_online_driver_store_for_hwid,
    _fetch_online_driver_store_for_hwids_batch,
    _fetch_wu_driver_rows_uncached,
    _get_cached_online_driver_store_for_ctx,
    _get_cached_online_driver_store_rows,
    _get_cached_wu_driver_rows,
    _gui_application_mode_active,
    _gui_batched_online_store_enabled,
    _gui_catalog_mode,
    _gui_catalog_session_active,
    _gui_gap_catalog_fallback_enabled,
    _lazy_load_online_driver_store_all,
    _online_store_hwid_candidates,
    _peek_online_driver_store_cache,
    _search_mscatalog_updates_cached,
    _should_skip_online_driver_store,
    _v6_catalog_enabled,
    _warm_mscatalog_parallel,
)
"""


def _assign_target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


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
                name = _assign_target_name(t)
                if name and name in ASSIGN_NAMES:
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    extracted.append((start, "".join(lines[start:end]) + "\n"))
                    remove_ranges.append((start, end))
                    break
        elif isinstance(node, ast.AnnAssign):
            name = _assign_target_name(node.target)
            if name and name in ASSIGN_NAMES:
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

    if SESSION.is_file() and "def set_gui_application_mode(" in SESSION.read_text(encoding="utf-8"):
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extracted.sort(key=lambda x: x[0])
    body = "\n\n".join(c.rstrip() for _, c in extracted) + "\n"

    getter = (
        "\n\ndef _gui_application_mode_active() -> bool:\n"
        "    return _GUI_APPLICATION_MODE\n"
    )
    SESSION.write_text(MODULE_HEADER + body + getter, encoding="utf-8")

    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]
    CATALOG.write_text("".join(new_lines), encoding="utf-8")

    cat = CATALOG.read_text(encoding="utf-8")
    if "from catalog_mscatalog_session import (" not in cat:
        anchor = "from catalog_oem_live import ("
        idx = cat.find(anchor)
        if idx == -1:
            print("Could not find insert point for session imports", file=sys.stderr)
            return 1
        cat = cat[:idx] + RE_EXPORTS + "\n" + cat[idx:]
        CATALOG.write_text(cat, encoding="utf-8")

    # Replace direct _quick_check_mode reads in driver_catalog with is_quick_check_mode().
    cat = CATALOG.read_text(encoding="utf-8")
    cat = re.sub(r"(?<![\w.])_quick_check_mode(?!\s*=)", "is_quick_check_mode()", cat)
    cat = re.sub(r"\b_GUI_APPLICATION_MODE\b", "_gui_application_mode_active()", cat)
    CATALOG.write_text(cat, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into catalog_mscatalog_session.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
